"""One translation job for the GUI: validate, run llama-server + engine, report progress, collect results."""
from __future__ import annotations

import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .download import check_cancel
from .engine import EngineLayout
from .engine_run import (
    collect_staged_results,
    headless_argv,
    run_streaming,
    stage_pages,
    write_engine_config,
)
from .llm.llama import LlamaConfig, start_llama_server
from .llm.process import ServerStartError
from .source import find_images
from .winjob import KillOnCloseJob

SOURCE_LANGUAGE = "일본어"
TARGET_LANGUAGE = "한국어"


class PipelineError(Exception):
    """A problem the user can fix; the message is shown as-is."""


@dataclass(frozen=True)
class TranslationRequest:
    input_dir: Path
    output_dir: Path
    llama_server: Path
    model: Path
    engine: EngineLayout
    ctx_size: int = 8192
    keep_work: bool = False
    work_root: Path | None = None


@dataclass(frozen=True)
class TranslationResult:
    total: int
    saved: list[Path]
    missing: list[Path]
    engine_exit_code: int
    work_dir: Path | None  # kept for inspection, or None when cleaned up
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not self.missing


def validate(req: TranslationRequest) -> list[Path]:
    if not req.input_dir.is_dir():
        raise PipelineError(f"폴더가 없습니다: {req.input_dir}")
    if req.output_dir.resolve() == req.input_dir.resolve():
        raise PipelineError("출력 폴더는 입력 폴더와 달라야 합니다.")
    images = find_images(req.input_dir, exclude=req.output_dir)
    if not images:
        raise PipelineError(f"이미지가 없습니다 (하위 폴더 포함): {req.input_dir}")
    for label, path in (("llama-server", req.llama_server), ("모델", req.model)):
        if not path.is_file():
            raise PipelineError(f"{label} 파일이 없습니다: {path}")
    if not req.engine.is_ready():
        raise PipelineError("번역 엔진이 설치되어 있지 않습니다. 창의 '번역 엔진' 줄에서 '설치'를 먼저 눌러 주세요.")
    return images


def _stopped(cancel: threading.Event | None) -> bool:
    return cancel is not None and cancel.is_set()


@contextmanager
def _llama_server(
    req: TranslationRequest,
    log_path: Path,
    on_log: Callable[[str], None],
    cancel: threading.Event | None,
) -> Iterator[tuple[KillOnCloseJob, str]]:
    """llama-server in a kill-on-close job; the engine joins the same job.

    Pressing 중단 closes the job, which ends both processes so the blocked calls return.
    """
    job = KillOnCloseJob()
    server = None
    finished = threading.Event()

    def close_job_on_cancel() -> None:
        while not finished.wait(0.2):
            if _stopped(cancel):
                job.close()
                return

    if cancel is not None:
        threading.Thread(target=close_job_on_cancel, daemon=True).start()
    try:
        on_log("LLM 서버를 시작하는 중...")
        try:
            server, base_url = start_llama_server(
                LlamaConfig(exe=req.llama_server, model=req.model, ctx_size=req.ctx_size), log_path, job=job
            )
        except (ServerStartError, OSError) as e:
            check_cancel(cancel)  # stopped by the user, not a failure
            raise PipelineError(f"LLM 서버를 시작하지 못했습니다: {e}") from e
        yield job, base_url
    finally:
        finished.set()
        if server is not None:
            server.stop()
        job.close()


def run_translation(
    req: TranslationRequest,
    *,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    cancel: threading.Event | None = None,
) -> TranslationResult:
    images = validate(req)
    total = len(images)
    if req.work_root is not None:
        req.work_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="manga-translate-", dir=req.work_root))
    exec_dir = work / "pages"
    result_dir = exec_dir / "result"

    last = -1

    def report(done: int) -> None:
        nonlocal last
        done = min(done, total)
        if done != last:
            last = done
            on_progress(done, total)

    def forward(line: str) -> None:
        on_log(line)
        # Progress = pages the engine has already written to result\.
        if result_dir.is_dir():
            report(sum(1 for p in result_dir.iterdir() if p.is_file()))

    report(0)
    code = -1
    staged: list = []
    try:
        staged = stage_pages(images, req.input_dir, exec_dir)
        with _llama_server(req, work / "llama-server.log", on_log, cancel) as (job, base_url):
            check_cancel(cancel)
            on_log("번역 설정을 쓰는 중...")
            write_engine_config(req.engine, base_url, req.model.stem)
            check_cancel(cancel)
            on_log(f"번역을 시작합니다 ({total}장)...")
            code = run_streaming(headless_argv(req.engine, exec_dir), req.engine.root, job=job, on_line=forward)
    except Exception:
        if not _stopped(cancel):
            on_log(f"작업 폴더: {work}")
            raise

    saved, missing = collect_staged_results(exec_dir, req.output_dir, staged)
    report(total - len(missing))
    if _stopped(cancel):
        on_log("번역을 중단했습니다.")
        shutil.rmtree(work, ignore_errors=True)
        return TranslationResult(total, saved, missing, code, None, cancelled=True)
    keep = bool(missing) or req.keep_work
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return TranslationResult(total, saved, missing, code, work if keep else None)
