import pytest

from manga_translate.page import Block, PageResult

PAGE = PageResult((800, 1200), (Block((1, 2, 30, 40), True, "こんにちは"), Block((5, 6, 70, 80), False, "えっ")))


def test_json_roundtrip():
    data = PAGE.to_json()
    assert data == {
        "size": [800, 1200],
        "blocks": [
            {"xyxy": [1, 2, 30, 40], "vertical": True, "text": "こんにちは", "translation": ""},
            {"xyxy": [5, 6, 70, 80], "vertical": False, "text": "えっ", "translation": ""},
        ],
    }
    assert PageResult.from_json(data) == PAGE


def test_from_json_without_translation_defaults_to_empty():
    page = PageResult.from_json({"size": [1, 2], "blocks": [{"xyxy": [0, 0, 1, 1], "vertical": False, "text": "a"}]})
    assert page.blocks[0].translation == ""


def test_from_json_rejects_bad_boxes():
    with pytest.raises(ValueError):
        PageResult.from_json({"size": [1, 2], "blocks": [{"xyxy": [0, 0, 1], "vertical": False, "text": "a"}]})


def test_with_translations():
    translated = PAGE.with_translations(["안녕", "엣"])
    assert [b.translation for b in translated.blocks] == ["안녕", "엣"]
    assert translated.blocks[0].text == "こんにちは"
    with pytest.raises(ValueError):
        PAGE.with_translations(["하나"])
