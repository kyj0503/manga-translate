"""Which page to translate next: the page on screen first, then the next few, then the one before."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Sequence

from .cache import TranslationCache
from .page import PageResult
from .translate import CONTEXT_PAGES


def process_page(
    pages: Sequence[Path],
    index: int,
    *,
    scan: Callable[[Path], PageResult],
    translate: Callable[[Sequence[str], Sequence[PageResult]], list[str]],
    cache: TranslationCache,
    context_pages: int = CONTEXT_PAGES,
) -> PageResult:
    """Detect and read the page's text, translate it with the previous pages as context, and cache it."""
    source = pages[index]
    result = scan(source)
    if result.blocks:
        earlier = (cache.get(page) for page in pages[max(0, index - context_pages):index])
        context = [page for page in earlier if page is not None and page.blocks]
        result = result.with_translations(translate([b.text for b in result.blocks], context))
    cache.put(source, result)
    return result


class Scheduler:
    """One background thread that processes one page at a time in priority order."""

    def __init__(
        self,
        process: Callable[[Sequence[Path], int], object],
        is_done: Callable[[Path], bool],
        *,
        next_pages: int = 3,
        previous_pages: int = 1,
    ) -> None:
        self._process = process
        self._is_done = is_done
        self._next_pages = next_pages
        self._previous_pages = previous_pages
        self._cond = threading.Condition()
        self._queue: list[tuple[tuple[Path, ...], int]] = []
        self._failed: dict[Path, str] = {}
        self._working: Path | None = None
        self._stopped = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def focus(self, pages: Sequence[Path], index: int) -> None:
        pages = tuple(pages)
        order = [index, *(index + i for i in range(1, self._next_pages + 1)), *(index - i for i in range(1, self._previous_pages + 1))]
        wanted = [i for i in order if 0 <= i < len(pages) and not self._is_done(pages[i])]
        with self._cond:
            if self._stopped:
                return
            self._queue = [
                (pages, i) for i in wanted if pages[i] not in self._failed and pages[i] != self._working
            ]
            self._cond.notify_all()

    def retry(self, pages: Sequence[Path], index: int) -> None:
        with self._cond:
            self._failed.pop(tuple(pages)[index], None)
        self.focus(pages, index)

    def status(self, page: Path) -> tuple[str, str]:
        with self._cond:
            if page in self._failed:
                return ("failed", self._failed[page])
            if page == self._working:
                return ("working", "")
            return ("pending", "")

    def wait_idle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._queue or self._working is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._queue = []
            self._cond.notify_all()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stopped:
                    self._cond.wait()
                if self._stopped:
                    return
                pages, index = self._queue.pop(0)
                self._working = pages[index]
            error = None
            try:
                self._process(pages, index)
            except Exception as e:
                error = str(e) or type(e).__name__
            with self._cond:
                if error is not None:
                    self._failed[pages[index]] = error
                self._working = None
                self._cond.notify_all()
