"""Install and locate the BallonsTranslator engine (GPL-3.0).

The engine does text detection, OCR, inpainting and typesetting in its own venv; we only
install it, write its config and run it headless. We never import its modules here.
"""
from __future__ import annotations

import hashlib
import locale
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

ENGINE_REPO = "https://github.com/dmMaze/BallonsTranslator.git"
ENGINE_COMMIT = "3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8"
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
SETUP_MARKER = ".manga-viewer-setup"


class EngineError(RuntimeError):
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


def default_engine_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "manga-viewer" / "BallonsTranslator"


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


def repo_commands(layout: EngineLayout, git: Path) -> list[list[str]]:
    root = str(layout.root)
    return [
        [str(git), "-C", root, "fetch", "--depth", "1", ENGINE_REPO, ENGINE_COMMIT],
        [str(git), "-C", root, "checkout", "--force", ENGINE_COMMIT],
    ]


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, dest: Path, sha256: str | None = None, log: Callable[[str], None] = print) -> None:
    if dest.is_file() and (sha256 is None or _sha256(dest) == sha256):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    log(f"다운로드: {dest.name}")
    try:
        with urllib.request.urlopen(url) as response, part.open("wb") as out:
            shutil.copyfileobj(response, out, 1024 * 1024)
    except (urllib.error.URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise EngineError(f"다운로드에 실패했습니다: {url} ({e})") from e
    if sha256 is not None and _sha256(part) != sha256:
        part.unlink()
        raise EngineError(f"다운로드한 파일 검증에 실패했습니다: {dest.name}")
    part.replace(dest)


def setup_engine(
    layout: EngineLayout,
    *,
    uv: Path,
    git: Path,
    run: Callable[[Sequence[str]], None] = run_checked,
    download: Callable[..., None] = download_file,
    log: Callable[[str], None] = print,
) -> None:
    """Idempotent: clone/checkout, venv and packages only when not installed; models always verified."""
    root = str(layout.root)
    if not (layout.root / ".git").is_dir():
        layout.root.mkdir(parents=True, exist_ok=True)
        run([str(git), "init", root])
    if not layout.is_ready():
        log("엔진 코드와 Python 패키지를 설치하는 중입니다. 몇 분 걸립니다...")
        for argv in repo_commands(layout, git):
            run(argv)
        if not layout.python.is_file():
            run(venv_command(layout, uv))
        for argv in package_commands(layout, uv):
            run(argv)
    log("모델 파일을 확인하는 중...")
    for model in MODEL_FILES:
        download(model.url, layout.root / model.path, model.sha256, log)
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
