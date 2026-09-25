import sys
import types

from manga_translate.app import WEB_DIR, WindowDialogs, reset_logs
from manga_translate.server import TOKEN_PLACEHOLDER


def test_web_files_are_packaged_and_carry_the_token():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert f"/static/app.js?token={TOKEN_PLACEHOLDER}" in html
    assert f"/static/style.css?token={TOKEN_PLACEHOLDER}" in html
    assert (WEB_DIR / "app.js").is_file()
    assert (WEB_DIR / "style.css").is_file()
    for element_id in ("setup", "library", "reader", "page-image", "overlay", "components", "books"):
        assert f'id="{element_id}"' in html


def test_reset_logs_removes_last_run_logs(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    for name in ("app.log", "worker.log", "llama-server.log"):
        (logs / name).write_text("old", encoding="utf-8")
    (logs / "keep.txt").write_text("x", encoding="utf-8")
    reset_logs(logs)
    assert sorted(p.name for p in logs.iterdir()) == ["keep.txt"]
    reset_logs(tmp_path / "new-logs")
    assert (tmp_path / "new-logs").is_dir()


class FakeWindow:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create_file_dialog(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        return self.result


def test_window_dialogs(monkeypatch):
    fake = types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER="folder", OPEN="open"))
    monkeypatch.setitem(sys.modules, "webview", fake)
    dialogs = WindowDialogs()
    dialogs.window = FakeWindow(("C:/만화",))
    assert dialogs.pick_folder() == "C:/만화"
    assert dialogs.window.calls == [("folder", {})]
    dialogs.window = FakeWindow(("C:/m.gguf",))
    assert dialogs.pick_model() == "C:/m.gguf"
    assert dialogs.window.calls[0][0] == "open"
    dialogs.window = FakeWindow(None)
    assert dialogs.pick_folder() is None
    assert dialogs.pick_model() is None
