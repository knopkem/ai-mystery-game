from __future__ import annotations

import json
import random
from pathlib import Path

from game.constants import ROOMS, SUSPECT_BLUEPRINTS


# ═══════════════════════════════════════════════════════════════════════════
# TRAINING-DATA NPC ACTION SAMPLER
# When the LLM server is offline we sample from the real training data
# (npc_actions.jsonl) instead of using pure rule-based logic. This gives
# richer internal_thought text while we still substitute real targets from
# the live game state.
# ═══════════════════════════════════════════════════════════════════════════

_NPC_ACTION_POOL: list[dict] | None = None  # lazy-loaded once

_ACTION_NORMALISE = {
    "conceal_evidence": "hide_evidence",
    "remove_evidence":  "hide_evidence",
    "pocket_evidence":  "hide_evidence",
    "avoid":            "move",
    "flee":             "move",
    "relocate":         "move",
    "confess_partial":  "stay_calm",
    "confess":          "stay_calm",
    "wait":             "stay_calm",
    "observe":          "investigate",
    "examine":          "investigate",
    "search":           "investigate",
    "approach_player_with_information": "talk_to",
    "deflect":          "stay_calm",
    "act_innocent":     "stay_calm",
    "confront":         "talk_to",
    "accuse":           "talk_to",
}
_VALID_ACTIONS = {
    "move", "hide_evidence", "destroy_evidence", "talk_to",
    "plant_evidence", "act_nervous", "stay_calm", "investigate",
}


def _load_npc_action_pool() -> list[dict]:
    global _NPC_ACTION_POOL
    if _NPC_ACTION_POOL is not None:
        return _NPC_ACTION_POOL
    # Path: pygame-game/game/../../training/data/npc_actions.jsonl
    data_path = Path(__file__).parent.parent.parent / "training" / "data" / "npc_actions.jsonl"
    pool: list[dict] = []
    if data_path.exists():
        with open(data_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ex = json.loads(line)
                    out = ex.get("output", {})
                    if isinstance(out, str):
                        out = json.loads(out)
                    action = _ACTION_NORMALISE.get(out.get("action", ""), out.get("action", ""))
                    if action not in _VALID_ACTIONS:
                        action = "stay_calm"
                    inp = ex.get("input", "").lower()
                    # Tag each entry for fast filtering
                    is_killer = any(kw in inp for kw in ("killer", "you killed", "the guilty", "guilt"))
                    pressure_bucket = "low"
                    for tok in inp.split():
                        tok = tok.strip("/:,.")
                        if tok.isdigit():
                            n = int(tok)
                            if n <= 3:
                                pressure_bucket = "low"
                            elif n <= 6:
                                pressure_bucket = "med"
                            else:
                                pressure_bucket = "high"
                            break
                    personality = "cold"
                    for p in ("nervous", "arrogant", "charming", "cold", "paranoid"):
                        if p in inp:
                            personality = p
                            break
                    pool.append({
                        "action":           action,
                        "internal_thought": out.get("internal_thought", ""),
                        "is_killer":        is_killer,
                        "personality":      personality,
                        "pressure_bucket":  pressure_bucket,
                    })
                except Exception:
                    pass
    _NPC_ACTION_POOL = pool
    return pool


def _sample_npc_action(is_killer: bool, personality: str, pressure: int) -> dict | None:
    """Return a sampled training-data action dict or None if pool is empty."""
    pool = _load_npc_action_pool()
    if not pool:
        return None
    bucket = "low" if pressure <= 3 else ("med" if pressure <= 6 else "high")
    # Progressively relax filters to always find something
    for filt in [
        lambda e: e["is_killer"] == is_killer and e["personality"] == personality and e["pressure_bucket"] == bucket,
        lambda e: e["is_killer"] == is_killer and e["personality"] == personality,
        lambda e: e["is_killer"] == is_killer and e["pressure_bucket"] == bucket,
        lambda e: e["is_killer"] == is_killer,
        lambda e: True,
    ]:
        candidates = [e for e in pool if filt(e)]
        if candidates:
            return random.choice(candidates)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# RULE-BASED INTERROGATION FALLBACK
# Used when LLM server is offline. Varies by personality, pressure,
# killer status, question keywords, and evidence shown.
# ═══════════════════════════════════════════════════════════════════════════

def _fallback_interrogate(npc: dict, question: str, evidence_shown: list[str]) -> dict:
    name        = npc.get("name", "Suspect")
    personality = npc.get("personality", "cold")
    is_killer   = npc.get("is_killer", False) or npc.get("identity", {}).get("is_killer", False)
    pressure    = npc.get("pressure", 0)
    alibi       = npc.get("alibi", "was elsewhere that evening")
    false_alibi = npc.get("false_alibi", "")
    relationship= npc.get("relationship", "associate")
    q           = question.lower()

    lie = False

    # ── Emotion ─────────────────────────────────────────────────────────
    if is_killer:
        if pressure >= 7:   emotion = random.choice(["nervous", "angry", "defensive"])
        elif pressure >= 4: emotion = random.choice(["calm", "defensive"])
        else:               emotion = "calm"
    else:
        base = {"nervous": "nervous", "arrogant": "calm",
                "charming": "calm", "cold": "calm", "paranoid": "nervous"}
        emotion = base.get(personality, "calm")
        if pressure >= 7:   emotion = random.choice(["tearful", "nervous", "angry"])
        elif pressure >= 4: emotion = random.choice(["nervous", "defensive"])

    dialogue = ""

    # ── Evidence reaction (only when question is about evidence) ─────────
    ev_keywords = ["this", "found", "evidence", "item", "object", "what is", "explain"]
    ev_names    = [e.replace("_", " ") for e in evidence_shown]
    asking_about_evidence = (
        evidence_shown and (
            any(kw in q for kw in ev_keywords)
            or any(en in q for en in ev_names)
        )
    )
    if asking_about_evidence:
        # Prefer the item the player actually named in the question
        ev = evidence_shown[-1].replace("_", " ")   # default: last found
        for en in ev_names:
            if en in q:
                ev = en
                break
        if is_killer:
            lie = True
            if pressure >= 6:
                dialogue = f"I... I don't know how that {ev} got there. You're trying to trap me."
            else:
                dialogue = f"That {ev}? I've never seen it before in my life. Someone must have planted it."
        else:
            other_room = random.choice([r for r in ROOMS])
            dialogue = f"That {ev}? I noticed it near the {other_room} earlier but thought nothing of it."

    # ── Alibi / whereabouts ──────────────────────────────────────────────
    elif any(w in q for w in ["where", "alibi", "doing", "were you", "location", "night", "evening", "time", "murder"]):
        if is_killer:
            lie = True
            fa = false_alibi or f"was in the {random.choice(ROOMS)} all evening"
            dialogue = f"I {fa}. I had no reason to be anywhere near the scene."
        else:
            dialogue = f"I {alibi}. I can assure you I had nothing to do with this tragedy."

    # ── Motive / relationship ────────────────────────────────────────────
    elif any(w in q for w in ["motive", "reason", "why", "hate", "gain", "benefit", "inherit", "money"]):
        if is_killer:
            lie = True
            dialogue = f"Motive? I had none. Lord Ashworth and I had our difficulties, but nothing like this."
        else:
            dialogue = f"As his {relationship}, I had everything to lose from his death. This is absurd."

    # ── Secrets / suspicious behaviour ──────────────────────────────────
    elif any(w in q for w in ["secret", "hiding", "lie", "truth", "nervous", "know", "seen", "witness", "saw"]):
        if is_killer:
            if pressure >= 7:
                lie = False
                dialogue = f"You're more observant than I gave you credit for. But knowing and proving are very different things."
            else:
                lie = True
                dialogue = f"I don't know what you've been told, but whoever said that is lying to protect themselves."
        else:
            if personality == "nervous":
                room = random.choice(ROOMS)
                other = random.choice([s["name"] for s in SUSPECT_BLUEPRINTS if s["name"] != name])
                dialogue = f"There is... one thing. I saw {other} coming out of the {room} very late. I didn't mention it because I didn't want trouble."
            elif personality == "paranoid":
                dialogue = "Someone in this house is framing me. I can feel it. You should be looking at the others."
            else:
                dialogue = "I've been completely honest with you. There is nothing more to tell."

    # ── Direct accusation ────────────────────────────────────────────────
    elif any(w in q for w in ["did you", "guilty", "kill", "murder", "confess", "you did it", "responsible"]):
        if is_killer:
            if pressure >= 8:
                lie = False
                emotion = "angry"
                dialogue = "You can't prove a thing without solid evidence. I want a solicitor."
            else:
                lie = True
                emotion = "angry"
                dialogue = f"How dare you! I am deeply offended. I demand you look at someone else."
        else:
            emotion = "angry"
            dialogue = f"Absolutely not! I am Lord Ashworth's {relationship} — why on earth would I harm him?"

    # ── Questions about other suspects ───────────────────────────────────
    else:
        mentioned = [s["name"] for s in SUSPECT_BLUEPRINTS
                     if s["name"].lower() in q and s["name"] != name]
        if mentioned:
            other = mentioned[0]
            if is_killer:
                lie = True
                dialogue = f"Since you ask — {other} was acting very strangely the night of the murder. I didn't want to say, but..."
            elif personality == "paranoid":
                dialogue = f"I never trusted {other}. Always lurking, always watching. You should look closely at them."
            elif personality == "charming":
                dialogue = f"I like {other} very much, but I did notice they seemed distracted that evening."
            else:
                dialogue = f"I really can't speak for {other}. You'd have to ask them yourself."

    # ── Personality-based default ────────────────────────────────────────
    if not dialogue:
        defaults = {
            "nervous":  [
                "I've told you everything I know. Please, this is very distressing.",
                "My mind is a blur. I keep replaying that morning over and over.",
            ],
            "arrogant": [
                "I've already given my statement. Is there a point to these repetitive questions?",
                "I find this line of inquiry rather beneath both of us.",
            ],
            "charming": [
                "I truly wish I could help more. I'm as desperate to find the truth as you are.",
                "You're very thorough, detective. I only wish I had more to offer.",
            ],
            "cold": [
                "I have said everything relevant. Move on.",
                "That question has been asked. The answer has not changed.",
            ],
            "paranoid": [
                "Are you sure no one else is listening? Something feels very wrong in this house.",
                "Someone here wants me blamed for this. I can sense it.",
            ],
        }
        options = defaults.get(personality, ["I have nothing more to add."])
        dialogue = random.choice(options)

    return {"dialogue": dialogue, "lie": lie, "emotion": emotion, "internal_thought": "(offline fallback)"}
