import subprocess
import sys


def test_heavy_dependencies_are_not_imported_at_module_level():
    code = (
        "import sys\n"
        "import manga_viewer.cli, manga_viewer.bench, manga_viewer.translate, manga_viewer.vision\n"
        "heavy = [m for m in ('torch', 'mokuro') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
