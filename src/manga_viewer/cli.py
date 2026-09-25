from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .bench import BenchMeta, PageResult, run_bench, summarize, write_outputs
from .glossary import load_glossary
from .source import list_images


class CliError(Exception):
    """A problem the user can fix; printed as-is with exit code 2."""


def _force_utf8_stdout() -> None:
    # The Windows console code page (e.g. cp949) cannot encode every kanji in file names.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("1 이상의 정수여야 합니다")
    return number


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llama-server", type=Path, required=True, help="llama-server.exe 경로")
    parser.add_argument("--model", type=Path, required=True, help="GGUF 모델 경로")
    parser.add_argument("--mmproj", type=Path, help="이미지 입력용 mmproj GGUF 경로")
    parser.add_argument("--with-image", action="store_true", help="페이지 이미지를 번역 참고 자료로 함께 보냄 (--mmproj 필요)")
    parser.add_argument("--glossary", type=Path, help="용어집 TOML")
    parser.add_argument("--ctx-size", type=int, default=8192, help="LLM 컨텍스트 길이")
    parser.add_argument("--no-think", action="store_true", help="추론(thinking) 모드가 있는 모델에서 끄기")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(prog="manga-viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="이미지 폴더를 번역하고 속도와 결과를 리포트로 저장")
    bench.add_argument("folder", type=Path, help="만화 이미지 폴더")
    _add_model_args(bench)
    bench.add_argument("--model-id", help="리포트에 표시할 모델 이름 (기본: 파일 이름)")
    bench.add_argument("--limit", type=_positive_int, help="앞에서부터 N장만 처리")
    bench.add_argument("--out", type=Path, default=Path("bench-out"), help="결과 폴더")

    args = parser.parse_args(argv)
    try:
        return _run_bench(args)
    except CliError as e:
        print(e)
        return 2


def _images(folder: Path, limit: int | None) -> list[Path]:
    if not folder.is_dir():
        raise CliError(f"폴더가 없습니다: {folder}")
    images = list_images(folder)[:limit]
    if not images:
        raise CliError(f"이미지가 없습니다: {folder}")
    return images


def _check_model_args(args: argparse.Namespace) -> None:
    if args.with_image and args.mmproj is None:
        raise CliError("--with-image를 쓰려면 --mmproj로 mmproj 파일 경로를 지정해야 합니다.")
    for label, path in (
        ("llama-server", args.llama_server),
        ("모델", args.model),
        ("mmproj", args.mmproj),
        ("용어집", args.glossary),
    ):
        if path is not None and not path.is_file():
            raise CliError(f"{label} 파일이 없습니다: {path}")


@contextmanager
def _pipeline(args: argparse.Namespace, log_path: Path) -> Iterator[tuple[object, object]]:
    """Start llama-server, the chat client and the vision models; always tear down what was started."""
    # Heavy imports only when actually running.
    from .llm.client import ChatClient
    from .llm.llama import LlamaConfig, start_llama_server
    from .llm.process import ServerStartError
    from .translate import Translator
    from .vision import Vision
    from .winjob import KillOnCloseJob

    job = KillOnCloseJob()
    server = None
    client = None
    try:
        print("LLM 서버를 시작하는 중...")
        try:
            server, base_url = start_llama_server(
                LlamaConfig(exe=args.llama_server, model=args.model, mmproj=args.mmproj, ctx_size=args.ctx_size),
                log_path,
                job=job,
            )
        except (ServerStartError, OSError) as e:
            raise CliError(f"LLM 서버를 시작하지 못했습니다: {e}") from e
        client = ChatClient(base_url)
        print("비전 모델을 불러오는 중...")
        vision = Vision()
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if args.no_think else None
        yield vision, Translator(client, extra_body=extra)
    finally:
        if client is not None:
            client.close()
        if server is not None:
            server.stop()
        job.close()


def _run_bench(args: argparse.Namespace) -> int:
    images = _images(args.folder, args.limit)
    _check_model_args(args)
    glossary = load_glossary(args.glossary) if args.glossary else []
    args.out.mkdir(parents=True, exist_ok=True)
    meta = BenchMeta(model_id=args.model_id or args.model.stem, folder=args.folder, with_image=args.with_image)
    results: list[PageResult] = []

    def report(r: PageResult) -> None:
        results.append(r)
        print(
            f"{r.image_path.name}: 말풍선 {len(r.analysis.blocks)}개, "
            f"비전 {r.vision_s:.2f}s, LLM {r.translation.elapsed_s:.2f}s, "
            f"실패 {len(r.translation.failed_ids)}개"
        )

    def skip(path: Path, exc: Exception) -> None:
        print(f"{path.name}: 건너뜀 ({exc})")

    try:
        with _pipeline(args, args.out / "llama-server.log") as (vision, translator):
            run_bench(images, vision, translator, glossary, on_page=report, with_image=args.with_image, on_error=skip)
    finally:
        if results:  # keep partial results even if the run was interrupted
            html_path = write_outputs(results, meta, args.out)
            for key, value in summarize(results).items():
                print(f"{key}: {value}")
            print(f"리포트: {html_path}")
    return 0
