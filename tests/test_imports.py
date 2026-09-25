import subprocess
import sys


def test_engine_modules_are_never_imported_by_the_app():
    code = (
        "import sys\n"
        "import manga_translate.app, manga_translate.server, manga_translate.scheduler, manga_translate.worker_client, "
        "manga_translate.translate, manga_translate.cache, manga_translate.library, manga_translate.engine, "
        "manga_translate.components, manga_translate.download, manga_translate.paths\n"
        "leaked = [m for m in ('torch', 'ballontranslator', 'webview') if m in sys.modules]\n"
        "assert not leaked, leaked\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
