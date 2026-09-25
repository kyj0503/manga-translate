from manga_translate.source import find_images


def touch(path):
    path.write_bytes(b"")
    return path


def test_nested_natural_order_across_folders_and_files(tmp_path):
    (tmp_path / "1권").mkdir()
    (tmp_path / "2권").mkdir()
    touch(tmp_path / "1권" / "2.webp")
    touch(tmp_path / "1권" / "10.webp")
    touch(tmp_path / "2권" / "1.webp")
    touch(tmp_path / "cover.webp")

    result = [p.relative_to(tmp_path).as_posix() for p in find_images(tmp_path)]
    assert result == ["1권/2.webp", "1권/10.webp", "2권/1.webp", "cover.webp"]


def test_mixed_case_extensions_and_non_images_ignored(tmp_path):
    touch(tmp_path / "1.JPG")
    touch(tmp_path / "2.WebP")
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "readme.md")

    result = [p.name for p in find_images(tmp_path)]
    assert result == ["1.JPG", "2.WebP"]


def test_hidden_directory_skipped(tmp_path):
    (tmp_path / ".thumbnails").mkdir()
    touch(tmp_path / ".thumbnails" / "1.jpg")
    touch(tmp_path / "cover.jpg")

    result = [p.name for p in find_images(tmp_path)]
    assert result == ["cover.jpg"]


def test_excluded_output_folder_inside_input_skipped(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    touch(out / "1.png")
    touch(tmp_path / "1.jpg")

    result = find_images(tmp_path, exclude=out)
    assert result == [tmp_path / "1.jpg"]


def test_empty_folder(tmp_path):
    assert find_images(tmp_path) == []
