"""Choices remembered between runs."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

PAGE_DIRECTIONS = ("rtl", "ltr")  # rtl: the next page is to the left (Japanese order)


@dataclass
class Settings:
    model: str = ""  # a GGUF the user picked; empty means the installed default model
    last_input: str = ""
    last_output: str = ""
    last_library: str = ""
    page_direction: str = "rtl"
    positions: dict[str, int] = field(default_factory=dict)  # book folder -> last page index


def load_settings(path: Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    settings = Settings()
    for name in ("model", "last_input", "last_output", "last_library"):
        value = data.get(name)
        if isinstance(value, str):
            setattr(settings, name, value)
    if data.get("page_direction") in PAGE_DIRECTIONS:
        settings.page_direction = data["page_direction"]
    positions = data.get("positions")
    if isinstance(positions, dict):
        settings.positions = {
            key: value
            for key, value in positions.items()
            if isinstance(key, str) and type(value) is int and value >= 0
        }
    return settings


def save_settings(settings: Settings, path: Path) -> None:
    """Write via a temp file and rename, so a reader never sees a partial or torn write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
