import numpy as np

from manga_viewer.background import border_median_color


def test_white_bubble_with_black_text_is_white():
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    image[40:60, 40:60] = 0  # "text" inside the box
    assert border_median_color(image, (20, 20, 80, 80)) == (255, 255, 255)


def test_uniform_gray():
    image = np.full((50, 50, 3), 128, dtype=np.uint8)
    assert border_median_color(image, (5, 5, 45, 45)) == (128, 128, 128)


def test_colored_background():
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    image[:, :] = (250, 230, 200)
    assert border_median_color(image, (10, 10, 40, 40)) == (250, 230, 200)


def test_box_outside_image_is_clamped():
    image = np.full((30, 30, 3), 200, dtype=np.uint8)
    assert border_median_color(image, (-10, -10, 100, 100)) == (200, 200, 200)


def test_degenerate_box_does_not_crash():
    image = np.full((30, 30, 3), 10, dtype=np.uint8)
    assert border_median_color(image, (15, 15, 15, 15)) == (10, 10, 10)
