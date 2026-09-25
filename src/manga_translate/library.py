"""Books in a folder the user opened: every folder that directly holds images is one book."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natsort import natsort_keygen, ns

from .source import find_images

_NATURAL = natsort_keygen(alg=ns.IGNORECASE)


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    dir: Path
    pages: tuple[Path, ...]


def _sort_key(root: Path, folder: Path) -> tuple[int, object]:
    # Subfolders first in natural order of their path, then the root folder's own pages.
    relative = folder.relative_to(root)
    if not relative.parts:
        return (1, ())
    return (0, _NATURAL(relative.as_posix()))


def scan_library(root: Path) -> list[Book]:
    groups: dict[Path, list[Path]] = {}
    for image in find_images(root):
        groups.setdefault(image.parent, []).append(image)
    books: list[Book] = []
    for folder, pages in sorted(groups.items(), key=lambda item: _sort_key(root, item[0])):
        relative = folder.relative_to(root)
        title = relative.as_posix() if relative.parts else (root.name or str(root))
        books.append(Book(len(books), title, folder, tuple(pages)))
    return books


def is_inside(root: Path, path: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())
