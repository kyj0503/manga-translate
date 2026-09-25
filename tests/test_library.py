from pathlib import Path

from manga_translate.library import Book, is_inside, scan_library


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_each_folder_with_images_is_a_book(tmp_path):
    root = tmp_path / "만화"
    touch(root / "표지.png")
    touch(root / "1권" / "2.webp")
    touch(root / "1권" / "10.webp")
    touch(root / "1권" / "메모.txt")
    touch(root / "2권" / "001.jpg")
    (root / "빈 폴더").mkdir()
    touch(root / ".숨김" / "a.png")

    books = scan_library(root)

    assert [b.title for b in books] == ["1권", "2권", "만화"]
    assert [b.id for b in books] == [0, 1, 2]
    assert books[0] == Book(0, "1권", root / "1권", (root / "1권" / "2.webp", root / "1권" / "10.webp"))
    assert books[2].pages == (root / "표지.png",)


def test_nested_title_uses_posix_relative_path(tmp_path):
    touch(tmp_path / "시리즈" / "1권" / "a.png")
    [book] = scan_library(tmp_path)
    assert book.title == "시리즈/1권"


def test_empty_folder_has_no_books(tmp_path):
    assert scan_library(tmp_path) == []


def test_is_inside(tmp_path):
    root = tmp_path / "root"
    inside = touch(root / "a" / "b.png")
    outside = touch(tmp_path / "other.png")
    assert is_inside(root, inside)
    assert is_inside(root, root)
    assert not is_inside(root, outside)
    assert not is_inside(root, root / ".." / "other.png")
