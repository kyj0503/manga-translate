from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..winjob import KillOnCloseJob
from .process import ManagedServer, free_port


@dataclass(frozen=True)
class LlamaConfig:
    exe: Path
    model: Path
    ctx_size: int = 8192
    n_gpu_layers: int = 999


def build_llama_args(cfg: LlamaConfig, port: int) -> list[str]:
    return [
        str(cfg.exe),
        "-m", str(cfg.model),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", str(cfg.ctx_size),
        "-ngl", str(cfg.n_gpu_layers),
        "--parallel", "1",
        "--reasoning-budget", "0",  # translation needs no thinking; it only costs time
    ]


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
