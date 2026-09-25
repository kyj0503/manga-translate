"""Stand-in for the engine's config module: records what the script sets and writes it as JSON."""
import json
from types import SimpleNamespace

from . import shared

pcfg = SimpleNamespace(module=SimpleNamespace(), global_fontformat=SimpleNamespace())


def save_config():
    module = {
        key: [vars(p) for p in value] if isinstance(value, list) else value
        for key, value in vars(pcfg.module).items()
    }
    data = {"module": module, "font_family": pcfg.global_fontformat.font_family}
    with open(shared.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return True
