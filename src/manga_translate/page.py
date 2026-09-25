"""What one page yields: text blocks with their box, reading direction, source text and translation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Block:
    xyxy: tuple[int, int, int, int]
    vertical: bool
    text: str
    translation: str = ""


@dataclass(frozen=True)
class PageResult:
    size: tuple[int, int]  # image width, height in pixels
    blocks: tuple[Block, ...]

    def with_translations(self, translations: Sequence[str]) -> PageResult:
        if len(translations) != len(self.blocks):
            raise ValueError(f"expected {len(self.blocks)} translations, got {len(translations)}")
        blocks = tuple(replace(b, translation=t) for b, t in zip(self.blocks, translations))
        return replace(self, blocks=blocks)

    def to_json(self) -> dict:
        return {
            "size": list(self.size),
            "blocks": [
                {"xyxy": list(b.xyxy), "vertical": b.vertical, "text": b.text, "translation": b.translation}
                for b in self.blocks
            ],
        }

    @classmethod
    def from_json(cls, data: Mapping) -> PageResult:
        width, height = data["size"]
        blocks = []
        for raw in data["blocks"]:
            xyxy = tuple(int(v) for v in raw["xyxy"])
            if len(xyxy) != 4:
                raise ValueError(f"a box needs 4 numbers, got {len(xyxy)}")
            blocks.append(Block(xyxy, bool(raw["vertical"]), str(raw["text"]), str(raw.get("translation", ""))))
        return cls((int(width), int(height)), tuple(blocks))
