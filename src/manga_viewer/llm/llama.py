from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..winjob import KillOnCloseJob
from .process import ManagedServer, free_port


@dataclass(frozen=True)
class LlamaConfig:
    exe: Path
    model: Path
    mmproj: Path | None = None  # vision projector; required for image input
    ctx_size: int = 8192
    n_gpu_layers: int = 999


def build_llama_args(cfg: LlamaConfig, port: int) -> list[str]:
    args = [
        str(cfg.exe),
        "-m", str(cfg.model),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", str(cfg.ctx_size),
        "-ngl", str(cfg.n_gpu_layers),
        "--parallel", "1",
    ]
    if cfg.mmproj is not None:
        args += ["--mmproj", str(cfg.mmproj)]
    return args


def start_llama_server(
    cfg: LlamaConfig,
    log_path: Path,
    job: KillOnCloseJob | None = None,
    timeout: float = 300.0,
) -> tuple[ManagedServer, str]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = ManagedServer(build_llama_args(cfg, port), f"{base_url}/health", log_path, job)
    server.start(timeout=timeout)
    return server, base_url
