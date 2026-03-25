"""
Fine-tune Qwen2.5-3B with Unsloth + LoRA (SFTTrainer).

Usage:
  python train.py [--epochs 3] [--batch-size 2] [--output ./checkpoints]

Requirements:
  pip install -r requirements-train.txt

Notes:
- Trains on all JSONL files in data/
- Uses Alpaca-format: instruction / input / output fields
- Saves LoRA adapter + merged model to ./checkpoints/
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
BASE_MODEL = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"

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
        from unsloth import FastLanguageModel  # type: ignore
        from datasets import Dataset  # type: ignore
        from trl import SFTTrainer, SFTConfig  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}\n"
            "Run: pip install -r requirements-train.txt"
        ) from e

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Load base model ---
    log.info("Loading base model: %s", BASE_MODEL)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=max_seq_length,
        dtype=None,         # auto-detect (bfloat16 on Apple Silicon)
        load_in_4bit=True,
    )

    # --- Apply LoRA ---
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
        use_gradient_checkpointing="unsloth",
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

    # --- Train ---
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
            fp16=False,
            bf16=True,
            logging_steps=10,
            save_strategy="epoch",
            output_dir=str(output_dir),
            warmup_ratio=0.05,
            lr_scheduler_type="cosine",
            seed=42,
        ),
    )

    log.info("Starting training (%d epochs, batch size %d)...", epochs, batch_size)
    trainer.train()
    log.info("Training complete.")

    # --- Save LoRA adapter ---
    adapter_path = output_dir / "lora-adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    log.info("LoRA adapter saved to %s", adapter_path)

    # --- Save merged model (for GGUF export) ---
    merged_path = output_dir / "merged"
    model.save_pretrained_merged(str(merged_path), tokenizer, save_method="merged_16bit")
    log.info("Merged model saved to %s", merged_path)


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
