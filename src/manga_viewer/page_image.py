from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

# Long-side cap before sending a page to the LLM; bounds image tokens and VRAM.
MAX_SIDE = 1024


def image_data_url(path: Path, max_side: int = MAX_SIDE) -> str:
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
