import json

from manga_translate.settings import Settings, load_settings, save_settings


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(model="C:/모델.gguf", last_input="D:/만화", last_output="D:/만화_번역")
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert "모델" in path.read_text(encoding="utf-8")


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_settings(bad) == Settings()


def test_old_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"model": "m.gguf", "llama_server": "x", "engine_dir": "y", "uv": "z"}), encoding="utf-8")
    assert load_settings(path) == Settings(model="m.gguf")
