#!/usr/bin/env python3
"""
AI Murder Mystery — Pygame Quickstart
======================================
Turn-based murder mystery with LLM-driven NPCs.
All UI is drawn programmatically — no external assets needed.

Requirements:
    pip install -r requirements.txt

Start the LLM server first (from llm-server/):
    uvicorn server:app --host 127.0.0.1 --port 8000

Then run:
    python main.py
"""
from __future__ import annotations

import json
import math
import queue
import random
import sys
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

import pygame
import requests

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS & LAYOUT
# ═══════════════════════════════════════════════════════════════════════════

WIN_W, WIN_H = 1280, 720
FPS = 60
TITLE = "AI Murder Mystery"
SERVER = "http://127.0.0.1:8000"

HUD_H = 48
LOG_H = 88
MAP_W = 820
SIDE_W = WIN_W - MAP_W - 5

HUD_RECT  = pygame.Rect(0,                    0,      WIN_W,  HUD_H)
MAP_RECT  = pygame.Rect(0,                    HUD_H,  MAP_W,  WIN_H - HUD_H - LOG_H)
SIDE_RECT = pygame.Rect(MAP_W + 5,            HUD_H,  SIDE_W, WIN_H - HUD_H - LOG_H)
LOG_RECT  = pygame.Rect(0,                    WIN_H - LOG_H, WIN_W, LOG_H)

# Room grid inside MAP_RECT
CELL_W, CELL_H, CELL_GAP = 397, 181, 8
GX = MAP_RECT.x + 6
GY = MAP_RECT.y + 6
DPR = 1  # updated by _apply_dpr() at runtime

def _room_rect(col: int, row: int, span: int = 1) -> pygame.Rect:
    return pygame.Rect(
        GX + col * (CELL_W + CELL_GAP),
        GY + row * (CELL_H + CELL_GAP),
        CELL_W * span + CELL_GAP * (span - 1),
        CELL_H,
    )

ROOM_RECTS: dict[str, pygame.Rect] = {
    "library":  _room_rect(0, 0),
    "foyer":    _room_rect(1, 0),
    "kitchen":  _room_rect(0, 1),
    "bedroom":  _room_rect(1, 1),
    "garden":   _room_rect(0, 2, span=2),
}

def px(n: int | float) -> int:
    """Scale a logical-pixel value by the current device pixel ratio."""
    return int(n * DPR)

def _apply_dpr(dpr: int) -> None:
    """Re-derive all layout globals for the detected device pixel ratio.
    Called once at startup before font init."""
    global DPR, WIN_W, WIN_H, HUD_H, LOG_H, MAP_W, SIDE_W
    global HUD_RECT, MAP_RECT, SIDE_RECT, LOG_RECT
    global CELL_W, CELL_H, CELL_GAP, GX, GY

    DPR   = dpr
    WIN_W = 1280 * dpr;  WIN_H  = 720 * dpr
    HUD_H = 48   * dpr;  LOG_H  = 88  * dpr
    MAP_W = 820  * dpr;  SIDE_W = WIN_W - MAP_W - 5 * dpr

    HUD_RECT  = pygame.Rect(0,              0,      WIN_W, HUD_H)
    MAP_RECT  = pygame.Rect(0,              HUD_H,  MAP_W, WIN_H - HUD_H - LOG_H)
    SIDE_RECT = pygame.Rect(MAP_W + 5*dpr,  HUD_H,  SIDE_W, WIN_H - HUD_H - LOG_H)
    LOG_RECT  = pygame.Rect(0,              WIN_H - LOG_H, WIN_W, LOG_H)

    CELL_W, CELL_H, CELL_GAP = 397*dpr, 181*dpr, 8*dpr
    GX = MAP_RECT.x + 6*dpr
    GY = MAP_RECT.y + 6*dpr

    ROOM_RECTS.update({
        "library":  _room_rect(0, 0),
        "foyer":    _room_rect(1, 0),
        "kitchen":  _room_rect(0, 1),
        "bedroom":  _room_rect(1, 1),
        "garden":   _room_rect(0, 2, span=2),
    })

ROOM_BG: dict[str, tuple] = {
    "foyer":   (38, 28, 16),
    "library": (16, 24, 38),
    "kitchen": (38, 20, 14),
    "bedroom": (26, 14, 38),
    "garden":  (14, 35, 14),
}

NPC_PALETTE = [
    (230, 110, 95),   # coral
    (95,  155, 230),  # cornflower
    (95,  210, 125),  # sea green
    (225, 185, 65),   # gold
    (185, 105, 230),  # orchid
]

C: dict[str, tuple] = {
    "bg":        (14, 10, 6),
    "hud":       (22, 16, 8),
    "log":       (10, 8, 4),
    "panel":     (10, 8, 20),
    "border":    (70, 55, 25),
    "border_hi": (200, 160, 60),
    "text":      (245, 228, 196),
    "text_dim":  (130, 110, 75),
    "text_hi":   (255, 215, 60),
    "gold":      (218, 165, 32),
    "player":    (200, 215, 255),
    "btn":       (32, 25, 14),
    "btn_hi":    (58, 46, 22),
    "btn_dis":   (20, 18, 12),
    "btn_t":     (222, 192, 112),
    "btn_t_dis": (80, 70, 50),
    "green":     (80, 205, 80),
    "red":       (225, 80, 80),
    "amber":     (215, 145, 30),
    "sep":       (45, 36, 18),
    "overlay":   (8, 6, 16, 220),
}

# ═══════════════════════════════════════════════════════════════════════════
# GAME DATA CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

ROOMS = ["foyer", "library", "kitchen", "bedroom", "garden"]

EVIDENCE_ITEMS = [
    "kitchen_knife", "poison_bottle", "torn_fabric", "love_letter",
    "ledger_page", "will_amendment", "muddy_boots", "bloodstained_glove",
]

SUSPECT_BLUEPRINTS = [
    {"name": "Lady Ashworth", "personality": "cold",     "relationship": "spouse",           "secret": "having an affair"},
    {"name": "Victor Crane",  "personality": "arrogant", "relationship": "business partner", "secret": "embezzled from the victim"},
    {"name": "Nell Marsh",    "personality": "nervous",  "relationship": "servant",          "secret": "witnessed something she won't speak of"},
    {"name": "Thomas Hale",   "personality": "charming", "relationship": "old friend",       "secret": "visited secretly the night before"},
    {"name": "Clara Voss",    "personality": "paranoid", "relationship": "estranged sibling","secret": "came to confront the victim over the will"},
]

MAX_TURNS = 15
PLAYER_AP = 2

# ═══════════════════════════════════════════════════════════════════════════
# FONTS — populated after pygame.init()
# ═══════════════════════════════════════════════════════════════════════════

F: dict[str, pygame.font.Font] = {}

def _init_fonts() -> None:
    def sf(name: str, size: int) -> pygame.font.Font:
        return pygame.font.SysFont(name, size * DPR)

    mono = "courier"
    sans = "helvetica"
    serif = "georgia"

    F["title"]    = sf(serif,  52)
    F["hud"]      = sf(sans,   18)
    F["room"]     = sf(serif,  16)
    F["room_sm"]  = sf(mono,   13)
    F["panel"]    = sf(sans,   16)
    F["panel_sm"] = sf(sans,   13)
    F["btn"]      = sf(sans,   15)
    F["log"]      = sf(mono,   13)
    F["big"]      = sf(serif,  32)
    F["input"]    = sf(mono,   16)


# ═══════════════════════════════════════════════════════════════════════════
# WIDGET HELPERS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Button:
    rect: pygame.Rect
    label: str
    enabled: bool = True
    active: bool = False    # visually "pressed" / selected state

    def draw(self, surf: pygame.Surface) -> None:
        if not self.enabled:
            bg, tc = C["btn_dis"], C["btn_t_dis"]
        elif self.active:
            bg, tc = C["border_hi"], C["bg"]
        else:
            mx, my = pygame.mouse.get_pos()
            hovered = self.rect.collidepoint(mx, my)
            bg, tc = (C["btn_hi"] if hovered else C["btn"]), C["btn_t"]

        pygame.draw.rect(surf, bg, self.rect, border_radius=px(4))
        border_col = C["border_hi"] if self.active else C["border"]
        pygame.draw.rect(surf, border_col, self.rect, 1, border_radius=px(4))

        txt = F["btn"].render(self.label, True, tc)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def is_clicked(self, event: pygame.event.Event) -> bool:
        return (
            self.enabled
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


@dataclass
class TextInput:
    rect: pygame.Rect
    placeholder: str = ""
    text: str = ""
    active: bool = False
    _cursor_timer: float = 0.0
    _show_cursor: bool = True

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if Enter was pressed (submit)."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                return True
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode and len(self.text) < 120:
                self.text += event.unicode
        return False

    def update(self, dt: float) -> None:
        self._cursor_timer += dt
        if self._cursor_timer >= 0.5:
            self._cursor_timer = 0.0
            self._show_cursor = not self._show_cursor

    def draw(self, surf: pygame.Surface) -> None:
        pygame.draw.rect(surf, C["btn"], self.rect, border_radius=px(4))
        border = C["border_hi"] if self.active else C["border"]
        pygame.draw.rect(surf, border, self.rect, 1, border_radius=px(4))

        display = self.text if self.text else self.placeholder
        color   = C["text"] if self.text else C["text_dim"]
        cursor  = "|" if (self.active and self._show_cursor) else ""
        rendered = F["input"].render(display + cursor, True, color)
        surf.blit(rendered, (self.rect.x + px(8), self.rect.y + (self.rect.h - rendered.get_height()) // 2))

    def clear(self) -> None:
        self.text = ""
        self.active = False


def draw_text(surf: pygame.Surface, font_key: str, text: str,
              color: tuple, x: int, y: int, max_w: int = 0) -> int:
    """Draw text, optionally word-wrapping. Returns y after last line."""
    font = F[font_key]
    if max_w <= 0:
        s = font.render(text, True, color)
        surf.blit(s, (x, y))
        return y + s.get_height() + px(2)

    words = text.split()
    line, lines = [], []
    for w in words:
        test = " ".join(line + [w])
        if font.size(test)[0] > max_w and line:
            lines.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(" ".join(line))

    for l in lines:
        s = font.render(l, True, color)
        surf.blit(s, (x, y))
        y += s.get_height() + px(2)
    return y


def draw_divider(surf: pygame.Surface, rect: pygame.Rect, y: int) -> None:
    pygame.draw.line(surf, C["sep"], (rect.x + px(8), y), (rect.right - px(8), y))


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
        actions = []
        for name, npc in self.npcs.items():
            ev = [i for i, loc in self.evidence_locations.items() if loc and loc != "__hidden__"]
            other = [r for r in ROOMS if r != npc["current_room"]]
            if npc["is_killer"]:
                if ev and random.random() < 0.5:
                    action, target = "hide_evidence", random.choice(ev)
                elif other and npc["current_room"] == self.player_room:
                    action, target = "move", random.choice(other)
                else:
                    action, target = "stay_calm", ""
            else:
                roll = random.random()
                if roll < 0.35:
                    action, target = "stay_calm", ""
                elif roll < 0.55 and other:
                    action, target = "move", random.choice(other)
                elif roll < 0.70:
                    action, target = "investigate", ""
                elif npc["personality"] == "nervous":
                    action, target = "act_nervous", ""
                else:
                    action, target = "stay_calm", ""
            actions.append({"npc_name": name, "action": action, "target": target,
                            "secondary_target": None, "internal_thought": "(fallback)"})
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


# ═══════════════════════════════════════════════════════════════════════════
# DRAWING — MAP
# ═══════════════════════════════════════════════════════════════════════════

def draw_room(surf: pygame.Surface, name: str, gs: GameState,
              hovered: str, selected_npc: str, selected_ev: str) -> None:
    rect = ROOM_RECTS[name]
    is_current = name == gs.player_room
    is_hover   = name == hovered and not is_current

    bg = ROOM_BG.get(name, C["btn"])
    if is_current:
        bg = tuple(min(c + 12, 255) for c in bg)
    if is_hover:
        bg = tuple(min(c + 8, 255) for c in bg)

    pygame.draw.rect(surf, bg, rect, border_radius=6)
    border = C["border_hi"] if is_current else C["border"]
    pygame.draw.rect(surf, border, rect, 2 if is_current else 1, border_radius=6)

    # Room title
    display = f"{'★ ' if is_current else ''}{name.capitalize()}"
    title_col = C["text_hi"] if is_current else C["text"]
    t = F["room"].render(display, True, title_col)
    surf.blit(t, (rect.x + 8, rect.y + 6))

    # Evidence items
    ev_items = gs.evidence_in_room(name)
    ex = rect.x + px(8)
    ey = rect.y + px(30)
    max_ev_w = rect.w - px(30)  # leave space for NPC circles on the right
    for item in ev_items:
        label = item.replace("_", " ")
        sel = item == selected_ev
        ic  = pygame.Rect(ex, ey, px(14), px(14))
        pygame.draw.rect(surf, C["gold"] if not sel else (255, 240, 100), ic, border_radius=2)
        if sel:
            pygame.draw.rect(surf, C["border_hi"], ic, 1, border_radius=2)
        et = F["room_sm"].render(label, True, C["gold"] if not sel else C["text_hi"])
        # Clip the label so it never overflows the room width
        clip_w = min(et.get_width(), rect.right - ex - px(18) - px(4))
        surf.blit(et, (ex + px(18), ey), area=pygame.Rect(0, 0, clip_w, et.get_height()))
        ey += px(18)
        if ey > rect.bottom - px(20):
            break

    # NPCs in this room — draw inside a clip rect so labels never escape the border
    npcs_here = gs.npcs_in_room(name)
    nx = rect.right - px(12)
    ny = rect.y + rect.h - px(32)
    old_clip = surf.get_clip()
    surf.set_clip(rect)
    for npc in npcs_here:
        first = npc["name"].split()[0]
        is_sel = npc["name"] == selected_npc
        col    = npc["color"]
        radius = px(14) if is_sel else px(11)
        cx     = nx - radius
        cy     = ny

        pygame.draw.circle(surf, col, (cx, cy), radius)
        if is_sel:
            pygame.draw.circle(surf, C["border_hi"], (cx, cy), radius, 2)

        nt = F["room_sm"].render(first, True, (255, 255, 255))
        surf.blit(nt, (cx - nt.get_width() // 2, cy + radius + px(1)))
        nx -= radius * 2 + px(24)
    surf.set_clip(old_clip)

    # Pressure indicator for visible NPCs
    if npcs_here and is_current:
        pi = rect.x + px(8)
        for npc in npcs_here:
            p = npc["pressure"]
            if p > 0:
                bar_w = min(p * px(8), px(80))
                bar_r = pygame.Rect(pi, rect.bottom - px(10), bar_w, px(5))
                pygame.draw.rect(surf, C["red"] if p > 6 else C["amber"], bar_r, border_radius=px(2))
                pi += bar_w + px(4)


def draw_map(surf: pygame.Surface, gs: GameState,
             hovered_room: str, selected_npc: str, selected_ev: str) -> None:
    pygame.draw.rect(surf, C["bg"], MAP_RECT)
    for name in ROOMS:
        draw_room(surf, name, gs, hovered_room, selected_npc, selected_ev)


# ═══════════════════════════════════════════════════════════════════════════
# DRAWING — HUD
# ═══════════════════════════════════════════════════════════════════════════

def draw_hud(surf: pygame.Surface, gs: GameState) -> None:
    pygame.draw.rect(surf, C["hud"], HUD_RECT)
    pygame.draw.line(surf, C["border"], (0, HUD_H - 1), (WIN_W, HUD_H - 1))

    phase_txt = {Phase.PLAYER: "YOUR TURN", Phase.NPC: "NPCs THINKING…", Phase.EVENT: "EVENT"}
    phase_col = {Phase.PLAYER: C["green"], Phase.NPC: C["amber"], Phase.EVENT: C["text_hi"]}

    cx, y = px(12), px(14)
    for text, color in [
        (f"Turn {gs.turn}/{MAX_TURNS}", C["text"]),
        ("  |  ", C["sep"]),
        (phase_txt.get(gs.phase, ""), phase_col.get(gs.phase, C["text"])),
        (f"  AP: {gs.ap}/{PLAYER_AP}" if gs.phase == Phase.PLAYER else "", C["text"]),
        ("  |  ", C["sep"]),
        (f"Location: {gs.player_room.capitalize()}", C["text_hi"]),
    ]:
        if not text:
            continue
        s = F["hud"].render(text, True, color)
        surf.blit(s, (cx, y))
        cx += s.get_width()


# ═══════════════════════════════════════════════════════════════════════════
# DRAWING — SIDE PANEL
# ═══════════════════════════════════════════════════════════════════════════

def draw_panel(surf: pygame.Surface, gs: GameState,
               buttons: dict[str, Button], selected_npc: str, selected_ev: str,
               thinking: bool, clickables: dict) -> None:
    """Draw side panel. Populates `clickables` with {"npc:<name>": Rect, "ev:<item>": Rect}."""
    clickables.clear()
    pygame.draw.rect(surf, C["panel"], SIDE_RECT)
    pygame.draw.line(surf, C["border"], (SIDE_RECT.x, SIDE_RECT.y),
                     (SIDE_RECT.x, SIDE_RECT.bottom))

    x0, w = SIDE_RECT.x + px(10), SIDE_RECT.w - px(20)
    y = SIDE_RECT.y + px(10)

    # NPCs in current room
    npcs_here = gs.npcs_in_room(gs.player_room)
    y = draw_text(surf, "panel", f"In the {gs.player_room.capitalize()}:", C["text_hi"], x0, y)
    y += px(4)
    if npcs_here:
        for npc in npcs_here:
            row_rect = pygame.Rect(x0, y, w, px(22))
            sel  = npc["name"] == selected_npc
            hovered = row_rect.collidepoint(pygame.mouse.get_pos())
            if sel:
                pygame.draw.rect(surf, C["btn_hi"], row_rect, border_radius=px(3))
            elif hovered:
                pygame.draw.rect(surf, C["btn"], row_rect, border_radius=px(3))
            col = npc["color"]
            pygame.draw.circle(surf, col, (x0 + px(8), y + px(8)), px(7))
            if sel:
                pygame.draw.circle(surf, C["border_hi"], (x0 + px(8), y + px(8)), px(7), 2)
            label = npc["name"] + (f"  [P:{npc['pressure']}]" if npc["pressure"] > 0 else "")
            tc = C["text_hi"] if sel else C["text"]
            draw_text(surf, "panel_sm", label, tc, x0 + px(20), y + px(2))
            clickables[f"npc:{npc['name']}"] = row_rect
            y += px(22)
    else:
        y = draw_text(surf, "panel_sm", "  Nobody here", C["text_dim"], x0, y)
    y += px(6)

    draw_divider(surf, SIDE_RECT, y)
    y += px(8)

    # Evidence in current room
    ev_here = gs.evidence_in_room(gs.player_room)
    y = draw_text(surf, "panel", "Evidence here:", C["text_hi"], x0, y)
    y += px(4)
    if ev_here:
        for item in ev_here:
            row_rect = pygame.Rect(x0, y, w, px(18))
            sel = item == selected_ev
            hovered = row_rect.collidepoint(pygame.mouse.get_pos())
            if sel:
                pygame.draw.rect(surf, C["btn_hi"], row_rect, border_radius=px(3))
            elif hovered:
                pygame.draw.rect(surf, C["btn"], row_rect, border_radius=px(3))
            col = C["text_hi"] if sel else C["gold"]
            prefix = "▸ " if sel else "  "
            draw_text(surf, "panel_sm", prefix + item.replace("_", " "), col, x0, y)
            clickables[f"ev:{item}"] = row_rect
            y += px(18)
    else:
        y = draw_text(surf, "panel_sm", "  Nothing visible", C["text_dim"], x0, y)
    y += px(6)

    draw_divider(surf, SIDE_RECT, y)
    y += px(8)

    # Selection status
    if selected_ev:
        draw_text(surf, "panel_sm", f"Selected: {selected_ev.replace('_',' ')}", C["gold"], x0, y)
        y += px(18)
    if selected_npc:
        draw_text(surf, "panel_sm", f"Selected: {selected_npc}", C["text_hi"], x0, y)
        y += px(18)
    y += px(4)

    # Action buttons
    for key, btn in buttons.items():
        btn.draw(surf)

    if thinking:
        spin_x = SIDE_RECT.x + SIDE_RECT.w // 2
        spin_y = SIDE_RECT.bottom - px(30)
        t = F["panel_sm"].render("⏳ Waiting for LLM…", True, C["amber"])
        surf.blit(t, t.get_rect(center=(spin_x, spin_y)))


# ═══════════════════════════════════════════════════════════════════════════
# DRAWING — LOG BAR
# ═══════════════════════════════════════════════════════════════════════════

def draw_log(surf: pygame.Surface, gs: GameState) -> None:
    pygame.draw.rect(surf, C["log"], LOG_RECT)
    pygame.draw.line(surf, C["border"], (0, LOG_RECT.y), (WIN_W, LOG_RECT.y))

    recent = gs.log[-4:]
    y = LOG_RECT.y + px(6)
    for entry in recent:
        draw_text(surf, "log", entry[:160], (175, 155, 115), px(10), y, WIN_W - px(20))
        y += px(18)


# ═══════════════════════════════════════════════════════════════════════════
# OVERLAYS
# ═══════════════════════════════════════════════════════════════════════════

def draw_overlay_bg(surf: pygame.Surface, rect: pygame.Rect) -> None:
    """Semi-transparent dark overlay behind a dialog."""
    dark = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    dark.fill((6, 4, 12, 200))
    surf.blit(dark, (0, 0))
    pygame.draw.rect(surf, C["panel"], rect, border_radius=px(8))
    pygame.draw.rect(surf, C["border_hi"], rect, 2, border_radius=px(8))


def draw_interrogate_overlay(surf: pygame.Surface, state: dict) -> None:
    rect = pygame.Rect(WIN_W // 2 - px(420), WIN_H // 2 - px(240), px(840), px(480))
    draw_overlay_bg(surf, rect)
    x, y, w = rect.x + px(24), rect.y + px(20), rect.w - px(48)

    npc_name = state["npc_name"]
    npc = state["gs"].npcs.get(npc_name, {})
    col  = npc.get("color", C["text"])

    pygame.draw.circle(surf, col, (x + px(16), y + px(16)), px(14))
    draw_text(surf, "big", f"Interrogating {npc_name}", C["text_hi"], x + px(36), y + px(4))
    y += px(44)
    draw_text(surf, "panel_sm",
              f"{npc.get('personality','').capitalize()} {npc.get('relationship','')}  "
              f"| Pressure: {npc.get('pressure',0)}/10",
              C["text_dim"], x, y)
    y += px(24)

    draw_divider(surf, rect, y)
    y += 10

    # Response area
    response = state.get("response")
    if state.get("waiting"):
        draw_text(surf, "panel", "⏳  Awaiting response…", C["amber"], x, y)
    elif response:
        emotion_map = {
            "calm":"😐", "nervous":"😰", "angry":"😠",
            "defensive":"🛡", "tearful":"😢", "smug":"😏",
        }
        em = emotion_map.get(response.get("emotion","calm"), "")
        draw_text(surf, "panel_sm", f"{em} {response.get('emotion','calm').capitalize()}", C["amber"], x, y)
        y += px(22)
        y = draw_text(surf, "panel",
                      f'"{response.get("dialogue","")}"',
                      C["text"], x, y, max_w=w)
        y += 10
        if response.get("lie"):
            draw_text(surf, "panel_sm", "⚠ Something about this feels inconsistent.", C["red"], x, y)
            y += px(18)
    else:
        draw_text(surf, "panel_sm", "Ask the suspect a question.", C["text_dim"], x, y)

    # Text input
    state["input"].rect = pygame.Rect(rect.x + px(24), rect.bottom - px(110), rect.w - px(48), px(40))
    state["input"].draw(surf)

    draw_text(surf, "panel_sm", "Type your question and press Enter — or click Ask",
              C["text_dim"], x, rect.bottom - px(62))

    state["btn_ask"].rect    = pygame.Rect(rect.x + px(24),       rect.bottom - px(42), px(120), px(34))
    state["btn_cancel"].rect = pygame.Rect(rect.right - px(144),  rect.bottom - px(42), px(120), px(34))
    state["btn_ask"].draw(surf)
    state["btn_cancel"].draw(surf)


def draw_accuse_overlay(surf: pygame.Surface, state: dict) -> None:
    rect = pygame.Rect(WIN_W // 2 - px(360), WIN_H // 2 - px(200), px(720), px(400))
    draw_overlay_bg(surf, rect)
    x, y, w = rect.x + px(24), rect.y + px(20), rect.w - px(48)

    draw_text(surf, "big", "Make Your Accusation", C["text_hi"], x, y)
    y += px(48)

    draw_text(surf, "panel", "Select suspect:", C["text"], x, y)
    y += px(26)
    suspects = list(state["gs"].npcs.keys())
    sel = state.get("selected_suspect", "")
    for sname in suspects:
        is_sel = sname == sel
        col = NPC_PALETTE[suspects.index(sname) % len(NPC_PALETTE)]
        pygame.draw.circle(surf, col, (x + px(10), y + px(10)), px(8))
        tc = C["text_hi"] if is_sel else C["text"]
        bg = pygame.Rect(x + px(22), y, w - px(22), px(22))
        if is_sel:
            pygame.draw.rect(surf, C["btn_hi"], bg, border_radius=3)
        draw_text(surf, "panel", sname, tc, x + px(24), y + px(2))
        y += px(26)

    y += px(8)
    draw_text(surf, "panel", "State your motive:", C["text"], x, y)
    y += px(26)
    state["input"].rect = pygame.Rect(rect.x + px(24), y, rect.w - px(48), px(38))
    state["input"].draw(surf)
    y += px(50)

    state["btn_confirm"].rect = pygame.Rect(rect.x + px(24),       y, px(140), px(36))
    state["btn_cancel"].rect  = pygame.Rect(rect.right - px(164),  y, px(140), px(36))
    state["btn_confirm"].draw(surf)
    state["btn_cancel"].draw(surf)


def draw_notes_overlay(surf: pygame.Surface, gs: GameState, btn_close: Button) -> None:
    rect = pygame.Rect(px(60), px(60), WIN_W - px(120), WIN_H - px(120))
    draw_overlay_bg(surf, rect)
    x, y, w = rect.x + px(20), rect.y + px(16), rect.w - px(40)

    draw_text(surf, "big", "Detective's Notes", C["text_hi"], x, y)
    y += px(44)
    draw_divider(surf, rect, y)
    y += px(8)

    clip = surf.get_clip()
    surf.set_clip(pygame.Rect(x, y, w, rect.bottom - y - px(60)))
    for note in gs.notes:
        y = draw_text(surf, "panel_sm", f"• {note}", C["text"], x, y, max_w=w)
    surf.set_clip(clip)

    btn_close.rect = pygame.Rect(rect.right - px(130), rect.bottom - px(48), px(110), px(34))
    btn_close.draw(surf)


def draw_game_over(surf: pygame.Surface, state: dict) -> None:
    rect = pygame.Rect(WIN_W // 2 - px(380), WIN_H // 2 - px(200), px(760), px(400))
    draw_overlay_bg(surf, rect)
    x, y = rect.x + px(30), rect.y + px(30)

    outcome = state["gs"].outcome
    color = {"win": C["green"], "lose": C["red"], "partial": C["amber"]}.get(outcome, C["text"])
    label = {"win": "CASE SOLVED!", "lose": "CASE FAILED", "partial": "INCONCLUSIVE"}.get(outcome, "")

    draw_text(surf, "title", label, color, x, y)
    y += px(70)
    for line in state["gs"].outcome_msg.split("\n"):
        y = draw_text(surf, "big", line, C["text"], x, y)
    y += px(24)
    draw_text(surf, "panel_sm",
              f"Killer: {state['gs'].killer}  |  Motive: {state['gs'].motive}",
              C["text_dim"], x, y)

    state["btn_restart"].rect = pygame.Rect(rect.x + px(30),        rect.bottom - px(56), px(160), px(40))
    state["btn_quit"].rect    = pygame.Rect(rect.right - px(190),   rect.bottom - px(56), px(160), px(40))
    state["btn_restart"].draw(surf)
    state["btn_quit"].draw(surf)


def draw_title_screen(surf: pygame.Surface, server_ok: bool | None,
                      btn_start: Button, btn_how: Button, btn_check: Button) -> None:
    surf.fill(C["bg"])

    cx = WIN_W // 2
    t1 = F["title"].render("AI MURDER MYSTERY", True, C["text_hi"])
    t2 = F["hud"].render("A turn-based mystery with LLM-driven NPCs", True, C["text_dim"])
    surf.blit(t1, t1.get_rect(center=(cx, px(180))))
    surf.blit(t2, t2.get_rect(center=(cx, px(244))))

    # decorative divider
    pygame.draw.line(surf, C["border"], (cx - px(200), px(268)), (cx + px(200), px(268)))

    # Server status
    if server_ok is None:
        st, sc = "Server: checking…", C["text_dim"]
    elif server_ok:
        st, sc = "✓  LLM server online", C["green"]
    else:
        st, sc = "✗  LLM server offline — fallback mode will be used", C["amber"]

    s = F["hud"].render(st, True, sc)
    surf.blit(s, s.get_rect(center=(cx, px(300))))

    btn_start.rect = pygame.Rect(cx - px(120), px(356), px(240), px(52))
    btn_how.rect   = pygame.Rect(cx - px(80),  px(424), px(160), px(36))
    btn_check.rect = pygame.Rect(cx - px(80),  px(474), px(160), px(36))
    btn_start.draw(surf)
    btn_how.draw(surf)
    btn_check.draw(surf)

    instructions = [
        "Click rooms on the map to move  •  Click evidence to examine  •  Click NPCs to select them",
        "Use the side panel to Interrogate, End Turn, or Accuse",
        "Identify the killer and their motive before 15 turns pass",
    ]
    iy = px(530)
    for line in instructions:
        s = F["panel_sm"].render(line, True, C["text_dim"])
        surf.blit(s, s.get_rect(center=(cx, iy)))
        iy += px(22)


def draw_tutorial_screen(surf: pygame.Surface, btn_back: Button) -> None:
    surf.fill(C["bg"])
    cx = WIN_W // 2

    # Title bar
    t = F["big"].render("HOW TO PLAY", True, C["text_hi"])
    surf.blit(t, t.get_rect(center=(cx, px(36))))
    pygame.draw.line(surf, C["border_hi"], (cx - px(260), px(62)), (cx + px(260), px(62)))

    col_l = px(60)
    col_r = WIN_W // 2 + px(20)
    col_w = WIN_W // 2 - px(80)
    y_l   = px(80)
    y_r   = px(80)

    def _section(title: str, items: list[str], x: int, y: int) -> int:
        surf.blit(F["panel"].render(title, True, C["gold"]), (x, y))
        y += px(24)
        pygame.draw.line(surf, C["sep"], (x, y), (x + col_w, y))
        y += px(8)
        for item in items:
            y = draw_text(surf, "panel_sm", item, C["text"], x, y, max_w=col_w)
            y += px(4)
        return y + px(12)

    # ── Left column ──────────────────────────────────────────────────────
    y_l = _section("OBJECTIVE", [
        "Lord Ashworth has been murdered. You have 15 turns to identify the killer "
        "and state their motive — before they escape.",
    ], col_l, y_l)

    y_l = _section("YOUR TURN  (2 Action Points per turn)", [
        "Move — click any room on the map  (1 AP)",
        "Examine — select evidence, then click 'Examine Selected'  (1 AP)",
        "Interrogate — select an NPC in your room, click 'Interrogate Selected', "
        "type a question and press Enter  (1 AP)",
        "End Turn — skip remaining AP and let NPCs act immediately",
    ], col_l, y_l)

    y_l = _section("MAKING AN ACCUSATION", [
        "Click 'Accuse...' at any time during your turn.",
        "Select the suspect you believe committed the murder.",
        "Type the motive (e.g. 'prevent exposure of embezzlement').",
        "Right suspect + right motive  →  CASE SOLVED  ✓",
        "Right suspect, wrong motive  →  Inconclusive  ⚠",
        "Wrong suspect  →  The killer escapes  ✗",
    ], col_l, y_l)

    # ── Right column ─────────────────────────────────────────────────────
    y_r = _section("NPC BEHAVIOUR  (AI-driven)", [
        "After your turn, each NPC acts using the local language model.",
        "Innocent suspects move, gossip, and investigate.",
        "The killer may hide or destroy evidence, avoid you, or act suspiciously calm.",
        "The pressure bar under an NPC circle shows how rattled they are — "
        "red means they are close to cracking.",
    ], col_r, y_r)

    y_r = _section("EVIDENCE", [
        "Gold squares in a room mark evidence you can examine.",
        "Examined clues appear in your Notes — press 'View Notes' to review them.",
        "Critical evidence can be destroyed by the killer. Act quickly!",
        "If all critical evidence is gone, the case becomes unsolvable.",
    ], col_r, y_r)

    y_r = _section("TIPS", [
        "Spend the first few turns sweeping every room for evidence.",
        "Interrogate each suspect at least once — liars show inconsistencies (⚠ warning shown).",
        "Bring evidence to interrogations for stronger, more revealing reactions.",
        "Compare alibis across suspects — the killer's story will eventually contradict itself.",
        "Use 'View Notes' to review all testimony before making your accusation.",
    ], col_r, y_r)

    # Back button centred at bottom
    btn_back.rect = pygame.Rect(cx - px(80), WIN_H - px(54), px(160), px(40))
    btn_back.draw(surf)


def draw_loading_screen(surf: pygame.Surface, tick: int) -> None:
    surf.fill(C["bg"])
    dots = "." * (1 + (tick // 20) % 4)
    t = F["big"].render(f"Generating mystery{dots}", True, C["text_hi"])
    surf.blit(t, t.get_rect(center=(WIN_W // 2, WIN_H // 2)))
    t2 = F["panel_sm"].render("Asking the LLM to devise a murder…", True, C["text_dim"])
    surf.blit(t2, t2.get_rect(center=(WIN_W // 2, WIN_H // 2 + px(50))))


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GAME CLASS
# ═══════════════════════════════════════════════════════════════════════════

class Screen(Enum):
    TITLE    = auto()
    TUTORIAL = auto()
    LOADING  = auto()
    GAME     = auto()
    GAME_OVER = auto()

class Overlay(Enum):
    NONE         = auto()
    INTERROGATE  = auto()
    ACCUSE       = auto()
    NOTES        = auto()


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption(TITLE)

        # Detect Retina / HiDPI: SDL_WINDOW_ALLOW_HIGHDPI = 0x2000
        _SDL_HIGHDPI = 0x2000
        _probe = pygame.display.set_mode((1280, 720), _SDL_HIGHDPI)
        _dpr = max(1, _probe.get_width() // 1280)
        _apply_dpr(_dpr)

        self.surf = pygame.display.set_mode((WIN_W, WIN_H), _SDL_HIGHDPI)
        self.clock = pygame.time.Clock()
        _init_fonts()

        self.client = LLMClient()
        self.gs     = GameState()

        self.screen  = Screen.TITLE
        self.overlay = Overlay.NONE

        self.hovered_room   = ""
        self.selected_npc   = ""
        self.selected_ev    = ""
        self.thinking       = False
        self.server_ok: bool | None = None
        self.tick = 0

        # Persistent buttons in side panel
        self.panel_btns: dict[str, Button] = {}
        self._build_panel_buttons()
        self.panel_clickables: dict[str, pygame.Rect] = {}  # populated each frame by draw_panel

        # Overlay states
        self.interrogate_state: dict = {}
        self.accuse_state: dict      = {}
        self.btn_notes_close = Button(pygame.Rect(0, 0, px(110), px(34)), "Close")

        # Title screen buttons
        self.btn_start    = Button(pygame.Rect(0, 0, px(240), px(52)), "New Investigation")
        self.btn_how      = Button(pygame.Rect(0, 0, px(160), px(36)), "How to Play")
        self.btn_check    = Button(pygame.Rect(0, 0, px(160), px(36)), "Check Server")
        self.btn_tut_back = Button(pygame.Rect(0, 0, px(160), px(40)), "← Back to Menu")

        # Game-over buttons
        self.go_state: dict = {}

    # ── Panel button layout ─────────────────────────────────────────────

    def _build_panel_buttons(self) -> None:
        bx = SIDE_RECT.x + px(10)
        bw = SIDE_RECT.w - px(20)
        by = SIDE_RECT.y + px(310)   # approximate starting y; adjusted at draw time

        specs = [
            ("examine",     "Examine Selected",    True),
            ("interrogate", "Interrogate Selected", True),
            ("end_turn",    "End Turn →",           True),
            ("accuse",      "Accuse…",              True),
            ("notes",       "View Notes",           True),
        ]
        bh, gap = px(36), px(6)
        for i, (key, label, enabled) in enumerate(specs):
            self.panel_btns[key] = Button(
                pygame.Rect(bx, by + i * (bh + gap), bw, bh),
                label, enabled,
            )

    def _update_panel_button_positions(self) -> None:
        """Re-stack buttons below the dynamic content in the side panel."""
        # Place buttons at a fixed y so they don't overlap NPC/evidence lists
        base_y = SIDE_RECT.y + SIDE_RECT.h - px(260)
        bx, bw = SIDE_RECT.x + px(10), SIDE_RECT.w - px(20)
        bh, gap = px(36), px(6)
        for i, btn in enumerate(self.panel_btns.values()):
            btn.rect = pygame.Rect(bx, base_y + i * (bh + gap), bw, bh)

        can = self.gs.can_act()
        self.panel_btns["examine"].enabled     = can and bool(self.selected_ev) and \
                                                 self.gs.evidence_locations.get(self.selected_ev) == self.gs.player_room
        self.panel_btns["interrogate"].enabled = can and bool(self.selected_npc) and \
                                                 any(n["name"] == self.selected_npc
                                                     for n in self.gs.npcs_in_room(self.gs.player_room))
        self.panel_btns["end_turn"].enabled    = self.gs.phase == Phase.PLAYER and not self.thinking
        self.panel_btns["accuse"].enabled      = self.gs.phase == Phase.PLAYER

    # ── Main loop ───────────────────────────────────────────────────────

    def run(self) -> None:
        while True:
            dt   = self.clock.tick(FPS) / 1000.0
            self.tick += 1

            self._poll_llm_results()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                self._handle_event(event)

            self._draw(dt)
            pygame.display.flip()

    # ── LLM result polling ──────────────────────────────────────────────

    def _poll_llm_results(self) -> None:
        try:
            while True:
                tag, data, err = self.client.result_queue.get_nowait()
                self._on_llm_result(tag, data, err)
        except queue.Empty:
            pass

    def _on_llm_result(self, tag: str, data: dict | None, err: str | None) -> None:
        if tag == "setup":
            self.thinking = False
            if data:
                self.gs.apply_mystery_setup(data)
            else:
                # Fallback: generate minimal mystery locally
                self._apply_fallback_setup()
            self.screen = Screen.GAME

        elif tag == "npc_actions":
            self.thinking = False
            actions = data.get("actions", []) if data else self.gs.fallback_actions()
            self.gs.end_npc_and_event(actions)
            if self.gs.outcome:
                self._open_game_over()

        elif tag == "interrogate":
            self.thinking = False
            if data:
                self.gs.record_interrogation(
                    self.interrogate_state.get("npc_name", ""),
                    data,
                )
                self.interrogate_state["response"] = data
                self.interrogate_state["waiting"]  = False
            else:
                fallback = {"dialogue": "I… I have nothing to say.",
                            "lie": False, "emotion": "nervous", "internal_thought": ""}
                self.gs.record_interrogation(self.interrogate_state.get("npc_name",""), fallback)
                self.interrogate_state["response"] = fallback
                self.interrogate_state["waiting"]  = False

    def _apply_fallback_setup(self) -> None:
        """Used when the LLM server is offline at game start."""
        killer_bp = random.choice(SUSPECT_BLUEPRINTS)
        motives = [
            "stands to inherit the entire estate",
            "preventing exposure of embezzlement",
            "eliminating a witness",
            "revenge for a disputed will",
        ]
        data = {
            "killer_name": killer_bp["name"],
            "motive": random.choice(motives),
            "evidence_placements": {item: random.choice(ROOMS) for item in random.sample(EVIDENCE_ITEMS, 5)},
            "true_alibis": {bp["name"]: f"was in the {random.choice(ROOMS)}" for bp in SUSPECT_BLUEPRINTS},
            "false_alibis": {killer_bp["name"]: f"was in the {random.choice(ROOMS)}"},
            "critical_evidence": random.sample(EVIDENCE_ITEMS, 3),
            "initial_npc_positions": {bp["name"]: random.choice(ROOMS) for bp in SUSPECT_BLUEPRINTS},
        }
        self.gs.apply_mystery_setup(data)

    # ── Event handling ──────────────────────────────────────────────────

    def _handle_event(self, event: pygame.event.Event) -> None:
        # Global: Escape goes back to title from tutorial, or closes overlay in game
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.screen == Screen.TUTORIAL:
                self.screen = Screen.TITLE
            else:
                self.overlay = Overlay.NONE
            return

        if self.screen == Screen.TITLE:
            self._handle_title(event)
        elif self.screen == Screen.TUTORIAL:
            if self.btn_tut_back.is_clicked(event):
                self.screen = Screen.TITLE
        elif self.screen == Screen.GAME:
            if   self.overlay == Overlay.INTERROGATE:
                self._handle_interrogate(event)
            elif self.overlay == Overlay.ACCUSE:
                self._handle_accuse(event)
            elif self.overlay == Overlay.NOTES:
                if self.btn_notes_close.is_clicked(event):
                    self.overlay = Overlay.NONE
            else:
                self._handle_game(event)
        elif self.screen == Screen.GAME_OVER:
            if self.go_state.get("btn_restart") and self.go_state["btn_restart"].is_clicked(event):
                self._start_new_game()
            if self.go_state.get("btn_quit") and self.go_state["btn_quit"].is_clicked(event):
                pygame.quit()
                sys.exit()

    def _handle_title(self, event: pygame.event.Event) -> None:
        if self.btn_start.is_clicked(event):
            self._start_new_game()
        if self.btn_how.is_clicked(event):
            self.screen = Screen.TUTORIAL
        if self.btn_check.is_clicked(event):
            self.server_ok = None
            threading.Thread(target=self._do_health_check, daemon=True).start()

    def _do_health_check(self) -> None:
        result = self.client.check_health()
        self.server_ok = result is not None and result.get("model_loaded", False)

    def _start_new_game(self) -> None:
        self.gs = GameState()
        self.selected_npc = ""
        self.selected_ev  = ""
        self.overlay      = Overlay.NONE
        self.thinking     = True
        self.screen       = Screen.LOADING
        self.client.request_setup(SUSPECT_BLUEPRINTS, ROOMS, EVIDENCE_ITEMS)

    def _handle_game(self, event: pygame.event.Event) -> None:
        if self.thinking or self.gs.phase != Phase.PLAYER:
            return

        # Panel buttons
        if self.panel_btns["examine"].is_clicked(event):
            self.gs.examine(self.selected_ev)
            self.selected_ev = ""
            self._maybe_trigger_npc()

        elif self.panel_btns["interrogate"].is_clicked(event):
            if self.gs.spend_for_interrogate():
                self._open_interrogate(self.selected_npc)
            # NPC phase (if AP ran out) is triggered when the overlay closes

        elif self.panel_btns["end_turn"].is_clicked(event):
            self.gs.phase = Phase.NPC
            self._trigger_npc_phase()

        elif self.panel_btns["accuse"].is_clicked(event):
            self._open_accuse()

        elif self.panel_btns["notes"].is_clicked(event):
            self.overlay = Overlay.NOTES

        # Panel NPC / evidence row clicks (select by clicking the list)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and \
                SIDE_RECT.collidepoint(event.pos):
            for key, rect in self.panel_clickables.items():
                if rect.collidepoint(event.pos):
                    if key.startswith("npc:"):
                        name = key[4:]
                        self.selected_npc = "" if self.selected_npc == name else name
                        self.selected_ev  = ""
                    elif key.startswith("ev:"):
                        item = key[3:]
                        self.selected_ev  = "" if self.selected_ev == item else item
                        self.selected_npc = ""
                    break

        # Map clicks: move to room or select NPC/evidence on map
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            clicked_room = None
            for rname, rrect in ROOM_RECTS.items():
                if rrect.collidepoint(pos):
                    clicked_room = rname
                    break

            if clicked_room:
                if clicked_room != self.gs.player_room:
                    self.gs.move(clicked_room)
                    self.selected_npc = ""
                    self.selected_ev  = ""
                    if self.gs.phase == Phase.NPC:
                        self._trigger_npc_phase()
                else:
                    # Same room: check if clicking an NPC dot or evidence square
                    self._try_select_in_room(clicked_room, pos)

    def _try_select_in_room(self, room: str, pos: tuple) -> None:
        rect = ROOM_RECTS[room]
        # Check NPCs (circles near right edge)
        npcs_here = self.gs.npcs_in_room(room)
        nx = rect.right - 12
        ny = rect.y + rect.h - 32
        for npc in npcs_here:
            radius = 14
            cx = nx - radius
            if math.dist((cx, ny), pos) <= radius + 4:
                self.selected_npc = npc["name"]
                return
            nx -= radius * 2 + 24

        # Check evidence (small squares near top-left)
        ev_here = self.gs.evidence_in_room(room)
        ey = rect.y + 30
        for item in ev_here:
            ic = pygame.Rect(rect.x + 8, ey, 80, 16)
            if ic.collidepoint(pos):
                self.selected_ev = item
                return
            ey += 18

    def _trigger_npc_phase(self) -> None:
        self.thinking = True
        self.client.request_npc_actions(self.gs.as_dict())

    def _maybe_trigger_npc(self) -> None:
        """Call after any player action — fires NPC phase if AP just ran out."""
        if self.gs.phase == Phase.NPC and not self.thinking:
            self._trigger_npc_phase()

    # ── Interrogation overlay ───────────────────────────────────────────

    def _open_interrogate(self, npc_name: str) -> None:
        self.overlay = Overlay.INTERROGATE
        self.interrogate_state = {
            "npc_name":   npc_name,
            "gs":         self.gs,
            "response":   None,
            "waiting":    False,
            "input":      TextInput(pygame.Rect(0, 0, px(792), px(40)), placeholder="Type your question…"),
            "btn_ask":    Button(pygame.Rect(0, 0, px(120), px(34)), "Ask"),
            "btn_cancel": Button(pygame.Rect(0, 0, px(120), px(34)), "Close"),
        }

    def _handle_interrogate(self, event: pygame.event.Event) -> None:
        st = self.interrogate_state
        if st["btn_cancel"].is_clicked(event):
            self.overlay = Overlay.NONE
            self._maybe_trigger_npc()  # fire NPC phase if interrogation used the last AP
            return

        submitted = st["input"].handle_event(event)
        if (st["btn_ask"].is_clicked(event) or submitted) and not st.get("waiting"):
            question = st["input"].text.strip()
            if question:
                st["waiting"]  = True
                st["response"] = None
                self.thinking  = True
                self.client.request_interrogate(
                    self.gs.npc_dict(st["npc_name"]),
                    question,
                    self.gs.found_evidence,
                    self.gs.as_dict(),
                )

    # ── Accusation overlay ──────────────────────────────────────────────

    def _open_accuse(self) -> None:
        suspects = list(self.gs.npcs.keys())
        self.overlay = Overlay.ACCUSE
        self.accuse_state = {
            "gs":               self.gs,
            "selected_suspect": suspects[0] if suspects else "",
            "input":            TextInput(pygame.Rect(0, 0, px(672), px(38)), placeholder="e.g. to prevent exposure of embezzlement"),
            "btn_confirm":      Button(pygame.Rect(0, 0, px(140), px(36)), "Accuse!"),
            "btn_cancel":       Button(pygame.Rect(0, 0, px(140), px(36)), "Cancel"),
        }

    def _handle_accuse(self, event: pygame.event.Event) -> None:
        st = self.accuse_state
        if st["btn_cancel"].is_clicked(event):
            self.overlay = Overlay.NONE
            return

        if st["btn_confirm"].is_clicked(event):
            suspect = st["selected_suspect"]
            motive  = st["input"].text.strip()
            if suspect and motive:
                self.gs.accuse(suspect, motive)
                self.overlay = Overlay.NONE
                self._open_game_over()
            return

        # Suspect selection by clicking name
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            suspects = list(self.gs.npcs.keys())
            rect = pygame.Rect(WIN_W // 2 - px(360), WIN_H // 2 - px(200), px(720), px(400))
            y = rect.y + px(94)
            for sname in suspects:
                row = pygame.Rect(rect.x + px(46), y, rect.w - px(70), px(22))
                if row.collidepoint(event.pos):
                    st["selected_suspect"] = sname
                    return
                y += px(26)

        st["input"].handle_event(event)

    # ── Game over ───────────────────────────────────────────────────────

    def _open_game_over(self) -> None:
        self.screen  = Screen.GAME_OVER
        self.overlay = Overlay.NONE
        self.go_state = {
            "gs":          self.gs,
            "btn_restart": Button(pygame.Rect(0, 0, px(160), px(40)), "New Game"),
            "btn_quit":    Button(pygame.Rect(0, 0, px(160), px(40)), "Quit"),
        }

    # ── Drawing ─────────────────────────────────────────────────────────

    def _draw(self, dt: float) -> None:
        self.surf.fill(C["bg"])

        if self.screen == Screen.TITLE:
            draw_title_screen(self.surf, self.server_ok, self.btn_start, self.btn_how, self.btn_check)
            return

        if self.screen == Screen.TUTORIAL:
            draw_tutorial_screen(self.surf, self.btn_tut_back)
            return

        if self.screen == Screen.LOADING:
            draw_loading_screen(self.surf, self.tick)
            return

        # ── Game screen ──
        self._update_panel_button_positions()

        # Hover detection for rooms
        mx, my = pygame.mouse.get_pos()
        self.hovered_room = ""
        if self.overlay == Overlay.NONE:
            for rname, rrect in ROOM_RECTS.items():
                if rrect.collidepoint(mx, my) and rname != self.gs.player_room:
                    self.hovered_room = rname

        draw_hud(self.surf, self.gs)
        draw_map(self.surf, self.gs, self.hovered_room, self.selected_npc, self.selected_ev)
        draw_panel(self.surf, self.gs, self.panel_btns, self.selected_npc, self.selected_ev, self.thinking, self.panel_clickables)
        draw_log(self.surf, self.gs)

        # Overlays
        if self.overlay == Overlay.INTERROGATE:
            if "input" in self.interrogate_state:
                self.interrogate_state["input"].update(dt)
            draw_interrogate_overlay(self.surf, self.interrogate_state)

        elif self.overlay == Overlay.ACCUSE:
            if "input" in self.accuse_state:
                self.accuse_state["input"].update(dt)
            draw_accuse_overlay(self.surf, self.accuse_state)

        elif self.overlay == Overlay.NOTES:
            draw_notes_overlay(self.surf, self.gs, self.btn_notes_close)

        if self.screen == Screen.GAME_OVER:
            draw_game_over(self.surf, self.go_state)


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    Game().run()
