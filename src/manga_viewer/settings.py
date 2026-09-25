"""Window choices remembered between runs."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Settings:
    llama_server: str = ""
    model: str = ""
    engine_dir: str = ""
    uv: str = ""
    last_input: str = ""
    last_output: str = ""


def default_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "manga-viewer" / "settings.json"


def load_settings(path: Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: str(v) for k, v in data.items() if k in known})


def save_settings(settings: Settings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
