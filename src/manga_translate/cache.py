"""Translated pages saved in the program folder, keyed by image path and valid while the image and model match."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .page import PageResult

CACHE_VERSION = 1


class TranslationCache:
    def __init__(self, cache_dir: Path, model: str) -> None:
        self.cache_dir = cache_dir
        self.model = model

    def _entry(self, source: Path) -> Path:
        key = os.path.normcase(str(source.resolve()))
        return self.cache_dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"

    def get(self, source: Path) -> PageResult | None:
        try:
            stat = source.stat()
            data = json.loads(self._entry(source).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (
            not isinstance(data, dict)
            or data.get("version") != CACHE_VERSION
            or data.get("model") != self.model
            or data.get("source_size") != stat.st_size
            or data.get("source_mtime_ns") != stat.st_mtime_ns
        ):
            return None
        try:
            return PageResult.from_json(data)
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, source: Path, result: PageResult) -> None:
        stat = source.stat()
        data = {
            "version": CACHE_VERSION,
            "source": str(source),
            "source_size": stat.st_size,
            "source_mtime_ns": stat.st_mtime_ns,
            "model": self.model,
            **result.to_json(),
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = self._entry(source)
        temp = entry.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        attempts = 5
        for attempt in range(attempts):
            try:
                os.replace(temp, entry)
                return
            except PermissionError:
                # a poll thread may have the entry open for reading (Windows) right now; retry briefly.
                if attempt == attempts - 1:
                    raise
                time.sleep(0.05)
