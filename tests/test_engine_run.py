import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from manga_translate.engine import EngineLayout
from manga_translate.engine_run import (
    CONFIG_SCRIPT,
    StagedPage,
    collect_staged_results,
    headless_argv,
    run_streaming,
    stage_pages,
    write_engine_config,
)

FAKE_BT = Path(__file__).parent / "helpers" / "fake_bt"
PYTHON = getattr(sys, "_base_executable", sys.executable)


def test_write_engine_config_runs_script_with_engine_python(tmp_path):
    layout = EngineLayout(tmp_path)
    ran = []
    write_engine_config(layout, "http://127.0.0.1:5555", "gemma-4-e4b", run=ran.append)
    assert ran == [[str(layout.python), str(CONFIG_SCRIPT), str(tmp_path), "http://127.0.0.1:5555", "gemma-4-e4b"]]


def test_config_script_writes_text_only_local_llm_config(tmp_path):
    root = tmp_path / "engine"
    shutil.copytree(FAKE_BT, root)
    result = subprocess.run(
        [sys.executable, str(CONFIG_SCRIPT), str(root), "http://127.0.0.1:5555", "gemma-4-e4b"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((root / "config" / "config.json").read_text(encoding="utf-8"))
    module = data["module"]
    assert module["textdetector"] == "ctd"
    assert module["ocr"] == "manga_ocr"
    assert module["inpainter"] == "lama_large_512px"
    assert module["translator"] == "LLMTranslator"
    assert module["translate_source"] == "日本語"
    assert module["translate_target"] == "한국어"
    assert module["llm_translate_context"] == "history"
    assert module["llm_translate_vision"] is False
    [profile] = module["llm_profiles"]
    assert module["translator_llm_id"] == profile["id"]
    assert profile["base_url"] == "http://127.0.0.1:5555/v1"
    assert profile["model"] == "gemma-4-e4b"
    assert profile["support_vision"] is False
    assert profile["thinking_level"] == "Disabled"
    assert data["font_family"] == "Malgun Gothic"


def test_headless_argv(tmp_path):
    layout = EngineLayout(tmp_path)
    assert headless_argv(layout, tmp_path / "pages") == [
        str(layout.python), "-m", "ballontranslator", "--headless", "--exec_dirs", str(tmp_path / "pages"),
    ]


def test_stage_pages_top_level_relative_dir_is_dot(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    images = []
    for name in ("1.jpg", "2.png"):
        (src / name).write_bytes(name.encode())
        images.append(src / name)
    exec_dir = tmp_path / "work" / "pages"

    staged = stage_pages(images, src, exec_dir)

    assert staged == [
        StagedPage(src / "1.jpg", "00001_1.jpg", Path(".")),
        StagedPage(src / "2.png", "00002_2.png", Path(".")),
    ]
    assert (exec_dir / "00001_1.jpg").read_bytes() == b"1.jpg"
    assert (exec_dir / "00002_2.png").read_bytes() == b"2.png"


def test_collect_staged_results_top_level(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    images = [src / "1.jpg", src / "2.png"]
    for image in images:
        image.write_bytes(b"img")
    exec_dir = tmp_path / "work" / "pages"
    staged = stage_pages(images, src, exec_dir)

    assert collect_staged_results(exec_dir, tmp_path / "out", staged) == ([], [src / "1.jpg", src / "2.png"])

    (exec_dir / "result").mkdir()
    (exec_dir / "result" / "00001_1.png").write_bytes(b"typeset")
    saved, missing = collect_staged_results(exec_dir, tmp_path / "out", staged)

    assert saved == [tmp_path / "out" / "1.png"]
    assert (tmp_path / "out" / "1.png").read_bytes() == b"typeset"
    assert missing == [src / "2.png"]


def test_stage_pages_avoids_name_collisions_across_subfolders(tmp_path):
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "b").mkdir(parents=True)
    (src / "a" / "001.webp").write_bytes(b"a")
    (src / "b" / "001.webp").write_bytes(b"b")
    images = [src / "a" / "001.webp", src / "b" / "001.webp"]
    exec_dir = tmp_path / "work" / "pages"

    staged = stage_pages(images, src, exec_dir)

    assert staged == [
        StagedPage(src / "a" / "001.webp", "00001_001.webp", Path("a")),
        StagedPage(src / "b" / "001.webp", "00002_001.webp", Path("b")),
    ]
    assert (exec_dir / "00001_001.webp").read_bytes() == b"a"
    assert (exec_dir / "00002_001.webp").read_bytes() == b"b"

    (exec_dir / "result").mkdir()
    (exec_dir / "result" / "00001_001.png").write_bytes(b"a-out")
    (exec_dir / "result" / "00002_001.png").write_bytes(b"b-out")

    saved, missing = collect_staged_results(exec_dir, tmp_path / "out", staged)

    assert missing == []
    assert saved == [tmp_path / "out" / "a" / "001.png", tmp_path / "out" / "b" / "001.png"]
    assert (tmp_path / "out" / "a" / "001.png").read_bytes() == b"a-out"
    assert (tmp_path / "out" / "b" / "001.png").read_bytes() == b"b-out"


def test_collect_staged_results_same_stem_different_extension_does_not_collide(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "001.jpg").write_bytes(b"jpg")
    (src / "001.png").write_bytes(b"png")
    images = [src / "001.jpg", src / "001.png"]
    exec_dir = tmp_path / "work" / "pages"

    staged = stage_pages(images, src, exec_dir)
    (exec_dir / "result").mkdir()
    (exec_dir / "result" / "00001_001.png").write_bytes(b"jpg-out")
    (exec_dir / "result" / "00002_001.png").write_bytes(b"png-out")

    saved, missing = collect_staged_results(exec_dir, tmp_path / "out", staged)

    assert missing == []
    assert saved == [tmp_path / "out" / "001_jpg.png", tmp_path / "out" / "001_png.png"]
    assert (tmp_path / "out" / "001_jpg.png").read_bytes() == b"jpg-out"
    assert (tmp_path / "out" / "001_png.png").read_bytes() == b"png-out"


def test_collect_staged_results_dotted_name_round_trips(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "vol.1.webp").write_bytes(b"img")
    images = [src / "vol.1.webp"]
    exec_dir = tmp_path / "work" / "pages"

    staged = stage_pages(images, src, exec_dir)
    (exec_dir / "result").mkdir()
    (exec_dir / "result" / "00001_vol.1.png").write_bytes(b"typeset")

    saved, missing = collect_staged_results(exec_dir, tmp_path / "out", staged)

    assert missing == []
    assert saved == [tmp_path / "out" / "vol.1.png"]
    assert (tmp_path / "out" / "vol.1.png").read_bytes() == b"typeset"


def test_run_streaming_passes_output_stdin_and_cwd(tmp_path):
    lines = []
    code = run_streaming(
        [PYTHON, "-c", "import os; print('한글 출력'); print(os.getcwd()); print('got', input())"],
        tmp_path,
        on_line=lines.append,
    )
    assert code == 0
    assert lines == ["한글 출력", str(tmp_path), "got exit"]


def test_run_streaming_returns_exit_code(tmp_path):
    assert run_streaming([PYTHON, "-c", "import sys; sys.exit(9)"], tmp_path, on_line=lambda l: None) == 9


def test_run_streaming_sets_no_proxy(tmp_path):
    lines = []
    run_streaming(
        [PYTHON, "-c", "import os; print(os.environ['NO_PROXY'])"],
        tmp_path,
        on_line=lines.append,
    )
    assert "127.0.0.1" in lines[0]
    assert "localhost" in lines[0]


def test_run_streaming_kills_process_when_consumer_fails(tmp_path):
    def boom(line):
        raise RuntimeError("stop")

    start = time.monotonic()
    with pytest.raises(RuntimeError, match="stop"):
        run_streaming([PYTHON, "-c", "import time; print('x', flush=True); time.sleep(60)"], tmp_path, on_line=boom)
    assert time.monotonic() - start < 20
