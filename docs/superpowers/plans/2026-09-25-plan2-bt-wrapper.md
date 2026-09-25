# 계획 2: BallonsTranslator 래퍼 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `manga-viewer setup`으로 BallonsTranslator 엔진과 모델을 설치하고, `manga-viewer translate A B` 또는 간단한 창(`manga-viewer gui`)으로 로컬 llama-server(Gemma 4, 텍스트 전용)를 띄워 엔진을 headless로 실행해 번역·식자된 이미지를 B에 저장한다. 창에는 입출력 폴더, 선택된 모델, 입출력 언어, 진행도가 보인다.

**Architecture:** 엔진(BallonsTranslator)은 자체 venv를 가진 별도 설치물이다. 우리 CLI는 (1) `engine.py`로 설치·검증하고, (2) `engine_run.py`로 엔진 venv에서 설정 스크립트를 실행해 `config.json`을 쓰고, 작업 폴더에 페이지를 복사해 headless 실행을 스트리밍하고 결과를 모은다. llama-server와 엔진 프로세스는 같은 Job Object에 묶는다. 계획 1의 자체 파이프라인 코드는 마지막 태스크에서 제거한다.

**Tech Stack:** Python 3.12, uv, git, BallonsTranslator(GPL-3.0, 커밋 3e401b2), llama.cpp llama-server, httpx, natsort, pytest, psutil

**Spec:** `docs/superpowers/specs/2026-09-25-bt-wrapper-design.md`

## Global Constraints

- 네이티브 Windows(PowerShell)에서 빌드·실행·테스트한다. WSL·Docker 금지. `uv`는 PATH에 없을 수 있다: `C:\Users\serial\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe` (아래에서 `$uv`).
- 엔진 저장소 `https://github.com/dmMaze/BallonsTranslator.git`, 고정 커밋 `3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8`.
- 엔진 기본 위치 `%LOCALAPPDATA%\manga-viewer\BallonsTranslator`, 설치 표시 파일 `<engine>\.manga-viewer-setup`(내용: 커밋 해시).
- 번역은 텍스트 전용: LLM 프로필 `support_vision=False`, `llm_translate_vision=False`. mmproj를 쓰지 않는다.
- llama-server는 `127.0.0.1`에만 바인딩하고 `--reasoning-budget 0`으로 추론을 끈다.
- 사용자에게 보이는 CLI 문구는 한국어. 입력 오류 종료 코드 2, 빠진 페이지가 있으면 1, 모두 성공 0.
- 엔진 모듈(`ballontranslator`)은 우리 프로세스에서 절대 import하지 않는다. 엔진 venv의 Python으로 실행되는 스크립트에서만 쓴다.
- 샘플(`manga-data/`), 모델·엔진(`.dev/`), 결과(`bench-out/`)는 커밋하지 않는다.
- 커밋 작성자 이메일은 repo-local `heroria0503@gmail.com`. 커밋 메시지 끝에 빈 줄 + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 파일 구조

| 파일 | 변경 | 책임 |
|---|---|---|
| `src/manga_viewer/engine.py` | 신규 | 엔진 위치·설치 명령·모델 다운로드·설치 여부 |
| `src/manga_viewer/engine_run.py` | 신규 | 설정 쓰기, 작업 폴더, headless 스트리밍 실행, 결과 수집 |
| `src/manga_viewer/scripts/bt_write_config.py` | 신규 | 엔진 venv에서만 실행되는 설정 스크립트 |
| `src/manga_viewer/llm/llama.py` | 수정 | mmproj 제거, `--reasoning-budget 0` |
| `src/manga_viewer/pipeline.py` | 신규 | 번역 작업 하나(검증, 실행, 진행도, 결과) — CLI·GUI 공용 |
| `src/manga_viewer/settings.py` | 신규 | GUI 설정 저장 |
| `src/manga_viewer/gui.py` | 신규 | tkinter 창 |
| `src/manga_viewer/cli.py` | 교체 | `setup`, `translate`, `gui` |
| `tests/test_engine.py`, `tests/test_engine_run.py` | 신규 | |
| `tests/helpers/fake_bt/ballontranslator/...` | 신규 | 설정 스크립트 테스트용 가짜 엔진 패키지 |
| `tests/test_pipeline.py`, `tests/test_settings.py`, `tests/test_gui.py` | 신규 | |
| `tests/test_llama.py`, `tests/test_cli.py`, `tests/test_imports.py` | 수정·교체 | |
| 자체 파이프라인 모듈과 테스트 | 삭제 | Task 6 |
| `pyproject.toml`, `LICENSE`, `README.md` | 수정·신규 | Task 6 |

---

### Task 1: 엔진 설치 (`engine.py`)

**Files:**
- Create: `src/manga_viewer/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Produces:
  - 상수 `ENGINE_REPO`, `ENGINE_COMMIT`, `TORCH_INDEX`, `EXTRA_PACKAGES: tuple[str, ...]`, `SETUP_MARKER = ".manga-viewer-setup"`
  - `class EngineError(RuntimeError)` — 메시지는 한국어, CLI가 출력하고 종료 코드 2
  - `@dataclass(frozen=True) ModelFile(url: str, path: str, sha256: str | None = None)`, `MODEL_FILES: tuple[ModelFile, ...]` (10개)
  - `@dataclass(frozen=True) EngineLayout(root: Path)` with properties `python`, `config_path`, `marker` and `is_ready() -> bool`
  - `default_engine_dir() -> Path`
  - `run_checked(argv: Sequence[str]) -> None` — 실패 시 `EngineError`
  - `repo_commands(layout, git: Path) -> list[list[str]]`, `venv_command(layout, uv: Path) -> list[str]`, `package_commands(layout, uv: Path) -> list[list[str]]`
  - `download_file(url: str, dest: Path, sha256: str | None = None, log=print) -> None`
  - `setup_engine(layout, *, uv: Path, git: Path, run=run_checked, download=download_file, log=print) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_engine.py`:

```python
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from manga_viewer.engine import (
    ENGINE_COMMIT,
    ENGINE_REPO,
    MODEL_FILES,
    TORCH_INDEX,
    EngineError,
    EngineLayout,
    download_file,
    package_commands,
    repo_commands,
    setup_engine,
    venv_command,
)

UV = Path("C:/tools/uv.exe")
GIT = Path("C:/tools/git.exe")


def make_ready(root: Path) -> EngineLayout:
    layout = EngineLayout(root)
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    (root / ".git").mkdir()
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    return layout


def test_layout_paths(tmp_path):
    layout = EngineLayout(tmp_path)
    assert layout.python == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert layout.config_path == tmp_path / "config" / "config.json"
    assert layout.marker == tmp_path / ".manga-viewer-setup"


def test_is_ready_needs_matching_marker_and_python(tmp_path):
    layout = EngineLayout(tmp_path)
    assert not layout.is_ready()
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    assert not layout.is_ready()
    layout.marker.write_text("some-other-commit", encoding="utf-8")
    assert not layout.is_ready()
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    assert layout.is_ready()


def test_commands(tmp_path):
    layout = EngineLayout(tmp_path)
    repo = repo_commands(layout, GIT)
    assert repo[0] == [str(GIT), "-C", str(tmp_path), "fetch", "--depth", "1", "origin", ENGINE_COMMIT]
    assert repo[1] == [str(GIT), "-C", str(tmp_path), "checkout", "--force", ENGINE_COMMIT]
    assert venv_command(layout, UV) == [str(UV), "venv", "--python", "3.12", str(tmp_path / ".venv")]
    packages = [" ".join(c) for c in package_commands(layout, UV)]
    assert any("-r " + str(tmp_path / "requirements.txt") in c for c in packages)
    assert any(f"-e {tmp_path} --no-deps" in c for c in packages)
    assert any("torch torchvision --index-url " + TORCH_INDEX in c for c in packages)
    assert any("transformers==4.57.6" in c for c in packages)
    assert all(f"--python {layout.python}" in c for c in packages)


def test_model_files():
    paths = {f.path for f in MODEL_FILES}
    assert len(MODEL_FILES) == 10
    assert {
        "data/models/comictextdetector.pt",
        "data/models/comictextdetector.pt.onnx",
        "data/models/lama_large_512px.ckpt",
        "data/models/manga-ocr-base/pytorch_model.bin",
    } <= paths
    big = [f for f in MODEL_FILES if not f.path.endswith((".json", ".md", ".txt"))]
    assert all(f.sha256 for f in big)


def test_fresh_setup_runs_everything_and_writes_marker(tmp_path):
    root = tmp_path / "engine"
    layout = EngineLayout(root)
    ran, downloaded = [], []

    setup_engine(
        layout,
        uv=UV,
        git=GIT,
        run=lambda argv: ran.append(list(argv)),
        download=lambda url, dest, sha256, log: downloaded.append(dest),
        log=lambda msg: None,
    )

    assert ran[0] == [str(GIT), "init", str(root)]
    assert ran[1] == [str(GIT), "-C", str(root), "remote", "add", "origin", ENGINE_REPO]
    assert ran[2:4] == repo_commands(layout, GIT)
    assert ran[4] == venv_command(layout, UV)
    assert ran[5:] == package_commands(layout, UV)
    assert downloaded == [root / f.path for f in MODEL_FILES]
    assert layout.marker.read_text(encoding="utf-8") == ENGINE_COMMIT


def test_ready_engine_only_verifies_models(tmp_path):
    layout = make_ready(tmp_path / "engine")
    ran, downloaded = [], []
    setup_engine(
        layout,
        uv=UV,
        git=GIT,
        run=lambda argv: ran.append(argv),
        download=lambda url, dest, sha256, log: downloaded.append(dest),
        log=lambda msg: None,
    )
    assert ran == []
    assert len(downloaded) == len(MODEL_FILES)


def test_existing_venv_is_not_recreated(tmp_path):
    root = tmp_path / "engine"
    layout = EngineLayout(root)
    (root / ".git").mkdir(parents=True)
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    ran = []
    setup_engine(layout, uv=UV, git=GIT, run=ran.append, download=lambda *a: None, log=lambda m: None)
    assert venv_command(layout, UV) not in ran
    assert ran[:2] == repo_commands(layout, GIT)


@pytest.fixture
def http_server():
    files, hits = {}, []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = files.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", files, hits
    server.shutdown()


def test_download_verifies_checksum(tmp_path, http_server):
    base, files, _ = http_server
    files["/m.bin"] = b"model-bytes"
    dest = tmp_path / "models" / "m.bin"
    download_file(base + "/m.bin", dest, hashlib.sha256(b"model-bytes").hexdigest(), log=lambda m: None)
    assert dest.read_bytes() == b"model-bytes"
    assert not dest.with_name("m.bin.part").exists()


def test_download_rejects_bad_checksum(tmp_path, http_server):
    base, files, _ = http_server
    files["/m.bin"] = b"tampered"
    dest = tmp_path / "m.bin"
    with pytest.raises(EngineError, match="검증"):
        download_file(base + "/m.bin", dest, hashlib.sha256(b"expected").hexdigest(), log=lambda m: None)
    assert not dest.exists()
    assert not dest.with_name("m.bin.part").exists()


def test_download_skips_valid_existing_file(tmp_path, http_server):
    base, files, hits = http_server
    dest = tmp_path / "m.bin"
    dest.write_bytes(b"model-bytes")
    download_file(base + "/m.bin", dest, hashlib.sha256(b"model-bytes").hexdigest(), log=lambda m: None)
    assert hits == []


def test_download_http_error_is_engine_error(tmp_path, http_server):
    base, _, _ = http_server
    with pytest.raises(EngineError, match="다운로드"):
        download_file(base + "/missing", tmp_path / "x.bin", None, log=lambda m: None)
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_engine.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_viewer.engine'`

- [ ] **Step 3: 구현**

`src/manga_viewer/engine.py`:

```python
"""Install and locate the BallonsTranslator engine (GPL-3.0).

The engine does text detection, OCR, inpainting and typesetting in its own venv; we only
install it, write its config and run it headless. We never import its modules here.
"""
from __future__ import annotations

import hashlib
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


def run_checked(argv: Sequence[str]) -> None:
    result = subprocess.run(list(argv))
    if result.returncode != 0:
        raise EngineError(f"명령이 실패했습니다 (코드 {result.returncode}): {' '.join(argv)}")


def repo_commands(layout: EngineLayout, git: Path) -> list[list[str]]:
    root = str(layout.root)
    return [
        [str(git), "-C", root, "fetch", "--depth", "1", "origin", ENGINE_COMMIT],
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
        run([str(git), "-C", root, "remote", "add", "origin", ENGINE_REPO])
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
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_engine.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/engine.py tests/test_engine.py
git commit -m "feat: install and verify the BallonsTranslator engine"
```

---

### Task 2: 엔진 실행 (`engine_run.py`, 설정 스크립트)

**Files:**
- Create: `src/manga_viewer/engine_run.py`, `src/manga_viewer/scripts/bt_write_config.py`
- Create: `tests/helpers/fake_bt/ballontranslator/__init__.py`, `tests/helpers/fake_bt/ballontranslator/utils/__init__.py`, `tests/helpers/fake_bt/ballontranslator/utils/shared.py`, `tests/helpers/fake_bt/ballontranslator/utils/config.py`, `tests/helpers/fake_bt/ballontranslator/utils/llm_profiles.py`
- Test: `tests/test_engine_run.py`

**Interfaces:**
- Consumes: Task 1의 `EngineLayout`, `run_checked`, `KillOnCloseJob`(`winjob.py`)
- Produces:
  - `CONFIG_SCRIPT: Path`
  - `write_engine_config(layout, base_url: str, model_id: str, run=run_checked) -> None` — `[layout.python, CONFIG_SCRIPT, layout.root, base_url, model_id]` 실행
  - `headless_argv(layout, exec_dir: Path) -> list[str]` — `[python, "-m", "ballontranslator", "--headless", "--exec_dirs", exec_dir]`
  - `prepare_work_dir(images: Sequence[Path], exec_dir: Path) -> None`
  - `collect_results(exec_dir: Path, output_dir: Path) -> list[Path]` — `exec_dir/result`의 파일을 복사하고 복사된 경로 목록 반환(없으면 빈 목록)
  - `missing_pages(images: Sequence[Path], results: Sequence[Path]) -> list[Path]` — 결과에 같은 stem이 없는 입력
  - `run_streaming(argv, cwd: Path, *, job=None, on_line=print, stdin_text="exit\n") -> int` — `PYTHONIOENCODING=utf-8`, 표준 입력에 `stdin_text`를 쓰고 닫은 뒤 출력 줄을 `on_line`으로 전달, 종료 코드 반환. 예외 시 프로세스를 죽이고 다시 던짐.

- [ ] **Step 1: 가짜 엔진 패키지 작성**

`tests/helpers/fake_bt/ballontranslator/__init__.py`, `tests/helpers/fake_bt/ballontranslator/utils/__init__.py`: 빈 파일.

`tests/helpers/fake_bt/ballontranslator/utils/shared.py`:

```python
CONFIG_PATH = ""
```

`tests/helpers/fake_bt/ballontranslator/utils/llm_profiles.py`:

```python
THINKING_DISABLED = "Disabled"


class LLMProfile:
    def __init__(self, **fields):
        self.__dict__.update(fields)
```

`tests/helpers/fake_bt/ballontranslator/utils/config.py`:

```python
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
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_engine_run.py`:

```python
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from manga_viewer.engine import EngineLayout
from manga_viewer.engine_run import (
    CONFIG_SCRIPT,
    collect_results,
    headless_argv,
    missing_pages,
    prepare_work_dir,
    run_streaming,
    write_engine_config,
)

FAKE_BT = Path(__file__).parent / "helpers" / "fake_bt"
PYTHON = getattr(sys, "_base_executable", sys.executable)


def test_write_engine_config_runs_script_with_engine_python(tmp_path):
    layout = EngineLayout(tmp_path)
    ran = []
    write_engine_config(layout, "http://127.0.0.1:5555", "gemma-4-e4b", run=ran.append)
    assert ran == [[str(layout.python), str(CONFIG_SCRIPT), str(tmp_path), "http://127.0.0.1:5555", "gemma-4-e4b"]]


def test_config_script_writes_text_only_local_llm_config(tmp_path):
    root = tmp_path / "engine"
    shutil.copytree(FAKE_BT, root)
    result = subprocess.run(
        [sys.executable, str(CONFIG_SCRIPT), str(root), "http://127.0.0.1:5555", "gemma-4-e4b"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((root / "config" / "config.json").read_text(encoding="utf-8"))
    module = data["module"]
    assert module["textdetector"] == "ctd"
    assert module["ocr"] == "manga_ocr"
    assert module["inpainter"] == "lama_large_512px"
    assert module["translator"] == "LLMTranslator"
    assert module["translate_source"] == "日本語"
    assert module["translate_target"] == "한국어"
    assert module["llm_translate_context"] == "history"
    assert module["llm_translate_vision"] is False
    [profile] = module["llm_profiles"]
    assert module["translator_llm_id"] == profile["id"]
    assert profile["base_url"] == "http://127.0.0.1:5555/v1"
    assert profile["model"] == "gemma-4-e4b"
    assert profile["support_vision"] is False
    assert profile["thinking_level"] == "Disabled"
    assert data["font_family"] == "Malgun Gothic"


def test_headless_argv(tmp_path):
    layout = EngineLayout(tmp_path)
    assert headless_argv(layout, tmp_path / "pages") == [
        str(layout.python), "-m", "ballontranslator", "--headless", "--exec_dirs", str(tmp_path / "pages"),
    ]


def test_prepare_collect_and_missing(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    images = []
    for name in ("1.jpg", "2.png"):
        (src / name).write_bytes(name.encode())
        images.append(src / name)
    exec_dir = tmp_path / "work" / "pages"

    prepare_work_dir(images, exec_dir)
    assert (exec_dir / "1.jpg").read_bytes() == b"1.jpg"

    assert collect_results(exec_dir, tmp_path / "out") == []
    (exec_dir / "result").mkdir()
    (exec_dir / "result" / "1.png").write_bytes(b"typeset")
    results = collect_results(exec_dir, tmp_path / "out")
    assert results == [tmp_path / "out" / "1.png"]
    assert (tmp_path / "out" / "1.png").read_bytes() == b"typeset"
    assert missing_pages(images, results) == [src / "2.png"]


def test_run_streaming_passes_output_stdin_and_cwd(tmp_path):
    lines = []
    code = run_streaming(
        [PYTHON, "-c", "import os; print('한글 출력'); print(os.getcwd()); print('got', input())"],
        tmp_path,
        on_line=lines.append,
    )
    assert code == 0
    assert lines == ["한글 출력", str(tmp_path), "got exit"]


def test_run_streaming_returns_exit_code(tmp_path):
    assert run_streaming([PYTHON, "-c", "import sys; sys.exit(9)"], tmp_path, on_line=lambda l: None) == 9


def test_run_streaming_kills_process_when_consumer_fails(tmp_path):
    def boom(line):
        raise RuntimeError("stop")

    start = time.monotonic()
    with pytest.raises(RuntimeError, match="stop"):
        run_streaming([PYTHON, "-c", "import time; print('x', flush=True); time.sleep(60)"], tmp_path, on_line=boom)
    assert time.monotonic() - start < 20
```

- [ ] **Step 3: 실패 확인**

Run: `& $uv run pytest tests/test_engine_run.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_viewer.engine_run'`

- [ ] **Step 4: 설정 스크립트 작성**

`src/manga_viewer/scripts/bt_write_config.py`:

```python
"""Runs inside the BallonsTranslator venv (never imported by manga_viewer).

Writes <engine>/config/config.json for a headless, text-only run against our local llama-server.
Usage: python bt_write_config.py <engine_root> <base_url> <model_id>
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])
base_url = sys.argv[2].rstrip("/")
model_id = sys.argv[3]
sys.path.insert(0, str(root))

from ballontranslator.utils import shared  # noqa: E402
from ballontranslator.utils.config import pcfg, save_config  # noqa: E402
from ballontranslator.utils.llm_profiles import THINKING_DISABLED, LLMProfile  # noqa: E402

profile = LLMProfile(
    id="manga-viewer-llama",
    name="manga-viewer llama.cpp",
    base_url=f"{base_url}/v1",
    api_key="sk-no-key-required",
    require_api_key=False,
    model=model_id,
    model_options=[model_id],
    support_text=True,
    support_vision=False,
    support_image=False,
    thinking_level=THINKING_DISABLED,
    max_tokens=2048,
    temperature=0.1,
    top_p=1.0,
    json_schema_response_format=False,
)

config_path = root / "config" / "config.json"
config_path.parent.mkdir(parents=True, exist_ok=True)
shared.CONFIG_PATH = str(config_path)

m = pcfg.module
m.textdetector = "ctd"
m.ocr = "manga_ocr"
m.inpainter = "lama_large_512px"
m.translator = "LLMTranslator"
m.enable_detect = True
m.enable_ocr = True
m.enable_translate = True
m.enable_inpaint = True
m.llm_profiles = [profile]
m.translator_llm_id = profile.id
m.translate_source = "日本語"
m.translate_target = "한국어"
m.llm_translate_context = "history"
m.llm_translate_vision = False
m.llm_translate_summary_memory = False
pcfg.global_fontformat.font_family = "Malgun Gothic"

if not save_config():
    sys.exit("config save failed")
```

- [ ] **Step 5: `engine_run.py` 작성**

```python
"""Drive one BallonsTranslator headless run: write its config, stage pages, run it, collect results."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .engine import EngineLayout, run_checked
from .winjob import KillOnCloseJob

CONFIG_SCRIPT = Path(__file__).parent / "scripts" / "bt_write_config.py"


def write_engine_config(
    layout: EngineLayout,
    base_url: str,
    model_id: str,
    run: Callable[[Sequence[str]], None] = run_checked,
) -> None:
    run([str(layout.python), str(CONFIG_SCRIPT), str(layout.root), base_url, model_id])


def headless_argv(layout: EngineLayout, exec_dir: Path) -> list[str]:
    return [str(layout.python), "-m", "ballontranslator", "--headless", "--exec_dirs", str(exec_dir)]


def prepare_work_dir(images: Sequence[Path], exec_dir: Path) -> None:
    """The engine writes project files next to the images, so it works on copies."""
    exec_dir.mkdir(parents=True, exist_ok=True)
    for image in images:
        shutil.copy2(image, exec_dir / image.name)


def collect_results(exec_dir: Path, output_dir: Path) -> list[Path]:
    result_dir = exec_dir / "result"
    if not result_dir.is_dir():
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(result_dir.iterdir()):
        if path.is_file():
            target = output_dir / path.name
            shutil.copy2(path, target)
            copied.append(target)
    return copied


def missing_pages(images: Sequence[Path], results: Sequence[Path]) -> list[Path]:
    produced = {p.stem for p in results}
    return [p for p in images if p.stem not in produced]


def run_streaming(
    argv: Sequence[str],
    cwd: Path,
    *,
    job: KillOnCloseJob | None = None,
    on_line: Callable[[str], None] = print,
    stdin_text: str = "exit\n",
) -> int:
    """Run a console program, feed stdin up front, forward its output line by line."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        if job is not None:
            job.assign(proc.pid)
        assert proc.stdin is not None and proc.stdout is not None
        try:
            # Headless mode asks for more folders when done; a queued "exit" makes it quit.
            proc.stdin.write(stdin_text.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass  # the program already exited; its output and exit code still tell the story
        for raw in proc.stdout:
            on_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        return proc.wait()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
```

- [ ] **Step 6: 통과 확인**

Run: `& $uv run pytest tests/test_engine_run.py -v`
Expected: 7 passed

- [ ] **Step 7: 실제 엔진으로 설정 스크립트 확인 (커밋 안 함)**

평가 때 설치된 엔진이 `.dev\BallonsTranslator`에 있다. 설정 파일을 백업하고 실행한 뒤 되돌린다.

```powershell
$engine = "C:\Users\serial\source\manga-viewer\.dev\BallonsTranslator"
Copy-Item "$engine\config\config.json" "$engine\config\config.json.bak" -ErrorAction SilentlyContinue
& "$engine\.venv\Scripts\python.exe" src\manga_viewer\scripts\bt_write_config.py $engine http://127.0.0.1:5555 gemma-4-e4b
Select-String -Path "$engine\config\config.json" -Pattern '"translator"|"llm_translate_vision"|"translate_target"|"base_url"'
```

Expected: 종료 코드 0, 출력에 `LLMTranslator`, `false`, `한국어`, `http://127.0.0.1:5555/v1`가 보인다. 실패하면(예: `LLMProfile`이 모르는 필드) 오류를 보고서에 적고, 스크립트를 엔진의 실제 `ballontranslator/utils/llm_profiles.py` 필드에 맞게 최소 수정한 뒤 가짜 패키지 테스트와 이 단계를 다시 통과시킨다.

- [ ] **Step 8: Commit**

```bash
git add src/manga_viewer/engine_run.py src/manga_viewer/scripts/bt_write_config.py tests/helpers/fake_bt tests/test_engine_run.py
git commit -m "feat: write engine config, stage pages and run BallonsTranslator headless"
```

---

### Task 3: 번역 작업 흐름 (`pipeline.py`)과 llama-server 옵션

**Files:**
- Create: `src/manga_viewer/pipeline.py`
- Modify: `src/manga_viewer/llm/llama.py`, `tests/test_llama.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 `EngineLayout`; Task 2 `write_engine_config`, `headless_argv`, `prepare_work_dir`, `run_streaming`, `collect_results`, `missing_pages`; 기존 `start_llama_server`, `LlamaConfig`, `ServerStartError`, `KillOnCloseJob`, `list_images`
- Produces:
  - `LlamaConfig(exe, model, ctx_size=8192, n_gpu_layers=999)` (mmproj 없음), `build_llama_args`가 `--reasoning-budget 0` 포함
  - `SOURCE_LANGUAGE = "일본어"`, `TARGET_LANGUAGE = "한국어"`
  - `class PipelineError(Exception)` — 사용자에게 보여줄 한국어 메시지
  - `@dataclass(frozen=True) TranslationRequest(input_dir: Path, output_dir: Path, llama_server: Path, model: Path, engine: EngineLayout, ctx_size: int = 8192, keep_work: bool = False)`
  - `@dataclass(frozen=True) TranslationResult(total: int, saved: list[Path], missing: list[Path], engine_exit_code: int, work_dir: Path | None)` with property `ok -> bool` (`not missing`). `work_dir`는 남긴 경우만 경로, 지웠으면 `None`.
  - `validate(req) -> list[Path]` — 입력 이미지 목록, 문제가 있으면 `PipelineError`
  - `run_translation(req, *, on_log=print, on_progress=lambda done, total: None) -> TranslationResult` — 진행은 (0, total)로 시작해 `result\` 파일 수가 바뀔 때마다, 마지막에 저장된 장수로 보고한다. 같은 값은 두 번 보고하지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_llama.py` 전체 교체:

```python
from pathlib import Path

from manga_viewer.llm.llama import LlamaConfig, build_llama_args


def test_build_llama_args():
    cfg = LlamaConfig(exe=Path("C:/x/llama-server.exe"), model=Path("C:/m/model.gguf"))
    args = build_llama_args(cfg, port=5555)
    assert args[0] == str(Path("C:/x/llama-server.exe"))
    joined = " ".join(args)
    assert f"-m {Path('C:/m/model.gguf')}" in joined
    assert "--host 127.0.0.1" in joined
    assert "--port 5555" in joined
    assert "-c 8192" in joined
    assert "-ngl 999" in joined
    assert "--parallel 1" in joined
    assert "--reasoning-budget 0" in joined
    assert "--mmproj" not in args
```

`tests/test_pipeline.py`:

```python
from pathlib import Path

import pytest

import manga_viewer.pipeline as pipeline
from manga_viewer.engine import ENGINE_COMMIT, EngineLayout
from manga_viewer.llm.process import ServerStartError
from manga_viewer.pipeline import PipelineError, TranslationRequest, run_translation, validate


def ready_engine(tmp_path) -> EngineLayout:
    root = tmp_path / "engine"
    (root / ".venv" / "Scripts").mkdir(parents=True, exist_ok=True)
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    (root / ".manga-viewer-setup").write_text(ENGINE_COMMIT, encoding="utf-8")
    return EngineLayout(root)


def request(tmp_path, *names, **overrides) -> TranslationRequest:
    src = tmp_path / "in"
    src.mkdir(exist_ok=True)
    for name in names:
        (src / name).write_bytes(b"img")
    exe = tmp_path / "llama-server.exe"
    model = tmp_path / "gemma-4-e4b.gguf"
    exe.write_bytes(b"")
    model.write_bytes(b"")
    fields = dict(
        input_dir=src,
        output_dir=tmp_path / "out",
        llama_server=exe,
        model=model,
        engine=ready_engine(tmp_path),
    )
    fields.update(overrides)
    return TranslationRequest(**fields)


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    calls = []
    state = {"produce": None, "code": 0, "start_error": None}
    work = tmp_path / "work"

    class FakeServer:
        def stop(self):
            calls.append("server.stop")

    class FakeJob:
        def close(self):
            calls.append("job.close")

    def fake_start(cfg, log_path, job=None, timeout=300.0):
        if state["start_error"] is not None:
            raise state["start_error"]
        calls.append(("start", cfg.model.name))
        return FakeServer(), "http://127.0.0.1:5555"

    def fake_config(layout, base_url, model_id, run=None):
        calls.append(("config", base_url, model_id))

    def fake_run(argv, cwd, *, job=None, on_line=print, stdin_text="exit\n"):
        exec_dir = Path(argv[-1])
        calls.append(("run", argv[1:4]))
        result = exec_dir / "result"
        result.mkdir()
        if state["produce"] is None:
            names = sorted(p.name for p in exec_dir.iterdir() if p.is_file())
        else:
            names = state["produce"]
        for name in names:
            (result / f"{Path(name).stem}.png").write_bytes(b"typeset")
            on_line(f"saved {name}")
        return state["code"]

    def fake_mkdtemp(prefix=""):
        work.mkdir()
        return str(work)

    monkeypatch.setattr(pipeline, "start_llama_server", fake_start)
    monkeypatch.setattr(pipeline, "KillOnCloseJob", FakeJob)
    monkeypatch.setattr(pipeline, "write_engine_config", fake_config)
    monkeypatch.setattr(pipeline, "run_streaming", fake_run)
    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", fake_mkdtemp)
    return calls, state, work


def test_validate_rejects_bad_requests(tmp_path):
    with pytest.raises(PipelineError, match="폴더가 없습니다"):
        validate(request(tmp_path, "1.jpg", input_dir=tmp_path / "nope"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(PipelineError, match="이미지가 없습니다"):
        validate(request(tmp_path, "1.jpg", input_dir=empty))
    with pytest.raises(PipelineError, match="모델 파일이 없습니다"):
        validate(request(tmp_path, "1.jpg", model=tmp_path / "nope.gguf"))
    with pytest.raises(PipelineError, match="manga-viewer setup"):
        validate(request(tmp_path, "1.jpg", engine=EngineLayout(tmp_path / "none")))
    with pytest.raises(PipelineError, match="출력 폴더는 입력 폴더와 달라야 합니다"):
        validate(request(tmp_path, "1.jpg", output_dir=tmp_path / "in"))


def test_successful_run(tmp_path, fakes):
    calls, _, work = fakes
    logs, progress = [], []
    req = request(tmp_path, "1.jpg", "2.png")

    result = run_translation(req, on_log=logs.append, on_progress=lambda d, t: progress.append((d, t)))

    assert result.ok and result.total == 2 and result.engine_exit_code == 0
    assert [p.name for p in result.saved] == ["1.png", "2.png"]
    assert (tmp_path / "out" / "1.png").read_bytes() == b"typeset"
    assert progress == [(0, 2), (1, 2), (2, 2)]
    assert "saved 1.jpg" in logs
    assert ("config", "http://127.0.0.1:5555", "gemma-4-e4b") in calls
    assert ("run", ["-m", "ballontranslator", "--headless"]) in calls
    assert calls[-2:] == ["server.stop", "job.close"]
    assert result.work_dir is None and not work.exists()


def test_missing_pages_keep_work(tmp_path, fakes):
    _, state, work = fakes
    state["produce"] = ["1.jpg"]
    state["code"] = 9
    progress = []

    result = run_translation(request(tmp_path, "1.jpg", "2.png"), on_log=lambda l: None,
                             on_progress=lambda d, t: progress.append((d, t)))

    assert not result.ok
    assert [p.name for p in result.missing] == ["2.png"]
    assert result.engine_exit_code == 9
    assert result.work_dir == work and work.exists()
    assert progress[-1] == (1, 2)


def test_keep_work_flag(tmp_path, fakes):
    _, _, work = fakes
    result = run_translation(request(tmp_path, "1.jpg", keep_work=True), on_log=lambda l: None)
    assert result.ok and result.work_dir == work and work.exists()


def test_server_start_failure(tmp_path, fakes):
    calls, state, _ = fakes
    state["start_error"] = ServerStartError("no gpu")
    with pytest.raises(PipelineError, match="LLM 서버를 시작하지 못했습니다"):
        run_translation(request(tmp_path, "1.jpg"), on_log=lambda l: None)
    assert calls == ["job.close"]
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_llama.py tests/test_pipeline.py -v`
Expected: FAIL (`--reasoning-budget` 없음, `ModuleNotFoundError: No module named 'manga_viewer.pipeline'`)

- [ ] **Step 3: `llama.py` 수정**

`LlamaConfig`에서 `mmproj` 필드를 지우고 `build_llama_args`를 아래로 바꾼다.

```python
@dataclass(frozen=True)
class LlamaConfig:
    exe: Path
    model: Path
    ctx_size: int = 8192
    n_gpu_layers: int = 999


def build_llama_args(cfg: LlamaConfig, port: int) -> list[str]:
    return [
        str(cfg.exe),
        "-m", str(cfg.model),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", str(cfg.ctx_size),
        "-ngl", str(cfg.n_gpu_layers),
        "--parallel", "1",
        "--reasoning-budget", "0",  # translation needs no thinking; it only costs time
    ]
```

- [ ] **Step 4: `pipeline.py` 작성**

```python
"""One translation job shared by the CLI and the GUI: validate, run llama-server + engine, collect results."""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .engine import EngineLayout
from .engine_run import (
    collect_results,
    headless_argv,
    missing_pages,
    prepare_work_dir,
    run_streaming,
    write_engine_config,
)
from .llm.llama import LlamaConfig, start_llama_server
from .llm.process import ServerStartError
from .source import list_images
from .winjob import KillOnCloseJob

SOURCE_LANGUAGE = "일본어"
TARGET_LANGUAGE = "한국어"


class PipelineError(Exception):
    """A problem the user can fix; the message is shown as-is."""


@dataclass(frozen=True)
class TranslationRequest:
    input_dir: Path
    output_dir: Path
    llama_server: Path
    model: Path
    engine: EngineLayout
    ctx_size: int = 8192
    keep_work: bool = False


@dataclass(frozen=True)
class TranslationResult:
    total: int
    saved: list[Path]
    missing: list[Path]
    engine_exit_code: int
    work_dir: Path | None  # kept for inspection, or None when cleaned up

    @property
    def ok(self) -> bool:
        return not self.missing


def validate(req: TranslationRequest) -> list[Path]:
    if not req.input_dir.is_dir():
        raise PipelineError(f"폴더가 없습니다: {req.input_dir}")
    images = list_images(req.input_dir)
    if not images:
        raise PipelineError(f"이미지가 없습니다: {req.input_dir}")
    for label, path in (("llama-server", req.llama_server), ("모델", req.model)):
        if not path.is_file():
            raise PipelineError(f"{label} 파일이 없습니다: {path}")
    if not req.engine.is_ready():
        raise PipelineError("번역 엔진이 설치되어 있지 않습니다. 먼저 'manga-viewer setup'을 실행하세요.")
    if req.output_dir.resolve() == req.input_dir.resolve():
        raise PipelineError("출력 폴더는 입력 폴더와 달라야 합니다.")
    return images


@contextmanager
def _llama_server(req: TranslationRequest, log_path: Path, on_log: Callable[[str], None]) -> Iterator[tuple[KillOnCloseJob, str]]:
    """llama-server in a kill-on-close job; the engine joins the same job. Always torn down."""
    job = KillOnCloseJob()
    server = None
    try:
        on_log("LLM 서버를 시작하는 중...")
        try:
            server, base_url = start_llama_server(
                LlamaConfig(exe=req.llama_server, model=req.model, ctx_size=req.ctx_size), log_path, job=job
            )
        except (ServerStartError, OSError) as e:
            raise PipelineError(f"LLM 서버를 시작하지 못했습니다: {e}") from e
        yield job, base_url
    finally:
        if server is not None:
            server.stop()
        job.close()


def run_translation(
    req: TranslationRequest,
    *,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
) -> TranslationResult:
    images = validate(req)
    total = len(images)
    work = Path(tempfile.mkdtemp(prefix="manga-viewer-"))
    exec_dir = work / "pages"
    result_dir = exec_dir / "result"
    prepare_work_dir(images, exec_dir)

    last = -1

    def report(done: int) -> None:
        nonlocal last
        done = min(done, total)
        if done != last:
            last = done
            on_progress(done, total)

    def forward(line: str) -> None:
        on_log(line)
        # Progress = pages the engine has already written to result\.
        if result_dir.is_dir():
            report(sum(1 for p in result_dir.iterdir() if p.is_file()))

    report(0)
    with _llama_server(req, work / "llama-server.log", on_log) as (job, base_url):
        on_log("번역 설정을 쓰는 중...")
        write_engine_config(req.engine, base_url, req.model.stem)
        on_log(f"번역을 시작합니다 ({total}장)...")
        code = run_streaming(headless_argv(req.engine, exec_dir), req.engine.root, job=job, on_line=forward)

    saved = collect_results(exec_dir, req.output_dir)
    missing = missing_pages(images, saved)
    report(total - len(missing))
    keep = bool(missing) or req.keep_work
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return TranslationResult(total, saved, missing, code, work if keep else None)
```

- [ ] **Step 5: 통과 확인**

Run: `& $uv run pytest tests/test_llama.py tests/test_pipeline.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/manga_viewer/llm/llama.py src/manga_viewer/pipeline.py tests/test_llama.py tests/test_pipeline.py
git commit -m "feat: add the shared translation pipeline around BallonsTranslator"
```

---

### Task 4: CLI (`setup`, `translate`, `gui`)

**Files:**
- Replace: `src/manga_viewer/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1 `EngineError`, `EngineLayout`, `default_engine_dir`, `setup_engine`; Task 3 `PipelineError`, `TranslationRequest`, `TranslationResult`, `run_translation`; Task 5에서 만들 `manga_viewer.gui.main`(`gui` 하위 명령에서 호출 시점에 import)
- Produces: `cli.main(argv=None) -> int`, `cli.CliError`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cli.py` 전체 교체:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

import manga_viewer.cli as cli
from manga_viewer.cli import main
from manga_viewer.pipeline import PipelineError, TranslationResult


def translate_args(tmp_path, *extra):
    return ["translate", str(tmp_path / "in"), str(tmp_path / "out"),
            "--llama-server", "llama-server.exe", "--model", "m.gguf", *extra]


def test_translate_requires_model_args(tmp_path):
    with pytest.raises(SystemExit):
        main(["translate", str(tmp_path), str(tmp_path / "out")])


def test_translate_builds_request_and_prints_summary(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake_run(req, *, on_log, on_progress):
        seen["req"] = req
        on_progress(1, 2)
        return TranslationResult(2, [tmp_path / "out" / "1.png", tmp_path / "out" / "2.png"], [], 0, None)

    monkeypatch.setattr(cli, "run_translation", fake_run)
    code = main(translate_args(tmp_path, "--engine-dir", str(tmp_path / "engine"), "--ctx-size", "4096", "--keep-work"))

    out = capsys.readouterr().out
    assert code == 0
    req = seen["req"]
    assert req.input_dir == tmp_path / "in" and req.output_dir == tmp_path / "out"
    assert req.model == Path("m.gguf") and req.llama_server == Path("llama-server.exe")
    assert req.engine.root == tmp_path / "engine"
    assert req.ctx_size == 4096 and req.keep_work is True
    assert "진행: 1/2" in out
    assert "2/2장 저장" in out


def test_translate_reports_missing_pages(tmp_path, monkeypatch, capsys):
    result = TranslationResult(2, [tmp_path / "out" / "1.png"], [tmp_path / "in" / "2.png"], 9, tmp_path / "work")
    monkeypatch.setattr(cli, "run_translation", lambda req, **kw: result)
    assert main(translate_args(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "결과 없음: 2.png" in out
    assert "엔진 종료 코드: 9" in out
    assert f"작업 폴더: {tmp_path / 'work'}" in out


def test_pipeline_error_is_exit_code_2(tmp_path, monkeypatch, capsys):
    def fail(req, **kw):
        raise PipelineError("이미지가 없습니다: x")

    monkeypatch.setattr(cli, "run_translation", fail)
    assert main(translate_args(tmp_path)) == 2
    assert "이미지가 없습니다" in capsys.readouterr().out


def test_default_engine_dir_is_used(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "default_engine_dir", lambda: tmp_path / "default-engine")
    monkeypatch.setattr(cli, "run_translation", lambda req, **kw: seen.setdefault("req", req) and TranslationResult(0, [], [], 0, None))
    main(translate_args(tmp_path))
    assert seen["req"].engine.root == tmp_path / "default-engine"


def test_setup_without_uv(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert main(["setup", "--engine-dir", str(tmp_path / "engine")]) == 2
    assert "uv를 찾을 수 없습니다" in capsys.readouterr().out


def test_setup_without_git(tmp_path, monkeypatch, capsys):
    uv = tmp_path / "uv.exe"
    uv.write_bytes(b"")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert main(["setup", "--engine-dir", str(tmp_path / "engine"), "--uv", str(uv)]) == 2
    assert "git을 찾을 수 없습니다" in capsys.readouterr().out


def test_setup_calls_engine_setup(tmp_path, monkeypatch):
    uv = tmp_path / "uv.exe"
    uv.write_bytes(b"")
    seen = {}
    monkeypatch.setattr(cli.shutil, "which", lambda name: "C:/git/git.exe" if name == "git" else None)
    monkeypatch.setattr(cli, "setup_engine", lambda layout, uv, git: seen.update(root=layout.root, uv=uv, git=git))
    assert main(["setup", "--engine-dir", str(tmp_path / "engine"), "--uv", str(uv)]) == 0
    assert seen == {"root": tmp_path / "engine", "uv": uv, "git": Path("C:/git/git.exe")}


def test_gui_subcommand_launches_window(monkeypatch):
    import manga_viewer.gui

    monkeypatch.setattr(manga_viewer.gui, "main", lambda: 0)
    assert main(["gui"]) == 0


def test_output_survives_non_cp949_characters(tmp_path):
    folder = tmp_path / "気"  # not encodable in cp949
    folder.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    code = (
        "import sys\n"
        "from manga_viewer.cli import main\n"
        f"sys.exit(main(['translate', {str(folder)!r}, 'out', '--llama-server', 'x', '--model', 'm']))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert result.returncode == 2, result.stderr.decode("utf-8", "replace")
    assert "気" in result.stdout.decode("utf-8")
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_cli.py -v`
Expected: FAIL (`invalid choice: 'translate'`, `cli` 속성 없음, `manga_viewer.gui` 없음)

`test_gui_subcommand_launches_window`는 Task 5 전까지 `ModuleNotFoundError`로 실패한다. 이 태스크에서는 `pytest.importorskip`을 쓰지 말고, 아래처럼 `gui.py` 자리 표시 파일을 만들어 통과시킨다. Task 5가 이 파일을 실제 창으로 교체한다.

`src/manga_viewer/gui.py` (임시):

```python
"""Replaced by the real window in the next task."""


def main() -> int:
    raise SystemExit("GUI is not implemented yet")
```

- [ ] **Step 3: `cli.py` 전체 교체**

```python
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .engine import EngineError, EngineLayout, default_engine_dir, setup_engine
from .pipeline import PipelineError, TranslationRequest, run_translation


class CliError(Exception):
    """A problem the user can fix; printed as-is with exit code 2."""


def _force_utf8_stdout() -> None:
    # The Windows console code page (e.g. cp949) cannot encode every kanji in file names.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(prog="manga-viewer", description="로컬 LLM으로 일본 만화를 한국어로 번역합니다")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="번역 엔진(BallonsTranslator)과 모델을 설치")
    setup.add_argument("--engine-dir", type=Path, help="엔진 설치 폴더 (기본: %%LOCALAPPDATA%%\\manga-viewer\\BallonsTranslator)")
    setup.add_argument("--uv", type=Path, help="uv.exe 경로 (기본: PATH에서 찾음)")

    translate = sub.add_parser("translate", help="폴더의 만화를 번역해 결과 이미지를 저장")
    translate.add_argument("input", type=Path, help="원본 만화 이미지 폴더")
    translate.add_argument("output", type=Path, help="번역 이미지를 저장할 폴더")
    translate.add_argument("--llama-server", type=Path, required=True, help="llama-server.exe 경로")
    translate.add_argument("--model", type=Path, required=True, help="번역용 GGUF 모델 경로")
    translate.add_argument("--engine-dir", type=Path, help="엔진 설치 폴더")
    translate.add_argument("--ctx-size", type=int, default=8192, help="LLM 컨텍스트 길이")
    translate.add_argument("--keep-work", action="store_true", help="작업 폴더를 지우지 않고 남김")

    sub.add_parser("gui", help="간단한 창으로 실행")

    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            return _run_setup(args)
        if args.command == "gui":
            from .gui import main as gui_main  # tkinter only when asked for

            return gui_main()
        return _run_translate(args)
    except (CliError, EngineError, PipelineError) as e:
        print(e)
        return 2


def _layout(args: argparse.Namespace) -> EngineLayout:
    return EngineLayout(args.engine_dir or default_engine_dir())


def _run_setup(args: argparse.Namespace) -> int:
    layout = _layout(args)
    found_uv = shutil.which("uv")
    uv = args.uv or (Path(found_uv) if found_uv else None)
    if uv is None or not uv.is_file():
        raise CliError("uv를 찾을 수 없습니다. --uv로 uv.exe 경로를 지정하세요.")
    git = shutil.which("git")
    if git is None:
        raise CliError("git을 찾을 수 없습니다. Git for Windows를 설치한 뒤 다시 실행하세요.")
    print(f"엔진 설치 위치: {layout.root}")
    setup_engine(layout, uv=uv, git=Path(git))
    print("설치가 끝났습니다.")
    return 0


def _run_translate(args: argparse.Namespace) -> int:
    req = TranslationRequest(
        input_dir=args.input,
        output_dir=args.output,
        llama_server=args.llama_server,
        model=args.model,
        engine=_layout(args),
        ctx_size=args.ctx_size,
        keep_work=args.keep_work,
    )
    result = run_translation(req, on_log=print, on_progress=lambda done, total: print(f"진행: {done}/{total}"))
    print(f"완료: {result.total - len(result.missing)}/{result.total}장 저장 → {args.output}")
    if result.engine_exit_code != 0:
        print(f"엔진 종료 코드: {result.engine_exit_code}")
    for page in result.missing:
        print(f"결과 없음: {page.name}")
    if result.work_dir is not None:
        print(f"작업 폴더: {result.work_dir}")
    return 0 if result.ok else 1
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_cli.py -v`
Expected: 모두 PASS

Run: `& $uv run pytest -v -m "not gpu"`
Expected: 전체 통과 (계획 1의 옛 모듈 테스트도 아직 남아 있다)

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/cli.py src/manga_viewer/gui.py tests/test_cli.py
git commit -m "feat: add setup, translate and gui commands"
```

---

### Task 5: 간단한 GUI (`gui.py`, `settings.py`)

**Files:**
- Create: `src/manga_viewer/settings.py`
- Replace: `src/manga_viewer/gui.py`
- Test: `tests/test_settings.py`, `tests/test_gui.py`

**Interfaces:**
- Consumes: Task 1 `EngineError`, `EngineLayout`, `default_engine_dir`; Task 3 `SOURCE_LANGUAGE`, `TARGET_LANGUAGE`, `PipelineError`, `TranslationRequest`, `TranslationResult`, `run_translation`
- Produces:
  - `@dataclass Settings(llama_server: str = "", model: str = "", engine_dir: str = "", last_input: str = "", last_output: str = "")`
  - `default_settings_path() -> Path` (`%LOCALAPPDATA%\manga-viewer\settings.json`), `load_settings(path) -> Settings`(없거나 깨졌으면 기본값, 모르는 키 무시), `save_settings(settings, path) -> None`
  - `gui.default_output_dir(input_dir: Path) -> Path` (`<입력>_번역`), `gui.format_progress(done, total) -> str`, `gui.model_label(path: str) -> str`, `gui.build_request(settings, input_dir: str, output_dir: str) -> TranslationRequest`, `gui.summary_text(result, output_dir: Path) -> str`, `class gui.App`, `gui.main() -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_settings.py`:

```python
import json

from manga_viewer.settings import Settings, load_settings, save_settings


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    settings = Settings(llama_server="C:/l.exe", model="C:/모델.gguf", last_input="D:/만화")
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert "모델" in path.read_text(encoding="utf-8")  # stored as readable UTF-8


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_settings(bad) == Settings()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"model": "m.gguf", "future_option": 1}), encoding="utf-8")
    assert load_settings(path) == Settings(model="m.gguf")
```

`tests/test_gui.py`:

```python
from pathlib import Path

import pytest

from manga_viewer.engine import EngineLayout
from manga_viewer.gui import build_request, default_output_dir, format_progress, model_label, summary_text
from manga_viewer.pipeline import PipelineError, TranslationResult
from manga_viewer.settings import Settings


def test_default_output_dir():
    assert default_output_dir(Path("D:/만화/1권")) == Path("D:/만화/1권_번역")


def test_format_progress():
    assert format_progress(0, 0) == "대기 중"
    assert format_progress(3, 6) == "3 / 6장"


def test_model_label():
    assert model_label("") == "(선택되지 않음)"
    assert model_label("C:/models/gemma-4-e4b-Q4_K_M.gguf") == "gemma-4-e4b-Q4_K_M"


def test_build_request_requires_every_choice():
    full = Settings(llama_server="C:/l.exe", model="C:/m.gguf")
    with pytest.raises(PipelineError, match="입력 폴더"):
        build_request(full, "", "D:/out")
    with pytest.raises(PipelineError, match="출력 폴더"):
        build_request(full, "D:/in", "")
    with pytest.raises(PipelineError, match="번역 모델"):
        build_request(Settings(llama_server="C:/l.exe"), "D:/in", "D:/out")
    with pytest.raises(PipelineError, match="llama-server"):
        build_request(Settings(model="C:/m.gguf"), "D:/in", "D:/out")


def test_build_request(tmp_path, monkeypatch):
    import manga_viewer.gui as gui

    monkeypatch.setattr(gui, "default_engine_dir", lambda: tmp_path / "default")
    req = build_request(Settings(llama_server="C:/l.exe", model="C:/m.gguf"), "D:/in", "D:/out")
    assert req.input_dir == Path("D:/in") and req.output_dir == Path("D:/out")
    assert req.model == Path("C:/m.gguf") and req.llama_server == Path("C:/l.exe")
    assert req.engine == EngineLayout(tmp_path / "default")
    custom = build_request(Settings(llama_server="C:/l.exe", model="C:/m.gguf", engine_dir="E:/engine"), "D:/in", "D:/out")
    assert custom.engine == EngineLayout(Path("E:/engine"))


def test_summary_text():
    ok = TranslationResult(2, [Path("o/1.png"), Path("o/2.png")], [], 0, None)
    assert summary_text(ok, Path("D:/out")) == "2 / 2장을 번역했습니다.\n저장 위치: D:\\out"
    partial = TranslationResult(2, [Path("o/1.png")], [Path("i/2.png")], 9, Path("C:/tmp/w"))
    text = summary_text(partial, Path("D:/out"))
    assert "1 / 2장을 번역했습니다." in text
    assert "결과가 없는 페이지: 2.png" in text
    assert "작업 폴더: C:\\tmp\\w" in text
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_settings.py tests/test_gui.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'manga_viewer.settings'`, `cannot import name 'build_request'`)

- [ ] **Step 3: `settings.py` 작성**

```python
"""GUI choices remembered between runs."""
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
```

- [ ] **Step 4: `gui.py` 교체**

```python
"""Small window: pick folders, see model and languages, run a translation and watch its progress."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .engine import EngineError, EngineLayout, default_engine_dir
from .pipeline import (
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    PipelineError,
    TranslationRequest,
    TranslationResult,
    run_translation,
)
from .settings import Settings, default_settings_path, load_settings, save_settings

TITLE = "manga-viewer 번역"
POLL_MS = 100


def default_output_dir(input_dir: Path) -> Path:
    return input_dir.with_name(f"{input_dir.name}_번역")


def format_progress(done: int, total: int) -> str:
    return f"{done} / {total}장" if total else "대기 중"


def model_label(path: str) -> str:
    return Path(path).stem if path else "(선택되지 않음)"


def build_request(settings: Settings, input_dir: str, output_dir: str) -> TranslationRequest:
    if not input_dir:
        raise PipelineError("입력 폴더를 선택하세요.")
    if not output_dir:
        raise PipelineError("출력 폴더를 선택하세요.")
    if not settings.model:
        raise PipelineError("번역 모델(GGUF 파일)을 선택하세요.")
    if not settings.llama_server:
        raise PipelineError("llama-server.exe를 선택하세요.")
    engine_root = Path(settings.engine_dir) if settings.engine_dir else default_engine_dir()
    return TranslationRequest(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        llama_server=Path(settings.llama_server),
        model=Path(settings.model),
        engine=EngineLayout(engine_root),
    )


def summary_text(result: TranslationResult, output_dir: Path) -> str:
    lines = [f"{result.total - len(result.missing)} / {result.total}장을 번역했습니다.", f"저장 위치: {output_dir}"]
    if result.missing:
        lines.append("결과가 없는 페이지: " + ", ".join(p.name for p in result.missing))
    if result.work_dir is not None:
        lines.append(f"작업 폴더: {result.work_dir}")
    return "\n".join(lines)


class App:
    def __init__(self, root: tk.Tk, settings_path: Path) -> None:
        self.root = root
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.events: queue.Queue = queue.Queue()
        self.running = False

        root.title(TITLE)
        root.minsize(600, 460)
        self.input_var = tk.StringVar(value=self.settings.last_input)
        self.output_var = tk.StringVar(value=self.settings.last_output)
        self.model_var = tk.StringVar(value=model_label(self.settings.model))
        self.llama_var = tk.StringVar(value=self.settings.llama_server or "(선택되지 않음)")
        self.progress_var = tk.StringVar(value=format_progress(0, 0))

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="입력 폴더").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_input).grid(row=0, column=2)

        ttk.Label(frame, text="출력 폴더").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_output).grid(row=1, column=2)

        ttk.Label(frame, text="번역 모델").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.model_var).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Button(frame, text="변경...", command=self._pick_model).grid(row=2, column=2)

        ttk.Label(frame, text="llama-server").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.llama_var).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Button(frame, text="변경...", command=self._pick_llama).grid(row=3, column=2)

        ttk.Label(frame, text="언어").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Label(frame, text=f"{SOURCE_LANGUAGE} → {TARGET_LANGUAGE}").grid(row=4, column=1, sticky="w", padx=6)

        self.bar = ttk.Progressbar(frame, mode="determinate", maximum=1)
        self.bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Label(frame, textvariable=self.progress_var).grid(row=5, column=2)

        self.start_button = ttk.Button(frame, text="번역 시작", command=self._start)
        self.start_button.grid(row=6, column=0, columnspan=3, pady=8)

        self.log = tk.Text(frame, height=12, state="disabled", wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(7, weight=1)

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(POLL_MS, self._drain)

    def _save(self) -> None:
        save_settings(self.settings, self.settings_path)

    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="입력 폴더 선택")
        if path:
            self.input_var.set(path)
            if not self.output_var.get().strip():
                self.output_var.set(str(default_output_dir(Path(path))))

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="출력 폴더 선택")
        if path:
            self.output_var.set(path)

    def _pick_model(self) -> None:
        path = filedialog.askopenfilename(title="번역 모델 선택", filetypes=[("GGUF 모델", "*.gguf")])
        if path:
            self.settings.model = path
            self.model_var.set(model_label(path))
            self._save()

    def _pick_llama(self) -> None:
        path = filedialog.askopenfilename(title="llama-server.exe 선택", filetypes=[("실행 파일", "*.exe")])
        if path:
            self.settings.llama_server = path
            self.llama_var.set(path)
            self._save()

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self) -> None:
        try:
            req = build_request(self.settings, self.input_var.get().strip(), self.output_var.get().strip())
        except PipelineError as e:
            messagebox.showwarning(TITLE, str(e))
            return
        self.settings.last_input = str(req.input_dir)
        self.settings.last_output = str(req.output_dir)
        self._save()
        self.running = True
        self.start_button.configure(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.bar.configure(maximum=1, value=0)
        threading.Thread(target=self._work, args=(req,), daemon=True).start()

    def _work(self, req: TranslationRequest) -> None:
        # Runs on a worker thread: only talk to Tk through the event queue.
        try:
            result = run_translation(
                req,
                on_log=lambda line: self.events.put(("log", line)),
                on_progress=lambda done, total: self.events.put(("progress", done, total)),
            )
            self.events.put(("done", result, req.output_dir))
        except (PipelineError, EngineError) as e:
            self.events.put(("error", str(e)))
        except Exception as e:  # keep the window usable and show what went wrong
            self.events.put(("error", f"예상하지 못한 오류: {e!r}"))

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "log":
                    self._append_log(event[1])
                elif event[0] == "progress":
                    _, done, total = event
                    self.bar.configure(maximum=max(total, 1), value=done)
                    self.progress_var.set(format_progress(done, total))
                elif event[0] == "done":
                    self._finish()
                    _, result, output_dir = event
                    show = messagebox.showinfo if result.ok else messagebox.showwarning
                    show(TITLE, summary_text(result, output_dir))
                elif event[0] == "error":
                    self._finish()
                    messagebox.showerror(TITLE, event[1])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain)

    def _finish(self) -> None:
        self.running = False
        self.start_button.configure(state="normal")

    def _on_close(self) -> None:
        if self.running and not messagebox.askokcancel(TITLE, "번역 중입니다. 창을 닫으면 번역이 중단됩니다. 닫을까요?"):
            return
        # Exiting closes our Job Object handles, which ends llama-server and the engine too.
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    App(root, default_settings_path())
    root.mainloop()
    return 0
```

- [ ] **Step 5: 통과 확인**

Run: `& $uv run pytest tests/test_settings.py tests/test_gui.py tests/test_cli.py -v`
Expected: 모두 PASS

Run: `& $uv run python -c "import tkinter; tkinter.Tk().destroy(); print('tk ok')"`
Expected: `tk ok` (uv가 설치한 Python에 tkinter가 포함되어 있는지 확인)

- [ ] **Step 6: 창 띄워 보기 (수동, 짧게)**

Run: `& $uv run manga-viewer gui`
Expected: 입력·출력 폴더, 번역 모델, llama-server, 언어("일본어 → 한국어"), 진행 막대, "번역 시작" 버튼, 로그 영역이 보인다. 아무것도 고르지 않고 "번역 시작"을 누르면 "입력 폴더를 선택하세요." 경고가 뜬다. 창을 닫는다. (실제 번역은 Task 7에서 한다.)

- [ ] **Step 7: Commit**

```bash
git add src/manga_viewer/settings.py src/manga_viewer/gui.py tests/test_settings.py tests/test_gui.py
git commit -m "feat: add a small tkinter window for folder translation"
```

---

### Task 6: 정리, 라이선스, README

**Files:**
- Delete: `src/manga_viewer/background.py`, `bench.py`, `glossary.py`, `order.py`, `page_image.py`, `render.py`, `translate.py`, `types.py`, `vision.py`, `llm/client.py`
- Delete: `tests/test_background.py`, `test_bench.py`, `test_glossary.py`, `test_order.py`, `test_page_image.py`, `test_render.py`, `test_translate.py`, `test_vision.py`, `test_client.py`
- Modify: `pyproject.toml`, `tests/test_imports.py`, `uv.lock`
- Create: `LICENSE`, `README.md`

**Interfaces:**
- Consumes: Task 1~5의 모듈 (남는 모듈: `source`, `winjob`, `llm/process`, `llm/llama`, `engine`, `engine_run`, `pipeline`, `settings`, `gui`, `cli`)

- [ ] **Step 1: 사용되지 않는 모듈과 테스트 삭제**

```powershell
git rm src/manga_viewer/background.py src/manga_viewer/bench.py src/manga_viewer/glossary.py src/manga_viewer/order.py src/manga_viewer/page_image.py src/manga_viewer/render.py src/manga_viewer/translate.py src/manga_viewer/types.py src/manga_viewer/vision.py src/manga_viewer/llm/client.py
git rm tests/test_background.py tests/test_bench.py tests/test_glossary.py tests/test_order.py tests/test_page_image.py tests/test_render.py tests/test_translate.py tests/test_vision.py tests/test_client.py
```

그다음 남은 코드에서 지운 모듈을 참조하는 곳이 없는지 확인한다.

Run: `git grep -n -E "background|bench|glossary|\border\b|page_image|render|translate import|\btypes\b|vision|llm.client|ChatClient" -- src tests`
Expected: `translate` 하위 명령 이름, `pipeline`/`gui`의 `TranslationRequest`·`run_translation` 같은 정상 사용 외에는 결과 없음. 남은 모듈이 지운 모듈을 import하면 이 단계에서 고친다.

- [ ] **Step 2: `tests/test_imports.py` 교체**

```python
import subprocess
import sys


def test_engine_modules_are_never_imported_by_the_wrapper():
    code = (
        "import sys\n"
        "import manga_viewer.cli, manga_viewer.engine, manga_viewer.engine_run, manga_viewer.pipeline, manga_viewer.gui\n"
        "leaked = [m for m in ('torch', 'ballontranslator') if m in sys.modules]\n"
        "assert not leaked, leaked\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: `pyproject.toml` 교체**

```toml
[project]
name = "manga-viewer"
version = "0.1.0"
description = "Batch Japanese-to-Korean manga translation with a local LLM, driving BallonsTranslator"
readme = "README.md"
license = "GPL-3.0-only"
requires-python = ">=3.12,<3.13"
dependencies = [
    "httpx>=0.27",
    "natsort>=8.4",
]

[project.scripts]
manga-viewer = "manga_viewer.cli:main"

[project.gui-scripts]
manga-viewer-gui = "manga_viewer.gui:main"

[dependency-groups]
dev = [
    "pytest>=8",
    "psutil>=6",
]

[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/manga_viewer"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: `LICENSE`와 `README.md` 작성**

GPL-3.0 전문을 받는다.

```powershell
Invoke-WebRequest https://www.gnu.org/licenses/gpl-3.0.txt -OutFile LICENSE
```

`README.md`:

````markdown
# manga-viewer

일본 만화 이미지 폴더를 로컬 LLM으로 한국어로 번역해, 말풍선을 지우고 한국어를 식자한 이미지를 저장하는 명령줄 도구입니다.
검출·OCR·인페인팅·식자는 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은 로컬
[llama.cpp](https://github.com/ggml-org/llama.cpp) 서버(Gemma 4 등 GGUF 모델)가 맡습니다.

## 요구 사항

- Windows 10/11, NVIDIA RTX 30 시리즈 이상
- [uv](https://docs.astral.sh/uv/), [Git for Windows](https://git-scm.com/download/win)
- llama.cpp Windows CUDA 빌드(`llama-server.exe`)와 번역용 GGUF 모델

## 설치

```powershell
uv sync
uv run manga-viewer setup
```

`setup`은 BallonsTranslator(고정 커밋)와 전용 Python 환경, 검출·OCR·인페인팅 모델(약 1GB)을
`%LOCALAPPDATA%\manga-viewer\BallonsTranslator`에 설치합니다. 다시 실행해도 안전합니다.

## 번역

```powershell
uv run manga-viewer translate <원본 폴더> <결과 폴더> --llama-server <llama-server.exe> --model <모델.gguf>
```

원본 폴더는 건드리지 않고, 결과 폴더에 번역된 이미지를 저장합니다.

## 창으로 실행

```powershell
uv run manga-viewer gui
```

입력·출력 폴더와 번역 모델(GGUF), llama-server.exe를 고르고 "번역 시작"을 누르면 진행 상황이 표시됩니다.

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
````

- [ ] **Step 5: 의존성 정리와 전체 테스트**

Run: `& $uv lock` 그리고 `& $uv sync`
Expected: torch, mokuro, numpy, pillow 등이 venv에서 제거된다.

Run: `& $uv run pytest -v`
Expected: 전체 통과, 경고 없음

- [ ] **Step 6: Commit**

```bash
git add -A src tests pyproject.toml uv.lock LICENSE README.md
git commit -m "chore: drop the in-house pipeline, license under GPL-3.0, add README"
```

---

### Task 7: 실제 확인 (수동)

코드 변경은 없다. 모델 파일 이름은 `.superpowers/sdd/2026-09-25-plan1-translation-core/task-10-report.md`에 있다.

- [ ] **Step 1: setup 멱등성 확인**

평가 때 설치한 엔진을 그대로 쓴다(새로 6GB를 받지 않기 위함).

```powershell
& $uv run manga-viewer setup --engine-dir .dev\BallonsTranslator --uv $uv
```

Expected: 고정 커밋 checkout, 패키지 설치(대부분 캐시), 모델은 검증 후 건너뜀, 종료 코드 0, `.dev\BallonsTranslator\.manga-viewer-setup` 생성.

- [ ] **Step 2: 샘플 번역**

```powershell
& $uv run manga-viewer translate manga-data\173830003 bench-out\translate-bt-e4b --llama-server .dev\llama\llama-server.exe --model .dev\models\gemma-4-e4b\<Q4 파일> --engine-dir .dev\BallonsTranslator
```

Expected: 6/6장 저장, 종료 코드 0, `manga-data\173830003`는 변경 없음(`git status`와 파일 수정 시각 확인), 끝난 뒤 `llama-server`·엔진 Python 프로세스가 남아 있지 않음(`Get-Process llama-server, python -ErrorAction SilentlyContinue`).

- [ ] **Step 3: GUI로 같은 번역 실행**

`%LOCALAPPDATA%\manga-viewer\settings.json`에 `engine_dir`(`.dev\BallonsTranslator`의 절대 경로), `model`, `llama_server`를 미리 넣어 두거나 창에서 고른다.

```powershell
& $uv run manga-viewer gui
```

입력 `manga-data\173830003`, 출력 `bench-out\translate-bt-gui`로 "번역 시작"을 누른다. 모델 이름과 "일본어 → 한국어"가 표시되고, 진행 막대가 0/6에서 6/6까지 오르며, 끝나면 요약 창이 뜨는지 확인한다. 창을 캡처해 보고서에 남긴다.

- [ ] **Step 4: 사용자 확인**

결과 폴더와 GUI 캡처를 사용자에게 알리고 품질을 확인받는다. 저장소에는 커밋하지 않는다.
