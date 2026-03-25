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

import math
import queue
import random
import sys
import threading
from enum import Enum, auto

import pygame

import ui.theme as _t
from ui.theme import px, C, F, ROOM_RECTS, HUD_RECT, MAP_RECT, SIDE_RECT, LOG_RECT
from ui.theme import _apply_dpr, _init_fonts
from ui.widgets import Button, TextInput
from ui.map_view import draw_map
from ui.hud import draw_hud, draw_panel, draw_log
from ui.overlays import draw_interrogate_overlay, draw_accuse_overlay, draw_notes_overlay
from ui.screens import draw_title_screen, draw_tutorial_screen, draw_loading_screen, draw_game_over
from game.constants import TITLE, FPS, ROOMS, EVIDENCE_ITEMS, SUSPECT_BLUEPRINTS, PLAYER_AP
from game.state import Phase, GameState
from game.client import LLMClient
from game.fallbacks import _fallback_interrogate


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

        self.surf = pygame.display.set_mode((_t.WIN_W, _t.WIN_H), _SDL_HIGHDPI)
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
            q = self.interrogate_state.get("last_question", "")
            if data:
                self.gs.record_interrogation(
                    self.interrogate_state.get("npc_name", ""),
                    data,
                )
                self.interrogate_state["response"] = data
                self.interrogate_state["waiting"]  = False
                self.interrogate_state["history"].append({"question": q, "response": data})
            else:
                npc_name = self.interrogate_state.get("npc_name", "")
                fallback = _fallback_interrogate(
                    self.gs.npc_dict(npc_name) if npc_name in self.gs.npcs else {},
                    q,
                    self.gs.found_evidence,
                )
                self.gs.record_interrogation(npc_name, fallback)
                self.interrogate_state["response"] = fallback
                self.interrogate_state["waiting"]  = False
                self.interrogate_state["history"].append({"question": q, "response": fallback})

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
            "history":    [],   # list of {"question": str, "response": dict}
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
                st["waiting"]       = True
                st["response"]      = None
                st["last_question"] = question
                st["input"].text    = ""   # clear input immediately
                self.thinking = True
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
            rect = pygame.Rect(_t.WIN_W // 2 - px(360), _t.WIN_H // 2 - px(200), px(720), px(400))
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
