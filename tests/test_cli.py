import pytest

from manga_viewer.cli import main


def test_bench_requires_llama_server_and_model(tmp_path):
    with pytest.raises(SystemExit):
        main(["bench", str(tmp_path)])


def test_bench_with_empty_folder_returns_error(tmp_path, capsys):
    code = main(["bench", str(tmp_path), "--llama-server", "x.exe", "--model", "m.gguf"])
    assert code == 2
    assert "이미지가 없습니다" in capsys.readouterr().out


def test_with_image_requires_mmproj(tmp_path, capsys):
    (tmp_path / "1.png").write_bytes(b"")
    code = main(["bench", str(tmp_path), "--llama-server", "x.exe", "--model", "m.gguf", "--with-image"])
    assert code == 2
    assert "--mmproj" in capsys.readouterr().out


def test_bench_closes_client_even_if_vision_fails(tmp_path, monkeypatch, capsys):
    """Regression test: client must be closed in finally block, not after run_bench."""
    from PIL import Image

    # Create a real PNG image
    Image.new("RGB", (10, 10), "white").save(tmp_path / "1.png")

    # Record calls to cleanup methods
    calls = {"server_stop": [], "client_close": [], "job_close": []}

    class FakeServer:
        def stop(self):
            calls["server_stop"].append(True)

    class FakeJob:
        def close(self):
            calls["job_close"].append(True)

    class FakeClient:
        def __init__(self, base_url):
            self.base_url = base_url

        def close(self):
            calls["client_close"].append(True)

    class FakeVision:
        def __init__(self):
            pass

        def analyze(self, path):
            raise RuntimeError("boom")

    def fake_start_llama_server(*args, **kwargs):
        return (FakeServer(), "http://x")

    # Patch the lazy-imported names on their modules
    import manga_viewer.llm.llama
    import manga_viewer.winjob
    import manga_viewer.llm.client
    import manga_viewer.vision

    monkeypatch.setattr(manga_viewer.llm.llama, "start_llama_server", fake_start_llama_server)
    monkeypatch.setattr(manga_viewer.winjob, "KillOnCloseJob", FakeJob)
    monkeypatch.setattr(manga_viewer.llm.client, "ChatClient", FakeClient)
    monkeypatch.setattr(manga_viewer.vision, "Vision", FakeVision)

    # Should raise RuntimeError from Vision.analyze
    with pytest.raises(RuntimeError, match="boom"):
        main(["bench", str(tmp_path), "--llama-server", "x.exe", "--model", "m.gguf"])

    # All cleanup methods must have been called
    capsys.readouterr()  # Clear captured output
    assert calls["client_close"] == [True], "client.close() not called"
    assert calls["server_stop"] == [True], "server.stop() not called"
    assert calls["job_close"] == [True], "job.close() not called"
