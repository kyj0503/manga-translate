import threading
import zipfile

import pytest

import manga_translate.components as components
from manga_translate.components import (
    LLAMA_ASSETS,
    LLAMA_MARKER,
    LLAMA_TAG,
    MODEL,
    Asset,
    install_llama,
    install_model,
    llama_ready,
    model_path,
    model_ready,
)
from manga_translate.download import Cancelled
from manga_translate.paths import AppLayout


def test_pinned_values():
    assert LLAMA_TAG == "b11177"
    assert [a.name for a in LLAMA_ASSETS] == [
        "llama-b11177-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
    ]
    assert LLAMA_ASSETS[0].sha256 == "14e756ba453e29db57578c1e5791245fe05c893671d3b334e08482ba1a0946bb"
    assert LLAMA_ASSETS[1].sha256 == "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"
    assert MODEL.name == "gemma-4-E4B-it-Q4_K_M.gguf"
    assert MODEL.size == 4977171584
    assert MODEL.sha256 == "85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87"
    assert "bfc15c382204943c3a8fff0c750b94ae2364d7a3" in MODEL.url


def zip_fetch(calls, contents):
    """Fake download: records the call and writes a small zip for each llama asset."""

    def fetch(url, dest, sha256=None, *, log=print, cancel=None):
        calls.append((url, dest, sha256, cancel))
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as zf:
            for name, data in contents[dest.name].items():
                zf.writestr(name, data)

    return fetch


def test_install_llama(tmp_path):
    layout = AppLayout(tmp_path)
    calls = []
    contents = {
        LLAMA_ASSETS[0].name: {"llama-server.exe": "exe", "ggml.dll": "dll"},
        LLAMA_ASSETS[1].name: {"cudart64_12.dll": "cuda"},
    }
    cancel = threading.Event()
    assert not llama_ready(layout)

    install_llama(layout, log=lambda m: None, cancel=cancel, fetch=zip_fetch(calls, contents))

    assert [c[0] for c in calls] == [a.url for a in LLAMA_ASSETS]
    assert [c[2] for c in calls] == [a.sha256 for a in LLAMA_ASSETS]
    assert all(c[3] is cancel for c in calls)
    assert (layout.llama_dir / "llama-server.exe").read_text() == "exe"
    assert (layout.llama_dir / "cudart64_12.dll").read_text() == "cuda"
    assert (layout.llama_dir / LLAMA_MARKER).read_text(encoding="utf-8") == LLAMA_TAG
    assert not any((layout.downloads_dir / a.name).exists() for a in LLAMA_ASSETS)
    assert llama_ready(layout)


def test_install_llama_cancelled_leaves_no_marker(tmp_path):
    layout = AppLayout(tmp_path)
    cancel = threading.Event()
    contents = {a.name: {"x.txt": "x"} for a in LLAMA_ASSETS}
    inner = zip_fetch([], contents)

    def fetch(url, dest, sha256=None, *, log=print, cancel=None):
        inner(url, dest, sha256, log=log, cancel=cancel)
        cancel.set()  # stopped right after the downloads finished

    with pytest.raises(Cancelled):
        install_llama(layout, log=lambda m: None, cancel=cancel, fetch=fetch)
    assert not (layout.llama_dir / LLAMA_MARKER).exists()
    assert not llama_ready(layout)


def test_model_ready_and_install(tmp_path, monkeypatch):
    layout = AppLayout(tmp_path)
    small = Asset("https://example.invalid/m.gguf", "m.gguf", "ab" * 32, 3)
    monkeypatch.setattr(components, "MODEL", small)
    assert model_path(layout) == layout.models_dir / "m.gguf"
    assert not model_ready(layout)
    layout.models_dir.mkdir()
    model_path(layout).write_bytes(b"12")
    assert not model_ready(layout)  # wrong size = incomplete
    model_path(layout).write_bytes(b"123")
    assert model_ready(layout)

    calls = []
    cancel = threading.Event()
    install_model(layout, log=lambda m: None, cancel=cancel,
                  fetch=lambda url, dest, sha256=None, *, log=print, cancel=None: calls.append((url, dest, sha256, cancel)))
    assert calls == [(small.url, model_path(layout), small.sha256, cancel)]
