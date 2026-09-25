# 계획 3: 창에서 설치·취소, 프로그램 폴더 배치 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 창에서 번역 엔진·llama.cpp·번역 모델을 설치하고, 각 설치와 번역을 중단할 수 있게 한다. 앱이 만드는 모든 파일은 프로그램 폴더 안에 두고, 빌드 스크립트로 `C:\Users\serial\Downloads\manga-translate`에 실행용 프로그램 폴더를 만든다.

**Architecture:** `paths.py`가 프로그램 폴더 배치를 정하고, `download.py`가 이어받기·체크섬·중단을 지원하는 다운로드와 안전한 zip 풀기를 제공한다. `engine.py`(엔진)와 `components.py`(llama.cpp, 모델)가 이를 써서 설치하고, `pipeline.py`는 중단 신호로 Job Object를 닫아 번역을 멈춘다. `gui.py`는 작업 하나를 백그라운드 스레드에서 돌리며 "중단" 버튼으로 신호를 보낸다.

**Tech Stack:** Python 3.12, tkinter, urllib, zipfile, threading, uv, llama.cpp b11177, BallonsTranslator(커밋 3e401b2), pytest

**Spec:** `docs/superpowers/specs/2026-09-25-gui-installer-design.md` (번역 흐름은 `docs/superpowers/specs/2026-09-25-bt-wrapper-design.md`)

## Global Constraints

- 네이티브 Windows(PowerShell)에서 빌드·실행·테스트. WSL·Docker 금지. uv 경로: `C:\Users\serial\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe` (아래에서 `$uv`). 필요하면 `$env:UV_PYTHON_INSTALL_DIR="C:\Users\serial\.uv-python"`.
- 저장소: `C:\Users\serial\source\manga-translate` (브랜치 `main`, 원격 `https://github.com/kyj0503/manga-translate.git`). 폴더 이름이 바뀌어 `.venv`가 깨져 있다. Task 1 시작 전에 `.venv`를 지우고 `& $uv sync`로 다시 만든다.
- 앱이 만드는 파일은 모두 프로그램 폴더 안: `settings.json`, `engine\BallonsTranslator`, `runtime\llama`, `models`, `downloads`, `tools\uv.exe`. `%LOCALAPPDATA%`에 아무것도 만들지 않는다.
- 실행·실제 확인은 `C:\Users\serial\Downloads\manga-translate`(빌드 결과)에서 한다. 소스 저장소에서는 단위 테스트만 돌린다.
- 고정 값: 엔진 커밋 `3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8`; llama.cpp `b11177` zip 두 개(크기·SHA-256은 스펙 3장); 모델 `unsloth/gemma-4-E4B-it-GGUF` 리비전 `bfc15c382204943c3a8fff0c750b94ae2364d7a3`, `gemma-4-E4B-it-Q4_K_M.gguf`, 4,977,171,584B, sha256 `85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87`.
- 창에서 실행하는 하위 프로세스는 콘솔 창을 띄우지 않는다(`CREATE_NO_WINDOW`). 사용자에게 보이는 문구는 한국어. 중단은 오류가 아니다.
- Task 3~5 사이에는 옛 `gui.py`가 새 API와 맞지 않아 깨진다. Task 3~5의 전체 테스트는 `& $uv run pytest -q --ignore=tests/test_gui.py --ignore=tests/test_imports.py`로 돌린다. Task 6부터는 전체를 돌린다.
- 줄바꿈은 LF(`.gitattributes`). 커밋 작성자 이메일은 repo-local `heroria0503@gmail.com`. 커밋 메시지는 파일로 쓰고 `git commit -F <파일>`: 제목 줄, 빈 줄, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- 커밋하지 않는 것: `.superpowers/`, `.idea/`, `manga-data/`, `.dev/`, `bench-out/`, 그리고 위 프로그램 폴더 항목들.

## 파일 구조

| 파일 | 변경 | 책임 |
|---|---|---|
| `src/manga_translate/paths.py` | 신규 | 프로그램 폴더와 그 안의 경로, uv 찾기 |
| `src/manga_translate/download.py` | 신규 | 이어받기·체크섬·중단 다운로드, 안전한 zip 풀기, `InstallError`, `Cancelled` |
| `src/manga_translate/engine.py` | 교체 | 엔진 설치(소스 zip, venv, 패키지, 모델), 중단 |
| `src/manga_translate/components.py` | 신규 | llama.cpp·번역 모델 설치와 설치 여부 |
| `src/manga_translate/pipeline.py` | 수정 | 번역 중단 |
| `src/manga_translate/settings.py` | 수정 | 필드를 `model`, `last_input`, `last_output`으로 줄임 |
| `src/manga_translate/gui.py` | 교체 | 구성 요소 설치 줄, 중단 버튼, 작업 하나씩 |
| `scripts/build.ps1` | 신규 | 프로그램 폴더 빌드 |
| `.gitignore`, `README.md` | 수정 | |
| `tests/test_paths.py`, `tests/test_download.py`, `tests/test_components.py` | 신규 | |
| `tests/test_engine.py`, `tests/test_gui.py`, `tests/test_settings.py` | 교체 | |
| `tests/test_pipeline.py`, `tests/test_imports.py` | 수정 | |

---

### Task 1: 프로그램 폴더 배치 (`paths.py`)

**Files:**
- Create: `src/manga_translate/paths.py`
- Modify: `.gitignore`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `APP_HOME_ENV = "MANGA_TRANSLATE_HOME"`
  - `app_dir(environ: Mapping[str, str] = os.environ) -> Path` — `MANGA_TRANSLATE_HOME`이 있으면 그 경로, 없으면 `Path(sys.prefix).resolve().parent`
  - `@dataclass(frozen=True) AppLayout(root: Path)` with properties `settings_path`, `engine_dir`, `llama_dir`, `llama_server`, `models_dir`, `downloads_dir`, `bundled_uv`
  - `find_uv(layout, environ=os.environ, which=shutil.which) -> Path | None` — `UV` 환경 변수 → `bundled_uv` → `which("uv")` 순서로 실제 파일인 첫 경로

- [ ] **Step 0: 개발 환경 복구**

```powershell
Remove-Item -Recurse -Force .venv
& $uv sync
& $uv run pytest -q
```
Expected: 57 passed

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_paths.py`:

```python
import sys
from pathlib import Path

from manga_translate.paths import APP_HOME_ENV, AppLayout, app_dir, find_uv


def test_app_dir_defaults_to_the_folder_holding_the_venv():
    assert app_dir({}) == Path(sys.prefix).resolve().parent


def test_app_dir_override(tmp_path):
    assert app_dir({APP_HOME_ENV: str(tmp_path)}) == tmp_path


def test_layout(tmp_path):
    layout = AppLayout(tmp_path)
    assert layout.settings_path == tmp_path / "settings.json"
    assert layout.engine_dir == tmp_path / "engine" / "BallonsTranslator"
    assert layout.llama_dir == tmp_path / "runtime" / "llama"
    assert layout.llama_server == tmp_path / "runtime" / "llama" / "llama-server.exe"
    assert layout.models_dir == tmp_path / "models"
    assert layout.downloads_dir == tmp_path / "downloads"
    assert layout.bundled_uv == tmp_path / "tools" / "uv.exe"


def test_find_uv_order(tmp_path):
    layout = AppLayout(tmp_path)
    from_env = tmp_path / "env-uv.exe"
    from_path = tmp_path / "path-uv.exe"
    for f in (from_env, from_path):
        f.write_bytes(b"")
    layout.bundled_uv.parent.mkdir(parents=True)
    layout.bundled_uv.write_bytes(b"")

    assert find_uv(layout, {"UV": str(from_env)}, lambda n: str(from_path)) == from_env
    assert find_uv(layout, {}, lambda n: str(from_path)) == layout.bundled_uv
    layout.bundled_uv.unlink()
    assert find_uv(layout, {"UV": str(tmp_path / "gone.exe")}, lambda n: str(from_path)) == from_path
    assert find_uv(layout, {}, lambda n: None) is None
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_paths.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_translate.paths'`

- [ ] **Step 3: 구현**

`src/manga_translate/paths.py`:

```python
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
```

`.gitignore` 끝에 추가:

```gitignore
# Program-folder data created when the app runs from the source tree
/settings.json
/engine/
/runtime/
/models/
/downloads/
/tools/
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_paths.py -v` → 4 passed
Run: `& $uv run pytest -q` → 전체 통과

- [ ] **Step 5: Commit**

`git add src/manga_translate/paths.py tests/test_paths.py .gitignore` 후 제목 `feat: keep all app files in the program folder`로 커밋.

---

### Task 2: 이어받기·중단 다운로드와 zip 풀기 (`download.py`)

**Files:**
- Create: `src/manga_translate/download.py`
- Test: `tests/test_download.py`

**Interfaces:**
- Produces:
  - `class InstallError(RuntimeError)` — 사용자에게 보여줄 설치 오류
  - `class Cancelled(Exception)` — 사용자가 "중단"을 누름
  - `check_cancel(cancel: threading.Event | None) -> None` — 켜져 있으면 `Cancelled`
  - `sha256_of(path: Path) -> str`
  - 모듈 상수 `CHUNK = 1024 * 1024`, `PROGRESS_EVERY = 50 * 1024 * 1024`, `TIMEOUT = 60`
  - `download(url: str, dest: Path, sha256: str | None = None, *, log=print, cancel=None) -> None`
  - `extract_zip(archive: Path, dest: Path, *, strip_top: bool = False, cancel=None) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_download.py`:

```python
import hashlib
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import manga_translate.download as dl
from manga_translate.download import Cancelled, InstallError, download, extract_zip

BODY = bytes(range(256)) * 20  # 5120 bytes
SHA = hashlib.sha256(BODY).hexdigest()


@pytest.fixture
def server():
    files, hits, state = {"/f.bin": BODY}, [], {"ignore_range": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            rng = self.headers.get("Range")
            hits.append((self.path, rng))
            body = files.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            if rng and not state["ignore_range"]:
                start = int(rng.split("=")[1].split("-")[0])
                if start >= len(body):
                    self.send_response(416)
                    self.end_headers()
                    return
                chunk = body[start:]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits, state
    srv.shutdown()


def quiet(msg):
    pass


def test_fresh_download_is_verified(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "d" / "f.bin"
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY
    assert not dest.with_name("f.bin.part").exists()


def test_resumes_from_part(tmp_path, server):
    base, hits, _ = server
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(BODY[:1000])
    logs = []
    download(base + "/f.bin", dest, SHA, log=logs.append)
    assert dest.read_bytes() == BODY
    assert hits[-1][1] == "bytes=1000-"
    assert any("이어받기" in line for line in logs)


def test_server_ignoring_range_restarts(tmp_path, server):
    base, _, state = server
    state["ignore_range"] = True
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(b"garbage")
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY


def test_complete_part_is_accepted(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(BODY)
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY


def test_bad_checksum(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    with pytest.raises(InstallError, match="검증"):
        download(base + "/f.bin", dest, "0" * 64, log=quiet)
    assert not dest.exists()
    assert not dest.with_name("f.bin.part").exists()


def test_valid_existing_file_is_skipped(tmp_path, server):
    base, hits, _ = server
    dest = tmp_path / "f.bin"
    dest.write_bytes(BODY)
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert hits == []


def test_http_error(tmp_path, server):
    base, _, _ = server
    with pytest.raises(InstallError, match="다운로드"):
        download(base + "/missing", tmp_path / "x.bin", None, log=quiet)


def test_cancel_keeps_part(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    cancel = threading.Event()
    with pytest.raises(Cancelled):
        download(base + "/f.bin", dest, SHA, log=lambda m: cancel.set(), cancel=cancel)
    assert not dest.exists()
    assert dest.with_name("f.bin.part").exists()


def test_progress_is_logged(tmp_path, server, monkeypatch):
    base, _, _ = server
    monkeypatch.setattr(dl, "PROGRESS_EVERY", 1024)
    monkeypatch.setattr(dl, "CHUNK", 512)
    logs = []
    download(base + "/f.bin", tmp_path / "f.bin", SHA, log=logs.append)
    assert sum("MB" in line or "KB" in line for line in logs) >= 2


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_extract_strips_top_folder(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"top/a.txt": "A", "top/sub/b.txt": "B"})
    extract_zip(archive, tmp_path / "out", strip_top=True)
    assert (tmp_path / "out" / "a.txt").read_text() == "A"
    assert (tmp_path / "out" / "sub" / "b.txt").read_text() == "B"


def test_extract_flat(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"llama-server.exe": "exe"})
    extract_zip(archive, tmp_path / "out")
    assert (tmp_path / "out" / "llama-server.exe").read_text() == "exe"


def test_extract_rejects_traversal(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"../evil.txt": "x"})
    with pytest.raises(InstallError, match="경로"):
        extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_extract_cancel(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"a.txt": "A"})
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        extract_zip(archive, tmp_path / "out", cancel=cancel)
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_download.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_translate.download'`

- [ ] **Step 3: 구현**

`src/manga_translate/download.py`:

```python
"""Resumable, checksum-verified, cancellable downloads and safe zip extraction."""
from __future__ import annotations

import hashlib
import shutil
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

CHUNK = 1024 * 1024
PROGRESS_EVERY = 50 * 1024 * 1024
TIMEOUT = 60


class InstallError(RuntimeError):
    """An install problem; the message is shown to the user."""


class Cancelled(Exception):
    """The user pressed 중단."""


def check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _size_text(n: int) -> str:
    return f"{n // (1024 * 1024)}MB" if n >= 1024 * 1024 else f"{n // 1024}KB"


def download(
    url: str,
    dest: Path,
    sha256: str | None = None,
    *,
    log: Callable[[str], None] = print,
    cancel: threading.Event | None = None,
) -> None:
    """Download to <dest>.part (resuming it if present), verify, then rename.

    The .part file is kept when stopped or when the network fails, so the next call resumes.
    """
    if dest.is_file() and (sha256 is None or sha256_of(dest) == sha256):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.is_file() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    log(f"다운로드: {dest.name}" + (f" ({_size_text(start)}부터 이어받기)" if start else ""))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
            if start and response.status != 206:
                start = 0  # the server ignored Range: start over
            with part.open("ab" if start else "wb") as out:
                done = start
                next_log = (done // PROGRESS_EVERY + 1) * PROGRESS_EVERY
                while True:
                    check_cancel(cancel)
                    block = response.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if done >= next_log:
                        log(f"  {dest.name}: {_size_text(done)}")
                        next_log += PROGRESS_EVERY
    except urllib.error.HTTPError as e:
        if not (e.code == 416 and start):  # 416 with a .part means it is already complete
            raise InstallError(f"다운로드에 실패했습니다: {url} ({e})") from e
    except (urllib.error.URLError, OSError) as e:
        raise InstallError(f"다운로드에 실패했습니다: {url} ({e})") from e
    if sha256 is not None and sha256_of(part) != sha256:
        part.unlink()
        raise InstallError(f"다운로드한 파일 검증에 실패했습니다: {dest.name}")
    part.replace(dest)


def extract_zip(
    archive: Path,
    dest: Path,
    *,
    strip_top: bool = False,
    cancel: threading.Event | None = None,
) -> None:
    """Extract into dest (optionally dropping the archive's top folder); refuse paths that escape dest."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            check_cancel(cancel)
            name = PurePosixPath(info.filename)
            parts = name.parts[1:] if strip_top else name.parts
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if name.is_absolute() or not target.resolve().is_relative_to(root):
                raise InstallError(f"압축 파일에 잘못된 경로가 있습니다: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_download.py -v` → 13 passed
Run: `& $uv run pytest -q` → 전체 통과

- [ ] **Step 5: Commit**

`git add src/manga_translate/download.py tests/test_download.py` 후 제목 `feat: add resumable, cancellable downloads and safe zip extraction`.

---

### Task 3: 엔진 설치를 소스 zip·중단 방식으로 (`engine.py`)

**Files:**
- Replace: `src/manga_translate/engine.py`, `tests/test_engine.py`

**Interfaces:**
- Consumes: Task 2 `InstallError`, `Cancelled`, `check_cancel`, `download`, `extract_zip`
- Produces:
  - `ENGINE_COMMIT`, `ENGINE_ARCHIVE_URL`, `TORCH_INDEX`, `EXTRA_PACKAGES`, `SETUP_MARKER = ".manga-translate-setup"`, `ModelFile`, `MODEL_FILES`(기존 10개 그대로)
  - `class EngineError(InstallError)`
  - `EngineLayout(root)` with `python`, `config_path`, `marker`, `is_ready()` (기존 그대로)
  - `run_checked(argv)`, `_decode_output(data)` (기존 그대로)
  - `venv_command(layout, uv)`, `package_commands(layout, uv)` (기존 그대로)
  - `setup_engine(layout, *, uv: Path, downloads_dir: Path, run=run_checked, fetch=download, log=print, cancel=None) -> None`
  - 제거: `ENGINE_REPO`, `default_engine_dir`, `repo_commands`, `download_file`, `_sha256`, `PROGRESS_EVERY`(→ `download.py`), git 인자

- [ ] **Step 1: 실패하는 테스트 작성 (`tests/test_engine.py` 전체 교체)**

```python
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from manga_translate.download import Cancelled
from manga_translate.engine import (
    ENGINE_ARCHIVE_URL,
    ENGINE_COMMIT,
    MODEL_FILES,
    TORCH_INDEX,
    EngineError,
    EngineLayout,
    _decode_output,
    package_commands,
    run_checked,
    setup_engine,
    venv_command,
)

UV = Path("C:/tools/uv.exe")


def fake_fetch(calls):
    """Records calls; for the engine archive writes a tiny source zip like GitHub's."""

    def fetch(url, dest, sha256=None, *, log=print, cancel=None):
        calls.append((url, dest, sha256))
        if url == ENGINE_ARCHIVE_URL:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest, "w") as zf:
                zf.writestr(f"BallonsTranslator-{ENGINE_COMMIT}/requirements.txt", "numpy\n")
                zf.writestr(f"BallonsTranslator-{ENGINE_COMMIT}/ballontranslator/__init__.py", "")

    return fetch


def make_ready(root: Path) -> EngineLayout:
    layout = EngineLayout(root)
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    return layout


def test_layout_paths(tmp_path):
    layout = EngineLayout(tmp_path)
    assert layout.python == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert layout.config_path == tmp_path / "config" / "config.json"
    assert layout.marker == tmp_path / ".manga-translate-setup"


def test_is_ready_needs_matching_marker_and_python(tmp_path):
    layout = EngineLayout(tmp_path)
    assert not layout.is_ready()
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    layout.marker.write_text("other", encoding="utf-8")
    assert not layout.is_ready()
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    assert layout.is_ready()


def test_commands(tmp_path):
    layout = EngineLayout(tmp_path)
    assert ENGINE_ARCHIVE_URL == f"https://github.com/dmMaze/BallonsTranslator/archive/{ENGINE_COMMIT}.zip"
    assert venv_command(layout, UV) == [str(UV), "venv", "--python", "3.12", str(tmp_path / ".venv")]
    packages = [" ".join(c) for c in package_commands(layout, UV)]
    assert any("-r " + str(tmp_path / "requirements.txt") in c for c in packages)
    assert any(f"-e {tmp_path} --no-deps" in c for c in packages)
    assert any("torch torchvision --index-url " + TORCH_INDEX in c for c in packages)


def test_model_files():
    assert len(MODEL_FILES) == 10
    big = [f for f in MODEL_FILES if not f.path.endswith((".json", ".md", ".txt"))]
    assert all(f.sha256 for f in big)


def test_fresh_setup(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    downloads = tmp_path / "downloads"
    ran, fetched = [], []

    setup_engine(layout, uv=UV, downloads_dir=downloads, run=ran.append, fetch=fake_fetch(fetched), log=lambda m: None)

    assert fetched[0][0] == ENGINE_ARCHIVE_URL
    assert (layout.root / "requirements.txt").read_text() == "numpy\n"
    assert (layout.root / "ballontranslator" / "__init__.py").exists()
    assert not fetched[0][1].exists()  # archive removed after extraction
    assert ran == [venv_command(layout, UV), *package_commands(layout, UV)]
    assert [f[1] for f in fetched[1:]] == [layout.root / m.path for m in MODEL_FILES]
    assert layout.marker.read_text(encoding="utf-8") == ENGINE_COMMIT


def test_ready_engine_only_verifies_models(tmp_path):
    layout = make_ready(tmp_path / "engine")
    ran, fetched = [], []
    setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=ran.append, fetch=fake_fetch(fetched), log=lambda m: None)
    assert ran == []
    assert len(fetched) == len(MODEL_FILES)


def test_existing_venv_is_kept(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    ran = []
    setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=ran.append, fetch=fake_fetch([]), log=lambda m: None)
    assert venv_command(layout, UV) not in ran


def test_cancel_before_start(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    cancel = threading.Event()
    cancel.set()
    fetched = []
    with pytest.raises(Cancelled):
        setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=lambda a: None,
                     fetch=fake_fetch(fetched), log=lambda m: None, cancel=cancel)
    assert fetched == []
    assert not layout.marker.exists()


def test_cancel_between_package_steps(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    cancel = threading.Event()
    ran = []

    def run(argv):
        ran.append(argv)
        cancel.set()  # the user presses 중단 while the first command runs

    with pytest.raises(Cancelled):
        setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=run,
                     fetch=fake_fetch([]), log=lambda m: None, cancel=cancel)
    assert len(ran) == 1
    assert not layout.marker.exists()


def test_run_checked_success_and_failure_tail():
    run_checked([sys.executable, "-c", "print('fine')"])
    with pytest.raises(EngineError) as info:
        run_checked([sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"])
    assert "코드 3" in str(info.value) and "boom" in str(info.value)


def test_decode_output_handles_cp949_and_utf8(monkeypatch):
    monkeypatch.setattr("manga_translate.engine.locale.getpreferredencoding", lambda _: "cp949")
    assert _decode_output("한글 오류".encode("cp949")) == "한글 오류"
    assert _decode_output("utf8 문자".encode("utf-8")) == "utf8 문자"
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_engine.py -v`
Expected: FAIL (`ImportError: cannot import name 'ENGINE_ARCHIVE_URL'`)

- [ ] **Step 3: `engine.py` 전체 교체**

```python
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
        fetch(model.url, layout.root / model.path, model.sha256, log=log, cancel=cancel)
    check_cancel(cancel)
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_engine.py -v` → 11 passed
Run: `& $uv run pytest -q --ignore=tests/test_gui.py --ignore=tests/test_imports.py` → 통과 (옛 `gui.py`는 Task 6에서 교체)

- [ ] **Step 5: Commit**

`git add src/manga_translate/engine.py tests/test_engine.py` 후 제목 `feat: install the engine from its source archive and support stopping`.

---

### Task 4: llama.cpp와 번역 모델 설치 (`components.py`)

**Files:**
- Create: `src/manga_translate/components.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: Task 1 `AppLayout`; Task 2 `download`, `extract_zip`, `check_cancel`
- Produces:
  - `@dataclass(frozen=True) Asset(url: str, name: str, sha256: str, size: int)`
  - `LLAMA_TAG = "b11177"`, `LLAMA_ASSETS: tuple[Asset, Asset]`, `LLAMA_MARKER = ".manga-translate-llama"`, `MODEL: Asset`
  - `llama_ready(layout) -> bool`, `install_llama(layout, *, log=print, cancel=None, fetch=download) -> None`
  - `model_path(layout) -> Path`, `model_ready(layout) -> bool`, `install_model(layout, *, log=print, cancel=None, fetch=download) -> None`
  - 설치 함수들은 모듈 전역 `MODEL`·`LLAMA_ASSETS`를 호출 시점에 읽는다(테스트에서 monkeypatch 가능).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_components.py`:

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_components.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_translate.components'`

- [ ] **Step 3: 구현**

`src/manga_translate/components.py`:

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_components.py -v` → 4 passed
Run: `& $uv run pytest -q --ignore=tests/test_gui.py --ignore=tests/test_imports.py` → 통과

- [ ] **Step 5: Commit**

`git add src/manga_translate/components.py tests/test_components.py` 후 제목 `feat: install llama.cpp and the translation model into the program folder`.

---

### Task 5: 번역 중단 (`pipeline.py`)

**Files:**
- Modify: `src/manga_translate/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 2 `Cancelled`, `check_cancel`
- Produces:
  - `TranslationResult`에 필드 `cancelled: bool = False` 추가(마지막 필드)
  - `run_translation(req, *, on_log=print, on_progress=..., cancel: threading.Event | None = None) -> TranslationResult`
  - 중단되면: llama-server와 엔진을 담은 Job을 닫고, 그때까지 결과를 출력 폴더로 복사하고, 작업 폴더를 지우고, `cancelled=True`, `work_dir=None`인 결과를 돌려준다(예외 아님). 로그에 `번역을 중단했습니다.`
  - `validate`의 엔진 미설치 문구: `번역 엔진이 설치되어 있지 않습니다. 창의 '번역 엔진' 줄에서 '설치'를 먼저 눌러 주세요.`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_pipeline.py`에서:

1. `import threading`을 맨 위에 추가한다.
2. `test_validate_rejects_bad_requests`의 `match="엔진 설치"`를 `match="번역 엔진이 설치되어 있지 않습니다"`로 바꾼다.
3. `fakes` fixture의 `FakeJob`을 아래로 바꾸고, `state`에 `"on_run": None`을 추가하고, `fake_run`의 `return state["code"]` 바로 앞에 `if state["on_run"]: state["on_run"]()`를 넣는다. fixture가 `closed` 이벤트도 돌려주도록 `return calls, state, work, closed`로 바꾸고, 기존 테스트의 언패킹(`calls, _, work = fakes` 등)에 `_`를 하나씩 더한다.

```python
    closed = threading.Event()

    class FakeJob:
        def close(self):
            calls.append("job.close")
            closed.set()
```

4. 파일 끝에 추가:

```python
def test_cancel_during_engine_run_keeps_finished_pages(tmp_path, fakes):
    calls, state, work, closed = fakes
    cancel = threading.Event()
    state["produce"] = ["1.jpg"]
    state["code"] = -1

    def press_stop():
        cancel.set()
        assert closed.wait(5), "the job was not closed after 중단"

    state["on_run"] = press_stop
    logs = []
    result = run_translation(request(tmp_path, "1.jpg", "2.png"), on_log=logs.append, cancel=cancel)

    assert result.cancelled and not result.ok
    assert [p.name for p in result.saved] == ["1.png"]
    assert (tmp_path / "out" / "1.png").exists()
    assert result.work_dir is None and not work.exists()
    assert "번역을 중단했습니다." in logs


def test_cancel_before_engine_starts(tmp_path, fakes):
    calls, _, work, _ = fakes
    cancel = threading.Event()
    cancel.set()
    result = run_translation(request(tmp_path, "1.jpg"), on_log=lambda l: None, cancel=cancel)
    assert result.cancelled and result.saved == []
    assert not any(isinstance(c, tuple) and c[0] == "run" for c in calls)
    assert not work.exists()


def test_server_start_failure_after_stop_is_a_cancel(tmp_path, fakes):
    _, state, _, _ = fakes
    cancel = threading.Event()
    cancel.set()
    state["start_error"] = ServerStartError("killed")
    result = run_translation(request(tmp_path, "1.jpg"), on_log=lambda l: None, cancel=cancel)
    assert result.cancelled
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_pipeline.py -v`
Expected: 새 테스트 3개 FAIL (`unexpected keyword argument 'cancel'`), 문구 테스트 FAIL

- [ ] **Step 3: 구현**

`src/manga_translate/pipeline.py`:

- import에 `import threading`과 `from .download import check_cancel`을 추가한다.
- `TranslationResult` 마지막에 `cancelled: bool = False`를 추가한다.
- `validate`의 엔진 미설치 문구를 인터페이스에 적힌 문장으로 바꾼다.
- `_llama_server`와 `run_translation`을 아래로 교체한다.

```python
def _stopped(cancel: threading.Event | None) -> bool:
    return cancel is not None and cancel.is_set()


@contextmanager
def _llama_server(
    req: TranslationRequest,
    log_path: Path,
    on_log: Callable[[str], None],
    cancel: threading.Event | None,
) -> Iterator[tuple[KillOnCloseJob, str]]:
    """llama-server in a kill-on-close job; the engine joins the same job.

    Pressing 중단 closes the job, which ends both processes so the blocked calls return.
    """
    job = KillOnCloseJob()
    server = None
    finished = threading.Event()

    def close_job_on_cancel() -> None:
        while not finished.wait(0.2):
            if _stopped(cancel):
                job.close()
                return

    if cancel is not None:
        threading.Thread(target=close_job_on_cancel, daemon=True).start()
    try:
        on_log("LLM 서버를 시작하는 중...")
        try:
            server, base_url = start_llama_server(
                LlamaConfig(exe=req.llama_server, model=req.model, ctx_size=req.ctx_size), log_path, job=job
            )
        except (ServerStartError, OSError) as e:
            check_cancel(cancel)  # stopped by the user, not a failure
            raise PipelineError(f"LLM 서버를 시작하지 못했습니다: {e}") from e
        yield job, base_url
    finally:
        finished.set()
        if server is not None:
            server.stop()
        job.close()


def run_translation(
    req: TranslationRequest,
    *,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    cancel: threading.Event | None = None,
) -> TranslationResult:
    images = validate(req)
    total = len(images)
    work = Path(tempfile.mkdtemp(prefix="manga-translate-"))
    exec_dir = work / "pages"
    result_dir = exec_dir / "result"

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
    code = -1
    try:
        prepare_work_dir(images, exec_dir)
        with _llama_server(req, work / "llama-server.log", on_log, cancel) as (job, base_url):
            check_cancel(cancel)
            on_log("번역 설정을 쓰는 중...")
            write_engine_config(req.engine, base_url, req.model.stem)
            check_cancel(cancel)
            on_log(f"번역을 시작합니다 ({total}장)...")
            code = run_streaming(headless_argv(req.engine, exec_dir), req.engine.root, job=job, on_line=forward)
    except Exception:
        if not _stopped(cancel):
            on_log(f"작업 폴더: {work}")
            raise

    saved = collect_results(exec_dir, req.output_dir)
    missing = missing_pages(images, saved)
    report(total - len(missing))
    if _stopped(cancel):
        on_log("번역을 중단했습니다.")
        shutil.rmtree(work, ignore_errors=True)
        return TranslationResult(total, saved, missing, code, None, cancelled=True)
    keep = bool(missing) or req.keep_work
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return TranslationResult(total, saved, missing, code, work if keep else None)
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_pipeline.py -v` → 모두 PASS
Run: `& $uv run pytest -q --ignore=tests/test_gui.py --ignore=tests/test_imports.py` → 통과

- [ ] **Step 5: Commit**

`git add src/manga_translate/pipeline.py tests/test_pipeline.py` 후 제목 `feat: stop a running translation and keep the finished pages`.

---

### Task 6: 창 (`gui.py`, `settings.py`)

**Files:**
- Replace: `src/manga_translate/gui.py`, `tests/test_gui.py`, `tests/test_settings.py`
- Modify: `src/manga_translate/settings.py`, `tests/test_imports.py`

**Interfaces:**
- Consumes: Task 1 `AppLayout`, `app_dir`, `find_uv`; Task 2 `Cancelled`, `InstallError`; Task 3 `EngineError`, `EngineLayout`, `setup_engine`; Task 4 `components` 모듈(`MODEL`, `llama_ready`, `install_llama`, `model_path`, `model_ready`, `install_model`); Task 5 `run_translation(..., cancel=)`, `TranslationResult.cancelled`; 기존 `run_streaming`, `KillOnCloseJob`, `SOURCE_LANGUAGE`, `TARGET_LANGUAGE`, `PipelineError`, `TranslationRequest`
- Produces:
  - `Settings(model: str = "", last_input: str = "", last_output: str = "")`, `load_settings(path)`, `save_settings(settings, path)` (`default_settings_path` 제거)
  - `gui.default_output_dir`, `gui.format_progress`, `gui.component_status_text(ready, size)`, `gui.effective_model(layout, settings)`, `gui.model_status_text(layout, settings)`, `gui.can_translate(layout, settings)`, `gui.make_runner(on_line, job=None)`, `gui.build_request(layout, settings, input_dir, output_dir)`, `gui.summary_text(result, output_dir)`, `class gui.App(root, layout)`, `gui.main()`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_settings.py` 전체 교체:

```python
import json

from manga_translate.settings import Settings, load_settings, save_settings


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(model="C:/모델.gguf", last_input="D:/만화", last_output="D:/만화_번역")
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert "모델" in path.read_text(encoding="utf-8")


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_settings(bad) == Settings()


def test_old_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"model": "m.gguf", "llama_server": "x", "engine_dir": "y", "uv": "z"}), encoding="utf-8")
    assert load_settings(path) == Settings(model="m.gguf")
```

`tests/test_gui.py` 전체 교체:

```python
import sys
from pathlib import Path

import pytest

import manga_translate.components as components
from manga_translate.components import LLAMA_MARKER, LLAMA_TAG, Asset
from manga_translate.engine import ENGINE_COMMIT, EngineError, EngineLayout
from manga_translate.gui import (
    build_request,
    can_translate,
    component_status_text,
    default_output_dir,
    effective_model,
    format_progress,
    make_runner,
    model_status_text,
    summary_text,
)
from manga_translate.paths import AppLayout
from manga_translate.pipeline import PipelineError, TranslationResult
from manga_translate.settings import Settings

PYTHON = getattr(sys, "_base_executable", sys.executable)


@pytest.fixture
def small_model(monkeypatch):
    asset = Asset("https://example.invalid/m.gguf", "small-model.gguf", "ab" * 32, 3)
    monkeypatch.setattr(components, "MODEL", asset)
    return asset


def install_all(layout: AppLayout, with_model=True):
    engine = EngineLayout(layout.engine_dir)
    engine.python.parent.mkdir(parents=True)
    engine.python.write_bytes(b"")
    engine.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    layout.llama_dir.mkdir(parents=True)
    layout.llama_server.write_bytes(b"")
    (layout.llama_dir / LLAMA_MARKER).write_text(LLAMA_TAG, encoding="utf-8")
    if with_model:
        layout.models_dir.mkdir()
        (layout.models_dir / "small-model.gguf").write_bytes(b"123")


def test_default_output_dir():
    assert default_output_dir(Path("D:/만화/1권")) == Path("D:/만화/1권_번역")
    assert default_output_dir(Path("D:/")) == Path("D:/번역")


def test_format_progress():
    assert format_progress(0, 0) == "대기 중"
    assert format_progress(3, 6) == "3 / 6장"


def test_component_status_text():
    assert component_status_text(True, "약 6GB") == "설치됨"
    assert component_status_text(False, "약 6GB") == "설치 필요 (약 6GB)"


def test_effective_model_and_status(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    assert effective_model(layout, Settings()) is None
    assert model_status_text(layout, Settings()) == "설치 필요 (약 5GB)"
    layout.models_dir.mkdir()
    (layout.models_dir / "small-model.gguf").write_bytes(b"123")
    assert effective_model(layout, Settings()) == layout.models_dir / "small-model.gguf"
    assert model_status_text(layout, Settings()) == "small-model (설치됨)"
    mine = tmp_path / "mine.gguf"
    assert effective_model(layout, Settings(model=str(mine))) is None
    assert model_status_text(layout, Settings(model=str(mine))) == "mine (파일 없음)"
    mine.write_bytes(b"x")
    assert effective_model(layout, Settings(model=str(mine))) == mine
    assert model_status_text(layout, Settings(model=str(mine))) == "mine (직접 선택)"


def test_can_translate(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    assert not can_translate(layout, Settings())
    install_all(layout, with_model=False)
    assert not can_translate(layout, Settings())
    (layout.models_dir).mkdir()
    (layout.models_dir / "small-model.gguf").write_bytes(b"123")
    assert can_translate(layout, Settings())


def test_build_request(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    with pytest.raises(PipelineError, match="입력 폴더"):
        build_request(layout, Settings(), "", "D:/out")
    with pytest.raises(PipelineError, match="출력 폴더"):
        build_request(layout, Settings(), "D:/in", "")
    with pytest.raises(PipelineError, match="번역 모델"):
        build_request(layout, Settings(), "D:/in", "D:/out")
    install_all(layout)
    req = build_request(layout, Settings(), "D:/in", "D:/out")
    assert req.input_dir == Path("D:/in") and req.output_dir == Path("D:/out")
    assert req.llama_server == layout.llama_server
    assert req.model == layout.models_dir / "small-model.gguf"
    assert req.engine == EngineLayout(layout.engine_dir)


def test_summary_text():
    ok = TranslationResult(2, [Path("o/1.png"), Path("o/2.png")], [], 0, None)
    assert summary_text(ok, Path("D:/out")) == "2 / 2장을 번역했습니다.\n저장 위치: D:\\out"
    partial = TranslationResult(2, [Path("o/1.png")], [Path("i/2.png")], 9, Path("C:/tmp/w"))
    text = summary_text(partial, Path("D:/out"))
    assert "1 / 2장을 번역했습니다." in text
    assert "결과가 없는 페이지: 2.png" in text
    assert "작업 폴더: C:\\tmp\\w" in text
    assert "엔진이 오류로 끝났습니다 (코드 9). 로그를 확인하세요." in text
    stopped = TranslationResult(3, [Path("o/1.png")], [Path("i/2.png"), Path("i/3.png")], -1, None, cancelled=True)
    assert summary_text(stopped, Path("D:/out")) == "1 / 3장 저장 후 중단했습니다.\n저장 위치: D:\\out"


def test_make_runner_streams_and_raises():
    lines = []
    run = make_runner(lines.append)
    run([PYTHON, "-c", "print('설치 중')"])
    assert lines == ["설치 중"]
    with pytest.raises(EngineError, match="코드 3"):
        run([PYTHON, "-c", "import sys; sys.exit(3)"])


def test_make_runner_forwards_job():
    class FakeJob:
        pid = None

        def assign(self, pid):
            self.pid = pid

    job = FakeJob()
    make_runner(lambda line: None, job)([PYTHON, "-c", "pass"])
    assert job.pid is not None
```

`tests/test_imports.py`의 import 줄을 아래로 바꾼다.

```python
        "import manga_translate.gui, manga_translate.pipeline, manga_translate.engine, manga_translate.engine_run, manga_translate.components, manga_translate.download, manga_translate.paths\n"
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_gui.py tests/test_settings.py -v`
Expected: FAIL (`cannot import name 'can_translate'`, `Settings` 인자 불일치)

- [ ] **Step 3: `settings.py` 수정**

`Settings`를 아래로 바꾸고 `default_settings_path`와 `import os`를 지운다. `load_settings`, `save_settings`는 그대로 둔다.

```python
@dataclass
class Settings:
    model: str = ""  # a GGUF the user picked; empty means the installed default model
    last_input: str = ""
    last_output: str = ""
```

- [ ] **Step 4: `gui.py` 전체 교체**

```python
"""The app window: install the engine, llama.cpp and the model; translate a folder; stop any of it."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Sequence

from . import components
from .download import Cancelled, InstallError
from .engine import EngineError, EngineLayout, setup_engine
from .engine_run import run_streaming
from .paths import AppLayout, app_dir, find_uv
from .pipeline import (
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    PipelineError,
    TranslationRequest,
    TranslationResult,
    run_translation,
)
from .settings import Settings, load_settings, save_settings
from .winjob import KillOnCloseJob

TITLE = "manga-translate 번역"
POLL_MS = 100
ENGINE_SIZE = "약 6GB"
LLAMA_SIZE = "약 0.6GB"
MODEL_SIZE = "약 5GB"


def default_output_dir(input_dir: Path) -> Path:
    if not input_dir.name:
        return input_dir / "번역"
    return input_dir.with_name(f"{input_dir.name}_번역")


def format_progress(done: int, total: int) -> str:
    return f"{done} / {total}장" if total else "대기 중"


def component_status_text(ready: bool, size: str) -> str:
    return "설치됨" if ready else f"설치 필요 ({size})"


def effective_model(layout: AppLayout, settings: Settings) -> Path | None:
    """The GGUF to translate with: the user's pick if set, otherwise the installed default."""
    if settings.model:
        chosen = Path(settings.model)
        return chosen if chosen.is_file() else None
    return components.model_path(layout) if components.model_ready(layout) else None


def model_status_text(layout: AppLayout, settings: Settings) -> str:
    if settings.model:
        chosen = Path(settings.model)
        return f"{chosen.stem} (직접 선택)" if chosen.is_file() else f"{chosen.stem} (파일 없음)"
    if components.model_ready(layout):
        return f"{Path(components.MODEL.name).stem} (설치됨)"
    return f"설치 필요 ({MODEL_SIZE})"


def can_translate(layout: AppLayout, settings: Settings) -> bool:
    return (
        EngineLayout(layout.engine_dir).is_ready()
        and components.llama_ready(layout)
        and effective_model(layout, settings) is not None
    )


def make_runner(on_line: Callable[[str], None], job: KillOnCloseJob | None = None) -> Callable[[Sequence[str]], None]:
    """Engine setup commands for the window: no console, output goes to the log."""

    def run(argv: Sequence[str]) -> None:
        code = run_streaming(argv, Path.home(), job=job, on_line=on_line, stdin_text="")
        if code != 0:
            raise EngineError(f"명령이 실패했습니다 (코드 {code}): {' '.join(map(str, argv))}")

    return run


def build_request(layout: AppLayout, settings: Settings, input_dir: str, output_dir: str) -> TranslationRequest:
    if not input_dir:
        raise PipelineError("입력 폴더를 선택하세요.")
    if not output_dir:
        raise PipelineError("출력 폴더를 선택하세요.")
    model = effective_model(layout, settings)
    if model is None:
        raise PipelineError("번역 모델을 먼저 설치하거나 선택하세요.")
    return TranslationRequest(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        llama_server=layout.llama_server,
        model=model,
        engine=EngineLayout(layout.engine_dir),
    )


def summary_text(result: TranslationResult, output_dir: Path) -> str:
    done = result.total - len(result.missing)
    if result.cancelled:
        return f"{done} / {result.total}장 저장 후 중단했습니다.\n저장 위치: {output_dir}"
    lines = [f"{done} / {result.total}장을 번역했습니다.", f"저장 위치: {output_dir}"]
    if result.missing:
        lines.append("결과가 없는 페이지: " + ", ".join(p.name for p in result.missing))
    if result.work_dir is not None:
        lines.append(f"작업 폴더: {result.work_dir}")
    if result.engine_exit_code != 0:
        lines.append(f"엔진이 오류로 끝났습니다 (코드 {result.engine_exit_code}). 로그를 확인하세요.")
    return "\n".join(lines)


def _set_enabled(widget: ttk.Button, enabled: bool) -> None:
    widget.configure(state="normal" if enabled else "disabled")


class App:
    def __init__(self, root: tk.Tk, layout: AppLayout) -> None:
        self.root = root
        self.layout = layout
        self.settings = load_settings(layout.settings_path)
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self.cancel = threading.Event()
        self.task_job: KillOnCloseJob | None = None
        self.output_dir: Path | None = None

        root.title(TITLE)
        root.minsize(680, 580)
        self.input_var = tk.StringVar(value=self.settings.last_input)
        self.output_var = tk.StringVar(value=self.settings.last_output)
        self.engine_var = tk.StringVar()
        self.llama_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.progress_var = tk.StringVar(value=format_progress(0, 0))

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="입력 폴더").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.input_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_input).grid(row=0, column=3, sticky="ew")

        ttk.Label(frame, text="출력 폴더").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_output).grid(row=1, column=3, sticky="ew")

        ttk.Label(frame, text="언어").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(frame, text=f"{SOURCE_LANGUAGE} → {TARGET_LANGUAGE}").grid(row=2, column=1, sticky="w", padx=6)

        ttk.Label(frame, text="구성 요소").grid(row=3, column=0, sticky="w", pady=(12, 2))

        ttk.Label(frame, text="번역 엔진").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.engine_var).grid(row=4, column=1, sticky="w", padx=6)
        self.engine_button = ttk.Button(frame, text="설치", command=self._install_engine)
        self.engine_button.grid(row=4, column=2, sticky="ew")

        ttk.Label(frame, text="llama.cpp").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.llama_var).grid(row=5, column=1, sticky="w", padx=6)
        self.llama_button = ttk.Button(frame, text="설치", command=self._install_llama)
        self.llama_button.grid(row=5, column=2, sticky="ew")

        ttk.Label(frame, text="번역 모델").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.model_var).grid(row=6, column=1, sticky="w", padx=6)
        self.model_button = ttk.Button(frame, text="설치", command=self._install_model)
        self.model_button.grid(row=6, column=2, sticky="ew")
        self.pick_model_button = ttk.Button(frame, text="변경...", command=self._pick_model)
        self.pick_model_button.grid(row=6, column=3, sticky="ew")

        self.bar = ttk.Progressbar(frame, mode="determinate", maximum=1)
        self.bar.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        ttk.Label(frame, textvariable=self.progress_var).grid(row=7, column=3)

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=4, pady=8)
        self.start_button = ttk.Button(buttons, text="번역 시작", command=self._start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(buttons, text="중단", command=self._stop)
        self.stop_button.pack(side="left", padx=4)

        self.log = tk.Text(frame, height=12, state="disabled", wrap="word")
        self.log.grid(row=9, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(9, weight=1)

        self._refresh()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(POLL_MS, self._drain)

    # --- state ---

    def _save(self) -> None:
        save_settings(self.settings, self.layout.settings_path)

    def _refresh(self) -> None:
        engine_ok = EngineLayout(self.layout.engine_dir).is_ready()
        llama_ok = components.llama_ready(self.layout)
        model_ok = components.model_ready(self.layout)
        self.engine_var.set(component_status_text(engine_ok, ENGINE_SIZE))
        self.llama_var.set(component_status_text(llama_ok, LLAMA_SIZE))
        self.model_var.set(model_status_text(self.layout, self.settings))
        idle = not self.running
        _set_enabled(self.engine_button, idle and not engine_ok)
        _set_enabled(self.llama_button, idle and not llama_ok)
        _set_enabled(self.model_button, idle and not model_ok)
        _set_enabled(self.pick_model_button, idle)
        _set_enabled(self.start_button, idle and can_translate(self.layout, self.settings))
        _set_enabled(self.stop_button, self.running)

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
            self._save()
            self._refresh()

    # --- one background task at a time ---

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _log(self, line: str) -> None:
        # Safe from any thread: Tk is only touched in _drain.
        self.events.put(("log", line))

    def _launch(self, work: Callable[[], object], kind: str) -> None:
        self.running = True
        self.cancel = threading.Event()
        self.task_job = None
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._refresh()
        threading.Thread(target=self._run, args=(work, kind), daemon=True).start()

    def _run(self, work: Callable[[], object], kind: str) -> None:
        try:
            self.events.put((kind, work()))
        except Cancelled:
            self.events.put(("cancelled",))
        except Exception as e:
            if self.cancel.is_set():
                self.events.put(("cancelled",))  # a killed process failing is part of stopping
            elif isinstance(e, (InstallError, PipelineError)):
                self.events.put(("error", str(e)))
            else:
                self.events.put(("error", f"예상하지 못한 오류: {e!r}"))

    def _install_engine(self) -> None:
        uv = find_uv(self.layout)
        if uv is None:
            messagebox.showerror(TITLE, "uv를 찾을 수 없습니다. 빌드 스크립트로 프로그램을 다시 만들어 주세요.")
            return

        def work() -> str:
            job = KillOnCloseJob()
            self.task_job = job
            try:
                self._log(f"엔진 설치 위치: {self.layout.engine_dir}")
                setup_engine(
                    EngineLayout(self.layout.engine_dir),
                    uv=uv,
                    downloads_dir=self.layout.downloads_dir,
                    run=make_runner(self._log, job),
                    log=self._log,
                    cancel=self.cancel,
                )
                return "번역 엔진 설치가 끝났습니다."
            finally:
                job.close()

        self._launch(work, "installed")

    def _install_llama(self) -> None:
        def work() -> str:
            components.install_llama(self.layout, log=self._log, cancel=self.cancel)
            return "llama.cpp 설치가 끝났습니다."

        self._launch(work, "installed")

    def _install_model(self) -> None:
        def work() -> str:
            components.install_model(self.layout, log=self._log, cancel=self.cancel)
            return "번역 모델 설치가 끝났습니다."

        self._launch(work, "installed")

    def _start(self) -> None:
        try:
            req = build_request(self.layout, self.settings, self.input_var.get().strip(), self.output_var.get().strip())
        except PipelineError as e:
            messagebox.showwarning(TITLE, str(e))
            return
        self.settings.last_input = str(req.input_dir)
        self.settings.last_output = str(req.output_dir)
        self._save()
        self.output_dir = req.output_dir
        self.bar.configure(maximum=1, value=0)
        self.progress_var.set(format_progress(0, 0))

        def work() -> TranslationResult:
            return run_translation(
                req,
                on_log=self._log,
                on_progress=lambda done, total: self.events.put(("progress", done, total)),
                cancel=self.cancel,
            )

        self._launch(work, "translated")

    def _stop(self) -> None:
        if not self.running:
            return
        self.cancel.set()
        job = self.task_job
        if job is not None:
            job.close()  # ends uv and friends right away
        self._append_log("중단하는 중...")
        _set_enabled(self.stop_button, False)

    def _finish(self) -> None:
        self.running = False
        self.task_job = None
        self._refresh()

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1])
                elif kind == "progress":
                    _, done, total = event
                    self.bar.configure(maximum=max(total, 1), value=done)
                    self.progress_var.set(format_progress(done, total))
                elif kind == "installed":
                    self._finish()
                    messagebox.showinfo(TITLE, event[1])
                elif kind == "translated":
                    self._finish()
                    result = event[1]
                    show = messagebox.showinfo if result.ok or result.cancelled else messagebox.showwarning
                    show(TITLE, summary_text(result, self.output_dir))
                elif kind == "cancelled":
                    self._finish()
                    self._append_log("중단했습니다. 다시 누르면 이어서 진행합니다.")
                elif kind == "error":
                    self._finish()
                    messagebox.showerror(TITLE, event[1])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain)

    def _on_close(self) -> None:
        if self.running and not messagebox.askokcancel(TITLE, "작업 중입니다. 창을 닫으면 작업이 중단됩니다. 닫을까요?"):
            return
        self.cancel.set()
        # Exiting closes our Job Object handles, which ends llama-server, the engine and uv too.
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    App(root, AppLayout(app_dir()))
    root.mainloop()
    return 0
```

- [ ] **Step 5: 통과 확인**

Run: `& $uv run pytest -q` → 전체 통과, 경고 없음

- [ ] **Step 6: 창이 뜨는지 확인 (자동, 짧게)**

소스 저장소에서 창을 띄우되 프로그램 폴더를 임시 폴더로 돌린다(저장소에 파일이 생기지 않게).

```powershell
$env:MANGA_TRANSLATE_HOME = Join-Path $env:TEMP "mt-smoke"
$p = Start-Process -PassThru -FilePath ".venv\Scripts\pythonw.exe" -ArgumentList "-m", "manga_translate"
Start-Sleep -Seconds 3
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
[System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
New-Item -ItemType Directory -Force bench-out | Out-Null
$bmp.Save("bench-out\gui-installer-smoke.png")
Stop-Process -Id $p.Id
Remove-Item Env:\MANGA_TRANSLATE_HOME
```

Expected: 캡처에 구성 요소 세 줄(모두 "설치 필요 (...)"와 켜진 "설치" 버튼), "변경...", 꺼진 "번역 시작"과 "중단"이 보인다. Read 도구로 캡처를 열어 확인한다.

- [ ] **Step 7: Commit**

`git add src/manga_translate/gui.py src/manga_translate/settings.py tests/test_gui.py tests/test_settings.py tests/test_imports.py` 후 제목 `feat: install every component from the window and stop any task`.

---

### Task 7: 빌드 스크립트와 README

**Files:**
- Create: `scripts/build.ps1`
- Modify: `README.md`

**Interfaces:**
- Consumes: 앱 휠(`uv build`), `manga-translate` gui-script
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-Dest <폴더>] [-Uv <uv.exe>]`

- [ ] **Step 1: `scripts/build.ps1` 작성**

PowerShell 5.1은 BOM 없는 UTF-8 한글을 깨뜨리므로 스크립트 안 문구는 영어로 쓴다.

```powershell
# Build the runnable program folder: app venv + app wheel + bundled uv + shortcut.
# Engine, llama.cpp, models and settings in the folder are left untouched on rebuild.
param(
    [string]$Dest = (Join-Path $env:USERPROFILE "Downloads\manga-translate"),
    [string]$Uv = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

if (-not $Uv) {
    if ($env:UV -and (Test-Path $env:UV)) { $Uv = $env:UV }
    else { $Uv = (Get-Command uv -ErrorAction Stop).Source }
}

$dist = Join-Path $env:TEMP "manga-translate-dist"
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
& $Uv build --wheel --out-dir $dist $repo
if ($LASTEXITCODE -ne 0) { throw "uv build failed" }
$wheel = Get-ChildItem $dist -Filter *.whl | Select-Object -First 1

New-Item -ItemType Directory -Force -Path $Dest, (Join-Path $Dest "tools") | Out-Null
$python = Join-Path $Dest ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    & $Uv venv --python 3.12 (Join-Path $Dest ".venv")
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed" }
}
& $Uv pip install --python $python --reinstall $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "installing the app failed" }

Copy-Item $Uv (Join-Path $Dest "tools\uv.exe") -Force

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $Dest "manga-translate.lnk"))
$link.TargetPath = Join-Path $Dest ".venv\Scripts\manga-translate.exe"
$link.WorkingDirectory = $Dest
$link.Save()

Write-Host "Built: $Dest"
```

- [ ] **Step 2: 임시 폴더로 빌드 확인**

```powershell
$env:UV = $uv
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -Dest "$env:TEMP\mt-build-test"
Test-Path "$env:TEMP\mt-build-test\.venv\Scripts\manga-translate.exe"
Test-Path "$env:TEMP\mt-build-test\tools\uv.exe"
Test-Path "$env:TEMP\mt-build-test\manga-translate.lnk"
& "$env:TEMP\mt-build-test\.venv\Scripts\python.exe" -c "from manga_translate.paths import app_dir; print(app_dir())"
& "$env:TEMP\mt-build-test\.venv\Scripts\python.exe" -c "import manga_translate, pathlib; print((pathlib.Path(manga_translate.__file__).parent / 'scripts' / 'bt_write_config.py').is_file())"
```

Expected: `True` 세 번, `app_dir()`가 `...\mt-build-test`, 설정 스크립트 `True`(휠에 포함됨). 끝나면 `Remove-Item -Recurse -Force "$env:TEMP\mt-build-test"`.

- [ ] **Step 3: `README.md` 교체**

````markdown
# manga-translate

일본 만화 이미지 폴더를 로컬 LLM으로 한국어로 번역해, 말풍선을 지우고 한국어를 식자한 이미지를 저장하는 Windows 프로그램입니다.
검출·OCR·인페인팅·식자는 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은
[llama.cpp](https://github.com/ggml-org/llama.cpp)의 llama-server와 Gemma 4 모델이 맡습니다. 필요한 것은 모두 프로그램 창에서 설치합니다.

## 요구 사항

- Windows 10/11, NVIDIA RTX 30 시리즈 이상 그래픽카드
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 여유 디스크 공간 약 12GB

## 설치

```powershell
git clone https://github.com/kyj0503/manga-translate.git
cd manga-translate
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

`%USERPROFILE%\Downloads\manga-translate`에 프로그램 폴더가 만들어집니다. 다른 곳에 만들려면 `-Dest <폴더>`를 붙입니다.
프로그램이 받는 파일(엔진, llama.cpp, 모델, 설정)은 모두 이 폴더 안에만 저장됩니다.

## 사용법

1. 프로그램 폴더의 `manga-translate` 바로가기를 실행합니다.
2. "구성 요소"의 세 줄에서 각각 "설치"를 누릅니다.
   - 번역 엔진: 약 6GB, 수십 분 걸릴 수 있습니다.
   - llama.cpp: 약 0.6GB
   - 번역 모델(Gemma 4 E4B): 약 5GB
3. 입력 폴더와 출력 폴더를 고르고 "번역 시작"을 누릅니다. 원본 폴더는 건드리지 않습니다.

설치나 번역 중에 "중단"을 누르면 멈춥니다. 설치는 다시 "설치"를 누르면 받던 곳부터 이어서 진행하고,
번역은 그때까지 완성된 페이지를 출력 폴더에 남깁니다. 다른 GGUF 모델을 쓰려면 "변경..."으로 고릅니다.

## 개발

```powershell
uv sync
uv run pytest
```

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
````

- [ ] **Step 4: Commit**

`git add scripts/build.ps1 README.md` 후 제목 `feat: build script for the runnable program folder`.

---

### Task 8: 실제 확인 (수동, `C:\Users\serial\Downloads\manga-translate`)

코드 변경과 커밋은 없다. 아래 `$app = "C:\Users\serial\Downloads\manga-translate"`, `$py = "$app\.venv\Scripts\python.exe"`. 샘플은 `C:\Users\serial\source\manga-translate\manga-data\173830003`(6장, 저작물: 커밋 금지, 텍스트 인용 금지).

- [ ] **Step 1: 빌드**

```powershell
$env:UV = $uv
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

- [ ] **Step 2: llama.cpp 설치 — 중간 중단 후 이어받기**

`$py`로 스크립트를 실행한다(프로그램 폴더는 자동으로 `$app`). `install_llama`를 스레드에서 돌리고 첫 진행 로그(50MB)가 나오면 `cancel.set()` → `Cancelled`와 `downloads\*.part` 존재를 확인한다. 다시 `install_llama` → 로그에 "이어받기", `llama_ready` True.

- [ ] **Step 3: 번역 모델 설치 — 이미 받은 파일 재사용**

`C:\Users\serial\source\manga-translate\.dev\models\gemma-4-e4b\gemma-4-E4B-it-Q4_K_M.gguf`를 `$app\models\`로 복사한 뒤 `install_model` → 체크섬만 확인하고 다운로드 없이 끝남, `model_ready` True.

- [ ] **Step 4: 엔진 설치 — 중단 후 재개**

`C:\Users\serial\source\manga-translate\.dev\BallonsTranslator`를 `$app\engine\BallonsTranslator`로 복사한다(`robocopy /E`, `.git` 제외). `.manga-translate-setup` 표시 파일을 지운다. `setup_engine`(gui와 같은 `make_runner` + Job)을 스레드에서 돌리고 "엔진 Python 패키지를 설치하는 중" 로그 뒤 몇 초 후 중단(Job 닫기 + cancel) → `Cancelled`, 표시 파일 없음, 남은 `uv` 프로세스 없음. 다시 실행 → `is_ready` True.

- [ ] **Step 5: 번역 중단과 전체 번역**

`run_translation`(창과 같은 요청: `build_request(AppLayout($app), Settings(), 입력, 출력)`)으로 `bench-out\translate-cancel`에 번역하다 진행이 2/6이 되면 중단 → `cancelled` True, 저장 2장 이상, 남은 `llama-server`·엔진 프로세스 없음. 다시 `bench-out\translate-full`로 끝까지 → 6/6, 시간 기록.

- [ ] **Step 6: 창 캡처**

`$app\manga-translate.lnk`(또는 `$app\.venv\Scripts\manga-translate.exe`)로 창을 띄워 캡처(`bench-out\gui-installed.png`). 구성 요소 세 줄이 "설치됨"이고 "번역 시작"이 켜져 있는지 확인한 뒤 창을 닫는다.

- [ ] **Step 7: 보고**

결과, 시간, 남은 프로세스 확인, 캡처 설명을 보고서에 쓴다. `%LOCALAPPDATA%\manga-translate`(이전 설계로 만든 폴더)는 지우지 말고 사용자에게 알린다.
