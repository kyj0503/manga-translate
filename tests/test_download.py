import hashlib
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import manga_translate.download as dl
from manga_translate.download import Cancelled, InstallError, download, extract_zip

BODY = bytes(range(256)) * 20  # 5120 bytes
SHA = hashlib.sha256(BODY).hexdigest()


@pytest.fixture
def server():
    files, hits, state = {"/f.bin": BODY}, [], {"ignore_range": False, "range_from_zero": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            rng = self.headers.get("Range")
            hits.append((self.path, rng))
            if self.path == "/short":
                self.send_response(200)
                self.send_header("Content-Length", "5120")
                self.end_headers()
                self.wfile.write(BODY[:1000])
                self.close_connection = True
                return
            body = files.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            if rng and not state["ignore_range"]:
                if state["range_from_zero"]:
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes 0-{len(body) - 1}/{len(body)}")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                start = int(rng.split("=")[1].split("-")[0])
                if start >= len(body):
                    self.send_response(416)
                    self.end_headers()
                    return
                chunk = body[start:]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits, state
    srv.shutdown()


def quiet(msg):
    pass


def test_fresh_download_is_verified(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "d" / "f.bin"
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY
    assert not dest.with_name("f.bin.part").exists()


def test_resumes_from_part(tmp_path, server):
    base, hits, _ = server
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(BODY[:1000])
    logs = []
    download(base + "/f.bin", dest, SHA, log=logs.append)
    assert dest.read_bytes() == BODY
    assert hits[-1][1] == "bytes=1000-"
    assert any("이어받기" in line for line in logs)


def test_server_ignoring_range_restarts(tmp_path, server):
    base, _, state = server
    state["ignore_range"] = True
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(b"garbage")
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY


def test_complete_part_is_accepted(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(BODY)
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY


def test_bad_checksum(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    with pytest.raises(InstallError, match="검증"):
        download(base + "/f.bin", dest, "0" * 64, log=quiet)
    assert not dest.exists()
    assert not dest.with_name("f.bin.part").exists()


def test_valid_existing_file_is_skipped(tmp_path, server):
    base, hits, _ = server
    dest = tmp_path / "f.bin"
    dest.write_bytes(BODY)
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert hits == []


def test_http_error(tmp_path, server):
    base, _, _ = server
    with pytest.raises(InstallError, match="다운로드"):
        download(base + "/missing", tmp_path / "x.bin", None, log=quiet)


def test_cancel_keeps_part(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    cancel = threading.Event()
    with pytest.raises(Cancelled):
        download(base + "/f.bin", dest, SHA, log=lambda m: cancel.set(), cancel=cancel)
    assert not dest.exists()
    assert dest.with_name("f.bin.part").exists()


def test_progress_is_logged(tmp_path, server, monkeypatch):
    base, _, _ = server
    monkeypatch.setattr(dl, "PROGRESS_EVERY", 1024)
    monkeypatch.setattr(dl, "CHUNK", 512)
    logs = []
    download(base + "/f.bin", tmp_path / "f.bin", SHA, log=logs.append)
    assert sum("MB" in line or "KB" in line for line in logs) >= 2


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_extract_strips_top_folder(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"top/a.txt": "A", "top/sub/b.txt": "B"})
    extract_zip(archive, tmp_path / "out", strip_top=True)
    assert (tmp_path / "out" / "a.txt").read_text() == "A"
    assert (tmp_path / "out" / "sub" / "b.txt").read_text() == "B"


def test_extract_flat(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"llama-server.exe": "exe"})
    extract_zip(archive, tmp_path / "out")
    assert (tmp_path / "out" / "llama-server.exe").read_text() == "exe"


def test_extract_rejects_traversal(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"../evil.txt": "x"})
    with pytest.raises(InstallError, match="경로"):
        extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_extract_cancel(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"a.txt": "A"})
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        extract_zip(archive, tmp_path / "out", cancel=cancel)


def test_truncated_transfer_is_rejected(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    with pytest.raises(InstallError, match="끊겼"):
        download(base + "/short", dest, None, log=quiet)
    assert not dest.exists()
    part = dest.with_name("f.bin.part")
    assert part.exists()
    assert part.stat().st_size == 1000


def test_resume_gets_full_body_instead_of_206(tmp_path, server):
    base, _, state = server
    state["range_from_zero"] = True
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(b"garbage")
    download(base + "/f.bin", dest, SHA, log=quiet)
    assert dest.read_bytes() == BODY


def test_rename_failure_is_reported(tmp_path, server):
    base, _, _ = server
    dest = tmp_path / "f.bin"
    dest.mkdir()
    with pytest.raises(InstallError, match="저장하지 못했습니다"):
        download(base + "/f.bin", dest, SHA, log=quiet)
