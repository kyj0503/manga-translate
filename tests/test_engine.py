import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from manga_translate.engine import (
    ENGINE_COMMIT,
    ENGINE_REPO,
    MODEL_FILES,
    TORCH_INDEX,
    EngineError,
    EngineLayout,
    download_file,
    package_commands,
    repo_commands,
    setup_engine,
    venv_command,
)

UV = Path("C:/tools/uv.exe")
GIT = Path("C:/tools/git.exe")


def make_ready(root: Path) -> EngineLayout:
    layout = EngineLayout(root)
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    (root / ".git").mkdir()
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
    assert not layout.is_ready()
    layout.marker.write_text("some-other-commit", encoding="utf-8")
    assert not layout.is_ready()
    layout.marker.write_text(ENGINE_COMMIT, encoding="utf-8")
    assert layout.is_ready()


def test_commands(tmp_path):
    layout = EngineLayout(tmp_path)
    repo = repo_commands(layout, GIT)
    assert repo[0] == [str(GIT), "-C", str(tmp_path), "fetch", "--depth", "1", ENGINE_REPO, ENGINE_COMMIT]
    assert repo[1] == [str(GIT), "-C", str(tmp_path), "checkout", "--force", ENGINE_COMMIT]
    assert venv_command(layout, UV) == [str(UV), "venv", "--python", "3.12", str(tmp_path / ".venv")]
    packages = [" ".join(c) for c in package_commands(layout, UV)]
    assert any("-r " + str(tmp_path / "requirements.txt") in c for c in packages)
    assert any(f"-e {tmp_path} --no-deps" in c for c in packages)
    assert any("torch torchvision --index-url " + TORCH_INDEX in c for c in packages)
    assert any("transformers==4.57.6" in c for c in packages)
    assert all(f"--python {layout.python}" in c for c in packages)


def test_model_files():
    paths = {f.path for f in MODEL_FILES}
    assert len(MODEL_FILES) == 10
    assert {
        "data/models/comictextdetector.pt",
        "data/models/comictextdetector.pt.onnx",
        "data/models/lama_large_512px.ckpt",
        "data/models/manga-ocr-base/pytorch_model.bin",
    } <= paths
    big = [f for f in MODEL_FILES if not f.path.endswith((".json", ".md", ".txt"))]
    assert all(f.sha256 for f in big)


def test_fresh_setup_runs_everything_and_writes_marker(tmp_path):
    root = tmp_path / "engine"
    layout = EngineLayout(root)
    ran, downloaded = [], []

    setup_engine(
        layout,
        uv=UV,
        git=GIT,
        run=lambda argv: ran.append(list(argv)),
        download=lambda url, dest, sha256, log: downloaded.append(dest),
        log=lambda msg: None,
    )

    assert ran[0] == [str(GIT), "init", str(root)]
    assert ran[1:3] == repo_commands(layout, GIT)
    assert ran[3] == venv_command(layout, UV)
    assert ran[4:] == package_commands(layout, UV)
    assert downloaded == [root / f.path for f in MODEL_FILES]
    assert layout.marker.read_text(encoding="utf-8") == ENGINE_COMMIT


def test_ready_engine_only_verifies_models(tmp_path):
    layout = make_ready(tmp_path / "engine")
    ran, downloaded = [], []
    setup_engine(
        layout,
        uv=UV,
        git=GIT,
        run=lambda argv: ran.append(argv),
        download=lambda url, dest, sha256, log: downloaded.append(dest),
        log=lambda msg: None,
    )
    assert ran == []
    assert len(downloaded) == len(MODEL_FILES)


def test_existing_venv_is_not_recreated(tmp_path):
    root = tmp_path / "engine"
    layout = EngineLayout(root)
    (root / ".git").mkdir(parents=True)
    layout.python.parent.mkdir(parents=True)
    layout.python.write_bytes(b"")
    ran = []
    setup_engine(layout, uv=UV, git=GIT, run=ran.append, download=lambda *a: None, log=lambda m: None)
    assert venv_command(layout, UV) not in ran
    assert ran[:2] == repo_commands(layout, GIT)


def test_interrupted_clone_recovers(tmp_path):
    root = tmp_path / "engine"
    layout = EngineLayout(root)
    (root / ".git").mkdir(parents=True)
    ran = []
    setup_engine(layout, uv=UV, git=GIT, run=ran.append, download=lambda *a: None, log=lambda m: None)
    assert ran[:2] == repo_commands(layout, GIT)
    assert not any("remote" in " ".join(argv) for argv in ran)
    assert layout.marker.read_text(encoding="utf-8") == ENGINE_COMMIT


@pytest.fixture
def http_server():
    files, hits = {}, []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = files.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", files, hits
    server.shutdown()


def test_download_verifies_checksum(tmp_path, http_server):
    base, files, _ = http_server
    files["/m.bin"] = b"model-bytes"
    dest = tmp_path / "models" / "m.bin"
    download_file(base + "/m.bin", dest, hashlib.sha256(b"model-bytes").hexdigest(), log=lambda m: None)
    assert dest.read_bytes() == b"model-bytes"
    assert not dest.with_name("m.bin.part").exists()


def test_download_rejects_bad_checksum(tmp_path, http_server):
    base, files, _ = http_server
    files["/m.bin"] = b"tampered"
    dest = tmp_path / "m.bin"
    with pytest.raises(EngineError, match="검증"):
        download_file(base + "/m.bin", dest, hashlib.sha256(b"expected").hexdigest(), log=lambda m: None)
    assert not dest.exists()
    assert not dest.with_name("m.bin.part").exists()


def test_download_skips_valid_existing_file(tmp_path, http_server):
    base, files, hits = http_server
    dest = tmp_path / "m.bin"
    dest.write_bytes(b"model-bytes")
    download_file(base + "/m.bin", dest, hashlib.sha256(b"model-bytes").hexdigest(), log=lambda m: None)
    assert hits == []


def test_download_http_error_is_engine_error(tmp_path, http_server):
    base, _, _ = http_server
    with pytest.raises(EngineError, match="다운로드"):
        download_file(base + "/missing", tmp_path / "x.bin", None, log=lambda m: None)


def test_download_logs_progress(tmp_path, http_server, monkeypatch):
    import manga_translate.engine as engine_module

    monkeypatch.setattr(engine_module, "PROGRESS_EVERY", 1024)
    base, files, _ = http_server
    body = b"x" * (3 * 1024)
    files["/big.bin"] = body
    dest = tmp_path / "big.bin"
    messages = []
    download_file(base + "/big.bin", dest, None, log=messages.append)
    assert dest.read_bytes() == body
    progress_lines = [m for m in messages if "MB" in m]
    assert len(progress_lines) >= 2


def test_run_checked_success_and_failure_tail():
    import sys

    from manga_translate.engine import run_checked

    run_checked([sys.executable, "-c", "print('fine')"])
    with pytest.raises(EngineError) as info:
        run_checked([sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"])
    assert "코드 3" in str(info.value)
    assert "boom" in str(info.value)


def test_decode_output_handles_cp949_and_utf8(monkeypatch):
    from manga_translate.engine import _decode_output

    monkeypatch.setattr("manga_translate.engine.locale.getpreferredencoding", lambda _: "cp949")

    # Test cp949 encoding fallback
    cp949_text = "한글 오류".encode("cp949")
    assert _decode_output(cp949_text) == "한글 오류"

    # Test UTF-8 encoding (should work without fallback)
    utf8_text = "utf8 문자".encode("utf-8")
    assert _decode_output(utf8_text) == "utf8 문자"
