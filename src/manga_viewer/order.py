from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from .types import TextBlock

# A block joins the current row when at least this fraction of its height
# overlaps the row's vertical extent.
ROW_OVERLAP_RATIO = 0.5


def sort_reading_order(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    """Manga order: rows top-to-bottom, right-to-left within a row. Ids are reassigned 0..n-1."""
    rows: list[list[TextBlock]] = []
    row_ranges: list[tuple[int, int]] = []
    for blk in sorted(blocks, key=lambda b: b.box[1]):
        y1, y2 = blk.box[1], blk.box[3]
        height = max(y2 - y1, 1)
        if rows:
            ry1, ry2 = row_ranges[-1]
            overlap = min(y2, ry2) - max(y1, ry1)
            if overlap >= ROW_OVERLAP_RATIO * height:
                rows[-1].append(blk)
                row_ranges[-1] = (min(ry1, y1), max(ry2, y2))
                continue
        rows.append([blk])
        row_ranges.append((y1, y2))

    ordered = [
        blk
        for row in rows
        for blk in sorted(row, key=lambda b: -(b.box[0] + b.box[2]))
    ]
    return [replace(blk, id=i) for i, blk in enumerate(ordered)]
