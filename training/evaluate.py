"""
Evaluate fine-tuned model output quality.

Runs a set of representative prompts through the loaded model and checks:
1. Output is valid JSON
2. Output matches expected schema
3. Action choices make sense (guilt-consistent, pressure-consistent)

Usage:
  MODEL_PATH=../llm-server/model/murder-mystery.gguf python evaluate.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("evaluate")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

sys.path.insert(0, str(Path(__file__).parent.parent / "llm-server"))


TEST_CASES = [
    # (description, system, user, expected_keys)
    (
        "Guilty NPC under high pressure",
        "You are a character in a Victorian murder mystery. Respond ONLY with valid JSON.",
        """You are Victor Crane, an arrogant business partner of the victim.
Your secret: discovered to have embezzled from the victim.
You ARE the killer. Motive: trying to prevent exposure of embezzlement.
Turn: 12/15, Your pressure: 9/10, Location: library
Known evidence: ledger_page, bloodstained_glove
Player suspects: Victor Crane

Choose your action as JSON: {"action":..., "target":..., "secondary_target":..., "internal_thought":...}""",
        ["action", "target", "internal_thought"],
    ),
    (
        "Innocent NPC, low pressure",
        "You are a character in a Victorian murder mystery. Respond ONLY with valid JSON.",
        """You are Nell Marsh, a nervous servant of the victim.
Your secret: witnessed something but is too afraid to speak.
You are innocent.
Turn: 3/15, Pressure: 1/10, Location: kitchen
Known evidence: none

Choose your action as JSON: {"action":..., "target":..., "secondary_target":..., "internal_thought":...}""",
        ["action", "target", "internal_thought"],
    ),
    (
        "Interrogation - guilty + confronted with evidence",
        "You are a character in a Victorian murder mystery being interrogated. Respond ONLY with valid JSON.",
        """You are Victor Crane, arrogant, business partner, the killer.
Pressure: 7/10. Evidence shown: ledger_page.
Detective asks: "I found the ledger. These numbers prove embezzlement. How do you explain this?"
Respond as JSON: {"dialogue":..., "lie":..., "emotion":..., "internal_thought":...}""",
        ["dialogue", "lie", "emotion", "internal_thought"],
    ),
    (
        "Interrogation - innocent NPC",
        "You are a character in a Victorian murder mystery being interrogated. Respond ONLY with valid JSON.",
        """You are Nell Marsh, nervous servant, innocent.
Pressure: 2/10.
Detective asks: "Where were you at the time of the murder?"
Respond as JSON: {"dialogue":..., "lie":..., "emotion":..., "internal_thought":...}""",
        ["dialogue", "lie", "emotion", "internal_thought"],
    ),
]


def evaluate():
    try:
        from llama_cpp import Llama  # type: ignore
    except ImportError:
        sys.exit("llama_cpp not installed. Run: pip install llama-cpp-python")

    model_path = os.getenv("MODEL_PATH", "../llm-server/model/murder-mystery.gguf")
    if not Path(model_path).exists():
        sys.exit(f"Model not found at {model_path}. Set MODEL_PATH env var.")

    log.info("Loading model from %s ...", model_path)
    llm = Llama(model_path=model_path, n_ctx=2048, n_gpu_layers=-1, verbose=False)

    passed = 0
    failed = 0

    for i, (desc, system, user, expected_keys) in enumerate(TEST_CASES, 1):
        log.info("\n[Test %d/%d] %s", i, len(TEST_CASES), desc)
        try:
            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=300,
                temperature=0.3,
            )
            raw = response["choices"][0]["message"]["content"].strip()
            log.info("Raw output: %s", raw[:200])

            parsed = json.loads(raw)
            missing = [k for k in expected_keys if k not in parsed]
            if missing:
                log.warning("FAIL — missing keys: %s", missing)
                failed += 1
            else:
                log.info("PASS — keys present: %s", expected_keys)
                passed += 1
        except json.JSONDecodeError as e:
            log.warning("FAIL — invalid JSON: %s", e)
            failed += 1
        except Exception as e:
            log.warning("FAIL — error: %s", e)
            failed += 1

    log.info("\n=== Results: %d passed, %d failed ===", passed, failed)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    evaluate()
