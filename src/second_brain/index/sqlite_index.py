"""Índice de búsqueda sobre SQLite FTS5.

El índice es un artefacto derivado: puede borrarse en cualquier momento y
regenerarse por completo leyendo los Markdown (`second-brain index`).
Nunca contiene información que no exista ya en la biblioteca.

El pipeline lo mantiene fresco con `upsert()` tras cada escritura, lo que
habilita la deduplicación de URLs y las relaciones entre notas; si no
existe, esas funciones simplemente se omiten.
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


def _row(note: Path, library_dir: Path, frontmatter: dict, body: str) -> tuple:
    return (
        str(note.relative_to(library_dir)),
        str(frontmatter.get("type", "")),
        str(frontmatter.get("title", "")),
        str(frontmatter.get("url", "")),
        " ".join(frontmatter.get("tags") or []),
        body,
        _enrichment_text(frontmatter.get("enrichment") or {}),
    )


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
            if not frontmatter.get("id"):
                continue  # no es una nota del sistema (p. ej. knowledge_model.md)
            con.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                _row(note, library_dir, frontmatter, body),
            )
            count += 1
    con.close()
    return count


def upsert(library_dir: Path, note: Path) -> None:
    """Actualiza una nota en el índice si el índice existe (si no, no-op)."""
    path = db_path(library_dir)
    if not path.exists():
        return
    frontmatter, body = markdown.parse_note(note)
    if not frontmatter.get("id"):
        return
    rel = str(note.relative_to(library_dir))
    con = sqlite3.connect(path)
    try:
        with con:
            con.execute("DELETE FROM notes WHERE path = ?", (rel,))
            con.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                _row(note, library_dir, frontmatter, body),
            )
    finally:
        con.close()


def find_by_url(library_dir: Path, url: str) -> dict | None:
    """Busca una nota ya capturada con esa URL exacta (para deduplicar)."""
    path = db_path(library_dir)
    if not path.exists() or not url:
        return None
    con = sqlite3.connect(path)
    try:
        row = con.execute(
            "SELECT path, title FROM notes WHERE url = ? LIMIT 1", (url,)
        ).fetchone()
    finally:
        con.close()
    return {"path": row[0], "title": row[1]} if row else None


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


def safe_query(text: str) -> str:
    """Convierte texto libre del usuario en una consulta FTS5 segura."""
    import re

    tokens = re.findall(r"\w+", text, re.UNICODE)
    return " ".join(f'"{t}"' for t in tokens) or '""'
