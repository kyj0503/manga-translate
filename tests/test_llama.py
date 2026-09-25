from pathlib import Path

from manga_viewer.llm.llama import LlamaConfig, build_llama_args


def test_build_llama_args():
    cfg = LlamaConfig(exe=Path("C:/x/llama-server.exe"), model=Path("C:/m/model.gguf"))
    args = build_llama_args(cfg, port=5555)
    assert args[0] == str(Path("C:/x/llama-server.exe"))
    joined = " ".join(args)
    assert f"-m {Path('C:/m/model.gguf')}" in joined
    assert "--host 127.0.0.1" in joined
    assert "--port 5555" in joined
    assert "-c 8192" in joined
    assert "-ngl 999" in joined
    assert "--parallel 1" in joined
    assert "--reasoning-budget 0" in joined
    assert "--mmproj" not in args
