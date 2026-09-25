"""Drive one BallonsTranslator headless run: write its config, stage pages, run it, collect results."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
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


@dataclass(frozen=True)
class StagedPage:
    source: Path
    staged_name: str
    relative_dir: Path


def stage_pages(images: Sequence[Path], root: Path, exec_dir: Path) -> list[StagedPage]:
    """Copy images into one flat, numbered folder so the engine sees them in reading order.

    The engine writes project files next to the images, so it works on copies. Numbering
    the copies keeps the engine's filename order equal to our order, which keeps its
    page-to-page context in reading order. Numbering also keeps names unique when images
    from different subfolders share a name.
    """
    exec_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    for i, src in enumerate(images):
        staged_name = f"{i + 1:05d}_{src.name}"
        shutil.copy2(src, exec_dir / staged_name)
        staged.append(StagedPage(src, staged_name, src.parent.relative_to(root)))
    return staged


def collect_staged_results(
    exec_dir: Path, output_dir: Path, staged: Sequence[StagedPage]
) -> tuple[list[Path], list[Path]]:
    """Move staged results back to their mirrored place in ``output_dir``.

    Returns (saved output paths, missing source paths) for pages the engine did not
    write a result for.
    """
    result_dir = exec_dir / "result"
    result_by_stem = {}
    if result_dir.is_dir():
        for path in result_dir.iterdir():
            if path.is_file():
                result_by_stem[Path(path.name).stem] = path

    # A page collides with another when they'd land on the same output name: same
    # folder, same source stem, compared case-insensitively.
    dir_stem_counts: dict[tuple[Path, str], int] = {}
    for page in staged:
        key = (page.relative_dir, page.source.stem.lower())
        dir_stem_counts[key] = dir_stem_counts.get(key, 0) + 1

    saved = []
    missing = []
    for page in staged:
        result_file = result_by_stem.get(Path(page.staged_name).stem)
        if result_file is None:
            missing.append(page.source)
            continue
        target_dir = output_dir / page.relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        key = (page.relative_dir, page.source.stem.lower())
        if dir_stem_counts[key] > 1:
            output_name = f"{page.source.stem}_{page.source.suffix[1:].lower()}{result_file.suffix}"
        else:
            output_name = f"{page.source.stem}{result_file.suffix}"
        target = target_dir / output_name
        shutil.copy2(result_file, target)
        saved.append(target)
    return saved, missing


def run_streaming(
    argv: Sequence[str],
    cwd: Path,
    *,
    job: KillOnCloseJob | None = None,
    on_line: Callable[[str], None] = print,
    stdin_text: str = "exit\n",
) -> int:
    """Run a console program, feed stdin up front, forward its output line by line."""
    no_proxy = "127.0.0.1,localhost"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for key in ("NO_PROXY", "no_proxy"):
        existing = env.get(key)
        env[key] = f"{existing},{no_proxy}" if existing else no_proxy
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
