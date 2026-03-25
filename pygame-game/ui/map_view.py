from __future__ import annotations

import pygame

import ui.theme as _t
from ui.theme import px, C, F, ROOM_RECTS, ROOM_BG, MAP_RECT
from game.constants import ROOMS
from game.state import GameState


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
