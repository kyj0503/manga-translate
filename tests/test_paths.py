import sys
from pathlib import Path

from manga_translate.paths import APP_HOME_ENV, AppLayout, app_dir, find_uv, uv_environment


def test_app_dir_defaults_to_the_folder_holding_the_venv():
    assert app_dir({}) == Path(sys.prefix).resolve().parent


def test_app_dir_override(tmp_path):
    assert app_dir({APP_HOME_ENV: str(tmp_path)}) == tmp_path


def test_layout(tmp_path):
    layout = AppLayout(tmp_path)
    assert layout.settings_path == tmp_path / "settings.json"
    assert layout.engine_dir == tmp_path / "engine" / "BallonsTranslator"
    assert layout.llama_dir == tmp_path / "runtime" / "llama"
    assert layout.llama_server == tmp_path / "runtime" / "llama" / "llama-server.exe"
    assert layout.models_dir == tmp_path / "models"
    assert layout.downloads_dir == tmp_path / "downloads"
    assert layout.bundled_uv == tmp_path / "tools" / "uv.exe"
    assert layout.uv_cache_dir == tmp_path / "downloads" / "uv-cache"
    assert layout.python_dir == tmp_path / "runtime" / "python"
    assert layout.work_dir == tmp_path / "work"


def test_uv_environment(tmp_path):
    layout = AppLayout(tmp_path)
    assert uv_environment(layout) == {
        "UV_CACHE_DIR": str(tmp_path / "downloads" / "uv-cache"),
        "UV_PYTHON_INSTALL_DIR": str(tmp_path / "runtime" / "python"),
        "UV_PYTHON_PREFERENCE": "only-managed",
    }


def test_find_uv_order(tmp_path):
    layout = AppLayout(tmp_path)
    from_env = tmp_path / "env-uv.exe"
    from_path = tmp_path / "path-uv.exe"
    for f in (from_env, from_path):
        f.write_bytes(b"")
    layout.bundled_uv.parent.mkdir(parents=True)
    layout.bundled_uv.write_bytes(b"")

    assert find_uv(layout, {"UV": str(from_env)}, lambda n: str(from_path)) == from_env
    assert find_uv(layout, {}, lambda n: str(from_path)) == layout.bundled_uv
    layout.bundled_uv.unlink()
    assert find_uv(layout, {"UV": str(tmp_path / "gone.exe")}, lambda n: str(from_path)) == from_path
    assert find_uv(layout, {}, lambda n: None) is None
