from second_brain.storage import markdown


def test_render_and_parse_roundtrip(tmp_path):
    frontmatter = {
        "id": "20260702T120000-abcd",
        "type": "text",
        "status": "complete",
        "title": "Título con acentos: año, ñu",
        "tags": ["idea", "producto"],
    }
    content = markdown.render_note(frontmatter, "Título con acentos: año, ñu", "Cuerpo\n\ncon párrafos.")
    path = tmp_path / "nota.md"
    markdown.write_note(path, content)

    parsed_fm, body = markdown.parse_note(path)
    assert parsed_fm == frontmatter
    assert "# Título con acentos: año, ñu" in body
    assert "con párrafos." in body


def test_parse_note_without_frontmatter(tmp_path):
    path = tmp_path / "plano.md"
    path.write_text("solo texto", encoding="utf-8")
    frontmatter, body = markdown.parse_note(path)
    assert frontmatter == {}
    assert body == "solo texto"


def test_write_note_is_atomic_no_tmp_left(tmp_path):
    path = tmp_path / "a" / "b" / "nota.md"
    markdown.write_note(path, "---\nid: x\n---\n\n# T\n")
    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
