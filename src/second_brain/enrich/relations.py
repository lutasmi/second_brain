"""Relaciones entre notas por etiquetas compartidas.

Genera enlaces wikilink de Obsidian (`[[fichero|Título]]`) hacia las notas
que comparten más etiquetas. Se guardan en el campo `related` del
frontmatter — Obsidian los reconoce como enlaces reales (aristas en el
grafo y backlinks) sin tocar el contenido original de la nota.

Usa el índice SQLite (siempre fresco gracias al upsert del pipeline); si el
índice no existe, simplemente no hay relaciones — nada se rompe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def related_wikilinks(
    library_dir: Path, tags: list[str], exclude_rel: str, limit: int = 5
) -> list[str]:
    if not tags:
        return []
    from second_brain.index import sqlite_index

    db = sqlite_index.db_path(library_dir)
    if not db.exists():
        return []

    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT path, title, tags FROM notes").fetchall()
    finally:
        con.close()

    tag_set = set(tags)
    scored: list[tuple[int, str, str]] = []
    for path, title, note_tags in rows:
        if path == exclude_rel:
            continue
        overlap = len(tag_set & set((note_tags or "").split()))
        if overlap:
            scored.append((overlap, path, title))
    # más etiquetas en común primero; a igualdad, la nota más reciente
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    links = []
    for _, path, title in scored[:limit]:
        stem = Path(path).stem
        safe_title = str(title).replace("|", "/").replace("]", ")").strip()[:80]
        links.append(f"[[{stem}|{safe_title}]]" if safe_title else f"[[{stem}]]")
    return links
