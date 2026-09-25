"""Stand-in for the engine's imread: a fake image is a JSON file {"size": [w, h], "blocks": [...]}."""
import json
import os


class FakeImage:
    ndim = 3

    def __init__(self, spec):
        self.spec = spec
        width, height = spec.get("size", [1, 1])
        self.shape = (height, width, 3)


def imread(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return FakeImage(json.load(f))
