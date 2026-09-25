import json

from manga_viewer.settings import Settings, load_settings, save_settings


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    settings = Settings(llama_server="C:/l.exe", model="C:/모델.gguf", uv="C:/uv.exe", last_input="D:/만화")
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert "모델" in path.read_text(encoding="utf-8")  # stored as readable UTF-8


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_settings(bad) == Settings()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"model": "m.gguf", "future_option": 1}), encoding="utf-8")
    assert load_settings(path) == Settings(model="m.gguf")
