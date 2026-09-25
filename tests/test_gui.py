import queue
import sys
import threading
import types
from pathlib import Path

import pytest

import manga_translate.components as components
from manga_translate.components import LLAMA_MARKER, LLAMA_TAG, Asset
from manga_translate.engine import ENGINE_COMMIT, EngineError, EngineLayout
from manga_translate.gui import (
    App,
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

    mine = tmp_path / "mine.gguf"
    # chosen file missing and no default installed: no fallback
    assert effective_model(layout, Settings(model=str(mine))) is None
    assert model_status_text(layout, Settings(model=str(mine))) == "mine (파일 없음)"

    layout.models_dir.mkdir()
    (layout.models_dir / "small-model.gguf").write_bytes(b"123")
    assert effective_model(layout, Settings()) == layout.models_dir / "small-model.gguf"
    assert model_status_text(layout, Settings()) == "small-model (설치됨)"

    # chosen file missing but the default is installed: fall back to it
    assert effective_model(layout, Settings(model=str(mine))) == layout.models_dir / "small-model.gguf"
    assert model_status_text(layout, Settings(model=str(mine))) == "mine (파일 없음, 기본 모델 사용)"

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
    assert req.work_root == layout.work_dir


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


def test_make_runner_child_sees_uv_cache_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "uv-cache"))
    lines = []
    run = make_runner(lines.append)
    run([PYTHON, "-c", "import os; print(os.environ['UV_CACHE_DIR'])"])
    assert lines == [str(tmp_path / "uv-cache")]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_closing_job_stops_a_running_command_and_raises_engine_error():
    job = KillOnCloseJob()
    run = make_runner(lambda line: None, job)
    errors = []

    def go():
        try:
            run([PYTHON, "-c", "import time; time.sleep(60)"])
        except EngineError as e:
            errors.append(e)
        except Exception as e:  # pragma: no cover - unexpected failure path
            errors.append(e)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout=1)  # let the child process start
    job.close()
    t.join(timeout=10)
    assert not t.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], EngineError)


def test_run_when_cancelled_reports_cancelled_even_on_error():
    fake_self = types.SimpleNamespace(events=queue.Queue(), cancel=threading.Event())
    fake_self.cancel.set()

    def work():
        raise EngineError("x")

    App._run(fake_self, work, "installed")

    assert fake_self.events.get_nowait() == ("cancelled",)


def test_run_when_not_cancelled_reports_error():
    fake_self = types.SimpleNamespace(events=queue.Queue(), cancel=threading.Event())

    def work():
        raise EngineError("x")

    App._run(fake_self, work, "installed")

    assert fake_self.events.get_nowait() == ("error", "x")
