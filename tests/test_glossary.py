from manga_viewer.glossary import GlossaryEntry, load_glossary, relevant_entries


def test_load_glossary(tmp_path):
    path = tmp_path / "g.toml"
    path.write_text(
        '[[entry]]\nja = "悟"\nko = "사토루"\nnote = "주인공"\n\n'
        '[[entry]]\nja = "呪術"\nko = "주술"\n',
        encoding="utf-8",
    )
    assert load_glossary(path) == [
        GlossaryEntry("悟", "사토루", "주인공"),
        GlossaryEntry("呪術", "주술", ""),
    ]


def test_relevant_entries_only_returns_terms_on_page():
    entries = [GlossaryEntry("悟", "사토루"), GlossaryEntry("呪術", "주술"), GlossaryEntry("", "빈값")]
    assert relevant_entries(entries, ["悟、行くぞ", "はい"]) == [GlossaryEntry("悟", "사토루")]
