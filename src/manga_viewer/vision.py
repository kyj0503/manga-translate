from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .background import border_median_color
from .order import sort_reading_order
from .types import PageAnalysis, TextBlock


def page_from_mokuro(result: dict, image: np.ndarray) -> PageAnalysis:
    blocks: list[TextBlock] = []
    for raw in result.get("blocks", []):
        text = "".join(raw.get("lines", [])).strip()
        if not text:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in raw["box"])
        box = (x1, y1, x2, y2)
        blocks.append(
            TextBlock(
                id=len(blocks),
                box=box,
                vertical=bool(raw.get("vertical", False)),
                ja=text,
                bg_color=border_median_color(image, box),
            )
        )
    return PageAnalysis(
        width=int(result["img_width"]),
        height=int(result["img_height"]),
        blocks=tuple(sort_reading_order(blocks)),
    )


class Vision:
    """Text detection + OCR on the GPU via mokuro (comic-text-detector + manga-ocr)."""

    def __init__(self, *, force_cpu: bool = False) -> None:
        from mokuro.manga_page_ocr import MangaPageOcr  # heavy: imports torch

        self._ocr = MangaPageOcr(force_cpu=force_cpu)

    def analyze(self, image_path: Path) -> PageAnalysis:
        result = self._ocr(str(image_path))
        with Image.open(image_path) as img:
            image = np.asarray(img.convert("RGB"))
        return page_from_mokuro(result, image)
