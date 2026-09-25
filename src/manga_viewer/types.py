from __future__ import annotations

from dataclasses import dataclass

Box = tuple[int, int, int, int]  # x1, y1, x2, y2 (x2, y2 exclusive)
RGB = tuple[int, int, int]


@dataclass(frozen=True)
class TextBlock:
    id: int
    box: Box
    vertical: bool
    ja: str
    bg_color: RGB = (255, 255, 255)


@dataclass(frozen=True)
class PageAnalysis:
    width: int
    height: int
    blocks: tuple[TextBlock, ...]
