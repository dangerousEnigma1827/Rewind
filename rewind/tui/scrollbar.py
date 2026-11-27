"""A thin scrollbar: a half-cell thumb on the panel's own dark track, instead of Textual's full reversed block.

Same geometry and mouse metadata as textual.scrollbar.ScrollBarRender (click above/below the thumb pages, drag the
thumb), so scrolling behaves exactly as before; only the drawing changes. ▐ and ─ exist in Cascadia, Consolas and
Lucida Console.
"""
from __future__ import annotations

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBarRender

VERTICAL_THUMB = "▐"
HORIZONTAL_THUMB = "─"  # a hairline: the tab bar's scrollbar sits right under the tabs' own underline


def thumb_span(size: int, virtual_size: float, window_size: float, position: float) -> tuple[int, int] | None:
    """(start, end) cells of the thumb along a track of `size` cells, or None when nothing scrolls."""
    if not (window_size and size and virtual_size) or virtual_size <= window_size or size == virtual_size:
        return None
    thumb = max(1, round(size * window_size / virtual_size))
    travel = virtual_size - window_size
    start = round((size - thumb) * min(max(position / travel, 0.0), 1.0)) if travel > 0 else 0
    return start, min(size, start + thumb)


class ThinScrollBarRender(ScrollBarRender):
    @classmethod
    def render_bar(cls, size: int = 25, virtual_size: float = 50, window_size: float = 20, position: float = 0,
                   thickness: int = 1, vertical: bool = True, back_color: Color = Color.parse("#08060D"),
                   bar_color: Color = Color.parse("#3A3448")) -> Segments:
        size = int(size)
        width = thickness if vertical else 1
        span = thumb_span(size, virtual_size, window_size, position)
        track = " " * width
        if span is None:
            segments = [Segment(track, Style(bgcolor=back_color))] * size
        else:
            start, end = span
            glyph = (" " * (width - 1) + VERTICAL_THUMB) if vertical else HORIZONTAL_THUMB
            up = Segment(track, Style(bgcolor=back_color, meta={"@mouse.down": "scroll_up"}))
            down = Segment(track, Style(bgcolor=back_color, meta={"@mouse.down": "scroll_down"}))
            thumb = Segment(glyph, Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "grab"}))
            segments = [up] * start + [thumb] * (end - start) + [down] * (size - end)
        if vertical:
            return Segments(segments, new_lines=True)
        return Segments((segments + [Segment.line()]) * thickness, new_lines=False)
