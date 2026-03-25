"""
Fine-tune Qwen2.5-3B with mlx-tune (Apple Silicon MLX) + LoRA.

mlx-tune is a community-built Unsloth-compatible fine-tuning library for
Apple Silicon. It uses the same FastLanguageModel / SFTTrainer API as Unsloth
but runs natively on MLX — no CUDA, no Triton required.

  Unsloth (CUDA):       from unsloth import FastLanguageModel
  mlx-tune (Apple Si):  from mlx_tune import FastLanguageModel   ← same API

Usage:
  python train.py [--epochs 3] [--batch-size 2] [--output ./checkpoints]

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
from pathlib import Path

log = logging.getLogger("train")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_OUTPUT = Path(__file__).parent / "checkpoints"

# mlx-community hosts MLX-quantized models — use 4-bit for 16GB RAM
BASE_MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"

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

def train(epochs: int, batch_size: int, output_dir: Path, max_seq_length: int):
    try:
        # mlx-tune mirrors the Unsloth API — just change the import source
        from mlx_tune import FastLanguageModel, SFTTrainer, SFTConfig  # type: ignore
        from datasets import Dataset  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}\n"
            "Run: pip install -r requirements-train.txt"
        ) from e

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Load base model from mlx-community (pre-quantized for Apple Silicon) ---
    log.info("Loading base model: %s", BASE_MODEL)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
    )

    # --- Apply LoRA (identical API to Unsloth) ---
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

    # --- Build dataset ---
    raw = load_all_data()
    if not raw:
        raise SystemExit(
            "No training data found in data/. "
            "Run generate_data.py first."
        )
    log.info("Total training examples: %d", len(raw))

    dataset = Dataset.from_dict({"text": [format_example(ex) for ex in raw]})

    # --- Train (SFTTrainer API identical to Unsloth/TRL) ---
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=max(1, 4 // batch_size),
            num_train_epochs=epochs,
            learning_rate=2e-4,
            logging_steps=10,
            save_strategy="epoch",
            output_dir=str(output_dir),
            warmup_ratio=0.05,
            lr_scheduler_type="cosine",
            seed=42,
        ),
    )

    log.info("Starting training (%d epochs, batch size %d) on Apple Silicon MLX...", epochs, batch_size)
    trainer.train()
    log.info("Training complete.")

    # --- Save in MLX format (primary — used by mlx-lm inference server) ---
    mlx_path = output_dir / "mlx-model"
    model.save_pretrained(str(mlx_path))
    tokenizer.save_pretrained(str(mlx_path))
    log.info("MLX model saved to %s", mlx_path)
    log.info("Copy to server: cp -r %s ../llm-server/model/mlx-model", mlx_path)

    # --- Also save merged model for optional GGUF export ---
    merged_path = output_dir / "merged"
    model.save_pretrained_merged(str(merged_path), tokenizer, save_method="merged_16bit")
    log.info("Merged (16-bit) model saved to %s (use export_gguf.py if GGUF needed)", merged_path)


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
    parser = argparse.ArgumentParser(description="Fine-tune Qwen2.5-3B with Unsloth")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    args = parser.parse_args()
    train(args.epochs, args.batch_size, args.output, args.max_seq_length)


if __name__ == "__main__":
    main()
