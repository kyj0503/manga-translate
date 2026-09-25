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
