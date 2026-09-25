import pytest
from PIL import Image, ImageDraw

from manga_viewer.render import (
    DEFAULT_FONT,
    fit_text,
    render_page,
    text_color,
    widen_box,
    wrap_text,
)
from manga_viewer.types import TextBlock

pytestmark = pytest.mark.skipif(not DEFAULT_FONT.exists(), reason="Malgun Gothic not installed")


def font(size):
    from PIL import ImageFont

    return ImageFont.truetype(str(DEFAULT_FONT), size)


def test_text_color_contrasts_with_background():
    assert text_color((255, 255, 255)) == (0, 0, 0)
    assert text_color((20, 20, 20)) == (255, 255, 255)


def test_narrow_box_is_widened_within_image():
    assert widen_box((100, 0, 120, 100), (1000, 1000)) == (95, 0, 125, 100)
    assert widen_box((0, 0, 20, 100), (1000, 1000)) == (0, 0, 25, 100)


def test_wide_box_is_unchanged():
    assert widen_box((0, 0, 100, 100), (1000, 1000)) == (0, 0, 100, 100)


def test_wrap_text_respects_width_and_keeps_every_character():
    f = font(20)
    text = "안녕하세요 오늘은 날씨가 정말 좋네요"
    lines = wrap_text(text, f, 90)
    assert len(lines) > 1
    assert all(f.getlength(line) <= 90 for line in lines)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")


def test_wrap_text_breaks_a_long_word_by_character():
    f = font(20)
    lines = wrap_text("가나다라마바사아자차카타파하", f, 50)
    assert len(lines) > 1
    assert all(f.getlength(line) <= 50 for line in lines)
    assert "".join(lines) == "가나다라마바사아자차카타파하"


def test_longer_text_gets_a_smaller_font():
    short_font, _ = fit_text("응", DEFAULT_FONT, 100, 100)
    long_font, long_lines = fit_text("이건 정말 긴 대사라서 작게 써야 들어갑니다", DEFAULT_FONT, 100, 100)
    assert long_font.size < short_font.size
    assert all(long_font.getlength(line) <= 100 for line in long_lines)


def test_render_page_covers_text_and_draws_translation():
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).rectangle((60, 60, 140, 140), fill="black")  # "Japanese text"
    block = TextBlock(id=0, box=(50, 50, 150, 150), vertical=False, ja="x", bg_color=(255, 255, 255))

    out = render_page(image, [block], {0: "안녕"})

    assert out is not image
    assert image.getpixel((61, 61)) == (0, 0, 0)  # input untouched
    assert out.getpixel((61, 61)) == (255, 255, 255)  # old text painted over
    inside = out.crop((50, 50, 150, 150)).convert("L")
    assert inside.getextrema()[0] < 128  # some dark translated glyphs were drawn
    assert out.getpixel((10, 10)) == (255, 255, 255)  # outside untouched


def test_render_page_leaves_untranslated_bubbles_alone():
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).rectangle((60, 60, 140, 140), fill="black")
    block = TextBlock(id=0, box=(50, 50, 150, 150), vertical=False, ja="x", bg_color=(255, 255, 255))

    out = render_page(image, [block], {})

    assert out.getpixel((61, 61)) == (0, 0, 0)
