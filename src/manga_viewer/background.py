from __future__ import annotations

import numpy as np

from .types import RGB, Box


def border_median_color(image: np.ndarray, box: Box) -> RGB:
    """Median color of the box's edge pixels; used to paint over the original text."""
    h, w = image.shape[:2]
    x1 = min(max(box[0], 0), w - 1)
    y1 = min(max(box[1], 0), h - 1)
    x2 = min(max(box[2], x1 + 1), w)
    y2 = min(max(box[3], y1 + 1), h)
    region = image[y1:y2, x1:x2, :3]
    border = np.concatenate([region[0], region[-1], region[:, 0], region[:, -1]])
    median = np.median(border, axis=0)
    return tuple(int(round(v)) for v in median)  # type: ignore[return-value]
