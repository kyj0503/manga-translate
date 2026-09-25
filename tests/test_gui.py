import sys
from pathlib import Path

import pytest

import manga_viewer.gui as gui
from manga_viewer.engine import ENGINE_COMMIT, EngineError, EngineLayout
from manga_viewer.gui import (
    build_request,
    default_output_dir,
    engine_layout,
    engine_status_text,
    find_uv,
    format_progress,
    make_runner,
    model_label,
    summary_text,
)
from manga_viewer.pipeline import PipelineError, TranslationResult
from manga_viewer.settings import Settings

PYTHON = getattr(sys, "_base_executable", sys.executable)


def test_default_output_dir():
    assert default_output_dir(Path("D:/만화/1권")) == Path("D:/만화/1권_번역")


def test_default_output_dir_at_drive_root():
    assert default_output_dir(Path("D:/")) == Path("D:/번역")


def test_format_progress():
    assert format_progress(0, 0) == "대기 중"
    assert format_progress(3, 6) == "3 / 6장"


def test_model_label():
    assert model_label("") == "(선택되지 않음)"
    assert model_label("C:/models/gemma-4-e4b-Q4_K_M.gguf") == "gemma-4-e4b-Q4_K_M"


def test_engine_layout_and_status(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "default_engine_dir", lambda: tmp_path / "default")
    assert engine_layout(Settings()) == EngineLayout(tmp_path / "default")
    layout = engine_layout(Settings(engine_dir=str(tmp_path / "custom")))
    assert layout == EngineLayout(tmp_path / "custom")
    assert engine_status_text(layout).startswith("설치 필요")
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    assert engine_status_text(layout) == "설치됨"


def test_find_uv(tmp_path, monkeypatch):
    uv = tmp_path / "uv.exe"
    uv.write_bytes(b"")
    monkeypatch.setattr(gui.shutil, "which", lambda name: None)
    assert find_uv(Settings(uv=str(uv))) == uv
    assert find_uv(Settings(uv=str(tmp_path / "gone.exe"))) is None
    monkeypatch.setattr(gui.shutil, "which", lambda name: "C:/tools/uv.exe")
    assert find_uv(Settings()) == Path("C:/tools/uv.exe")


def test_make_runner_streams_and_raises():
    lines = []
    run = make_runner(lines.append)
    run([PYTHON, "-c", "print('설치 중')"])
    assert lines == ["설치 중"]
    with pytest.raises(EngineError, match="코드 3"):
        run([PYTHON, "-c", "import sys; sys.exit(3)"])


def test_make_runner_forwards_job():
    class FakeJob:
        def __init__(self):
            self.pid = None

        def assign(self, pid):
            self.pid = pid

    job = FakeJob()
    run = make_runner(lambda line: None, job=job)
    run([PYTHON, "-c", "pass"])
    assert job.pid is not None


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
    monkeypatch.setattr(gui, "default_engine_dir", lambda: tmp_path / "default")
    req = build_request(Settings(llama_server="C:/l.exe", model="C:/m.gguf"), "D:/in", "D:/out")
    assert req.input_dir == Path("D:/in") and req.output_dir == Path("D:/out")
    assert req.model == Path("C:/m.gguf") and req.llama_server == Path("C:/l.exe")
    assert req.engine == EngineLayout(tmp_path / "default")


def test_summary_text():
    ok = TranslationResult(2, [Path("o/1.png"), Path("o/2.png")], [], 0, None)
    assert summary_text(ok, Path("D:/out")) == "2 / 2장을 번역했습니다.\n저장 위치: D:\\out"
    partial = TranslationResult(2, [Path("o/1.png")], [Path("i/2.png")], 9, Path("C:/tmp/w"))
    text = summary_text(partial, Path("D:/out"))
    assert "1 / 2장을 번역했습니다." in text
    assert "결과가 없는 페이지: 2.png" in text
    assert "작업 폴더: C:\\tmp\\w" in text
    assert "엔진이 오류로 끝났습니다 (코드 9). 로그를 확인하세요." in text
