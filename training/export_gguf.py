"""
Export the fine-tuned merged model to GGUF format for local inference with llama.cpp.

Usage:
  python export_gguf.py [--merged ./checkpoints/merged] [--output ./model-gguf] [--quant q4_k_m]

The resulting .gguf file should be copied to ../llm-server/model/
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
            f"Merged model not found at {merged_dir}. Run train.py first."
        )

    try:
        from unsloth import FastLanguageModel  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}\nRun: pip install -r requirements-train.txt"
        ) from e

    log.info("Loading merged model from %s ...", merged_dir)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(merged_dir),
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=False,  # load full precision for export
    )

    gguf_path = output_dir / f"murder-mystery-{quant}.gguf"
    log.info("Exporting to GGUF (%s) → %s ...", quant, gguf_path)

    model.save_pretrained_gguf(
        str(output_dir / "murder-mystery"),
        tokenizer,
        quantization_method=quant,
    )

    log.info("Export complete.")
    log.info("")
    log.info("Next step: copy the GGUF file to the LLM server:")
    log.info("  cp %s/*.gguf ../llm-server/model/murder-mystery.gguf", output_dir)
    log.info("Then update MODEL_PATH in your .env if needed.")


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
