"""One translation job for the GUI: validate, run llama-server + engine, report progress, collect results."""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .engine import EngineLayout
from .engine_run import (
    collect_results,
    headless_argv,
    missing_pages,
    prepare_work_dir,
    run_streaming,
    write_engine_config,
)
from .llm.llama import LlamaConfig, start_llama_server
from .llm.process import ServerStartError
from .source import list_images
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


@dataclass(frozen=True)
class TranslationResult:
    total: int
    saved: list[Path]
    missing: list[Path]
    engine_exit_code: int
    work_dir: Path | None  # kept for inspection, or None when cleaned up

    @property
    def ok(self) -> bool:
        return not self.missing


def validate(req: TranslationRequest) -> list[Path]:
    if not req.input_dir.is_dir():
        raise PipelineError(f"폴더가 없습니다: {req.input_dir}")
    images = list_images(req.input_dir)
    if not images:
        raise PipelineError(f"이미지가 없습니다: {req.input_dir}")
    for label, path in (("llama-server", req.llama_server), ("모델", req.model)):
        if not path.is_file():
            raise PipelineError(f"{label} 파일이 없습니다: {path}")
    if not req.engine.is_ready():
        raise PipelineError("번역 엔진이 설치되어 있지 않습니다. '엔진 설치' 버튼을 먼저 눌러 주세요.")
    if req.output_dir.resolve() == req.input_dir.resolve():
        raise PipelineError("출력 폴더는 입력 폴더와 달라야 합니다.")
    return images


@contextmanager
def _llama_server(req: TranslationRequest, log_path: Path, on_log: Callable[[str], None]) -> Iterator[tuple[KillOnCloseJob, str]]:
    """llama-server in a kill-on-close job; the engine joins the same job. Always torn down."""
    job = KillOnCloseJob()
    server = None
    try:
        on_log("LLM 서버를 시작하는 중...")
        try:
            server, base_url = start_llama_server(
                LlamaConfig(exe=req.llama_server, model=req.model, ctx_size=req.ctx_size), log_path, job=job
            )
        except (ServerStartError, OSError) as e:
            raise PipelineError(f"LLM 서버를 시작하지 못했습니다: {e}") from e
        yield job, base_url
    finally:
        if server is not None:
            server.stop()
        job.close()


def run_translation(
    req: TranslationRequest,
    *,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
) -> TranslationResult:
    images = validate(req)
    total = len(images)
    work = Path(tempfile.mkdtemp(prefix="manga-viewer-"))
    exec_dir = work / "pages"
    result_dir = exec_dir / "result"
    prepare_work_dir(images, exec_dir)

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
    code = None
    try:
        with _llama_server(req, work / "llama-server.log", on_log) as (job, base_url):
            on_log("번역 설정을 쓰는 중...")
            write_engine_config(req.engine, base_url, req.model.stem)
            on_log(f"번역을 시작합니다 ({total}장)...")
            code = run_streaming(headless_argv(req.engine, exec_dir), req.engine.root, job=job, on_line=forward)
    except Exception:
        on_log(f"작업 폴더: {work}")
        raise

    saved = collect_results(exec_dir, req.output_dir)
    missing = missing_pages(images, saved)
    report(total - len(missing))
    keep = bool(missing) or req.keep_work
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return TranslationResult(total, saved, missing, code, work if keep else None)
