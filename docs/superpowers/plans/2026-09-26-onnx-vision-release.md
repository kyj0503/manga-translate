# ONNX 검출·OCR 전환과 포터블 배포 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BallonsTranslator/PyTorch 워커를 CPU ONNX Runtime 기반 검출(comic-text-detector 1280)·OCR(manga-ocr)로 바꾸고, 앱을 포터블 zip(실행기 + 독립형 Python + llama.cpp + 검출·OCR 모델)으로 배포할 수 있게 한다.

**Architecture:** `manga_translate/vision/` 패키지가 ctd ONNX 실행, BallonsTranslator에서 이식한 말풍선 묶기, manga-ocr ONNX(빔 서치)를 담고, `python -m manga_translate.vision.worker`가 기존 JSON 한 줄 프로토콜로 응답한다. 앱은 같은 Python으로 워커를 띄우며 엔진 설치·uv 관련 코드는 모두 사라진다. 변환 모델 5개 파일은 GitHub Release 에셋 `vision-models-v1.zip`으로 받고, 빌드·패키징 스크립트가 SHA-256을 확인해 `models\`에 푼다.

**Tech Stack:** Python 3.12, onnxruntime(CPU) 1.24.4, numpy 2.5.3, opencv-python-headless 5.0.0.93, Pillow 12.3.0, shapely 2.1.2, pyclipper 1.4.0, jaconv 0.5.0, httpx, pywebview, PowerShell 5.1, .NET Framework csc, uv(개발·패키징 시에만)

**Spec:** `docs/superpowers/specs/2026-09-26-onnx-vision-release-design.md`

## Global Constraints

- 저장소 `C:\Users\serial\source\manga-translate`, 브랜치 `main`에 직접 커밋한다. push하지 않는다(컨트롤러가 한다). 커밋 작성자는 저장소 로컬 설정 그대로, `--author` 금지, `Co-Authored-By` 트레일러 금지, 메시지는 `-F <파일>`로 넘긴다.
- 줄바꿈은 LF. 커밋 전에 `git diff --cached --check`.
- 테스트: `uv run pytest -q`가 모두 통과해야 한다. 모델이 필요한 테스트는 환경 변수 `MANGA_TRANSLATE_VISION_MODELS`가 가리키는 폴더에 모델이 있을 때만 돌고, 없으면 skip한다. 이 계획을 실행하는 동안 모델 폴더는 `C:\Users\serial\source\manga-translate\.dev\vision-models-v1`이다.
- 앱 코드(`manga_translate`)는 `torch`, `transformers`, `ballontranslator`를 import하지 않는다.
- 검출·OCR은 onnxruntime `CPUExecutionProvider`만 쓴다.
- 실제 이미지로 하는 확인은 `C:\Users\serial\Downloads\sample` 폴더만 쓴다. 다른 이미지 폴더는 열거나 읽지 않는다. 보고서나 출력에 만화 원문·번역을 적지 않는다(개수와 수치만).
- 프로그램이 받거나 만드는 파일은 모두 프로그램 폴더 안에만 둔다. 개발 도구의 임시 파일은 `.dev\`(git 무시) 또는 `dist\`(git 무시)에만 둔다.
- 뷰어 앱만 유지한다. 사용자용 CLI를 추가하지 않는다(개발용 `tools/` 스크립트와 내부 워커 모듈은 예외).
- PowerShell 스크립트의 메시지는 영어(Windows PowerShell 5.1이 BOM 없는 파일을 ANSI로 읽는다).
- 주석은 코드가 하는 일을 쓴다. BallonsTranslator/comic-text-detector에서 옮긴 코드는 파일 머리에 출처 저장소·커밋·GPL-3.0을 적는다.
- 소스를 바꾼 태스크의 마지막에 새로 빌드하는 AGENTS.md 규칙은 이 계획에서 Task 7(개발 빌드 스크립트 완성)부터 적용한다. Task 1~6 동안은 빌드 스크립트가 아직 모델을 설치하지 못하므로 빌드하지 않는다.
- 고정 값:
  - 모델 에셋 URL: `https://github.com/kyj0503/manga-translate/releases/download/vision-models-v1/vision-models-v1.zip`
  - 모델 에셋 zip SHA-256: `011a08838ddd4c7824b4b76e77bde992eec4f3531a0db7bc4cae50c06603949a`, 크기 487724374
  - 에셋이 업로드되기 전에는 로컬 zip `C:\Users\serial\source\manga-translate\.dev\vision-models-v1.zip`을 쓴다.
  - 모델 파일 (경로는 모델 폴더 기준, SHA-256, 크기):
    - `ctd/ctd_1280.onnx` `93b9be7e50caa324b53a2ee8b5cd6931fd77d0849793360fbea84474941401fb` 93760845
    - `manga-ocr/encoder.onnx` `df35f64c2400ea860c70a2d06f2a1f99892374a78c89fcf35308076557a3863f` 343377067
    - `manga-ocr/cross_kv.onnx` `3fb87bc6c884a84469a4ac754d5024bfaf35941c7e646016513a9eaeb1209a51` 9455844
    - `manga-ocr/decoder_step.onnx` `de0f600ca1196ca3c7672b52daa9a2e3dc56f2e27707da538865ac088ac04d3d` 107920310
    - `manga-ocr/vocab.txt` `344fbb6b8bf18c57839e924e2c9365434697e0227fac00b88bb4899b78aa594d` 24072
  - 이식 원본: BallonsTranslator 커밋 `3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8` (`C:\Users\serial\source\manga-translate\.dev\BallonsTranslator`), comic-text-detector 커밋 `440b978563c71b758e31aaa315d100faba1efa2f`.
  - 실험 코드(참고용, 태스크가 끝나면 지워질 수 있음): `C:\Users\serial\source\manga-translate\.dev\spike-onnx\` (`onnx_engine.py`, `ref_run.py`, `compare.py`, venv `.venv`에 onnxruntime-directml과 BallonsTranslator import 경로가 있음). BallonsTranslator 참조 venv: `.dev\BallonsTranslator\.venv\Scripts\python.exe`.

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `pyproject.toml`, `uv.lock` | 비전 의존성 고정, `export` 의존성 그룹 | 1 |
| `src/manga_translate/vision/__init__.py` | 패키지 | 1 |
| `src/manga_translate/vision/models.py` | 모델 파일 목록·확인·설치 | 1 |
| `tools/export/export_ctd.py`, `tools/export/export_decoder_kv.py` | 모델 재변환(개발용, torch 필요) | 1 |
| `src/manga_translate/vision/grouping.py` | 글줄→말풍선 묶기(이식) | 2 |
| `tools/parity/make_grouping_fixtures.py`, `tests/fixtures/vision/*` | 묶기·회귀 기대값 | 2 |
| `src/manga_translate/vision/ctd.py` | ctd ONNX 실행 | 3 |
| `src/manga_translate/vision/ocr.py` | manga-ocr ONNX | 4 |
| `src/manga_translate/vision/engine.py`, `src/manga_translate/vision/worker.py` | 이미지 → 블록, 워커 프로세스 | 5 |
| `src/manga_translate/worker_client.py` | 워커 실행 명령 | 5 |
| `tests/helpers/fake_worker.py` | WorkerClient 테스트용 가짜 워커 | 5 |
| `src/manga_translate/app.py`, `paths.py`, `engine.py`(삭제), `scripts/bt_worker.py`(삭제) | 앱 통합과 엔진 제거 | 6 |
| `scripts/build.ps1` | 개발 빌드: 모델 설치, uv 복사 제거 | 7 |
| `scripts/package.ps1`, `THIRD_PARTY_NOTICES.txt`, `packaging/사용법.txt` | 포터블 zip | 8 |
| `tools/parity/reference_run.py`, `tools/parity/compare_sample.py`, `README.md`, `AGENTS.md` | 실제 페이지 비교 도구, 문서 | 9 |

---

### Task 1: 의존성 고정, 모델 목록·설치, 변환 스크립트

**Files:**
- Modify: `pyproject.toml`
- Create: `src/manga_translate/vision/__init__.py`, `src/manga_translate/vision/models.py`
- Create: `tools/export/export_ctd.py`, `tools/export/export_decoder_kv.py`
- Test: `tests/test_vision_models.py`

**Interfaces:**
- Consumes: `manga_translate.download.download(url, dest, sha256=None, *, log, cancel)`, `extract_zip(archive, dest, *, strip_top, cancel)`, `sha256_of(path) -> str`, `InstallError`, `check_cancel`
- Produces (`vision/models.py`):
  - `MODELS_URL: str`, `MODELS_ZIP_SHA256: str`, `MODELS_ZIP_NAME = "vision-models-v1.zip"`
  - `ModelFile(path: str, sha256: str, size: int)` frozen dataclass; `MODEL_FILES: tuple[ModelFile, ...]` (위 고정 값 5개)
  - `CTD_MODEL = "ctd/ctd_1280.onnx"`, `OCR_DIR = "manga-ocr"`
  - `model_problems(models_dir: Path) -> list[str]` — 파일이 없거나 크기가 다르면 한국어 문장 하나씩(빈 목록이면 정상). 크기만 본다(빠름).
  - `verify_models(models_dir: Path) -> list[str]` — 크기와 SHA-256까지 확인(설치 직후용).
  - `install_models(models_dir: Path, downloads_dir: Path, *, zip_path: Path | None = None, log=print, cancel=None) -> None` — `zip_path`가 있으면 그 파일을, 없으면 `MODELS_URL`에서 받은 zip을 SHA-256 확인 후 `models_dir`에 풀고 `verify_models`가 빈 목록이 아니면 `InstallError`. 받은 zip은 끝나면 지운다(로컬 `zip_path`는 지우지 않는다).

- [ ] **Step 1: 의존성 추가**

`pyproject.toml`의 `dependencies`를 다음으로 바꾼다:

```toml
dependencies = [
    "httpx>=0.27",
    "natsort>=8.4",
    "pywebview>=5.3",
    "numpy==2.5.3",
    "opencv-python-headless==5.0.0.93",
    "onnxruntime==1.24.4",
    "pillow==12.3.0",
    "shapely==2.1.2",
    "pyclipper==1.4.0",
    "jaconv==0.5.0",
]
```

`[dependency-groups]`에 export 그룹을 추가한다(기본 설치 안 됨):

```toml
[dependency-groups]
dev = [
    "pytest>=8",
    "psutil>=6",
]
export = [
    "torch>=2.7",
    "transformers==4.57.6",
    "onnx>=1.17",
]
```

Run: `uv sync` → `uv run python -c "import onnxruntime, cv2, numpy, shapely, pyclipper, jaconv, PIL; print(onnxruntime.__version__, cv2.__version__, numpy.__version__)"`
Expected: `1.24.4 5.0.0 2.5.3` (cv2 버전 문자열은 `5.0.0`).

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_vision_models.py`:

```python
import zipfile
from pathlib import Path

import pytest

from manga_translate.download import InstallError, sha256_of
from manga_translate.vision import models
from manga_translate.vision.models import ModelFile, install_models, model_problems, verify_models


@pytest.fixture
def tiny_models(monkeypatch, tmp_path):
    """Replaces the real model list with two small files and returns (files dict, zip path, zip sha)."""
    contents = {"ctd/ctd_1280.onnx": b"detector", "manga-ocr/vocab.txt": b"[PAD]\n[UNK]\n"}
    src = tmp_path / "zip"
    archive = tmp_path / "vision-models-v1.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for rel, data in contents.items():
            zf.writestr(rel, data)
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_bytes(data)
    files = tuple(ModelFile(rel, sha256_of(src / rel), len(data)) for rel, data in contents.items())
    monkeypatch.setattr(models, "MODEL_FILES", files)
    monkeypatch.setattr(models, "MODELS_ZIP_SHA256", sha256_of(archive))
    return contents, archive


def test_real_model_list_matches_the_asset():
    assert [f.path for f in models.MODEL_FILES] == [
        "ctd/ctd_1280.onnx",
        "manga-ocr/encoder.onnx",
        "manga-ocr/cross_kv.onnx",
        "manga-ocr/decoder_step.onnx",
        "manga-ocr/vocab.txt",
    ]
    assert models.MODELS_URL.endswith("/vision-models-v1/vision-models-v1.zip")
    assert len(models.MODELS_ZIP_SHA256) == 64


def test_problems_for_missing_and_wrong_size(tiny_models, tmp_path):
    contents, _ = tiny_models
    models_dir = tmp_path / "models"
    problems = model_problems(models_dir)
    assert len(problems) == 2
    assert all("없습니다" in p for p in problems)
    (models_dir / "ctd").mkdir(parents=True)
    (models_dir / "ctd" / "ctd_1280.onnx").write_bytes(b"short")
    problems = model_problems(models_dir)
    assert any("크기" in p for p in problems)


def test_install_from_local_zip(tiny_models, tmp_path):
    contents, archive = tiny_models
    models_dir = tmp_path / "models"
    lines = []
    install_models(models_dir, tmp_path / "downloads", zip_path=archive, log=lines.append)
    assert model_problems(models_dir) == []
    assert verify_models(models_dir) == []
    assert archive.exists()  # a local zip is left in place
    assert (models_dir / "manga-ocr" / "vocab.txt").read_bytes() == contents["manga-ocr/vocab.txt"]


def test_install_rejects_a_zip_with_the_wrong_hash(tiny_models, tmp_path, monkeypatch):
    _, archive = tiny_models
    monkeypatch.setattr(models, "MODELS_ZIP_SHA256", "0" * 64)
    with pytest.raises(InstallError):
        install_models(tmp_path / "models", tmp_path / "downloads", zip_path=archive)


def test_verify_detects_changed_content(tiny_models, tmp_path):
    _, archive = tiny_models
    models_dir = tmp_path / "models"
    install_models(models_dir, tmp_path / "downloads", zip_path=archive)
    target = models_dir / "ctd" / "ctd_1280.onnx"
    target.write_bytes(b"detectoR")  # same size, different bytes
    assert model_problems(models_dir) == []
    assert verify_models(models_dir) != []
```

Run: `uv run pytest tests/test_vision_models.py -v` → FAIL (`ModuleNotFoundError: manga_translate.vision`).

- [ ] **Step 3: 구현**

`src/manga_translate/vision/__init__.py`:

```python
"""Text detection and Japanese OCR on ONNX Runtime (CPU)."""
```

`src/manga_translate/vision/models.py`:

```python
"""The detection/OCR model files: where they live, how to check them, how to install them from the release asset."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..download import InstallError, check_cancel, download, extract_zip, sha256_of

MODELS_ZIP_NAME = "vision-models-v1.zip"
MODELS_URL = f"https://github.com/kyj0503/manga-translate/releases/download/vision-models-v1/{MODELS_ZIP_NAME}"
MODELS_ZIP_SHA256 = "011a08838ddd4c7824b4b76e77bde992eec4f3531a0db7bc4cae50c06603949a"

CTD_MODEL = "ctd/ctd_1280.onnx"
OCR_DIR = "manga-ocr"


@dataclass(frozen=True)
class ModelFile:
    path: str  # relative to the models folder, "/"-separated
    sha256: str
    size: int


MODEL_FILES: tuple[ModelFile, ...] = (
    ModelFile(CTD_MODEL, "93b9be7e50caa324b53a2ee8b5cd6931fd77d0849793360fbea84474941401fb", 93760845),
    ModelFile(f"{OCR_DIR}/encoder.onnx", "df35f64c2400ea860c70a2d06f2a1f99892374a78c89fcf35308076557a3863f", 343377067),
    ModelFile(f"{OCR_DIR}/cross_kv.onnx", "3fb87bc6c884a84469a4ac754d5024bfaf35941c7e646016513a9eaeb1209a51", 9455844),
    ModelFile(f"{OCR_DIR}/decoder_step.onnx", "de0f600ca1196ca3c7672b52daa9a2e3dc56f2e27707da538865ac088ac04d3d", 107920310),
    ModelFile(f"{OCR_DIR}/vocab.txt", "344fbb6b8bf18c57839e924e2c9365434697e0227fac00b88bb4899b78aa594d", 24072),
)


def model_problems(models_dir: Path) -> list[str]:
    """Missing files or files of the wrong size, as messages for the user. Empty means the models look installed."""
    problems = []
    for f in MODEL_FILES:
        path = models_dir / f.path
        if not path.is_file():
            problems.append(f"검출·OCR 모델 파일이 없습니다: {path}")
        elif path.stat().st_size != f.size:
            problems.append(f"검출·OCR 모델 파일 크기가 다릅니다: {path}")
    return problems


def verify_models(models_dir: Path) -> list[str]:
    """Like model_problems, and also compares every file's SHA-256."""
    problems = model_problems(models_dir)
    if problems:
        return problems
    return [
        f"검출·OCR 모델 파일이 손상되었습니다: {models_dir / f.path}"
        for f in MODEL_FILES
        if sha256_of(models_dir / f.path) != f.sha256
    ]


def install_models(
    models_dir: Path,
    downloads_dir: Path,
    *,
    zip_path: Path | None = None,
    log: Callable[[str], None] = print,
    cancel: threading.Event | None = None,
) -> None:
    downloaded = zip_path is None
    archive = downloads_dir / MODELS_ZIP_NAME if downloaded else zip_path
    if downloaded:
        download(MODELS_URL, archive, MODELS_ZIP_SHA256, log=log, cancel=cancel)
    elif sha256_of(archive) != MODELS_ZIP_SHA256:
        raise InstallError(f"검출·OCR 모델 묶음의 SHA-256이 다릅니다: {archive}")
    check_cancel(cancel)
    log(f"압축 푸는 중: {archive.name}")
    extract_zip(archive, models_dir, strip_top=False, cancel=cancel)
    problems = verify_models(models_dir)
    if problems:
        raise InstallError("\n".join(problems))
    if downloaded:
        archive.unlink(missing_ok=True)
```

`extract_zip`의 `strip_top=False`가 zip 안의 `ctd/`, `manga-ocr/` 경로를 그대로 푸는지 `src/manga_translate/download.py`에서 확인한다. 다르게 동작하면 이 태스크 안에서 `install_models`만 맞춰 고치고 보고서에 적는다.

`tools/export/export_ctd.py` — `.dev\spike-onnx\export_ctd.py` 내용을 그대로 옮기고 첫 docstring을 다음으로 바꾼다:

```python
"""Dev-time only (needs torch): exports BallonsTranslator's comic-text-detector torch model to ONNX at a fixed
square input size. The release asset's ctd/ctd_1280.onnx was made with size 1280:
  <BallonsTranslator venv python> tools/export/export_ctd.py <BallonsTranslator root> <out.onnx> 1280
"""
```

`tools/export/export_decoder_kv.py` — `.dev\spike-onnx\export_decoder_kv.py` 내용을 그대로 옮기고 첫 docstring을 다음으로 바꾼다:

```python
"""Dev-time only (needs torch, transformers, onnx): exports manga-ocr's 2-layer BERT decoder as two KV-cache graphs.
  cross_kv.onnx     : encoder_hidden_states -> cross K/V per layer
  decoder_step.onnx : input_ids[B,1], past self K/V, cross K/V -> logits[B,V], present self K/V
The release asset's manga-ocr/cross_kv.onnx and decoder_step.onnx were made from kha-white/manga-ocr-base:
  uv run --group export python tools/export/export_decoder_kv.py <manga-ocr-base dir> <out dir>
"""
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_vision_models.py -v` → PASS. `uv run pytest -q` → 모두 PASS.

- [ ] **Step 5: 커밋**

```bash
git add pyproject.toml uv.lock src/manga_translate/vision tools/export tests/test_vision_models.py
git commit -F <메시지 파일>   # 제목: Add the vision model manifest, installer and export tools
```

---

### Task 2: 말풍선 묶기 이식과 기대값 고정

**Files:**
- Create: `src/manga_translate/vision/grouping.py`
- Create: `tools/parity/make_grouping_fixtures.py`
- Create: `tests/fixtures/vision/page1.jpg`, `page2.jpg`, `page3.jpg`, `grouping_page{1,2,3}.npz`, `grouping_page{1,2,3}.json`
- Test: `tests/test_vision_grouping.py`

**Interfaces:**
- Produces (`vision/grouping.py`):
  - `TextBlock` — BallonsTranslator `TextBlock`에서 아래 함수들이 쓰는 속성·메서드만 가진 작은 클래스. 최소한 `xyxy: list[int]`(4개), `lines: list`(각 글줄은 4점 좌표 리스트), `vertical: bool`, `language`, `src_is_vertical`, `_detected_font_size: float`, `font_size`, `angle`, `vec`, `norm`, `merged`, 메서드 `adjust_bbox`, `sort_lines`, `lines_array`, `center`, `min_rect`.
  - `group_output(blks, lines, im_w, im_h, mask=None, sort_blklist=True, canvas=None) -> list[TextBlock]` (BallonsTranslator와 같은 시그니처·동작)
  - `read_rgb(path: Path) -> np.ndarray` — PIL로 열어 RGB `uint8` 배열(기대값 생성과 테스트가 같은 방식으로 읽기 위함)

이식 원본(커밋 3e401b29, `.dev\BallonsTranslator\ballontranslator\utils\`):
- `textblock.py`: `group_output`(931-1051), `examine_textblk`(787-823), `try_merge_textline`(825-884), `merge_textlines`(886-898), `sort_regions`(754-785). `TextBlock`에서는 위 함수들이 부르는 것만: `vertical` 속성(146-147), `font_size` 속성(154-155), `adjust_bbox`(402-420), `sort_lines`(422-427), `lines_array`(429-430), `center`(496-498), `min_rect`(510-519), 그리고 생성자에서 이 함수들이 넘기는 인자·초기값.
- `imgproc_utils.py`: `union_area`(26~), `xywh2xyxypoly`(44~), `rotate_polygons`(81~), `color_difference`(256~)
- `textlines_merge.py`: `sort_pnts`(293~)

BallonsTranslator의 `TextBlock.vertical`/`font_size`는 `fontformat` 객체를 거치는 속성이다. 이식본에서는 평범한 필드로 둔다(폰트·효과 모듈을 가져오지 않는다). 함수 본문은 동작을 바꾸지 않고 옮긴다. 파일 머리 주석:

```python
"""Groups detected text lines into text blocks (speech bubbles), decides vertical writing and reading order.

Ported from BallonsTranslator (https://github.com/dmMaze/BallonsTranslator, commit 3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8,
ballontranslator/utils/textblock.py, imgproc_utils.py, textlines_merge.py), GPL-3.0. TextBlock keeps only what the
grouping functions use; the function bodies are unchanged.
"""
```

- [ ] **Step 1: 기대값 생성 도구 작성과 실행**

`tools/parity/make_grouping_fixtures.py`:

```python
"""Dev tool: writes tests/fixtures/vision/ from synthetic pages (text written for this project, not manga).

For each page it saves the JPEG test image, the detector's text lines and mask (the inputs to grouping), and
BallonsTranslator's own group_output result on those inputs. Run once with the spike venv, which can import
BallonsTranslator and the spike's ONNX detector:
  .dev/spike-onnx/.venv/Scripts/python.exe tools/parity/make_grouping_fixtures.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SPIKE = REPO / ".dev" / "spike-onnx"
sys.path.insert(0, str(SPIKE))
import onnx_engine  # noqa: E402  (spike code; imports BallonsTranslator's group_output)
from onnx_engine import OnnxCTD, group_output, letterbox  # noqa: E402

PAGES = {
    "page1": SPIKE / "synthetic" / "synth_01.png",
    "page2": SPIKE / "synthetic" / "synth_04.png",
    "page3": sorted((SPIKE / "synthetic_tall").glob("*.png"))[0],
}
OUT = REPO / "tests" / "fixtures" / "vision"


def detector_inputs(det, img):
    """Everything OnnxCTD.detect does before group_output."""
    import cv2

    im_h, im_w = img.shape[:2]
    lines_map, mask = det._rearrange_forward(img)
    if lines_map is None:
        im, dw, dh = letterbox(img, det.size)
        chw = np.ascontiguousarray(im.transpose(2, 0, 1)[::-1]).astype(np.float32) / 255.0
        mask, lines_map = det._forward(chw)
        mask = mask.squeeze()
        mask = mask[: mask.shape[0] - dh, : mask.shape[1] - dw]
        lines_map = lines_map[..., : lines_map.shape[2] - dh, : lines_map.shape[3] - dw]
    mask = (mask.squeeze() * 255).astype(np.uint8)
    lines, scores = det.seg_rep(lines_map, height=im_h, width=im_w)
    lines = lines[np.where(scores > 0.6)]
    mask = cv2.resize(mask, (im_w, im_h), interpolation=cv2.INTER_LINEAR)
    lines = np.zeros((0, 4, 2), np.int64) if lines.size == 0 else lines.astype(np.int64)
    return lines, mask


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    det = OnnxCTD(SPIKE / "models" / "ctd_1280.onnx", "cpu")
    for name, src in PAGES.items():
        jpg = OUT / f"{name}.jpg"
        Image.open(src).convert("RGB").save(jpg, quality=90)
        img = np.array(Image.open(jpg).convert("RGB"))
        lines, mask = detector_inputs(det, img)
        np.savez_compressed(OUT / f"grouping_{name}.npz", lines=lines, mask=mask)
        blocks = group_output([], lines if len(lines) else [], img.shape[1], img.shape[0], mask, canvas=img)
        expected = [
            {"xyxy": [int(v) for v in b.xyxy], "vertical": bool(b.vertical),
             "lines": np.asarray(b.lines, dtype=np.int64).tolist()}
            for b in blocks
        ]
        (OUT / f"grouping_{name}.json").write_text(json.dumps(expected), encoding="utf-8")
        print(name, img.shape[1], img.shape[0], "lines", len(lines), "blocks", len(blocks))


if __name__ == "__main__":
    main()
```

Run: `.dev/spike-onnx/.venv/Scripts/python.exe tools/parity/make_grouping_fixtures.py`
Expected: 세 페이지 모두 `blocks` 5개 이상. 만들어진 jpg 세 장의 합이 3MB를 넘으면 `quality=80`으로 낮춰 다시 실행한다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_vision_grouping.py`:

```python
import json
from pathlib import Path

import numpy as np
import pytest

from manga_translate.vision.grouping import group_output, read_rgb

FIXTURES = Path(__file__).parent / "fixtures" / "vision"
PAGES = ["page1", "page2", "page3"]


def describe(blocks):
    return [
        {"xyxy": [int(v) for v in b.xyxy], "vertical": bool(b.vertical),
         "lines": np.asarray(b.lines, dtype=np.int64).tolist()}
        for b in blocks
    ]


@pytest.mark.parametrize("name", PAGES)
def test_grouping_matches_ballons_translator(name):
    data = np.load(FIXTURES / f"grouping_{name}.npz")
    img = read_rgb(FIXTURES / f"{name}.jpg")
    lines = data["lines"]
    blocks = group_output([], lines if len(lines) else [], img.shape[1], img.shape[0], data["mask"], canvas=img)
    expected = json.loads((FIXTURES / f"grouping_{name}.json").read_text(encoding="utf-8"))
    assert describe(blocks) == expected


def test_no_lines_gives_no_blocks():
    img = np.full((100, 80, 3), 255, np.uint8)
    assert group_output([], [], 80, 100, np.zeros((100, 80), np.uint8), canvas=img) == []


def test_read_rgb_returns_three_channels(tmp_path):
    from PIL import Image

    path = tmp_path / "gray.png"
    Image.new("L", (5, 4), 128).save(path)
    img = read_rgb(path)
    assert img.shape == (4, 5, 3) and img.dtype == np.uint8
```

Run: `uv run pytest tests/test_vision_grouping.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: 구현**

위 "이식 원본"의 함수들을 `src/manga_translate/vision/grouping.py`로 옮긴다. 규칙:
1. 함수 본문의 계산은 바꾸지 않는다(변수 이름, 상수, 정렬 방식 그대로).
2. `TextBlock`은 필요한 필드만 가진 클래스로 새로 쓴다. 생성자는 `group_output`/`try_merge_textline` 등이 실제로 넘기는 키워드를 받는다(원본 생성자와 dataclass 필드 기본값을 보고 맞춘다). `vertical`, `font_size`는 평범한 속성으로 둔다.
3. 필요한 import는 `numpy`, `cv2`, `math`, `shapely.geometry.Polygon`, `copy` 정도로 한정한다. `networkx`, Qt, 폰트 모듈은 가져오지 않는다.
4. `read_rgb(path)`: `np.array(Image.open(path).convert("RGB"))`.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_vision_grouping.py -v` → PASS (세 페이지 모두 BallonsTranslator 결과와 정확히 같음). `uv run pytest -q` → 모두 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/vision/grouping.py tools/parity/make_grouping_fixtures.py tests/fixtures/vision tests/test_vision_grouping.py
git commit -F <메시지 파일>   # 제목: Port BallonsTranslator's text-line grouping with golden fixtures
```

---

### Task 3: ctd ONNX 검출

**Files:**
- Create: `src/manga_translate/vision/ctd.py`
- Test: `tests/test_vision_ctd.py`

**Interfaces:**
- Consumes: `group_output`, `TextBlock`, `read_rgb` (Task 2), `CTD_MODEL` (Task 1)
- Produces: `make_session(path: Path) -> onnxruntime.InferenceSession` (CPU, 그래프 최적화 ALL); `letterbox(im, size) -> (im, dw, dh)`; `square_pad_resize(img, tgt_size) -> (img, ratio, pad_h, pad_w)`; `SegDetectorRepresenter`; `CTD(model_path: Path)` with `.detect(img: np.ndarray) -> list[TextBlock]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_vision_ctd.py`:

```python
import json
import os
from pathlib import Path

import numpy as np
import pytest

from manga_translate.vision.ctd import CTD, SegDetectorRepresenter, letterbox, square_pad_resize
from manga_translate.vision.grouping import read_rgb
from manga_translate.vision.models import CTD_MODEL

FIXTURES = Path(__file__).parent / "fixtures" / "vision"
MODELS = Path(os.environ.get("MANGA_TRANSLATE_VISION_MODELS", "__none__"))
needs_models = pytest.mark.skipif(not (MODELS / CTD_MODEL).is_file(), reason="vision models not available")


def test_letterbox_pads_bottom_right_to_square():
    im = np.zeros((100, 200, 3), np.uint8)
    out, dw, dh = letterbox(im, 64)
    assert out.shape == (64, 64, 3)
    assert (dw, dh) == (0, 32)


def test_square_pad_resize_pads_short_side_then_shrinks():
    img = np.zeros((300, 100, 3), np.uint8)
    out, ratio, pad_h, pad_w = square_pad_resize(img, 150)
    assert out.shape[:2] == (150, 150)
    assert (pad_h, pad_w) == (0, 200)
    assert ratio == pytest.approx(0.5)


def test_seg_detector_finds_a_box_in_a_bitmap():
    pred = np.zeros((1, 1, 64, 64), np.float32)
    pred[0, 0, 20:30, 10:50] = 0.9
    boxes, scores = SegDetectorRepresenter(thresh=0.3)(pred, height=128, width=128)
    assert len(boxes) == 1 and scores[0] > 0.6
    xs, ys = boxes[0][:, 0], boxes[0][:, 1]
    assert xs.min() < 25 and xs.max() > 95 and ys.min() < 45 and ys.max() > 55


@needs_models
@pytest.mark.parametrize("name", ["page1", "page2", "page3"])
def test_detect_matches_the_grouping_fixture(name):
    det = CTD(MODELS / CTD_MODEL)
    blocks = det.detect(read_rgb(FIXTURES / f"{name}.jpg"))
    expected = json.loads((FIXTURES / f"grouping_{name}.json").read_text(encoding="utf-8"))
    assert [[int(v) for v in b.xyxy] for b in blocks] == [e["xyxy"] for e in expected]
    assert [bool(b.vertical) for b in blocks] == [e["vertical"] for e in expected]
```

Run: `MANGA_TRANSLATE_VISION_MODELS=.dev/vision-models-v1 uv run pytest tests/test_vision_ctd.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: 구현**

`src/manga_translate/vision/ctd.py`:

```python
"""comic-text-detector on ONNX Runtime (CPU): finds text lines and groups them into text blocks.

Pre/post-processing ported from comic-text-detector (https://github.com/dmMaze/comic-text-detector, commit 440b978)
and BallonsTranslator (commit 3e401b29, modules/textdetector/ctd/inference.py, db_utils.py), GPL-3.0, with torch
and einops replaced by numpy. The detector's YOLO block output is not used, as in BallonsTranslator.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import pyclipper
from shapely.geometry import Polygon

from .grouping import TextBlock, group_output

LINE_SCORE_THRESHOLD = 0.6


def make_session(path: Path) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def letterbox(im: np.ndarray, size: int) -> tuple[np.ndarray, int, int]:
    h, w = im.shape[:2]
    r = min(size / h, size / w)
    new_unpad = int(round(w * r)), int(round(h * r))
    dw, dh = size - new_unpad[0], size - new_unpad[1]
    if (w, h) != new_unpad:
        im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    im = cv2.copyMakeBorder(im, 0, dh, 0, dw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    return im, int(dw), int(dh)


def square_pad_resize(img: np.ndarray, tgt_size: int) -> tuple[np.ndarray, float, int, int]:
    h, w = img.shape[:2]
    pad_h = pad_w = 0
    if w < h:
        pad_w = h - w
        w += pad_w
    elif h < w:
        pad_h = w - h
        h += pad_h
    pad_size = tgt_size - h
    if pad_size > 0:
        pad_h += pad_size
        pad_w += pad_size
    if pad_h > 0 or pad_w > 0:
        img = cv2.copyMakeBorder(img, 0, pad_h, 0, pad_w, cv2.BORDER_CONSTANT)
    ratio = tgt_size / img.shape[0]
    if ratio < 1:
        img = cv2.resize(img, (tgt_size, tgt_size), interpolation=cv2.INTER_AREA)
    return img, ratio, pad_h, pad_w


class SegDetectorRepresenter:
    """DB post-process: text-line quadrilaterals from the line probability map."""

    def __init__(self, thresh: float = 0.3, max_candidates: int = 1000, unclip_ratio: float = 1.5) -> None:
        self.thresh, self.max_candidates, self.unclip_ratio = thresh, max_candidates, unclip_ratio

    def __call__(self, pred: np.ndarray, height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
        pred = pred[:, 0, :, :]
        seg = pred > self.thresh
        return self.boxes_from_bitmap(pred[0], seg[0], width, height)

    def boxes_from_bitmap(self, pred, bitmap, dest_width, dest_height):
        height, width = bitmap.shape
        contours, _ = cv2.findContours((bitmap * 255).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        n = min(len(contours), self.max_candidates)
        boxes = np.zeros((n, 4, 2), dtype=np.int64)
        scores = np.zeros((n,), dtype=np.float32)
        for i in range(n):
            contour = contours[i].squeeze(1)
            points, sside = self.get_mini_boxes(contour)
            if sside < 2:
                continue
            score = self.box_score_fast(pred, contour)
            box = self.unclip(np.array(points)).reshape(-1, 1, 2)
            box, _ = self.get_mini_boxes(box)
            box = np.array(box)
            box[:, 0] = np.clip(np.round(box[:, 0] / width * dest_width), 0, dest_width)
            box[:, 1] = np.clip(np.round(box[:, 1] / height * dest_height), 0, dest_height)
            boxes[i] = box.astype(np.int64)
            scores[i] = score
        return boxes, scores

    def unclip(self, box):
        poly = Polygon(box)
        distance = poly.area * self.unclip_ratio / poly.length
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(box, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        return np.array(offset.Execute(distance))

    @staticmethod
    def get_mini_boxes(contour):
        rect = cv2.minAreaRect(contour)
        pts = sorted(list(cv2.boxPoints(rect)), key=lambda x: x[0])
        i1, i4 = (0, 1) if pts[1][1] > pts[0][1] else (1, 0)
        i2, i3 = (2, 3) if pts[3][1] > pts[2][1] else (3, 2)
        return [pts[i1], pts[i2], pts[i3], pts[i4]], min(rect[1])

    @staticmethod
    def box_score_fast(bitmap, _box):
        h, w = bitmap.shape[:2]
        box = _box.copy()
        xmin = np.clip(np.floor(box[:, 0].min()).astype(np.int64), 0, w - 1)
        xmax = np.clip(np.ceil(box[:, 0].max()).astype(np.int64), 0, w - 1)
        ymin = np.clip(np.floor(box[:, 1].min()).astype(np.int64), 0, h - 1)
        ymax = np.clip(np.ceil(box[:, 1].max()).astype(np.int64), 0, h - 1)
        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        box[:, 0] -= xmin
        box[:, 1] -= ymin
        cv2.fillPoly(mask, box.reshape(1, -1, 2).astype(np.int32), 1)
        return cv2.mean(bitmap[ymin:ymax + 1, xmin:xmax + 1].astype(np.float32), mask)[0]


class CTD:
    def __init__(self, model_path: Path) -> None:
        self.sess = make_session(model_path)
        self.size = self.sess.get_inputs()[0].shape[-1]
        self.in_name = self.sess.get_inputs()[0].name
        self.seg_rep = SegDetectorRepresenter(thresh=0.3)

    def _forward(self, chw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        _blocks, seg, lines = self.sess.run(None, {self.in_name: chw[None]})
        return seg, lines  # seg: (1,1,S,S) text mask, lines: (1,2,S,S) line map

    def _rearrange_forward(self, img: np.ndarray):
        """Very tall or wide pages: run on overlapping square patches and stitch the maps back together."""
        tgt = self.size
        h, w = img.shape[:2]
        transpose = False
        if h < w:
            transpose = True
            h, w = img.shape[1], img.shape[0]
        if not (h / tgt > 2.5 and h / w > 3):
            return None, None
        if transpose:
            img = img.transpose(1, 0, 2)
        pw_num = max(int(np.floor(2 * tgt / w)), 2)
        patch_size = ph = pw_num * w
        ph_num = int(np.ceil(h / ph))
        ph_step = int((h - ph) / (ph_num - 1)) if ph_num > 1 else 0
        rel_steps, patches = [], []
        for ii in range(ph_num):
            t = ii * ph_step
            rel_steps.append(t / h)
            patches.append(img[t:t + ph])
        p_num = int(np.ceil(ph_num / pw_num))
        pad_num = p_num * pw_num - ph_num
        patches += [np.zeros_like(patches[0]) for _ in range(pad_num)]
        arr = np.array(patches).reshape(p_num, pw_num, ph, w, 3)
        if transpose:
            arr = arr.transpose(0, 1, 3, 2, 4).reshape(p_num, pw_num * w, ph, 3)
        else:
            arr = arr.transpose(0, 2, 1, 3, 4).reshape(p_num, ph, pw_num * w, 3)
        line_maps, masks = [], []
        for patch in arr:
            p, _, pad_h, _ = square_pad_resize(patch, tgt)
            chw = np.ascontiguousarray(p.transpose(2, 0, 1)).astype(np.float32) / 255.0
            m, d = self._forward(chw)
            d, m = d[0], m[0]
            if pad_h > 0:
                pad_line = int(d.shape[-1] / tgt * pad_h)
                pad_mask = int(m.shape[-1] / tgt * pad_h)
                d = d[..., :-pad_line, :-pad_line]
                m = m[..., :-pad_mask, :-pad_mask]
            line_maps.append(d)
            masks.append(m)

        def unrearrange(plist, channel):
            psize = plist[0].shape[-1]
            step = int(ph_step * psize / patch_size)
            pw = int(psize / pw_num)
            hh = int(pw / w * h)
            tgtmap = np.zeros((channel, hh, pw), dtype=np.float32)
            num_patches = len(plist) * pw_num - pad_num
            for ii, p in enumerate(plist):
                if transpose:
                    p = p.transpose(0, 2, 1)
                for jj in range(pw_num):
                    pidx = ii * pw_num + jj
                    t = int(round(rel_steps[pidx] * hh))
                    b = min(t + psize, hh)
                    left = jj * pw
                    tgtmap[..., t:b, :] += p[..., :b - t, left:left + pw]
                    if pidx > 0:
                        inter = psize - step
                        tgtmap[..., t:t + inter, :] /= 2.0
                    if pidx >= num_patches - 1:
                        break
            if transpose:
                tgtmap = tgtmap.transpose(0, 2, 1)
            return tgtmap[None]

        return unrearrange(line_maps, 2), unrearrange(masks, 1)

    def detect(self, img: np.ndarray) -> list[TextBlock]:
        """Text blocks of an RGB page, in reading order."""
        im_h, im_w = img.shape[:2]
        lines_map, mask = self._rearrange_forward(img)
        if lines_map is None:
            im, dw, dh = letterbox(img, self.size)
            # The model was trained on channel-flipped input (BallonsTranslator's torch path flips the RGB page).
            chw = np.ascontiguousarray(im.transpose(2, 0, 1)[::-1]).astype(np.float32) / 255.0
            mask, lines_map = self._forward(chw)
            mask = mask.squeeze()
            mask = mask[: mask.shape[0] - dh, : mask.shape[1] - dw]
            lines_map = lines_map[..., : lines_map.shape[2] - dh, : lines_map.shape[3] - dw]
        mask = (mask.squeeze() * 255).astype(np.uint8)
        lines, scores = self.seg_rep(lines_map, height=im_h, width=im_w)
        lines = lines[np.where(scores > LINE_SCORE_THRESHOLD)]
        mask = cv2.resize(mask, (im_w, im_h), interpolation=cv2.INTER_LINEAR)
        lines = [] if lines.size == 0 else lines.astype(np.int64)
        return group_output([], lines, im_w, im_h, mask, canvas=img)
```

- [ ] **Step 3: 통과 확인**

Run: `MANGA_TRANSLATE_VISION_MODELS=.dev/vision-models-v1 uv run pytest tests/test_vision_ctd.py -v` → PASS (모델 테스트 3개 포함). `uv run pytest -q`(환경 변수 없이) → 모델 테스트는 skip, 나머지 PASS.

- [ ] **Step 4: 커밋**

```bash
git add src/manga_translate/vision/ctd.py tests/test_vision_ctd.py
git commit -F <메시지 파일>   # 제목: Run comic-text-detector on ONNX Runtime
```

---

### Task 4: manga-ocr ONNX

**Files:**
- Create: `src/manga_translate/vision/ocr.py`
- Test: `tests/test_vision_ocr.py`

**Interfaces:**
- Consumes: `make_session` (Task 3), `OCR_DIR` (Task 1)
- Produces: `MangaOCR(model_dir: Path)` (`model_dir`는 `models/manga-ocr`), `.read(img: np.ndarray) -> str`, `.read_blocks(img, xyxys) -> list[str]`; 정적 `preprocess(img) -> np.ndarray[1,3,224,224]`, `post_process(text) -> str`; `banned_tokens(seq: list[int], n: int) -> list[int]`; `beam_search(step, start, eos, *, num_beams=4, max_length=300, length_penalty=2.0, no_repeat=3) -> list[int]` where `step(seqs: list[list[int]], src: list[int] | None) -> np.ndarray[num_beams, vocab]` returns log-probability rows for the current beams.

설계 메모: 실험 코드의 `generate`를 모델 호출(`step`)과 빔 서치 알고리즘으로 나눠, 빔 서치를 가짜 `step`으로 테스트할 수 있게 한다. `src`는 직전 단계에서 살아남은 빔이 어느 이전 빔에서 왔는지(첫 단계는 `None`)이며, KV 캐시를 그 순서로 재배열하는 데 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_vision_ocr.py`:

```python
import json
import os
from pathlib import Path

import numpy as np
import pytest

from manga_translate.vision.grouping import read_rgb
from manga_translate.vision.models import OCR_DIR
from manga_translate.vision.ocr import MangaOCR, banned_tokens, beam_search

MODELS = Path(os.environ.get("MANGA_TRANSLATE_VISION_MODELS", "__none__"))
needs_models = pytest.mark.skipif(not (MODELS / OCR_DIR / "encoder.onnx").is_file(), reason="vision models not available")


def test_post_process_joins_and_widens():
    assert MangaOCR.post_process("ab c1 …!") == "ａｂｃ１．．．！"
    assert MangaOCR.post_process("・・・") == "．．．"


def test_preprocess_shape_and_range():
    img = np.zeros((30, 50, 3), np.uint8)
    x = MangaOCR.preprocess(img)
    assert x.shape == (1, 3, 224, 224) and x.dtype == np.float32
    assert float(x.min()) == pytest.approx(-1.0)


def test_banned_tokens_blocks_a_repeated_trigram():
    assert banned_tokens([2, 7, 8, 9, 7, 8], 3) == [9]
    assert banned_tokens([2, 7], 3) == []


def scripted_step(script, vocab=6):
    """A fake model: at step t every beam gets the same log-probs, taken from script[t]."""
    calls = []

    def step(seqs, src):
        calls.append((len(seqs), src))
        row = np.full(vocab, -1e9)
        for token, logp in script[min(len(calls) - 1, len(script) - 1)].items():
            row[token] = logp
        return np.tile(row, (len(seqs), 1))

    return step, calls


def test_beam_search_returns_best_sequence_without_start_or_eos():
    # token 4 then 5 then EOS(3) is the only likely path
    step, _ = scripted_step([{4: -0.1, 5: -3.0}, {5: -0.1, 4: -3.0}, {3: -0.01, 4: -5.0}])
    assert beam_search(step, start=2, eos=3, num_beams=2, max_length=10) == [4, 5]


def test_beam_search_stops_at_max_length():
    step, calls = scripted_step([{4: -0.1, 5: -0.2}])
    tokens = beam_search(step, start=2, eos=3, num_beams=2, max_length=5, no_repeat=0)
    assert 0 < len(tokens) <= 4
    assert len(calls) == 4


@needs_models
def test_reads_the_fixture_blocks_like_the_reference():
    fixtures = Path(__file__).parent / "fixtures" / "vision"
    expected = json.loads((fixtures / "expected.json").read_text(encoding="utf-8"))
    ocr = MangaOCR(MODELS / OCR_DIR)
    for page in expected["pages"]:
        img = read_rgb(fixtures / page["image"])
        texts = ocr.read_blocks(img, [b["xyxy"] for b in page["blocks"]])
        assert texts == [b["text"] for b in page["blocks"]]
```

`test_reads_the_fixture_blocks_like_the_reference`는 Task 5 Step 1에서 만드는 `expected.json`이 필요하다. 이 태스크에서는 파일이 없으면 skip되도록 데코레이터 위에 다음을 추가한다:

```python
@pytest.mark.skipif(not (Path(__file__).parent / "fixtures" / "vision" / "expected.json").is_file(), reason="expected.json comes in Task 5")
```

Run: `uv run pytest tests/test_vision_ocr.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: 구현**

`src/manga_translate/vision/ocr.py`:

```python
"""manga-ocr (kha-white/manga-ocr-base, Apache-2.0) on ONNX Runtime (CPU).

The encoder is the onnx-community export; the decoder is split into cross_kv.onnx (cross-attention keys/values)
and decoder_step.onnx (one token with a self-attention KV cache), exported by tools/export/export_decoder_kv.py.
Decoding matches the engine's settings: beam search with 4 beams, no repeated 3-grams, length penalty 2.0,
early stopping.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Sequence

import jaconv
import numpy as np
from PIL import Image

from .ctd import make_session

SPECIAL_TOKENS = frozenset({0, 1, 2, 3, 4})
START, EOS = 2, 3
LAYERS = ("k0", "v0", "k1", "v1")


def banned_tokens(seq: Sequence[int], n: int) -> list[int]:
    """Tokens that would repeat an n-gram already in seq."""
    if n <= 0 or len(seq) + 1 < n:
        return []
    prefix = tuple(seq[-(n - 1):]) if n > 1 else ()
    return [seq[i + n - 1] for i in range(len(seq) - n + 1) if tuple(seq[i:i + n - 1]) == prefix]


def beam_search(
    step: Callable[[list[list[int]], list[int] | None], np.ndarray],
    start: int,
    eos: int,
    *,
    num_beams: int = 4,
    max_length: int = 300,
    length_penalty: float = 2.0,
    no_repeat: int = 3,
) -> list[int]:
    seqs = [[start] for _ in range(num_beams)]
    beam_scores = np.full(num_beams, -1e9, dtype=np.float64)
    beam_scores[0] = 0.0
    finished: list[tuple[float, list[int]]] = []
    worst = None
    src: list[int] | None = None
    for cur_len in range(1, max_length):
        logp = np.asarray(step(seqs, src), dtype=np.float64)
        logp = logp - logp.max(-1, keepdims=True)
        logp = logp - np.log(np.exp(logp).sum(-1, keepdims=True))
        for b in range(num_beams):
            for t in banned_tokens(seqs[b], no_repeat):
                logp[b, t] = -np.inf
        cand = (logp + beam_scores[:, None]).reshape(-1)
        k = 2 * num_beams
        top = np.argpartition(-cand, k)[:k]
        top = top[np.argsort(-cand[top], kind="stable")]
        new_seqs, new_scores, new_src = [], [], []
        for rank, flat in enumerate(top):
            b, tok = divmod(int(flat), logp.shape[1])
            score = cand[flat]
            if tok == eos:
                if rank >= num_beams:
                    continue
                norm = score / (cur_len ** length_penalty)
                if len(finished) < num_beams or norm > worst:
                    finished.append((norm, seqs[b][1:]))
                    finished.sort(key=lambda x: -x[0])
                    finished = finished[:num_beams]
                    worst = finished[-1][0]
            else:
                new_seqs.append(seqs[b] + [tok])
                new_scores.append(score)
                new_src.append(b)
            if len(new_seqs) == num_beams:
                break
        seqs, src = new_seqs, new_src
        beam_scores = np.array(new_scores)
        if len(finished) >= num_beams:  # early stopping
            break
    if len(finished) < num_beams:
        for s, score in zip(seqs, beam_scores):
            finished.append((score / ((len(s) - 1) ** length_penalty), s[1:]))
        finished.sort(key=lambda x: -x[0])
    return finished[0][1]


class MangaOCR:
    def __init__(self, model_dir: Path, *, num_beams: int = 4, max_length: int = 300) -> None:
        self.encoder = make_session(model_dir / "encoder.onnx")
        self.cross = make_session(model_dir / "cross_kv.onnx")
        self.step_session = make_session(model_dir / "decoder_step.onnx")
        self.vocab = (model_dir / "vocab.txt").read_text(encoding="utf-8").split("\n")
        self.num_beams, self.max_length = num_beams, max_length

    @staticmethod
    def preprocess(img: np.ndarray) -> np.ndarray:
        """Like manga-ocr's ViTImageProcessor: RGB, bilinear resize to 224, scale to [0, 1], normalize 0.5/0.5."""
        pil = Image.fromarray(img).convert("L").convert("RGB")
        pil = pil.resize((224, 224), resample=Image.BILINEAR)
        x = np.asarray(pil).astype(np.float32) * np.float32(1 / 255)
        x = (x - 0.5) / 0.5
        return x.transpose(2, 0, 1)[None].astype(np.float32)

    @staticmethod
    def post_process(text: str) -> str:
        text = "".join(text.split())
        text = text.replace("…", "...")
        text = re.sub("[・.]{2,}", lambda m: (m.end() - m.start()) * ".", text)
        return jaconv.h2z(text, ascii=True, digit=True)

    def decode(self, tokens: Sequence[int]) -> str:
        words = [self.vocab[t] for t in tokens if t not in SPECIAL_TOKENS]
        return self.post_process(" ".join(words).replace(" ##", "").strip())

    def read(self, img: np.ndarray) -> str:
        encoded = self.encoder.run(None, {"pixel_values": self.preprocess(img)})[0]
        nb = self.num_beams
        cross = self.cross.run(None, {"encoder_hidden_states": encoded})
        cross_feeds = {f"cross_{n}": np.repeat(c, nb, axis=0) for n, c in zip(LAYERS, cross)}
        past = {f"past_{n}": np.zeros((nb, 12, 0, 64), np.float32) for n in LAYERS}

        def step(seqs: list[list[int]], src: list[int] | None) -> np.ndarray:
            nonlocal past
            if src is not None:
                past = {name: value[src] for name, value in past.items()}
            ids = np.array([[s[-1]] for s in seqs], dtype=np.int64)
            outs = self.step_session.run(None, {"input_ids": ids, **past, **cross_feeds})
            past = {f"past_{n}": p for n, p in zip(LAYERS, outs[1:])}
            return outs[0]

        tokens = beam_search(step, START, EOS, num_beams=nb, max_length=self.max_length)
        return self.decode(tokens)

    def read_blocks(self, img: np.ndarray, xyxys: Sequence[Sequence[int]]) -> list[str]:
        im_h, im_w = img.shape[:2]
        texts = []
        for x1, y1, x2, y2 in xyxys:
            y1c, y2c = max(0, y1), min(im_h, y2)
            x1c, x2c = max(0, x1), min(im_w, x2)
            if y1c < y2c and x1c < x2c:
                texts.append(self.read(np.ascontiguousarray(img[y1c:y2c, x1c:x2c])))
            else:
                texts.append("")
        return texts
```

주의 — 실험 코드와 다른 곳이 두 군데 있다. 둘 다 실제 결과를 바꿀 수 있으니 Task 5의 회귀 테스트로 확인한다.
1. `preprocess`의 `.convert("L").convert("RGB")`(흑백 변환): manga-ocr 원본 동작이다. 실험 코드에는 없었다. 엔진(BallonsTranslator)의 manga_ocr 모듈이 흑백 변환을 하는지 `.dev\BallonsTranslator\ballontranslator\modules\ocr\ocr_manga.py`에서 확인하고, **엔진과 같게** 맞춘다(하지 않으면 이 줄을 지운다). 보고서에 확인 결과를 적는다.
2. KV 캐시 재배열: 실험 코드는 다음 단계 입력 전에 `p[src]`로 재배열했다. 여기서는 `step`이 `src`를 받아 같은 일을 한다.

- [ ] **Step 3: 통과 확인**

Run: `uv run pytest tests/test_vision_ocr.py -v` → PASS (모델 테스트는 Task 5 전까지 skip). `uv run pytest -q` → 모두 PASS.

- [ ] **Step 4: 커밋**

```bash
git add src/manga_translate/vision/ocr.py tests/test_vision_ocr.py
git commit -F <메시지 파일>   # 제목: Run manga-ocr on ONNX Runtime with beam search
```

---

### Task 5: 비전 엔진, 워커, 회귀 기대값

**Files:**
- Create: `src/manga_translate/vision/engine.py`, `src/manga_translate/vision/worker.py`
- Create: `tests/helpers/fake_worker.py`, `tests/fixtures/vision/expected.json`
- Modify: `src/manga_translate/worker_client.py` (`WORKER_SCRIPT`, `worker_argv` 삭제, `vision_worker_argv` 추가, `EngineLayout` import 삭제)
- Modify: `tests/test_worker.py` (가짜 BallonsTranslator 대신 가짜 워커 사용)
- Test: `tests/test_vision_engine.py`, `tests/test_worker.py`

**Interfaces:**
- Consumes: `CTD`, `MangaOCR`, `read_rgb`, `model_problems`, `CTD_MODEL`, `OCR_DIR`; `WorkerClient(argv, cwd, log_path, *, job, ready_timeout, request_timeout)` (`.start/.scan/.stop/.running`), `WorkerError`
- Produces:
  - `vision/engine.py`: `VisionEngine(models_dir: Path)`, `.scan(image: str) -> dict` (`{"size": [w, h], "blocks": [{"xyxy": [...], "vertical": bool, "text": str}]}`); 이미지를 못 읽으면 `ValueError("이미지를 읽을 수 없습니다: <path>")`
  - `vision/worker.py`: `serve(lines: Iterable[str], send: Callable[[dict], None], scan: Callable[[str], dict]) -> None`; `main(argv: Sequence[str] | None = None) -> int` (모듈 실행 `python -m manga_translate.vision.worker <models_dir>`). 모델에 문제가 있으면 stderr에 문제 목록을 쓰고 ready 없이 종료 코드 2.
  - `worker_client.vision_worker_argv(models_dir: Path) -> list[str]` = `[sys.executable, "-m", "manga_translate.vision.worker", str(models_dir)]`

- [ ] **Step 1: 회귀 기대값 만들기 (기준: 지금 엔진)**

BallonsTranslator 참조 엔진(PyTorch, 1280)으로 Task 2의 fixture 이미지 세 장을 처리한다. 결과 텍스트는 이 프로젝트용 합성 문장이다.

Run (Git Bash, 저장소 루트):

```bash
.dev/BallonsTranslator/.venv/Scripts/python.exe .dev/spike-onnx/ref_run.py .dev/BallonsTranslator .dev/ref_fixtures.json 1280 \
  "$(cygpath -w tests/fixtures/vision/page1.jpg)" "$(cygpath -w tests/fixtures/vision/page2.jpg)" "$(cygpath -w tests/fixtures/vision/page3.jpg)"
uv run python -c "
import json; from pathlib import Path
ref = json.loads(Path('.dev/ref_fixtures.json').read_text(encoding='utf-8'))
out = {'source': 'BallonsTranslator 3e401b29, ctd torch detect_size 1280 + manga_ocr', 'pages': [
  {'image': p['image'], 'size': p['size'], 'blocks': [{'xyxy': b['xyxy'], 'vertical': b['vertical'], 'text': b['text']} for b in p['blocks']]}
  for p in ref['pages']]}
Path('tests/fixtures/vision/expected.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print([len(p['blocks']) for p in out['pages']])"
rm -f .dev/ref_fixtures.json
```

Expected: 세 페이지의 블록 수가 각각 5 이상.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_vision_engine.py`:

```python
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from manga_translate.vision.models import CTD_MODEL
from manga_translate.vision.worker import serve
from manga_translate.worker_client import WorkerClient, WorkerError, vision_worker_argv

FIXTURES = Path(__file__).parent / "fixtures" / "vision"
MODELS = Path(os.environ.get("MANGA_TRANSLATE_VISION_MODELS", "__none__"))
needs_models = pytest.mark.skipif(not (MODELS / CTD_MODEL).is_file(), reason="vision models not available")


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def test_vision_worker_argv(tmp_path):
    assert vision_worker_argv(tmp_path) == [sys.executable, "-m", "manga_translate.vision.worker", str(tmp_path)]


def test_serve_answers_requests_and_reports_errors():
    sent = []

    def scan(image):
        if image == "bad":
            raise ValueError("이미지를 읽을 수 없습니다: bad")
        return {"size": [1, 2], "blocks": []}

    serve(['{"id": 1, "image": "ok"}\n', "\n", '{"id": 2, "image": "bad"}\n', "not json\n"], sent.append, scan)
    assert sent[0] == {"id": 1, "size": [1, 2], "blocks": []}
    assert sent[1]["id"] == 2 and "이미지를 읽을 수 없습니다" in sent[1]["error"]
    assert sent[2]["id"] is None and "error" in sent[2]


def test_worker_exits_without_ready_when_models_are_missing(tmp_path):
    client = WorkerClient(vision_worker_argv(tmp_path / "no-models"), tmp_path, tmp_path / "worker.log", ready_timeout=60)
    with pytest.raises(WorkerError):
        client.start()
    assert "검출·OCR 모델 파일이 없습니다" in (tmp_path / "worker.log").read_text(encoding="utf-8")


@needs_models
def test_worker_process_matches_the_reference(tmp_path):
    expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
    client = WorkerClient(vision_worker_argv(MODELS), tmp_path, tmp_path / "worker.log", ready_timeout=120, request_timeout=120)
    client.start()
    try:
        for page in expected["pages"]:
            result = client.scan(FIXTURES / page["image"])
            assert list(result.size) == page["size"]
            got, want = result.blocks, page["blocks"]
            assert len(got) == len(want)
            for g, w in zip(got, want):
                assert iou(list(g.xyxy), w["xyxy"]) >= 0.98
                assert g.vertical == w["vertical"]
                assert g.text == w["text"]
    finally:
        client.stop()
```

`tests/helpers/fake_worker.py`:

```python
"""A stand-in vision worker for WorkerClient tests. A fake image is a JSON file:
{"size": [w, h], "blocks": [...]}; {"fail": "msg"} answers with an error; {"crash": true} kills the process.
It prints a line to stderr before ready, like a real worker's library output."""
import json
import os
import sys

print("fake worker starting", file=sys.stderr, flush=True)
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    try:
        with open(request["image"], encoding="utf-8") as f:
            spec = json.load(f)
    except OSError:
        print(json.dumps({"id": request["id"], "error": f"이미지를 읽을 수 없습니다: {request['image']}"}), flush=True)
        continue
    if spec.get("crash"):
        os._exit(3)
    if "fail" in spec:
        print(json.dumps({"id": request["id"], "error": spec["fail"]}), flush=True)
        continue
    print(json.dumps({"id": request["id"], "size": spec["size"], "blocks": spec["blocks"]}, ensure_ascii=False), flush=True)
```

`tests/test_worker.py`를 가짜 워커 기준으로 바꾼다. 지금 파일의 테스트 목록과 기대 동작은 그대로 두고, 다음만 바꾼다:
- 맨 위 import에서 `from manga_translate.engine import EngineLayout`, `WORKER_SCRIPT`, `worker_argv`를 지운다.
- `FAKE_BT` 대신 `FAKE_WORKER = Path(__file__).parent / "helpers" / "fake_worker.py"`를 쓴다. 클라이언트는 `WorkerClient([PYTHON, str(FAKE_WORKER)], tmp_path, tmp_path / "logs" / "worker.log", ...)`로 만든다.
- 가짜 이미지 JSON의 블록은 응답 형식 그대로(`{"xyxy": [...], "vertical": ..., "text": ...}`) 적는다.
- `test_worker_argv`는 지운다(`test_vision_engine.py`의 `test_vision_worker_argv`가 대신한다).
- 로그 확인 테스트는 `"Device name: fake GPU"` 대신 `"fake worker starting"`을 찾는다.

Run: `uv run pytest tests/test_vision_engine.py tests/test_worker.py -v` → FAIL (`vision.worker` 없음, `vision_worker_argv` 없음).

- [ ] **Step 3: 구현**

`src/manga_translate/vision/engine.py`:

```python
"""One page in, text blocks out: detection, then OCR of each block."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from .ctd import CTD
from .models import CTD_MODEL, OCR_DIR
from .ocr import MangaOCR


def read_image(path: str) -> np.ndarray:
    try:
        with Image.open(path) as img:
            return np.array(img.convert("RGB"))
    except (OSError, UnidentifiedImageError) as e:
        raise ValueError(f"이미지를 읽을 수 없습니다: {path}") from e


class VisionEngine:
    def __init__(self, models_dir: Path) -> None:
        self.detector = CTD(models_dir / CTD_MODEL)
        self.ocr = MangaOCR(models_dir / OCR_DIR)

    def scan(self, image: str) -> dict:
        img = read_image(image)
        blocks = self.detector.detect(img)
        xyxys = [[int(v) for v in b.xyxy] for b in blocks]
        texts = self.ocr.read_blocks(img, xyxys)
        return {
            "size": [int(img.shape[1]), int(img.shape[0])],
            "blocks": [
                {"xyxy": xyxy, "vertical": bool(b.vertical), "text": text}
                for xyxy, b, text in zip(xyxys, blocks, texts)
            ],
        }
```

`src/manga_translate/vision/worker.py`:

```python
"""The detection/OCR worker process: python -m manga_translate.vision.worker <models dir>

Loads the models, sends {"ready": true}, then answers one JSON request per stdin line:
  {"id": 1, "image": "C:/.../page.png"} -> {"id": 1, "size": [w, h], "blocks": [...]} or {"id": 1, "error": "..."}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .models import model_problems


def serve(lines: Iterable[str], send: Callable[[dict], None], scan: Callable[[str], dict]) -> None:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request["id"]
            send({"id": request_id, **scan(request["image"])})
        except Exception as e:
            send({"id": request_id, "error": f"{type(e).__name__}: {e}" if not isinstance(e, ValueError) else str(e)})


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    models_dir = Path(args[0])
    # The protocol owns the real stdout; anything a library prints goes to stderr (the worker log).
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    problems = model_problems(models_dir)
    if problems:
        print("\n".join(problems), file=sys.stderr, flush=True)
        return 2
    from .engine import VisionEngine

    engine = VisionEngine(models_dir)

    def send(message: dict) -> None:
        protocol.write(json.dumps(message, ensure_ascii=False) + "\n")
        protocol.flush()

    send({"ready": True})
    serve(sys.stdin, send, engine.scan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`test_serve_answers_requests_and_reports_errors`의 세 번째 요청(`not json`)은 `json.loads`가 `ValueError`의 하위 클래스인 `JSONDecodeError`를 던진다. `error`에 무엇이 들어가든 `"error"` 키만 있으면 된다.

`src/manga_translate/worker_client.py`에서 `WORKER_SCRIPT`, `worker_argv`, `from .engine import EngineLayout`을 지우고 다음을 추가한다(`import sys` 추가):

```python
def vision_worker_argv(models_dir: Path) -> list[str]:
    """The detection/OCR worker runs with the app's own Python."""
    return [sys.executable, "-m", "manga_translate.vision.worker", str(models_dir)]
```

모듈 docstring을 `"""The resident detection/OCR worker: a child process answering one JSON line per page."""`로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `MANGA_TRANSLATE_VISION_MODELS=.dev/vision-models-v1 uv run pytest tests/test_vision_engine.py tests/test_vision_ocr.py tests/test_worker.py -v` → PASS (모델 테스트 포함). 회귀 테스트가 실패하면 Task 4 Step 2의 흑백 변환 확인 결과를 다시 보고, 원인을 보고서에 적는다(허용 오차를 늘리지 않는다).

이 태스크 뒤에도 `app.py`는 아직 `worker_argv`를 import하므로 `uv run pytest -q` 전체는 Task 6에서 통과시킨다. 이 태스크에서는 위 세 파일과 `tests/test_vision_*.py`만 통과하면 된다. 보고서에 전체 실행 결과(실패 목록)를 그대로 적는다.

- [ ] **Step 5: 커밋**

```bash
git add src/manga_translate/vision/engine.py src/manga_translate/vision/worker.py src/manga_translate/worker_client.py tests/helpers/fake_worker.py tests/fixtures/vision/expected.json tests/test_vision_engine.py tests/test_worker.py
git commit -F <메시지 파일>   # 제목: Add the ONNX vision worker process
```

---

### Task 6: 앱 통합과 엔진 제거

**Files:**
- Modify: `src/manga_translate/app.py`, `src/manga_translate/paths.py`
- Delete: `src/manga_translate/engine.py`, `src/manga_translate/scripts/bt_worker.py`, `tests/test_engine.py`, `tests/helpers/fake_bt/` 전체
- Modify: `tests/test_app.py`, `tests/test_paths.py`, `tests/test_imports.py`, `tests/test_window.py`(필요한 경우)

**Interfaces:**
- Consumes: `vision_worker_argv` (Task 5), `model_problems` (Task 1)
- Produces:
  - `COMPONENTS = (("llama", "llama.cpp", "약 0.6GB"), ("model", "번역 모델", "약 5GB"))`, `MODEL_SIZE = COMPONENTS[1][2]`
  - `AppState.install(kind)`는 `"llama"`, `"model"`만 받는다(그 밖은 404).
  - `AppState.start()`: `model_problems(layout.models_dir)`가 비어 있지 않으면 `ApiError(409, "검출·OCR 모델이 없습니다. 프로그램을 다시 받아 주세요.\n" + 문제 목록)`.
  - `Runtime`: `WorkerClient(vision_worker_argv(layout.models_dir), layout.root, layout.logs_dir / "worker.log", job=job)`
  - 라우트에서 `("POST", "/api/install/engine")`이 빠진다.
  - `AppLayout`에서 `engine_dir`, `bundled_uv`, `uv_cache_dir`, `python_dir`, `work_dir`를 지운다. `uv_environment`, `find_uv`를 지운다. `models_dir`(검출·OCR 모델과 번역 GGUF가 함께 있는 곳), `downloads_dir`, `llama_dir`, `llama_server`, `settings_path`, `cache_dir`, `logs_dir`는 남는다.

- [ ] **Step 1: 테스트 먼저 고치기**

`tests/test_app.py`:
- `install_all(layout, with_model=True)`에서 엔진 부분(`EngineLayout` 생성·마커 쓰기)을 지우고, 다음 줄을 추가해 가짜 검출·OCR 모델을 만든다:

```python
    for f in vision_models.MODEL_FILES:
        path = layout.models_dir / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\0" * f.size) if f.size < 1024 else None
```

  크기가 큰 파일을 만들지 않으려고, 이 테스트 파일 맨 위 fixture에서 `vision_models.MODEL_FILES`를 작은 가짜 목록으로 바꾼다:

```python
from manga_translate.vision import models as vision_models
from manga_translate.vision.models import ModelFile


@pytest.fixture(autouse=True)
def tiny_vision_models(monkeypatch):
    monkeypatch.setattr(vision_models, "MODEL_FILES", (ModelFile("ctd/ctd_1280.onnx", "0" * 64, 3), ModelFile("manga-ocr/vocab.txt", "0" * 64, 2)))
```

  그리고 위 `install_all`의 모델 파일 생성은 `path.write_bytes(b"\0" * f.size)`로 단순화한다(가짜 목록은 모두 작다). `app.py`가 `model_problems`를 모듈 속성으로 참조해야 monkeypatch가 먹는다: `from .vision import models as vision_models` 후 `vision_models.model_problems(...)`로 호출한다.
- 엔진 설치·uv 관련 테스트를 지운다(`EngineLayout`, `ENGINE_COMMIT`, `find_uv`, `EngineError` import 포함). `make_runner` 테스트를 지운다.
- `test_state_before_and_after_install`의 구성 요소 키 기대값을 `["llama", "model"]`로 바꾼다.
- `test_routes_cover_the_api`의 기대 집합에서 `("POST", "/api/install/engine")`을 뺀다.
- `test_unknown_component`는 `state.install("engine")`이 404인지 확인하도록 바꾼다.
- 새 테스트를 추가한다:

```python
def test_start_refuses_without_vision_models(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    install_all(layout)
    (layout.models_dir / "ctd" / "ctd_1280.onnx").unlink()
    state = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    with pytest.raises(ApiError) as error:
        state.start()
    assert error.value.status == 409
    assert "검출·OCR 모델이 없습니다" in error.value.message
```

`tests/test_paths.py`: `test_layout`에서 `engine_dir`, `bundled_uv`, `uv_cache_dir`, `python_dir`, `work_dir` 줄을 지운다. `uv_environment`, `find_uv` 테스트와 import를 지운다.

`tests/test_imports.py`: import 목록에서 `manga_translate.engine`을 빼고 `manga_translate.vision.models, manga_translate.vision.worker`를 넣는다. 금지 목록에 `'transformers'`를 추가한다(`vision.worker`는 모델을 import할 때만 onnxruntime을 불러오므로 import만으로는 무겁지 않다).

Run: `uv run pytest tests/test_app.py tests/test_paths.py tests/test_imports.py -q` → FAIL (앱이 아직 엔진을 씀).

- [ ] **Step 2: 구현**

`src/manga_translate/app.py`:
- import에서 `from .engine import ...`, `find_uv`, `uv_environment`, `worker_argv`를 지우고 `from .worker_client import WorkerClient, WorkerError, vision_worker_argv`, `from .vision import models as vision_models`를 넣는다.
- `COMPONENTS`, `MODEL_SIZE`를 위 Interfaces 값으로 바꾼다.
- `make_runner` 함수를 지운다.
- `Runtime.__init__`에서 `EngineLayout` 부분을 지우고 워커를 `WorkerClient(vision_worker_argv(layout.models_dir), layout.root, layout.logs_dir / "worker.log", job=job)`로 만든다.
- `_ready`의 `"engine"` 분기, `can_start`의 `self._ready("engine")`을 지운다.
- `install`의 `"engine"` 분기를 지운다.
- `start()`에서 `can_start` 확인 직후에 추가:

```python
        problems = vision_models.model_problems(self.layout.models_dir)
        if problems:
            raise ApiError(409, "검출·OCR 모델이 없습니다. 프로그램을 다시 받아 주세요.\n" + "\n".join(problems))
```

- `build_routes`에서 `/api/install/engine`을 지운다.
- `main()`에서 `os.environ.update(uv_environment(layout))` 줄을 지운다(`os` import가 더 쓰이지 않으면 함께 지운다).
- 모듈 docstring의 "run the translation engine"은 그대로 둬도 된다(llama-server + 워커).

`src/manga_translate/paths.py`: 위 Interfaces대로 속성과 함수를 지우고, 쓰이지 않게 된 import(`os`, `shutil`, `Callable`, `Mapping` 등 — `app_dir`가 쓰는 것은 남긴다)를 정리한다.

삭제:

```bash
git rm src/manga_translate/engine.py src/manga_translate/scripts/bt_worker.py tests/test_engine.py
git rm -r tests/helpers/fake_bt
```

`src/manga_translate/scripts/`가 비면 그 폴더도 지운다(`__init__.py`만 남았다면 함께 지운다).

`src/manga_translate/web/app.js`: 구성 요소 줄은 서버 상태로 그리므로 바꿀 곳이 없는지 확인만 한다(`"engine"` 문자열이 있으면 지운다).

- [ ] **Step 3: 남은 참조 확인과 전체 테스트**

Run: `git grep -n "engine_dir\|EngineLayout\|setup_engine\|bt_worker\|find_uv\|uv_environment\|worker_argv\|fake_bt\|work_dir\|run_streaming\|install/engine" -- src tests`
Expected: `vision_worker_argv` 말고는 결과 없음.

Run: `MANGA_TRANSLATE_VISION_MODELS=.dev/vision-models-v1 uv run pytest -q` → 모두 PASS. 환경 변수 없이도 `uv run pytest -q` → PASS(모델 테스트 skip).

- [ ] **Step 4: 커밋**

```bash
git add -A src tests
git status --short
git diff --cached --check
git commit -F <메시지 파일>   # 제목: Use the ONNX vision worker and drop the BallonsTranslator engine
```

---

### Task 7: 개발 빌드 스크립트

**Files:**
- Modify: `scripts/build.ps1`

**Interfaces:**
- Consumes: `manga_translate.vision.models.install_models`, `model_problems`; `manga_translate.paths.AppLayout`
- Produces: `build.ps1 [-Dest <folder>] [-Uv <uv.exe>] [-ModelsZip <local vision-models-v1.zip>]` — 앱 venv·wheel·바로가기, 검출·OCR 모델 설치(이미 정상이면 건너뜀). `tools\uv.exe` 복사는 하지 않는다.

- [ ] **Step 1: 스크립트 수정**

`scripts/build.ps1`에서:
- `param`에 `[string]$ModelsZip = ""`를 추가한다.
- `Copy-Item $Uv (Join-Path $Dest "tools\uv.exe") -Force` 줄과 `tools` 폴더 생성(`New-Item ... (Join-Path $Dest "tools")`)을 지운다. `New-Item -ItemType Directory -Force -Path $Dest | Out-Null`만 남긴다.
- 앱 설치 직후(바로가기 만들기 전)에 다음을 추가한다:

```powershell
# Detection/OCR models: install from the release asset (or a local zip) unless they are already in place.
$env:MT_DEST = $Dest
$env:MT_MODELS_ZIP = $ModelsZip
$check = @'
import os, sys
from pathlib import Path
from manga_translate.paths import AppLayout
from manga_translate.vision.models import install_models, model_problems
layout = AppLayout(Path(os.environ["MT_DEST"]))
if model_problems(layout.models_dir):
    zip_path = os.environ.get("MT_MODELS_ZIP") or None
    install_models(layout.models_dir, layout.downloads_dir, zip_path=Path(zip_path) if zip_path else None)
    print("Installed vision models")
else:
    print("Vision models already installed")
'@
& $python -c $check
if ($LASTEXITCODE -ne 0) { throw "installing the vision models failed" }
Remove-Item Env:MT_DEST, Env:MT_MODELS_ZIP -ErrorAction SilentlyContinue
```

- 맨 위 주석 두 줄을 다음으로 바꾼다:

```powershell
# Build the runnable program folder for development: app venv + app wheel + detection/OCR models + shortcut.
# llama.cpp, the translation model, settings and caches already in the folder are left untouched on rebuild.
```

- [ ] **Step 2: 확인**

실행 중인 manga-translate 앱이 없는지 확인하고:

Run: `powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -ModelsZip C:\Users\serial\source\manga-translate\.dev\vision-models-v1.zip`
Expected: `Installed vision models` 또는 `Vision models already installed`, `Built: C:\Users\serial\Downloads\manga-translate`.

Run: `diff -rq src/manga_translate "$USERPROFILE/Downloads/manga-translate/.venv/Lib/site-packages/manga_translate" -x __pycache__` → 출력 없음.

Run: `"$USERPROFILE/Downloads/manga-translate/.venv/Scripts/python.exe" -c "from pathlib import Path; from manga_translate.vision.models import verify_models; print(verify_models(Path(r'C:\Users\serial\Downloads\manga-translate\models')))"` → `[]`.

Run: 같은 명령으로 빌드를 한 번 더 → `Vision models already installed`.

- [ ] **Step 3: 커밋**

```bash
git add scripts/build.ps1
git commit -F <메시지 파일>   # 제목: Install the vision models in the development build
```

---

### Task 8: 포터블 배포 패키지

**Files:**
- Create: `scripts/package.ps1`, `THIRD_PARTY_NOTICES.txt`, `packaging/사용법.txt`
- Modify: `.gitignore` (필요하면 `dist/` 확인만)

**Interfaces:**
- Consumes: `scripts/launcher/Launcher.cs`, `components.install_llama(layout, *, log, cancel)`, `vision.models.install_models`
- Produces: `package.ps1 [-Uv <uv.exe>] [-ModelsZip <local zip>]` → `dist\manga-translate-<version>-win64.zip` (version은 `pyproject.toml`의 `version`), 압축 안의 최상위 폴더 이름은 `manga-translate`.

- [ ] **Step 1: 사용자용 문서 두 개 작성**

`packaging/사용법.txt` (UTF-8, CRLF로 변환하지 않아도 메모장에서 열린다):

```text
manga-translate — 일본 만화를 한 장씩 보여주며 한국어 번역을 겹쳐 보여주는 뷰어

요구 사항
- Windows 10/11, NVIDIA RTX 30 시리즈 이상 그래픽카드
- Microsoft Edge WebView2 런타임 (Windows 11 기본 포함)
- 번역 모델을 받을 여유 공간 약 6GB

시작하기
1. manga-translate.exe를 실행합니다.
   "Windows의 PC 보호" 창이 뜨면 "추가 정보" → "실행"을 누릅니다(서명되지 않은 프로그램이라 뜨는 경고입니다).
2. 구성 요소 화면에서 "번역 모델"의 "설치"를 누릅니다(약 5GB). 가진 GGUF 모델이 있으면 "변경..."으로 고릅니다.
3. "시작"을 누르고, "폴더 열기"로 만화 폴더를 고른 뒤 책을 선택합니다.

조작: ← → / 화면 좌우 클릭 / 휠로 넘기기, T로 번역 표시 켜기·끄기, 번역 칸에 마우스를 올리면 원문.
모든 파일은 이 폴더 안에만 저장됩니다. 문제가 생기면 logs 폴더를 확인하세요.
소스와 라이선스: https://github.com/kyj0503/manga-translate (GPL-3.0)
```

`THIRD_PARTY_NOTICES.txt`:

```text
manga-translate is licensed under the GNU General Public License v3.0 (see LICENSE).
Source: https://github.com/kyj0503/manga-translate

This package includes or downloads the following third-party components.

Code ported into manga-translate (GPL-3.0)
- BallonsTranslator (https://github.com/dmMaze/BallonsTranslator), commit 3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8:
  text-line grouping (manga_translate/vision/grouping.py) and detector post-processing (manga_translate/vision/ctd.py).
- comic-text-detector (https://github.com/dmMaze/comic-text-detector), commit 440b978563c71b758e31aaa315d100faba1efa2f:
  detector pre/post-processing (manga_translate/vision/ctd.py).

Models (models/)
- models/ctd/ctd_1280.onnx: converted by this project to ONNX (fixed 1280x1280 input) from comictextdetector.pt
  distributed at https://huggingface.co/dreMaz/mit_models (comic-text-detector / BallonsTranslator, dmMaze).
  The original weights carry no separate license statement; they are distributed with the GPL-3.0 projects above.
- models/manga-ocr/encoder.onnx: onnx-community/manga-ocr-base-ONNX (Apache-2.0), an export of
  kha-white/manga-ocr-base (Apache-2.0, https://huggingface.co/kha-white/manga-ocr-base).
- models/manga-ocr/cross_kv.onnx, decoder_step.onnx: converted by this project from kha-white/manga-ocr-base (Apache-2.0).
- models/manga-ocr/vocab.txt: from kha-white/manga-ocr-base (Apache-2.0).
- The translation model (GGUF) is downloaded by the user from Hugging Face under its own license
  (default: unsloth/gemma-4-E4B-it-GGUF, Gemma terms of use).

Programs and libraries
- llama.cpp / llama-server (MIT, https://github.com/ggml-org/llama.cpp), with NVIDIA CUDA runtime DLLs
  (NVIDIA CUDA EULA) from the llama.cpp release.
- Python (PSF License), python-build-standalone (https://github.com/astral-sh/python-build-standalone).
- onnxruntime (MIT), OpenCV / opencv-python-headless (Apache-2.0), numpy (BSD-3-Clause), Pillow (MIT-CMU),
  shapely (BSD-3-Clause), pyclipper (MIT), jaconv (MIT), httpx (BSD-3-Clause), natsort (MIT),
  pywebview (BSD-3-Clause), pythonnet (MIT), bottle (MIT), and their dependencies as installed in python\Lib\site-packages
  (each package's license file is in its *.dist-info folder).
```

- [ ] **Step 2: 패키징 스크립트 작성**

`scripts/package.ps1`:

```powershell
# Build the portable release: dist\manga-translate-<version>-win64.zip with a launcher, a standalone Python with the
# app installed, llama.cpp and the detection/OCR models. The translation model is downloaded by the user in the app.
param(
    [string]$Uv = "",
    [string]$ModelsZip = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Uv) { $Uv = (Get-Command uv -ErrorAction Stop).Source }

$version = (Select-String -Path (Join-Path $repo "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$dist = Join-Path $repo "dist"
$work = Join-Path $dist "work"
$stage = Join-Path $dist "manga-translate"
$zip = Join-Path $dist "manga-translate-$version-win64.zip"
foreach ($p in $work, $stage, $zip) { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
New-Item -ItemType Directory -Force -Path $work, $stage | Out-Null

# 1. A clean standalone Python 3.12 (python-build-standalone via uv), copied to <stage>\python.
$pyInstall = Join-Path $work "python-install"
$env:UV_PYTHON_INSTALL_DIR = $pyInstall
& $Uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw "uv python install failed" }
Remove-Item Env:UV_PYTHON_INSTALL_DIR
$pyDir = Get-ChildItem $pyInstall -Directory | Where-Object { $_.Name -like "cpython-3.12*" } | Select-Object -First 1
if (-not $pyDir) { throw "standalone Python not found in $pyInstall" }
Copy-Item -Recurse $pyDir.FullName (Join-Path $stage "python")
$python = Join-Path $stage "python\python.exe"
$marker = Join-Path $stage "python\Lib\EXTERNALLY-MANAGED"
if (Test-Path $marker) { Remove-Item $marker }

# 2. The app and its locked dependencies.
$reqs = Join-Path $work "requirements.txt"
& $Uv export --project $repo --frozen --no-dev --no-hashes --no-emit-project -o $reqs
if ($LASTEXITCODE -ne 0) { throw "uv export failed" }
& $Uv pip install --python $python --no-deps -r $reqs
if ($LASTEXITCODE -ne 0) { throw "installing dependencies failed" }
& $Uv build --wheel --out-dir (Join-Path $work "wheel") $repo
if ($LASTEXITCODE -ne 0) { throw "uv build failed" }
$wheel = Get-ChildItem (Join-Path $work "wheel") -Filter *.whl | Select-Object -First 1
& $Uv pip install --python $python --no-deps $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "installing the app failed" }

# 3. The launcher.
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:winexe /codepage:65001 /reference:System.Windows.Forms.dll `
    /out:(Join-Path $stage "manga-translate.exe") (Join-Path $repo "scripts\launcher\Launcher.cs")
if ($LASTEXITCODE -ne 0) { throw "building the launcher failed" }

# 4 + 5. llama.cpp and the detection/OCR models, with the app's own installers (SHA-256 checked).
$env:MT_STAGE = $stage
$env:MT_MODELS_ZIP = $ModelsZip
$install = @'
import os
from pathlib import Path
from manga_translate import components
from manga_translate.paths import AppLayout
from manga_translate.vision.models import install_models
layout = AppLayout(Path(os.environ["MT_STAGE"]))
components.install_llama(layout)
zip_path = os.environ.get("MT_MODELS_ZIP") or None
install_models(layout.models_dir, layout.downloads_dir, zip_path=Path(zip_path) if zip_path else None)
'@
& $python -c $install
if ($LASTEXITCODE -ne 0) { throw "installing llama.cpp or the models failed" }
Remove-Item Env:MT_STAGE, Env:MT_MODELS_ZIP -ErrorAction SilentlyContinue
foreach ($leftover in "downloads", "settings.json", "cache", "logs") {
    $p = Join-Path $stage $leftover
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
Get-ChildItem $stage -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# 6. Notices and the user guide.
Copy-Item (Join-Path $repo "LICENSE") $stage
Copy-Item (Join-Path $repo "THIRD_PARTY_NOTICES.txt") $stage
Copy-Item (Join-Path $repo "packaging\*.txt") $stage

# 7. The zip.
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Remove-Item -Recurse -Force $work
Write-Host "Packaged: $zip"
```

`components.install_llama`가 다운로드 폴더(`layout.downloads_dir`)를 스테이지 안에 만들므로 끝에 지운다. `install_models`도 같은 폴더를 쓴다(`-ModelsZip`을 주면 받지 않는다).

- [ ] **Step 3: 패키지 만들기**

Run: `powershell -ExecutionPolicy Bypass -File scripts\package.ps1 -ModelsZip C:\Users\serial\source\manga-translate\.dev\vision-models-v1.zip`
Expected: `Packaged: ...\dist\manga-translate-0.1.0-win64.zip`. zip 크기 1.0~1.6GB.

- [ ] **Step 4: 풀어서 확인 (창 없이)**

```powershell
$verify = "C:\Users\serial\source\manga-translate\dist\verify"
if (Test-Path $verify) { Remove-Item -Recurse -Force $verify }
Expand-Archive "C:\Users\serial\source\manga-translate\dist\manga-translate-0.1.0-win64.zip" $verify
Get-ChildItem "$verify\manga-translate" | Select-Object Name
```

Expected: `manga-translate.exe`, `python`, `runtime`, `models`, `LICENSE`, `THIRD_PARTY_NOTICES.txt`, `사용법.txt`.

uv와 저장소 venv가 PATH에 없는 상태로 확인 스크립트를 돌린다. 스크립트는 `dist\verify\check.py`에 쓴다(저장소에 커밋하지 않는다):

```python
"""Checks an unpacked release without a window: layout, vision worker, one sample page, server state."""
import sys
import threading
from pathlib import Path

import httpx

from manga_translate.app import AppState, build_routes, WEB_DIR
from manga_translate.paths import AppLayout, app_dir
from manga_translate.server import make_server
from manga_translate.vision.models import verify_models
from manga_translate.worker_client import WorkerClient, vision_worker_argv

root = app_dir()
print("app_dir", root)
layout = AppLayout(root)
print("models", verify_models(layout.models_dir))
sample = sorted(p for p in Path(r"C:\Users\serial\Downloads\sample").iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})[0]
client = WorkerClient(vision_worker_argv(layout.models_dir), root, root / "logs" / "worker.log", ready_timeout=120)
client.start()
result = client.scan(sample)
print("sample blocks", len(result.blocks), "size", result.size)
client.stop()


class Dialogs:
    def pick_folder(self):
        return None

    def pick_model(self):
        return None


state = AppState(layout, Dialogs())
server = make_server(build_routes(state), "t", WEB_DIR)
threading.Thread(target=server.serve_forever, daemon=True).start()
data = httpx.get(f"http://127.0.0.1:{server.server_address[1]}/api/state?token=t", trust_env=False).json()
print("components", [(c["key"], c["ready"]) for c in data["components"]])
server.shutdown()
```

Run (PowerShell):

```powershell
$env:PATH = "C:\Windows\System32;C:\Windows"
& "$verify\manga-translate\python\python.exe" "$verify\check.py"
```

Expected:
- `app_dir`가 `...\dist\verify\manga-translate`
- `models []`
- `sample blocks`가 1 이상
- `components [('llama', True), ('model', False)]`

그 뒤 `Get-CimInstance Win32_Process`로 `manga_translate.vision.worker`를 실행하는 python이 남지 않았는지 확인한다. 확인이 끝나면 `dist\verify`를 지운다. `dist\manga-translate-0.1.0-win64.zip`은 남긴다(Release용). 원문은 출력하지 않는다.

- [ ] **Step 5: 커밋**

```bash
git add scripts/package.ps1 THIRD_PARTY_NOTICES.txt packaging
git commit -F <메시지 파일>   # 제목: Package a portable release zip
```

---

### Task 9: 실제 페이지 비교 도구와 문서

**Files:**
- Create: `tools/parity/reference_run.py`, `tools/parity/compare_sample.py`
- Modify: `README.md`, `AGENTS.md`

**Interfaces:**
- Consumes: `VisionEngine` (Task 5)
- Produces: 두 개발 도구. `reference_run.py`는 BallonsTranslator venv로, `compare_sample.py`는 앱 venv로 실행한다. 둘 다 원문을 출력하지 않는다.

- [ ] **Step 1: 도구 작성**

`tools/parity/reference_run.py` — `.dev\spike-onnx\ref_run.py`에서 VRAM 측정(`vram` import, `VramSampler`)과 시간 측정 필드를 뺀 버전이다. 사용법 docstring:

```python
"""Dev tool: today's reference engine (BallonsTranslator ctd torch + manga_ocr) on a folder of pages.
Run with the BallonsTranslator venv; writes JSON with extracted text (delete it after comparing):
  .dev/BallonsTranslator/.venv/Scripts/python.exe tools/parity/reference_run.py <BallonsTranslator root> <out.json> 1280 <image>...
"""
```

출력 형식: `{"pages": [{"image": <file name>, "size": [w, h], "blocks": [{"xyxy", "vertical", "text"}]}]}`.

`tools/parity/compare_sample.py`:

```python
"""Dev tool: runs the ONNX vision engine on the same pages and prints match metrics against reference_run.py output.
Never prints the text. Run with the app venv:
  MANGA_TRANSLATE_VISION_MODELS=<models dir> uv run python tools/parity/compare_sample.py <reference.json> <image>...
"""
import json
import os
import sys
import time
from pathlib import Path

from manga_translate.vision.engine import VisionEngine


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def edit_distance(s, t):
    prev = list(range(len(t) + 1))
    for i, cs in enumerate(s, 1):
        cur = [i]
        for j, ct in enumerate(t, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cs != ct)))
        prev = cur
    return prev[-1]


def main():
    ref = {p["image"]: p for p in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["pages"]}
    images = [Path(p) for p in sys.argv[2:]]
    t0 = time.perf_counter()
    engine = VisionEngine(Path(os.environ["MANGA_TRANSLATE_VISION_MODELS"]))
    print(f"load {time.perf_counter() - t0:.2f}s")
    totals = {"ref": 0, "got": 0, "matched": 0, "vertical": 0, "exact": 0, "chars": 0, "errors": 0}
    print("| page | ref | got | matched | mean IoU | vertical | OCR exact | CER | s/page |")
    print("|---|---|---|---|---|---|---|---|---|")
    for n, image in enumerate(images, 1):
        want = ref[image.name]["blocks"]
        t = time.perf_counter()
        got = engine.scan(str(image))["blocks"]
        dt = time.perf_counter() - t
        pairs = sorted(((iou(w["xyxy"], g["xyxy"]), i, j) for i, w in enumerate(want) for j, g in enumerate(got)), reverse=True)
        used_w, used_g, matched = set(), set(), []
        for v, i, j in pairs:
            if v >= 0.5 and i not in used_w and j not in used_g:
                used_w.add(i)
                used_g.add(j)
                matched.append((i, j, v))
        vert = sum(want[i]["vertical"] == got[j]["vertical"] for i, j, _ in matched)
        exact = sum(want[i]["text"] == got[j]["text"] for i, j, _ in matched)
        chars = sum(len(want[i]["text"]) for i, j, _ in matched)
        errors = sum(edit_distance(want[i]["text"], got[j]["text"]) for i, j, _ in matched)
        mean_iou = sum(v for *_, v in matched) / len(matched) if matched else 0.0
        print(f"| {n} | {len(want)} | {len(got)} | {len(matched)} | {mean_iou:.3f} | {vert}/{len(matched)} | "
              f"{exact}/{len(matched)} | {100 * errors / max(chars, 1):.2f}% | {dt:.2f} |")
        for key, value in (("ref", len(want)), ("got", len(got)), ("matched", len(matched)), ("vertical", vert),
                           ("exact", exact), ("chars", chars), ("errors", errors)):
            totals[key] += value
    print(f"| all | {totals['ref']} | {totals['got']} | {totals['matched']} | | {totals['vertical']}/{totals['matched']} | "
          f"{totals['exact']}/{totals['matched']} | {100 * totals['errors'] / max(totals['chars'], 1):.2f}% | |")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실제 페이지로 비교 (`Downloads\sample`만)**

```bash
mapfile -t IMGS < <(find /c/Users/serial/Downloads/sample -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) | sort | while IFS= read -r f; do cygpath -w "$f"; done)
.dev/BallonsTranslator/.venv/Scripts/python.exe tools/parity/reference_run.py .dev/BallonsTranslator .dev/ref_sample.json 1280 "${IMGS[@]}"
MANGA_TRANSLATE_VISION_MODELS=.dev/vision-models-v1 uv run python tools/parity/compare_sample.py .dev/ref_sample.json "${IMGS[@]}"
rm -f .dev/ref_sample.json
```

Expected:
- `all` 줄에서 matched = ref = got
- vertical 전부 일치
- OCR exact가 실험 결과 이상(72개 중 71 이상)
- CER 1% 이하
- 페이지당 시간은 약 1~3초(CPU)

결과 표를 보고서에 붙인다. 원문은 출력되지 않는다.

- [ ] **Step 3: 문서**

`README.md`를 다음 구조로 고친다. 요구 사항의 uv는 개발자용으로 옮기고, 설치 절은 두 개로 나눈다. 기존 "사용법", "업데이트", "개발" 내용은 살린다.

1. 소개(검출·OCR은 comic-text-detector와 manga-ocr을 ONNX Runtime(CPU)으로, 번역은 llama.cpp)
2. 요구 사항(사용자: Windows, NVIDIA RTX 30+, WebView2, 약 7GB 여유 공간)
3. **설치 (Release)**:
   1. GitHub Releases에서 `manga-translate-<버전>-win64.zip`을 받습니다.
   2. 압축을 풉니다.
   3. `manga-translate.exe`를 실행합니다(SmartScreen이 뜨면 "추가 정보 → 실행").
   4. 번역 모델을 설치합니다.
4. 사용법(기존 표 포함)
5. **소스에서 빌드 (개발자)**: uv 필요, 기존 clone·build·업데이트 절, `-ModelsZip` 옵션, 개발 실행(`MANGA_TRANSLATE_HOME`), 테스트(`MANGA_TRANSLATE_VISION_MODELS`를 설정하면 모델 테스트까지 돈다)
6. **배포 zip 만들기**: `scripts\package.ps1`
7. 라이선스(GPL-3.0, 이식 코드와 모델 출처는 `THIRD_PARTY_NOTICES.txt`)

`AGENTS.md`의 "그 밖의 규칙"에 추가:

```
- 검출·OCR 모델은 저장소에 커밋하지 않는다. `vision-models-v1.zip` Release 에셋으로만 배포하고, `src/manga_translate/vision/models.py`에 zip과 파일별 SHA-256을 고정한다. 모델을 바꾸면 에셋 이름(버전)을 올린다.
- BallonsTranslator·comic-text-detector에서 옮긴 코드는 파일 머리에 출처 저장소·커밋·GPL-3.0을 적는다.
- 배포 zip은 `scripts\package.ps1`로 만든다(`dist\`, git 무시). 실제 이미지 확인은 `C:\Users\serial\Downloads\sample`만 쓴다.
```

- [ ] **Step 4: 빌드와 전체 테스트**

Run: `MANGA_TRANSLATE_VISION_MODELS=.dev/vision-models-v1 uv run pytest -q` → 모두 PASS.
Run: `powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -ModelsZip C:\Users\serial\source\manga-translate\.dev\vision-models-v1.zip` → 성공. `diff -rq src/manga_translate "$USERPROFILE/Downloads/manga-translate/.venv/Lib/site-packages/manga_translate" -x __pycache__` → 출력 없음.

- [ ] **Step 5: 커밋**

```bash
git add tools/parity README.md AGENTS.md
git commit -F <메시지 파일>   # 제목: Add the parity tools and document the portable release
```

---

### Task 10: Release (컨트롤러와 사용자)

서브에이전트에 맡기지 않는다. 컨트롤러가 사용자 확인을 받으며 진행한다.

- [ ] **Step 1:** 사용자에게 `gh auth login`을 직접 해 달라고 요청한다. 인증 정보는 다루지 않는다.
- [ ] **Step 2:** 사용자 확인을 받은 뒤 `gh release create vision-models-v1 .dev/vision-models-v1.zip --title "Vision models v1" --notes "<출처와 라이선스 요약>"`를 실행한다. 받은 URL로 zip의 SHA-256이 `011a0883...949a`인지 확인한다(다운로드 후 `sha256sum`).
- [ ] **Step 3:** `-ModelsZip` 없이 `scripts\package.ps1`을 다시 실행해 Release 에셋에서 모델을 받는 경로를 확인한다.
- [ ] **Step 4:** 사용자에게 zip을 풀어 `manga-translate.exe`로 실제 창을 확인해 달라고 요청한다.
  - 번역 모델 설치 또는 "변경..."
  - 시작
  - 폴더 열기
  - 넘기기
  - T 키
  - 창을 닫은 뒤 남은 프로세스
- [ ] **Step 5:** 사용자 확인 후 `gh release create v0.1.0 dist/manga-translate-0.1.0-win64.zip --title "manga-translate 0.1.0" --notes "<사용법 요약>"`.
- [ ] **Step 6:** 정리.
  - `.dev\spike-slim`, `.dev\spike-onnx`의 `.venv`와 `cache`, `dist\work`를 지운다.
  - `.dev\vision-models-v1*`는 Release 업로드가 확인된 뒤에 지운다.
  - 지우기 전에 사용자에게 목록을 보여 준다.
