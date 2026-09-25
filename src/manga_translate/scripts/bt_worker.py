"""Runs inside the BallonsTranslator venv (never imported by manga_translate).

Loads the text detector and OCR once, then answers one JSON request per stdin line:
  {"id": 1, "image": "C:/.../page.png"}
  -> {"id": 1, "size": [w, h], "blocks": [{"xyxy": [x1, y1, x2, y2], "vertical": bool, "text": str}]}
  -> {"id": 1, "error": "..."} when that page fails
Usage: python bt_worker.py <engine_root>
"""
import json
import os
import sys
from pathlib import Path


def scan(image, detector, ocr, imread):
    img = imread(image)
    if img is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image}")
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[..., :3]
    _, blocks = detector.detect(img)
    if blocks:
        ocr.run_ocr(img, blocks)
    return {
        "size": [int(img.shape[1]), int(img.shape[0])],
        "blocks": [
            {"xyxy": [int(v) for v in block.xyxy], "vertical": bool(block.vertical), "text": block.get_text()}
            for block in blocks
        ],
    }


def main():
    root = Path(sys.argv[1])
    # The protocol owns the real stdout; anything the engine prints goes to stderr (the worker log).
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    sys.path.insert(0, str(root))
    os.chdir(root)  # the engine finds its models under data/models relative to its root
    from ballontranslator.modules import OCR, TEXTDETECTORS
    from ballontranslator.utils.io_utils import imread

    detector = TEXTDETECTORS.get("ctd").resolve()()
    ocr = OCR.get("manga_ocr").resolve()()
    detector.load_model()
    ocr.load_model()

    def send(message):
        protocol.write(json.dumps(message, ensure_ascii=False) + "\n")
        protocol.flush()

    send({"ready": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request["id"]
            send({"id": request_id, **scan(request["image"], detector, ocr, imread)})
        except Exception as e:
            send({"id": request_id, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
