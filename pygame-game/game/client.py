from __future__ import annotations

import queue
import threading

import requests

from game.constants import SERVER


# ═══════════════════════════════════════════════════════════════════════════
# LLM CLIENT  (threaded — keeps pygame responsive during inference)
# ═══════════════════════════════════════════════════════════════════════════

class LLMClient:
    def __init__(self) -> None:
        self.result_queue: queue.Queue = queue.Queue()

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
        payload = {"suspects": suspects, "rooms": rooms, "evidence_items": evidence}
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
