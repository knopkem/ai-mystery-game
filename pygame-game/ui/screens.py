from __future__ import annotations

import pygame

import ui.theme as _t
from ui.theme import px, C, F
from ui.widgets import Button, draw_text, draw_overlay_bg


# ═══════════════════════════════════════════════════════════════════════════
# SCREENS
# ═══════════════════════════════════════════════════════════════════════════

def draw_title_screen(surf: pygame.Surface, server_ok: bool | None,
                      btn_start: Button, btn_how: Button, btn_check: Button) -> None:
    surf.fill(C["bg"])

    cx = _t.WIN_W // 2
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
    cx = _t.WIN_W // 2

    # Title bar
    t = F["big"].render("HOW TO PLAY", True, C["text_hi"])
    surf.blit(t, t.get_rect(center=(cx, px(36))))
    pygame.draw.line(surf, C["border_hi"], (cx - px(260), px(62)), (cx + px(260), px(62)))

    col_l = px(60)
    col_r = _t.WIN_W // 2 + px(20)
    col_w = _t.WIN_W // 2 - px(80)
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
    btn_back.rect = pygame.Rect(cx - px(80), _t.WIN_H - px(54), px(160), px(40))
    btn_back.draw(surf)


def draw_loading_screen(surf: pygame.Surface, tick: int) -> None:
    surf.fill(C["bg"])
    dots = "." * (1 + (tick // 20) % 4)
    t = F["big"].render(f"Generating mystery{dots}", True, C["text_hi"])
    surf.blit(t, t.get_rect(center=(_t.WIN_W // 2, _t.WIN_H // 2)))
    t2 = F["panel_sm"].render("Asking the LLM to devise a murder…", True, C["text_dim"])
    surf.blit(t2, t2.get_rect(center=(_t.WIN_W // 2, _t.WIN_H // 2 + px(50))))


def draw_game_over(surf: pygame.Surface, state: dict) -> None:
    rect = pygame.Rect(_t.WIN_W // 2 - px(380), _t.WIN_H // 2 - px(200), px(760), px(400))
    draw_overlay_bg(surf, rect)
    x, y = rect.x + px(30), rect.y + px(30)

    outcome = state["gs"].outcome
    color = {"win": C["green"], "lose": C["red"], "partial": C["amber"]}.get(outcome, C["text"])
    label = {"win": "CASE SOLVED!", "lose": "CASE FAILED", "partial": "INCONCLUSIVE"}.get(outcome, "")

    draw_text(surf, "title", label, color, x, y)
    y += px(70)
    max_w = rect.width - px(60)
    for line in state["gs"].outcome_msg.split("\n"):
        y = draw_text(surf, "big", line, C["text"], x, y, max_w=max_w)
    y += px(24)
    draw_text(surf, "panel_sm",
              f"Killer: {state['gs'].killer}  |  Motive: {state['gs'].motive}",
              C["text_dim"], x, y, max_w=max_w)

    state["btn_restart"].rect = pygame.Rect(rect.x + px(30),        rect.bottom - px(56), px(160), px(40))
    state["btn_quit"].rect    = pygame.Rect(rect.right - px(190),   rect.bottom - px(56), px(160), px(40))
    state["btn_restart"].draw(surf)
    state["btn_quit"].draw(surf)
