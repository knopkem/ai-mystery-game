"""
Export the fine-tuned merged model to GGUF format for llama.cpp (cross-platform).

NOTE: On Apple Silicon the MLX-format model in checkpoints/mlx-model is preferred
for inference (use it directly with mlx-lm). GGUF export is optional and only needed
if you want to deploy to a non-Apple machine or test with other llama.cpp tools.

Usage:
  python export_gguf.py [--merged ./checkpoints/merged] [--output ./model-gguf] [--quant q4_k_m]

The resulting .gguf file can be copied to ../llm-server/model/ and used with
the llama-cpp-python backend (see llm-server/.env: BACKEND=llamacpp).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

log = logging.getLogger("export-gguf")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

QUANT_OPTIONS = ["q4_k_m", "q5_k_m", "q8_0", "f16"]


def export(merged_dir: Path, output_dir: Path, quant: str):
    output_dir.mkdir(parents=True, exist_ok=True)

    if not merged_dir.exists():
        raise SystemExit(
            f"Merged model not found at {merged_dir}. Run train.py first.\n"
            "The merged model is saved to checkpoints/merged/ by train.py."
        )

    try:
        # mlx-tune uses identical save_pretrained_gguf API to Unsloth
        from mlx_tune import FastLanguageModel  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}\nRun: pip install -r requirements-train.txt"
        ) from e

    log.info("Loading merged model from %s ...", merged_dir)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(merged_dir),
        max_seq_length=2048,
        load_in_4bit=False,  # load full precision for export
    )

    log.info("Exporting to GGUF (%s) → %s ...", quant, output_dir)
    model.save_pretrained_gguf(
        str(output_dir / "murder-mystery"),
        tokenizer,
        quantization_method=quant,
    )

    gguf_file = output_dir / f"murder-mystery-{quant}.gguf"
    log.info("GGUF export complete: %s", gguf_file)
    log.info("")
    log.info("To use with the llama-cpp backend:")
    log.info("  cp %s ../llm-server/model/murder-mystery.gguf", gguf_file)
    log.info("  # Set in llm-server/.env:  BACKEND=llamacpp")
    log.info("")
    log.info("For Apple Silicon (recommended), use the MLX model instead:")
    log.info("  cp -r checkpoints/mlx-model ../llm-server/model/mlx-model")
    log.info("  # Set in llm-server/.env:  BACKEND=mlx  (default)")


def main():
    parser = argparse.ArgumentParser(description="Export fine-tuned model to GGUF")
    parser.add_argument(
        "--merged",
        type=Path,
        default=Path(__file__).parent / "checkpoints" / "merged",
        help="Path to merged model directory from train.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "model-gguf",
        help="Output directory for GGUF file",
    )
    parser.add_argument(
        "--quant",
        choices=QUANT_OPTIONS,
        default="q4_k_m",
        help="Quantization method (default: q4_k_m, ~2GB, best for M4 16GB)",
    )
    args = parser.parse_args()
    export(args.merged, args.output, args.quant)


if __name__ == "__main__":
    main()
