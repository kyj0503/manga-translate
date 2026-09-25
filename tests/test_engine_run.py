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
    collect_results,
    headless_argv,
    missing_pages,
    prepare_work_dir,
    run_streaming,
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


def test_prepare_collect_and_missing(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    images = []
    for name in ("1.jpg", "2.png"):
        (src / name).write_bytes(name.encode())
        images.append(src / name)
    exec_dir = tmp_path / "work" / "pages"

    prepare_work_dir(images, exec_dir)
    assert (exec_dir / "1.jpg").read_bytes() == b"1.jpg"

    assert collect_results(exec_dir, tmp_path / "out") == []
    (exec_dir / "result").mkdir()
    (exec_dir / "result" / "1.png").write_bytes(b"typeset")
    results = collect_results(exec_dir, tmp_path / "out")
    assert results == [tmp_path / "out" / "1.png"]
    assert (tmp_path / "out" / "1.png").read_bytes() == b"typeset"
    assert missing_pages(images, results) == [src / "2.png"]


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
