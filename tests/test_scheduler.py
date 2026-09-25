import threading
from pathlib import Path

from manga_translate.cache import TranslationCache
from manga_translate.page import Block, PageResult
from manga_translate.scheduler import Scheduler, process_page

PAGES = tuple(Path(f"p{i}") for i in range(10))


def recorder(done=frozenset(), fail=frozenset(), gate=None):
    order = []

    def process(pages, index):
        order.append(index)
        if gate is not None and index == gate[0]:
            gate[1].wait(10)
        if index in fail:
            raise RuntimeError(f"page {index} broke")

    return order, process, (lambda page: int(page.name[1:]) in done)


def test_focus_orders_current_then_next_three_then_previous():
    order, process, is_done = recorder()
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert order == [5, 6, 7, 8, 4]
    finally:
        scheduler.stop()


def test_done_pages_and_out_of_range_pages_are_skipped():
    order, process, is_done = recorder(done={6})
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 8)
        assert scheduler.wait_idle(10)
        assert order == [8, 9, 7]
    finally:
        scheduler.stop()


def test_refocus_keeps_the_page_in_progress_and_replaces_the_queue():
    release = threading.Event()
    order, process, is_done = recorder(gate=(5, release))
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 5)
        for _ in range(200):
            if scheduler.status(PAGES[5]) == ("working", ""):
                break
            threading.Event().wait(0.01)
        assert scheduler.status(PAGES[5]) == ("working", "")
        assert scheduler.status(PAGES[6]) == ("pending", "")
        scheduler.focus(PAGES, 0)
        release.set()
        assert scheduler.wait_idle(10)
        assert order == [5, 0, 1, 2, 3]
    finally:
        release.set()
        scheduler.stop()


def test_failed_page_is_not_retried_until_asked():
    order, process, is_done = recorder(fail={5})
    scheduler = Scheduler(process, is_done)
    try:
        scheduler.focus(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert scheduler.status(PAGES[5]) == ("failed", "page 5 broke")
        order.clear()
        scheduler.focus(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert 5 not in order
        order.clear()
        scheduler.retry(PAGES, 5)
        assert scheduler.wait_idle(10)
        assert order[0] == 5
    finally:
        scheduler.stop()


def test_stop_ends_the_thread():
    _, process, is_done = recorder()
    scheduler = Scheduler(process, is_done)
    scheduler.stop()
    scheduler.focus(PAGES, 0)  # ignored after stop
    assert scheduler.wait_idle(1)


def make_pages(tmp_path, count):
    pages = []
    for i in range(count):
        page = tmp_path / f"{i:03d}.png"
        page.write_bytes(f"image {i}".encode())
        pages.append(page)
    return pages


def test_process_page_translates_with_previous_pages_as_context(tmp_path):
    pages = make_pages(tmp_path, 3)
    cache = TranslationCache(tmp_path / "cache", "m")
    earlier = PageResult((1, 1), (Block((0, 0, 1, 1), False, "前", "앞"),))
    cache.put(pages[0], earlier)
    scanned = PageResult((10, 10), (Block((1, 1, 5, 5), True, "今"), Block((6, 6, 9, 9), False, "次")))
    calls = []

    def translate(texts, context):
        calls.append((list(texts), list(context)))
        return ["지금", "다음"]

    result = process_page(pages, 2, scan=lambda path: scanned, translate=translate, cache=cache)

    assert [b.translation for b in result.blocks] == ["지금", "다음"]
    assert calls == [(["今", "次"], [earlier])]
    assert cache.get(pages[2]) == result


def test_process_page_with_no_text_skips_translation(tmp_path):
    pages = make_pages(tmp_path, 1)
    cache = TranslationCache(tmp_path / "cache", "m")
    empty = PageResult((10, 10), ())

    def translate(texts, context):
        raise AssertionError("nothing to translate")

    assert process_page(pages, 0, scan=lambda path: empty, translate=translate, cache=cache) == empty
    assert cache.get(pages[0]) == empty
