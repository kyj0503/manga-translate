"""Stand-in for the engine's module registries, for bt_worker.py tests.

A fake image is a JSON file (see utils/io_utils.py). Its "blocks" become detected blocks and
their "text" is what OCR reads. {"fail": "msg"} makes detection raise; {"crash": true} kills the process.
"""
import os

print("Device name: fake GPU")  # the real engine prints on import; the worker must keep this off its protocol


class _Block:
    def __init__(self, spec):
        self.xyxy = spec["xyxy"]
        self.vertical = spec["vertical"]
        self._ocr_text = spec["text"]
        self.text = []

    def get_text(self):
        return "".join(self.text)


class _Detector:
    def load_model(self):
        pass

    def detect(self, img):
        if img.spec.get("crash"):
            os._exit(3)
        if "fail" in img.spec:
            raise RuntimeError(img.spec["fail"])
        return None, [_Block(b) for b in img.spec.get("blocks", [])]


class _Ocr:
    def load_model(self):
        pass

    def run_ocr(self, img, blocks):
        for block in blocks:
            block.text = [block._ocr_text]
        return blocks


class _Spec:
    def __init__(self, cls):
        self._cls = cls

    def resolve(self):
        return self._cls


class _Registry:
    def __init__(self, entries):
        self._entries = entries

    def get(self, key):
        return _Spec(self._entries[key])


TEXTDETECTORS = _Registry({"ctd": _Detector})
OCR = _Registry({"manga_ocr": _Ocr})
