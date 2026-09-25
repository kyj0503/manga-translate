"""Paint over detected speech bubbles and typeset the Korean translation into them."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

from .types import RGB, Box, TextBlock

DEFAULT_FONT = Path("C:/Windows/Fonts/malgun.ttf")
MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 72
LINE_SPACING = 1.15
PADDING_RATIO = 0.06  # of the box's shorter side, kept free on every edge
NARROW_ASPECT = 2.0  # height / width above which a box is treated as a vertical-text column
WIDEN_FACTOR = 1.5


def text_color(bg: RGB) -> RGB:
    luminance = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return (0, 0, 0) if luminance >= 128 else (255, 255, 255)


def widen_box(box: Box, image_size: tuple[int, int]) -> Box:
    """Japanese vertical text leaves tall, narrow boxes; give horizontal Korean more room."""
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    if width <= 0 or height / width <= NARROW_ASPECT:
        return box
    extra = int(width * (WIDEN_FACTOR - 1) / 2)
    return (max(0, x1 - extra), y1, min(image_size[0], x2 + extra), y2)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if font.getlength(candidate) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            if font.getlength(word) <= max_width:
                line = word
                continue
            for ch in word:  # a single word wider than the box: break between characters
                if line and font.getlength(line + ch) > max_width:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
        if line:
            lines.append(line)
    return lines


@lru_cache(maxsize=256)
def _font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, size)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return int((ascent + descent) * LINE_SPACING)


def _fits(lines: list[str], font: ImageFont.FreeTypeFont, width: int, height: int) -> bool:
    return all(font.getlength(line) <= width for line in lines) and _line_height(font) * len(lines) <= height


def fit_text(text: str, font_path: Path, width: int, height: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest font size whose wrapped text fits; falls back to MIN_FONT_SIZE even if it overflows."""
    best: tuple[ImageFont.FreeTypeFont, list[str]] | None = None
    lo, hi = MIN_FONT_SIZE, MAX_FONT_SIZE
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _font(str(font_path), mid)
        lines = wrap_text(text, font, width)
        if _fits(lines, font, width, height):
            best = (font, lines)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        font = _font(str(font_path), MIN_FONT_SIZE)
        best = (font, wrap_text(text, font, width))
    return best


def render_page(
    image: Image.Image,
    blocks: Sequence[TextBlock],
    translations: Mapping[int, str],
    font_path: Path = DEFAULT_FONT,
) -> Image.Image:
    out = image.convert("RGB")  # always a new image; the input is never modified
    draw = ImageDraw.Draw(out)
    for block in blocks:
        ko = translations.get(block.id)
        if not ko:
            continue  # failed bubble: keep the original Japanese visible
        x1, y1, x2, y2 = widen_box(block.box, out.size)
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=block.bg_color)
        pad = int(min(x2 - x1, y2 - y1) * PADDING_RATIO)
        width, height = x2 - x1 - 2 * pad, y2 - y1 - 2 * pad
        if width <= 0 or height <= 0:
            continue
        font, lines = fit_text(ko, font_path, width, height)
        line_height = _line_height(font)
        top = y1 + pad + (height - line_height * len(lines)) // 2
        color = text_color(block.bg_color)
        for i, line in enumerate(lines):
            left = x1 + pad + (width - font.getlength(line)) / 2
            draw.text((left, top + i * line_height), line, font=font, fill=color)
    return out
