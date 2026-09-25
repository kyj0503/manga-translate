from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import IO

import httpx

from ..winjob import KillOnCloseJob

_LOG_TAIL_BYTES = 2000


class ServerStartError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ManagedServer:
    """A child process that serves HTTP and is ready once ``health_url`` returns 200."""

    def __init__(
        self,
        argv: list[str],
        health_url: str,
        log_path: Path,
        job: KillOnCloseJob | None = None,
    ) -> None:
        self._argv = argv
        self._health_url = health_url
        self._log_path = log_path
        self._job = job
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, timeout: float = 180.0, poll_interval: float = 0.25) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self._log_path.open("ab")
        self._proc = subprocess.Popen(
            self._argv,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if self._job is not None:
            self._job.assign(self._proc.pid)

        deadline = time.monotonic() + timeout
        while True:
            code = self._proc.poll()
            if code is not None:
                self._close_log()
                raise ServerStartError(f"서버가 종료되었습니다 (코드 {code}):\n{self._log_tail()}")
            if self.is_healthy():
                return
            if time.monotonic() > deadline:
                self.stop()
                raise ServerStartError(f"서버 준비 대기 시간을 초과했습니다 ({timeout}s):\n{self._log_tail()}")
            time.sleep(poll_interval)

    def is_healthy(self) -> bool:
        try:
            return httpx.get(self._health_url, timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def stop(self, timeout: float = 10.0) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout)
        self._close_log()

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None

    def _log_tail(self) -> str:
        try:
            data = self._log_path.read_bytes()[-_LOG_TAIL_BYTES:]
        except OSError:
            return ""
        return data.decode("utf-8", errors="replace")
