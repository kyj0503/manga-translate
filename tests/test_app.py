import sys
import threading
import time
import types
from pathlib import Path

import pytest

import manga_translate.app as app_module
import manga_translate.components as components
from manga_translate.app import (
    AppState,
    Runtime,
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
        self.alive_value = True

    def alive(self):
        return self.alive_value

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


def test_state_reports_runtime_error_when_the_server_died(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    install_all(layout)
    state = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    state.start()
    wait_task(state)
    assert state.state()["runtime"] == "ready"

    state.runtime.alive_value = False
    data = state.state()
    assert data["runtime"] == "error"
    assert "다시 시작" in data["error"]
    assert data["can_start"] is True  # "시작" must be usable to restart


def test_start_restarts_a_dead_runtime_and_closes_the_old_one(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    install_all(layout)
    state = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    state.start()
    wait_task(state)
    old_runtime = state.runtime
    old_runtime.alive_value = False

    state.start()
    wait_task(state)

    assert old_runtime.closed is True
    assert state.runtime is not old_runtime
    assert state.state()["runtime"] == "ready"


def test_start_is_a_no_op_while_the_runtime_is_alive(tmp_path, small_model):
    layout = AppLayout(tmp_path)
    install_all(layout)
    state = AppState(layout, FakeDialogs(), runtime_factory=FakeRuntime)
    state.start()
    wait_task(state)
    live_runtime = state.runtime

    state.start()

    assert state.runtime is live_runtime
    assert live_runtime.closed is False


def test_runtime_close_kills_the_job_before_waiting_on_worker_and_server():
    order = []

    class FakeJob:
        def close(self):
            order.append("job")

    class FakeWorker:
        def stop(self):
            order.append("worker")

    class FakeServer:
        def stop(self):
            order.append("server")

    class FakeSched:
        def stop(self):
            order.append("scheduler")

    runtime = Runtime.__new__(Runtime)
    runtime._job = FakeJob()
    runtime._worker = FakeWorker()
    runtime._server = FakeServer()
    runtime.scheduler = FakeSched()

    runtime.close()

    assert order == ["scheduler", "job", "worker", "server"]


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


def test_concurrent_save_position_is_thread_safe(tmp_path):
    book_count = 8
    pages_per_book = 50
    root = tmp_path / "만화"
    for b in range(book_count):
        folder = root / f"book{b:02d}"
        folder.mkdir(parents=True)
        for p in range(pages_per_book):
            (folder / f"{p:03d}.png").write_bytes(b"x")

    layout = AppLayout(tmp_path / "app")
    state = AppState(layout, FakeDialogs(folder=str(root)), runtime_factory=FakeRuntime)
    state.open_library()
    assert len(state.books) == book_count

    errors: list[Exception] = []

    def worker(book_id: int) -> None:
        try:
            for index in range(pages_per_book):
                state.save_position(book_id, index)
        except Exception as e:  # pragma: no cover - only hit on a real race
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(book_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
        assert not t.is_alive()

    assert errors == []
    loaded = load_settings(layout.settings_path)
    for book in state.books:
        assert loaded.positions[str(book.dir)] == pages_per_book - 1


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


# --- startup failures (main), no window ---


def test_main_reports_an_appstate_failure_via_message_box(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "uv_environment", lambda layout: {})  # keep the real env untouched
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace())
    boxes = []
    monkeypatch.setattr(app_module, "_show_startup_error", boxes.append)

    def broken_appstate(*args, **kwargs):
        raise RuntimeError("상태를 만들지 못했습니다")

    monkeypatch.setattr(app_module, "AppState", broken_appstate)

    assert app_module.main() == 1

    assert len(boxes) == 1
    assert "상태를 만들지 못했습니다" in boxes[0]
    assert str(tmp_path / "logs") in boxes[0]
    log_text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "Traceback" in log_text


def test_main_reports_a_reset_logs_failure_via_message_box(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "uv_environment", lambda layout: {})  # keep the real env untouched
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace())
    boxes = []
    monkeypatch.setattr(app_module, "_show_startup_error", boxes.append)

    def broken_reset_logs(logs_dir):
        raise PermissionError("다른 인스턴스가 로그 파일을 쓰고 있습니다")

    monkeypatch.setattr(app_module, "reset_logs", broken_reset_logs)

    assert app_module.main() == 1

    assert len(boxes) == 1
    assert "다른 인스턴스가 로그 파일을 쓰고 있습니다" in boxes[0]
