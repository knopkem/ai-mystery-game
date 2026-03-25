from __future__ import annotations

from dataclasses import dataclass

import pygame

import ui.theme as _t
from ui.theme import px, C, F


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


def draw_overlay_bg(surf: pygame.Surface, rect: pygame.Rect) -> None:
    """Semi-transparent dark overlay behind a dialog."""
    dark = pygame.Surface((_t.WIN_W, _t.WIN_H), pygame.SRCALPHA)
    dark.fill((6, 4, 12, 200))
    surf.blit(dark, (0, 0))
    pygame.draw.rect(surf, C["panel"], rect, border_radius=px(8))
    pygame.draw.rect(surf, C["border_hi"], rect, 2, border_radius=px(8))
