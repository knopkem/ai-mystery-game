from __future__ import annotations

import pygame

import ui.theme as _t
from ui.theme import px, C, F, HUD_RECT, SIDE_RECT, LOG_RECT
from ui.widgets import Button, draw_text, draw_divider
from game.constants import MAX_TURNS, PLAYER_AP
from game.state import Phase, GameState


# ═══════════════════════════════════════════════════════════════════════════
# DRAWING — HUD
# ═══════════════════════════════════════════════════════════════════════════

def draw_hud(surf: pygame.Surface, gs: GameState) -> None:
    pygame.draw.rect(surf, C["hud"], HUD_RECT)
    pygame.draw.line(surf, C["border"], (0, _t.HUD_H - 1), (_t.WIN_W, _t.HUD_H - 1))

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
    pygame.draw.line(surf, C["border"], (0, LOG_RECT.y), (_t.WIN_W, LOG_RECT.y))

    recent = gs.log[-4:]
    y = LOG_RECT.y + px(6)
    for entry in recent:
        draw_text(surf, "log", entry[:160], (175, 155, 115), px(10), y, _t.WIN_W - px(20))
        y += px(18)
