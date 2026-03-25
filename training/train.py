"""
Fine-tune an instruction-tuned model with mlx-tune (Apple Silicon MLX) + LoRA.

mlx-tune is a community-built Unsloth-compatible fine-tuning library for
Apple Silicon. It uses the same FastLanguageModel / SFTTrainer API as Unsloth
but runs natively on MLX — no CUDA, no Triton required.

  Unsloth (CUDA):       from unsloth import FastLanguageModel
  mlx-tune (Apple Si):  from mlx_tune import FastLanguageModel   ← same API

Usage:
  python train.py [--model <model_id>] [--epochs 3] [--batch-size 2] [--output ./checkpoints]

Recommended models (all available pre-quantised on mlx-community):

  Model                                           Size   Speed   Quality
  ─────────────────────────────────────────────────────────────────────
  mlx-community/Meta-Llama-3.1-8B-Instruct-4bit  ~4 GB  medium  ★★★★★  (default)
  mlx-community/Mistral-7B-Instruct-v0.3-4bit    ~3.5GB medium  ★★★★☆
  mlx-community/Phi-3.5-mini-instruct-4bit        ~2 GB  fast    ★★★★☆
  mlx-community/Qwen2.5-3B-Instruct-4bit          ~1.5GB fast    ★★★☆☆

All fit comfortably in 16 GB RAM including LoRA training overhead.

Requirements:
  pip install -r requirements-train.txt   # installs mlx-tune, mlx, mlx-lm

Notes:
- Trains on all JSONL files in data/
- Uses Alpaca-format: instruction / input / output fields
- Saves LoRA adapter + merged model to ./checkpoints/
- Model is saved in MLX format for use with mlx-lm inference server
- Optionally export to GGUF with export_gguf.py for llama.cpp cross-platform use
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("train")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_OUTPUT = Path(__file__).parent / "checkpoints"

# Default: Llama 3.1 8B — best balance of quality and speed on M-series Macs.
# Override with --model (see docstring for alternatives).
DEFAULT_MODEL = "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit"

# Batch size recommendation per model size:
#   8B → batch 2, grad_accum 2  (effective 4)
#   7B → batch 2, grad_accum 2
#   3-4B → batch 4, grad_accum 1
DEFAULT_BATCH = 1   # 1 is safest on MacBook Air (passive cooling, 16 GB)
                    # bump to 2 on MacBook Pro / Mac Studio

ALPACA_TEMPLATE = """\
Below is an instruction that describes a task, paired with an input that provides further context. \
Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_data() -> list[dict]:
    examples = []
    for path in DATA_DIR.glob("*.jsonl"):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ex = json.loads(line)
                        if all(k in ex for k in ("instruction", "input", "output")):
                            examples.append(ex)
                    except json.JSONDecodeError:
                        pass
        log.info("Loaded from %s: %d total examples so far", path.name, len(examples))
    return examples


def format_example(example: dict) -> str:
    output = example["output"]
    if isinstance(output, (dict, list)):
        output = json.dumps(output, ensure_ascii=False)
    return ALPACA_TEMPLATE.format(
        instruction=example["instruction"],
        input=example["input"],
        output=output,
    )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(epochs: int, batch_size: int, output_dir: Path,
          max_seq_length: int, model_name: str, cooldown_secs: int):
    try:
        from mlx_tune import FastLanguageModel, SFTTrainer, SFTConfig  # type: ignore
        from datasets import Dataset  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}\n"
            "Run: pip install -r requirements-train.txt"
        ) from e

    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading base model: %s", model_name)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
    )

    # LoRA r=16: good quality, low thermal load (avoid r=64+ on Air)
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        random_state=42,
    )
    log.info("LoRA applied. Trainable parameters: %s", _count_params(model))

    raw = load_all_data()
    if not raw:
        raise SystemExit("No training data found in data/. Run generate_data.py first.")
    log.info("Total training examples: %d", len(raw))
    dataset = Dataset.from_dict({"text": [format_example(ex) for ex in raw]})

    # Effective batch = batch_size × grad_accum_steps
    # With batch=1, grad_accum=4 → effective batch of 4 (same quality, less RAM burst)
    grad_accum = max(1, 4 // batch_size)

    # ── Epoch loop with optional cool-down ───────────────────────────────
    # We train 1 epoch at a time so we can insert a thermal cool-down pause
    # between epochs. On a MacBook Air this prevents sustained throttling
    # and gives consistent tokens/sec throughout the run.
    log.info(
        "Training: %d epochs × 1, batch=%d, grad_accum=%d (effective batch %d)",
        epochs, batch_size, grad_accum, batch_size * grad_accum,
    )
    if cooldown_secs > 0:
        log.info("Cool-down between epochs: %d s  (disable with --cooldown 0)", cooldown_secs)

    for epoch in range(1, epochs + 1):
        log.info("─── Epoch %d / %d ───", epoch, epochs)
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            args=SFTConfig(
                dataset_text_field="text",
                max_seq_length=max_seq_length,
                per_device_train_batch_size=batch_size,
                gradient_accumulation_steps=grad_accum,
                num_train_epochs=1,          # one epoch per trainer call
                learning_rate=2e-4,
                logging_steps=20,
                save_strategy="no",          # we save manually below
                eval_strategy="no",          # no eval — reduces heat spikes
                output_dir=str(output_dir),
                warmup_ratio=0.05 if epoch == 1 else 0.0,   # warmup first epoch only
                lr_scheduler_type="cosine",
                seed=42 + epoch,
            ),
        )
        trainer.train()

        # Save checkpoint after every epoch so a crash / forced stop loses nothing
        ckpt = output_dir / f"checkpoint-epoch{epoch}"
        model.save_pretrained(str(ckpt))
        tokenizer.save_pretrained(str(ckpt))
        log.info("Checkpoint saved → %s", ckpt)

        if epoch < epochs and cooldown_secs > 0:
            log.info(
                "Cooling down for %d s before next epoch "
                "(tip: keep lid open, place on a cold hard surface)…",
                cooldown_secs,
            )
            time.sleep(cooldown_secs)

    log.info("Training complete.")

    # Final save in MLX format for the inference server
    mlx_path = output_dir / "mlx-model"
    model.save_pretrained(str(mlx_path))
    tokenizer.save_pretrained(str(mlx_path))
    log.info("MLX model saved → %s", mlx_path)
    log.info("Copy to server:  cp -r %s ../llm-server/model/mlx-model", mlx_path)
    log.info("Start server:    cd ../llm-server && uvicorn server:app --host 127.0.0.1 --port 8000")

    # Merged 16-bit for optional GGUF export
    merged_path = output_dir / "merged"
    model.save_pretrained_merged(str(merged_path), tokenizer, save_method="merged_16bit")
    log.info("Merged model → %s  (use export_gguf.py if GGUF needed)", merged_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_params(model) -> str:
    try:
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        return f"{trainable:,} / {total:,} ({100*trainable/total:.1f}%)"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune a model for the murder mystery game on Apple Silicon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "mlx-community model ID to fine-tune. Options:\n"
            "  mlx-community/Meta-Llama-3.1-8B-Instruct-4bit  (default, recommended)\n"
            "  mlx-community/Mistral-7B-Instruct-v0.3-4bit\n"
            "  mlx-community/Phi-3.5-mini-instruct-4bit\n"
            "  mlx-community/Qwen2.5-3B-Instruct-4bit"
        ),
    )
    parser.add_argument("--epochs",          type=int,  default=3)
    parser.add_argument("--batch-size",      type=int,  default=DEFAULT_BATCH)
    parser.add_argument("--output",          type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-seq-length",  type=int,  default=2048)
    parser.add_argument(
        "--cooldown",
        type=int, default=300,
        metavar="SECS",
        help=(
            "Seconds to pause between epochs for the chip to cool down. "
            "Default: 300 (5 min) — recommended for MacBook Air. "
            "Set to 0 to disable (MacBook Pro / Mac Studio)."
        ),
    )
    args = parser.parse_args()
    train(args.epochs, args.batch_size, args.output, args.max_seq_length,
          args.model, args.cooldown)


if __name__ == "__main__":
    main()
