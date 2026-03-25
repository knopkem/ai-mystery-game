"""
Rule-based fallback NPC logic used when the LLM server is unavailable
or returns malformed output.

Behaviour mirrors what the LLM should produce:
- Guilty NPCs tend to hide/destroy evidence and avoid the player.
- Innocent NPCs wander, occasionally investigate, or stay calm.
"""
from __future__ import annotations

import random

from schemas import (
    GameState,
    NpcAction,
    NpcActionResult,
    NpcState,
)


def fallback_npc_action(npc: NpcState, game_state: GameState) -> NpcActionResult:
    """Produce a plausible NPC action without the LLM."""
    identity = npc.identity
    is_guilty = identity.is_killer
    player_nearby = npc.current_room == game_state.player_room
    high_pressure = npc.pressure >= 7

    other_rooms = _other_rooms(npc, game_state)
    known_evidence = game_state.known_evidence

    # --- Guilty NPC logic ---
    if is_guilty:
        if high_pressure and known_evidence:
            # Under pressure with evidence on the board: try to destroy it
            if random.random() < 0.5:
                return NpcActionResult(
                    npc_name=identity.name,
                    action=NpcAction.destroy_evidence,
                    target=random.choice(known_evidence),
                    internal_thought="(fallback) Too much pressure, destroying evidence.",
                )
        if known_evidence and random.random() < 0.45:
            return NpcActionResult(
                npc_name=identity.name,
                action=NpcAction.hide_evidence,
                target=random.choice(known_evidence),
                internal_thought="(fallback) Hiding incriminating evidence.",
            )
        if player_nearby and other_rooms and random.random() < 0.55:
            return NpcActionResult(
                npc_name=identity.name,
                action=NpcAction.move,
                target=random.choice(other_rooms),
                internal_thought="(fallback) Moving away from detective.",
            )
        return NpcActionResult(
            npc_name=identity.name,
            action=NpcAction.stay_calm,
            internal_thought="(fallback) Staying calm to avoid suspicion.",
        )

    # --- Innocent NPC logic ---
    roll = random.random()
    if roll < 0.35:
        return NpcActionResult(
            npc_name=identity.name,
            action=NpcAction.stay_calm,
            internal_thought="(fallback) Nothing to hide.",
        )
    if roll < 0.55 and other_rooms:
        return NpcActionResult(
            npc_name=identity.name,
            action=NpcAction.move,
            target=random.choice(other_rooms),
            internal_thought="(fallback) Wandering the manor.",
        )
    if roll < 0.70:
        return NpcActionResult(
            npc_name=identity.name,
            action=NpcAction.investigate,
            internal_thought="(fallback) Curious about what happened.",
        )
    # Nervous personality acts nervous sometimes
    if identity.personality.value == "nervous":
        return NpcActionResult(
            npc_name=identity.name,
            action=NpcAction.act_nervous,
            internal_thought="(fallback) Can't help feeling anxious.",
        )
    return NpcActionResult(
        npc_name=identity.name,
        action=NpcAction.stay_calm,
        internal_thought="(fallback) Keeping composure.",
    )


def fallback_all_npc_actions(
    npcs: list[NpcState], game_state: GameState
) -> list[NpcActionResult]:
    return [fallback_npc_action(npc, game_state) for npc in npcs]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _other_rooms(npc: NpcState, game_state: GameState) -> list[str]:
    all_rooms = list({n.current_room for n in game_state.npcs} | {game_state.player_room})
    return [r for r in all_rooms if r != npc.current_room]
