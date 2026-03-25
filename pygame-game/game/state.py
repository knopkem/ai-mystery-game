from __future__ import annotations

import random
from enum import Enum, auto

from game.constants import PLAYER_AP, MAX_TURNS, ROOMS, SUSPECT_BLUEPRINTS, NPC_PALETTE


# ═══════════════════════════════════════════════════════════════════════════
# GAME STATE
# ═══════════════════════════════════════════════════════════════════════════

class Phase(Enum):
    PLAYER = auto()
    NPC    = auto()
    EVENT  = auto()


class GameState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.turn: int = 1
        self.phase: Phase = Phase.PLAYER
        self.ap: int = PLAYER_AP
        self.player_room: str = "foyer"
        self.suspicion_target: str = ""

        self.npcs: dict[str, dict] = {}
        self.evidence_locations: dict[str, str] = {}  # item → room | "__hidden__" | ""
        self.found_evidence: list[str] = []
        self.destroyed_evidence: list[str] = []

        self.killer: str = ""
        self.motive: str = ""
        self.critical_evidence: list[str] = []

        self.log: list[str] = []          # recent events (shown in log bar)
        self.notes: list[str] = []        # all player notes (shown in notes overlay)
        self.interrogation_response: dict | None = None

        self.outcome: str = ""            # "win" | "lose" | "partial"
        self.outcome_msg: str = ""

    # ── Mystery initialisation ──────────────────────────────────────────

    def apply_mystery_setup(self, data: dict) -> None:
        self.killer = data.get("killer_name", "")
        self.motive = data.get("motive", "")
        self.critical_evidence = data.get("critical_evidence", [])

        placements: dict = data.get("evidence_placements", {})
        for item in placements:
            self.evidence_locations[item] = placements[item]

        true_alibis: dict  = data.get("true_alibis", {})
        false_alibis: dict = data.get("false_alibis", {})
        positions: dict    = data.get("initial_npc_positions", {})

        color_idx = 0
        for bp in SUSPECT_BLUEPRINTS:
            name = bp["name"]
            self.npcs[name] = {
                "name": name,
                "personality": bp["personality"],
                "relationship": bp["relationship"],
                "secret": bp["secret"],
                "is_killer": name == self.killer,
                "motive": self.motive if name == self.killer else "",
                "current_room": positions.get(name, random.choice(ROOMS)),
                "action_history": [],
                "interrogation_count": 0,
                "pressure": 0,
                "lies_told": [],
                "alibi": true_alibis.get(name, "was elsewhere"),
                "false_alibi": false_alibis.get(name, ""),
                "color": NPC_PALETTE[color_idx % len(NPC_PALETTE)],
            }
            color_idx += 1

        self._note("Lord Ashworth has been found dead in the foyer. The investigation begins.")

    # ── Player actions ──────────────────────────────────────────────────

    def can_act(self) -> bool:
        return self.phase == Phase.PLAYER and self.ap > 0

    def move(self, room: str) -> bool:
        if not self.can_act() or room == self.player_room or room not in ROOMS:
            return False
        self.player_room = room
        self._spend()
        return True

    def examine(self, item: str) -> bool:
        if not self.can_act():
            return False
        if self.evidence_locations.get(item) != self.player_room:
            return False
        if item not in self.found_evidence:
            self.found_evidence.append(item)
            self._note(f"Found {item.replace('_',' ')} in the {self.player_room}.")
        self._spend()
        return True

    def spend_for_interrogate(self) -> bool:
        if not self.can_act():
            return False
        self._spend()
        return True

    def accuse(self, suspect: str, motive_guess: str) -> None:
        if suspect == self.killer and motive_guess.strip().lower() in self.motive.lower():
            self.outcome = "win"
            self.outcome_msg = (
                f"Correct! {suspect} is the killer.\n"
                f"Motive: {self.motive}"
            )
        elif suspect == self.killer:
            self.outcome = "partial"
            self.outcome_msg = (
                f"Right suspect, wrong motive.\n"
                f"{suspect} was the killer, but the case is inconclusive."
            )
        else:
            self.outcome = "lose"
            self.outcome_msg = (
                f"{suspect} was innocent.\n"
                f"The real killer escapes into the night."
            )

    # ── NPC phase ───────────────────────────────────────────────────────

    def apply_npc_actions(self, actions: list[dict]) -> None:
        for a in actions:
            self._apply_one_npc_action(a)

    def _apply_one_npc_action(self, data: dict) -> None:
        name   = data.get("npc_name", "")
        action = data.get("action", "stay_calm")
        target = data.get("target") or ""
        secondary = data.get("secondary_target") or ""

        if name not in self.npcs:
            return
        npc = self.npcs[name]
        npc["action_history"].append(action)

        match action:
            case "move":
                if target in ROOMS:
                    npc["current_room"] = target
            case "hide_evidence":
                if target in self.evidence_locations and self.evidence_locations[target]:
                    self.evidence_locations[target] = "__hidden__"
            case "destroy_evidence":
                if target in self.evidence_locations:
                    self.evidence_locations[target] = ""
                    if target not in self.destroyed_evidence:
                        self.destroyed_evidence.append(target)
                    self._check_evidence_loss()
            case "plant_evidence":
                if target in self.evidence_locations and secondary in ROOMS:
                    self.evidence_locations[target] = secondary
            case "act_nervous":
                npc["pressure"] = min(npc["pressure"] + 1, 10)

        if npc["current_room"] == self.player_room:
            label = f" → {target}" if target else ""
            self._log(f"[T{self.turn}] Witnessed: {name} {action.replace('_',' ')}{label}")

    def run_event_phase(self) -> None:
        roll = random.random()
        msg = ""
        if roll < 0.10:
            msg = "The lights flicker and die! NPCs move in darkness."
        elif roll < 0.18:
            msg = "A suspect demands to leave the manor!"
        elif roll < 0.33:
            for item, loc in self.evidence_locations.items():
                if loc == "__hidden__":
                    new_room = random.choice(ROOMS)
                    self.evidence_locations[item] = new_room
                    msg = f"A servant discovers hidden {item.replace('_',' ')} in the {new_room}."
                    break
        elif roll < 0.46:
            names = list(self.npcs.keys())
            if names:
                npc_name = random.choice(names)
                room = self.npcs[npc_name]["current_room"]
                msg = f"Gossip: {npc_name} was seen in the {room}."
                self._note(f"[Event] {msg}")

        if msg:
            self._log(f"[Event] {msg}")

    def end_npc_and_event(self, actions: list[dict]) -> None:
        self.apply_npc_actions(actions)
        self.run_event_phase()
        if self.turn >= MAX_TURNS:
            self.outcome = "lose"
            self.outcome_msg = "Time is up. The killer escapes into the night."
            return
        self.turn += 1
        self.ap = PLAYER_AP
        self.phase = Phase.PLAYER

    def record_interrogation(self, npc_name: str, response: dict) -> None:
        npc = self.npcs.get(npc_name)
        if npc:
            npc["interrogation_count"] += 1
            npc["pressure"] = min(npc["pressure"] + 1, 10)
            if npc_name not in (self.suspicion_target or "") and npc["interrogation_count"] >= 2:
                self.suspicion_target = npc_name
        dialogue = response.get("dialogue", "…")
        emotion  = response.get("emotion", "calm")
        self._note(f"[Testimony] {npc_name} ({emotion}): \"{dialogue}\"")
        self.interrogation_response = {"npc_name": npc_name, **response}

    # ── Serialisation (sent to LLM server) ──────────────────────────────

    def as_dict(self) -> dict:
        npc_list = []
        for name, npc in self.npcs.items():
            npc_list.append({
                "identity": {
                    "name": npc["name"],
                    "personality": npc["personality"],
                    "relationship": npc["relationship"],
                    "secret": npc["secret"],
                    "is_killer": npc["is_killer"],
                    "motive": npc["motive"],
                },
                "current_room": npc["current_room"],
                "action_history": npc["action_history"],
                "interrogation_count": npc["interrogation_count"],
                "pressure": npc["pressure"],
                "lies_told": npc["lies_told"],
                "alibi": npc["alibi"],
            })
        return {
            "turn_number": self.turn,
            "player_room": self.player_room,
            "player_suspicion_target": self.suspicion_target,
            "known_evidence": self.found_evidence,
            "npcs": npc_list,
        }

    def npc_dict(self, name: str) -> dict:
        npc = self.npcs[name]
        return {
            "identity": {
                "name": npc["name"],
                "personality": npc["personality"],
                "relationship": npc["relationship"],
                "secret": npc["secret"],
                "is_killer": npc["is_killer"],
                "motive": npc["motive"],
            },
            "name": npc["name"],
            "current_room": npc["current_room"],
            "action_history": npc["action_history"],
            "interrogation_count": npc["interrogation_count"],
            "pressure": npc["pressure"],
            "lies_told": npc["lies_told"],
            "alibi": npc["alibi"],
        }

    def npcs_in_room(self, room: str) -> list[dict]:
        return [n for n in self.npcs.values() if n["current_room"] == room]

    def evidence_in_room(self, room: str) -> list[str]:
        return [i for i, loc in self.evidence_locations.items() if loc == room]

    # ── Fallback NPC actions (used when LLM unavailable) ────────────────

    def fallback_actions(self) -> list[dict]:
        from game.fallbacks import _sample_npc_action  # lazy import to avoid circular dependency
        actions = []
        for name, npc in self.npcs.items():
            ev_here   = [i for i, loc in self.evidence_locations.items()
                         if loc == npc["current_room"]]
            ev_any    = [i for i, loc in self.evidence_locations.items()
                         if loc and loc != "__hidden__"]
            other_rooms = [r for r in ROOMS if r != npc["current_room"]]
            pressure  = npc.get("pressure", 0)

            # Try training-data sampler first
            sampled = _sample_npc_action(npc["is_killer"], npc.get("personality","cold"), pressure)
            if sampled:
                action = sampled["action"]
                thought = sampled["internal_thought"]
                # Map action → real target from live game state
                if action == "hide_evidence":
                    target = random.choice(ev_here) if ev_here else (random.choice(ev_any) if ev_any else "")
                    if not target:
                        action, target = "stay_calm", ""
                elif action == "destroy_evidence":
                    target = random.choice(ev_here) if ev_here else ""
                    if not target:
                        action, target = "move", random.choice(other_rooms) if other_rooms else ""
                elif action == "plant_evidence":
                    target = random.choice(ev_any) if ev_any else ""
                    if not target:
                        action, target = "stay_calm", ""
                elif action == "move":
                    target = random.choice(other_rooms) if other_rooms else npc["current_room"]
                elif action == "talk_to":
                    others = [n for n in self.npcs if n != name]
                    target = random.choice(others) if others else ""
                    if not target:
                        action, target = "stay_calm", ""
                else:
                    target = ""
            else:
                # Pure rule-based last resort
                thought = "(fallback)"
                if npc["is_killer"]:
                    if ev_any and random.random() < 0.5:
                        action, target = "hide_evidence", random.choice(ev_any)
                    elif other_rooms and npc["current_room"] == self.player_room:
                        action, target = "move", random.choice(other_rooms)
                    else:
                        action, target = "stay_calm", ""
                else:
                    roll = random.random()
                    if roll < 0.35:
                        action, target = "stay_calm", ""
                    elif roll < 0.55 and other_rooms:
                        action, target = "move", random.choice(other_rooms)
                    elif roll < 0.70:
                        action, target = "investigate", ""
                    elif npc.get("personality") == "nervous":
                        action, target = "act_nervous", ""
                    else:
                        action, target = "stay_calm", ""

            actions.append({"npc_name": name, "action": action, "target": target,
                            "secondary_target": None, "internal_thought": thought})
        return actions

    # ── Helpers ──────────────────────────────────────────────────────────

    def _spend(self) -> None:
        self.ap -= 1
        if self.ap <= 0:
            self.phase = Phase.NPC

    def _note(self, text: str) -> None:
        self.notes.append(text)
        self._log(text)

    def _log(self, text: str) -> None:
        self.log.append(text)
        if len(self.log) > 40:
            self.log.pop(0)

    def _check_evidence_loss(self) -> None:
        remaining = [e for e in self.critical_evidence if e not in self.destroyed_evidence]
        if not remaining:
            self.outcome = "lose"
            self.outcome_msg = "The killer has destroyed all critical evidence. Case unsolvable."
