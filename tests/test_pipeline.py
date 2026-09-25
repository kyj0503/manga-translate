import threading
from pathlib import Path

import pytest

import manga_translate.pipeline as pipeline
from manga_translate.engine import ENGINE_COMMIT, EngineLayout
from manga_translate.llm.process import ServerStartError
from manga_translate.pipeline import PipelineError, TranslationRequest, run_translation, validate


def ready_engine(tmp_path) -> EngineLayout:
    root = tmp_path / "engine"
    (root / ".venv" / "Scripts").mkdir(parents=True, exist_ok=True)
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    (root / ".manga-translate-setup").write_text(ENGINE_COMMIT, encoding="utf-8")
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
    state = {"produce": None, "code": 0, "start_error": None, "on_run": None}
    work = tmp_path / "work"
    closed = threading.Event()

    class FakeServer:
        def stop(self):
            calls.append("server.stop")

    class FakeJob:
        def close(self):
            calls.append("job.close")
            closed.set()

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
        if state["on_run"]:
            state["on_run"]()
        return state["code"]

    def fake_mkdtemp(prefix="", dir=None):
        work.mkdir()
        return str(work)

    monkeypatch.setattr(pipeline, "start_llama_server", fake_start)
    monkeypatch.setattr(pipeline, "KillOnCloseJob", FakeJob)
    monkeypatch.setattr(pipeline, "write_engine_config", fake_config)
    monkeypatch.setattr(pipeline, "run_streaming", fake_run)
    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", fake_mkdtemp)
    return calls, state, work, closed


def test_run_translation_creates_work_dir_under_work_root(tmp_path, monkeypatch):
    recorded = {}

    def fake_mkdtemp(prefix="", dir=None):
        recorded["dir"] = dir
        raise SystemExit("stop before doing real work")  # validate already ran; that's all we need

    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", fake_mkdtemp)
    work_root = tmp_path / "work"
    req = request(tmp_path, "1.jpg", work_root=work_root)

    with pytest.raises(SystemExit):
        run_translation(req, on_log=lambda l: None)

    assert recorded["dir"] == work_root


def test_validate_rejects_bad_requests(tmp_path):
    with pytest.raises(PipelineError, match="폴더가 없습니다"):
        validate(request(tmp_path, "1.jpg", input_dir=tmp_path / "nope"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(PipelineError, match="이미지가 없습니다"):
        validate(request(tmp_path, "1.jpg", input_dir=empty))
    with pytest.raises(PipelineError, match="모델 파일이 없습니다"):
        validate(request(tmp_path, "1.jpg", model=tmp_path / "nope.gguf"))
    with pytest.raises(PipelineError, match="번역 엔진이 설치되어 있지 않습니다"):
        validate(request(tmp_path, "1.jpg", engine=EngineLayout(tmp_path / "none")))
    with pytest.raises(PipelineError, match="출력 폴더는 입력 폴더와 달라야 합니다"):
        validate(request(tmp_path, "1.jpg", output_dir=tmp_path / "in"))


def test_successful_run(tmp_path, fakes):
    calls, _, work, _ = fakes
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
    _, state, work, _ = fakes
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
    _, _, work, _ = fakes
    result = run_translation(request(tmp_path, "1.jpg", keep_work=True), on_log=lambda l: None)
    assert result.ok and result.work_dir == work and work.exists()


def test_server_start_failure(tmp_path, fakes):
    calls, state, _, _ = fakes
    state["start_error"] = ServerStartError("no gpu")
    with pytest.raises(PipelineError, match="LLM 서버를 시작하지 못했습니다"):
        run_translation(request(tmp_path, "1.jpg"), on_log=lambda l: None)
    assert calls == ["job.close"]


def test_prepare_work_dir_failure_logs_work_dir(tmp_path, fakes, monkeypatch):
    _, _, work, _ = fakes
    logs = []

    def failing_prepare(images, exec_dir):
        raise OSError("copy failed")

    monkeypatch.setattr(pipeline, "prepare_work_dir", failing_prepare)

    with pytest.raises(OSError, match="copy failed"):
        run_translation(request(tmp_path, "1.jpg"), on_log=logs.append)

    assert any(f"작업 폴더: {work}" in log for log in logs)


def test_config_failure_keeps_work_and_logs(tmp_path, fakes, monkeypatch):
    from manga_translate.engine import EngineError

    calls, _, work, _ = fakes
    logs = []

    def failing_config(layout, base_url, model_id, run=None):
        raise EngineError("config failed")

    monkeypatch.setattr(pipeline, "write_engine_config", failing_config)

    with pytest.raises(EngineError, match="config failed"):
        run_translation(request(tmp_path, "1.jpg"), on_log=logs.append)

    assert work.exists()
    assert any(f"작업 폴더: {work}" in log for log in logs)
    assert calls[-2:] == ["server.stop", "job.close"]


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
