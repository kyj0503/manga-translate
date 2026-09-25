"""Where the app keeps its files: everything lives in the program folder."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

APP_HOME_ENV = "MANGA_TRANSLATE_HOME"


def app_dir(environ: Mapping[str, str] = os.environ) -> Path:
    """The program folder: the parent of the app's venv, unless MANGA_TRANSLATE_HOME points elsewhere."""
    override = environ.get(APP_HOME_ENV)
    if override:
        return Path(override)
    return Path(sys.prefix).resolve().parent


@dataclass(frozen=True)
class AppLayout:
    root: Path

    @property
    def settings_path(self) -> Path:
        return self.root / "settings.json"

    @property
    def engine_dir(self) -> Path:
        return self.root / "engine" / "BallonsTranslator"

    @property
    def llama_dir(self) -> Path:
        return self.root / "runtime" / "llama"

    @property
    def llama_server(self) -> Path:
        return self.llama_dir / "llama-server.exe"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def downloads_dir(self) -> Path:
        return self.root / "downloads"

    @property
    def bundled_uv(self) -> Path:
        return self.root / "tools" / "uv.exe"

    @property
    def uv_cache_dir(self) -> Path:
        return self.root / "downloads" / "uv-cache"

    @property
    def python_dir(self) -> Path:
        return self.root / "runtime" / "python"

    @property
    def work_dir(self) -> Path:
        return self.root / "work"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"


def uv_environment(layout: AppLayout) -> dict[str, str]:
    """Env overrides that keep uv's cache and managed Python inside the program folder."""
    return {
        "UV_CACHE_DIR": str(layout.uv_cache_dir),
        "UV_PYTHON_INSTALL_DIR": str(layout.python_dir),
        "UV_PYTHON_PREFERENCE": "only-managed",
    }


def find_uv(
    layout: AppLayout,
    environ: Mapping[str, str] = os.environ,
    which: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    """uv that launched us (`uv run` sets UV), then the copy the build put in tools\\, then PATH."""
    for candidate in (environ.get("UV"), str(layout.bundled_uv), which("uv")):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None
