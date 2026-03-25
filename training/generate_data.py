"""
Synthetic training data generation.

Uses Anthropic Claude to generate ~2700 training examples across three categories:
  A. NPC Action Decisions    (~1500 examples)
  B. Interrogation Responses (~1000 examples)
  C. Mystery Setups          (~200 examples)

Output: JSONL files in data/ — each line is Alpaca-format:
  {"instruction": "...", "input": "...", "output": "..."}

Usage:
  ANTHROPIC_API_KEY=sk-ant-... python generate_data.py [--target 2700] [--model claude-haiku-4-5]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

import anthropic

log = logging.getLogger("data-gen")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Game world constants used to vary scenarios
# ---------------------------------------------------------------------------

PERSONALITIES = ["nervous", "arrogant", "charming", "cold", "paranoid"]
RELATIONSHIPS = ["spouse", "business partner", "servant", "old friend", "estranged sibling"]
ROOMS = ["foyer", "library", "kitchen", "bedroom", "garden"]
EVIDENCE_ITEMS = [
    "kitchen_knife", "poison_bottle", "torn_fabric", "love_letter",
    "ledger_page", "will_amendment", "muddy_boots", "broken_vase",
    "bloodstained_glove", "mysterious_note",
]
EMOTIONS = ["calm", "nervous", "angry", "defensive", "tearful", "smug"]
NPC_ACTIONS = [
    "move", "hide_evidence", "destroy_evidence", "talk_to",
    "plant_evidence", "act_nervous", "stay_calm", "investigate",
]
SUSPECT_NAMES = ["Lady Ashworth", "Victor Crane", "Nell Marsh", "Thomas Hale", "Clara Voss"]
SECRETS = [
    "having an affair",
    "discovered to have embezzled from the victim",
    "witnessed something incriminating but is too afraid to speak",
    "visited the victim secretly the night before and owes them a large debt",
    "came to confront the victim over a disputed inheritance",
]
MOTIVES = [
    "stands to inherit the entire estate",
    "trying to prevent exposure of embezzlement",
    "silencing a witness who knew too much",
    "eliminating a creditor before being exposed",
    "revenge for being disinherited",
]


# ---------------------------------------------------------------------------
# Prompt builders for cloud LLM calls
# ---------------------------------------------------------------------------

def _npc_action_system() -> str:
    return (
        "You generate training examples for a murder mystery game. "
        "Each example shows an NPC making a realistic, strategically appropriate decision "
        "given their situation. Respond ONLY with a JSON object. No explanation."
    )


def _npc_action_user(
    name: str, personality: str, relationship: str, secret: str,
    is_killer: bool, motive: str | None,
    turn: int, room: str, player_room: str, pressure: int,
    known_evidence: list[str], action_history: list[str],
    player_suspicion: str | None,
) -> str:
    guilt = "the killer" if is_killer else "innocent"
    motive_line = f"Motive: {motive}" if motive else ""
    return f"""Create a training example where {name} ({personality}, {relationship} of victim, {guilt}) decides their action.
{motive_line}
Secret: {secret}
Turn: {turn}/15, Pressure: {pressure}/10
Location: {room}, Player is in: {player_room}
Evidence visible: {', '.join(known_evidence) or 'none'}
Recent actions: {', '.join(action_history[-3:]) or 'none'}
Player suspects: {player_suspicion or 'unknown'}

Return:
{{
  "instruction": "You are an NPC in a murder mystery game. Given this character and game state, decide your action.",
  "input": "<full game state prompt that would be sent to the model>",
  "output": {{"action": "...", "target": "...", "secondary_target": null, "internal_thought": "..."}}
}}"""


def _interrogate_system() -> str:
    return (
        "You generate training examples for a murder mystery game. "
        "Each example shows an NPC responding authentically to a detective's interrogation. "
        "Responses should be in-character and match the NPC's guilt status, personality, and pressure level. "
        "Respond ONLY with a JSON object. No explanation."
    )


def _interrogate_user(
    name: str, personality: str, relationship: str, secret: str,
    is_killer: bool, motive: str | None,
    pressure: int, alibi: str, lies_told: list[str],
    question: str, evidence_shown: list[str],
) -> str:
    guilt = "the killer" if is_killer else "innocent"
    motive_line = f"Motive: {motive}" if motive else ""
    return f"""Create a training example where {name} ({personality}, {relationship} of victim, {guilt}) responds to interrogation.
{motive_line}
Secret: {secret}
Pressure: {pressure}/10, True alibi: {alibi}
Lies already told: {', '.join(lies_told) or 'none'}
Detective asks: "{question}"
Evidence shown: {', '.join(evidence_shown) or 'none'}

Return:
{{
  "instruction": "You are an NPC in a murder mystery game being interrogated. Respond in character.",
  "input": "<full interrogation prompt that would be sent to the model>",
  "output": {{"dialogue": "...", "lie": true/false, "emotion": "...", "internal_thought": "..."}}
}}"""


def _mystery_setup_system() -> str:
    return (
        "You generate training examples for a murder mystery game. "
        "Each example creates a balanced, solvable mystery scenario. "
        "Respond ONLY with a JSON object. No explanation."
    )


def _mystery_setup_user(suspects: list[dict]) -> str:
    lines = "\n".join(
        f"- {s['name']}: {s['personality']}, {s['relationship']}. Secret: {s['secret']}"
        for s in suspects
    )
    return f"""Create a training example that generates a complete mystery setup for these suspects:
{lines}

Return:
{{
  "instruction": "You are a murder mystery game master. Generate a balanced, solvable mystery.",
  "input": "<full setup prompt that would be sent to the model>",
  "output": {{
    "killer_name": "...",
    "motive": "...",
    "evidence_placements": {{"item": "room"}},
    "true_alibis": {{"name": "alibi"}},
    "false_alibis": {{"name": "lie"}},
    "critical_evidence": ["item1", "item2", "item3"],
    "initial_npc_positions": {{"name": "room"}}
  }}
}}"""


# ---------------------------------------------------------------------------
# Generation helpers
# ---------------------------------------------------------------------------

def _call(client: anthropic.Anthropic, model: str, system: str, user: str) -> dict | None:
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system + " Return ONLY valid JSON — no markdown, no explanation.",
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text.strip()
        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        log.warning("Cloud LLM call failed: %s", exc)
        return None


def _random_suspects(n: int = 5) -> list[dict]:
    names = random.sample(SUSPECT_NAMES, min(n, len(SUSPECT_NAMES)))
    personalities = random.sample(PERSONALITIES, len(names))
    relationships = random.sample(RELATIONSHIPS, len(names))
    secrets = random.sample(SECRETS, len(names))
    return [
        {"name": names[i], "personality": personalities[i],
         "relationship": relationships[i], "secret": secrets[i]}
        for i in range(len(names))
    ]


def _random_alibi() -> str:
    options = [
        "was reading in the library alone",
        "was tending to the garden",
        "was asleep in their room",
        "was in the kitchen preparing tea",
        "was writing correspondence in the study",
    ]
    return random.choice(options)


SAMPLE_QUESTIONS = [
    "Where were you at the time of the murder?",
    "Did you have any reason to dislike Lord Ashworth?",
    "Can anyone confirm your alibi?",
    "I found this near the body. Have you seen it before?",
    "I've been told you argued with the victim last night. Is that true?",
    "Were you aware of the recent changes to Lord Ashworth's will?",
    "What was your relationship with the victim really like?",
    "I have evidence you were near the scene. How do you explain that?",
]


# ---------------------------------------------------------------------------
# Per-category generators
# ---------------------------------------------------------------------------

def generate_npc_actions(client: anthropic.Anthropic, model: str, count: int) -> list[dict]:
    examples = []
    log.info("Generating %d NPC action examples...", count)
    for i in range(count):
        suspects = _random_suspects(1)
        s = suspects[0]
        is_killer = random.random() < 0.5
        motive = random.choice(MOTIVES) if is_killer else None
        known_ev = random.sample(EVIDENCE_ITEMS, random.randint(0, 3))
        action_history = random.sample(NPC_ACTIONS, random.randint(0, 4))
        result = _call(
            client, model,
            _npc_action_system(),
            _npc_action_user(
                name=s["name"],
                personality=s["personality"],
                relationship=s["relationship"],
                secret=s["secret"],
                is_killer=is_killer,
                motive=motive,
                turn=random.randint(1, 15),
                room=random.choice(ROOMS),
                player_room=random.choice(ROOMS),
                pressure=random.randint(0, 10),
                known_evidence=known_ev,
                action_history=action_history,
                player_suspicion=random.choice(SUSPECT_NAMES + [None]),
            ),
        )
        if result:
            examples.append(result)
        if (i + 1) % 50 == 0:
            log.info("  NPC actions: %d/%d", i + 1, count)
    return examples


def generate_interrogations(client: anthropic.Anthropic, model: str, count: int) -> list[dict]:
    examples = []
    log.info("Generating %d interrogation examples...", count)
    for i in range(count):
        suspects = _random_suspects(1)
        s = suspects[0]
        is_killer = random.random() < 0.5
        motive = random.choice(MOTIVES) if is_killer else None
        pressure = random.randint(0, 10)
        result = _call(
            client, model,
            _interrogate_system(),
            _interrogate_user(
                name=s["name"],
                personality=s["personality"],
                relationship=s["relationship"],
                secret=s["secret"],
                is_killer=is_killer,
                motive=motive,
                pressure=pressure,
                alibi=_random_alibi(),
                lies_told=random.sample(SAMPLE_QUESTIONS[:3], random.randint(0, 2)),
                question=random.choice(SAMPLE_QUESTIONS),
                evidence_shown=random.sample(EVIDENCE_ITEMS, random.randint(0, 2)),
            ),
        )
        if result:
            examples.append(result)
        if (i + 1) % 50 == 0:
            log.info("  Interrogations: %d/%d", i + 1, count)
    return examples


def generate_mystery_setups(client: anthropic.Anthropic, model: str, count: int) -> list[dict]:
    examples = []
    log.info("Generating %d mystery setup examples...", count)
    for i in range(count):
        result = _call(
            client, model,
            _mystery_setup_system(),
            _mystery_setup_user(_random_suspects(5)),
        )
        if result:
            examples.append(result)
        if (i + 1) % 20 == 0:
            log.info("  Mystery setups: %d/%d", i + 1, count)
    return examples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def save_jsonl(examples: list[dict], path: Path):
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    log.info("Saved %d examples → %s", len(examples), path)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic training data")
    parser.add_argument("--target", type=int, default=2700, help="Total examples to generate")
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5",
        help=(
            "Anthropic model to use. Options:\n"
            "  claude-haiku-4-5   — fastest, cheapest (~$1-2 for 2700 examples) [default]\n"
            "  claude-sonnet-4-6  — higher quality, ~10x more expensive\n"
            "  claude-opus-4-6    — best quality, ~50x more expensive"
        ),
    )
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)

    # Proportional split: 55% actions, 37% interrogations, 8% setups
    n_actions = int(args.target * 0.55)
    n_interrogations = int(args.target * 0.37)
    n_setups = args.target - n_actions - n_interrogations

    actions = generate_npc_actions(client, args.model, n_actions)
    save_jsonl(actions, DATA_DIR / "npc_actions.jsonl")

    interrogations = generate_interrogations(client, args.model, n_interrogations)
    save_jsonl(interrogations, DATA_DIR / "interrogations.jsonl")

    setups = generate_mystery_setups(client, args.model, n_setups)
    save_jsonl(setups, DATA_DIR / "mystery_setups.jsonl")

    total = len(actions) + len(interrogations) + len(setups)
    log.info("Done. Total examples generated: %d", total)


if __name__ == "__main__":
    main()
