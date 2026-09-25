from __future__ import annotations

import argparse
from pathlib import Path

from .bench import BenchMeta, PageResult, run_bench, summarize, write_outputs
from .glossary import load_glossary
from .source import list_images


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manga-viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="이미지 폴더를 번역하고 속도와 결과를 리포트로 저장")
    bench.add_argument("folder", type=Path, help="만화 이미지 폴더")
    bench.add_argument("--llama-server", type=Path, required=True, help="llama-server.exe 경로")
    bench.add_argument("--model", type=Path, required=True, help="GGUF 모델 경로")
    bench.add_argument("--mmproj", type=Path, help="이미지 입력용 mmproj GGUF 경로")
    bench.add_argument("--with-image", action="store_true", help="페이지 이미지를 번역 참고 자료로 함께 보냄 (--mmproj 필요)")
    bench.add_argument("--model-id", help="리포트에 표시할 모델 이름 (기본: 파일 이름)")
    bench.add_argument("--glossary", type=Path, help="용어집 TOML")
    bench.add_argument("--limit", type=int, help="앞에서부터 N장만 처리")
    bench.add_argument("--out", type=Path, default=Path("bench-out"), help="결과 폴더")
    bench.add_argument("--ctx-size", type=int, default=8192, help="LLM 컨텍스트 길이")
    bench.add_argument("--no-think", action="store_true", help="추론(thinking) 모드가 있는 모델에서 끄기")

    args = parser.parse_args(argv)
    return _run_bench(args)


def _run_bench(args: argparse.Namespace) -> int:
    images = list_images(args.folder)[: args.limit]
    if not images:
        print(f"이미지가 없습니다: {args.folder}")
        return 2
    if args.with_image and args.mmproj is None:
        print("--with-image를 쓰려면 --mmproj로 mmproj 파일 경로를 지정해야 합니다.")
        return 2
    glossary = load_glossary(args.glossary) if args.glossary else []

    # Heavy imports only when actually running.
    from .llm.client import ChatClient
    from .llm.llama import LlamaConfig, start_llama_server
    from .translate import Translator
    from .vision import Vision
    from .winjob import KillOnCloseJob

    args.out.mkdir(parents=True, exist_ok=True)
    job = KillOnCloseJob()
    print("LLM 서버를 시작하는 중...")
    server, base_url = start_llama_server(
        LlamaConfig(exe=args.llama_server, model=args.model, mmproj=args.mmproj, ctx_size=args.ctx_size),
        args.out / "llama-server.log",
        job=job,
    )
    client = None
    try:
        print("비전 모델을 불러오는 중...")
        vision = Vision()
        client = ChatClient(base_url)
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if args.no_think else None
        translator = Translator(client, extra_body=extra)

        def report(r: PageResult) -> None:
            print(
                f"{r.image_path.name}: 말풍선 {len(r.analysis.blocks)}개, "
                f"비전 {r.vision_s:.2f}s, LLM {r.translation.elapsed_s:.2f}s, "
                f"실패 {len(r.translation.failed_ids)}개"
            )

        results = run_bench(images, vision, translator, glossary, on_page=report, with_image=args.with_image)
    finally:
        if client is not None:
            client.close()
        server.stop()
        job.close()

    meta = BenchMeta(model_id=args.model_id or args.model.stem, folder=args.folder, with_image=args.with_image)
    html_path = write_outputs(results, meta, args.out)
    for key, value in summarize(results).items():
        print(f"{key}: {value}")
    print(f"리포트: {html_path}")
    return 0
