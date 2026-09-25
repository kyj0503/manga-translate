"""Install and locate the BallonsTranslator engine (GPL-3.0).

The engine does text detection, OCR, inpainting and typesetting in its own venv; we only
install it, write its config and run it headless. We never import its modules here.
"""
from __future__ import annotations

import locale
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .download import InstallError, check_cancel, download, extract_zip

ENGINE_COMMIT = "3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8"
ENGINE_ARCHIVE_URL = f"https://github.com/dmMaze/BallonsTranslator/archive/{ENGINE_COMMIT}.zip"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
EXTRA_PACKAGES = (
    "transformers==4.57.6",
    "jaconv",
    "fugashi",
    "unidic-lite",
    "openai>=2.8.1",
    "httpx[socks,brotli]",
    "tiktoken>=0.7.0",
)
SETUP_MARKER = ".manga-translate-setup"


class EngineError(InstallError):
    """Engine install or run problem; the message is shown to the user."""


@dataclass(frozen=True)
class ModelFile:
    url: str
    path: str  # relative to the engine root
    sha256: str | None = None


_MIT = "https://huggingface.co/dreMaz/mit_models/resolve/main/"
_OCR = "https://huggingface.co/kha-white/manga-ocr-base/resolve/main/"

# URLs and checksums come from each module's download_file_list in the pinned engine commit.
MODEL_FILES: tuple[ModelFile, ...] = (
    ModelFile(
        _MIT + "comictextdetector.pt",
        "data/models/comictextdetector.pt",
        "1f90fa60aeeb1eb82e2ac1167a66bf139a8a61b8780acd351ead55268540cccb",
    ),
    ModelFile(
        _MIT + "comictextdetector.pt.onnx",
        "data/models/comictextdetector.pt.onnx",
        "1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f",
    ),
    ModelFile(
        "https://huggingface.co/dreMaz/AnimeMangaInpainting/resolve/main/lama_large_512px.ckpt",
        "data/models/lama_large_512px.ckpt",
        "11d30fbb3000fb2eceae318b75d9ced9229d99ae990a7f8b3ac35c8d31f2c935",
    ),
    ModelFile(
        _OCR + "pytorch_model.bin",
        "data/models/manga-ocr-base/pytorch_model.bin",
        "c63e0bb5b3ff798c5991de18a8e0956c7ee6d1563aca6729029815eda6f5c2eb",
    ),
    *(
        ModelFile(_OCR + name, f"data/models/manga-ocr-base/{name}")
        for name in (
            "config.json",
            "preprocessor_config.json",
            "README.md",
            "special_tokens_map.json",
            "tokenizer_config.json",
            "vocab.txt",
        )
    ),
)


@dataclass(frozen=True)
class EngineLayout:
    root: Path

    @property
    def python(self) -> Path:
        return self.root / ".venv" / "Scripts" / "python.exe"

    @property
    def config_path(self) -> Path:
        return self.root / "config" / "config.json"

    @property
    def marker(self) -> Path:
        return self.root / SETUP_MARKER

    def is_ready(self) -> bool:
        try:
            installed = self.marker.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        return installed == ENGINE_COMMIT and self.python.is_file()


def _decode_output(data: bytes) -> str:
    """Decode output trying UTF-8 first, then fall back to system locale encoding."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def run_checked(argv: Sequence[str]) -> None:
    """Run a helper command without a console window; on failure show the end of its output."""
    result = subprocess.run(list(argv), capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        output = _decode_output(result.stdout + result.stderr).strip()
        tail = "\n".join(output.splitlines()[-10:])
        raise EngineError(f"명령이 실패했습니다 (코드 {result.returncode}): {' '.join(map(str, argv))}\n{tail}")


def venv_command(layout: EngineLayout, uv: Path) -> list[str]:
    return [str(uv), "venv", "--python", "3.12", str(layout.root / ".venv")]


def package_commands(layout: EngineLayout, uv: Path) -> list[list[str]]:
    pip = [str(uv), "pip", "install", "--python", str(layout.python)]
    return [
        [*pip, "-r", str(layout.root / "requirements.txt")],
        [*pip, "-e", str(layout.root), "--no-deps"],
        [*pip, "torch", "torchvision", "--index-url", TORCH_INDEX],
        [*pip, *EXTRA_PACKAGES],
    ]


def setup_engine(
    layout: EngineLayout,
    *,
    uv: Path,
    downloads_dir: Path,
    run: Callable[[Sequence[str]], None] = run_checked,
    fetch: Callable[..., None] = download,
    log: Callable[[str], None] = print,
    cancel: threading.Event | None = None,
) -> None:
    """Idempotent: source, venv and packages only when not installed; model files always verified.

    Stopping leaves the marker unwritten, so the next call picks up where this one ended.
    """
    check_cancel(cancel)
    if not layout.is_ready():
        log("엔진 코드를 받는 중...")
        archive = downloads_dir / f"BallonsTranslator-{ENGINE_COMMIT[:12]}.zip"
        fetch(ENGINE_ARCHIVE_URL, archive, None, log=log, cancel=cancel)
        extract_zip(archive, layout.root, strip_top=True, cancel=cancel)
        archive.unlink(missing_ok=True)
        log("엔진 Python 패키지를 설치하는 중입니다. 몇 분 걸립니다...")
        if not layout.python.is_file():
            check_cancel(cancel)
            run(venv_command(layout, uv))
        for argv in package_commands(layout, uv):
            check_cancel(cancel)
            run(argv)
    log("엔진 모델 파일을 확인하는 중...")
    for model in MODEL_FILES:
        check_cancel(cancel)
        fetch(model.url, layout.root / model.path, model.sha256, log=log, cancel=cancel)
    check_cancel(cancel)
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
