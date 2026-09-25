import json
from pathlib import Path

from manga_viewer.bench import BenchMeta, render_report, run_bench, summarize, write_outputs
from manga_viewer.glossary import GlossaryEntry
from manga_viewer.translate import PageTranslation
from manga_viewer.types import PageAnalysis, TextBlock


def page(*texts):
    return PageAnalysis(
        width=100,
        height=100,
        blocks=tuple(TextBlock(id=i, box=(0, 0, 10, 10), vertical=True, ja=t) for i, t in enumerate(texts)),
    )


class FakeVision:
    def __init__(self, pages):
        self.pages = pages

    def analyze(self, path):
        return self.pages[Path(path).name]


class FakeTranslator:
    def __init__(self):
        self.calls = []

    def translate_page(self, blocks, context_pages=(), glossary=(), page_image=None):
        self.calls.append({"context": list(context_pages), "glossary": list(glossary), "image": page_image})
        translations = {b.id: f"ko:{b.ja}" for b in blocks if b.ja != "fail"}
        failed = tuple(b.id for b in blocks if b.ja == "fail")
        return PageTranslation(translations, failed, 5, 30.0, 1.5)


def test_run_bench_passes_last_two_pages_as_context():
    vision = FakeVision({"1.png": page("a"), "2.png": page("b"), "3.png": page("c", "fail"), "4.png": page("d")})
    translator = FakeTranslator()
    glossary = [GlossaryEntry("a", "에이")]
    seen = []

    results = run_bench(
        [Path("1.png"), Path("2.png"), Path("3.png"), Path("4.png")],
        vision,
        translator,
        glossary,
        on_page=seen.append,
    )

    assert len(results) == 4 and seen == results
    assert translator.calls[0]["context"] == []
    assert translator.calls[2]["context"] == [[("a", "ko:a")], [("b", "ko:b")]]
    # failed bubbles are left out of later context
    assert translator.calls[3]["context"] == [[("b", "ko:b")], [("c", "ko:c")]]
    assert translator.calls[0]["glossary"] == glossary
    assert translator.calls[0]["image"] is None


def test_run_bench_with_image_sends_data_url(tmp_path):
    from PIL import Image

    Image.new("RGB", (40, 40), "white").save(tmp_path / "1.png")
    Image.new("RGB", (40, 40), "white").save(tmp_path / "2.png")
    vision = FakeVision({"1.png": page("a"), "2.png": page()})
    translator = FakeTranslator()

    run_bench([tmp_path / "1.png", tmp_path / "2.png"], vision, translator, [], with_image=True)

    assert translator.calls[0]["image"].startswith("data:image/jpeg;base64,")
    assert translator.calls[1]["image"] is None  # no text on the page, no image encoding


def test_summarize():
    vision = FakeVision({"1.png": page("a", "fail"), "2.png": page()})
    results = run_bench([Path("1.png"), Path("2.png")], vision, FakeTranslator(), [])
    summary = summarize(results)
    assert summary["pages"] == 2
    assert summary["bubbles"] == 2
    assert summary["failed_bubbles"] == 1
    assert summary["avg_llm_s"] == 1.5
    assert summary["avg_tokens_per_second"] == 30.0


def test_report_escapes_html(tmp_path):
    vision = FakeVision({"1.png": page("<script>x</script>")})
    results = run_bench([tmp_path / "1.png"], vision, FakeTranslator(), [])
    html = render_report(results, BenchMeta(model_id="m<1>", folder=tmp_path, with_image=True))
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html
    assert "m&lt;1&gt;" in html
    assert "이미지 참고" in html


def test_write_outputs(tmp_path):
    vision = FakeVision({"1.png": page("a")})
    results = run_bench([tmp_path / "1.png"], vision, FakeTranslator(), [])
    html_path = write_outputs(results, BenchMeta(model_id="m", folder=tmp_path), tmp_path / "out")
    assert html_path == tmp_path / "out" / "report.html"
    data = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert data["meta"] == {"model_id": "m", "folder": str(tmp_path), "with_image": False}
    assert data["summary"]["pages"] == 1
    assert data["pages"][0]["bubbles"] == [{"id": 0, "box": [0, 0, 10, 10], "ja": "a", "ko": "ko:a"}]


def test_textless_page_does_not_take_a_context_slot():
    vision = FakeVision({"1.png": page("a"), "2.png": page(), "3.png": page("b"), "4.png": page("c")})
    translator = FakeTranslator()
    run_bench([Path("1.png"), Path("2.png"), Path("3.png"), Path("4.png")], vision, translator, [])
    assert translator.calls[3]["context"] == [[("a", "ko:a")], [("b", "ko:b")]]


def test_unreadable_page_is_skipped_via_on_error():
    class BrokenVision(FakeVision):
        def analyze(self, path):
            if Path(path).name == "2.png":
                raise OSError("cannot identify image file")
            return super().analyze(path)

    vision = BrokenVision({"1.png": page("a"), "3.png": page("b")})
    errors = []
    results = run_bench(
        [Path("1.png"), Path("2.png"), Path("3.png")],
        vision,
        FakeTranslator(),
        [],
        on_error=lambda path, exc: errors.append((path.name, str(exc))),
    )
    assert [r.image_path.name for r in results] == ["1.png", "3.png"]
    assert errors == [("2.png", "cannot identify image file")]


def test_without_on_error_the_exception_propagates():
    import pytest

    class BrokenVision:
        def analyze(self, path):
            raise OSError("broken")

    with pytest.raises(OSError):
        run_bench([Path("1.png")], BrokenVision(), FakeTranslator(), [])
