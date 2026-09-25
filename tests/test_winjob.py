import os
import subprocess
import sys
import threading
from pathlib import Path

import psutil
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

ROOT = Path(__file__).resolve().parents[1]
PYTHON = getattr(sys, "_base_executable", sys.executable)


def test_close_kills_assigned_process():
    from manga_translate.winjob import KillOnCloseJob

    job = KillOnCloseJob()
    child = subprocess.Popen([PYTHON, "-c", "import time; time.sleep(120)"])
    job.assign(child.pid)
    job.close()
    child.wait(timeout=10)


def test_close_is_safe_from_two_threads_and_twice_sequentially():
    from manga_translate.winjob import KillOnCloseJob

    job = KillOnCloseJob()
    errors = []

    def close():
        try:
            job.close()
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    t1 = threading.Thread(target=close)
    t2 = threading.Thread(target=close)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not errors

    job2 = KillOnCloseJob()
    job2.close()
    job2.close()  # must not raise


def test_child_dies_when_owner_is_killed():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    parent = subprocess.Popen(
        [PYTHON, str(ROOT / "tests" / "helpers" / "job_parent.py")],
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    child = psutil.Process(int(parent.stdout.readline()))
    assert child.is_running()

    parent.kill()
    parent.wait(timeout=10)
    child.wait(timeout=10)  # raises psutil.TimeoutExpired if the child survived
