import json
import sys
from pathlib import Path

import pytest

from manga_translate.engine import EngineLayout
from manga_translate.page import Block, PageResult
from manga_translate.winjob import KillOnCloseJob
from manga_translate.worker_client import WORKER_SCRIPT, WorkerClient, WorkerError, worker_argv

FAKE_BT = Path(__file__).parent / "helpers" / "fake_bt"
PYTHON = getattr(sys, "_base_executable", sys.executable)


def fake_image(tmp_path: Path, name: str, spec: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def client(tmp_path):
    worker = WorkerClient(
        [PYTHON, str(WORKER_SCRIPT), str(FAKE_BT)], FAKE_BT, tmp_path / "logs" / "worker.log", ready_timeout=30, request_timeout=30
    )
    worker.start()
    yield worker
    worker.stop()


PAGE_SPEC = {
    "size": [964, 1200],
    "blocks": [
        {"xyxy": [10, 20, 30, 40], "vertical": True, "text": "こんにちは"},
        {"xyxy": [50, 60, 70, 80], "vertical": False, "text": "えっ"},
    ],
}


def test_worker_argv(tmp_path):
    engine = EngineLayout(tmp_path / "engine")
    assert worker_argv(engine) == [str(engine.python), str(WORKER_SCRIPT), str(engine.root)]


def test_scan_returns_blocks_and_ignores_engine_prints(client, tmp_path):
    image = fake_image(tmp_path, "페그오 001.json", PAGE_SPEC)
    assert client.scan(image) == PageResult(
        (964, 1200),
        (Block((10, 20, 30, 40), True, "こんにちは"), Block((50, 60, 70, 80), False, "えっ")),
    )
    assert "Device name: fake GPU" in (tmp_path / "logs" / "worker.log").read_text(encoding="utf-8")


def test_page_error_is_reported_and_worker_keeps_running(client, tmp_path):
    with pytest.raises(WorkerError, match="detector exploded"):
        client.scan(fake_image(tmp_path, "bad.json", {"fail": "detector exploded"}))
    assert client.running
    assert client.scan(fake_image(tmp_path, "ok.json", PAGE_SPEC)).size == (964, 1200)


def test_unreadable_image_is_an_error(client, tmp_path):
    with pytest.raises(WorkerError, match="이미지를 읽을 수 없습니다"):
        client.scan(tmp_path / "없는 파일.png")


def test_crashed_worker_restarts_on_next_scan(client, tmp_path):
    with pytest.raises(WorkerError, match="종료"):
        client.scan(fake_image(tmp_path, "crash.json", {"crash": True}))
    assert not client.running
    assert client.scan(fake_image(tmp_path, "ok.json", PAGE_SPEC)).blocks[0].text == "こんにちは"
    assert client.running


def test_stop_ends_the_process(client):
    client.stop()
    assert not client.running


def test_closing_the_job_ends_the_worker(tmp_path):
    job = KillOnCloseJob()
    worker = WorkerClient(
        [PYTHON, str(WORKER_SCRIPT), str(FAKE_BT)], FAKE_BT, tmp_path / "worker.log", job=job, ready_timeout=30
    )
    worker.start()
    try:
        job.close()
        with pytest.raises(WorkerError):
            worker.scan(fake_image(tmp_path, "ok.json", PAGE_SPEC))
    finally:
        worker.stop()
