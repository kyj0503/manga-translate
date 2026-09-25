import base64
import io

from PIL import Image

from manga_viewer.page_image import image_data_url


def decode(url):
    header, data = url.split(",", 1)
    assert header == "data:image/jpeg;base64"
    return Image.open(io.BytesIO(base64.b64decode(data)))


def test_large_image_is_downscaled_keeping_aspect(tmp_path):
    path = tmp_path / "p.png"
    Image.new("RGB", (1500, 3000), "white").save(path)
    img = decode(image_data_url(path, max_side=1000))
    assert img.size == (500, 1000)


def test_small_image_keeps_size_and_converts_mode(tmp_path):
    path = tmp_path / "p.png"
    Image.new("L", (300, 200), 128).save(path)
    img = decode(image_data_url(path))
    assert img.size == (300, 200)
    assert img.mode == "RGB"
