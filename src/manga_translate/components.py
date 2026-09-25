"""llama.cpp and the translation model: pinned downloads installed into the program folder."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .download import check_cancel, download, extract_zip
from .paths import AppLayout


@dataclass(frozen=True)
class Asset:
    url: str
    name: str
    sha256: str
    size: int


LLAMA_TAG = "b11177"
_LLAMA = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/"
LLAMA_ASSETS = (
    Asset(
        _LLAMA + "llama-b11177-bin-win-cuda-12.4-x64.zip",
        "llama-b11177-bin-win-cuda-12.4-x64.zip",
        "14e756ba453e29db57578c1e5791245fe05c893671d3b334e08482ba1a0946bb",
        254724695,
    ),
    Asset(
        _LLAMA + "cudart-llama-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
        "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
        391443627,
    ),
)
LLAMA_MARKER = ".manga-translate-llama"

MODEL = Asset(
    "https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/"
    "bfc15c382204943c3a8fff0c750b94ae2364d7a3/gemma-4-E4B-it-Q4_K_M.gguf",
    "gemma-4-E4B-it-Q4_K_M.gguf",
    "85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87",
    4977171584,
)


def llama_ready(layout: AppLayout) -> bool:
    try:
        installed = (layout.llama_dir / LLAMA_MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return installed == LLAMA_TAG and layout.llama_server.is_file()


def install_llama(
    layout: AppLayout,
    *,
    log: Callable[[str], None] = print,
    cancel: threading.Event | None = None,
    fetch: Callable[..., None] = download,
) -> None:
    for asset in LLAMA_ASSETS:
        fetch(asset.url, layout.downloads_dir / asset.name, asset.sha256, log=log, cancel=cancel)
    for asset in LLAMA_ASSETS:
        log(f"압축 푸는 중: {asset.name}")
        extract_zip(layout.downloads_dir / asset.name, layout.llama_dir, cancel=cancel)
    check_cancel(cancel)
    (layout.llama_dir / LLAMA_MARKER).write_text(LLAMA_TAG, encoding="utf-8")
    for asset in LLAMA_ASSETS:
        (layout.downloads_dir / asset.name).unlink(missing_ok=True)


def model_path(layout: AppLayout) -> Path:
    return layout.models_dir / MODEL.name


def model_ready(layout: AppLayout) -> bool:
    path = model_path(layout)
    return path.is_file() and path.stat().st_size == MODEL.size


def install_model(
    layout: AppLayout,
    *,
    log: Callable[[str], None] = print,
    cancel: threading.Event | None = None,
    fetch: Callable[..., None] = download,
) -> None:
    fetch(MODEL.url, model_path(layout), MODEL.sha256, log=log, cancel=cancel)
