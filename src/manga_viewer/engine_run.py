"""Drive one BallonsTranslator headless run: write its config, stage pages, run it, collect results."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .engine import EngineLayout, run_checked
from .winjob import KillOnCloseJob

CONFIG_SCRIPT = Path(__file__).parent / "scripts" / "bt_write_config.py"


def write_engine_config(
    layout: EngineLayout,
    base_url: str,
    model_id: str,
    run: Callable[[Sequence[str]], None] = run_checked,
) -> None:
    run([str(layout.python), str(CONFIG_SCRIPT), str(layout.root), base_url, model_id])


def headless_argv(layout: EngineLayout, exec_dir: Path) -> list[str]:
    return [str(layout.python), "-m", "ballontranslator", "--headless", "--exec_dirs", str(exec_dir)]


def prepare_work_dir(images: Sequence[Path], exec_dir: Path) -> None:
    """The engine writes project files next to the images, so it works on copies."""
    exec_dir.mkdir(parents=True, exist_ok=True)
    for image in images:
        shutil.copy2(image, exec_dir / image.name)


def collect_results(exec_dir: Path, output_dir: Path) -> list[Path]:
    result_dir = exec_dir / "result"
    if not result_dir.is_dir():
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(result_dir.iterdir()):
        if path.is_file():
            target = output_dir / path.name
            shutil.copy2(path, target)
            copied.append(target)
    return copied


def missing_pages(images: Sequence[Path], results: Sequence[Path]) -> list[Path]:
    produced = {p.stem for p in results}
    return [p for p in images if p.stem not in produced]


def run_streaming(
    argv: Sequence[str],
    cwd: Path,
    *,
    job: KillOnCloseJob | None = None,
    on_line: Callable[[str], None] = print,
    stdin_text: str = "exit\n",
) -> int:
    """Run a console program, feed stdin up front, forward its output line by line."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        if job is not None:
            job.assign(proc.pid)
        assert proc.stdin is not None and proc.stdout is not None
        try:
            # Headless mode asks for more folders when done; a queued "exit" makes it quit.
            proc.stdin.write(stdin_text.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass  # the program already exited; its output and exit code still tell the story
        for raw in proc.stdout:
            on_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        return proc.wait()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
