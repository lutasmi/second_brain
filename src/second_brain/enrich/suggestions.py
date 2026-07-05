"""Detector de temas recurrentes sin categoría oficial.

Agrega las `suggested_categories` que el enriquecedor fue dejando en las
notas: cuando un tema se repite lo suficiente, se propone al usuario para
que lo apruebe (pasa a `knowledge_model.md`) o lo descarte (sección
`## Descartadas` del mismo archivo). La estructura de conocimiento crece
con el uso real, pero cada cambio pasa por las manos del usuario.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from second_brain.enrich.knowledge_model import KnowledgeModel
from second_brain.storage import library, markdown

REPORT_THRESHOLD = 3  # repeticiones para avisar proactivamente
LIST_THRESHOLD = 2  # repeticiones para aparecer en /sugerencias


@dataclass(frozen=True)
class Suggestion:
    slug: str
    count: int
    titles: list[str]  # ejemplos de notas que lo sugirieron


def aggregate(
    library_dir: Path, model: KnowledgeModel, threshold: int = LIST_THRESHOLD
) -> list[Suggestion]:
    """Candidatas a nueva categoría, ordenadas por frecuencia."""
    excluded = set(model.slugs) | set(model.dismissed)
    counts: Counter[str] = Counter()
    titles: dict[str, list[str]] = {}

    for path in library.iter_notes(library_dir):
        frontmatter, _ = markdown.parse_note(path)
        if not frontmatter.get("id"):
            continue
        enrichment = frontmatter.get("enrichment") or {}
        for slug in enrichment.get("suggested_categories") or []:
            slug = str(slug).lower()
            if slug in excluded:
                continue
            counts[slug] += 1
            titles.setdefault(slug, [])
            if len(titles[slug]) < 3:
                titles[slug].append(str(frontmatter.get("title", ""))[:60])

    return [
        Suggestion(slug=slug, count=count, titles=titles[slug])
        for slug, count in counts.most_common()
        if count >= threshold
    ]


def report_line(library_dir: Path, model: KnowledgeModel) -> str | None:
    """Línea para el parte diario, solo si hay temas con señal fuerte."""
    strong = aggregate(library_dir, model, threshold=REPORT_THRESHOLD)
    if not strong:
        return None
    listed = ", ".join(f"{s.slug} ({s.count})" for s in strong[:3])
    return f"💡 Temas recurrentes sin categoría: {listed} → /sugerencias"
