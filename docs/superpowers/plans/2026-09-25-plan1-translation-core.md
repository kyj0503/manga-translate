# 계획 1: 번역 코어와 bench 도구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미지 폴더를 입력받아 텍스트 검출 → OCR → 읽기 순서 정렬 → 로컬 LLM 번역을 수행하고, 번역 결과와 속도를 HTML 리포트로 출력하는 `manga-viewer bench` 명령을 만든다. 이 도구로 기본 번역 모델을 확정한다.

**Architecture:** `src/manga_viewer/` 패키지에 순수 로직 모듈(`order`, `background`, `source`, `glossary`, `translate`)과 외부 연동 모듈(`vision`은 mokuro, `llm/`은 llama-server, `winjob`은 Windows Job Object)을 분리한다. 무거운 의존성(PyTorch, mokuro)은 `engine` extra로 분리하고 `vision.Vision` 생성 시점에만 import한다. 이 구조는 계획 3에서 "가벼운 venv 먼저, 무거운 의존성은 마법사가 설치" 방식과 맞물린다.

**Tech Stack:** Python 3.12, uv, mokuro 0.2.5+(comic-text-detector + manga-ocr 포함), PyTorch CUDA 12.8 휠, httpx, numpy, Pillow, natsort, llama.cpp `llama-server.exe`, pytest, psutil(테스트 전용)

**Spec:** `docs/superpowers/specs/2026-09-25-manga-viewer-design.md`

## Global Constraints

- 대상 OS: Windows 10/11. `winjob`은 Windows 전용이며 다른 OS에서는 테스트를 skip한다.
- GPU: NVIDIA RTX 30 시리즈 이상, VRAM 12GB 이상.
- Python: `>=3.12,<3.13`.
- 무거운 의존성(`mokuro`, `torch`, `torchvision`)은 `engine` extra에만 둔다. 기본 의존성과 `vision.py`를 제외한 모듈은 이것들을 import하지 않는다.
- llama-server는 `127.0.0.1`에만 바인딩한다.
- LLM 응답은 `response_format`의 `json_schema`로 강제하고, 스키마는 `{"translations": [{"id": int, "ko": str}]}`이다.
- temperature 기본값은 0.3, 이전 페이지 문맥은 2페이지.
- 누락 id 또는 LLM 오류는 1회만 재요청한다. 그래도 실패한 말풍선은 `failed_ids`로 보고한다.
- 샘플 만화, 모델, llama.cpp 바이너리는 저장소에 커밋하지 않는다(`.dev/` 아래에 두고 gitignore).
- 사용자에게 보이는 CLI 문구는 한국어로 쓴다.
- 모든 커밋의 작성자 이메일은 `heroria0503@gmail.com`이다. 이 저장소의 로컬 git 설정에 이미 지정되어 있다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `pyproject.toml` | 패키지 정의, 의존성, uv PyTorch 인덱스, pytest 설정 |
| `.gitignore` | venv, 캐시, `.dev/`, `bench-out/`, `.idea/` 제외 |
| `src/manga_viewer/__init__.py` | 버전 |
| `src/manga_viewer/types.py` | `TextBlock`, `PageAnalysis`, `Box`, `RGB` |
| `src/manga_viewer/order.py` | 읽기 순서 정렬 |
| `src/manga_viewer/background.py` | 박스 테두리 중앙값 배경색 |
| `src/manga_viewer/source.py` | 폴더 내 이미지 목록(자연 정렬) |
| `src/manga_viewer/glossary.py` | 용어집 항목, TOML 로드, 페이지 관련 항목 추출 |
| `src/manga_viewer/winjob.py` | Job Object(KILL_ON_JOB_CLOSE) |
| `src/manga_viewer/llm/__init__.py` | 패키지 표시 |
| `src/manga_viewer/llm/process.py` | 헬스체크 기반 자식 프로세스 관리(`ManagedServer`) |
| `src/manga_viewer/llm/llama.py` | llama-server 인자 구성과 기동 |
| `src/manga_viewer/llm/client.py` | OpenAI 호환 JSON 스키마 채팅 클라이언트 |
| `src/manga_viewer/translate.py` | 프롬프트, 응답 파싱, 재요청 |
| `src/manga_viewer/vision.py` | mokuro 결과 → `PageAnalysis` |
| `src/manga_viewer/bench.py` | bench 실행 루프, 요약, HTML/JSON 출력 |
| `src/manga_viewer/cli.py` | `manga-viewer bench` 명령 |
| `tests/helpers/job_parent.py` | Job 테스트용 부모 프로세스 |
| `tests/helpers/fake_health_server.py` | `/health` 흉내 서버 |
| `tests/test_*.py` | 모듈별 테스트 |
| `docs/superpowers/notes/model-benchmark.md` | 모델 비교 결과와 결정 |

---

### Task 0: 프로젝트 골격

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/manga_viewer/__init__.py`, `tests/test_package.py`

**Interfaces:**
- Produces: import 가능한 `manga_viewer` 패키지(`manga_viewer.__version__ == "0.1.0"`), `uv run pytest`로 실행되는 테스트 환경, `engine` extra가 설치된 `.venv`

- [ ] **Step 1: uv 설치 확인**

Run: `uv --version`
없으면 설치한다. 공식 배포 채널인 winget을 쓴다.

```powershell
winget install --id=astral-sh.uv -e
```

설치한 뒤 새 셸에서 `uv --version`이 출력되는지 확인한다.

- [ ] **Step 2: `pyproject.toml` 작성**

```toml
[project]
name = "manga-viewer"
version = "0.1.0"
description = "Local-LLM manga translation viewer for Korean readers"
requires-python = ">=3.12,<3.13"
dependencies = [
    "httpx>=0.27",
    "natsort>=8.4",
    "numpy>=1.26",
    "pillow>=11.3",
]

[project.optional-dependencies]
engine = [
    "mokuro>=0.2.5",
    "torch>=2.7",
    "torchvision>=0.22",
]

[project.scripts]
manga-viewer = "manga_viewer.cli:main"

[dependency-groups]
dev = [
    "pytest>=8",
    "psutil>=6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/manga_viewer"]

[tool.uv.sources]
torch = [{ index = "pytorch-cu128" }]
torchvision = [{ index = "pytorch-cu128" }]

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["gpu: requires a CUDA GPU and the engine extra"]
```

- [ ] **Step 3: `.gitignore` 작성**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
build/
dist/
.idea/
.vscode/
.dev/
bench-out/
```

- [ ] **Step 4: 패키지와 스모크 테스트 작성**

`src/manga_viewer/__init__.py`:

```python
__version__ = "0.1.0"
```

`tests/test_package.py`:

```python
import manga_viewer


def test_version():
    assert manga_viewer.__version__ == "0.1.0"
```

- [ ] **Step 5: 의존성 설치**

Run: `uv sync --extra engine`
Expected: `.venv` 생성, torch(cu128) 포함 설치 완료. 다운로드가 약 3GB라 몇 분 걸린다.

Run: `uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
Expected: `2.x.x+cu128 True`

- [ ] **Step 6: 테스트 실행**

Run: `uv run pytest -v`
Expected: `test_version PASSED`

- [ ] **Step 7: Commit**

`uv.lock`도 함께 커밋한다.

```bash
git add pyproject.toml uv.lock .gitignore src tests
git commit -m "chore: scaffold manga-viewer package with uv"
```

---

### Task 1: 데이터 타입과 읽기 순서 정렬

**Files:**
- Create: `src/manga_viewer/types.py`, `src/manga_viewer/order.py`
- Test: `tests/test_order.py`

**Interfaces:**
- Produces:
  - `Box = tuple[int, int, int, int]` (x1, y1, x2, y2), `RGB = tuple[int, int, int]`
  - `@dataclass(frozen=True) TextBlock(id: int, box: Box, vertical: bool, ja: str, bg_color: RGB = (255, 255, 255))`
  - `@dataclass(frozen=True) PageAnalysis(width: int, height: int, blocks: tuple[TextBlock, ...])`
  - `sort_reading_order(blocks: Sequence[TextBlock]) -> list[TextBlock]`: 위→아래로 행을 묶고, 행 안에서는 오른쪽→왼쪽으로 정렬한다. id는 0부터 다시 매긴다.

- [ ] **Step 1: `types.py` 작성**

```python
from __future__ import annotations

from dataclasses import dataclass

Box = tuple[int, int, int, int]  # x1, y1, x2, y2 (x2, y2 exclusive)
RGB = tuple[int, int, int]


@dataclass(frozen=True)
class TextBlock:
    id: int
    box: Box
    vertical: bool
    ja: str
    bg_color: RGB = (255, 255, 255)


@dataclass(frozen=True)
class PageAnalysis:
    width: int
    height: int
    blocks: tuple[TextBlock, ...]
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_order.py`:

```python
from manga_viewer.order import sort_reading_order
from manga_viewer.types import TextBlock


def block(name, box):
    return TextBlock(id=-1, box=box, vertical=True, ja=name)


def names(blocks):
    return [b.ja for b in blocks]


def test_empty():
    assert sort_reading_order([]) == []


def test_same_row_right_to_left():
    left = block("left", (0, 0, 100, 100))
    right = block("right", (200, 0, 300, 100))
    assert names(sort_reading_order([left, right])) == ["right", "left"]


def test_rows_top_to_bottom():
    top = block("top", (0, 0, 100, 100))
    bottom = block("bottom", (0, 200, 100, 300))
    assert names(sort_reading_order([bottom, top])) == ["top", "bottom"]


def test_grid():
    blocks = [
        block("BL", (0, 200, 100, 300)),
        block("TL", (0, 0, 100, 100)),
        block("BR", (200, 200, 300, 300)),
        block("TR", (200, 0, 300, 100)),
    ]
    assert names(sort_reading_order(blocks)) == ["TR", "TL", "BR", "BL"]


def test_slightly_offset_blocks_share_a_row():
    left = block("left", (0, 10, 100, 110))
    right = block("right", (200, 0, 300, 100))
    assert names(sort_reading_order([left, right])) == ["right", "left"]


def test_ids_are_reassigned_in_order():
    blocks = [block("a", (0, 0, 100, 100)), block("b", (200, 0, 300, 100))]
    assert [b.id for b in sort_reading_order(blocks)] == [0, 1]
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_order.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_viewer.order'`

- [ ] **Step 4: `order.py` 구현**

```python
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from .types import TextBlock

# A block joins the current row when at least this fraction of its height
# overlaps the row's vertical extent.
ROW_OVERLAP_RATIO = 0.5


def sort_reading_order(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    """Manga order: rows top-to-bottom, right-to-left within a row. Ids are reassigned 0..n-1."""
    rows: list[list[TextBlock]] = []
    row_ranges: list[tuple[int, int]] = []
    for blk in sorted(blocks, key=lambda b: b.box[1]):
        y1, y2 = blk.box[1], blk.box[3]
        height = max(y2 - y1, 1)
        if rows:
            ry1, ry2 = row_ranges[-1]
            overlap = min(y2, ry2) - max(y1, ry1)
            if overlap >= ROW_OVERLAP_RATIO * height:
                rows[-1].append(blk)
                row_ranges[-1] = (min(ry1, y1), max(ry2, y2))
                continue
        rows.append([blk])
        row_ranges.append((y1, y2))

    ordered = [
        blk
        for row in rows
        for blk in sorted(row, key=lambda b: -(b.box[0] + b.box[2]))
    ]
    return [replace(blk, id=i) for i, blk in enumerate(ordered)]
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_order.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/manga_viewer/types.py src/manga_viewer/order.py tests/test_order.py
git commit -m "feat: add text block types and manga reading order"
```

---

### Task 2: 말풍선 배경색

**Files:**
- Create: `src/manga_viewer/background.py`
- Test: `tests/test_background.py`

**Interfaces:**
- Consumes: `Box`, `RGB` (Task 1)
- Produces: `border_median_color(image: np.ndarray, box: Box) -> RGB`. `image`는 `H x W x 3` RGB uint8이다. 박스를 이미지 안으로 잘라낸 뒤, 박스 네 변의 픽셀 중앙값을 반환한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_background.py`:

```python
import numpy as np

from manga_viewer.background import border_median_color


def test_white_bubble_with_black_text_is_white():
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    image[40:60, 40:60] = 0  # "text" inside the box
    assert border_median_color(image, (20, 20, 80, 80)) == (255, 255, 255)


def test_uniform_gray():
    image = np.full((50, 50, 3), 128, dtype=np.uint8)
    assert border_median_color(image, (5, 5, 45, 45)) == (128, 128, 128)


def test_colored_background():
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    image[:, :] = (250, 230, 200)
    assert border_median_color(image, (10, 10, 40, 40)) == (250, 230, 200)


def test_box_outside_image_is_clamped():
    image = np.full((30, 30, 3), 200, dtype=np.uint8)
    assert border_median_color(image, (-10, -10, 100, 100)) == (200, 200, 200)


def test_degenerate_box_does_not_crash():
    image = np.full((30, 30, 3), 10, dtype=np.uint8)
    assert border_median_color(image, (15, 15, 15, 15)) == (10, 10, 10)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_background.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`src/manga_viewer/background.py`:

```python
from __future__ import annotations

import numpy as np

from .types import RGB, Box


def border_median_color(image: np.ndarray, box: Box) -> RGB:
    """Median color of the box's edge pixels; used to paint over the original text."""
    h, w = image.shape[:2]
    x1 = min(max(box[0], 0), w - 1)
    y1 = min(max(box[1], 0), h - 1)
    x2 = min(max(box[2], x1 + 1), w)
    y2 = min(max(box[3], y1 + 1), h)
    region = image[y1:y2, x1:x2, :3]
    border = np.concatenate([region[0], region[-1], region[:, 0], region[:, -1]])
    median = np.median(border, axis=0)
    return tuple(int(round(v)) for v in median)  # type: ignore[return-value]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_background.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/background.py tests/test_background.py
git commit -m "feat: compute bubble background color from box border"
```

---

### Task 3: 이미지 목록과 용어집

**Files:**
- Create: `src/manga_viewer/source.py`, `src/manga_viewer/glossary.py`
- Test: `tests/test_source.py`, `tests/test_glossary.py`

**Interfaces:**
- Produces:
  - `IMAGE_SUFFIXES: frozenset[str]`
  - `list_images(folder: Path) -> list[Path]`: 하위 폴더를 뒤지지 않고, 이미지 파일만 대소문자 무시 자연 정렬로 반환한다.
  - `@dataclass(frozen=True) GlossaryEntry(ja: str, ko: str, note: str = "")`
  - `load_glossary(path: Path) -> list[GlossaryEntry]`: TOML의 `[[entry]]` 배열을 읽는다.
  - `relevant_entries(entries: Iterable[GlossaryEntry], texts: Iterable[str]) -> list[GlossaryEntry]`: `ja`가 텍스트 중 하나에라도 포함된 항목만 반환한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_source.py`:

```python
from manga_viewer.source import list_images


def touch(path):
    path.write_bytes(b"")
    return path


def test_natural_sort_and_filtering(tmp_path):
    for name in ["10.jpg", "2.png", "1.JPG", "notes.txt", "cover.webp"]:
        touch(tmp_path / name)
    (tmp_path / "sub").mkdir()
    touch(tmp_path / "sub" / "0.jpg")

    assert [p.name for p in list_images(tmp_path)] == ["1.JPG", "2.png", "10.jpg", "cover.webp"]


def test_empty_folder(tmp_path):
    assert list_images(tmp_path) == []
```

`tests/test_glossary.py`:

```python
from manga_viewer.glossary import GlossaryEntry, load_glossary, relevant_entries


def test_load_glossary(tmp_path):
    path = tmp_path / "g.toml"
    path.write_text(
        '[[entry]]\nja = "悟"\nko = "사토루"\nnote = "주인공"\n\n'
        '[[entry]]\nja = "呪術"\nko = "주술"\n',
        encoding="utf-8",
    )
    assert load_glossary(path) == [
        GlossaryEntry("悟", "사토루", "주인공"),
        GlossaryEntry("呪術", "주술", ""),
    ]


def test_relevant_entries_only_returns_terms_on_page():
    entries = [GlossaryEntry("悟", "사토루"), GlossaryEntry("呪術", "주술"), GlossaryEntry("", "빈값")]
    assert relevant_entries(entries, ["悟、行くぞ", "はい"]) == [GlossaryEntry("悟", "사토루")]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_source.py tests/test_glossary.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`src/manga_viewer/source.py`:

```python
from __future__ import annotations

from pathlib import Path

from natsort import natsorted, ns

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})


def list_images(folder: Path) -> list[Path]:
    """Image files directly inside ``folder``, naturally sorted (2.jpg before 10.jpg)."""
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    return natsorted(files, key=lambda p: p.name, alg=ns.IGNORECASE)
```

`src/manga_viewer/glossary.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class GlossaryEntry:
    ja: str
    ko: str
    note: str = ""


def load_glossary(path: Path) -> list[GlossaryEntry]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return [
        GlossaryEntry(ja=str(e.get("ja", "")), ko=str(e.get("ko", "")), note=str(e.get("note", "")))
        for e in data.get("entry", [])
    ]


def relevant_entries(entries: Iterable[GlossaryEntry], texts: Iterable[str]) -> list[GlossaryEntry]:
    """Entries whose Japanese term appears on the page; keeps the prompt short."""
    joined = "\n".join(texts)
    return [e for e in entries if e.ja and e.ja in joined]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_source.py tests/test_glossary.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/source.py src/manga_viewer/glossary.py tests/test_source.py tests/test_glossary.py
git commit -m "feat: add natural-sorted image listing and glossary loading"
```

---

### Task 4: Windows Job Object

**Files:**
- Create: `src/manga_viewer/winjob.py`, `tests/helpers/job_parent.py`
- Test: `tests/test_winjob.py`

**Interfaces:**
- Produces: `class KillOnCloseJob` with `assign(pid: int) -> None` and `close() -> None`. `close()`를 호출하거나 소유 프로세스가 죽어서 핸들이 닫히면, 할당된 프로세스가 모두 종료된다.

**주의:** uv venv의 `python.exe`는 실제 인터프리터를 자식으로 띄우는 런처일 수 있다. 런처를 kill해도 실제 인터프리터는 살아남을 수 있으므로, 테스트는 `sys._base_executable`(실제 인터프리터)에 `PYTHONPATH=src`를 줘서 실행한다.

- [ ] **Step 1: 헬퍼 작성**

`tests/helpers/job_parent.py`:

```python
"""Creates a kill-on-close job, puts a sleeping child in it, prints the child pid, then waits."""
import subprocess
import sys
import time

from manga_viewer.winjob import KillOnCloseJob

job = KillOnCloseJob()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
job.assign(child.pid)
print(child.pid, flush=True)
time.sleep(120)
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_winjob.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

ROOT = Path(__file__).resolve().parents[1]
PYTHON = getattr(sys, "_base_executable", sys.executable)


def test_close_kills_assigned_process():
    from manga_viewer.winjob import KillOnCloseJob

    job = KillOnCloseJob()
    child = subprocess.Popen([PYTHON, "-c", "import time; time.sleep(120)"])
    job.assign(child.pid)
    job.close()
    child.wait(timeout=10)


def test_child_dies_when_owner_is_killed():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    parent = subprocess.Popen(
        [PYTHON, str(ROOT / "tests" / "helpers" / "job_parent.py")],
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    child = psutil.Process(int(parent.stdout.readline()))
    assert child.is_running()

    parent.kill()
    parent.wait(timeout=10)
    child.wait(timeout=10)  # raises psutil.TimeoutExpired if the child survived
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_winjob.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_viewer.winjob'`

- [ ] **Step 4: 구현**

`src/manga_viewer/winjob.py`:

```python
"""Windows Job Object that kills its processes when the last handle closes.

The OS closes our handle when this process exits for any reason (window close,
crash, Task Manager), so children such as llama-server never outlive the app.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
_kernel32.SetInformationJobObject.restype = wintypes.BOOL
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


class KillOnCloseJob:
    def __init__(self) -> None:
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
        ):
            err = ctypes.get_last_error()
            _kernel32.CloseHandle(handle)
            raise ctypes.WinError(err)
        self._handle = handle

    def assign(self, pid: int) -> None:
        if self._handle is None:
            raise RuntimeError("job is closed")
        process = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not _kernel32.AssignProcessToJobObject(self._handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _kernel32.CloseHandle(process)

    def close(self) -> None:
        """Closing the last handle terminates every assigned process."""
        if self._handle is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_winjob.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/manga_viewer/winjob.py tests/helpers/job_parent.py tests/test_winjob.py
git commit -m "feat: add kill-on-close Windows job object"
```

---

### Task 5: 헬스체크 기반 서버 프로세스 관리와 llama-server 기동

**Files:**
- Create: `src/manga_viewer/llm/__init__.py`, `src/manga_viewer/llm/process.py`, `src/manga_viewer/llm/llama.py`, `tests/helpers/fake_health_server.py`
- Test: `tests/test_process.py`, `tests/test_llama.py`

**Interfaces:**
- Consumes: `KillOnCloseJob` (Task 4)
- Produces:
  - `class ServerStartError(RuntimeError)`
  - `free_port() -> int`
  - `class ManagedServer(argv: list[str], health_url: str, log_path: Path, job: KillOnCloseJob | None = None)` with `start(timeout: float = 180.0, poll_interval: float = 0.25) -> None`, `is_healthy() -> bool`, `stop(timeout: float = 10.0) -> None`, `running: bool`(property)
  - `@dataclass(frozen=True) LlamaConfig(exe: Path, model: Path, ctx_size: int = 8192, n_gpu_layers: int = 999)`
  - `build_llama_args(cfg: LlamaConfig, port: int) -> list[str]`
  - `start_llama_server(cfg: LlamaConfig, log_path: Path, job: KillOnCloseJob | None = None, timeout: float = 300.0) -> tuple[ManagedServer, str]` (두 번째 값은 `http://127.0.0.1:<port>`)

- [ ] **Step 1: 가짜 서버 헬퍼 작성**

`tests/helpers/fake_health_server.py`:

```python
"""Minimal stand-in for llama-server: /health returns 503 until ready_after seconds pass."""
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[1])
ready_after = float(sys.argv[2])
started = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            ready = time.monotonic() - started >= ready_after
            self.send_response(200 if ready else 503)
            self.end_headers()
            self.wfile.write(b"{}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_process.py`:

```python
import sys
from pathlib import Path

import pytest

from manga_viewer.llm.process import ManagedServer, ServerStartError, free_port

HELPER = Path(__file__).parent / "helpers" / "fake_health_server.py"
# The real interpreter, not the venv launcher: terminating a launcher can orphan its child.
PYTHON = getattr(sys, "_base_executable", sys.executable)


def fake_server(tmp_path, ready_after):
    port = free_port()
    return ManagedServer(
        [PYTHON, str(HELPER), str(port), str(ready_after)],
        health_url=f"http://127.0.0.1:{port}/health",
        log_path=tmp_path / "server.log",
    )


def test_start_waits_until_healthy_then_stop(tmp_path):
    server = fake_server(tmp_path, ready_after=0.5)
    server.start(timeout=15)
    try:
        assert server.running
        assert server.is_healthy()
    finally:
        server.stop()
    assert not server.running


def test_process_that_exits_reports_log_tail(tmp_path):
    server = ManagedServer(
        [PYTHON, "-c", "import sys; print('boom', flush=True); sys.exit(3)"],
        health_url=f"http://127.0.0.1:{free_port()}/health",
        log_path=tmp_path / "server.log",
    )
    with pytest.raises(ServerStartError, match="boom"):
        server.start(timeout=15)


def test_timeout_stops_process(tmp_path):
    server = fake_server(tmp_path, ready_after=100)
    with pytest.raises(ServerStartError, match="시간"):
        server.start(timeout=1.5)
    assert not server.running
```

`tests/test_llama.py`:

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
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_process.py tests/test_llama.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 4: 구현**

`src/manga_viewer/llm/__init__.py`: 빈 파일.

`src/manga_viewer/llm/process.py`:

```python
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import IO

import httpx

from ..winjob import KillOnCloseJob

_LOG_TAIL_BYTES = 2000


class ServerStartError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ManagedServer:
    """A child process that serves HTTP and is ready once ``health_url`` returns 200."""

    def __init__(
        self,
        argv: list[str],
        health_url: str,
        log_path: Path,
        job: KillOnCloseJob | None = None,
    ) -> None:
        self._argv = argv
        self._health_url = health_url
        self._log_path = log_path
        self._job = job
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, timeout: float = 180.0, poll_interval: float = 0.25) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self._log_path.open("ab")
        self._proc = subprocess.Popen(
            self._argv,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if self._job is not None:
            self._job.assign(self._proc.pid)

        deadline = time.monotonic() + timeout
        while True:
            code = self._proc.poll()
            if code is not None:
                self._close_log()
                raise ServerStartError(f"서버가 종료되었습니다 (코드 {code}):\n{self._log_tail()}")
            if self.is_healthy():
                return
            if time.monotonic() > deadline:
                self.stop()
                raise ServerStartError(f"서버 준비 대기 시간을 초과했습니다 ({timeout}s):\n{self._log_tail()}")
            time.sleep(poll_interval)

    def is_healthy(self) -> bool:
        try:
            return httpx.get(self._health_url, timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def stop(self, timeout: float = 10.0) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout)
        self._close_log()

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None

    def _log_tail(self) -> str:
        try:
            data = self._log_path.read_bytes()[-_LOG_TAIL_BYTES:]
        except OSError:
            return ""
        return data.decode("utf-8", errors="replace")
```

`src/manga_viewer/llm/llama.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..winjob import KillOnCloseJob
from .process import ManagedServer, free_port


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
    ]


def start_llama_server(
    cfg: LlamaConfig,
    log_path: Path,
    job: KillOnCloseJob | None = None,
    timeout: float = 300.0,
) -> tuple[ManagedServer, str]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = ManagedServer(build_llama_args(cfg, port), f"{base_url}/health", log_path, job)
    server.start(timeout=timeout)
    return server, base_url
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_process.py tests/test_llama.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/manga_viewer/llm tests/helpers/fake_health_server.py tests/test_process.py tests/test_llama.py
git commit -m "feat: manage llama-server child process with health checks"
```

---

### Task 6: JSON 스키마 채팅 클라이언트

**Files:**
- Create: `src/manga_viewer/llm/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Produces:
  - `class LLMError(RuntimeError)`
  - `@dataclass(frozen=True) ChatResult(content: dict, completion_tokens: int, tokens_per_second: float | None)`
  - `class ChatClient(base_url: str, *, timeout: float = 120.0, transport: httpx.BaseTransport | None = None)` with `chat_json(messages: list[dict], schema: dict, *, temperature: float = 0.3, extra_body: dict | None = None) -> ChatResult` and `close() -> None`
  - 요청은 `POST /v1/chat/completions`, `response_format = {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": schema}}` 형태다. `extra_body`는 요청 본문 최상위에 병합한다(예: `{"chat_template_kwargs": {"enable_thinking": False}}`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_client.py`:

```python
import json

import httpx
import pytest

from manga_viewer.llm.client import ChatClient, LLMError

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


def completion(content, tokens=12, tps=40.0):
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"completion_tokens": tokens},
        "timings": {"predicted_per_second": tps},
    }


def client_with(handler):
    return ChatClient("http://llm.test", transport=httpx.MockTransport(handler))


def test_sends_schema_and_parses_content():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion('{"a": 1}'))

    result = client_with(handler).chat_json(
        [{"role": "user", "content": "hi"}],
        SCHEMA,
        temperature=0.2,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    assert seen["path"] == "/v1/chat/completions"
    body = seen["body"]
    assert body["temperature"] == 0.2
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert result.content == {"a": 1}
    assert result.completion_tokens == 12
    assert result.tokens_per_second == 40.0


def test_http_error_raises_llm_error():
    client = client_with(lambda request: httpx.Response(500, text="oops"))
    with pytest.raises(LLMError):
        client.chat_json([], SCHEMA)


def test_invalid_json_raises_llm_error():
    client = client_with(lambda request: httpx.Response(200, json=completion("not json")))
    with pytest.raises(LLMError, match="JSON"):
        client.chat_json([], SCHEMA)


def test_connection_error_raises_llm_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError):
        client_with(handler).chat_json([], SCHEMA)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`src/manga_viewer/llm/client.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass

import httpx


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    content: dict
    completion_tokens: int
    tokens_per_second: float | None


class ChatClient:
    """OpenAI-compatible chat client for llama-server with schema-constrained JSON output."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = 0.3,
        extra_body: dict | None = None,
    ) -> ChatResult:
        body = {
            "model": "local",
            "messages": messages,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            },
            **(extra_body or {}),
        }
        try:
            response = self._http.post("/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM 요청 실패: {e}") from e

        try:
            content = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"LLM 응답이 JSON이 아닙니다: {text[:200]!r}") from e
        if not isinstance(content, dict):
            raise LLMError(f"LLM 응답이 JSON 객체가 아닙니다: {text[:200]!r}")

        usage = data.get("usage") or {}
        timings = data.get("timings") or {}
        return ChatResult(
            content=content,
            completion_tokens=int(usage.get("completion_tokens", 0)),
            tokens_per_second=timings.get("predicted_per_second"),
        )

    def close(self) -> None:
        self._http.close()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/llm/client.py tests/test_client.py
git commit -m "feat: add schema-constrained chat client for llama-server"
```

---

### Task 7: 페이지 번역기

**Files:**
- Create: `src/manga_viewer/translate.py`
- Test: `tests/test_translate.py`

**Interfaces:**
- Consumes: `TextBlock` (Task 1), `GlossaryEntry`, `relevant_entries` (Task 3), `ChatResult`, `LLMError` (Task 6)
- Produces:
  - `PROMPT_VERSION = 1`, `SYSTEM_PROMPT: str`, `RESPONSE_SCHEMA: dict`
  - `ContextPage = list[tuple[str, str]]`: 이전 한 페이지의 (원문, 번역) 쌍 목록
  - `build_messages(blocks: Sequence[TextBlock], context_pages: Sequence[ContextPage], glossary: Sequence[GlossaryEntry]) -> list[dict]`
  - `parse_translations(content: dict, expected_ids: set[int]) -> dict[int, str]`
  - `@dataclass(frozen=True) PageTranslation(translations: dict[int, str], failed_ids: tuple[int, ...], completion_tokens: int, tokens_per_second: float | None, elapsed_s: float)`
  - `class Translator(client, *, temperature: float = 0.3, extra_body: dict | None = None)` with `translate_page(blocks: Sequence[TextBlock], context_pages: Sequence[ContextPage] = (), glossary: Sequence[GlossaryEntry] = ()) -> PageTranslation`. `client`는 `chat_json(messages, schema, *, temperature, extra_body) -> ChatResult`를 가진 객체다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_translate.py`:

```python
import json

from manga_viewer.glossary import GlossaryEntry
from manga_viewer.llm.client import ChatResult, LLMError
from manga_viewer.translate import (
    RESPONSE_SCHEMA,
    Translator,
    build_messages,
    parse_translations,
)
from manga_viewer.types import TextBlock


def blk(i, ja):
    return TextBlock(id=i, box=(0, 0, 10, 10), vertical=True, ja=ja)


class FakeClient:
    """Returns queued results (or raises queued exceptions) and records requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat_json(self, messages, schema, *, temperature=0.3, extra_body=None):
        self.calls.append({"messages": messages, "schema": schema, "extra_body": extra_body})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResult(content=item, completion_tokens=10, tokens_per_second=35.0)

    def payload(self, call_index):
        return json.loads(self.calls[call_index]["messages"][1]["content"])


def test_build_messages_payload_keeps_japanese():
    messages = build_messages(
        [blk(0, "行くぞ")],
        [[("はい", "응")]],
        [GlossaryEntry("悟", "사토루", "주인공")],
    )
    assert messages[0]["role"] == "system"
    assert "行くぞ" in messages[1]["content"]  # ensure_ascii=False
    payload = json.loads(messages[1]["content"])
    assert payload == {
        "glossary": [{"ja": "悟", "ko": "사토루", "note": "주인공"}],
        "previous_pages": [[{"ja": "はい", "ko": "응"}]],
        "bubbles": [{"id": 0, "ja": "行くぞ"}],
    }


def test_parse_translations_ignores_bad_items():
    content = {
        "translations": [
            {"id": 0, "ko": " 가자 "},
            {"id": 0, "ko": "중복"},
            {"id": 9, "ko": "없는 id"},
            {"id": 1, "ko": ""},
            {"id": "2", "ko": "문자열 id"},
            "garbage",
        ]
    }
    assert parse_translations(content, {0, 1, 2}) == {0: "가자"}


def test_translates_all_in_one_call():
    client = FakeClient({"translations": [{"id": 0, "ko": "가자"}, {"id": 1, "ko": "응"}]})
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {0: "가자", 1: "응"}
    assert result.failed_ids == ()
    assert len(client.calls) == 1
    assert client.calls[0]["schema"] == RESPONSE_SCHEMA
    assert result.completion_tokens == 10
    assert result.tokens_per_second == 35.0


def test_missing_ids_are_retried_once_with_only_missing_bubbles():
    client = FakeClient(
        {"translations": [{"id": 0, "ko": "가자"}]},
        {"translations": [{"id": 1, "ko": "응"}]},
    )
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {0: "가자", 1: "응"}
    assert client.payload(1)["bubbles"] == [{"id": 1, "ja": "うん"}]
    assert result.completion_tokens == 20


def test_still_missing_after_retry_is_reported():
    client = FakeClient(
        {"translations": [{"id": 0, "ko": "가자"}]},
        {"translations": []},
    )
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {0: "가자"}
    assert result.failed_ids == (1,)


def test_llm_error_is_retried_once():
    client = FakeClient(LLMError("down"), {"translations": [{"id": 0, "ko": "가자"}]})
    result = Translator(client).translate_page([blk(0, "行くぞ")])
    assert result.translations == {0: "가자"}


def test_two_llm_errors_fail_every_bubble():
    client = FakeClient(LLMError("down"), LLMError("down"))
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {}
    assert result.failed_ids == (0, 1)


def test_empty_page_makes_no_call():
    client = FakeClient()
    result = Translator(client).translate_page([])
    assert result.translations == {}
    assert client.calls == []


def test_only_relevant_glossary_and_extra_body_are_sent():
    client = FakeClient({"translations": [{"id": 0, "ko": "사토루, 가자"}]})
    translator = Translator(client, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    translator.translate_page(
        [blk(0, "悟、行くぞ")],
        glossary=[GlossaryEntry("悟", "사토루"), GlossaryEntry("呪術", "주술")],
    )
    assert client.payload(0)["glossary"] == [{"ja": "悟", "ko": "사토루", "note": ""}]
    assert client.calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_translate.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`src/manga_viewer/translate.py`:

```python
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

from .glossary import GlossaryEntry, relevant_entries
from .llm.client import ChatResult, LLMError
from .types import TextBlock

PROMPT_VERSION = 1

SYSTEM_PROMPT = """You translate Japanese manga dialogue into natural Korean.
Rules:
- Translate every item in "bubbles" and return exactly one translation per id.
- The bubbles are one page in reading order. Use them and "previous_pages" as context; Japanese often omits the subject.
- Keep each character's speech level (반말/존댓말) consistent with previous pages.
- Write natural spoken Korean, not a literal translation. Keep it short enough to fit in a speech bubble.
- Translate sound effects briefly as Korean onomatopoeia.
- Always use the "glossary" translation for listed terms.
- Output only the JSON object."""

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"id": {"type": "integer"}, "ko": {"type": "string"}},
                "required": ["id", "ko"],
            },
        }
    },
    "required": ["translations"],
}

MAX_ATTEMPTS = 2  # first request + one retry for missing ids or LLM errors

ContextPage = list[tuple[str, str]]


class ChatJsonClient(Protocol):
    def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = ...,
        extra_body: dict | None = ...,
    ) -> ChatResult: ...


@dataclass(frozen=True)
class PageTranslation:
    translations: dict[int, str]
    failed_ids: tuple[int, ...]
    completion_tokens: int
    tokens_per_second: float | None
    elapsed_s: float


def build_messages(
    blocks: Sequence[TextBlock],
    context_pages: Sequence[ContextPage],
    glossary: Sequence[GlossaryEntry],
) -> list[dict]:
    payload = {
        "glossary": [{"ja": e.ja, "ko": e.ko, "note": e.note} for e in glossary],
        "previous_pages": [[{"ja": ja, "ko": ko} for ja, ko in page] for page in context_pages],
        "bubbles": [{"id": b.id, "ja": b.ja} for b in blocks],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def parse_translations(content: dict, expected_ids: set[int]) -> dict[int, str]:
    result: dict[int, str] = {}
    for item in content.get("translations", []):
        if not isinstance(item, dict):
            continue
        block_id, ko = item.get("id"), item.get("ko")
        if isinstance(block_id, int) and block_id in expected_ids and isinstance(ko, str) and ko.strip():
            result.setdefault(block_id, ko.strip())
    return result


class Translator:
    def __init__(
        self,
        client: ChatJsonClient,
        *,
        temperature: float = 0.3,
        extra_body: dict | None = None,
    ) -> None:
        self._client = client
        self._temperature = temperature
        self._extra_body = extra_body

    def translate_page(
        self,
        blocks: Sequence[TextBlock],
        context_pages: Sequence[ContextPage] = (),
        glossary: Sequence[GlossaryEntry] = (),
    ) -> PageTranslation:
        start = time.perf_counter()
        translations: dict[int, str] = {}
        tokens = 0
        tokens_per_second: float | None = None
        pending = list(blocks)
        relevant = relevant_entries(glossary, [b.ja for b in blocks])

        for _ in range(MAX_ATTEMPTS):
            if not pending:
                break
            try:
                result = self._client.chat_json(
                    build_messages(pending, context_pages, relevant),
                    RESPONSE_SCHEMA,
                    temperature=self._temperature,
                    extra_body=self._extra_body,
                )
            except LLMError:
                continue
            tokens += result.completion_tokens
            tokens_per_second = result.tokens_per_second or tokens_per_second
            translations.update(parse_translations(result.content, {b.id for b in pending}))
            pending = [b for b in blocks if b.id not in translations]

        return PageTranslation(
            translations=translations,
            failed_ids=tuple(b.id for b in blocks if b.id not in translations),
            completion_tokens=tokens,
            tokens_per_second=tokens_per_second,
            elapsed_s=time.perf_counter() - start,
        )
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_translate.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/translate.py tests/test_translate.py
git commit -m "feat: add page translator with glossary, context and retry"
```

---

### Task 8: 비전 파이프라인(mokuro 어댑터)

**Files:**
- Create: `src/manga_viewer/vision.py`
- Test: `tests/test_vision.py`

**Interfaces:**
- Consumes: `TextBlock`, `PageAnalysis` (Task 1), `sort_reading_order` (Task 1), `border_median_color` (Task 2)
- Produces:
  - `page_from_mokuro(result: dict, image: np.ndarray) -> PageAnalysis`: mokuro 결과(`img_width`, `img_height`, `blocks[].box/vertical/lines`)를 변환한다. `lines`를 이어 붙인 텍스트가 비어 있는 블록은 버리고, 결과는 읽기 순서로 정렬한다.
  - `class Vision(*, force_cpu: bool = False)` with `analyze(image_path: Path) -> PageAnalysis`. mokuro와 torch는 생성자 안에서만 import한다.

mokuro 참고: `MangaPageOcr(force_cpu=False)`는 CUDA가 있으면 자동으로 GPU를 쓴다. `__call__(img_path)`는 PIL로 이미지를 열기 때문에 한글·일본어 경로도 처리된다. 반환 블록의 `box`는 `[x1, y1, x2, y2]`이고, 값이 float일 수 있어 반올림한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_vision.py`:

```python
from pathlib import Path

import numpy as np
import pytest

from manga_viewer.vision import page_from_mokuro

FONT = Path("C:/Windows/Fonts/msgothic.ttc")


def test_page_from_mokuro_converts_orders_and_filters():
    image = np.full((200, 400, 3), 255, dtype=np.uint8)
    result = {
        "img_width": 400,
        "img_height": 200,
        "blocks": [
            {"box": [10.4, 10, 100, 90], "vertical": True, "lines": ["左", "です"]},
            {"box": [300, 12, 390, 88.6], "vertical": True, "lines": ["右"]},
            {"box": [150, 120, 250, 190], "vertical": False, "lines": ["", "  "]},
        ],
    }
    page = page_from_mokuro(result, image)

    assert (page.width, page.height) == (400, 200)
    assert [b.ja for b in page.blocks] == ["右", "左です"]
    assert [b.id for b in page.blocks] == [0, 1]
    assert page.blocks[1].box == (10, 10, 100, 90)
    assert page.blocks[0].box == (300, 12, 390, 89)
    assert page.blocks[0].vertical is True
    assert page.blocks[0].bg_color == (255, 255, 255)


@pytest.mark.gpu
def test_vision_reads_rendered_japanese(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("mokuro")
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")
    if not FONT.exists():
        pytest.skip("MS Gothic font not found")
    from PIL import Image, ImageDraw, ImageFont

    from manga_viewer.vision import Vision

    img = Image.new("RGB", (900, 300), "white")
    ImageDraw.Draw(img).text((40, 110), "今日はいい天気ですね", font=ImageFont.truetype(str(FONT), 64), fill="black")
    path = tmp_path / "ページ.png"  # non-ASCII path on purpose
    img.save(path)

    page = Vision().analyze(path)

    assert page.blocks, "no text detected"
    assert "天気" in "".join(b.ja for b in page.blocks)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vision.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_viewer.vision'`

- [ ] **Step 3: 구현**

`src/manga_viewer/vision.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .background import border_median_color
from .order import sort_reading_order
from .types import PageAnalysis, TextBlock


def page_from_mokuro(result: dict, image: np.ndarray) -> PageAnalysis:
    blocks: list[TextBlock] = []
    for raw in result.get("blocks", []):
        text = "".join(raw.get("lines", [])).strip()
        if not text:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in raw["box"])
        box = (x1, y1, x2, y2)
        blocks.append(
            TextBlock(
                id=len(blocks),
                box=box,
                vertical=bool(raw.get("vertical", False)),
                ja=text,
                bg_color=border_median_color(image, box),
            )
        )
    return PageAnalysis(
        width=int(result["img_width"]),
        height=int(result["img_height"]),
        blocks=tuple(sort_reading_order(blocks)),
    )


class Vision:
    """Text detection + OCR on the GPU via mokuro (comic-text-detector + manga-ocr)."""

    def __init__(self, *, force_cpu: bool = False) -> None:
        from mokuro.manga_page_ocr import MangaPageOcr  # heavy: imports torch

        self._ocr = MangaPageOcr(force_cpu=force_cpu)

    def analyze(self, image_path: Path) -> PageAnalysis:
        result = self._ocr(str(image_path))
        with Image.open(image_path) as img:
            image = np.asarray(img.convert("RGB"))
        return page_from_mokuro(result, image)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_vision.py -v`
Expected: 2 passed. 처음 실행하면 mokuro가 검출 모델과 manga-ocr 모델(약 500MB)을 내려받는다.

GPU 테스트가 검출 실패로 떨어지면 폰트 크기를 80으로 키워서 다시 실행한다. 그래도 실패하면 mokuro 결과를 출력해 원인을 확인하고, 테스트 조건을 완화하지 말고 보고한다.

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/vision.py tests/test_vision.py
git commit -m "feat: add mokuro-based text detection and OCR adapter"
```

---

### Task 9: bench 실행 루프, 리포트, CLI

**Files:**
- Create: `src/manga_viewer/bench.py`, `src/manga_viewer/cli.py`
- Test: `tests/test_bench.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `PageAnalysis` (Task 1), `list_images` (Task 3), `load_glossary`, `GlossaryEntry` (Task 3), `KillOnCloseJob` (Task 4), `LlamaConfig`, `start_llama_server` (Task 5), `ChatClient` (Task 6), `Translator`, `PageTranslation`, `ContextPage` (Task 7), `Vision` (Task 8)
- Produces:
  - `CONTEXT_PAGES = 2`
  - `@dataclass(frozen=True) PageResult(image_path: Path, analysis: PageAnalysis, translation: PageTranslation, vision_s: float)`
  - `@dataclass(frozen=True) BenchMeta(model_id: str, folder: Path)`
  - `run_bench(image_paths, vision, translator, glossary, on_page=None) -> list[PageResult]`: `vision`은 `analyze(Path) -> PageAnalysis`, `translator`는 `translate_page(...)`를 가진 객체다.
  - `summarize(results) -> dict` (키: `pages`, `bubbles`, `failed_bubbles`, `avg_vision_s`, `avg_llm_s`, `avg_tokens_per_second`)
  - `render_report(results, meta) -> str`
  - `write_outputs(results, meta, out_dir: Path) -> Path` (`report.html`, `results.json`을 쓰고 html 경로를 반환)
  - `cli.main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_bench.py`:

```python
import json
from pathlib import Path

from manga_viewer.bench import BenchMeta, render_report, run_bench, summarize, write_outputs
from manga_viewer.glossary import GlossaryEntry
from manga_viewer.translate import PageTranslation
from manga_viewer.types import PageAnalysis, TextBlock


def page(*texts):
    return PageAnalysis(
        width=100,
        height=100,
        blocks=tuple(TextBlock(id=i, box=(0, 0, 10, 10), vertical=True, ja=t) for i, t in enumerate(texts)),
    )


class FakeVision:
    def __init__(self, pages):
        self.pages = pages

    def analyze(self, path):
        return self.pages[Path(path).name]


class FakeTranslator:
    def __init__(self):
        self.calls = []

    def translate_page(self, blocks, context_pages=(), glossary=()):
        self.calls.append({"context": list(context_pages), "glossary": list(glossary)})
        translations = {b.id: f"ko:{b.ja}" for b in blocks if b.ja != "fail"}
        failed = tuple(b.id for b in blocks if b.ja == "fail")
        return PageTranslation(translations, failed, 5, 30.0, 1.5)


def test_run_bench_passes_last_two_pages_as_context():
    vision = FakeVision({"1.png": page("a"), "2.png": page("b"), "3.png": page("c", "fail"), "4.png": page("d")})
    translator = FakeTranslator()
    glossary = [GlossaryEntry("a", "에이")]
    seen = []

    results = run_bench(
        [Path("1.png"), Path("2.png"), Path("3.png"), Path("4.png")],
        vision,
        translator,
        glossary,
        on_page=seen.append,
    )

    assert len(results) == 4 and seen == results
    assert translator.calls[0]["context"] == []
    assert translator.calls[2]["context"] == [[("a", "ko:a")], [("b", "ko:b")]]
    # failed bubbles are left out of later context
    assert translator.calls[3]["context"] == [[("b", "ko:b")], [("c", "ko:c")]]
    assert translator.calls[0]["glossary"] == glossary


def test_summarize():
    vision = FakeVision({"1.png": page("a", "fail"), "2.png": page()})
    results = run_bench([Path("1.png"), Path("2.png")], vision, FakeTranslator(), [])
    summary = summarize(results)
    assert summary["pages"] == 2
    assert summary["bubbles"] == 2
    assert summary["failed_bubbles"] == 1
    assert summary["avg_llm_s"] == 1.5
    assert summary["avg_tokens_per_second"] == 30.0


def test_report_escapes_html(tmp_path):
    vision = FakeVision({"1.png": page("<script>x</script>")})
    results = run_bench([tmp_path / "1.png"], vision, FakeTranslator(), [])
    html = render_report(results, BenchMeta(model_id="m<1>", folder=tmp_path))
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html
    assert "m&lt;1&gt;" in html


def test_write_outputs(tmp_path):
    vision = FakeVision({"1.png": page("a")})
    results = run_bench([tmp_path / "1.png"], vision, FakeTranslator(), [])
    html_path = write_outputs(results, BenchMeta(model_id="m", folder=tmp_path), tmp_path / "out")
    assert html_path == tmp_path / "out" / "report.html"
    data = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert data["meta"]["model_id"] == "m"
    assert data["summary"]["pages"] == 1
    assert data["pages"][0]["bubbles"] == [{"id": 0, "box": [0, 0, 10, 10], "ja": "a", "ko": "ko:a"}]
```

`tests/test_cli.py`:

```python
import pytest

from manga_viewer.cli import main


def test_bench_requires_llama_server_and_model(tmp_path):
    with pytest.raises(SystemExit):
        main(["bench", str(tmp_path)])


def test_bench_with_empty_folder_returns_error(tmp_path, capsys):
    code = main(["bench", str(tmp_path), "--llama-server", "x.exe", "--model", "m.gguf"])
    assert code == 2
    assert "이미지가 없습니다" in capsys.readouterr().out
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_bench.py tests/test_cli.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: `bench.py` 구현**

```python
from __future__ import annotations

import html
import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable, Protocol, Sequence

from .glossary import GlossaryEntry
from .translate import ContextPage, PageTranslation
from .types import PageAnalysis, TextBlock

CONTEXT_PAGES = 2


class PageVision(Protocol):
    def analyze(self, image_path: Path) -> PageAnalysis: ...


class PageTranslator(Protocol):
    def translate_page(
        self,
        blocks: Sequence[TextBlock],
        context_pages: Sequence[ContextPage] = ...,
        glossary: Sequence[GlossaryEntry] = ...,
    ) -> PageTranslation: ...


@dataclass(frozen=True)
class PageResult:
    image_path: Path
    analysis: PageAnalysis
    translation: PageTranslation
    vision_s: float


@dataclass(frozen=True)
class BenchMeta:
    model_id: str
    folder: Path


def run_bench(
    image_paths: Iterable[Path],
    vision: PageVision,
    translator: PageTranslator,
    glossary: Sequence[GlossaryEntry],
    on_page: Callable[[PageResult], None] | None = None,
) -> list[PageResult]:
    results: list[PageResult] = []
    context: deque[ContextPage] = deque(maxlen=CONTEXT_PAGES)
    for path in image_paths:
        start = time.perf_counter()
        analysis = vision.analyze(path)
        vision_s = time.perf_counter() - start

        translation = translator.translate_page(analysis.blocks, list(context), glossary)
        context.append(
            [(b.ja, translation.translations[b.id]) for b in analysis.blocks if b.id in translation.translations]
        )

        result = PageResult(path, analysis, translation, vision_s)
        results.append(result)
        if on_page is not None:
            on_page(result)
    return results


def summarize(results: Sequence[PageResult]) -> dict:
    speeds = [r.translation.tokens_per_second for r in results if r.translation.tokens_per_second]
    return {
        "pages": len(results),
        "bubbles": sum(len(r.analysis.blocks) for r in results),
        "failed_bubbles": sum(len(r.translation.failed_ids) for r in results),
        "avg_vision_s": round(mean(r.vision_s for r in results), 3) if results else 0.0,
        "avg_llm_s": round(mean(r.translation.elapsed_s for r in results), 3) if results else 0.0,
        "avg_tokens_per_second": round(mean(speeds), 1) if speeds else None,
    }


def _page_json(result: PageResult) -> dict:
    return {
        "image": str(result.image_path),
        "vision_s": round(result.vision_s, 3),
        "llm_s": round(result.translation.elapsed_s, 3),
        "tokens_per_second": result.translation.tokens_per_second,
        "bubbles": [
            {"id": b.id, "box": list(b.box), "ja": b.ja, "ko": result.translation.translations.get(b.id)}
            for b in result.analysis.blocks
        ],
    }


def render_report(results: Sequence[PageResult], meta: BenchMeta) -> str:
    esc = html.escape
    summary = summarize(results)
    parts = [
        "<!doctype html><html lang='ko'><meta charset='utf-8'>",
        f"<title>bench: {esc(meta.model_id)}</title>",
        "<style>body{font-family:sans-serif;margin:24px}section{display:flex;gap:24px;margin:32px 0}"
        "img{max-width:480px;border:1px solid #ccc}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:4px 8px;vertical-align:top}.fail{background:#fdd}</style>",
        f"<h1>{esc(meta.model_id)}</h1>",
        f"<p>{esc(str(meta.folder))}</p>",
        "<table>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>" for k, v in summary.items()) + "</table>",
    ]
    for r in results:
        rows = []
        for b in r.analysis.blocks:
            ko = r.translation.translations.get(b.id)
            cls = "" if ko is not None else " class='fail'"
            rows.append(f"<tr{cls}><td>{b.id}</td><td>{esc(b.ja)}</td><td>{esc(ko or '(실패)')}</td></tr>")
        parts.append(
            "<section>"
            f"<img src='{esc(r.image_path.resolve().as_uri())}' loading='lazy'>"
            f"<div><h2>{esc(r.image_path.name)}</h2>"
            f"<p>비전 {r.vision_s:.2f}s · LLM {r.translation.elapsed_s:.2f}s</p>"
            "<table><tr><th>#</th><th>원문</th><th>번역</th></tr>" + "".join(rows) + "</table></div>"
            "</section>"
        )
    parts.append("</html>")
    return "\n".join(parts)


def write_outputs(results: Sequence[PageResult], meta: BenchMeta, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"model_id": meta.model_id, "folder": str(meta.folder)},
        "summary": summarize(results),
        "pages": [_page_json(r) for r in results],
    }
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = out_dir / "report.html"
    html_path.write_text(render_report(results, meta), encoding="utf-8")
    return html_path
```

- [ ] **Step 4: `cli.py` 구현**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .bench import BenchMeta, PageResult, run_bench, summarize, write_outputs
from .glossary import load_glossary
from .source import list_images


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manga-viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="이미지 폴더를 번역하고 속도와 결과를 리포트로 저장")
    bench.add_argument("folder", type=Path, help="만화 이미지 폴더")
    bench.add_argument("--llama-server", type=Path, required=True, help="llama-server.exe 경로")
    bench.add_argument("--model", type=Path, required=True, help="GGUF 모델 경로")
    bench.add_argument("--model-id", help="리포트에 표시할 모델 이름 (기본: 파일 이름)")
    bench.add_argument("--glossary", type=Path, help="용어집 TOML")
    bench.add_argument("--limit", type=int, help="앞에서부터 N장만 처리")
    bench.add_argument("--out", type=Path, default=Path("bench-out"), help="결과 폴더")
    bench.add_argument("--ctx-size", type=int, default=8192, help="LLM 컨텍스트 길이")
    bench.add_argument("--no-think", action="store_true", help="Qwen3 같은 추론 모델의 thinking 끄기")

    args = parser.parse_args(argv)
    return _run_bench(args)


def _run_bench(args: argparse.Namespace) -> int:
    images = list_images(args.folder)[: args.limit]
    if not images:
        print(f"이미지가 없습니다: {args.folder}")
        return 2
    glossary = load_glossary(args.glossary) if args.glossary else []

    # Heavy imports only when actually running.
    from .llm.client import ChatClient
    from .llm.llama import LlamaConfig, start_llama_server
    from .translate import Translator
    from .vision import Vision
    from .winjob import KillOnCloseJob

    args.out.mkdir(parents=True, exist_ok=True)
    job = KillOnCloseJob()
    print("LLM 서버를 시작하는 중...")
    server, base_url = start_llama_server(
        LlamaConfig(exe=args.llama_server, model=args.model, ctx_size=args.ctx_size),
        args.out / "llama-server.log",
        job=job,
    )
    try:
        print("비전 모델을 불러오는 중...")
        vision = Vision()
        client = ChatClient(base_url)
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if args.no_think else None
        translator = Translator(client, extra_body=extra)

        def report(r: PageResult) -> None:
            print(
                f"{r.image_path.name}: 말풍선 {len(r.analysis.blocks)}개, "
                f"비전 {r.vision_s:.2f}s, LLM {r.translation.elapsed_s:.2f}s, "
                f"실패 {len(r.translation.failed_ids)}개"
            )

        results = run_bench(images, vision, translator, glossary, on_page=report)
        client.close()
    finally:
        server.stop()
        job.close()

    html_path = write_outputs(results, BenchMeta(model_id=args.model_id or args.model.stem, folder=args.folder), args.out)
    for key, value in summarize(results).items():
        print(f"{key}: {value}")
    print(f"리포트: {html_path}")
    return 0
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_bench.py tests/test_cli.py -v`
Expected: 6 passed

Run: `uv run pytest -v -m "not gpu"`
Expected: GPU 테스트를 제외한 모든 테스트 통과

- [ ] **Step 6: Commit**

```bash
git add src/manga_viewer/bench.py src/manga_viewer/cli.py tests/test_bench.py tests/test_cli.py
git commit -m "feat: add bench command with HTML and JSON reports"
```

---

### Task 10: 실제 모델 벤치마크와 기본 모델 결정

이 태스크는 코드가 아니라 **실측과 사람의 판단**이다. 다운로드 용량이 크므로(모델당 7~9GB) 실행하는 사람이 사용자에게 먼저 확인받는다.

**Files:**
- Create: `docs/superpowers/notes/model-benchmark.md`

**Interfaces:**
- Consumes: `manga-viewer bench` (Task 9)
- Produces: 기본 모델 id와 그 근거. 계획 3의 `manifest.toml`이 이 결과를 사용한다.

- [ ] **Step 1: 최신 후보 확인**

Hugging Face에서 12~14B급 다국어 instruct 모델 중 한국어·일본어 품질이 좋다고 알려진 최신 모델이 Gemma 3 12B나 Qwen3 14B보다 나은지 확인한다. 더 나은 후보가 있으면 사용자에게 알리고 비교 대상에 추가할지 묻는다.

- [ ] **Step 2: llama.cpp CUDA 빌드 받기**

```powershell
gh release view --repo ggml-org/llama.cpp --json tagName,assets --jq '.tagName, (.assets[].name | select(test("win-cuda")))'
```

출력에서 **하나의 CUDA 버전**을 골라, 그 버전의 `llama-*-bin-win-cuda-<ver>-x64.zip`과 `cudart-llama-bin-win-cuda-<ver>-x64.zip`을 받는다. `<ver>`는 출력에 있는 값(예: `12.4`)으로 바꾼다.

```powershell
New-Item -ItemType Directory -Force .dev\llama | Out-Null
gh release download --repo ggml-org/llama.cpp --pattern "llama-*-bin-win-cuda-<ver>-x64.zip" --pattern "cudart-llama-bin-win-cuda-<ver>-x64.zip" --dir .dev --clobber
Get-ChildItem .dev\*.zip | ForEach-Object { Expand-Archive $_.FullName -DestinationPath .dev\llama -Force }
.dev\llama\llama-server.exe --version
```

Expected: 버전 정보와 CUDA 장치(`NVIDIA GeForce ...`)가 출력된다.

- [ ] **Step 3: 모델 받기**

```powershell
uvx --from huggingface_hub hf download bartowski/google_gemma-3-12b-it-GGUF google_gemma-3-12b-it-Q4_K_M.gguf --local-dir .dev\models
uvx --from huggingface_hub hf download Qwen/Qwen3-14B-GGUF Qwen3-14B-Q4_K_M.gguf --local-dir .dev\models
```

- [ ] **Step 4: 샘플 준비**

사용자에게 대사가 많은 일본 만화 페이지 10~20장을 `.dev\samples\<작품명>\`에 넣어 달라고 요청한다. 커밋하지 않는다.

- [ ] **Step 5: 두 모델로 bench 실행**

```powershell
uv run manga-viewer bench .dev\samples\<작품명> --llama-server .dev\llama\llama-server.exe --model .dev\models\google_gemma-3-12b-it-Q4_K_M.gguf --out bench-out\gemma3-12b
uv run manga-viewer bench .dev\samples\<작품명> --llama-server .dev\llama\llama-server.exe --model .dev\models\Qwen3-14B-Q4_K_M.gguf --no-think --out bench-out\qwen3-14b
```

Qwen3 14B가 VRAM 부족으로 기동에 실패하면 `--ctx-size 4096`으로 다시 실행하고, 그 사실을 기록한다. 실행 중 `nvidia-smi`로 최대 VRAM 사용량을 기록한다.

- [ ] **Step 6: 결과 기록과 결정**

두 `report.html`을 사용자에게 보여주고, 번역 품질(말투, 자연스러움, 오역)을 사용자가 판단하게 한다. 그 결과를 `docs/superpowers/notes/model-benchmark.md`에 아래 형식으로 기록한다.

```markdown
# 번역 모델 벤치마크 (YYYY-MM-DD)

- GPU: <이름, VRAM>
- 샘플: <작품명>, <N>장, 말풍선 <M>개

| 모델 | 평균 비전(s) | 평균 LLM(s/페이지) | tok/s | 실패 말풍선 | 최대 VRAM | ctx |
|---|---|---|---|---|---|---|
| gemma-3-12b Q4_K_M | | | | | | |
| qwen3-14b Q4_K_M | | | | | | |

## 품질 메모
- <사용자 평가 요약>

## 결정
- 기본 모델: <모델 id>
- 이유: <한두 줄>
```

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/notes/model-benchmark.md
git commit -m "docs: record translation model benchmark and default choice"
```

---

## 이후 계획

- **계획 2: 뷰어.** ZIP/CBZ 읽기와 경로 검증, SQLite 캐시, 스케줄러(우선순위, 프리페치, 취소, 2단계 병행, llama-server 재시작), FastAPI 서버와 WebSocket, 웹 UI(라이브러리, 읽기, 오버레이, 용어집 편집), `--browser` 실행 모드를 만든다.
- **계획 3: 일반인 배포.** 환경 검사, `manifest.toml`과 다운로드·이어받기, 첫 실행 마법사, pywebview 앱(단일 인스턴스, 세션 토큰), 설정 화면, 새 버전 알림, 포터블 Python 빌드 스크립트와 Inno Setup 설치 파일을 만든다.
