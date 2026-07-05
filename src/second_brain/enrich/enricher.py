"""Enriquecimiento estructurado de notas.

Dado el contenido original de una nota y el modelo de conocimiento oficial,
genera metadatos estructurados: categorías (SOLO de la taxonomía oficial),
resumen, entidades, conceptos, palabras clave, temas relacionados, idioma y
confianza. Todo va al frontmatter: el contenido original nunca se toca y el
enriquecimiento puede regenerarse por completo en cualquier momento.
"""

from __future__ import annotations

from datetime import datetime

from second_brain.enrich.knowledge_model import KnowledgeModel

_ENTITY_KINDS = ("people", "organizations", "technologies", "products", "places")

_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "entities": {
            "type": "object",
            "properties": {
                kind: {"type": "array", "items": {"type": "string"}}
                for kind in _ENTITY_KINDS
            },
            "required": list(_ENTITY_KINDS),
            "additionalProperties": False,
        },
        "concepts": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "related_topics": {"type": "array", "items": {"type": "string"}},
        "language": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "categories",
        "summary",
        "entities",
        "concepts",
        "keywords",
        "related_topics",
        "language",
        "confidence",
    ],
    "additionalProperties": False,
}

_PROMPT = """Eres el sistema de enriquecimiento de una biblioteca documental personal
pensada para durar décadas. Analiza el documento y genera metadatos fieles.

Categorías oficiales de la biblioteca (elige EXCLUSIVAMENTE de esta lista,
usando el slug exacto):
{categories}

Devuelve:
- categories: entre 1 y 4 slugs de la lista oficial que describan la temática
  (las más específicas primero). Nunca inventes categorías.
- summary: resumen fiel del contenido en español, de 1 a 3 frases, sin opinar.
- entities.people / organizations / technologies / products / places:
  nombres propios mencionados en el documento (listas vacías si no hay).
- concepts: de 2 a 6 conceptos o ideas clave del documento (minúsculas).
- keywords: de 3 a 8 palabras clave útiles para búsqueda (minúsculas).
- related_topics: de 2 a 5 temas afines que conectarían este documento con
  otros de la biblioteca (minúsculas).
- language: código ISO 639-1 del idioma principal del contenido.
- confidence: tu confianza en la clasificación de categories, de 0 a 1.

Documento
=========
Título: {title}

Contenido:
{body}"""


def _clean_list(values, limit: int) -> list[str]:
    seen, out = set(), []
    for value in values or []:
        text = str(value).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
        if len(out) >= limit:
            break
    return out


def enrich(title: str, body: str, model: KnowledgeModel, config) -> dict:
    """Enriquece un documento. Devuelve el bloque `enrichment` completo."""
    from second_brain import ai

    prompt = _PROMPT.format(
        categories="\n".join(
            f"- {slug} — {desc}" if desc else f"- {slug}"
            for slug, desc in model.categories
        ),
        title=title,
        body=body[:8000],
    )
    data = ai.classify_json(prompt, _SCHEMA, config)

    official = set(model.slugs)
    categories = [c.lower() for c in data.get("categories", []) if c.lower() in official]

    enrichment: dict = {
        "categories": categories[:4],
        "summary": str(data.get("summary", "")).strip(),
    }
    entities = {
        kind: _clean_list((data.get("entities") or {}).get(kind), 10)
        for kind in _ENTITY_KINDS
    }
    entities = {k: v for k, v in entities.items() if v}
    if entities:
        enrichment["entities"] = entities
    for field, limit in (("concepts", 6), ("keywords", 8), ("related_topics", 5)):
        values = _clean_list(data.get(field), limit)
        if values:
            enrichment[field] = [v.lower() for v in values]

    language = str(data.get("language", "")).strip().lower()[:5]
    if language:
        enrichment["language"] = language
    try:
        enrichment["confidence"] = round(min(1.0, max(0.0, float(data.get("confidence")))), 2)
    except (TypeError, ValueError):
        pass

    provider = ai.provider(config)
    enrichment["provider"] = provider
    enrichment["model"] = ai.model_for(config, provider)
    enrichment["enriched_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    enrichment["knowledge_model"] = model.hash
    return enrichment
