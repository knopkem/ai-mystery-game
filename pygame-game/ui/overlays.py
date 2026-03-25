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

    # ── Conversation history — render to tall surface, blit bottom slice ─
    history_top    = y
    history_bottom = rect.bottom - px(120)   # reserve space for input + buttons
    avail_h        = history_bottom - history_top

    emotion_map = {
        "calm": "😐", "nervous": "😰", "angry": "😠",
        "defensive": "🛡", "tearful": "😢", "smug": "😏",
    }

    history = state.get("history", [])

    # Render all content onto an oversized surface so we can auto-scroll
    CONTENT_H = max(avail_h, px(4000))
    content = pygame.Surface((w, CONTENT_H), pygame.SRCALPHA)
    cy = 0  # cursor on content surface

    if not history and not state.get("waiting"):
        draw_text(content, "panel_sm", "Ask the suspect a question.", C["text_dim"], 0, cy)
    else:
        for entry in history:
            q    = entry["question"]
            resp = entry["response"]
            draw_text(content, "panel_sm", f"You:  {q}", C["text_dim"], 0, cy, max_w=w)
            cy += px(18)
            em = emotion_map.get(resp.get("emotion", "calm"), "")
            draw_text(content, "panel_sm",
                      f"{em} {resp.get('emotion','calm').capitalize()}",
                      C["amber"], 0, cy)
            cy += px(18)
            cy = draw_text(content, "panel",
                           f'"{resp.get("dialogue","")}"',
                           C["text"], 0, cy, max_w=w)
            if resp.get("lie"):
                draw_text(content, "panel_sm", "⚠ Something about this feels inconsistent.",
                          C["red"], 0, cy)
                cy += px(16)
            cy += px(8)

    if state.get("waiting"):
        draw_text(content, "panel", "⏳  Awaiting response…", C["amber"], 0, cy)
        cy += px(24)

    # scroll offset: keep newest content pinned to bottom of the visible area
    scroll_y = max(0, cy - avail_h)

    old_clip = surf.get_clip()
    surf.set_clip(pygame.Rect(x, history_top, w, avail_h))
    surf.blit(content, (x, history_top), pygame.Rect(0, scroll_y, w, avail_h))
    surf.set_clip(old_clip)

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


def draw_thinking_popup(surf: pygame.Surface, message: str = "NPCs are deliberating") -> None:
    """Non-interactive popup shown while the LLM is processing. Auto-dismissed by caller."""
    W, H = px(380), px(110)
    rect = pygame.Rect(_t.WIN_W // 2 - W // 2, _t.WIN_H // 2 - H // 2, W, H)

    # dim the whole screen
    veil = pygame.Surface((_t.WIN_W, _t.WIN_H), pygame.SRCALPHA)
    veil.fill((0, 0, 0, 140))
    surf.blit(veil, (0, 0))

    draw_overlay_bg(surf, rect)

    # animated dots — cycle every 500 ms
    dots = "." * (pygame.time.get_ticks() // 500 % 4)
    label = f"{message}{dots}"

    # hourglass icon + message centred vertically
    icon_y = rect.centery - px(18)
    draw_text(surf, "big", "⏳", (215, 145, 30), rect.centerx - px(130), icon_y)
    draw_text(surf, "panel", label, (255, 215, 60),
              rect.centerx - px(85), icon_y + px(4))

    hint_y = rect.bottom - px(26)
    draw_text(surf, "panel_sm", "Please wait…", (130, 110, 75),
              rect.centerx - px(38), hint_y)


def draw_notes_overlay(surf: pygame.Surface, gs: GameState, btn_close: Button) -> None:
    rect = pygame.Rect(px(60), px(60), _t.WIN_W - px(120), _t.WIN_H - px(120))
    draw_overlay_bg(surf, rect)
    x, y, w = rect.x + px(20), rect.y + px(16), rect.w - px(40)

    draw_text(surf, "big", "Detective's Notes", C["text_hi"], x, y)
    y += px(44)
    draw_divider(surf, rect, y)
    y += px(8)

    content_top = y
    avail_h     = rect.bottom - content_top - px(60)   # leave room for Close button

    # Render all notes onto an off-screen surface; blit bottom slice so
    # newest note is always visible (same pattern as interrogation history).
    CONTENT_H = max(avail_h, px(4000))
    content   = pygame.Surface((w, CONTENT_H), pygame.SRCALPHA)
    cy = 0
    if gs.notes:
        for note in gs.notes:
            cy = draw_text(content, "panel_sm", f"• {note}", C["text"], 0, cy, max_w=w)
    else:
        draw_text(content, "panel_sm", "No notes yet — examine evidence and interrogate suspects.",
                  C["text_dim"], 0, cy)
        cy += px(20)

    scroll_y = max(0, cy - avail_h)

    old_clip = surf.get_clip()
    surf.set_clip(pygame.Rect(x, content_top, w, avail_h))
    surf.blit(content, (x, content_top), pygame.Rect(0, scroll_y, w, avail_h))
    surf.set_clip(old_clip)

    btn_close.rect = pygame.Rect(rect.right - px(130), rect.bottom - px(48), px(110), px(34))
    btn_close.draw(surf)
