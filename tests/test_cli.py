import os
import subprocess
import sys

import pytest

from manga_viewer.cli import main


def model_files(tmp_path):
    exe = tmp_path / "llama-server.exe"
    model = tmp_path / "m.gguf"
    exe.write_bytes(b"")
    model.write_bytes(b"")
    return ["--llama-server", str(exe), "--model", str(model)]


def test_bench_requires_llama_server_and_model(tmp_path):
    with pytest.raises(SystemExit):
        main(["bench", str(tmp_path)])


def test_bench_with_empty_folder_returns_error(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    code = main(["bench", str(pages), *model_files(tmp_path)])
    assert code == 2
    assert "이미지가 없습니다" in capsys.readouterr().out


def test_missing_folder_returns_error(tmp_path, capsys):
    code = main(["bench", str(tmp_path / "nope"), *model_files(tmp_path)])
    assert code == 2
    assert "폴더가 없습니다" in capsys.readouterr().out


def test_limit_must_be_positive(tmp_path):
    with pytest.raises(SystemExit):
        main(["bench", str(tmp_path), *model_files(tmp_path), "--limit", "0"])


def test_missing_model_file_returns_error(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "1.png").write_bytes(b"")
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"")
    code = main(["bench", str(pages), "--llama-server", str(exe), "--model", str(tmp_path / "missing.gguf")])
    assert code == 2
    assert "모델 파일이 없습니다" in capsys.readouterr().out


def test_with_image_requires_mmproj(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "1.png").write_bytes(b"")
    code = main(["bench", str(pages), *model_files(tmp_path), "--with-image"])
    assert code == 2
    assert "--mmproj" in capsys.readouterr().out


def fake_pipeline(monkeypatch, calls, *, vision_factory, start_error=None):
    """Patch the names _pipeline imports lazily so no GPU, server or model is needed."""
    import manga_viewer.llm.client
    import manga_viewer.llm.llama
    import manga_viewer.vision
    import manga_viewer.winjob

    class FakeServer:
        def stop(self):
            calls.append("server.stop")

    class FakeJob:
        def close(self):
            calls.append("job.close")

    class FakeClient:
        def __init__(self, base_url):
            calls.append("client.open")

        def close(self):
            calls.append("client.close")

    def fake_start(*args, **kwargs):
        if start_error is not None:
            raise start_error
        return FakeServer(), "http://x"

    monkeypatch.setattr(manga_viewer.llm.llama, "start_llama_server", fake_start)
    monkeypatch.setattr(manga_viewer.winjob, "KillOnCloseJob", FakeJob)
    monkeypatch.setattr(manga_viewer.llm.client, "ChatClient", FakeClient)
    monkeypatch.setattr(manga_viewer.vision, "Vision", vision_factory)


def test_pipeline_cleans_up_when_vision_fails_to_load(tmp_path, monkeypatch, capsys):
    from PIL import Image

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (10, 10), "white").save(pages / "1.png")
    calls = []

    def broken_vision():
        raise RuntimeError("boom")

    fake_pipeline(monkeypatch, calls, vision_factory=broken_vision)
    with pytest.raises(RuntimeError, match="boom"):
        main(["bench", str(pages), *model_files(tmp_path), "--out", str(tmp_path / "out")])
    assert calls == ["client.open", "client.close", "server.stop", "job.close"]


def test_server_start_failure_is_a_user_error(tmp_path, monkeypatch, capsys):
    from PIL import Image

    from manga_viewer.llm.process import ServerStartError

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (10, 10), "white").save(pages / "1.png")
    calls = []
    fake_pipeline(monkeypatch, calls, vision_factory=object, start_error=ServerStartError("no gpu"))
    code = main(["bench", str(pages), *model_files(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 2
    assert "LLM 서버를 시작하지 못했습니다" in capsys.readouterr().out
    assert calls == ["job.close"]


def test_output_survives_non_cp949_characters(tmp_path):
    folder = tmp_path / "気"  # not encodable in cp949
    folder.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    code = (
        "import sys\n"
        "from manga_viewer.cli import main\n"
        f"sys.exit(main(['bench', {str(folder)!r}, '--llama-server', 'x', '--model', 'm']))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert result.returncode == 2, result.stderr.decode("utf-8", "replace")
    assert "気" in result.stdout.decode("utf-8")


def test_returns_1_when_a_page_is_skipped(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    from PIL import Image

    import manga_viewer.translate
    from manga_viewer.translate import PageTranslation
    from manga_viewer.types import PageAnalysis

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (10, 10), "white").save(pages / "1.png")
    Image.new("RGB", (10, 10), "white").save(pages / "2.png")
    calls = []

    class FakeVision:
        def analyze(self, path):
            if Path(path).name == "2.png":
                raise OSError("broken")
            return PageAnalysis(width=10, height=10, blocks=())

    class FakeTranslator:
        def __init__(self, client, **kwargs):
            pass

        def translate_page(self, blocks, context_pages=(), glossary=(), page_image=None):
            return PageTranslation({}, (), 0, None, 0.0)

    fake_pipeline(monkeypatch, calls, vision_factory=FakeVision)
    monkeypatch.setattr(manga_viewer.translate, "Translator", FakeTranslator)

    code = main(["bench", str(pages), *model_files(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 1
    assert "2.png: 건너뜀" in capsys.readouterr().out


def test_original_exception_survives_failed_report_write(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    from PIL import Image

    import manga_viewer.cli
    import manga_viewer.translate
    from manga_viewer.translate import PageTranslation
    from manga_viewer.types import PageAnalysis

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (10, 10), "white").save(pages / "1.png")
    Image.new("RGB", (10, 10), "white").save(pages / "2.png")
    Image.new("RGB", (10, 10), "white").save(pages / "3.png")
    calls = []

    class FakeVision:
        def analyze(self, path):
            if Path(path).name == "2.png":
                raise OSError("broken")
            return PageAnalysis(width=10, height=10, blocks=())

    class FakeTranslator:
        def __init__(self, client, **kwargs):
            self._calls = 0

        def translate_page(self, blocks, context_pages=(), glossary=(), page_image=None):
            self._calls += 1
            if self._calls == 2:
                raise RuntimeError("boom")
            return PageTranslation({}, (), 0, None, 0.0)

    fake_pipeline(monkeypatch, calls, vision_factory=FakeVision)
    monkeypatch.setattr(manga_viewer.translate, "Translator", FakeTranslator)

    def broken_write_outputs(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(manga_viewer.cli, "write_outputs", broken_write_outputs)

    with pytest.raises(RuntimeError, match="boom"):
        main(["bench", str(pages), *model_files(tmp_path), "--out", str(tmp_path / "out")])
    assert "리포트 저장 실패" in capsys.readouterr().out
