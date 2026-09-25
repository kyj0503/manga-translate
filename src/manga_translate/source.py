from __future__ import annotations

from pathlib import Path

from natsort import natsorted, ns

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})


def find_images(root: Path, exclude: Path | None = None) -> list[Path]:
    """Image files under ``root``, recursively, naturally sorted by their path relative to ``root``.

    Directories whose name starts with "." are skipped, as is everything inside ``exclude``
    (compared by resolved path) when it is given.
    """
    resolved_exclude = exclude.resolve() if exclude is not None else None
    matches = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts[:-1]):
            continue
        if resolved_exclude is not None:
            resolved = path.resolve()
            if resolved == resolved_exclude or resolved_exclude in resolved.parents:
                continue
        matches.append(path)
    return natsorted(matches, key=lambda p: p.relative_to(root).parts, alg=ns.IGNORECASE)
