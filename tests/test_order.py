from manga_viewer.order import sort_reading_order
from manga_viewer.types import TextBlock


def block(name, box):
    return TextBlock(id=-1, box=box, vertical=True, ja=name)


def names(blocks):
    return [b.ja for b in blocks]


def test_empty():
    assert sort_reading_order([]) == []


def test_same_row_right_to_left():
    left = block("left", (0, 0, 100, 100))
    right = block("right", (200, 0, 300, 100))
    assert names(sort_reading_order([left, right])) == ["right", "left"]


def test_rows_top_to_bottom():
    top = block("top", (0, 0, 100, 100))
    bottom = block("bottom", (0, 200, 100, 300))
    assert names(sort_reading_order([bottom, top])) == ["top", "bottom"]


def test_grid():
    blocks = [
        block("BL", (0, 200, 100, 300)),
        block("TL", (0, 0, 100, 100)),
        block("BR", (200, 200, 300, 300)),
        block("TR", (200, 0, 300, 100)),
    ]
    assert names(sort_reading_order(blocks)) == ["TR", "TL", "BR", "BL"]


def test_slightly_offset_blocks_share_a_row():
    left = block("left", (0, 10, 100, 110))
    right = block("right", (200, 0, 300, 100))
    assert names(sort_reading_order([left, right])) == ["right", "left"]


def test_ids_are_reassigned_in_order():
    blocks = [block("a", (0, 0, 100, 100)), block("b", (200, 0, 300, 100))]
    assert [b.id for b in sort_reading_order(blocks)] == [0, 1]
