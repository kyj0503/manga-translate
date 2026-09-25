# 계획 1.5: 배치 번역 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `manga-viewer translate <A> <B>`로 A 폴더의 만화 이미지를 번역해 말풍선을 한국어로 덮어 그린 PNG를 B 폴더에 저장한다. 계획 1 최종 리뷰의 수정 사항도 함께 반영한다.

**Architecture:** 계획 1의 파이프라인(`Vision` → `Translator`, `run_bench` 루프)을 그대로 재사용한다. 신규 `render.py`가 말풍선을 칠하고 한국어를 그린다. CLI는 llama-server·클라이언트·비전의 기동과 정리를 `_pipeline` 컨텍스트 매니저 하나로 모아 `bench`와 `translate`가 공유한다.

**Tech Stack:** Python 3.12, uv, Pillow(ImageDraw/ImageFont), httpx, mokuro, llama.cpp llama-server, pytest

**Spec:** `docs/superpowers/specs/2026-09-25-batch-cli-design.md` (번역 파이프라인 세부는 `docs/superpowers/specs/2026-09-25-manga-viewer-design.md` 5장)

## Global Constraints

- 대상 OS: Windows 10/11. 빌드·실행·테스트는 네이티브 Windows(PowerShell)에서 한다. WSL과 Docker는 쓰지 않는다.
- Python `>=3.12,<3.13`. `uv`는 PATH에 없을 수 있다: `C:\Users\serial\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.
- 무거운 의존성(`mokuro`, `torch`, `torchvision`)은 `Vision.__init__` 안에서만 import한다.
- llama-server는 `127.0.0.1`에만 바인딩하고, llama-server와의 HTTP 통신은 시스템 프록시를 쓰지 않는다(`trust_env=False`).
- 사용자에게 보이는 CLI 문구는 한국어로 쓴다. 입력 오류는 종료 코드 2.
- `translate` 종료 코드: 모든 페이지 성공 0, 건너뛴 페이지가 있으면 1, 입력 오류 2.
- 렌더링: 글자 크기 10~72를 이진 탐색, 세로로 긴 박스(높이/너비 > 2)는 좌우 1.5배까지 넓힘, 기본 폰트 `C:\Windows\Fonts\malgun.ttf`, 글자색은 배경 밝기(0.299R+0.587G+0.114B) 128 이상이면 검정 아니면 흰색.
- 샘플 만화(`manga-data/`), 모델(`.dev/`), 결과(`bench-out/`)는 커밋하지 않는다.
- 커밋 작성자 이메일은 repo-local `heroria0503@gmail.com`. 커밋 메시지 끝에 빈 줄 + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 파일 구조

| 파일 | 변경 | 책임 |
|---|---|---|
| `src/manga_viewer/llm/process.py` | 수정 | 헬스체크가 프록시를 쓰지 않음 |
| `src/manga_viewer/llm/client.py` | 수정 | 채팅 클라이언트가 프록시를 쓰지 않음 |
| `src/manga_viewer/bench.py` | 수정 | `run_bench`: 페이지 단위 오류 건너뛰기(`on_error`), 대사 없는 페이지는 문맥에서 제외 |
| `src/manga_viewer/cli.py` | 수정 | UTF-8 출력, 입력 검증(`CliError`), `_pipeline`, `bench`의 부분 결과 저장, `translate` 명령 |
| `src/manga_viewer/render.py` | 신규 | 말풍선 칠하기와 한국어 식자 |
| `tests/test_process.py`, `tests/test_client.py`, `tests/test_bench.py`, `tests/test_cli.py` | 수정 | 위 변경 검증 |
| `tests/test_render.py` | 신규 | 렌더링 검증 |
| `tests/test_imports.py` | 신규 | 무거운 의존성 지연 import 검증 |

---

### Task 1: 견고성 수정 (프록시, 출력 인코딩, 입력 검증, 페이지 단위 오류, 지연 import 테스트)

**Files:**
- Modify: `src/manga_viewer/llm/process.py:81`, `src/manga_viewer/llm/client.py:30`, `src/manga_viewer/bench.py` (`run_bench`), `src/manga_viewer/cli.py` (전체 교체)
- Test: `tests/test_process.py`, `tests/test_client.py`, `tests/test_bench.py`, `tests/test_cli.py`, `tests/test_imports.py`(신규)

**Interfaces:**
- Consumes: 계획 1의 `ManagedServer`, `ChatClient`, `run_bench`, `start_llama_server`, `LlamaConfig`, `KillOnCloseJob`, `Vision`, `Translator`, `ServerStartError`
- Produces:
  - `run_bench(image_paths, vision, translator, glossary, on_page=None, with_image=False, on_error=None) -> list[PageResult]`. `on_error: Callable[[Path, Exception], None] | None`. `vision.analyze` 또는 페이지 이미지 인코딩이 `Exception`을 던지면 `on_error`가 있으면 호출하고 그 페이지를 건너뛴다. 없으면 다시 던진다. 번역된 말풍선이 하나도 없는 페이지는 문맥 deque에 넣지 않는다.
  - `cli.CliError(Exception)`: 메시지를 출력하고 종료 코드 2.
  - `cli._force_utf8_stdout() -> None`
  - `cli._positive_int(value: str) -> int`
  - `cli._add_model_args(parser: argparse.ArgumentParser) -> None`: `--llama-server`(필수), `--model`(필수), `--mmproj`, `--with-image`, `--glossary`, `--ctx-size`(기본 8192), `--no-think`
  - `cli._images(folder: Path, limit: int | None) -> list[Path]`
  - `cli._check_model_args(args) -> None`
  - `cli._pipeline(args, log_path: Path)`: 컨텍스트 매니저, `(vision, translator)`를 yield. 순서: Job 생성 → llama-server 기동(`ServerStartError`/`OSError`는 `CliError`로 변환) → `ChatClient` → `Vision()` → `Translator`. 종료 시 항상 client.close → server.stop → job.close (만들어진 것만).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_process.py` 끝에 추가:

```python
def test_health_check_ignores_proxy_environment(tmp_path, monkeypatch):
    # A dead proxy: if httpx honoured it, /health would never succeed.
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    server = fake_server(tmp_path, ready_after=0.2)
    server.start(timeout=10)
    try:
        assert server.is_healthy()
    finally:
        server.stop()
```

`tests/test_client.py` 끝에 추가:

```python
def test_real_http_ignores_proxy_environment(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    body = json.dumps(completion('{"a": 7}')).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    try:
        client = ChatClient(f"http://127.0.0.1:{server.server_address[1]}", timeout=5)
        assert client.chat_json([], SCHEMA).content == {"a": 7}
        client.close()
    finally:
        server.shutdown()
```

`tests/test_bench.py` 끝에 추가:

```python
def test_textless_page_does_not_take_a_context_slot():
    vision = FakeVision({"1.png": page("a"), "2.png": page(), "3.png": page("b"), "4.png": page("c")})
    translator = FakeTranslator()
    run_bench([Path("1.png"), Path("2.png"), Path("3.png"), Path("4.png")], vision, translator, [])
    assert translator.calls[3]["context"] == [[("a", "ko:a")], [("b", "ko:b")]]


def test_unreadable_page_is_skipped_via_on_error():
    class BrokenVision(FakeVision):
        def analyze(self, path):
            if Path(path).name == "2.png":
                raise OSError("cannot identify image file")
            return super().analyze(path)

    vision = BrokenVision({"1.png": page("a"), "3.png": page("b")})
    errors = []
    results = run_bench(
        [Path("1.png"), Path("2.png"), Path("3.png")],
        vision,
        FakeTranslator(),
        [],
        on_error=lambda path, exc: errors.append((path.name, str(exc))),
    )
    assert [r.image_path.name for r in results] == ["1.png", "3.png"]
    assert errors == [("2.png", "cannot identify image file")]


def test_without_on_error_the_exception_propagates():
    import pytest

    class BrokenVision:
        def analyze(self, path):
            raise OSError("broken")

    with pytest.raises(OSError):
        run_bench([Path("1.png")], BrokenVision(), FakeTranslator(), [])
```

`tests/test_imports.py` (신규):

```python
import subprocess
import sys


def test_heavy_dependencies_are_not_imported_at_module_level():
    code = (
        "import sys\n"
        "import manga_viewer.cli, manga_viewer.bench, manga_viewer.translate, manga_viewer.vision\n"
        "heavy = [m for m in ('torch', 'mokuro') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

`tests/test_cli.py`를 아래 내용으로 **전체 교체**한다. (기존 테스트는 존재하지 않는 `x.exe`를 넘기는데, 이제 파일 존재를 검사하므로 임시 파일을 만든다. 정리 순서 회귀 테스트는 `Vision()` 생성 실패로 바꾼다. 비전 분석 실패는 이제 페이지 건너뛰기로 처리되기 때문이다.)

```python
import os
import subprocess
import sys

import pytest

from manga_viewer.cli import main


def model_files(tmp_path):
    exe = tmp_path / "llama-server.exe"
    model = tmp_path / "m.gguf"
    exe.write_bytes(b"")
    model.write_bytes(b"")
    return ["--llama-server", str(exe), "--model", str(model)]


def test_bench_requires_llama_server_and_model(tmp_path):
    with pytest.raises(SystemExit):
        main(["bench", str(tmp_path)])


def test_bench_with_empty_folder_returns_error(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    code = main(["bench", str(pages), *model_files(tmp_path)])
    assert code == 2
    assert "이미지가 없습니다" in capsys.readouterr().out


def test_missing_folder_returns_error(tmp_path, capsys):
    code = main(["bench", str(tmp_path / "nope"), *model_files(tmp_path)])
    assert code == 2
    assert "폴더가 없습니다" in capsys.readouterr().out


def test_limit_must_be_positive(tmp_path):
    with pytest.raises(SystemExit):
        main(["bench", str(tmp_path), *model_files(tmp_path), "--limit", "0"])


def test_missing_model_file_returns_error(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "1.png").write_bytes(b"")
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"")
    code = main(["bench", str(pages), "--llama-server", str(exe), "--model", str(tmp_path / "missing.gguf")])
    assert code == 2
    assert "모델 파일이 없습니다" in capsys.readouterr().out


def test_with_image_requires_mmproj(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "1.png").write_bytes(b"")
    code = main(["bench", str(pages), *model_files(tmp_path), "--with-image"])
    assert code == 2
    assert "--mmproj" in capsys.readouterr().out


def fake_pipeline(monkeypatch, calls, *, vision_factory, start_error=None):
    """Patch the names _pipeline imports lazily so no GPU, server or model is needed."""
    import manga_viewer.llm.client
    import manga_viewer.llm.llama
    import manga_viewer.vision
    import manga_viewer.winjob

    class FakeServer:
        def stop(self):
            calls.append("server.stop")

    class FakeJob:
        def close(self):
            calls.append("job.close")

    class FakeClient:
        def __init__(self, base_url):
            calls.append("client.open")

        def close(self):
            calls.append("client.close")

    def fake_start(*args, **kwargs):
        if start_error is not None:
            raise start_error
        return FakeServer(), "http://x"

    monkeypatch.setattr(manga_viewer.llm.llama, "start_llama_server", fake_start)
    monkeypatch.setattr(manga_viewer.winjob, "KillOnCloseJob", FakeJob)
    monkeypatch.setattr(manga_viewer.llm.client, "ChatClient", FakeClient)
    monkeypatch.setattr(manga_viewer.vision, "Vision", vision_factory)


def test_pipeline_cleans_up_when_vision_fails_to_load(tmp_path, monkeypatch, capsys):
    from PIL import Image

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (10, 10), "white").save(pages / "1.png")
    calls = []

    def broken_vision():
        raise RuntimeError("boom")

    fake_pipeline(monkeypatch, calls, vision_factory=broken_vision)
    with pytest.raises(RuntimeError, match="boom"):
        main(["bench", str(pages), *model_files(tmp_path), "--out", str(tmp_path / "out")])
    assert calls == ["client.open", "client.close", "server.stop", "job.close"]


def test_server_start_failure_is_a_user_error(tmp_path, monkeypatch, capsys):
    from PIL import Image

    from manga_viewer.llm.process import ServerStartError

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (10, 10), "white").save(pages / "1.png")
    calls = []
    fake_pipeline(monkeypatch, calls, vision_factory=object, start_error=ServerStartError("no gpu"))
    code = main(["bench", str(pages), *model_files(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 2
    assert "LLM 서버를 시작하지 못했습니다" in capsys.readouterr().out
    assert calls == ["job.close"]


def test_output_survives_non_cp949_characters(tmp_path):
    folder = tmp_path / "気"  # not encodable in cp949
    folder.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    code = (
        "import sys\n"
        "from manga_viewer.cli import main\n"
        f"sys.exit(main(['bench', {str(folder)!r}, '--llama-server', 'x', '--model', 'm']))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert result.returncode == 2, result.stderr.decode("utf-8", "replace")
    assert "気" in result.stdout.decode("utf-8")
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_process.py tests/test_client.py tests/test_bench.py tests/test_cli.py tests/test_imports.py -v`
(`$uv`는 Global Constraints의 uv 경로)
Expected: 새 테스트들이 FAIL. 프록시 테스트 2개는 시간 초과 또는 연결 오류, `on_error` 테스트는 `TypeError: run_bench() got an unexpected keyword argument 'on_error'`, 대사 없는 페이지 테스트는 context 불일치, CLI 테스트들은 메시지나 호출 순서 불일치, cp949 테스트는 `UnicodeEncodeError`. `test_imports.py`는 이미 통과할 수 있다(현재 구조가 이미 지연 import이므로 회귀 방지용).

- [ ] **Step 3: 프록시 수정**

`src/manga_viewer/llm/process.py`의 `is_healthy`:

```python
    def is_healthy(self) -> bool:
        try:
            # trust_env=False: never route loopback traffic through a system proxy.
            return httpx.get(self._health_url, timeout=2.0, trust_env=False).status_code == 200
        except httpx.HTTPError:
            return False
```

`src/manga_viewer/llm/client.py`의 `ChatClient.__init__`:

```python
        # trust_env=False: never route loopback traffic through a system proxy.
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport, trust_env=False)
```

- [ ] **Step 4: `run_bench` 수정**

`src/manga_viewer/bench.py`의 `run_bench`를 아래로 교체한다.

```python
def run_bench(
    image_paths: Iterable[Path],
    vision: PageVision,
    translator: PageTranslator,
    glossary: Sequence[GlossaryEntry],
    on_page: Callable[[PageResult], None] | None = None,
    with_image: bool = False,
    on_error: Callable[[Path, Exception], None] | None = None,
) -> list[PageResult]:
    results: list[PageResult] = []
    context: deque[ContextPage] = deque(maxlen=CONTEXT_PAGES)
    for path in image_paths:
        start = time.perf_counter()
        try:
            analysis = vision.analyze(path)
            vision_s = time.perf_counter() - start
            page_image = image_data_url(path) if with_image and analysis.blocks else None
        except Exception as exc:  # unreadable or corrupt page: skip it and keep going
            if on_error is None:
                raise
            on_error(path, exc)
            continue

        translation = translator.translate_page(analysis.blocks, list(context), glossary, page_image)
        pairs = [(b.ja, translation.translations[b.id]) for b in analysis.blocks if b.id in translation.translations]
        if pairs:  # pages without dialogue must not push real dialogue out of the window
            context.append(pairs)

        result = PageResult(path, analysis, translation, vision_s)
        results.append(result)
        if on_page is not None:
            on_page(result)
    return results
```

- [ ] **Step 5: `cli.py` 전체 교체**

```python
from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .bench import BenchMeta, PageResult, run_bench, summarize, write_outputs
from .glossary import load_glossary
from .source import list_images


class CliError(Exception):
    """A problem the user can fix; printed as-is with exit code 2."""


def _force_utf8_stdout() -> None:
    # The Windows console code page (e.g. cp949) cannot encode every kanji in file names.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("1 이상의 정수여야 합니다")
    return number


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llama-server", type=Path, required=True, help="llama-server.exe 경로")
    parser.add_argument("--model", type=Path, required=True, help="GGUF 모델 경로")
    parser.add_argument("--mmproj", type=Path, help="이미지 입력용 mmproj GGUF 경로")
    parser.add_argument("--with-image", action="store_true", help="페이지 이미지를 번역 참고 자료로 함께 보냄 (--mmproj 필요)")
    parser.add_argument("--glossary", type=Path, help="용어집 TOML")
    parser.add_argument("--ctx-size", type=int, default=8192, help="LLM 컨텍스트 길이")
    parser.add_argument("--no-think", action="store_true", help="추론(thinking) 모드가 있는 모델에서 끄기")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(prog="manga-viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="이미지 폴더를 번역하고 속도와 결과를 리포트로 저장")
    bench.add_argument("folder", type=Path, help="만화 이미지 폴더")
    _add_model_args(bench)
    bench.add_argument("--model-id", help="리포트에 표시할 모델 이름 (기본: 파일 이름)")
    bench.add_argument("--limit", type=_positive_int, help="앞에서부터 N장만 처리")
    bench.add_argument("--out", type=Path, default=Path("bench-out"), help="결과 폴더")

    args = parser.parse_args(argv)
    try:
        return _run_bench(args)
    except CliError as e:
        print(e)
        return 2


def _images(folder: Path, limit: int | None) -> list[Path]:
    if not folder.is_dir():
        raise CliError(f"폴더가 없습니다: {folder}")
    images = list_images(folder)[:limit]
    if not images:
        raise CliError(f"이미지가 없습니다: {folder}")
    return images


def _check_model_args(args: argparse.Namespace) -> None:
    if args.with_image and args.mmproj is None:
        raise CliError("--with-image를 쓰려면 --mmproj로 mmproj 파일 경로를 지정해야 합니다.")
    for label, path in (
        ("llama-server", args.llama_server),
        ("모델", args.model),
        ("mmproj", args.mmproj),
        ("용어집", args.glossary),
    ):
        if path is not None and not path.is_file():
            raise CliError(f"{label} 파일이 없습니다: {path}")


@contextmanager
def _pipeline(args: argparse.Namespace, log_path: Path) -> Iterator[tuple[object, object]]:
    """Start llama-server, the chat client and the vision models; always tear down what was started."""
    # Heavy imports only when actually running.
    from .llm.client import ChatClient
    from .llm.llama import LlamaConfig, start_llama_server
    from .llm.process import ServerStartError
    from .translate import Translator
    from .vision import Vision
    from .winjob import KillOnCloseJob

    job = KillOnCloseJob()
    server = None
    client = None
    try:
        print("LLM 서버를 시작하는 중...")
        try:
            server, base_url = start_llama_server(
                LlamaConfig(exe=args.llama_server, model=args.model, mmproj=args.mmproj, ctx_size=args.ctx_size),
                log_path,
                job=job,
            )
        except (ServerStartError, OSError) as e:
            raise CliError(f"LLM 서버를 시작하지 못했습니다: {e}") from e
        client = ChatClient(base_url)
        print("비전 모델을 불러오는 중...")
        vision = Vision()
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if args.no_think else None
        yield vision, Translator(client, extra_body=extra)
    finally:
        if client is not None:
            client.close()
        if server is not None:
            server.stop()
        job.close()


def _run_bench(args: argparse.Namespace) -> int:
    images = _images(args.folder, args.limit)
    _check_model_args(args)
    glossary = load_glossary(args.glossary) if args.glossary else []
    args.out.mkdir(parents=True, exist_ok=True)
    meta = BenchMeta(model_id=args.model_id or args.model.stem, folder=args.folder, with_image=args.with_image)
    results: list[PageResult] = []

    def report(r: PageResult) -> None:
        results.append(r)
        print(
            f"{r.image_path.name}: 말풍선 {len(r.analysis.blocks)}개, "
            f"비전 {r.vision_s:.2f}s, LLM {r.translation.elapsed_s:.2f}s, "
            f"실패 {len(r.translation.failed_ids)}개"
        )

    def skip(path: Path, exc: Exception) -> None:
        print(f"{path.name}: 건너뜀 ({exc})")

    try:
        with _pipeline(args, args.out / "llama-server.log") as (vision, translator):
            run_bench(images, vision, translator, glossary, on_page=report, with_image=args.with_image, on_error=skip)
    finally:
        if results:  # keep partial results even if the run was interrupted
            html_path = write_outputs(results, meta, args.out)
            for key, value in summarize(results).items():
                print(f"{key}: {value}")
            print(f"리포트: {html_path}")
    return 0
```

- [ ] **Step 6: 통과 확인**

Run: `& $uv run pytest tests/test_process.py tests/test_client.py tests/test_bench.py tests/test_cli.py tests/test_imports.py -v`
Expected: 모두 PASS

Run: `& $uv run pytest -v -m "not gpu"`
Expected: GPU 테스트를 제외한 전체 통과, 경고 없음

- [ ] **Step 7: Commit**

```bash
git add src/manga_viewer/llm/process.py src/manga_viewer/llm/client.py src/manga_viewer/bench.py src/manga_viewer/cli.py tests/test_process.py tests/test_client.py tests/test_bench.py tests/test_cli.py tests/test_imports.py
git commit -m "fix: bypass system proxy, force UTF-8 output, skip unreadable pages, validate CLI input"
```

---

### Task 2: 말풍선 렌더러

**Files:**
- Create: `src/manga_viewer/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Box`, `RGB`, `TextBlock` (`manga_viewer.types`)
- Produces:
  - `DEFAULT_FONT: Path = Path("C:/Windows/Fonts/malgun.ttf")`
  - `text_color(bg: RGB) -> RGB`
  - `widen_box(box: Box, image_size: tuple[int, int]) -> Box`
  - `wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]`
  - `fit_text(text: str, font_path: Path, width: int, height: int) -> tuple[ImageFont.FreeTypeFont, list[str]]`
  - `render_page(image: Image.Image, blocks: Sequence[TextBlock], translations: Mapping[int, str], font_path: Path = DEFAULT_FONT) -> Image.Image` — 새 RGB 이미지를 반환하고 입력은 바꾸지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_render.py`:

```python
import pytest
from PIL import Image, ImageDraw

from manga_viewer.render import (
    DEFAULT_FONT,
    fit_text,
    render_page,
    text_color,
    widen_box,
    wrap_text,
)
from manga_viewer.types import TextBlock

pytestmark = pytest.mark.skipif(not DEFAULT_FONT.exists(), reason="Malgun Gothic not installed")


def font(size):
    from PIL import ImageFont

    return ImageFont.truetype(str(DEFAULT_FONT), size)


def test_text_color_contrasts_with_background():
    assert text_color((255, 255, 255)) == (0, 0, 0)
    assert text_color((20, 20, 20)) == (255, 255, 255)


def test_narrow_box_is_widened_within_image():
    assert widen_box((100, 0, 120, 100), (1000, 1000)) == (95, 0, 125, 100)
    assert widen_box((0, 0, 20, 100), (1000, 1000)) == (0, 0, 25, 100)


def test_wide_box_is_unchanged():
    assert widen_box((0, 0, 100, 100), (1000, 1000)) == (0, 0, 100, 100)


def test_wrap_text_respects_width_and_keeps_every_character():
    f = font(20)
    text = "안녕하세요 오늘은 날씨가 정말 좋네요"
    lines = wrap_text(text, f, 90)
    assert len(lines) > 1
    assert all(f.getlength(line) <= 90 for line in lines)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")


def test_wrap_text_breaks_a_long_word_by_character():
    f = font(20)
    lines = wrap_text("가나다라마바사아자차카타파하", f, 50)
    assert len(lines) > 1
    assert all(f.getlength(line) <= 50 for line in lines)
    assert "".join(lines) == "가나다라마바사아자차카타파하"


def test_longer_text_gets_a_smaller_font():
    short_font, _ = fit_text("응", DEFAULT_FONT, 100, 100)
    long_font, long_lines = fit_text("이건 정말 긴 대사라서 작게 써야 들어갑니다", DEFAULT_FONT, 100, 100)
    assert long_font.size < short_font.size
    assert all(long_font.getlength(line) <= 100 for line in long_lines)


def test_render_page_covers_text_and_draws_translation():
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).rectangle((60, 60, 140, 140), fill="black")  # "Japanese text"
    block = TextBlock(id=0, box=(50, 50, 150, 150), vertical=False, ja="x", bg_color=(255, 255, 255))

    out = render_page(image, [block], {0: "안녕"})

    assert out is not image
    assert image.getpixel((61, 61)) == (0, 0, 0)  # input untouched
    assert out.getpixel((61, 61)) == (255, 255, 255)  # old text painted over
    inside = out.crop((50, 50, 150, 150)).convert("L")
    assert inside.getextrema()[0] < 128  # some dark translated glyphs were drawn
    assert out.getpixel((10, 10)) == (255, 255, 255)  # outside untouched


def test_render_page_leaves_untranslated_bubbles_alone():
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).rectangle((60, 60, 140, 140), fill="black")
    block = TextBlock(id=0, box=(50, 50, 150, 150), vertical=False, ja="x", bg_color=(255, 255, 255))

    out = render_page(image, [block], {})

    assert out.getpixel((61, 61)) == (0, 0, 0)
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_render.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'manga_viewer.render'`

- [ ] **Step 3: 구현**

`src/manga_viewer/render.py`:

```python
"""Paint over detected speech bubbles and typeset the Korean translation into them."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

from .types import RGB, Box, TextBlock

DEFAULT_FONT = Path("C:/Windows/Fonts/malgun.ttf")
MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 72
LINE_SPACING = 1.15
PADDING_RATIO = 0.06  # of the box's shorter side, kept free on every edge
NARROW_ASPECT = 2.0  # height / width above which a box is treated as a vertical-text column
WIDEN_FACTOR = 1.5


def text_color(bg: RGB) -> RGB:
    luminance = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return (0, 0, 0) if luminance >= 128 else (255, 255, 255)


def widen_box(box: Box, image_size: tuple[int, int]) -> Box:
    """Japanese vertical text leaves tall, narrow boxes; give horizontal Korean more room."""
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    if width <= 0 or height / width <= NARROW_ASPECT:
        return box
    extra = int(width * (WIDEN_FACTOR - 1) / 2)
    return (max(0, x1 - extra), y1, min(image_size[0], x2 + extra), y2)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if font.getlength(candidate) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            if font.getlength(word) <= max_width:
                line = word
                continue
            for ch in word:  # a single word wider than the box: break between characters
                if line and font.getlength(line + ch) > max_width:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
        if line:
            lines.append(line)
    return lines


@lru_cache(maxsize=256)
def _font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, size)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return int((ascent + descent) * LINE_SPACING)


def _fits(lines: list[str], font: ImageFont.FreeTypeFont, width: int, height: int) -> bool:
    return all(font.getlength(line) <= width for line in lines) and _line_height(font) * len(lines) <= height


def fit_text(text: str, font_path: Path, width: int, height: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest font size whose wrapped text fits; falls back to MIN_FONT_SIZE even if it overflows."""
    best: tuple[ImageFont.FreeTypeFont, list[str]] | None = None
    lo, hi = MIN_FONT_SIZE, MAX_FONT_SIZE
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _font(str(font_path), mid)
        lines = wrap_text(text, font, width)
        if _fits(lines, font, width, height):
            best = (font, lines)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        font = _font(str(font_path), MIN_FONT_SIZE)
        best = (font, wrap_text(text, font, width))
    return best


def render_page(
    image: Image.Image,
    blocks: Sequence[TextBlock],
    translations: Mapping[int, str],
    font_path: Path = DEFAULT_FONT,
) -> Image.Image:
    out = image.convert("RGB")  # always a new image; the input is never modified
    draw = ImageDraw.Draw(out)
    for block in blocks:
        ko = translations.get(block.id)
        if not ko:
            continue  # failed bubble: keep the original Japanese visible
        x1, y1, x2, y2 = widen_box(block.box, out.size)
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=block.bg_color)
        pad = int(min(x2 - x1, y2 - y1) * PADDING_RATIO)
        width, height = x2 - x1 - 2 * pad, y2 - y1 - 2 * pad
        if width <= 0 or height <= 0:
            continue
        font, lines = fit_text(ko, font_path, width, height)
        line_height = _line_height(font)
        top = y1 + pad + (height - line_height * len(lines)) // 2
        color = text_color(block.bg_color)
        for i, line in enumerate(lines):
            left = x1 + pad + (width - font.getlength(line)) / 2
            draw.text((left, top + i * line_height), line, font=font, fill=color)
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_render.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/render.py tests/test_render.py
git commit -m "feat: typeset Korean translations into speech bubbles"
```

---

### Task 3: `translate` 명령

**Files:**
- Modify: `src/manga_viewer/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1의 `CliError`, `_add_model_args`, `_images`, `_check_model_args`, `_pipeline`, `run_bench(..., on_error=...)`; Task 2의 `DEFAULT_FONT`, `render_page`
- Produces: `manga-viewer translate <input> <output> [모델 인자] [--font PATH]`, `cli._run_translate(args) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cli.py` 끝에 추가:

```python
def fake_translation_pipeline(monkeypatch, calls, analysis_by_name):
    """Fake vision returns canned pages (or raises for None); fake translator translates everything."""
    import manga_viewer.translate
    from manga_viewer.translate import PageTranslation

    class FakeVision:
        def analyze(self, path):
            analysis = analysis_by_name[path.name]
            if analysis is None:
                raise OSError("cannot identify image file")
            return analysis

    class FakeTranslator:
        def __init__(self, client, extra_body=None):
            pass

        def translate_page(self, blocks, context_pages=(), glossary=(), page_image=None):
            return PageTranslation({b.id: "안녕" for b in blocks}, (), 1, 1.0, 0.1)

    fake_pipeline(monkeypatch, calls, vision_factory=FakeVision)
    monkeypatch.setattr(manga_viewer.translate, "Translator", FakeTranslator)


def one_bubble_page():
    from manga_viewer.types import PageAnalysis, TextBlock

    block = TextBlock(id=0, box=(10, 10, 90, 90), vertical=False, ja="こんにちは", bg_color=(255, 255, 255))
    return PageAnalysis(width=100, height=100, blocks=(block,))


def test_translate_saves_rendered_pages_and_skips_broken_ones(tmp_path, monkeypatch, capsys):
    from PIL import Image, ImageDraw

    src = tmp_path / "in"
    dst = tmp_path / "out"
    src.mkdir()
    img = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(img).rectangle((20, 20, 80, 80), fill="black")
    img.save(src / "1.png")
    (src / "2.jpg").write_bytes(b"not an image")
    calls = []
    fake_translation_pipeline(monkeypatch, calls, {"1.png": one_bubble_page(), "2.jpg": None})

    code = main(["translate", str(src), str(dst), *model_files(tmp_path)])

    out = capsys.readouterr().out
    assert code == 1  # one page skipped
    assert (dst / "1.png").exists()
    assert not (dst / "2.png").exists()
    assert Image.open(dst / "1.png").getpixel((21, 21)) == (255, 255, 255)  # bubble painted over
    assert "2.jpg: 건너뜀" in out
    assert "저장 1장, 건너뜀 1장" in out
    assert calls[-3:] == ["client.close", "server.stop", "job.close"]


def test_translate_all_pages_ok_returns_zero(tmp_path, monkeypatch, capsys):
    from PIL import Image

    src = tmp_path / "in"
    src.mkdir()
    Image.new("RGB", (100, 100), "white").save(src / "1.png")
    fake_translation_pipeline(monkeypatch, [], {"1.png": one_bubble_page()})
    assert main(["translate", str(src), str(tmp_path / "out"), *model_files(tmp_path)]) == 0


def test_translate_refuses_same_input_and_output(tmp_path, capsys):
    src = tmp_path / "in"
    src.mkdir()
    (src / "1.png").write_bytes(b"")
    code = main(["translate", str(src), str(src), *model_files(tmp_path)])
    assert code == 2
    assert "출력 폴더는 입력 폴더와 달라야 합니다" in capsys.readouterr().out


def test_translate_missing_font_returns_error(tmp_path, capsys):
    src = tmp_path / "in"
    src.mkdir()
    (src / "1.png").write_bytes(b"")
    code = main(["translate", str(src), str(tmp_path / "out"), *model_files(tmp_path), "--font", str(tmp_path / "x.ttf")])
    assert code == 2
    assert "폰트 파일이 없습니다" in capsys.readouterr().out
```

- [ ] **Step 2: 실패 확인**

Run: `& $uv run pytest tests/test_cli.py -v`
Expected: 새 테스트 4개 FAIL (`invalid choice: 'translate'`로 `SystemExit`)

- [ ] **Step 3: 구현**

`src/manga_viewer/cli.py`에 import 한 줄을 추가한다.

```python
import tempfile
```

(`import sys` 아래에 둔다.)

`main`에서 `bench` 파서 정의 뒤, `args = parser.parse_args(argv)` 앞에 추가한다.

```python
    translate = sub.add_parser("translate", help="폴더의 만화를 번역해 한국어로 덮어 그린 이미지를 저장")
    translate.add_argument("input", type=Path, help="원본 만화 이미지 폴더")
    translate.add_argument("output", type=Path, help="번역 이미지를 저장할 폴더")
    _add_model_args(translate)
    translate.add_argument("--font", type=Path, default=None, help="한국어 폰트 파일 (기본: 맑은 고딕)")
```

`main`의 실행 부분을 아래로 바꾼다.

```python
    args = parser.parse_args(argv)
    try:
        if args.command == "translate":
            return _run_translate(args)
        return _run_bench(args)
    except CliError as e:
        print(e)
        return 2
```

파일 끝에 `_run_translate`를 추가한다.

```python
def _run_translate(args: argparse.Namespace) -> int:
    from PIL import Image

    from .render import DEFAULT_FONT, render_page

    images = _images(args.input, None)
    _check_model_args(args)
    font = args.font or DEFAULT_FONT
    if not font.is_file():
        raise CliError(f"폰트 파일이 없습니다: {font}")
    if args.output.resolve() == args.input.resolve():
        raise CliError("출력 폴더는 입력 폴더와 달라야 합니다.")
    glossary = load_glossary(args.glossary) if args.glossary else []
    args.output.mkdir(parents=True, exist_ok=True)

    total = len(images)
    counts = {"saved": 0, "skipped": 0, "failed_bubbles": 0}

    def save(r: PageResult) -> None:
        try:
            with Image.open(r.image_path) as img:
                page = render_page(img, r.analysis.blocks, r.translation.translations, font)
            page.save(args.output / f"{r.image_path.stem}.png")
        except OSError as exc:
            skip(r.image_path, exc)
            return
        counts["saved"] += 1
        counts["failed_bubbles"] += len(r.translation.failed_ids)
        done = counts["saved"] + counts["skipped"]
        print(
            f"[{done}/{total}] {r.image_path.name}: 말풍선 {len(r.analysis.blocks)}개, "
            f"번역 실패 {len(r.translation.failed_ids)}개"
        )

    def skip(path: Path, exc: Exception) -> None:
        counts["skipped"] += 1
        print(f"{path.name}: 건너뜀 ({exc})")

    log_path = Path(tempfile.gettempdir()) / "manga-viewer" / "llama-server.log"
    with _pipeline(args, log_path) as (vision, translator):
        run_bench(images, vision, translator, glossary, on_page=save, with_image=args.with_image, on_error=skip)

    print(
        f"완료: 저장 {counts['saved']}장, 건너뜀 {counts['skipped']}장, "
        f"번역 실패 말풍선 {counts['failed_bubbles']}개"
    )
    print(f"결과 폴더: {args.output}")
    return 0 if counts["skipped"] == 0 else 1
```

- [ ] **Step 4: 통과 확인**

Run: `& $uv run pytest tests/test_cli.py -v`
Expected: 모두 PASS

Run: `& $uv run pytest -v -m "not gpu"`
Expected: 전체 통과, 경고 없음

- [ ] **Step 5: Commit**

```bash
git add src/manga_viewer/cli.py tests/test_cli.py
git commit -m "feat: add translate command that writes typeset pages to an output folder"
```

---

### Task 4: 실제 샘플로 확인 (수동)

코드 변경은 없다. 사용자에게 결과 이미지를 보여주기 위한 실행이다.

- [ ] **Step 1: 샘플 번역**

`.dev` 아래의 모델 경로는 `.superpowers/sdd/2026-09-25-plan1-translation-core/task-10-report.md`에 기록된 실제 파일 이름을 쓴다.

```powershell
& $uv run manga-viewer translate manga-data\173830003 bench-out\translate-e4b --llama-server .dev\llama\llama-server.exe --model .dev\models\gemma-4-e4b\<Q4 파일> --mmproj .dev\models\gemma-4-e4b\<mmproj 파일> --with-image --no-think
```

Expected: 6장 모두 저장, 종료 코드 0, `bench-out\translate-e4b\*.png` 생성

- [ ] **Step 2: 사용자 확인**

결과 폴더 경로를 사용자에게 알리고 식자 품질(글자 크기, 줄바꿈, 가려진 그림)을 확인받는다. 저장소에는 아무것도 커밋하지 않는다.
