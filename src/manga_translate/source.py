from __future__ import annotations

from pathlib import Path

from natsort import natsorted, ns

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})


def list_images(folder: Path) -> list[Path]:
    """Image files directly inside ``folder``, naturally sorted (2.jpg before 10.jpg)."""
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    return natsorted(files, key=lambda p: p.name, alg=ns.IGNORECASE)
