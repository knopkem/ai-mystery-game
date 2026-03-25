import pygame

# ═══════════════════════════════════════════════════════════════════════════
# THEME — layout globals, colours, fonts
# All DPR-mutable Rect objects are updated in place by _apply_dpr() so that
# any module that imports them directly always sees the current values.
# ═══════════════════════════════════════════════════════════════════════════

DPR = 1  # updated by _apply_dpr() at runtime

WIN_W, WIN_H = 1280, 720
HUD_H = 48
LOG_H = 88
MAP_W = 820
SIDE_W = WIN_W - MAP_W - 5

# Rect objects are initialised here and mutated in place by _apply_dpr()
HUD_RECT  = pygame.Rect(0,         0,      WIN_W,  HUD_H)
MAP_RECT  = pygame.Rect(0,         HUD_H,  MAP_W,  WIN_H - HUD_H - LOG_H)
SIDE_RECT = pygame.Rect(MAP_W + 5, HUD_H,  SIDE_W, WIN_H - HUD_H - LOG_H)
LOG_RECT  = pygame.Rect(0,         WIN_H - LOG_H, WIN_W, LOG_H)

# Room grid inside MAP_RECT
CELL_W, CELL_H, CELL_GAP = 397, 181, 8
GX = MAP_RECT.x + 6
GY = MAP_RECT.y + 6

ROOM_BG: dict[str, tuple] = {
    "foyer":   (38, 28, 16),
    "library": (16, 24, 38),
    "kitchen": (38, 20, 14),
    "bedroom": (26, 14, 38),
    "garden":  (14, 35, 14),
}

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
# FONTS — populated after pygame.init()
# ═══════════════════════════════════════════════════════════════════════════

F: dict[str, pygame.font.Font] = {}

# Room rects dict — populated/updated by _apply_dpr()
ROOM_RECTS: dict[str, pygame.Rect] = {}


def _room_rect(col: int, row: int, span: int = 1) -> pygame.Rect:
    return pygame.Rect(
        GX + col * (CELL_W + CELL_GAP),
        GY + row * (CELL_H + CELL_GAP),
        CELL_W * span + CELL_GAP * (span - 1),
        CELL_H,
    )


# Initialise ROOM_RECTS with default (DPR=1) values
ROOM_RECTS.update({
    "library":  _room_rect(0, 0),
    "foyer":    _room_rect(1, 0),
    "kitchen":  _room_rect(0, 1),
    "bedroom":  _room_rect(1, 1),
    "garden":   _room_rect(0, 2, span=2),
})


def px(n: int | float) -> int:
    """Scale a logical-pixel value by the current device pixel ratio."""
    return int(n * DPR)


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


def _apply_dpr(dpr: int) -> None:
    """Re-derive all layout globals for the detected device pixel ratio.
    Called once at startup before font init.
    Rect objects are mutated in place; int globals are reassigned via global."""
    global DPR, WIN_W, WIN_H, HUD_H, LOG_H, MAP_W, SIDE_W
    global CELL_W, CELL_H, CELL_GAP, GX, GY

    DPR   = dpr
    WIN_W = 1280 * dpr;  WIN_H  = 720 * dpr
    HUD_H = 48   * dpr;  LOG_H  = 88  * dpr
    MAP_W = 820  * dpr;  SIDE_W = WIN_W - MAP_W - 5 * dpr

    # Mutate Rects in place so all importers see the updated geometry
    HUD_RECT.update(0,              0,      WIN_W, HUD_H)
    MAP_RECT.update(0,              HUD_H,  MAP_W, WIN_H - HUD_H - LOG_H)
    SIDE_RECT.update(MAP_W + 5*dpr, HUD_H,  SIDE_W, WIN_H - HUD_H - LOG_H)
    LOG_RECT.update(0,              WIN_H - LOG_H, WIN_W, LOG_H)

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
