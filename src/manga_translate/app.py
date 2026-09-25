"""The viewer app: install components, run the translation engine, and serve books to the window."""
from __future__ import annotations

import logging
import os
import secrets
import threading
from collections import deque
from pathlib import Path
from typing import Callable, Protocol, Sequence

from . import components
from .cache import TranslationCache
from .download import Cancelled, InstallError
from .engine import EngineError, EngineLayout, run_streaming, setup_engine
from .library import Book, is_inside, scan_library
from .llm.llama import LlamaConfig, start_llama_server
from .llm.process import ServerStartError
from .paths import AppLayout, app_dir, find_uv, uv_environment
from .scheduler import Scheduler, process_page
from .server import ApiError, Response, Route, make_server
from .settings import PAGE_DIRECTIONS, Settings, load_settings, save_settings
from .translate import TranslateError, Translator
from .winjob import KillOnCloseJob
from .worker_client import WorkerClient, WorkerError, worker_argv

logger = logging.getLogger(__name__)

TITLE = "manga-translate"
WEB_DIR = Path(__file__).parent / "web"
LOG_FILES = ("app.log", "worker.log", "llama-server.log")
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
        self._settings_lock = threading.Lock()  # guards settings mutation + save against concurrent API calls
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
        """Save ``self.settings``. Callers must hold ``self._settings_lock``."""
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
            with self._settings_lock:
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
            with self._settings_lock:
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
        with self._settings_lock:
            self.settings.positions[str(book.dir)] = index
            self._save()
        return {}

    def set_page_direction(self, value: str) -> dict:
        if value not in PAGE_DIRECTIONS:
            raise ApiError(400, f"넘기는 방향 값이 올바르지 않습니다: {value}")
        with self._settings_lock:
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
