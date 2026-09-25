import sys
from pathlib import Path

import pytest

from manga_viewer.llm.process import ManagedServer, ServerStartError, free_port

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
