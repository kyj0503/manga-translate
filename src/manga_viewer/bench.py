from __future__ import annotations

import html
import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable, Protocol, Sequence

from .glossary import GlossaryEntry
from .page_image import image_data_url
from .translate import ContextPage, PageTranslation
from .types import PageAnalysis, TextBlock

CONTEXT_PAGES = 2


class PageVision(Protocol):
    def analyze(self, image_path: Path) -> PageAnalysis: ...


class PageTranslator(Protocol):
    def translate_page(
        self,
        blocks: Sequence[TextBlock],
        context_pages: Sequence[ContextPage] = ...,
        glossary: Sequence[GlossaryEntry] = ...,
        page_image: str | None = ...,
    ) -> PageTranslation: ...


@dataclass(frozen=True)
class PageResult:
    image_path: Path
    analysis: PageAnalysis
    translation: PageTranslation
    vision_s: float


@dataclass(frozen=True)
class BenchMeta:
    model_id: str
    folder: Path
    with_image: bool = False


def run_bench(
    image_paths: Iterable[Path],
    vision: PageVision,
    translator: PageTranslator,
    glossary: Sequence[GlossaryEntry],
    on_page: Callable[[PageResult], None] | None = None,
    with_image: bool = False,
) -> list[PageResult]:
    results: list[PageResult] = []
    context: deque[ContextPage] = deque(maxlen=CONTEXT_PAGES)
    for path in image_paths:
        start = time.perf_counter()
        analysis = vision.analyze(path)
        vision_s = time.perf_counter() - start

        page_image = image_data_url(path) if with_image and analysis.blocks else None
        translation = translator.translate_page(analysis.blocks, list(context), glossary, page_image)
        context.append(
            [(b.ja, translation.translations[b.id]) for b in analysis.blocks if b.id in translation.translations]
        )

        result = PageResult(path, analysis, translation, vision_s)
        results.append(result)
        if on_page is not None:
            on_page(result)
    return results


def summarize(results: Sequence[PageResult]) -> dict:
    speeds = [r.translation.tokens_per_second for r in results if r.translation.tokens_per_second]
    return {
        "pages": len(results),
        "bubbles": sum(len(r.analysis.blocks) for r in results),
        "failed_bubbles": sum(len(r.translation.failed_ids) for r in results),
        "avg_vision_s": round(mean(r.vision_s for r in results), 3) if results else 0.0,
        "avg_llm_s": round(mean(r.translation.elapsed_s for r in results), 3) if results else 0.0,
        "avg_tokens_per_second": round(mean(speeds), 1) if speeds else None,
    }


def _page_json(result: PageResult) -> dict:
    return {
        "image": str(result.image_path),
        "vision_s": round(result.vision_s, 3),
        "llm_s": round(result.translation.elapsed_s, 3),
        "tokens_per_second": result.translation.tokens_per_second,
        "bubbles": [
            {"id": b.id, "box": list(b.box), "ja": b.ja, "ko": result.translation.translations.get(b.id)}
            for b in result.analysis.blocks
        ],
    }


def render_report(results: Sequence[PageResult], meta: BenchMeta) -> str:
    esc = html.escape
    summary = summarize(results)
    parts = [
        "<!doctype html><html lang='ko'><meta charset='utf-8'>",
        f"<title>bench: {esc(meta.model_id)}</title>",
        "<style>body{font-family:sans-serif;margin:24px}section{display:flex;gap:24px;margin:32px 0}"
        "img{max-width:480px;border:1px solid #ccc}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:4px 8px;vertical-align:top}.fail{background:#fdd}</style>",
        f"<h1>{esc(meta.model_id)}</h1>",
        f"<p>{esc(str(meta.folder))} · {'이미지 참고' if meta.with_image else '텍스트 전용'}</p>",
        "<table>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>" for k, v in summary.items()) + "</table>",
    ]
    for r in results:
        rows = []
        for b in r.analysis.blocks:
            ko = r.translation.translations.get(b.id)
            cls = "" if ko is not None else " class='fail'"
            rows.append(f"<tr{cls}><td>{b.id}</td><td>{esc(b.ja)}</td><td>{esc(ko or '(실패)')}</td></tr>")
        parts.append(
            "<section>"
            f"<img src='{esc(r.image_path.resolve().as_uri())}' loading='lazy'>"
            f"<div><h2>{esc(r.image_path.name)}</h2>"
            f"<p>비전 {r.vision_s:.2f}s · LLM {r.translation.elapsed_s:.2f}s</p>"
            "<table><tr><th>#</th><th>원문</th><th>번역</th></tr>" + "".join(rows) + "</table></div>"
            "</section>"
        )
    parts.append("</html>")
    return "\n".join(parts)


def write_outputs(results: Sequence[PageResult], meta: BenchMeta, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"model_id": meta.model_id, "folder": str(meta.folder), "with_image": meta.with_image},
        "summary": summarize(results),
        "pages": [_page_json(r) for r in results],
    }
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = out_dir / "report.html"
    html_path.write_text(render_report(results, meta), encoding="utf-8")
    return html_path
