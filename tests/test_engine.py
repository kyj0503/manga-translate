import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest

from manga_translate.download import Cancelled
from manga_translate.engine import (
    ENGINE_ARCHIVE_URL,
    ENGINE_COMMIT,
    MODEL_FILES,
    TORCH_INDEX,
    EngineError,
    EngineLayout,
    _decode_output,
    package_commands,
    run_checked,
    run_streaming,
    setup_engine,
    venv_command,
)

UV = Path("C:/tools/uv.exe")
PYTHON = getattr(sys, "_base_executable", sys.executable)


def fake_fetch(calls):
    """Records calls; for the engine archive writes a tiny source zip like GitHub's."""

    def fetch(url, dest, sha256=None, *, log=print, cancel=None):
        calls.append((url, dest, sha256))
        if url == ENGINE_ARCHIVE_URL:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest, "w") as zf:
                zf.writestr(f"BallonsTranslator-{ENGINE_COMMIT}/requirements.txt", "numpy\n")
                zf.writestr(f"BallonsTranslator-{ENGINE_COMMIT}/ballontranslator/__init__.py", "")

    return fetch


def make_ready(root: Path) -> EngineLayout:
    layout = EngineLayout(root)
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    return layout


def test_layout_paths(tmp_path):
    layout = EngineLayout(tmp_path)
    assert layout.python == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert layout.config_path == tmp_path / "config" / "config.json"
    assert layout.marker == tmp_path / ".manga-translate-setup"


def test_is_ready_needs_matching_marker_and_python(tmp_path):
    layout = EngineLayout(tmp_path)
    assert not layout.is_ready()
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    layout.marker.write_text("other", encoding="utf-8")
    assert not layout.is_ready()
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    assert layout.is_ready()


def test_commands(tmp_path):
    layout = EngineLayout(tmp_path)
    assert ENGINE_ARCHIVE_URL == f"https://github.com/dmMaze/BallonsTranslator/archive/{ENGINE_COMMIT}.zip"
    assert venv_command(layout, UV) == [str(UV), "venv", "--python", "3.12", str(tmp_path / ".venv")]
    packages = [" ".join(c) for c in package_commands(layout, UV)]
    assert any("-r " + str(tmp_path / "requirements.txt") in c for c in packages)
    assert any(f"-e {tmp_path} --no-deps" in c for c in packages)
    assert any("torch torchvision --index-url " + TORCH_INDEX in c for c in packages)


def test_model_files():
    assert len(MODEL_FILES) == 10
    big = [f for f in MODEL_FILES if not f.path.endswith((".json", ".md", ".txt"))]
    assert all(f.sha256 for f in big)


def test_fresh_setup(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    downloads = tmp_path / "downloads"
    ran, fetched = [], []

    setup_engine(layout, uv=UV, downloads_dir=downloads, run=ran.append, fetch=fake_fetch(fetched), log=lambda m: None)

    assert fetched[0][0] == ENGINE_ARCHIVE_URL
    assert (layout.root / "requirements.txt").read_text() == "numpy\n"
    assert (layout.root / "ballontranslator" / "__init__.py").exists()
    assert not fetched[0][1].exists()  # archive removed after extraction
    assert ran == [venv_command(layout, UV), *package_commands(layout, UV)]
    assert [f[1] for f in fetched[1:]] == [layout.root / m.path for m in MODEL_FILES]
    assert layout.marker.read_text(encoding="utf-8") == ENGINE_COMMIT


def test_ready_engine_only_verifies_models(tmp_path):
    layout = make_ready(tmp_path / "engine")
    ran, fetched = [], []
    setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=ran.append, fetch=fake_fetch(fetched), log=lambda m: None)
    assert ran == []
    assert len(fetched) == len(MODEL_FILES)


def test_existing_venv_is_kept(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    ran = []
    setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=ran.append, fetch=fake_fetch([]), log=lambda m: None)
    assert venv_command(layout, UV) not in ran


def test_corrupt_archive_is_reported_and_deleted(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    downloads = tmp_path / "downloads"

    def fetch(url, dest, sha256=None, *, log=print, cancel=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"not a zip file")

    with pytest.raises(EngineError, match="손상"):
        setup_engine(layout, uv=UV, downloads_dir=downloads, run=lambda a: None, fetch=fetch, log=lambda m: None)

    archive = downloads / f"BallonsTranslator-{ENGINE_COMMIT[:12]}.zip"
    assert not archive.exists()


def test_cancel_before_start(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    cancel = threading.Event()
    cancel.set()
    fetched = []
    with pytest.raises(Cancelled):
        setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=lambda a: None,
                     fetch=fake_fetch(fetched), log=lambda m: None, cancel=cancel)
    assert fetched == []
    assert not layout.marker.exists()


def test_cancel_during_model_verification(tmp_path):
    layout = make_ready(tmp_path / "engine")
    cancel = threading.Event()
    fetched = []

    def fetch(url, dest, sha256=None, *, log=print, cancel=None):
        fetched.append((url, dest, sha256))
        cancel.set()  # the user presses 중단 while the first model is verified

    with pytest.raises(Cancelled):
        setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=lambda a: None,
                     fetch=fetch, log=lambda m: None, cancel=cancel)
    assert len(fetched) == 1


def test_cancel_between_package_steps(tmp_path):
    layout = EngineLayout(tmp_path / "engine")
    cancel = threading.Event()
    ran = []

    def run(argv):
        ran.append(argv)
        cancel.set()  # the user presses 중단 while the first command runs

    with pytest.raises(Cancelled):
        setup_engine(layout, uv=UV, downloads_dir=tmp_path / "dl", run=run,
                     fetch=fake_fetch([]), log=lambda m: None, cancel=cancel)
    assert len(ran) == 1
    assert not layout.marker.exists()


def test_run_checked_success_and_failure_tail():
    run_checked([sys.executable, "-c", "print('fine')"])
    with pytest.raises(EngineError) as info:
        run_checked([sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"])
    assert "코드 3" in str(info.value) and "boom" in str(info.value)


def test_decode_output_handles_cp949_and_utf8(monkeypatch):
    monkeypatch.setattr("manga_translate.engine.locale.getpreferredencoding", lambda _: "cp949")
    assert _decode_output("한글 오류".encode("cp949")) == "한글 오류"
    assert _decode_output("utf8 문자".encode("utf-8")) == "utf8 문자"


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
