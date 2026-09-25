from manga_translate.source import list_images


def touch(path):
    path.write_bytes(b"")
    return path


def test_natural_sort_and_filtering(tmp_path):
    for name in ["10.jpg", "2.png", "1.JPG", "notes.txt", "cover.webp"]:
        touch(tmp_path / name)
    (tmp_path / "sub").mkdir()
    touch(tmp_path / "sub" / "0.jpg")

    assert [p.name for p in list_images(tmp_path)] == ["1.JPG", "2.png", "10.jpg", "cover.webp"]


def test_empty_folder(tmp_path):
    assert list_images(tmp_path) == []
