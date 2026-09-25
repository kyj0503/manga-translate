# 실시간 오버레이 번역 뷰어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tkinter 배치 번역 앱을, 만화 페이지를 한 장씩 보여주며 로컬 GPU로 실시간 번역해 HTML 오버레이로 겹쳐 보여주는 pywebview 뷰어 앱으로 교체한다.

**Architecture:** 앱 프로세스가 127.0.0.1 HTTP 서버와 pywebview 창을 띄운다. 엔진 venv 안의 상주 워커(`bt_worker.py`)가 검출(ctd)과 OCR(manga_ocr)을 하고, 앱이 llama-server에 JSON 스키마로 번역을 직접 요청한다. 우선순위 스케줄러가 현재 페이지 → 다음 3장 → 이전 1장을 처리하고, 결과를 프로그램 폴더 `cache\`에 저장한다.

**Tech Stack:** Python 3.12, httpx, natsort, pywebview(WebView2), 표준 라이브러리 `http.server`, 순수 HTML/CSS/JS, pytest

**Spec:** `docs/superpowers/specs/2026-09-26-web-viewer-design.md`

## Global Constraints

- 저장소: `C:\Users\serial\source\manga-translate`, 브랜치 `main`. 커밋 작성자는 저장소 로컬 설정(`heroria0503@gmail.com`)을 그대로 쓰고 `--author`를 넘기지 않는다. 커밋 메시지에 `Co-Authored-By` 트레일러를 붙이지 않는다. 커밋 메시지는 `-F <파일>`로 넘긴다(제목, 빈 줄, 본문).
- 줄바꿈은 LF. 파이썬으로 파일을 쓰면 CRLF가 될 수 있으니 커밋 전에 `git diff --check`와 `file <경로>`로 확인한다.
- 테스트: `uv run pytest`가 모두 통과해야 한다. GPU를 쓰는 테스트는 만들지 않는다.
- 빌드, 실행, 테스트는 이 PC에서 직접 한다. WSL이나 Docker는 쓰지 않는다.
- 프로그램이 만드는 파일(엔진, llama.cpp, 모델, 설정, 캐시, 로그, uv 캐시)은 모두 프로그램 폴더 안에만 둔다.
- 뷰어 앱만 유지한다. CLI를 추가하지 않는다.
- 주석에는 코드가 하는 일을 쓴다. 변경 이력("X를 제거했다")은 쓰지 않는다.
- 앱 코드(`manga_translate`)는 `torch`나 `ballontranslator`를 import하지 않는다. 엔진 모듈은 엔진 venv에서 도는 `scripts/bt_worker.py`만 import한다.
- 실제 이미지로 하는 확인은 `C:\Users\serial\Downloads\(페그오` 폴더만 쓴다. 다른 이미지 폴더(설정 파일이나 로그에 적힌 경로 포함)는 열거나 읽지 않는다.
- 실험 결과와 샘플 이미지는 git으로 추적하지 않는다.
- 소스를 바꾼 작업은 마지막에 `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`로 프로그램 폴더를 새로 빌드하고, `diff -rq src/manga_translate "$USERPROFILE/Downloads/manga-translate/.venv/Lib/site-packages/manga_translate" -x __pycache__`로 같은지 확인한다. 이 계획에서는 Task 10에서 한 번 빌드한다(Task 1~9는 기존 앱을 깨지 않는 추가 작업이고, 새 앱은 Task 9에서 처음 실행 가능해진다). 번역 엔진이 실행 중이면 끝난 뒤에 빌드한다.

## File Structure

| 파일 | 책임 | 작업 |
|---|---|---|
| `src/manga_translate/paths.py` | `cache_dir`, `logs_dir` 추가 | Task 1 |
| `src/manga_translate/settings.py` | `last_library`, `page_direction`, `positions` 추가, 타입 검사 로드 | Task 1, 10 |
| `src/manga_translate/library.py` | 폴더 → 책 목록, 경로 안쪽 검사 | Task 2 |
| `src/manga_translate/page.py` | `Block`, `PageResult` (JSON 변환) | Task 3 |
| `src/manga_translate/cache.py` | `TranslationCache` | Task 3 |
| `src/manga_translate/translate.py` | llama-server 번역 요청 | Task 4 |
| `src/manga_translate/scripts/bt_worker.py` | 엔진 venv에서 도는 검출 + OCR 워커 | Task 5 |
| `src/manga_translate/worker_client.py` | 워커 프로세스 관리와 요청 | Task 5 |
| `src/manga_translate/scheduler.py` | `process_page`, `Scheduler` | Task 6 |
| `src/manga_translate/server.py` | HTTP 서버, 토큰, 라우팅, 정적 파일 | Task 7 |
| `src/manga_translate/app.py` | `AppState`, `Runtime`, 라우트, 창(`main`) | Task 8, 9 |
| `src/manga_translate/web/{index.html,app.js,style.css}` | 설치·책장·뷰어 화면 | Task 9 |
| `src/manga_translate/engine.py` | `run_streaming` 이동 | Task 10 |
| `gui.py`, `pipeline.py`, `engine_run.py`, `scripts/bt_write_config.py` | 삭제 | Task 10 |

---

### Task 1: 경로와 설정

**Files:**
- Modify: `src/manga_translate/paths.py` (`AppLayout`에 속성 두 개)
- Modify: `src/manga_translate/settings.py` (전체)
- Modify: `.gitignore`
- Test: `tests/test_paths.py`, `tests/test_settings.py`

**Interfaces:**
- Produces: `AppLayout.cache_dir -> Path` (`root / "cache"`), `AppLayout.logs_dir -> Path` (`root / "logs"`)
- Produces: `Settings(model: str = "", last_input: str = "", last_output: str = "", last_library: str = "", page_direction: str = "rtl", positions: dict[str, int] = {})`. `last_input`, `last_output`은 Task 10에서 지운다(그 전까지 `gui.py`가 쓴다). `load_settings(path) -> Settings`, `save_settings(settings, path) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_paths.py`의 `test_layout` 끝에 추가:

```python
    assert layout.cache_dir == tmp_path / "cache"
    assert layout.logs_dir == tmp_path / "logs"
```

`tests/test_settings.py` 전체를 다음으로 교체:

```python
import json

from manga_translate.settings import Settings, load_settings, save_settings


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(
        model="C:/모델.gguf",
        last_library="D:/만화",
        page_direction="ltr",
        positions={"D:/만화/1권": 12},
    )
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert "모델" in path.read_text(encoding="utf-8")


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_settings(bad) == Settings()
    not_object = tmp_path / "list.json"
    not_object.write_text("[1, 2]", encoding="utf-8")
    assert load_settings(not_object) == Settings()


def test_old_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"model": "m.gguf", "llama_server": "x", "engine_dir": "y", "uv": "z"}), encoding="utf-8")
    assert load_settings(path) == Settings(model="m.gguf")


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "model": 3,
                "page_direction": "up",
                "positions": {"a": 2, "b": -1, "c": "x", "d": True},
            }
        ),
        encoding="utf-8",
    )
    assert load_settings(path) == Settings(positions={"a": 2})
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_paths.py tests/test_settings.py -v`
Expected: FAIL (`AttributeError: 'AppLayout' object has no attribute 'cache_dir'`, `TypeError: Settings.__init__() got an unexpected keyword argument 'last_library'`)

- [ ] **Step 3: 구현**

`src/manga_translate/paths.py`의 `work_dir` 속성 아래에 추가:

```python
    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"
```

`src/manga_translate/settings.py` 전체:

```python
"""Choices remembered between runs."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

PAGE_DIRECTIONS = ("rtl", "ltr")  # rtl: the next page is to the left (Japanese order)


@dataclass
class Settings:
    model: str = ""  # a GGUF the user picked; empty means the installed default model
    last_input: str = ""
    last_output: str = ""
    last_library: str = ""
    page_direction: str = "rtl"
    positions: dict[str, int] = field(default_factory=dict)  # book folder -> last page index


def load_settings(path: Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    settings = Settings()
    for name in ("model", "last_input", "last_output", "last_library"):
        value = data.get(name)
        if isinstance(value, str):
            setattr(settings, name, value)
    if data.get("page_direction") in PAGE_DIRECTIONS:
        settings.page_direction = data["page_direction"]
    positions = data.get("positions")
    if isinstance(positions, dict):
        settings.positions = {
            key: value
            for key, value in positions.items()
            if isinstance(key, str) and type(value) is int and value >= 0
        }
    return settings


def save_settings(settings: Settings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
```

`.gitignore`의 `/work/` 줄 아래에 추가:

```
/cache/
/logs/
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q`
Expected: 모두 PASS (기존 `test_gui.py`도 통과. `Settings`의 기존 필드를 유지했으므로)

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/paths.py src/manga_translate/settings.py .gitignore tests/test_paths.py tests/test_settings.py
git commit -F <메시지 파일>   # 제목: Add cache/logs folders and viewer settings
```

---

### Task 2: 책장 (폴더 → 책 목록)

**Files:**
- Create: `src/manga_translate/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: `manga_translate.source.find_images(root: Path) -> list[Path]` (재귀, 자연 정렬, 점으로 시작하는 폴더 제외)
- Produces:
  - `Book(id: int, title: str, dir: Path, pages: tuple[Path, ...])` (frozen dataclass)
  - `scan_library(root: Path) -> list[Book]`: 이미지가 직접 들어 있는 폴더 하나가 책 한 권. `id`는 목록 순서(0부터). `title`은 `root` 기준 상대 경로(POSIX 표기), 루트 자신이면 `root.name`(빈 문자열이면 `str(root)`)
  - `is_inside(root: Path, path: Path) -> bool`: `path.resolve()`가 `root.resolve()` 아래(같음 포함)인지

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_library.py`:

```python
from pathlib import Path

from manga_translate.library import Book, is_inside, scan_library


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_each_folder_with_images_is_a_book(tmp_path):
    root = tmp_path / "만화"
    touch(root / "표지.png")
    touch(root / "1권" / "2.webp")
    touch(root / "1권" / "10.webp")
    touch(root / "1권" / "메모.txt")
    touch(root / "2권" / "001.jpg")
    (root / "빈 폴더").mkdir()
    touch(root / ".숨김" / "a.png")

    books = scan_library(root)

    assert [b.title for b in books] == ["1권", "2권", "만화"]
    assert [b.id for b in books] == [0, 1, 2]
    assert books[0] == Book(0, "1권", root / "1권", (root / "1권" / "2.webp", root / "1권" / "10.webp"))
    assert books[2].pages == (root / "표지.png",)


def test_nested_title_uses_posix_relative_path(tmp_path):
    touch(tmp_path / "시리즈" / "1권" / "a.png")
    [book] = scan_library(tmp_path)
    assert book.title == "시리즈/1권"


def test_empty_folder_has_no_books(tmp_path):
    assert scan_library(tmp_path) == []


def test_is_inside(tmp_path):
    root = tmp_path / "root"
    inside = touch(root / "a" / "b.png")
    outside = touch(tmp_path / "other.png")
    assert is_inside(root, inside)
    assert is_inside(root, root)
    assert not is_inside(root, outside)
    assert not is_inside(root, root / ".." / "other.png")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_library.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'manga_translate.library'`)

- [ ] **Step 3: 구현**

`src/manga_translate/library.py`:

```python
"""Books in a folder the user opened: every folder that directly holds images is one book."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natsort import natsort_keygen, ns

from .source import find_images

_NATURAL = natsort_keygen(alg=ns.IGNORECASE)


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    dir: Path
    pages: tuple[Path, ...]


def _sort_key(root: Path, folder: Path) -> tuple[int, object]:
    # Subfolders first in natural order of their path, then the root folder's own pages.
    relative = folder.relative_to(root)
    if not relative.parts:
        return (1, ())
    return (0, _NATURAL(relative.as_posix()))


def scan_library(root: Path) -> list[Book]:
    groups: dict[Path, list[Path]] = {}
    for image in find_images(root):
        groups.setdefault(image.parent, []).append(image)
    books: list[Book] = []
    for folder, pages in sorted(groups.items(), key=lambda item: _sort_key(root, item[0])):
        relative = folder.relative_to(root)
        title = relative.as_posix() if relative.parts else (root.name or str(root))
        books.append(Book(len(books), title, folder, tuple(pages)))
    return books


def is_inside(root: Path, path: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_library.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/library.py tests/test_library.py
git commit -F <메시지 파일>   # 제목: Scan an opened folder into books
```

---

### Task 3: 페이지 결과와 번역 캐시

**Files:**
- Create: `src/manga_translate/page.py`, `src/manga_translate/cache.py`
- Test: `tests/test_page.py`, `tests/test_cache.py`

**Interfaces:**
- Produces (`page.py`):
  - `Block(xyxy: tuple[int, int, int, int], vertical: bool, text: str, translation: str = "")` frozen
  - `PageResult(size: tuple[int, int], blocks: tuple[Block, ...])` frozen
  - `PageResult.with_translations(translations: Sequence[str]) -> PageResult` (개수가 다르면 `ValueError`)
  - `PageResult.to_json() -> dict` → `{"size": [w, h], "blocks": [{"xyxy": [...], "vertical": bool, "text": str, "translation": str}]}`
  - `PageResult.from_json(data: Mapping) -> PageResult` (형식이 틀리면 `KeyError`/`TypeError`/`ValueError`)
- Produces (`cache.py`):
  - `CACHE_VERSION = 1`
  - `TranslationCache(cache_dir: Path, model: str)`, `.get(source: Path) -> PageResult | None`, `.put(source: Path, result: PageResult) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_page.py`:

```python
import pytest

from manga_translate.page import Block, PageResult

PAGE = PageResult((800, 1200), (Block((1, 2, 30, 40), True, "こんにちは"), Block((5, 6, 70, 80), False, "えっ")))


def test_json_roundtrip():
    data = PAGE.to_json()
    assert data == {
        "size": [800, 1200],
        "blocks": [
            {"xyxy": [1, 2, 30, 40], "vertical": True, "text": "こんにちは", "translation": ""},
            {"xyxy": [5, 6, 70, 80], "vertical": False, "text": "えっ", "translation": ""},
        ],
    }
    assert PageResult.from_json(data) == PAGE


def test_from_json_without_translation_defaults_to_empty():
    page = PageResult.from_json({"size": [1, 2], "blocks": [{"xyxy": [0, 0, 1, 1], "vertical": False, "text": "a"}]})
    assert page.blocks[0].translation == ""


def test_from_json_rejects_bad_boxes():
    with pytest.raises(ValueError):
        PageResult.from_json({"size": [1, 2], "blocks": [{"xyxy": [0, 0, 1], "vertical": False, "text": "a"}]})


def test_with_translations():
    translated = PAGE.with_translations(["안녕", "엣"])
    assert [b.translation for b in translated.blocks] == ["안녕", "엣"]
    assert translated.blocks[0].text == "こんにちは"
    with pytest.raises(ValueError):
        PAGE.with_translations(["하나"])
```

`tests/test_cache.py`:

```python
import os

from manga_translate.cache import TranslationCache
from manga_translate.page import Block, PageResult

RESULT = PageResult((10, 20), (Block((1, 2, 3, 4), False, "原文", "번역"),))


def make_source(tmp_path, content=b"image"):
    source = tmp_path / "페이지 01.png"
    source.write_bytes(content)
    return source


def test_put_then_get(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    assert cache.get(source) is None
    cache.put(source, RESULT)
    assert cache.get(source) == RESULT
    assert list((tmp_path / "cache").glob("*.tmp")) == []


def test_changed_image_invalidates(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    cache.put(source, RESULT)
    source.write_bytes(b"different image")
    assert cache.get(source) is None


def test_changed_mtime_invalidates(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    cache.put(source, RESULT)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert cache.get(source) is None


def test_other_model_does_not_see_the_entry(tmp_path):
    source = make_source(tmp_path)
    TranslationCache(tmp_path / "cache", "gemma.gguf").put(source, RESULT)
    assert TranslationCache(tmp_path / "cache", "other.gguf").get(source) is None


def test_corrupt_entry_is_a_miss(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    cache.put(source, RESULT)
    [entry] = (tmp_path / "cache").glob("*.json")
    entry.write_text("{broken", encoding="utf-8")
    assert cache.get(source) is None


def test_missing_source_is_a_miss(tmp_path):
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    assert cache.get(tmp_path / "없음.png") is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_page.py tests/test_cache.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/manga_translate/page.py`:

```python
"""What one page yields: text blocks with their box, reading direction, source text and translation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Block:
    xyxy: tuple[int, int, int, int]
    vertical: bool
    text: str
    translation: str = ""


@dataclass(frozen=True)
class PageResult:
    size: tuple[int, int]  # image width, height in pixels
    blocks: tuple[Block, ...]

    def with_translations(self, translations: Sequence[str]) -> PageResult:
        if len(translations) != len(self.blocks):
            raise ValueError(f"expected {len(self.blocks)} translations, got {len(translations)}")
        blocks = tuple(replace(b, translation=t) for b, t in zip(self.blocks, translations))
        return replace(self, blocks=blocks)

    def to_json(self) -> dict:
        return {
            "size": list(self.size),
            "blocks": [
                {"xyxy": list(b.xyxy), "vertical": b.vertical, "text": b.text, "translation": b.translation}
                for b in self.blocks
            ],
        }

    @classmethod
    def from_json(cls, data: Mapping) -> PageResult:
        width, height = data["size"]
        blocks = []
        for raw in data["blocks"]:
            xyxy = tuple(int(v) for v in raw["xyxy"])
            if len(xyxy) != 4:
                raise ValueError(f"a box needs 4 numbers, got {len(xyxy)}")
            blocks.append(Block(xyxy, bool(raw["vertical"]), str(raw["text"]), str(raw.get("translation", ""))))
        return cls((int(width), int(height)), tuple(blocks))
```

`src/manga_translate/cache.py`:

```python
"""Translated pages saved in the program folder, keyed by image path and valid while the image and model match."""
from __future__ import annotations

import hashlib
import json
import os
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
        os.replace(temp, entry)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_page.py tests/test_cache.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/page.py src/manga_translate/cache.py tests/test_page.py tests/test_cache.py
git commit -F <메시지 파일>   # 제목: Add page results and the translation cache
```

---

### Task 4: llama-server 번역 요청

**Files:**
- Create: `src/manga_translate/translate.py`
- Test: `tests/test_translate.py`

**Interfaces:**
- Consumes: `PageResult`, `Block` (Task 3)
- Produces:
  - `TranslateError(RuntimeError)`
  - `CONTEXT_PAGES = 3`
  - `translation_schema(count: int) -> dict`
  - `build_messages(texts: Sequence[str], context: Sequence[PageResult]) -> list[dict]`
  - `parse_translations(content: str, count: int) -> list[str]` (틀리면 `TranslateError`)
  - `Translator(base_url: str, model: str, *, timeout: float = 60.0, attempts: int = 2, transport: httpx.BaseTransport | None = None)`
  - `Translator.translate(texts: Sequence[str], context: Sequence[PageResult] = ()) -> list[str]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_translate.py`:

```python
import json

import httpx
import pytest

from manga_translate.page import Block, PageResult
from manga_translate.translate import (
    TranslateError,
    Translator,
    build_messages,
    parse_translations,
    translation_schema,
)


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_translation_schema_requires_every_key():
    schema = translation_schema(3)
    assert schema["type"] == "object"
    assert list(schema["properties"]) == ["1", "2", "3"]
    assert schema["required"] == ["1", "2", "3"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["2"] == {"type": "string"}


def test_build_messages_puts_context_pages_before_the_request():
    context = [PageResult((1, 1), (Block((0, 0, 1, 1), False, "前", "앞"),))]
    messages = build_messages(["今", "次"], context)
    assert messages[0]["role"] == "system"
    assert [m["role"] for m in messages[1:]] == ["user", "assistant", "user"]
    assert json.loads(messages[1]["content"]) == {"1": "前"}
    assert json.loads(messages[2]["content"]) == {"1": "앞"}
    assert json.loads(messages[3]["content"]) == {"1": "今", "2": "次"}


def test_parse_translations():
    assert parse_translations('{"2": "나", "1": "가"}', 2) == ["가", "나"]
    with pytest.raises(TranslateError):
        parse_translations('{"1": "가"}', 2)
    with pytest.raises(TranslateError):
        parse_translations('{"1": 3}', 1)
    with pytest.raises(TranslateError):
        parse_translations("not json", 1)
    with pytest.raises(TranslateError):
        parse_translations('["가"]', 1)


def test_translate_sends_schema_and_returns_in_order():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return reply(json.dumps({"1": "안녕", "2": "엣"}, ensure_ascii=False))

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    assert translator.translate(["こんにちは", "えっ"]) == ["안녕", "엣"]

    [(path, body)] = seen
    assert path == "/v1/chat/completions"
    assert body["model"] == "gemma"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == translation_schema(2)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert json.loads(body["messages"][-1]["content"]) == {"1": "こんにちは", "2": "えっ"}


def test_translate_retries_once_after_a_bad_reply():
    replies = iter([reply('{"1": "가"}'), reply('{"1": "가", "2": "나"}')])
    calls = []

    def handler(request):
        calls.append(1)
        return next(replies)

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    assert translator.translate(["a", "b"]) == ["가", "나"]
    assert len(calls) == 2


def test_translate_gives_up_after_two_attempts():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"error": "boom"})

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    with pytest.raises(TranslateError, match="번역에 실패했습니다"):
        translator.translate(["a"])
    assert len(calls) == 2


def test_translate_nothing_makes_no_request():
    def handler(request):
        raise AssertionError("no request expected")

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    assert translator.translate([]) == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_translate.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/manga_translate/translate.py`:

```python
"""Translate a page's text blocks through llama-server's OpenAI-compatible chat API.

A JSON schema with one required key per block makes the server return exactly one
translation for every block, in the same numbering.
"""
from __future__ import annotations

import json
from typing import Sequence

import httpx

from .page import PageResult

CONTEXT_PAGES = 3

SYSTEM_PROMPT = (
    "너는 일본 만화 번역가다. 사용자가 보내는 JSON의 각 값은 한 페이지에 있는 말풍선의 일본어 원문이고, "
    "키는 읽는 순서다. 같은 키에 자연스러운 한국어 구어체 번역을 넣은 JSON만 답하라. "
    "인물 이름은 앞 페이지와 같게 옮기고, 말줄임표와 느낌표 같은 부호는 살린다."
)


class TranslateError(RuntimeError):
    pass


def _numbered(values: Sequence[str]) -> str:
    return json.dumps({str(i + 1): v for i, v in enumerate(values)}, ensure_ascii=False)


def translation_schema(count: int) -> dict:
    keys = [str(i + 1) for i in range(count)]
    return {
        "type": "object",
        "properties": {key: {"type": "string"} for key in keys},
        "required": keys,
        "additionalProperties": False,
    }


def build_messages(texts: Sequence[str], context: Sequence[PageResult]) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for page in context:
        messages.append({"role": "user", "content": _numbered([b.text for b in page.blocks])})
        messages.append({"role": "assistant", "content": _numbered([b.translation for b in page.blocks])})
    messages.append({"role": "user", "content": _numbered(texts)})
    return messages


def parse_translations(content: str, count: int) -> list[str]:
    try:
        data = json.loads(content)
    except ValueError as e:
        raise TranslateError(f"JSON이 아닌 응답: {content[:200]!r}") from e
    if not isinstance(data, dict):
        raise TranslateError(f"객체가 아닌 응답: {content[:200]!r}")
    translations = []
    for i in range(count):
        value = data.get(str(i + 1))
        if not isinstance(value, str):
            raise TranslateError(f"{i + 1}번 번역이 없습니다: {content[:200]!r}")
        translations.append(value)
    return translations


class Translator:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 60.0,
        attempts: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.attempts = attempts
        self._transport = transport

    def translate(self, texts: Sequence[str], context: Sequence[PageResult] = ()) -> list[str]:
        if not texts:
            return []
        payload = {
            "model": self.model,
            "messages": build_messages(texts, context),
            "temperature": 0.1,
            "max_tokens": 2048,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "translations", "strict": True, "schema": translation_schema(len(texts))},
            },
            "chat_template_kwargs": {"enable_thinking": False},
        }
        last_error: Exception | None = None
        for _ in range(self.attempts):
            try:
                # trust_env=False: never route loopback traffic through a system proxy.
                with httpx.Client(timeout=self.timeout, trust_env=False, transport=self._transport) as client:
                    response = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                    response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return parse_translations(content, len(texts))
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, TranslateError) as e:
                last_error = e
        raise TranslateError(f"번역에 실패했습니다: {last_error}")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_translate.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/translate.py tests/test_translate.py
git commit -F <메시지 파일>   # 제목: Translate text blocks through llama-server with a JSON schema
```

---

### Task 5: 검출·OCR 워커와 클라이언트

**Files:**
- Create: `src/manga_translate/scripts/bt_worker.py`, `src/manga_translate/worker_client.py`
- Create: `tests/helpers/fake_bt/ballontranslator/modules/__init__.py`, `tests/helpers/fake_bt/ballontranslator/utils/io_utils.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `PageResult.from_json` (Task 3), `EngineLayout(root).python`, `EngineLayout.root` (`engine.py`), `KillOnCloseJob.assign(pid)` (`winjob.py`)
- Produces:
  - 워커 프로토콜 (스펙 4.3): 시작 후 `{"ready": true}`, 요청 `{"id": n, "image": "<경로>"}`, 응답 `{"id": n, "size": [w, h], "blocks": [...]}` 또는 `{"id": n, "error": "..."}`
  - `WORKER_SCRIPT: Path`, `worker_argv(engine: EngineLayout) -> list[str]`
  - `WorkerError(RuntimeError)`
  - `WorkerClient(argv: Sequence[str], cwd: Path, log_path: Path, *, job: KillOnCloseJob | None = None, ready_timeout: float = 300.0, request_timeout: float = 120.0)`
  - `.start() -> None`, `.scan(image: Path) -> PageResult` (번역은 빈 문자열), `.stop() -> None`, `.running -> bool`
  - 워커가 죽었으면 다음 `scan`이 한 번 다시 시작한다.

엔진 API (2026-09-26 프로브로 확인, 엔진 커밋 `3e401b29`):
- `from ballontranslator.modules import TEXTDETECTORS, OCR`
- `TEXTDETECTORS.get("ctd").resolve()` → 클래스. 인스턴스 `.load_model()`, `.detect(img) -> (mask, blocks)`
- `OCR.get("manga_ocr").resolve()` → 클래스. `.load_model()`, `.run_ocr(img, blocks)`는 블록에 텍스트를 채운다
- `from ballontranslator.utils.io_utils import imread` → `imread(path)`는 RGB(또는 RGBA) numpy 배열, 못 읽으면 `None`
- 블록: `.xyxy`(numpy int 4개), `.vertical`(bool), `.get_text()`
- 엔진은 import할 때 stdout에 출력(예: `Device name: ...`)하므로 워커는 프로토콜용 stdout을 따로 떼어 둬야 한다.

- [ ] **Step 1: 가짜 엔진 모듈 작성**

`tests/helpers/fake_bt/ballontranslator/modules/__init__.py`:

```python
"""Stand-in for the engine's module registries, for bt_worker.py tests.

A fake image is a JSON file (see utils/io_utils.py). Its "blocks" become detected blocks and
their "text" is what OCR reads. {"fail": "msg"} makes detection raise; {"crash": true} kills the process.
"""
import os

print("Device name: fake GPU")  # the real engine prints on import; the worker must keep this off its protocol


class _Block:
    def __init__(self, spec):
        self.xyxy = spec["xyxy"]
        self.vertical = spec["vertical"]
        self._ocr_text = spec["text"]
        self.text = []

    def get_text(self):
        return "".join(self.text)


class _Detector:
    def load_model(self):
        pass

    def detect(self, img):
        if img.spec.get("crash"):
            os._exit(3)
        if "fail" in img.spec:
            raise RuntimeError(img.spec["fail"])
        return None, [_Block(b) for b in img.spec.get("blocks", [])]


class _Ocr:
    def load_model(self):
        pass

    def run_ocr(self, img, blocks):
        for block in blocks:
            block.text = [block._ocr_text]
        return blocks


class _Spec:
    def __init__(self, cls):
        self._cls = cls

    def resolve(self):
        return self._cls


class _Registry:
    def __init__(self, entries):
        self._entries = entries

    def get(self, key):
        return _Spec(self._entries[key])


TEXTDETECTORS = _Registry({"ctd": _Detector})
OCR = _Registry({"manga_ocr": _Ocr})
```

`tests/helpers/fake_bt/ballontranslator/utils/io_utils.py`:

```python
"""Stand-in for the engine's imread: a fake image is a JSON file {"size": [w, h], "blocks": [...]}."""
import json
import os


class FakeImage:
    ndim = 3

    def __init__(self, spec):
        self.spec = spec
        width, height = spec.get("size", [1, 1])
        self.shape = (height, width, 3)


def imread(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return FakeImage(json.load(f))
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_worker.py`:

```python
import json
import sys
from pathlib import Path

import pytest

from manga_translate.engine import EngineLayout
from manga_translate.page import Block, PageResult
from manga_translate.winjob import KillOnCloseJob
from manga_translate.worker_client import WORKER_SCRIPT, WorkerClient, WorkerError, worker_argv

FAKE_BT = Path(__file__).parent / "helpers" / "fake_bt"
PYTHON = getattr(sys, "_base_executable", sys.executable)


def fake_image(tmp_path: Path, name: str, spec: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def client(tmp_path):
    worker = WorkerClient(
        [PYTHON, str(WORKER_SCRIPT), str(FAKE_BT)], FAKE_BT, tmp_path / "logs" / "worker.log", ready_timeout=30, request_timeout=30
    )
    worker.start()
    yield worker
    worker.stop()


PAGE_SPEC = {
    "size": [964, 1200],
    "blocks": [
        {"xyxy": [10, 20, 30, 40], "vertical": True, "text": "こんにちは"},
        {"xyxy": [50, 60, 70, 80], "vertical": False, "text": "えっ"},
    ],
}


def test_worker_argv(tmp_path):
    engine = EngineLayout(tmp_path / "engine")
    assert worker_argv(engine) == [str(engine.python), str(WORKER_SCRIPT), str(engine.root)]


def test_scan_returns_blocks_and_ignores_engine_prints(client, tmp_path):
    image = fake_image(tmp_path, "페그오 001.json", PAGE_SPEC)
    assert client.scan(image) == PageResult(
        (964, 1200),
        (Block((10, 20, 30, 40), True, "こんにちは"), Block((50, 60, 70, 80), False, "えっ")),
    )
    assert "Device name: fake GPU" in (tmp_path / "logs" / "worker.log").read_text(encoding="utf-8")


def test_page_error_is_reported_and_worker_keeps_running(client, tmp_path):
    with pytest.raises(WorkerError, match="detector exploded"):
        client.scan(fake_image(tmp_path, "bad.json", {"fail": "detector exploded"}))
    assert client.running
    assert client.scan(fake_image(tmp_path, "ok.json", PAGE_SPEC)).size == (964, 1200)


def test_unreadable_image_is_an_error(client, tmp_path):
    with pytest.raises(WorkerError, match="이미지를 읽을 수 없습니다"):
        client.scan(tmp_path / "없는 파일.png")


def test_crashed_worker_restarts_on_next_scan(client, tmp_path):
    with pytest.raises(WorkerError, match="종료"):
        client.scan(fake_image(tmp_path, "crash.json", {"crash": True}))
    assert not client.running
    assert client.scan(fake_image(tmp_path, "ok.json", PAGE_SPEC)).blocks[0].text == "こんにちは"
    assert client.running


def test_stop_ends_the_process(client):
    client.stop()
    assert not client.running


def test_closing_the_job_ends_the_worker(tmp_path):
    job = KillOnCloseJob()
    worker = WorkerClient(
        [PYTHON, str(WORKER_SCRIPT), str(FAKE_BT)], FAKE_BT, tmp_path / "worker.log", job=job, ready_timeout=30
    )
    worker.start()
    try:
        job.close()
        with pytest.raises(WorkerError):
            worker.scan(fake_image(tmp_path, "ok.json", PAGE_SPEC))
    finally:
        worker.stop()
```

주의: `test_closing_the_job_ends_the_worker`에서 job이 닫히면 워커가 죽고, `scan`은 한 번 다시 시작하려다 `job.assign`이 `RuntimeError("job is closed")`로 실패한다. 클라이언트는 이를 `WorkerError`로 바꿔 올려야 한다(구현의 `_start` 참고).

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'manga_translate.worker_client'`)

- [ ] **Step 4: 워커 스크립트 구현**

`src/manga_translate/scripts/bt_worker.py`:

```python
"""Runs inside the BallonsTranslator venv (never imported by manga_translate).

Loads the text detector and OCR once, then answers one JSON request per stdin line:
  {"id": 1, "image": "C:/.../page.png"}
  -> {"id": 1, "size": [w, h], "blocks": [{"xyxy": [x1, y1, x2, y2], "vertical": bool, "text": str}]}
  -> {"id": 1, "error": "..."} when that page fails
Usage: python bt_worker.py <engine_root>
"""
import json
import os
import sys
from pathlib import Path


def scan(image, detector, ocr, imread):
    img = imread(image)
    if img is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image}")
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[..., :3]
    _, blocks = detector.detect(img)
    if blocks:
        ocr.run_ocr(img, blocks)
    return {
        "size": [int(img.shape[1]), int(img.shape[0])],
        "blocks": [
            {"xyxy": [int(v) for v in block.xyxy], "vertical": bool(block.vertical), "text": block.get_text()}
            for block in blocks
        ],
    }


def main():
    root = Path(sys.argv[1])
    # The protocol owns the real stdout; anything the engine prints goes to stderr (the worker log).
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    sys.path.insert(0, str(root))
    os.chdir(root)  # the engine finds its models under data/models relative to its root
    from ballontranslator.modules import OCR, TEXTDETECTORS
    from ballontranslator.utils.io_utils import imread

    detector = TEXTDETECTORS.get("ctd").resolve()()
    ocr = OCR.get("manga_ocr").resolve()()
    detector.load_model()
    ocr.load_model()

    def send(message):
        protocol.write(json.dumps(message, ensure_ascii=False) + "\n")
        protocol.flush()

    send({"ready": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request["id"]
            send({"id": request_id, **scan(request["image"], detector, ocr, imread)})
        except Exception as e:
            send({"id": request_id, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 클라이언트 구현**

`src/manga_translate/worker_client.py`:

```python
"""The resident detection/OCR worker: a child process in the engine venv answering one JSON line per page."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import IO, Sequence

from .engine import EngineLayout
from .page import PageResult
from .winjob import KillOnCloseJob

WORKER_SCRIPT = Path(__file__).parent / "scripts" / "bt_worker.py"


class WorkerError(RuntimeError):
    pass


def worker_argv(engine: EngineLayout) -> list[str]:
    return [str(engine.python), str(WORKER_SCRIPT), str(engine.root)]


def _pump(stream: IO[bytes], lines: queue.Queue) -> None:
    for raw in stream:
        lines.put(raw.decode("utf-8", errors="replace"))
    lines.put(None)


class WorkerClient:
    def __init__(
        self,
        argv: Sequence[str],
        cwd: Path,
        log_path: Path,
        *,
        job: KillOnCloseJob | None = None,
        ready_timeout: float = 300.0,
        request_timeout: float = 120.0,
    ) -> None:
        self._argv = list(argv)
        self._cwd = cwd
        self._log_path = log_path
        self._job = job
        self._ready_timeout = ready_timeout
        self._request_timeout = request_timeout
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._lines: queue.Queue | None = None
        self._log: IO[bytes] | None = None
        self._next_id = 0

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            self._start()

    def stop(self) -> None:
        with self._lock:
            self._stop_process()

    def scan(self, image: Path) -> PageResult:
        with self._lock:
            if not self.running:
                self._start()  # the worker died since the last page: start it once more
            assert self._proc is not None and self._proc.stdin is not None
            self._next_id += 1
            request_id = self._next_id
            request = json.dumps({"id": request_id, "image": str(image)}, ensure_ascii=False) + "\n"
            try:
                self._proc.stdin.write(request.encode("utf-8"))
                self._proc.stdin.flush()
            except OSError as e:
                self._stop_process()
                raise WorkerError(f"번역 엔진이 종료되었습니다. 로그: {self._log_path}") from e
            while True:
                message = self._read(self._request_timeout)
                if message.get("id") == request_id:
                    break
        if "error" in message:
            raise WorkerError(str(message["error"]))
        try:
            return PageResult.from_json(message)
        except (KeyError, TypeError, ValueError) as e:
            raise WorkerError(f"번역 엔진 응답을 읽지 못했습니다: {e}") from e

    def _start(self) -> None:
        self._stop_process()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self._log_path.open("ab")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        try:
            self._proc = subprocess.Popen(
                self._argv,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if self._job is not None:
                self._job.assign(self._proc.pid)
        except (OSError, RuntimeError) as e:
            self._stop_process()
            raise WorkerError(f"번역 엔진을 시작하지 못했습니다: {e}") from e
        lines: queue.Queue = queue.Queue()
        self._lines = lines
        assert self._proc.stdout is not None
        threading.Thread(target=_pump, args=(self._proc.stdout, lines), daemon=True).start()
        message = self._read(self._ready_timeout)
        if not message.get("ready"):
            self._stop_process()
            raise WorkerError(f"번역 엔진이 준비되지 않았습니다. 로그: {self._log_path}")

    def _read(self, timeout: float) -> dict:
        assert self._lines is not None
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty:
                self._stop_process()
                raise WorkerError(f"번역 엔진이 응답하지 않습니다. 로그: {self._log_path}") from None
            if line is None:
                self._stop_process()
                raise WorkerError(f"번역 엔진이 종료되었습니다. 로그: {self._log_path}")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict):
                return message

    def _stop_process(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        if self._log is not None:
            self._log.close()
            self._log = None
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add src/manga_translate/scripts/bt_worker.py src/manga_translate/worker_client.py tests/helpers/fake_bt/ballontranslator/modules/__init__.py tests/helpers/fake_bt/ballontranslator/utils/io_utils.py tests/test_worker.py
git commit -F <메시지 파일>   # 제목: Add the resident detection/OCR worker and its client
```

---

### Task 6: 페이지 처리와 스케줄러

**Files:**
- Create: `src/manga_translate/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `PageResult` (Task 3), `TranslationCache.get/put` (Task 3), `CONTEXT_PAGES` (Task 4)
- Produces:
  - `process_page(pages: Sequence[Path], index: int, *, scan: Callable[[Path], PageResult], translate: Callable[[Sequence[str], Sequence[PageResult]], list[str]], cache: TranslationCache, context_pages: int = CONTEXT_PAGES) -> PageResult`
  - `Scheduler(process: Callable[[Sequence[Path], int], object], is_done: Callable[[Path], bool], *, next_pages: int = 3, previous_pages: int = 1)`
  - `.focus(pages: Sequence[Path], index: int) -> None`, `.status(page: Path) -> tuple[str, str]` (`("working", "")`, `("pending", "")`, `("failed", 메시지)`), `.retry(pages, index) -> None`, `.wait_idle(timeout: float) -> bool`, `.stop() -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_scheduler.py`:

```python
import threading
from pathlib import Path

from manga_translate.cache import TranslationCache
from manga_translate.page import Block, PageResult
from manga_translate.scheduler import Scheduler, process_page

PAGES = tuple(Path(f"p{i}") for i in range(10))


def recorder(done=frozenset(), fail=frozenset(), gate=None):
    order = []

    def process(pages, index):
        order.append(index)
        if gate is not None and index == gate[0]:
            gate[1].wait(10)
        if index in fail:
            raise RuntimeError(f"page {index} broke")

    return order, process, (lambda page: int(page.name[1:]) in done)


def test_focus_orders_current_then_next_three_then_previous():
    order, process, is_done = recorder()
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert order == [5, 6, 7, 8, 4]
    finally:
        scheduler.stop()


def test_done_pages_and_out_of_range_pages_are_skipped():
    order, process, is_done = recorder(done={6})
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 8)
        assert scheduler.wait_idle(10)
        assert order == [8, 9, 7]
    finally:
        scheduler.stop()


def test_refocus_keeps_the_page_in_progress_and_replaces_the_queue():
    release = threading.Event()
    order, process, is_done = recorder(gate=(5, release))
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 5)
        for _ in range(200):
            if scheduler.status(PAGES[5]) == ("working", ""):
                break
            threading.Event().wait(0.01)
        assert scheduler.status(PAGES[5]) == ("working", "")
        assert scheduler.status(PAGES[6]) == ("pending", "")
        scheduler.focus(PAGES, 0)
        release.set()
        assert scheduler.wait_idle(10)
        assert order == [5, 0, 1, 2, 3]
    finally:
        release.set()
        scheduler.stop()


def test_failed_page_is_not_retried_until_asked():
    order, process, is_done = recorder(fail={5})
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert scheduler.status(PAGES[5]) == ("failed", "page 5 broke")
        order.clear()
        scheduler.focus(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert 5 not in order
        scheduler.retry(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert order[0] == 5
    finally:
        scheduler.stop()


def test_stop_ends_the_thread():
    _, process, is_done = recorder()
    scheduler = Scheduler(process, is_done)
    scheduler.stop()
    scheduler.focus(PAGES, 0)  # ignored after stop


def make_pages(tmp_path, count):
    pages = []
    for i in range(count):
        page = tmp_path / f"{i:03d}.png"
        page.write_bytes(f"image {i}".encode())
        pages.append(page)
    return pages


def test_process_page_translates_with_previous_pages_as_context(tmp_path):
    pages = make_pages(tmp_path, 3)
    cache = TranslationCache(tmp_path / "cache", "m")
    earlier = PageResult((1, 1), (Block((0, 0, 1, 1), False, "前", "앞"),))
    cache.put(pages[0], earlier)
    scanned = PageResult((10, 10), (Block((1, 1, 5, 5), True, "今"), Block((6, 6, 9, 9), False, "次")))
    calls = []

    def translate(texts, context):
        calls.append((list(texts), list(context)))
        return ["지금", "다음"]

    result = process_page(pages, 2, scan=lambda path: scanned, translate=translate, cache=cache)

    assert [b.translation for b in result.blocks] == ["지금", "다음"]
    assert calls == [(["今", "次"], [earlier])]
    assert cache.get(pages[2]) == result


def test_process_page_with_no_text_skips_translation(tmp_path):
    pages = make_pages(tmp_path, 1)
    cache = TranslationCache(tmp_path / "cache", "m")
    empty = PageResult((10, 10), ())

    def translate(texts, context):
        raise AssertionError("nothing to translate")

    assert process_page(pages, 0, scan=lambda path: empty, translate=translate, cache=cache) == empty
    assert cache.get(pages[0]) == empty
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/manga_translate/scheduler.py`:

```python
"""Which page to translate next: the page on screen first, then the next few, then the one before."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Sequence

from .cache import TranslationCache
from .page import PageResult
from .translate import CONTEXT_PAGES


def process_page(
    pages: Sequence[Path],
    index: int,
    *,
    scan: Callable[[Path], PageResult],
    translate: Callable[[Sequence[str], Sequence[PageResult]], list[str]],
    cache: TranslationCache,
    context_pages: int = CONTEXT_PAGES,
) -> PageResult:
    """Detect and read the page's text, translate it with the previous pages as context, and cache it."""
    source = pages[index]
    result = scan(source)
    if result.blocks:
        earlier = (cache.get(page) for page in pages[max(0, index - context_pages):index])
        context = [page for page in earlier if page is not None and page.blocks]
        result = result.with_translations(translate([b.text for b in result.blocks], context))
    cache.put(source, result)
    return result


class Scheduler:
    """One background thread that processes one page at a time in priority order."""

    def __init__(
        self,
        process: Callable[[Sequence[Path], int], object],
        is_done: Callable[[Path], bool],
        *,
        next_pages: int = 3,
        previous_pages: int = 1,
    ) -> None:
        self._process = process
        self._is_done = is_done
        self._next_pages = next_pages
        self._previous_pages = previous_pages
        self._cond = threading.Condition()
        self._queue: list[tuple[tuple[Path, ...], int]] = []
        self._failed: dict[Path, str] = {}
        self._working: Path | None = None
        self._stopped = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def focus(self, pages: Sequence[Path], index: int) -> None:
        pages = tuple(pages)
        order = [index, *(index + i for i in range(1, self._next_pages + 1)), *(index - i for i in range(1, self._previous_pages + 1))]
        wanted = [i for i in order if 0 <= i < len(pages) and not self._is_done(pages[i])]
        with self._cond:
            if self._stopped:
                return
            self._queue = [
                (pages, i) for i in wanted if pages[i] not in self._failed and pages[i] != self._working
            ]
            self._cond.notify_all()

    def retry(self, pages: Sequence[Path], index: int) -> None:
        with self._cond:
            self._failed.pop(tuple(pages)[index], None)
        self.focus(pages, index)

    def status(self, page: Path) -> tuple[str, str]:
        with self._cond:
            if page in self._failed:
                return ("failed", self._failed[page])
            if page == self._working:
                return ("working", "")
            return ("pending", "")

    def wait_idle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._queue or self._working is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._queue = []
            self._cond.notify_all()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stopped:
                    self._cond.wait()
                if self._stopped:
                    return
                pages, index = self._queue.pop(0)
                self._working = pages[index]
            error = None
            try:
                self._process(pages, index)
            except Exception as e:
                error = str(e) or type(e).__name__
            with self._cond:
                if error is not None:
                    self._failed[pages[index]] = error
                self._working = None
                self._cond.notify_all()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/scheduler.py tests/test_scheduler.py
git commit -F <메시지 파일>   # 제목: Schedule page translation around the page on screen
```

---

### Task 7: 로컬 HTTP 서버

**Files:**
- Create: `src/manga_translate/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces:
  - `Response(body: bytes, content_type: str, status: int = 200)` frozen
  - `ApiError(status: int, message: str)` (Exception)
  - `Route = Callable[[dict[str, str]], object]` — 쿼리 파라미터(토큰 제외)를 받아 `Response` 또는 JSON으로 바꿀 값을 돌려준다
  - `TOKEN_PLACEHOLDER = "{{TOKEN}}"`
  - `make_server(routes: Mapping[tuple[str, str], Route], token: str, web_dir: Path, port: int = 0) -> ThreadingHTTPServer` (127.0.0.1)
  - 규칙: 모든 요청은 `token` 쿼리나 `X-Token` 헤더가 맞아야 한다(아니면 403 `{"error": "forbidden"}`). `GET /`는 `index.html`의 `{{TOKEN}}`을 토큰으로 바꿔 준다. `GET /static/<이름>`은 `web_dir` 바로 아래의 `.js`/`.css`/`.html`만 준다. 라우트가 `ApiError`를 던지면 그 상태 코드와 `{"error": 메시지}`, 다른 예외는 500.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py`:

```python
import http.client
import threading

import httpx
import pytest

from manga_translate.server import ApiError, Response, make_server

TOKEN = "secret-token"


@pytest.fixture
def base_url(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text('<script src="/static/app.js?token={{TOKEN}}"></script>', encoding="utf-8")
    (web / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (web / "notes.txt").write_text("no", encoding="utf-8")

    def boom(query):
        raise RuntimeError("kaboom")

    def busy(query):
        raise ApiError(409, "다른 작업이 진행 중입니다.")

    routes = {
        ("GET", "/api/echo"): lambda query: {"query": query},
        ("POST", "/api/echo"): lambda query: {"posted": query},
        ("GET", "/api/bytes"): lambda query: Response(b"\x89PNG", "image/png"),
        ("GET", "/api/busy"): busy,
        ("GET", "/api/boom"): boom,
    }
    server = make_server(routes, TOKEN, web)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(base_url, path, **kwargs):
    return httpx.get(base_url + path, trust_env=False, **kwargs)


def test_requests_without_the_token_are_forbidden(base_url):
    assert get(base_url, "/api/echo").status_code == 403
    assert get(base_url, "/api/echo?token=wrong").status_code == 403
    assert get(base_url, "/?token=wrong").status_code == 403


def test_token_in_query_or_header(base_url):
    assert get(base_url, f"/api/echo?token={TOKEN}&book=2").json() == {"query": {"book": "2"}}
    assert get(base_url, "/api/echo?index=1", headers={"X-Token": TOKEN}).json() == {"query": {"index": "1"}}


def test_post_route(base_url):
    response = httpx.post(f"{base_url}/api/echo?token={TOKEN}&a=1", trust_env=False)
    assert response.json() == {"posted": {"a": "1"}}


def test_index_gets_the_token(base_url):
    response = get(base_url, f"/?token={TOKEN}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f"app.js?token={TOKEN}" in response.text


def test_static_files(base_url):
    response = get(base_url, f"/static/app.js?token={TOKEN}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert get(base_url, f"/static/notes.txt?token={TOKEN}").status_code == 404
    assert get(base_url, f"/static/.hidden?token={TOKEN}").status_code == 404


def test_static_rejects_paths_outside_the_web_folder(base_url):
    host, port = base_url.removeprefix("http://").split(":")
    for path in (f"/static/../web/app.js?token={TOKEN}", f"/static/sub%2Fapp.js?token={TOKEN}"):
        connection = http.client.HTTPConnection(host, int(port))
        connection.request("GET", path)
        assert connection.getresponse().status == 404
        connection.close()


def test_bytes_response(base_url):
    response = get(base_url, f"/api/bytes?token={TOKEN}")
    assert response.content == b"\x89PNG"
    assert response.headers["content-type"] == "image/png"


def test_errors(base_url):
    busy = get(base_url, f"/api/busy?token={TOKEN}")
    assert busy.status_code == 409
    assert busy.json() == {"error": "다른 작업이 진행 중입니다."}
    boom = get(base_url, f"/api/boom?token={TOKEN}")
    assert boom.status_code == 500
    assert "kaboom" in boom.json()["error"]
    assert get(base_url, f"/api/nothing?token={TOKEN}").status_code == 404
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/manga_translate/server.py`:

```python
"""Local HTTP server for the viewer window: its web files and a JSON API, guarded by a per-run token."""
from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

TOKEN_PLACEHOLDER = "{{TOKEN}}"
JSON_TYPE = "application/json; charset=utf-8"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


@dataclass(frozen=True)
class Response:
    body: bytes
    content_type: str
    status: int = 200


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


Route = Callable[[dict[str, str]], object]


def _json(value: object, status: int = 200) -> Response:
    return Response(json.dumps(value, ensure_ascii=False).encode("utf-8"), JSON_TYPE, status)


def _index(web_dir: Path, token: str) -> Response:
    html = (web_dir / "index.html").read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, token)
    return Response(html.encode("utf-8"), STATIC_TYPES[".html"])


def _static(web_dir: Path, name: str) -> Response:
    if not name or "/" in name or "\\" in name or "%" in name or name.startswith("."):
        raise ApiError(404, "not found")
    path = web_dir / name
    content_type = STATIC_TYPES.get(path.suffix)
    if content_type is None or not path.is_file():
        raise ApiError(404, "not found")
    return Response(path.read_bytes(), content_type)


def make_server(
    routes: Mapping[tuple[str, str], Route], token: str, web_dir: Path, port: int = 0
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args: object) -> None:
            logger.debug(format, *args)

        def _handle(self, method: str) -> None:
            url = urlsplit(self.path)
            query = {key: values[-1] for key, values in parse_qs(url.query).items()}
            given = query.pop("token", None) or self.headers.get("X-Token") or ""
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)  # the API takes no bodies
            if not hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8")):
                self._send(_json({"error": "forbidden"}, 403))
                return
            try:
                if method == "GET" and url.path == "/":
                    response = _index(web_dir, token)
                elif method == "GET" and url.path.startswith("/static/"):
                    response = _static(web_dir, url.path[len("/static/"):])
                else:
                    route = routes.get((method, url.path))
                    if route is None:
                        raise ApiError(404, "not found")
                    result = route(query)
                    response = result if isinstance(result, Response) else _json(result)
            except ApiError as e:
                response = _json({"error": e.message}, e.status)
            except Exception as e:
                logger.exception("request failed: %s %s", method, url.path)
                response = _json({"error": f"내부 오류: {e}"}, 500)
            self._send(response)

        def _send(self, response: Response) -> None:
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(response.body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # the window navigated away mid-response

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_server.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/server.py tests/test_server.py
git commit -F <메시지 파일>   # 제목: Add the token-guarded local HTTP server
```

---

### Task 8: 앱 상태와 API

**Files:**
- Create: `src/manga_translate/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes:
  - `components.llama_ready/model_ready/model_path/install_llama/install_model`, `components.MODEL` (`components.py`)
  - `EngineLayout`, `setup_engine`, `EngineError` (`engine.py`); `run_streaming(argv, cwd, *, job, on_line, stdin_text)` (`engine_run.py`, Task 10에서 `engine.py`로 옮김)
  - `Cancelled`, `InstallError` (`download.py`); `find_uv`, `AppLayout` (`paths.py`); `ServerStartError` (`llm/process.py`); `LlamaConfig`, `start_llama_server` (`llm/llama.py`); `KillOnCloseJob`
  - `Settings`, `load_settings`, `save_settings`, `PAGE_DIRECTIONS` (Task 1); `Book`, `scan_library`, `is_inside` (Task 2); `TranslationCache` (Task 3); `Translator` (Task 4); `WorkerClient`, `WorkerError`, `worker_argv` (Task 5); `Scheduler`, `process_page` (Task 6); `ApiError`, `Response` (Task 7)
- Produces:
  - `TITLE = "manga-translate"`, `LANGUAGES = "일본어 → 한국어"`, `COMPONENTS = (("engine", "번역 엔진", "약 6GB"), ("llama", "llama.cpp", "약 0.6GB"), ("model", "번역 모델", "약 5GB"))`
  - `component_status_text(ready: bool, size: str) -> str`, `effective_model(layout, settings) -> Path | None`, `model_status_text(layout, settings) -> str`, `make_runner(on_line, job=None) -> Callable[[Sequence[str]], None]` (기존 `gui.py`와 같은 동작)
  - `Runtime(layout: AppLayout, model: Path, job: KillOnCloseJob)`: `.cache: TranslationCache`, `.scheduler: Scheduler`, `.close()`
  - `AppState(layout: AppLayout, dialogs: Dialogs, runtime_factory=Runtime)`: `.state() -> dict`, `.install(kind) -> dict`, `.cancel_task() -> dict`, `.start() -> dict`, `.pick_model() -> dict`, `.open_library() -> dict`, `.library_json() -> dict`, `.image(book_id, index) -> Response`, `.translation(book_id, index) -> dict`, `.retry(book_id, index) -> dict`, `.save_position(book_id, index) -> dict`, `.set_page_direction(value) -> dict`, `.can_start() -> bool`, `.shutdown() -> None`
  - `Dialogs` 프로토콜: `pick_folder() -> str | None`, `pick_model() -> str | None`
  - `build_routes(state: AppState) -> dict[tuple[str, str], Route]` — 스펙 6장의 경로 전부

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_app.py`:

```python
import sys
import threading
import time
from pathlib import Path

import pytest

import manga_translate.components as components
from manga_translate.app import (
    AppState,
    build_routes,
    component_status_text,
    effective_model,
    make_runner,
    model_status_text,
)
from manga_translate.cache import TranslationCache
from manga_translate.components import LLAMA_MARKER, LLAMA_TAG, Asset
from manga_translate.download import Cancelled, InstallError
from manga_translate.engine import ENGINE_COMMIT, EngineError, EngineLayout
from manga_translate.llm.process import ServerStartError
from manga_translate.page import Block, PageResult
from manga_translate.paths import AppLayout
from manga_translate.server import ApiError
from manga_translate.settings import Settings, load_settings
from manga_translate.winjob import KillOnCloseJob

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


class FakeDialogs:
    def __init__(self, folder=None, model=None):
        self.folder = folder
        self.model = model

    def pick_folder(self):
        return self.folder

    def pick_model(self):
        return self.model


class FakeScheduler:
    def __init__(self):
        self.focused = []
        self.retried = []

    def focus(self, pages, index):
        self.focused.append((tuple(pages), index))

    def status(self, page):
        return ("working", "")

    def retry(self, pages, index):
        self.retried.append((tuple(pages), index))


class FakeRuntime:
    def __init__(self, layout, model, job):
        self.model = model
        self.cache = TranslationCache(layout.cache_dir, model.name)
        self.scheduler = FakeScheduler()
        self.closed = False

    def close(self):
        self.closed = True


def wait_task(state, timeout=10):
    deadline = time.monotonic() + timeout
    while state.task is not None:
        assert time.monotonic() < deadline, "task did not finish"
        time.sleep(0.01)


def make_library(root: Path) -> Path:
    for name in ("1권/001.png", "1권/002.png", "2권/001.webp"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    return root


# --- helpers carried over from the tkinter window ---


def test_component_status_text():
    assert component_status_text(True, "약 1GB") == "설치됨"
    assert component_status_text(False, "약 1GB") == "설치 필요 (약 1GB)"


def test_effective_model_and_status(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    assert effective_model(layout, Settings()) is None
    assert model_status_text(layout, Settings()) == "설치 필요 (약 5GB)"
    install_all(layout)
    assert effective_model(layout, Settings()) == layout.models_dir / "small-model.gguf"
    assert model_status_text(layout, Settings()) == "small-model (설치됨)"
    chosen = tmp_path / "mine.gguf"
    chosen.write_bytes(b"x")
    assert effective_model(layout, Settings(model=str(chosen))) == chosen
    assert model_status_text(layout, Settings(model=str(chosen))) == "mine (직접 선택)"
    missing = str(tmp_path / "gone.gguf")
    assert effective_model(layout, Settings(model=missing)) == layout.models_dir / "small-model.gguf"
    assert model_status_text(layout, Settings(model=missing)) == "gone (파일 없음, 기본 모델 사용)"


def test_make_runner_streams_and_raises():
    lines = []
    make_runner(lines.append)([PYTHON, "-c", "print('설치 중')"])
    assert lines == ["설치 중"]
    with pytest.raises(EngineError, match="코드 3"):
        make_runner(lines.append)([PYTHON, "-c", "import sys; sys.exit(3)"])


# --- state and install tasks ---


def test_state_before_and_after_install(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    state = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    data = state.state()
    assert [c["key"] for c in data["components"]] == ["engine", "llama", "model"]
    assert not any(c["ready"] for c in data["components"])
    assert data["can_start"] is False
    assert data["runtime"] == "stopped"
    assert data["languages"] == "일본어 → 한국어"
    assert data["page_direction"] == "rtl"

    install_all(layout)
    data = state.state()
    assert all(c["ready"] for c in data["components"])
    assert data["model"] == "small-model"
    assert data["can_start"] is True


def test_only_one_task_at_a_time(tmp_path, small_model):
    state = AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime)
    state.task = "engine"
    with pytest.raises(ApiError) as error:
        state.install("llama")
    assert error.value.status == 409


def test_install_error_is_reported(tmp_path, small_model, monkeypatch):
    def fail(layout, *, log, cancel):
        raise InstallError("다운로드 실패")

    monkeypatch.setattr(components, "install_llama", fail)
    state = AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime)
    state.install("llama")
    wait_task(state)
    assert state.state()["error"] == "다운로드 실패"


def test_cancel_stops_an_install(tmp_path, small_model, monkeypatch):
    started = threading.Event()

    def slow(layout, *, log, cancel):
        started.set()
        assert cancel.wait(10)
        raise Cancelled()

    monkeypatch.setattr(components, "install_model", slow)
    state = AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime)
    state.install("model")
    assert started.wait(10)
    state.cancel_task()
    wait_task(state)
    assert "중단했습니다" in state.state()["message"]


def test_unknown_component(tmp_path):
    state = AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime)
    with pytest.raises(ApiError) as error:
        state.install("gpu")
    assert error.value.status == 404


def test_start_builds_the_runtime(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    install_all(layout)
    state = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    state.start()
    wait_task(state)
    assert state.state()["runtime"] == "ready"
    assert state.runtime.model == layout.models_dir / "small-model.gguf"
    assert state.state()["can_start"] is False
    state.shutdown()
    assert state.runtime is None


def test_start_failure_is_reported(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    install_all(layout)

    def broken(layout, model, job):
        raise ServerStartError("서버가 종료되었습니다")

    state = AppState(layout, FakeDialogs(), runtime_factory=broken)
    state.start()
    wait_task(state)
    assert state.state()["runtime"] == "error"
    assert "서버가 종료되었습니다" in state.state()["error"]
    assert state.can_start()


def test_start_needs_everything_installed(tmp_path, small_model):
    state = AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime)
    with pytest.raises(ApiError) as error:
        state.start()
    assert error.value.status == 409


def test_pick_model(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    chosen = tmp_path / "mine.gguf"
    chosen.write_bytes(b"x")
    state = AppState(layout, FakeDialogs(model=str(chosen)), runtime_factory=FakeRuntime)
    state.pick_model()
    assert load_settings(layout.settings_path).model == str(chosen)
    state.runtime = object()
    with pytest.raises(ApiError) as error:
        state.pick_model()
    assert error.value.status == 409


# --- library, images, translations ---


def test_open_library_lists_books_and_remembers_the_folder(tmp_path):
    layout = AppLayout(tmp_path / "app")
    root = make_library(tmp_path / "만화")
    state = AppState(layout, FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    data = state.open_library()
    assert data["root"] == str(root)
    assert [(b["id"], b["title"], b["pages"], b["position"]) for b in data["books"]] == [
        (0, "1권", 2, 0),
        (1, "2권", 1, 0),
    ]
    assert load_settings(layout.settings_path).last_library == str(root)
    reopened = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    assert len(reopened.library_json()["books"]) == 2


def test_cancelled_folder_dialog_keeps_the_library(tmp_path):
    state = AppState(AppLayout(tmp_path), FakeDialogs(folder=None), runtime_factory=FakeRuntime)
    assert state.open_library() == {"root": "", "books": []}


def test_image_serves_bytes_and_checks_bounds(tmp_path):
    root = make_library(tmp_path / "만화")
    state = AppState(AppLayout(tmp_path / "app"), FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    state.open_library()
    response = state.image(0, 1)
    assert response.body == b"1\xea\xb6\x8c/002.png"
    assert response.content_type == "image/png"
    assert state.image(1, 0).content_type == "image/webp"
    for book, index in ((2, 0), (0, 2), (-1, 0)):
        with pytest.raises(ApiError) as error:
            state.image(book, index)
        assert error.value.status == 404


def test_pages_outside_the_opened_folder_are_refused(tmp_path):
    root = make_library(tmp_path / "만화")
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"x")
    state = AppState(AppLayout(tmp_path / "app"), FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    state.open_library()
    book = state.books[0]
    state.books[0] = type(book)(book.id, book.title, book.dir, (outside,))
    with pytest.raises(ApiError) as error:
        state.image(0, 0)
    assert error.value.status == 403


def test_translation_needs_a_running_engine(tmp_path):
    root = make_library(tmp_path / "만화")
    state = AppState(AppLayout(tmp_path / "app"), FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    state.open_library()
    with pytest.raises(ApiError) as error:
        state.translation(0, 0)
    assert error.value.status == 409


def test_translation_pending_then_done(tmp_path, small_model):
    layout = AppLayout(tmp_path / "app")
    install_all(layout)
    root = make_library(tmp_path / "만화")
    state = AppState(layout, FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    state.open_library()
    state.start()
    wait_task(state)
    book = state.books[0]

    assert state.translation(0, 1) == {"status": "working", "error": ""}
    assert state.runtime.scheduler.focused == [(book.pages, 1)]

    result = PageResult((5, 6), (Block((1, 2, 3, 4), True, "原文", "번역"),))
    state.runtime.cache.put(book.pages[1], result)
    assert state.translation(0, 1) == {"status": "done", **result.to_json()}

    assert state.retry(0, 1) == {"status": "pending", "error": ""}
    assert state.runtime.scheduler.retried == [(book.pages, 1)]


def test_save_position_and_page_direction(tmp_path):
    layout = AppLayout(tmp_path / "app")
    root = make_library(tmp_path / "만화")
    state = AppState(layout, FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    state.open_library()
    state.save_position(0, 1)
    assert load_settings(layout.settings_path).positions == {str(root / "1권"): 1}
    assert state.library_json()["books"][0]["position"] == 1
    state.set_page_direction("ltr")
    assert load_settings(layout.settings_path).page_direction == "ltr"
    with pytest.raises(ApiError) as error:
        state.set_page_direction("up")
    assert error.value.status == 400


def test_routes_cover_the_api(tmp_path):
    routes = build_routes(AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime))
    assert set(routes) == {
        ("GET", "/api/state"),
        ("POST", "/api/install/engine"),
        ("POST", "/api/install/llama"),
        ("POST", "/api/install/model"),
        ("POST", "/api/cancel"),
        ("POST", "/api/model"),
        ("POST", "/api/start"),
        ("POST", "/api/library/open"),
        ("GET", "/api/library"),
        ("GET", "/api/image"),
        ("GET", "/api/translation"),
        ("POST", "/api/retry"),
        ("POST", "/api/progress"),
        ("POST", "/api/settings"),
    }


def test_route_arguments_are_validated(tmp_path):
    routes = build_routes(AppState(AppLayout(tmp_path), FakeDialogs(), runtime_factory=FakeRuntime))
    with pytest.raises(ApiError) as error:
        routes[("GET", "/api/image")]({"book": "x", "index": "0"})
    assert error.value.status == 400
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'manga_translate.app'`)

- [ ] **Step 3: 구현**

`src/manga_translate/app.py`:

```python
"""The viewer app: install components, run the translation engine, and serve books to the window."""
from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path
from typing import Callable, Protocol, Sequence

from . import components
from .cache import TranslationCache
from .download import Cancelled, InstallError
from .engine import EngineError, EngineLayout, setup_engine
from .engine_run import run_streaming
from .library import Book, is_inside, scan_library
from .llm.llama import LlamaConfig, start_llama_server
from .llm.process import ServerStartError
from .paths import AppLayout, find_uv
from .scheduler import Scheduler, process_page
from .server import ApiError, Response, Route
from .settings import PAGE_DIRECTIONS, Settings, load_settings, save_settings
from .translate import TranslateError, Translator
from .winjob import KillOnCloseJob
from .worker_client import WorkerClient, WorkerError, worker_argv

logger = logging.getLogger(__name__)

TITLE = "manga-translate"
LANGUAGES = "일본어 → 한국어"
COMPONENTS = (
    ("engine", "번역 엔진", "약 6GB"),
    ("llama", "llama.cpp", "약 0.6GB"),
    ("model", "번역 모델", "약 5GB"),
)
MODEL_SIZE = COMPONENTS[2][2]
STOPPED_MESSAGE = "중단했습니다. 다시 누르면 이어서 진행합니다."
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def component_status_text(ready: bool, size: str) -> str:
    return "설치됨" if ready else f"설치 필요 ({size})"


def effective_model(layout: AppLayout, settings: Settings) -> Path | None:
    """The GGUF to translate with: the user's pick if it exists, else the installed default."""
    default = components.model_path(layout) if components.model_ready(layout) else None
    if settings.model:
        chosen = Path(settings.model)
        return chosen if chosen.is_file() else default
    return default


def model_status_text(layout: AppLayout, settings: Settings) -> str:
    if settings.model:
        chosen = Path(settings.model)
        if chosen.is_file():
            return f"{chosen.stem} (직접 선택)"
        if components.model_ready(layout):
            return f"{chosen.stem} (파일 없음, 기본 모델 사용)"
        return f"{chosen.stem} (파일 없음)"
    if components.model_ready(layout):
        return f"{Path(components.MODEL.name).stem} (설치됨)"
    return f"설치 필요 ({MODEL_SIZE})"


def make_runner(on_line: Callable[[str], None], job: KillOnCloseJob | None = None) -> Callable[[Sequence[str]], None]:
    """Engine setup commands: no console, output goes to the log."""

    def run(argv: Sequence[str]) -> None:
        code = run_streaming(argv, Path.home(), job=job, on_line=on_line, stdin_text="")
        if code != 0:
            raise EngineError(f"명령이 실패했습니다 (코드 {code}): {' '.join(map(str, argv))}")

    return run


class Dialogs(Protocol):
    def pick_folder(self) -> str | None: ...

    def pick_model(self) -> str | None: ...


class Runtime:
    """llama-server, the detection/OCR worker and the scheduler, all ended by closing ``job``."""

    def __init__(self, layout: AppLayout, model: Path, job: KillOnCloseJob) -> None:
        self._job = job
        engine = EngineLayout(layout.engine_dir)
        self._server, base_url = start_llama_server(
            LlamaConfig(exe=layout.llama_server, model=model), layout.logs_dir / "llama-server.log", job=job
        )
        try:
            self._worker = WorkerClient(worker_argv(engine), engine.root, layout.logs_dir / "worker.log", job=job)
            self._worker.start()
        except BaseException:
            self._server.stop()
            raise
        self.cache = TranslationCache(layout.cache_dir, model.name)
        translator = Translator(base_url, model.stem)
        self.scheduler = Scheduler(
            lambda pages, index: process_page(
                pages, index, scan=self._worker.scan, translate=translator.translate, cache=self.cache
            ),
            is_done=lambda page: self.cache.get(page) is not None,
        )

    def close(self) -> None:
        self.scheduler.stop()
        self._worker.stop()
        self._server.stop()
        self._job.close()


class AppState:
    def __init__(
        self,
        layout: AppLayout,
        dialogs: Dialogs,
        runtime_factory: Callable[[AppLayout, Path, KillOnCloseJob], object] = Runtime,
    ) -> None:
        self.layout = layout
        self.dialogs = dialogs
        self._runtime_factory = runtime_factory
        self.settings = load_settings(layout.settings_path)
        self._lock = threading.Lock()
        self.task: str | None = None
        self.cancel = threading.Event()
        self.task_job: KillOnCloseJob | None = None
        self.log: deque[str] = deque(maxlen=300)
        self.message = ""
        self.error = ""
        self.runtime = None
        self.runtime_status = "stopped"  # stopped | starting | ready | error
        self.library_root: Path | None = None
        self.books: list[Book] = []
        if self.settings.last_library and Path(self.settings.last_library).is_dir():
            self._load_library(Path(self.settings.last_library))

    # --- state ---

    def _save(self) -> None:
        save_settings(self.settings, self.layout.settings_path)

    def _log(self, line: str) -> None:
        self.log.append(line)
        logger.info(line)

    def _ready(self, key: str) -> bool:
        if key == "engine":
            return EngineLayout(self.layout.engine_dir).is_ready()
        if key == "llama":
            return components.llama_ready(self.layout)
        return components.model_ready(self.layout)

    def can_start(self) -> bool:
        return (
            self.task is None
            and self.runtime is None
            and self._ready("engine")
            and self._ready("llama")
            and effective_model(self.layout, self.settings) is not None
        )

    def state(self) -> dict:
        model = effective_model(self.layout, self.settings)
        rows = []
        for key, label, size in COMPONENTS:
            ready = self._ready(key)
            status = model_status_text(self.layout, self.settings) if key == "model" else component_status_text(ready, size)
            rows.append({"key": key, "label": label, "ready": ready, "status": status})
        return {
            "components": rows,
            "model": model.stem if model else "",
            "task": self.task,
            "log": list(self.log),
            "message": self.message,
            "error": self.error,
            "runtime": self.runtime_status,
            "can_start": self.can_start(),
            "languages": LANGUAGES,
            "page_direction": self.settings.page_direction,
        }

    # --- one background task at a time ---

    def _launch(self, kind: str, work: Callable[[], str]) -> None:
        with self._lock:
            if self.task is not None:
                raise ApiError(409, "다른 작업이 진행 중입니다.")
            self.task = kind
            self.cancel = threading.Event()
            self.task_job = None
            self.message = ""
            self.error = ""
            self.log.clear()
        threading.Thread(target=self._run, args=(work,), daemon=True).start()

    def _run(self, work: Callable[[], str]) -> None:
        try:
            self.message = work()
        except Cancelled:
            self.message = STOPPED_MESSAGE
        except Exception as e:
            if self.cancel.is_set():
                self.message = STOPPED_MESSAGE  # a killed process failing is part of stopping
            elif isinstance(e, (InstallError, ServerStartError, WorkerError, TranslateError)):
                self.error = str(e)
            else:
                logger.exception("task failed")
                self.error = f"예상하지 못한 오류: {e!r}"
        finally:
            with self._lock:
                self.task = None
                self.task_job = None

    def install(self, kind: str) -> dict:
        if kind == "engine":
            uv = find_uv(self.layout)
            if uv is None:
                raise ApiError(409, "uv를 찾을 수 없습니다. 빌드 스크립트로 프로그램을 다시 만들어 주세요.")

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

        elif kind == "llama":

            def work() -> str:
                components.install_llama(self.layout, log=self._log, cancel=self.cancel)
                return "llama.cpp 설치가 끝났습니다."

        elif kind == "model":

            def work() -> str:
                components.install_model(self.layout, log=self._log, cancel=self.cancel)
                return "번역 모델 설치가 끝났습니다."

        else:
            raise ApiError(404, f"알 수 없는 구성 요소: {kind}")
        self._launch(kind, work)
        return self.state()

    def cancel_task(self) -> dict:
        if self.task is not None:
            self.cancel.set()
            job = self.task_job
            if job is not None:
                job.close()  # ends uv, llama-server or the worker right away
            self._log("중단하는 중...")
        return self.state()

    def start(self) -> dict:
        if self.runtime is not None:
            return self.state()
        model = effective_model(self.layout, self.settings)
        if not self.can_start() or model is None:
            raise ApiError(409, "구성 요소를 모두 설치한 뒤 시작하세요.")

        def work() -> str:
            job = KillOnCloseJob()
            self.task_job = job
            self.runtime_status = "starting"
            self._log("번역 엔진과 LLM 서버를 시작하는 중... (처음에는 1분 정도 걸릴 수 있습니다)")
            try:
                self.runtime = self._runtime_factory(self.layout, model, job)
            except BaseException:
                job.close()
                self.runtime_status = "stopped" if self.cancel.is_set() else "error"
                raise
            self.runtime_status = "ready"
            return "번역 준비가 끝났습니다."

        self._launch("start", work)
        return self.state()

    def pick_model(self) -> dict:
        if self.runtime is not None or self.task is not None:
            raise ApiError(409, "번역 엔진이 실행 중일 때는 모델을 바꿀 수 없습니다.")
        path = self.dialogs.pick_model()
        if path:
            self.settings.model = path
            self._save()
        return self.state()

    # --- library ---

    def _load_library(self, root: Path) -> None:
        self.library_root = root
        self.books = scan_library(root)

    def open_library(self) -> dict:
        path = self.dialogs.pick_folder()
        if path:
            root = Path(path)
            self._load_library(root)
            self.settings.last_library = str(root)
            self._save()
        return self.library_json()

    def library_json(self) -> dict:
        return {
            "root": str(self.library_root) if self.library_root else "",
            "books": [
                {
                    "id": book.id,
                    "title": book.title,
                    "pages": len(book.pages),
                    "position": min(self.settings.positions.get(str(book.dir), 0), len(book.pages) - 1),
                }
                for book in self.books
            ],
        }

    def _page(self, book_id: int, index: int) -> tuple[Book, Path]:
        if not 0 <= book_id < len(self.books):
            raise ApiError(404, "책을 찾을 수 없습니다.")
        book = self.books[book_id]
        if not 0 <= index < len(book.pages):
            raise ApiError(404, "페이지를 찾을 수 없습니다.")
        path = book.pages[index]
        if self.library_root is None or not is_inside(self.library_root, path):
            raise ApiError(403, "열린 폴더 밖의 파일입니다.")
        return book, path

    def image(self, book_id: int, index: int) -> Response:
        _, path = self._page(book_id, index)
        try:
            data = path.read_bytes()
        except OSError as e:
            raise ApiError(404, f"이미지를 읽을 수 없습니다: {e}") from e
        return Response(data, IMAGE_TYPES.get(path.suffix.lower(), "application/octet-stream"))

    def _running(self):
        runtime = self.runtime
        if runtime is None:
            raise ApiError(409, "번역 엔진이 시작되지 않았습니다.")
        return runtime

    def translation(self, book_id: int, index: int) -> dict:
        book, path = self._page(book_id, index)
        runtime = self._running()
        runtime.scheduler.focus(book.pages, index)
        result = runtime.cache.get(path)
        if result is not None:
            return {"status": "done", **result.to_json()}
        status, error = runtime.scheduler.status(path)
        return {"status": status, "error": error}

    def retry(self, book_id: int, index: int) -> dict:
        book, _ = self._page(book_id, index)
        self._running().scheduler.retry(book.pages, index)
        return {"status": "pending", "error": ""}

    def save_position(self, book_id: int, index: int) -> dict:
        book, _ = self._page(book_id, index)
        self.settings.positions[str(book.dir)] = index
        self._save()
        return {}

    def set_page_direction(self, value: str) -> dict:
        if value not in PAGE_DIRECTIONS:
            raise ApiError(400, f"넘기는 방향 값이 올바르지 않습니다: {value}")
        self.settings.page_direction = value
        self._save()
        return self.state()

    def shutdown(self) -> None:
        self.cancel_task()
        runtime, self.runtime = self.runtime, None
        self.runtime_status = "stopped"
        if runtime is not None:
            runtime.close()


def _int_arg(query: dict[str, str], name: str) -> int:
    try:
        return int(query[name])
    except (KeyError, ValueError):
        raise ApiError(400, f"{name} 값이 올바르지 않습니다.") from None


def build_routes(state: AppState) -> dict[tuple[str, str], Route]:
    def page(method: Callable[[int, int], object]) -> Route:
        return lambda query: method(_int_arg(query, "book"), _int_arg(query, "index"))

    return {
        ("GET", "/api/state"): lambda query: state.state(),
        ("POST", "/api/install/engine"): lambda query: state.install("engine"),
        ("POST", "/api/install/llama"): lambda query: state.install("llama"),
        ("POST", "/api/install/model"): lambda query: state.install("model"),
        ("POST", "/api/cancel"): lambda query: state.cancel_task(),
        ("POST", "/api/model"): lambda query: state.pick_model(),
        ("POST", "/api/start"): lambda query: state.start(),
        ("POST", "/api/library/open"): lambda query: state.open_library(),
        ("GET", "/api/library"): lambda query: state.library_json(),
        ("GET", "/api/image"): page(state.image),
        ("GET", "/api/translation"): page(state.translation),
        ("POST", "/api/retry"): page(state.retry),
        ("POST", "/api/progress"): page(state.save_position),
        ("POST", "/api/settings"): lambda query: state.set_page_direction(query.get("page_direction", "")),
    }
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS. 이어서 `uv run pytest -q`로 전체도 통과하는지 확인한다.

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/app.py tests/test_app.py
git commit -F <메시지 파일>   # 제목: Add viewer app state and API routes
```

---

### Task 9: 창과 웹 화면

**Files:**
- Modify: `src/manga_translate/app.py` (창 연결: `WEB_DIR`, `WindowDialogs`, `reset_logs`, `main`)
- Create: `src/manga_translate/web/index.html`, `src/manga_translate/web/app.js`, `src/manga_translate/web/style.css`
- Modify: `pyproject.toml` (`pywebview` 의존성, gui-script 진입점), `src/manga_translate/__main__.py`
- Test: `tests/test_window.py`

**Interfaces:**
- Consumes: `AppState`, `build_routes`, `TITLE` (Task 8); `make_server`, `TOKEN_PLACEHOLDER` (Task 7); `AppLayout`, `app_dir`, `uv_environment` (`paths.py`)
- Produces: `WEB_DIR: Path`, `WindowDialogs` (`.window` 속성, `pick_folder()`, `pick_model()`), `reset_logs(logs_dir: Path) -> None`, `main() -> int`
- pywebview API: `webview.create_window(title, url, width=, height=, min_size=)`, `webview.start()`, `window.create_file_dialog(webview.FileDialog.FOLDER)`, `window.create_file_dialog(webview.FileDialog.OPEN, file_types=("GGUF 모델 (*.gguf)",))` → 선택한 경로 튜플 또는 `None`

- [ ] **Step 1: 의존성 추가와 API 확인**

`pyproject.toml`에서:

```toml
dependencies = [
    "httpx>=0.27",
    "natsort>=8.4",
    "pywebview>=5.3",
]

[project.gui-scripts]
manga-translate = "manga_translate.app:main"
```

`src/manga_translate/__main__.py`:

```python
from .app import main

raise SystemExit(main())
```

Run: `uv sync`
Run: `uv run python -c "import webview; print(webview.__version__ if hasattr(webview, '__version__') else 'ok', webview.FileDialog.FOLDER, webview.FileDialog.OPEN)"`
Expected: 오류 없이 출력. `FileDialog`가 없으면 설치된 pywebview 버전을 확인하고 `pywebview>=5.3`이 설치됐는지 본다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_window.py`:

```python
import sys
import types

from manga_translate.app import WEB_DIR, WindowDialogs, reset_logs
from manga_translate.server import TOKEN_PLACEHOLDER


def test_web_files_are_packaged_and_carry_the_token():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert f"/static/app.js?token={TOKEN_PLACEHOLDER}" in html
    assert f"/static/style.css?token={TOKEN_PLACEHOLDER}" in html
    assert (WEB_DIR / "app.js").is_file()
    assert (WEB_DIR / "style.css").is_file()
    for element_id in ("setup", "library", "reader", "page-image", "overlay", "components", "books"):
        assert f'id="{element_id}"' in html


def test_reset_logs_removes_last_run_logs(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    for name in ("app.log", "worker.log", "llama-server.log"):
        (logs / name).write_text("old", encoding="utf-8")
    (logs / "keep.txt").write_text("x", encoding="utf-8")
    reset_logs(logs)
    assert sorted(p.name for p in logs.iterdir()) == ["keep.txt"]
    reset_logs(tmp_path / "new-logs")
    assert (tmp_path / "new-logs").is_dir()


class FakeWindow:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create_file_dialog(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        return self.result


def test_window_dialogs(monkeypatch):
    fake = types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER="folder", OPEN="open"))
    monkeypatch.setitem(sys.modules, "webview", fake)
    dialogs = WindowDialogs()
    dialogs.window = FakeWindow(("C:/만화",))
    assert dialogs.pick_folder() == "C:/만화"
    assert dialogs.window.calls == [("folder", {})]
    dialogs.window = FakeWindow(("C:/m.gguf",))
    assert dialogs.pick_model() == "C:/m.gguf"
    assert dialogs.window.calls[0][0] == "open"
    dialogs.window = FakeWindow(None)
    assert dialogs.pick_folder() is None
    assert dialogs.pick_model() is None
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_window.py -v`
Expected: FAIL (`ImportError: cannot import name 'WEB_DIR'`)

- [ ] **Step 4: 창 연결 구현**

`src/manga_translate/app.py` 맨 위 import에 추가:

```python
import os
import secrets
```

그리고 `from .paths import AppLayout, find_uv`를 다음으로 바꾼다:

```python
from .paths import AppLayout, app_dir, find_uv, uv_environment
```

`from .server import ApiError, Response, Route`를 다음으로 바꾼다:

```python
from .server import ApiError, Response, Route, make_server
```

`TITLE` 정의 아래에 추가:

```python
WEB_DIR = Path(__file__).parent / "web"
LOG_FILES = ("app.log", "worker.log", "llama-server.log")
```

파일 끝에 추가:

```python
class WindowDialogs:
    """Windows file dialogs owned by the viewer window."""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self) -> str | None:
        import webview

        result = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    def pick_model(self) -> str | None:
        import webview

        result = self.window.create_file_dialog(webview.FileDialog.OPEN, file_types=("GGUF 모델 (*.gguf)",))
        return result[0] if result else None


def reset_logs(logs_dir: Path) -> None:
    """Each run starts with fresh logs."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    for name in LOG_FILES:
        (logs_dir / name).unlink(missing_ok=True)


def main() -> int:
    import webview

    layout = AppLayout(app_dir())
    os.environ.update(uv_environment(layout))  # keep uv's cache and Python inside the program folder
    reset_logs(layout.logs_dir)
    logging.basicConfig(
        filename=str(layout.logs_dir / "app.log"),
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    dialogs = WindowDialogs()
    state = AppState(layout, dialogs)
    if state.can_start():
        state.start()
    token = secrets.token_urlsafe(24)
    server = make_server(build_routes(state), token, WEB_DIR)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    dialogs.window = webview.create_window(TITLE, url, width=1280, height=900, min_size=(800, 600))
    try:
        webview.start()
    finally:
        server.shutdown()
        state.shutdown()  # closing the Job Objects ends llama-server, the worker and any install
    return 0
```

- [ ] **Step 5: 웹 파일 작성**

`src/manga_translate/web/index.html`:

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>manga-translate</title>
<link rel="stylesheet" href="/static/style.css?token={{TOKEN}}">
</head>
<body>
<section id="setup" hidden>
  <h1>manga-translate</h1>
  <p id="setup-languages" class="muted"></p>
  <table id="components"></table>
  <div class="actions">
    <button id="start">시작</button>
    <button id="cancel">중단</button>
  </div>
  <p id="setup-message"></p>
  <pre id="log"></pre>
</section>

<section id="library" hidden>
  <header class="bar">
    <button id="open-folder">폴더 열기</button>
    <span id="library-root" class="muted"></span>
    <span class="spacer"></span>
    <button id="to-setup">구성 요소</button>
  </header>
  <p id="library-empty" class="muted">"폴더 열기"로 만화 폴더를 고르세요. 하위 폴더마다 한 권으로 보여줍니다.</p>
  <div id="books"></div>
</section>

<section id="reader" hidden>
  <header class="bar">
    <button id="to-library">책장</button>
    <span id="book-title"></span>
    <span id="page-number" class="muted"></span>
    <span id="page-status"></span>
    <button id="retry" hidden>다시 번역</button>
    <span class="spacer"></span>
    <span id="reader-model" class="muted"></span>
    <span id="reader-languages" class="muted"></span>
    <label><input type="checkbox" id="overlay-toggle" checked> 번역 표시 (T)</label>
    <select id="direction">
      <option value="rtl">일본식 (← 다음)</option>
      <option value="ltr">서양식 (→ 다음)</option>
    </select>
  </header>
  <main id="stage">
    <div id="page">
      <img id="page-image" alt="">
      <div id="overlay"></div>
    </div>
  </main>
</section>

<script src="/static/app.js?token={{TOKEN}}"></script>
</body>
</html>
```

`src/manga_translate/web/app.js`:

```js
"use strict";

const TOKEN = new URLSearchParams(location.search).get("token") || "";
const $ = (id) => document.getElementById(id);

function withToken(path) {
  return `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}`;
}

async function api(path, method = "GET") {
  const response = await fetch(withToken(path), { method });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function imageUrl(book, index) {
  return withToken(`/api/image?book=${book}&index=${index}`);
}

let appState = null;
let library = { root: "", books: [] };
const reader = { book: null, index: 0, request: 0, timer: null, result: null, lastWheel: 0 };

// ---------- screens ----------

function showScreen(name) {
  for (const id of ["setup", "library", "reader"]) $(id).hidden = id !== name;
}

function route() {
  const match = location.hash.match(/^#\/read\/(\d+)\/(\d+)$/);
  if (match) {
    openPage(Number(match[1]), Number(match[2]));
    return;
  }
  stopPolling();
  reader.book = null;
  if (location.hash === "#/library") {
    showScreen("library");
    loadLibrary();
    return;
  }
  showScreen("setup");
  renderSetup();
}

window.addEventListener("hashchange", route);

async function refreshState() {
  try {
    appState = await api("/api/state");
  } catch (e) {
    return;
  }
  if (!$("setup").hidden) renderSetup();
  renderReaderInfo();
  if (appState.runtime === "ready" && (location.hash === "" || location.hash === "#/")) {
    location.hash = "#/library";
  }
}

// ---------- setup ----------

async function act(path) {
  try {
    appState = await api(path, "POST");
  } catch (e) {
    alert(e.message);
  }
  renderSetup();
}

function makeButton(label, onClick, disabled) {
  const button = document.createElement("button");
  button.textContent = label;
  button.disabled = disabled;
  button.onclick = onClick;
  return button;
}

function renderSetup() {
  if (!appState) return;
  const busy = appState.task !== null;
  $("setup-languages").textContent = appState.languages;
  $("components").replaceChildren(
    ...appState.components.map((c) => {
      const row = document.createElement("tr");
      const label = document.createElement("td");
      label.textContent = c.label;
      const status = document.createElement("td");
      status.textContent = c.status;
      const actions = document.createElement("td");
      actions.append(makeButton("설치", () => act(`/api/install/${c.key}`), busy || c.ready));
      if (c.key === "model") {
        actions.append(makeButton("변경...", () => act("/api/model"), busy || appState.runtime !== "stopped"));
      }
      row.append(label, status, actions);
      return row;
    })
  );
  const ready = appState.runtime === "ready";
  $("start").textContent = ready ? "책장으로" : appState.runtime === "starting" ? "시작하는 중..." : "시작";
  $("start").disabled = !(ready || appState.can_start);
  $("cancel").disabled = !busy;
  const message = $("setup-message");
  message.textContent = appState.error || appState.message;
  message.className = appState.error ? "error" : "";
  const log = $("log");
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 4;
  log.textContent = appState.log.join("\n");
  if (atBottom) log.scrollTop = log.scrollHeight;
}

$("start").onclick = () => {
  if (appState && appState.runtime === "ready") location.hash = "#/library";
  else act("/api/start");
};
$("cancel").onclick = () => act("/api/cancel");
$("to-setup").onclick = () => (location.hash = "#/setup");

// ---------- library ----------

async function loadLibrary() {
  try {
    library = await api("/api/library");
  } catch (e) {
    alert(e.message);
    return;
  }
  renderLibrary();
}

function renderLibrary() {
  $("library-root").textContent = library.root;
  $("library-empty").hidden = library.books.length > 0;
  $("books").replaceChildren(
    ...library.books.map((book) => {
      const card = document.createElement("a");
      card.className = "book";
      card.href = `#/read/${book.id}/${book.position}`;
      const cover = document.createElement("img");
      cover.loading = "lazy";
      cover.src = imageUrl(book.id, 0);
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = book.title;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${book.position + 1} / ${book.pages}쪽`;
      card.append(cover, title, meta);
      return card;
    })
  );
}

$("open-folder").onclick = async () => {
  try {
    library = await api("/api/library/open", "POST");
  } catch (e) {
    alert(e.message);
  }
  renderLibrary();
};

// ---------- reader ----------

function stopPolling() {
  if (reader.timer !== null) clearTimeout(reader.timer);
  reader.timer = null;
}

function setStatus(text, failed = false) {
  $("page-status").textContent = text;
  $("page-status").className = failed ? "failed" : "";
  $("retry").hidden = !failed;
}

function renderReaderInfo() {
  if (!appState) return;
  $("reader-model").textContent = appState.model;
  $("reader-languages").textContent = appState.languages;
  $("direction").value = appState.page_direction;
}

async function openPage(bookId, index) {
  showScreen("reader");
  if (!library.books[bookId]) await loadLibrary();
  const book = library.books[bookId];
  if (!book) {
    location.hash = "#/library";
    return;
  }
  index = Math.max(0, Math.min(index, book.pages - 1));
  stopPolling();
  reader.book = bookId;
  reader.index = index;
  reader.result = null;
  reader.request += 1;
  $("book-title").textContent = book.title;
  $("page-number").textContent = `${index + 1} / ${book.pages}`;
  $("overlay").replaceChildren();
  setStatus("번역 대기");
  $("page-image").src = imageUrl(bookId, index);
  if (index + 1 < book.pages) new Image().src = imageUrl(bookId, index + 1);
  book.position = index;
  api(`/api/progress?book=${bookId}&index=${index}`, "POST").catch(() => {});
  renderReaderInfo();
  pollTranslation(reader.request);
}

function pollTranslation(request) {
  api(`/api/translation?book=${reader.book}&index=${reader.index}`)
    .then((data) => {
      if (request !== reader.request) return;
      if (data.status === "done") {
        reader.result = data;
        setStatus(data.blocks.length ? "번역 완료" : "대사 없음");
        drawOverlay();
        return;
      }
      if (data.status === "failed") {
        setStatus(`번역 실패: ${data.error}`, true);
        return;
      }
      setStatus(data.status === "working" ? "번역 중..." : "번역 대기");
      reader.timer = setTimeout(() => pollTranslation(request), 500);
    })
    .catch((e) => {
      if (request !== reader.request) return;
      setStatus(e.message, true);
    });
}

$("retry").onclick = async () => {
  try {
    await api(`/api/retry?book=${reader.book}&index=${reader.index}`, "POST");
  } catch (e) {
    setStatus(e.message, true);
    return;
  }
  reader.request += 1;
  setStatus("번역 대기");
  pollTranslation(reader.request);
};

function drawOverlay() {
  const overlay = $("overlay");
  overlay.replaceChildren();
  const result = reader.result;
  if (!result || !$("overlay-toggle").checked) return;
  const [width, height] = result.size;
  for (const block of result.blocks) {
    const [x1, y1, x2, y2] = block.xyxy;
    const box = document.createElement("div");
    box.className = "bubble";
    box.style.left = `${(x1 / width) * 100}%`;
    box.style.top = `${(y1 / height) * 100}%`;
    box.style.width = `${((x2 - x1) / width) * 100}%`;
    box.style.height = `${((y2 - y1) / height) * 100}%`;
    box.title = block.text;
    const text = document.createElement("span");
    text.textContent = block.translation || block.text;
    box.append(text);
    overlay.append(box);
  }
  fitText();
}

// The largest font size at which each translation still fits its box.
function fitText() {
  for (const box of $("overlay").children) {
    let low = 6;
    let high = 72;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      box.style.fontSize = `${mid}px`;
      if (box.scrollHeight <= box.clientHeight && box.scrollWidth <= box.clientWidth) low = mid;
      else high = mid - 1;
    }
    box.style.fontSize = `${low}px`;
  }
}

$("page-image").addEventListener("load", drawOverlay);
window.addEventListener("resize", fitText);
$("overlay-toggle").onchange = drawOverlay;

$("direction").onchange = async () => {
  try {
    appState = await api(`/api/settings?page_direction=${$("direction").value}`, "POST");
  } catch (e) {
    alert(e.message);
  }
  renderReaderInfo();
};

$("to-library").onclick = () => (location.hash = "#/library");

function go(delta) {
  if (reader.book === null) return;
  const book = library.books[reader.book];
  const next = reader.index + delta;
  if (!book || next < 0 || next >= book.pages) return;
  location.hash = `#/read/${reader.book}/${next}`;
}

function rightToLeft() {
  return !appState || appState.page_direction !== "ltr";
}

document.addEventListener("keydown", (event) => {
  if ($("reader").hidden || event.target.tagName === "SELECT") return;
  if (event.key === "t" || event.key === "T") {
    $("overlay-toggle").checked = !$("overlay-toggle").checked;
    drawOverlay();
  } else if (event.key === "ArrowLeft") {
    go(rightToLeft() ? 1 : -1);
  } else if (event.key === "ArrowRight") {
    go(rightToLeft() ? -1 : 1);
  } else if (event.key === "PageDown" || event.key === " ") {
    go(1);
  } else if (event.key === "PageUp") {
    go(-1);
  }
});

$("stage").addEventListener("click", (event) => {
  const leftHalf = event.clientX < window.innerWidth / 2;
  go(leftHalf === rightToLeft() ? 1 : -1);
});

$("stage").addEventListener(
  "wheel",
  (event) => {
    const now = Date.now();
    if (now - reader.lastWheel < 250) return;
    reader.lastWheel = now;
    go(event.deltaY > 0 ? 1 : -1);
  },
  { passive: true }
);

// ---------- start ----------

refreshState().then(route);
setInterval(refreshState, 1000);
```

`src/manga_translate/web/style.css`:

```css
:root {
  color-scheme: dark;
  --bg: #1b1b1f;
  --panel: #26262c;
  --line: #3a3a42;
  --text: #e8e8ea;
  --muted: #9a9aa3;
  --danger: #ff6b6b;
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }

html, body {
  margin: 0;
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: "Malgun Gothic", "Segoe UI", sans-serif;
}

button, select {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 12px;
  font: inherit;
  cursor: pointer;
}
button:disabled { opacity: 0.45; cursor: default; }
.muted { color: var(--muted); }
.error, .failed { color: var(--danger); }
.spacer { flex: 1; }

#setup { max-width: 760px; margin: 32px auto; padding: 0 16px; }
#components { width: 100%; border-collapse: collapse; margin: 16px 0; }
#components td { padding: 8px 6px; border-bottom: 1px solid var(--line); }
#components td:last-child { text-align: right; white-space: nowrap; }
#components button { margin-left: 6px; }
.actions { display: flex; gap: 8px; }
#log {
  background: #111114;
  padding: 10px;
  height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 12px;
  color: var(--muted);
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--panel);
  font-size: 14px;
  height: 48px;
}

#library-empty { padding: 24px; }
#books {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px;
  padding: 16px;
}
.book { color: inherit; text-decoration: none; background: var(--panel); border-radius: 8px; overflow: hidden; }
.book img { display: block; width: 100%; aspect-ratio: 3 / 4; object-fit: cover; background: #000; }
.book .title { padding: 6px 8px 0; font-size: 14px; overflow-wrap: anywhere; }
.book .meta { padding: 2px 8px 8px; font-size: 12px; color: var(--muted); }

#reader { height: 100%; display: flex; flex-direction: column; }
#stage {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  user-select: none;
}
#page { position: relative; line-height: 0; }
#page-image { display: block; max-width: 100vw; max-height: calc(100vh - 48px); }
#overlay { position: absolute; inset: 0; line-height: 1.25; }
.bubble {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  text-align: center;
  background: rgba(255, 255, 255, 0.92);
  color: #111;
  border-radius: 6px;
  overflow: hidden;
  word-break: keep-all;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest -q`
Expected: 모두 PASS

- [ ] **Step 7: 개발 환경에서 창 띄워 보기 (GPU 없이 화면만)**

설치된 구성 요소가 없는 임시 폴더로 실행해 설치 화면이 뜨는지만 본다(설치 버튼은 누르지 않는다).

Run (PowerShell): `$env:MANGA_TRANSLATE_HOME = "$env:TEMP\mt-ui-check"; uv run python -m manga_translate`
Expected: "manga-translate" 창이 뜨고 설치 화면에 세 줄(번역 엔진, llama.cpp, 번역 모델)이 "설치 필요"로 보인다. 창을 닫으면 프로세스가 끝난다. 확인 후 `Remove-Item -Recurse -Force "$env:TEMP\mt-ui-check"`로 임시 폴더를 지우고 `Remove-Item Env:MANGA_TRANSLATE_HOME`을 실행한다.

- [ ] **Step 8: 커밋**

```bash
git add pyproject.toml uv.lock src/manga_translate/__main__.py src/manga_translate/app.py src/manga_translate/web tests/test_window.py
git commit -F <메시지 파일>   # 제목: Open the viewer in a pywebview window
```

---

### Task 10: 배치 앱 제거, 문서, 빌드, 실제 확인

**Files:**
- Delete: `src/manga_translate/gui.py`, `src/manga_translate/pipeline.py`, `src/manga_translate/engine_run.py`, `src/manga_translate/scripts/bt_write_config.py`
- Delete: `tests/test_gui.py`, `tests/test_pipeline.py`, `tests/test_engine_run.py`
- Delete: `tests/helpers/fake_bt/ballontranslator/utils/config.py`, `tests/helpers/fake_bt/ballontranslator/utils/llm_profiles.py`, `tests/helpers/fake_bt/ballontranslator/utils/shared.py`
- Modify: `src/manga_translate/engine.py` (`run_streaming` 이동, 모듈 docstring)
- Modify: `src/manga_translate/app.py` (`run_streaming` import 경로)
- Modify: `src/manga_translate/settings.py` (`last_input`, `last_output` 삭제)
- Modify: `tests/test_engine.py` (`run_streaming` 테스트 이동), `tests/test_imports.py`, `tests/test_settings.py`
- Modify: `README.md`, `AGENTS.md`

**Interfaces:**
- Produces: `manga_translate.engine.run_streaming(argv, cwd, *, job=None, on_line=print, stdin_text="exit\n") -> int` (동작은 기존과 같음)

- [ ] **Step 1: `run_streaming`을 `engine.py`로 옮기기**

`src/manga_translate/engine_run.py`의 `run_streaming` 함수 전체(시그니처부터 `finally` 블록까지)를 `src/manga_translate/engine.py`의 `run_checked` 함수 아래로 그대로 옮긴다. `engine.py`에 필요한 import를 추가한다:

```python
import os
```

그리고 `from typing import Callable, Sequence`는 이미 있으므로 그대로 두고, `KillOnCloseJob` 타입을 쓰기 위해 추가한다:

```python
from .winjob import KillOnCloseJob
```

`engine.py`의 모듈 docstring을 다음으로 바꾼다:

```python
"""Install and locate the BallonsTranslator engine (GPL-3.0).

The engine does text detection and OCR in its own venv. We install it and run
scripts/bt_worker.py with its Python; we never import its modules here.
"""
```

`run_streaming` 안의 주석 `# Headless mode asks for more folders when done; a queued "exit" makes it quit.`을 다음으로 바꾼다:

```python
            # Input the program needs is written up front, then stdin is closed.
```

`src/manga_translate/app.py`에서 `from .engine_run import run_streaming`을 지우고 `from .engine import EngineError, EngineLayout, setup_engine`을 다음으로 바꾼다:

```python
from .engine import EngineError, EngineLayout, run_streaming, setup_engine
```

- [ ] **Step 2: 테스트 이동**

`tests/test_engine_run.py`의 `run_streaming` 테스트 네 개(`test_run_streaming_passes_output_stdin_and_cwd`, `test_run_streaming_returns_exit_code`, `test_run_streaming_sets_no_proxy`, `test_run_streaming_kills_process_when_consumer_fails`)를 `tests/test_engine.py` 끝으로 그대로 옮긴다. `tests/test_engine.py` 위쪽에 필요한 import를 추가한다(이미 있으면 중복하지 않는다):

```python
import sys
import time

import pytest

from manga_translate.engine import run_streaming

PYTHON = getattr(sys, "_base_executable", sys.executable)
```

- [ ] **Step 3: 옛 코드와 테스트 삭제**

```bash
git rm src/manga_translate/gui.py src/manga_translate/pipeline.py src/manga_translate/engine_run.py src/manga_translate/scripts/bt_write_config.py
git rm tests/test_gui.py tests/test_pipeline.py tests/test_engine_run.py
git rm tests/helpers/fake_bt/ballontranslator/utils/config.py tests/helpers/fake_bt/ballontranslator/utils/llm_profiles.py tests/helpers/fake_bt/ballontranslator/utils/shared.py
```

- [ ] **Step 4: 설정에서 옛 필드 삭제**

`src/manga_translate/settings.py`의 `Settings`에서 `last_input`, `last_output` 두 줄을 지우고, `load_settings`의 문자열 필드 목록을 다음으로 바꾼다:

```python
    for name in ("model", "last_library"):
```

`tests/test_settings.py`의 `test_old_and_unknown_keys_are_ignored`를 다음으로 바꾼다:

```python
def test_old_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"model": "m.gguf", "llama_server": "x", "last_input": "D:/a", "last_output": "D:/b"}),
        encoding="utf-8",
    )
    assert load_settings(path) == Settings(model="m.gguf")
```

- [ ] **Step 5: import 테스트 갱신**

`tests/test_imports.py` 전체:

```python
import subprocess
import sys


def test_engine_modules_are_never_imported_by_the_app():
    code = (
        "import sys\n"
        "import manga_translate.app, manga_translate.server, manga_translate.scheduler, manga_translate.worker_client, "
        "manga_translate.translate, manga_translate.cache, manga_translate.library, manga_translate.engine, "
        "manga_translate.components, manga_translate.download, manga_translate.paths\n"
        "leaked = [m for m in ('torch', 'ballontranslator', 'webview') if m in sys.modules]\n"
        "assert not leaked, leaked\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 6: 남은 참조 확인과 전체 테스트**

Run: `git grep -n "engine_run\|pipeline\|bt_write_config\|manga_translate.gui\|last_input\|last_output" -- src tests pyproject.toml`
Expected: 결과 없음

Run: `uv run pytest -q`
Expected: 모두 PASS

- [ ] **Step 7: 문서 갱신**

`AGENTS.md`의 `- GUI 프로그램만 유지한다. CLI를 추가하지 않는다.`를 다음으로 바꾼다:

```
- 뷰어 앱(pywebview 창)만 유지한다. CLI를 추가하지 않는다.
```

`AGENTS.md`의 첫 설명 두 줄을 다음으로 바꾼다:

```
manga-translate는 일본 만화 이미지를 한 장씩 보여주며 로컬 LLM으로 한국어 번역을 겹쳐 보여주는 Windows 뷰어 앱입니다.
검출·OCR은 BallonsTranslator(엔진 venv의 상주 워커), 번역은 llama-server가 맡습니다. 사용법은 README.md를 봅니다.
```

`README.md` 전체:

````markdown
# manga-translate

일본 만화 이미지 폴더를 한 장씩 보여주면서, 로컬 LLM으로 말풍선을 한국어로 번역해 그림 위에 겹쳐 보여주는 Windows 뷰어입니다.
검출·OCR은 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은
[llama.cpp](https://github.com/ggml-org/llama.cpp)의 llama-server와 Gemma 4 모델이 맡습니다. 필요한 것은 모두 프로그램 창에서 설치합니다.

## 요구 사항

- Windows 10/11, NVIDIA RTX 30 시리즈 이상 그래픽카드
- Microsoft Edge WebView2 런타임 (Windows 11에는 기본 포함)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 여유 디스크 공간 약 12GB

## 설치

```powershell
git clone https://github.com/kyj0503/manga-translate.git
cd manga-translate
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

`%USERPROFILE%\Downloads\manga-translate`에 프로그램 폴더가 만들어집니다. 다른 곳에 만들려면 `-Dest <폴더>`를 붙입니다.
프로그램이 받거나 만드는 파일(엔진, llama.cpp, 모델, 설정, 번역 캐시, 로그)은 모두 이 폴더 안에만 저장됩니다.
폴더를 지우면 전부 함께 지워집니다. 만화 폴더에는 아무것도 쓰지 않습니다.

## 사용법

1. 프로그램 폴더의 `manga-translate` 바로가기를 실행합니다.
2. 처음에는 구성 요소 화면이 나옵니다. 세 줄에서 각각 "설치"를 누릅니다.
   - 번역 엔진: 약 6GB, 수십 분 걸릴 수 있습니다.
   - llama.cpp: 약 0.6GB
   - 번역 모델(Gemma 4 E4B): 약 5GB
3. "시작"을 누르면 번역 엔진과 LLM 서버가 켜지고 책장으로 넘어갑니다. 다음부터는 자동으로 시작합니다.
4. "폴더 열기"로 만화 폴더를 고릅니다. 이미지가 들어 있는 폴더(하위 폴더 포함)마다 한 권으로 보여줍니다.
5. 책을 고르면 페이지가 열리고, 몇 초 뒤 번역이 말풍선 위에 겹쳐 보입니다. 다음 몇 장은 미리 번역해 둡니다.

| 조작 | 동작 |
|---|---|
| ← / → , 화면 왼쪽·오른쪽 클릭, 마우스 휠 | 페이지 넘기기 (방향은 상단 바에서 일본식/서양식 선택) |
| T | 번역 표시 켜기/끄기 (원문 보기) |
| 번역 칸에 마우스 올리기 | 원문 보기 |

한 번 번역한 페이지는 저장해 두었다가 다시 열면 바로 보여줍니다. 설치 중에 "중단"을 누르면 멈추고, 다시 "설치"를 누르면
받던 곳부터 이어서 진행합니다. 다른 GGUF 모델을 쓰려면 구성 요소 화면에서 "변경..."으로 고릅니다.
문제가 생기면 프로그램 폴더의 `logs\`를 확인합니다.

## 개발

```powershell
uv sync
uv run pytest
```

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
````

- [ ] **Step 8: 커밋**

```bash
git add -A src tests README.md AGENTS.md
git status --short   # 의도한 파일만 들어갔는지 확인
git diff --cached --check
git commit -F <메시지 파일>   # 제목: Replace the batch window with the viewer app
```

- [ ] **Step 9: 빌드와 설치 확인**

번역 엔진, llama-server, 워커가 실행 중이 아닌지 확인한 뒤 빌드한다.

Run: `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`
Expected: `Built: C:\Users\serial\Downloads\manga-translate`. "액세스가 거부되었습니다"로 실패하면 앱이 실행 중이 아닌지 확인하고 한 번 더 실행한다.

Run: `diff -rq src/manga_translate "$USERPROFILE/Downloads/manga-translate/.venv/Lib/site-packages/manga_translate" -x __pycache__`
Expected: 출력 없음 (web 폴더와 scripts/bt_worker.py 포함)

Run: `"$USERPROFILE/Downloads/manga-translate/.venv/Scripts/python.exe" -c "import manga_translate.app, webview; print('ok')"`
Expected: `ok`

- [ ] **Step 10: 실제 GPU로 번역 흐름 확인 (창 없이, `(페그오`만 사용)**

세션 scratchpad에 스크립트를 만든다(저장소에 넣지 않는다). E2B 모델로 GPU 부담을 줄인다.

```python
"""Throwaway check: the real engine, worker and llama-server translate the allowed sample folder."""
import time
from pathlib import Path

from manga_translate.app import AppState
from manga_translate.paths import AppLayout

SAMPLES = r"C:\Users\serial\Downloads\(페그오"
E2B = r"C:\Users\serial\source\manga-translate\.dev\models\gemma-4-e2b\gemma-4-E2B-it-Q4_K_M.gguf"


class Dialogs:
    def pick_folder(self):
        return SAMPLES

    def pick_model(self):
        return None


layout = AppLayout(Path(r"C:\Users\serial\Downloads\manga-translate"))
state = AppState(layout, Dialogs())
state.settings.model = E2B  # not saved: only this run uses E2B
started = time.monotonic()
state.start()
while state.task is not None:
    time.sleep(0.5)
print("runtime:", state.runtime_status, state.error, f"{time.monotonic() - started:.1f}s")
try:
    library = state.open_library()
    print("books:", [(b["title"], b["pages"]) for b in library["books"]])
    for index in range(library["books"][0]["pages"]):
        page_started = time.monotonic()
        while True:
            data = state.translation(0, index)
            if data["status"] in ("done", "failed"):
                break
            time.sleep(0.3)
        blocks = data.get("blocks", [])
        empty = sum(1 for b in blocks if not b["translation"])
        print(f"page {index}: {data['status']} blocks={len(blocks)} empty={empty} {time.monotonic() - page_started:.1f}s {data.get('error', '')}")
finally:
    state.shutdown()
```

Run: `"$USERPROFILE/Downloads/manga-translate/.venv/Scripts/python.exe" <scratchpad>/viewer_check.py`
Expected: `runtime: ready`, 모든 페이지 `done`, `empty=0`. 첫 페이지는 수 초, 다음 페이지들은 미리 번역되어 더 빨리 끝난다.

확인 후:
- `Get-CimInstance Win32_Process`로 `llama-server.exe`와 `bt_worker.py`를 실행하는 python이 남아 있지 않은지 확인한다.
- 이 스크립트가 `settings.json`의 `last_library`를 `(페그오`로 바꿨으므로, 그대로 둬도 된다(허용된 폴더). 번역 캐시(`cache\`)는 E2B 모델 이름으로 저장되어 E4B 사용 시에는 쓰이지 않는다.

- [ ] **Step 11: push**

```bash
git push origin main
git status -sb
```

Expected: `## main...origin/main`, 커밋하지 않은 변경 없음

- [ ] **Step 12: 사용자 확인 요청**

창 조작(폴더 선택 창, 페이지 넘기기, 오버레이 모양, 창 닫을 때 프로세스 종료)은 사용자가 직접 확인한다. 바로가기 실행 → (자동 시작) → 폴더 열기 → 책 선택 → 넘기기 순서를 안내한다.
