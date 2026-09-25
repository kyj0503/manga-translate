import json

from manga_translate.settings import Settings, load_settings, save_settings


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(
        model="C:/모델.gguf",
        last_library="D:/만화",
        page_direction="ltr",
        positions={"D:/만화/1권": 12},
    )
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert "모델" in path.read_text(encoding="utf-8")


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_settings(bad) == Settings()
    not_object = tmp_path / "list.json"
    not_object.write_text("[1, 2]", encoding="utf-8")
    assert load_settings(not_object) == Settings()


def test_save_settings_writes_atomically(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(last_library="D:/만화", positions={"D:/만화/1권": 3})
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert list(tmp_path.iterdir()) == [path]  # no leftover .tmp file


def test_old_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"model": "m.gguf", "llama_server": "x", "last_input": "D:/a", "last_output": "D:/b"}),
        encoding="utf-8",
    )
    assert load_settings(path) == Settings(model="m.gguf")


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "model": 3,
                "page_direction": "up",
                "positions": {"a": 2, "b": -1, "c": "x", "d": True},
            }
        ),
        encoding="utf-8",
    )
    assert load_settings(path) == Settings(positions={"a": 2})
