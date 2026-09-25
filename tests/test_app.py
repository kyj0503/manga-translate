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
