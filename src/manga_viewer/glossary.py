from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class GlossaryEntry:
    ja: str
    ko: str
    note: str = ""


def load_glossary(path: Path) -> list[GlossaryEntry]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return [
        GlossaryEntry(ja=str(e.get("ja", "")), ko=str(e.get("ko", "")), note=str(e.get("note", "")))
        for e in data.get("entry", [])
    ]


def relevant_entries(entries: Iterable[GlossaryEntry], texts: Iterable[str]) -> list[GlossaryEntry]:
    """Entries whose Japanese term appears on the page; keeps the prompt short."""
    joined = "\n".join(texts)
    return [e for e in entries if e.ja and e.ja in joined]
