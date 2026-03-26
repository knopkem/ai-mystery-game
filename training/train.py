"""
Fine-tune an instruction-tuned model with LoRA. Supports Apple Silicon (MLX),
NVIDIA CUDA, and AMD ROCm — backend is auto-detected or set via --backend.

  Backend   Library      Hardware
  ────────────────────────────────────────────────────────
  mlx       mlx-tune     Apple Silicon (M1/M2/M3/M4)
  cuda      Unsloth+TRL  NVIDIA GPU (RTX, A100, H100 …)
  rocm      Unsloth+TRL  AMD GPU (RX 7900, MI300 …)

Usage:
  python train.py [--model <id_or_path>] [--epochs 3] [--batch-size 2]
  python train.py --backend cuda --model unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit

Requirements (install the right file for your hardware):
  Apple Silicon:  pip install -r requirements-train.txt
  NVIDIA CUDA:    pip install torch ... --index-url .../cu124
                  pip install -r requirements-train-cuda.txt
  AMD ROCm:       pip install torch ... --index-url .../rocm6.2
                  pip install -r requirements-train-rocm.txt

Recommended models:

  [MLX — Apple Silicon]
  mlx-community/Meta-Llama-3.1-8B-Instruct-4bit  ~4 GB   ★★★★★  (default)
  mlx-community/Mistral-7B-Instruct-v0.3-4bit    ~3.5 GB ★★★★☆
  mlx-community/Phi-3.5-mini-instruct-4bit        ~2 GB   ★★★★☆
  mlx-community/Qwen2.5-3B-Instruct-4bit          ~1.5 GB ★★★☆☆

  [CUDA / ROCm — GPU]
  unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit    ~5 GB VRAM ★★★★★  (default)
  unsloth/mistral-7b-instruct-v0.3-bnb-4bit       ~5 GB VRAM ★★★★☆
  unsloth/Phi-3.5-mini-instruct-bnb-4bit          ~3 GB VRAM ★★★★☆
  unsloth/Qwen2.5-3B-Instruct-bnb-4bit            ~2 GB VRAM ★★★☆☆

Notes:
- Trains on all JSONL files in data/
- Uses Alpaca-format: instruction / input / output fields
- MLX: saves mlx-model/ (for mlx-lm server) + merged/ (for GGUF export)
- GPU:  saves lora-adapters/ + merged/ — run export_gguf.py for GGUF
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import time
from pathlib import Path

log = logging.getLogger("train")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_OUTPUT = Path(__file__).parent / "checkpoints"

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def detect_backend(override: str | None = None) -> str:
    """Detect the best available training backend.

    Returns one of: 'mlx', 'cuda', 'rocm'.  Raises SystemExit for 'cpu' since
    full LoRA fine-tuning without a GPU/NPU is impractically slow.
    """
    if override and override != "auto":
        return override.lower()

    # Apple Silicon: prefer MLX when available
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx  # noqa: F401
            return "mlx"
        except ImportError:
            log.warning("Apple Silicon detected but mlx not installed — checking for GPU...")

    # NVIDIA or AMD GPU via PyTorch
    try:
        import torch  # noqa: F401
        if torch.cuda.is_available():
            if getattr(torch.version, "hip", None) is not None:
                return "rocm"
            return "cuda"
    except ImportError:
        pass

    raise SystemExit(
        "No supported training backend found.\n"
        "  Apple Silicon: pip install -r requirements-train.txt\n"
        "  NVIDIA CUDA:   pip install -r requirements-train-cuda.txt\n"
        "  AMD ROCm:      pip install -r requirements-train-rocm.txt"
    )


# Detect at import time so DEFAULT_MODEL / DEFAULT_BATCH can use it.
# Can be overridden later via --backend; the final value is passed into train().
_DETECTED_BACKEND = detect_backend()

# ---------------------------------------------------------------------------
# Per-backend defaults
# ---------------------------------------------------------------------------

_LOCAL_MLX_PATH = Path(__file__).parent.parent / "llm-server" / "model" / "mlx-model"
_LOCAL_HF_PATH  = Path(__file__).parent.parent / "llm-server" / "model" / "hf-model"

_DEFAULT_MODELS = {
    "mlx":  (
        str(_LOCAL_MLX_PATH)
        if (_LOCAL_MLX_PATH / "config.json").exists()
        else "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit"
    ),
    "cuda": (
        str(_LOCAL_HF_PATH)
        if (_LOCAL_HF_PATH / "config.json").exists()
        else "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
    ),
    "rocm": (
        str(_LOCAL_HF_PATH)
        if (_LOCAL_HF_PATH / "config.json").exists()
        else "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
    ),
}

DEFAULT_MODEL = _DEFAULT_MODELS[_DETECTED_BACKEND]

# Batch size defaults: Apple Silicon (passive cooling + shared memory) needs 1;
# GPU benefits from larger batches — 2 is a safe conservative start.
DEFAULT_BATCH = 1 if _DETECTED_BACKEND == "mlx" else 2

# Load HF_TOKEN from llm-server/.env if not already in the environment
_env_file = Path(__file__).parent.parent / "llm-server" / ".env"
if "HF_TOKEN" not in os.environ and _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if _line.startswith("HF_TOKEN="):
            os.environ["HF_TOKEN"] = _line.split("=", 1)[1].strip().strip('"').strip("'")
            log.info("HF_TOKEN loaded from llm-server/.env")
            break

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
          max_seq_length: int, model_name: str, cooldown_secs: int, backend: str):
    if backend == "mlx":
        try:
            from mlx_tune import FastLanguageModel, SFTTrainer, SFTConfig  # type: ignore
            import datasets as _datasets
            _datasets.disable_caching()   # avoids dill/Python-3.14 fingerprint crash
            from datasets import Dataset  # type: ignore
        except ImportError as e:
            raise SystemExit(
                f"Missing dependency: {e}\n"
                "Run: pip install -r requirements-train.txt"
            ) from e
    elif backend in ("cuda", "rocm"):
        try:
            from unsloth import FastLanguageModel  # type: ignore
            from trl import SFTTrainer, SFTConfig  # type: ignore
            from datasets import Dataset  # type: ignore
        except ImportError as e:
            req = f"requirements-train-{backend}.txt"
            raise SystemExit(
                f"Missing dependency: {e}\n"
                f"Run: pip install -r {req}  (install PyTorch first — see that file)"
            ) from e
    else:
        raise SystemExit(f"Unsupported backend: {backend!r}. Use mlx, cuda, or rocm.")

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
    # between epochs. Useful on passive-cooled devices (MacBook Air) to prevent
    # sustained throttling; set --cooldown 0 to skip on GPU / actively cooled systems.
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
                # Step-level saves: LoRA adapters are ~50-100MB so saving
                # every 50 steps is cheap. On a crash/OOM you lose at most
                # 50 steps rather than the whole epoch.
                # save_total_limit=3 keeps only the last 3 to avoid disk bloat.
                save_strategy="steps",
                save_steps=50,
                save_total_limit=3,
                eval_strategy="no",          # no eval — reduces heat spikes
                output_dir=str(output_dir / f"steps-epoch{epoch}"),
                warmup_ratio=0.05 if epoch == 1 else 0.0,
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
            log.info("Cooling down for %d s before next epoch…", cooldown_secs)
            time.sleep(cooldown_secs)

    log.info("Training complete.")

    if backend == "mlx":
        # Save in MLX format for direct use with the mlx-lm inference server
        mlx_path = output_dir / "mlx-model"
        model.save_pretrained(str(mlx_path))
        tokenizer.save_pretrained(str(mlx_path))
        log.info("MLX model saved → %s", mlx_path)
        log.info("Copy to server:  cp -r %s ../llm-server/model/mlx-model", mlx_path)
        log.info("Start server:    cd ../llm-server && uvicorn server:app --host 127.0.0.1 --port 8000")
    else:
        # Save LoRA adapters in HuggingFace format
        lora_path = output_dir / "lora-adapters"
        model.save_pretrained(str(lora_path))
        tokenizer.save_pretrained(str(lora_path))
        log.info("LoRA adapters saved → %s", lora_path)

    # Merged 16-bit for GGUF export (all backends)
    merged_path = output_dir / "merged"
    model.save_pretrained_merged(str(merged_path), tokenizer, save_method="merged_16bit")
    log.info("Merged model → %s", merged_path)
    if backend != "mlx":
        log.info("Run export_gguf.py to convert to GGUF for the llama-cpp inference server")


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
        description="Fine-tune a model for the murder mystery game (MLX / CUDA / ROCm)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "mlx", "cuda", "rocm"],
        help=(
            "Training backend. Default: auto (detect from hardware).\n"
            "  mlx   — Apple Silicon via mlx-tune\n"
            "  cuda  — NVIDIA GPU via Unsloth+TRL\n"
            "  rocm  — AMD GPU via Unsloth+TRL"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,  # resolved after --backend is parsed
        help=(
            "Local path or HuggingFace model ID to fine-tune.\n"
            "Defaults (auto-selected per backend):\n"
            "  mlx:       mlx-community/Meta-Llama-3.1-8B-Instruct-4bit\n"
            "  cuda/rocm: unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
        ),
    )
    parser.add_argument("--epochs",          type=int,  default=3)
    parser.add_argument("--batch-size",      type=int,  default=None,
                        help="Per-device batch size (default: 1 for MLX, 2 for GPU)")
    parser.add_argument("--output",          type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-seq-length",  type=int,  default=2048)
    parser.add_argument(
        "--cooldown",
        type=int, default=None,
        metavar="SECS",
        help=(
            "Seconds to pause between epochs (thermal cool-down). "
            "Default: 300 for MLX (MacBook Air), 0 for GPU. Set to 0 to disable."
        ),
    )
    args = parser.parse_args()

    # Resolve backend (may differ from _DETECTED_BACKEND if --backend is explicit)
    backend = detect_backend(args.backend)
    log.info("Backend: %s", backend)

    # Apply per-backend defaults for args not explicitly provided
    model_name = args.model or _DEFAULT_MODELS.get(backend, DEFAULT_MODEL)
    batch_size = args.batch_size if args.batch_size is not None else (1 if backend == "mlx" else 2)
    cooldown   = args.cooldown   if args.cooldown   is not None else (300 if backend == "mlx" else 0)

    train(args.epochs, batch_size, args.output, args.max_seq_length,
          model_name, cooldown, backend)


if __name__ == "__main__":
    main()
