import os

from manga_translate.cache import TranslationCache
from manga_translate.page import Block, PageResult

RESULT = PageResult((10, 20), (Block((1, 2, 3, 4), False, "原文", "번역"),))


def make_source(tmp_path, content=b"image"):
    source = tmp_path / "페이지 01.png"
    source.write_bytes(content)
    return source


def test_put_then_get(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    assert cache.get(source) is None
    cache.put(source, RESULT)
    assert cache.get(source) == RESULT
    assert list((tmp_path / "cache").glob("*.tmp")) == []


def test_changed_image_invalidates(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    cache.put(source, RESULT)
    source.write_bytes(b"different image")
    assert cache.get(source) is None


def test_changed_mtime_invalidates(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    cache.put(source, RESULT)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert cache.get(source) is None


def test_other_model_does_not_see_the_entry(tmp_path):
    source = make_source(tmp_path)
    TranslationCache(tmp_path / "cache", "gemma.gguf").put(source, RESULT)
    assert TranslationCache(tmp_path / "cache", "other.gguf").get(source) is None


def test_corrupt_entry_is_a_miss(tmp_path):
    source = make_source(tmp_path)
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    cache.put(source, RESULT)
    [entry] = (tmp_path / "cache").glob("*.json")
    entry.write_text("{broken", encoding="utf-8")
    assert cache.get(source) is None


def test_missing_source_is_a_miss(tmp_path):
    cache = TranslationCache(tmp_path / "cache", "gemma.gguf")
    assert cache.get(tmp_path / "없음.png") is None
