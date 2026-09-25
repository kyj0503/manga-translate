import sys
from pathlib import Path

import pytest

from manga_translate.llm.process import ManagedServer, ServerStartError, free_port

HELPER = Path(__file__).parent / "helpers" / "fake_health_server.py"
# The real interpreter, not the venv launcher: terminating a launcher can orphan its child.
PYTHON = getattr(sys, "_base_executable", sys.executable)


def fake_server(tmp_path, ready_after):
    port = free_port()
    return ManagedServer(
        [PYTHON, str(HELPER), str(port), str(ready_after)],
        health_url=f"http://127.0.0.1:{port}/health",
        log_path=tmp_path / "server.log",
    )


def test_start_waits_until_healthy_then_stop(tmp_path):
    server = fake_server(tmp_path, ready_after=0.5)
    server.start(timeout=15)
    try:
        assert server.running
        assert server.is_healthy()
    finally:
        server.stop()
    assert not server.running


def test_process_that_exits_reports_log_tail(tmp_path):
    server = ManagedServer(
        [PYTHON, "-c", "import sys; print('boom', flush=True); sys.exit(3)"],
        health_url=f"http://127.0.0.1:{free_port()}/health",
        log_path=tmp_path / "server.log",
    )
    with pytest.raises(ServerStartError, match="boom"):
        server.start(timeout=15)


def test_timeout_stops_process(tmp_path):
    server = fake_server(tmp_path, ready_after=100)
    with pytest.raises(ServerStartError, match="시간"):
        server.start(timeout=1.5)
    assert not server.running


def test_missing_executable_closes_log_and_leaves_no_process(tmp_path):
    log_path = tmp_path / "server.log"
    server = ManagedServer(
        [str(tmp_path / "does-not-exist.exe")],
        health_url=f"http://127.0.0.1:{free_port()}/health",
        log_path=log_path,
    )
    with pytest.raises(FileNotFoundError):
        server.start(timeout=5)
    assert not server.running
    # The log handle must have been closed, or deleting/reopening it would fail on Windows.
    log_path.unlink()
    log_path.write_bytes(b"")


def test_job_assign_failure_kills_process_and_closes_log(tmp_path):
    class FailingJob:
        def assign(self, pid):
            raise OSError("boom")

    log_path = tmp_path / "server.log"
    server = ManagedServer(
        [PYTHON, "-c", "import time; time.sleep(120)"],
        health_url=f"http://127.0.0.1:{free_port()}/health",
        log_path=log_path,
        job=FailingJob(),
    )
    with pytest.raises(OSError, match="boom"):
        server.start(timeout=5)
    assert not server.running
    log_path.unlink()
    log_path.write_bytes(b"")


def test_health_check_ignores_proxy_environment(tmp_path, monkeypatch):
    # A dead proxy: if httpx honoured it, /health would never succeed.
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    server = fake_server(tmp_path, ready_after=0.2)
    server.start(timeout=10)
    try:
        assert server.is_healthy()
    finally:
        server.stop()
