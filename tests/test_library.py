from datetime import datetime
from pathlib import Path

from second_brain.storage import library


def test_slugify():
    assert library.slugify("Hola, Mundo! Ñoño") == "hola-mundo-nono"
    assert library.slugify("   ") == "nota"
    assert len(library.slugify("x" * 500)) <= 60


def test_note_path_sharded_by_month(tmp_path):
    dt = datetime(2026, 7, 2, 15, 30, 1)
    path = library.note_path(tmp_path, dt, "20260702T153001-ab12", "hola")
    assert path == tmp_path / "2026" / "07" / "20260702T153001-ab12-hola.md"


def test_new_note_id_format():
    dt = datetime(2026, 7, 2, 15, 30, 1)
    nid = library.new_note_id(dt)
    assert nid.startswith("20260702T153001-")
    assert len(nid.split("-")[1]) == 4


def test_save_attachment(tmp_path):
    note = tmp_path / "2026" / "07" / "nota.md"
    note.parent.mkdir(parents=True)
    rel = library.save_attachment(note, "id123", "foto.JPG", b"bytes")
    assert rel == "media/id123.jpg"
    assert (note.parent / rel).read_bytes() == b"bytes"


def test_iter_notes_skips_non_md(tmp_path):
    (tmp_path / "2026" / "07" / "media").mkdir(parents=True)
    (tmp_path / "2026" / "07" / "a.md").write_text("x")
    (tmp_path / "2026" / "07" / "media" / "img.jpg").write_bytes(b"j")
    notes = list(library.iter_notes(tmp_path))
    assert [p.name for p in notes] == ["a.md"]
