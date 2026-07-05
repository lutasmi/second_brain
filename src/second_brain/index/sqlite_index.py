"""Índice de búsqueda sobre SQLite FTS5.

El índice es un artefacto derivado: puede borrarse en cualquier momento y
regenerarse por completo leyendo los Markdown (`second-brain index`).
Nunca contiene información que no exista ya en la biblioteca.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from second_brain.storage import library, markdown


def db_path(library_dir: Path) -> Path:
    return library_dir / ".index" / "notes.db"


def _enrichment_text(enrichment: dict) -> str:
    """Aplana el bloque de enriquecimiento para indexarlo como texto."""
    parts: list[str] = [str(enrichment.get("summary", ""))]
    for field in ("concepts", "keywords", "related_topics"):
        parts.extend(enrichment.get(field) or [])
    for values in (enrichment.get("entities") or {}).values():
        parts.extend(values or [])
    return " ".join(p for p in parts if p)


def rebuild(library_dir: Path) -> int:
    """Reconstruye el índice completo desde los Markdown. Devuelve nº de notas."""
    path = db_path(library_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    con = sqlite3.connect(path)
    con.execute(
        "CREATE VIRTUAL TABLE notes USING "
        "fts5(path UNINDEXED, type UNINDEXED, title, url, tags, body, enrichment)"
    )
    count = 0
    with con:
        for note in library.iter_notes(library_dir):
            frontmatter, body = markdown.parse_note(note)
            con.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(note.relative_to(library_dir)),
                    str(frontmatter.get("type", "")),
                    str(frontmatter.get("title", "")),
                    str(frontmatter.get("url", "")),
                    " ".join(frontmatter.get("tags") or []),
                    body,
                    _enrichment_text(frontmatter.get("enrichment") or {}),
                ),
            )
            count += 1
    con.close()
    return count


def search(library_dir: Path, query: str, limit: int = 10) -> list[dict]:
    path = db_path(library_dir)
    if not path.exists():
        raise FileNotFoundError(
            "No hay índice; ejecuta `second-brain index` primero."
        )
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT path, type, title, snippet(notes, 5, '**', '**', '…', 12) "
            "FROM notes WHERE notes MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
    finally:
        con.close()
    return [
        {"path": r[0], "type": r[1], "title": r[2], "snippet": r[3]} for r in rows
    ]
