"""
Prompt templates for all LLM interactions.

Each function takes structured game data and returns a fully-formatted
prompt string ready to send to the model.
"""
from __future__ import annotations

from schemas import GameState, NpcState, SuspectBlueprint


_SYSTEM_NPC_ACTION = (
    "You are a character in a Victorian murder mystery. "
    "Respond ONLY with a valid JSON object matching the schema given. "
    "No markdown, no explanation, no extra text."
)

_SYSTEM_INTERROGATE = (
    "You are a character in a Victorian murder mystery being interrogated by a detective. "
    "Stay in character at all times. "
    "Respond ONLY with a valid JSON object matching the schema given. "
    "No markdown, no explanation, no extra text."
)

_SYSTEM_SETUP = (
    "You are a murder mystery game master. "
    "Generate a balanced, solvable mystery. "
    "The killer must have clear evidence against them — the player must be able to win. "
    "Respond ONLY with a valid JSON object matching the schema given. "
    "No markdown, no explanation, no extra text."
)


def build_npc_action_prompt(npc: NpcState, game_state: GameState) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for a single NPC action decision."""
    identity = npc.identity
    npcs_in_room = [
        n.identity.name for n in game_state.npcs
        if n.current_room == npc.current_room and n.identity.name != identity.name
    ]
    guilt_line = "You ARE the killer." if identity.is_killer else "You are innocent."
    motive_line = f"Your motive: {identity.motive}" if identity.is_killer and identity.motive else ""

    user = f"""You are {identity.name}, a {identity.personality.value} {identity.relationship.value} of the victim.
Your secret: {identity.secret}
{guilt_line}
{motive_line}

Current game state:
- Turn: {game_state.turn_number}/15
- Your location: {npc.current_room}
- Other NPCs present: {', '.join(npcs_in_room) if npcs_in_room else 'none'}
- Player location: {game_state.player_room}
- Evidence you know about: {', '.join(game_state.known_evidence) if game_state.known_evidence else 'none'}
- Your previous actions this game: {', '.join(npc.action_history[-5:]) if npc.action_history else 'none'}
- Times you have been interrogated: {npc.interrogation_count}
- Player seems to suspect: {game_state.player_suspicion_target or 'unknown'}

Available rooms: {_rooms_from_state(game_state)}

Choose your single most strategic action. Respond with this exact JSON schema:
{{
  "action": "<move|hide_evidence|destroy_evidence|talk_to|plant_evidence|act_nervous|stay_calm|investigate>",
  "target": "<room_name | npc_name | item_name | null>",
  "secondary_target": "<room_name for plant_evidence, otherwise null>",
  "internal_thought": "<1 sentence: your character's reasoning>"
}}"""
    return _SYSTEM_NPC_ACTION, user


def build_batch_npc_action_prompt(npcs: list[NpcState], game_state: GameState) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for ALL NPCs in a single call."""
    npc_blocks = []
    for npc in npcs:
        identity = npc.identity
        guilt_line = "KILLER" if identity.is_killer else "innocent"
        npc_blocks.append(
            f"- {identity.name} | {identity.personality.value} {identity.relationship.value} | "
            f"{guilt_line} | location: {npc.current_room} | "
            f"pressure: {npc.pressure}/10 | interrogated: {npc.interrogation_count}x | "
            f"secret: {identity.secret}"
        )

    user = f"""Murder mystery, turn {game_state.turn_number}/15.
Player is in: {game_state.player_room}.
Player suspects: {game_state.player_suspicion_target or 'unknown'}.
Known evidence on the board: {', '.join(game_state.known_evidence) if game_state.known_evidence else 'none'}.
Available rooms: {_rooms_from_state(game_state)}.

Suspects (decide one action each):
{chr(10).join(npc_blocks)}

For each suspect, choose their most strategically appropriate action.
Respond with this exact JSON schema — a list, one entry per suspect in the same order:
[
  {{
    "npc_name": "<name>",
    "action": "<move|hide_evidence|destroy_evidence|talk_to|plant_evidence|act_nervous|stay_calm|investigate>",
    "target": "<room_name | npc_name | item_name | null>",
    "secondary_target": "<room_name for plant_evidence, otherwise null>",
    "internal_thought": "<1 sentence reasoning>"
  }}
]"""
    return _SYSTEM_NPC_ACTION, user


def build_interrogate_prompt(
    npc: NpcState,
    player_question: str,
    evidence_shown: list[str],
    game_state: GameState,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for an interrogation response."""
    identity = npc.identity
    guilt_line = "You ARE the killer." if identity.is_killer else "You are innocent."
    motive_line = f"Your motive: {identity.motive}" if identity.is_killer and identity.motive else ""
    evidence_line = f"Evidence the detective just showed you: {', '.join(evidence_shown)}" if evidence_shown else ""

    user = f"""You are {identity.name}, a {identity.personality.value} {identity.relationship.value} of the murdered Lord Ashworth.
Your secret: {identity.secret}
Your alibi (true): {npc.alibi}
{guilt_line}
{motive_line}

Interrogation context:
- Turn: {game_state.turn_number}/15
- Times interrogated so far: {npc.interrogation_count}
- Your pressure level: {npc.pressure}/10
- Lies you have already told: {', '.join(npc.lies_told) if npc.lies_told else 'none'}
{evidence_line}

The detective asks: "{player_question}"

Behavior guidelines:
- Pressure 0-3: Answer as your character naturally would; if guilty, lie or deflect smoothly.
- Pressure 4-6: Show some strain; if guilty, make small inconsistencies or get defensive.
- Pressure 7-9: Visibly uncomfortable; if guilty, you may slip up or reveal partial truths.
- Pressure 10: If guilty, you may crack and reveal something significant (not full confession).
- If innocent, answer honestly but protect your secret if it is embarrassing.

Respond with this exact JSON schema:
{{
  "dialogue": "<what you say to the detective, 1-3 sentences, in character>",
  "lie": <true if your dialogue contains a deliberate falsehood, else false>,
  "emotion": "<calm|nervous|angry|defensive|tearful|smug>",
  "internal_thought": "<1 sentence: what you are actually thinking>"
}}"""
    return _SYSTEM_INTERROGATE, user


def build_setup_mystery_prompt(
    suspects: list[SuspectBlueprint],
    rooms: list[str],
    evidence_items: list[str],
    forced_killer: str | None = None,
    forced_positions: dict[str, str] | None = None,
    forced_evidence_placements: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for generating a fresh mystery."""
    suspect_lines = "\n".join(
        f"- {s.name}: {s.personality.value}, {s.relationship.value}. Secret: {s.secret}"
        for s in suspects
    )

    # Build hard-constraint block when the client has pre-randomised structure
    constraints: list[str] = []
    if forced_killer:
        constraints.append(f'- FIXED: killer_name MUST be "{forced_killer}"')
    if forced_positions:
        pos_str = ", ".join(f"{n}→{r}" for n, r in forced_positions.items())
        constraints.append(f"- FIXED: initial_npc_positions MUST be exactly: {pos_str}")
    if forced_evidence_placements:
        ev_str = ", ".join(f"{i}→{r}" for i, r in forced_evidence_placements.items())
        constraints.append(f"- FIXED: evidence_placements MUST be exactly: {ev_str}")
    constraint_block = (
        "\nHARD CONSTRAINTS (do not change these values):\n" + "\n".join(constraints) + "\n"
        if constraints else ""
    )

    user = f"""Generate a murder mystery scenario for these suspects:
{suspect_lines}

Mansion rooms: {', '.join(rooms)}
Evidence items available: {', '.join(evidence_items)}
{constraint_block}
Rules:
- Choose exactly one killer. Their secret should be plausibly related to the motive.
- Place at least 3 critical evidence items that point to the killer.
- Give every suspect a true alibi. Give the killer a false alibi to tell.
- The mystery must be solvable — a clever player with the evidence should be able to identify the killer.

Respond with this exact JSON schema:
{{
  "killer_name": "<name>",
  "motive": "<brief motive string>",
  "evidence_placements": {{"<item>": "<room>"}},
  "true_alibis": {{"<npc_name>": "<true alibi>"}},
  "false_alibis": {{"<npc_name>": "<lie to tell if pressed>"}},
  "critical_evidence": ["<item1>", "<item2>", "<item3>"],
  "initial_npc_positions": {{"<npc_name>": "<room>"}}
}}"""
    return _SYSTEM_SETUP, user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rooms_from_state(game_state: GameState) -> str:
    rooms = {npc.current_room for npc in game_state.npcs}
    rooms.add(game_state.player_room)
    return ', '.join(sorted(rooms))
