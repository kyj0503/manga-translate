from pathlib import Path

import numpy as np
import pytest

from manga_viewer.vision import page_from_mokuro

FONT = next(
    (
        p
        for p in (
            Path("C:/Windows/Fonts/msgothic.ttc"),
            Path("C:/Windows/Fonts/YuGothM.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttc"),
        )
        if p.exists()
    ),
    None,
)


def test_page_from_mokuro_converts_orders_and_filters():
    image = np.full((200, 400, 3), 255, dtype=np.uint8)
    result = {
        "img_width": 400,
        "img_height": 200,
        "blocks": [
            {"box": [10.4, 10, 100, 90], "vertical": True, "lines": ["左", "です"]},
            {"box": [300, 12, 390, 88.6], "vertical": True, "lines": ["右"]},
            {"box": [150, 120, 250, 190], "vertical": False, "lines": ["", "  "]},
        ],
    }
    page = page_from_mokuro(result, image)

    assert (page.width, page.height) == (400, 200)
    assert [b.ja for b in page.blocks] == ["右", "左です"]
    assert [b.id for b in page.blocks] == [0, 1]
    assert page.blocks[1].box == (10, 10, 100, 90)
    assert page.blocks[0].box == (300, 12, 390, 89)
    assert page.blocks[0].vertical is True
    assert page.blocks[0].bg_color == (255, 255, 255)


@pytest.mark.gpu
def test_vision_reads_rendered_japanese(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("mokuro")
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")
    if FONT is None:
        pytest.skip("MS Gothic font not found")
    from PIL import Image, ImageDraw, ImageFont

    from manga_viewer.vision import Vision

    img = Image.new("RGB", (900, 300), "white")
    ImageDraw.Draw(img).text((40, 110), "今日はいい天気ですね", font=ImageFont.truetype(str(FONT), 64), fill="black")
    path = tmp_path / "ページ.png"  # non-ASCII path on purpose
    img.save(path)

    page = Vision().analyze(path)

    assert page.blocks, "no text detected"
    assert "天気" in "".join(b.ja for b in page.blocks)
