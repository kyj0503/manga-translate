"""The resident detection/OCR worker: a child process in the engine venv answering one JSON line per page."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import IO, Sequence

from .engine import EngineLayout
from .page import PageResult
from .winjob import KillOnCloseJob

WORKER_SCRIPT = Path(__file__).parent / "scripts" / "bt_worker.py"


class WorkerError(RuntimeError):
    pass


def worker_argv(engine: EngineLayout) -> list[str]:
    return [str(engine.python), str(WORKER_SCRIPT), str(engine.root)]


def _pump(stream: IO[bytes], lines: queue.Queue) -> None:
    for raw in stream:
        lines.put(raw.decode("utf-8", errors="replace"))
    lines.put(None)


class WorkerClient:
    def __init__(
        self,
        argv: Sequence[str],
        cwd: Path,
        log_path: Path,
        *,
        job: KillOnCloseJob | None = None,
        ready_timeout: float = 300.0,
        request_timeout: float = 120.0,
    ) -> None:
        self._argv = list(argv)
        self._cwd = cwd
        self._log_path = log_path
        self._job = job
        self._ready_timeout = ready_timeout
        self._request_timeout = request_timeout
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._lines: queue.Queue | None = None
        self._log: IO[bytes] | None = None
        self._next_id = 0

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            self._start()

    def stop(self) -> None:
        with self._lock:
            self._stop_process()

    def scan(self, image: Path) -> PageResult:
        with self._lock:
            if not self.running:
                self._start()  # the worker died since the last page: start it once more
            assert self._proc is not None and self._proc.stdin is not None
            self._next_id += 1
            request_id = self._next_id
            request = json.dumps({"id": request_id, "image": str(image)}, ensure_ascii=False) + "\n"
            try:
                self._proc.stdin.write(request.encode("utf-8"))
                self._proc.stdin.flush()
            except OSError as e:
                self._stop_process()
                raise WorkerError(f"번역 엔진이 종료되었습니다. 로그: {self._log_path}") from e
            while True:
                message = self._read(self._request_timeout)
                if message.get("id") == request_id:
                    break
        if "error" in message:
            raise WorkerError(str(message["error"]))
        try:
            return PageResult.from_json(message)
        except (KeyError, TypeError, ValueError) as e:
            raise WorkerError(f"번역 엔진 응답을 읽지 못했습니다: {e}") from e

    def _start(self) -> None:
        self._stop_process()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self._log_path.open("ab")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        try:
            self._proc = subprocess.Popen(
                self._argv,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if self._job is not None:
                self._job.assign(self._proc.pid)
        except (OSError, RuntimeError) as e:
            self._stop_process()
            raise WorkerError(f"번역 엔진을 시작하지 못했습니다: {e}") from e
        lines: queue.Queue = queue.Queue()
        self._lines = lines
        assert self._proc.stdout is not None
        threading.Thread(target=_pump, args=(self._proc.stdout, lines), daemon=True).start()
        message = self._read(self._ready_timeout)
        if not message.get("ready"):
            self._stop_process()
            raise WorkerError(f"번역 엔진이 준비되지 않았습니다. 로그: {self._log_path}")

    def _read(self, timeout: float) -> dict:
        assert self._lines is not None
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty:
                self._stop_process()
                raise WorkerError(f"번역 엔진이 응답하지 않습니다. 로그: {self._log_path}") from None
            if line is None:
                self._stop_process()
                raise WorkerError(f"번역 엔진이 종료되었습니다. 로그: {self._log_path}")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict):
                return message

    def _stop_process(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        if self._log is not None:
            self._log.close()
            self._log = None
