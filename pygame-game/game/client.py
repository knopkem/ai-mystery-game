from __future__ import annotations

import queue
import random
import threading

import requests

from game.constants import SERVER


# ═══════════════════════════════════════════════════════════════════════════
# LLM CLIENT  (threaded — keeps pygame responsive during inference)
# ═══════════════════════════════════════════════════════════════════════════

class LLMClient:
    def __init__(self) -> None:
        self.result_queue: queue.Queue = queue.Queue()
        self.pending_setup_constraints: dict = {}

    def _post(self, path: str, payload: dict, tag: str) -> None:
        try:
            r = requests.post(f"{SERVER}{path}", json=payload, timeout=60)
            r.raise_for_status()
            self.result_queue.put((tag, r.json(), None))
        except Exception as e:
            self.result_queue.put((tag, None, str(e)))

    def check_health(self) -> dict | None:
        try:
            r = requests.get(f"{SERVER}/health", timeout=4)
            return r.json()
        except Exception:
            return None

    def request_setup(self, suspects: list, rooms: list, evidence: list) -> None:
        # Pre-randomise structural choices so the LLM generates different
        # mysteries each run rather than always picking the same killer/layout.
        suspect_names   = [s["name"] for s in suspects]
        shuffled_rooms  = random.sample(rooms, len(rooms))
        forced_killer   = random.choice(suspect_names)
        forced_positions = {
            name: shuffled_rooms[i % len(shuffled_rooms)]
            for i, name in enumerate(suspect_names)
        }
        forced_evidence = {
            item: random.choice(rooms)
            for item in random.sample(evidence, min(len(evidence), 5))
        }
        # Stash so the game can enforce them client-side after the response
        self.pending_setup_constraints = {
            "forced_killer": forced_killer,
            "forced_positions": forced_positions,
            "forced_evidence_placements": forced_evidence,
        }
        payload = {
            "suspects": suspects,
            "rooms": rooms,
            "evidence_items": evidence,
            **self.pending_setup_constraints,
        }
        threading.Thread(target=self._post, args=("/setup-mystery", payload, "setup"), daemon=True).start()

    def request_npc_actions(self, game_state_dict: dict) -> None:
        payload = {"game_state": game_state_dict}
        threading.Thread(target=self._post, args=("/npc-actions", payload, "npc_actions"), daemon=True).start()

    def request_interrogate(self, npc: dict, question: str, evidence_shown: list, game_state_dict: dict) -> None:
        payload = {
            "npc_state": npc,
            "player_question": question,
            "evidence_shown": evidence_shown,
            "game_state": game_state_dict,
        }
        threading.Thread(target=self._post, args=("/interrogate", payload, "interrogate"), daemon=True).start()
