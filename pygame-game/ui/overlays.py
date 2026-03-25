from __future__ import annotations

import pygame

import ui.theme as _t
from ui.theme import px, C, F
from ui.widgets import Button, TextInput, draw_text, draw_divider, draw_overlay_bg
from game.constants import NPC_PALETTE
from game.state import GameState


# ═══════════════════════════════════════════════════════════════════════════
# OVERLAYS
# ═══════════════════════════════════════════════════════════════════════════

def draw_interrogate_overlay(surf: pygame.Surface, state: dict) -> None:
    rect = pygame.Rect(_t.WIN_W // 2 - px(420), _t.WIN_H // 2 - px(240), px(840), px(480))
    draw_overlay_bg(surf, rect)
    x, y, w = rect.x + px(24), rect.y + px(20), rect.w - px(48)

    npc_name = state["npc_name"]
    npc = state["gs"].npcs.get(npc_name, {})
    col = npc.get("color", C["text"])

    pygame.draw.circle(surf, col, (x + px(16), y + px(16)), px(14))
    draw_text(surf, "big", f"Interrogating {npc_name}", C["text_hi"], x + px(36), y + px(4))
    y += px(44)
    draw_text(surf, "panel_sm",
              f"{npc.get('personality','').capitalize()} {npc.get('relationship','')}  "
              f"| Pressure: {npc.get('pressure',0)}/10",
              C["text_dim"], x, y)
    y += px(24)
    draw_divider(surf, rect, y)
    y += px(10)

    # ── Conversation history area ────────────────────────────────────────
    history_bottom = rect.bottom - px(120)   # reserve space for input + buttons
    clip_rect = pygame.Rect(x, y, w, history_bottom - y)
    surf.set_clip(clip_rect)

    emotion_map = {
        "calm": "😐", "nervous": "😰", "angry": "😠",
        "defensive": "🛡", "tearful": "😢", "smug": "😏",
    }

    history = state.get("history", [])
    if not history and not state.get("waiting"):
        draw_text(surf, "panel_sm", "Ask the suspect a question.", C["text_dim"], x, y)
    else:
        # Draw older entries dimmed; keep track so newest is always visible
        entries_to_draw = history[-4:]  # show at most last 4 exchanges
        for entry in entries_to_draw:
            q   = entry["question"]
            resp = entry["response"]
            # Question line
            draw_text(surf, "panel_sm", f"You:  {q}", C["text_dim"], x, y, max_w=w)
            y += px(18)
            em = emotion_map.get(resp.get("emotion", "calm"), "")
            draw_text(surf, "panel_sm",
                      f"{em} {resp.get('emotion','calm').capitalize()}",
                      C["amber"], x, y)
            y += px(18)
            y = draw_text(surf, "panel",
                          f'"{resp.get("dialogue","")}"',
                          C["text"], x, y, max_w=w)
            if resp.get("lie"):
                draw_text(surf, "panel_sm", "⚠ Something about this feels inconsistent.",
                          C["red"], x, y)
                y += px(16)
            y += px(8)

    if state.get("waiting"):
        draw_text(surf, "panel", "⏳  Awaiting response…", C["amber"], x, y)

    surf.set_clip(None)

    # ── Input + buttons ──────────────────────────────────────────────────
    state["input"].rect = pygame.Rect(rect.x + px(24), rect.bottom - px(110), rect.w - px(48), px(40))
    state["input"].draw(surf)
    draw_text(surf, "panel_sm", "Type your question and press Enter — or click Ask",
              C["text_dim"], x, rect.bottom - px(62))
    state["btn_ask"].rect    = pygame.Rect(rect.x + px(24),      rect.bottom - px(42), px(120), px(34))
    state["btn_cancel"].rect = pygame.Rect(rect.right - px(144), rect.bottom - px(42), px(120), px(34))
    state["btn_ask"].draw(surf)
    state["btn_cancel"].draw(surf)


def draw_accuse_overlay(surf: pygame.Surface, state: dict) -> None:
    rect = pygame.Rect(_t.WIN_W // 2 - px(360), _t.WIN_H // 2 - px(200), px(720), px(400))
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
    rect = pygame.Rect(px(60), px(60), _t.WIN_W - px(120), _t.WIN_H - px(120))
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
