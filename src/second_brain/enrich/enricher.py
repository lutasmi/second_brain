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
from second_brain.storage.library import slugify
from second_brain.storage.markdown import ENRICH_END, ENRICH_START

# Versión del esquema de enriquecimiento. Al incrementarla, `second-brain
# enrich` detecta como obsoletas las notas enriquecidas con versiones
# anteriores y las regenera (el contenido original nunca se toca).
ENRICHMENT_VERSION = 3

_ENTITY_KINDS = ("people", "organizations", "technologies", "products", "places")

_CONTENT_TYPES = (
    "articulo",
    "video",
    "audio",
    "hilo-social",
    "idea-propia",
    "imagen",
    "documento",
    "herramienta",
    "referencia",
    "otro",
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {"type": "array", "items": {"type": "string"}},
        "suggested_categories": {"type": "array", "items": {"type": "string"}},
        "content_type": {"type": "string", "enum": list(_CONTENT_TYPES)},
        "summary": {"type": "string"},
        "why_relevant": {"type": "string"},
        "key_ideas": {"type": "array", "items": {"type": "string"}},
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
        "extraction_confidence": {"type": "number"},
        "classification_confidence": {"type": "number"},
    },
    "required": [
        "categories",
        "suggested_categories",
        "content_type",
        "summary",
        "why_relevant",
        "key_ideas",
        "entities",
        "concepts",
        "keywords",
        "related_topics",
        "language",
        "extraction_confidence",
        "classification_confidence",
    ],
    "additionalProperties": False,
}

_PROMPT = """Eres el sistema de enriquecimiento de una biblioteca documental personal
pensada para durar décadas. Su dueño captura todo lo que despierta su
curiosidad; tu trabajo es que cada nota conserve el máximo valor futuro.
Analiza el documento y genera metadatos fieles.

Categorías oficiales de la biblioteca (elige EXCLUSIVAMENTE de esta lista,
usando el slug exacto):
{categories}

Devuelve:
- categories: entre 1 y 4 slugs de la lista oficial que describan la temática
  (las más específicas primero). Nunca inventes categorías aquí.
- suggested_categories: SOLO si el documento pide a gritos una categoría que
  no existe en la lista oficial, propónla aquí (máximo 2; minúsculas,
  singular, con guiones). No repitas ninguna de la lista. Vacío si la lista
  oficial basta — no propongas por proponer.{dismissed_note}
- content_type: qué es este documento, uno de: {content_types}.
- summary: resumen fiel del contenido en español, de 1 a 3 frases, sin opinar.
- why_relevant: responde a "¿por qué este documento debería seguir existiendo
  en esta biblioteca dentro de diez años?" — qué aporta, qué preserva o para
  qué podría servir (1 o 2 frases). Si hay una "Nota del usuario", esa es la
  motivación principal: respétala y compleméntala.
- key_ideas: de 2 a 5 ideas que merece la pena recordar de este contenido.
  No es un resumen: es lo que aporta valor intelectual, según el caso —
  aprendizajes, inspiración, decisiones, hipótesis o contexto esencial
  (frases cortas; si el contenido no da para tanto, menos).
- entities.people / organizations / technologies / products / places:
  nombres propios mencionados en el documento (listas vacías si no hay).
- concepts: de 2 a 6 conceptos o ideas clave del documento (minúsculas).
- keywords: de 3 a 8 palabras clave útiles para búsqueda (minúsculas).
- related_topics: de 2 a 5 temas afines que conectarían este documento con
  otros de la biblioteca (minúsculas).
- language: código ISO 639-1 del idioma principal del contenido.
- extraction_confidence: de 0 a 1, cuánto confías en que el contenido que ves
  está completo y es fiel al original (extracción troceada, OCR ruidoso o
  transcripción dudosa ⇒ baja).
- classification_confidence: de 0 a 1, tu confianza en las categories elegidas.

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

    dismissed_note = ""
    if model.dismissed:
        dismissed_note = (
            " El usuario ya descartó estas propuestas; NO vuelvas a sugerirlas: "
            + ", ".join(model.dismissed)
            + "."
        )
    prompt = _PROMPT.format(
        categories="\n".join(
            f"- {slug} — {desc}" if desc else f"- {slug}"
            for slug, desc in model.categories
        ),
        content_types=", ".join(_CONTENT_TYPES),
        dismissed_note=dismissed_note,
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
    suggested = [slugify(s) for s in _clean_list(data.get("suggested_categories"), 2)]
    suggested = [
        s for s in suggested if s and s not in official and s not in set(model.dismissed)
    ]
    if suggested:
        enrichment["suggested_categories"] = suggested
    content_type = str(data.get("content_type", "")).strip().lower()
    if content_type in _CONTENT_TYPES:
        enrichment["content_type"] = content_type
    why_relevant = str(data.get("why_relevant", "")).strip()
    if why_relevant:
        enrichment["why_relevant"] = why_relevant
    key_ideas = _clean_list(data.get("key_ideas"), 5)
    if key_ideas:
        enrichment["key_ideas"] = key_ideas
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
    for field in ("extraction_confidence", "classification_confidence"):
        try:
            enrichment[field] = round(min(1.0, max(0.0, float(data.get(field)))), 2)
        except (TypeError, ValueError):
            pass

    provider = ai.provider(config)
    enrichment["provider"] = provider
    enrichment["model"] = ai.model_for(config, provider)
    enrichment["enriched_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    enrichment["knowledge_model"] = model.hash
    enrichment["version"] = ENRICHMENT_VERSION
    return enrichment


def _callout(kind: str, title: str, text: str) -> str:
    lines = [f"> [!{kind}]- {title}"]
    lines.extend(f"> {line}" for line in text.splitlines() if line.strip())
    return "\n".join(lines)


def render_section(enrichment: dict) -> str:
    """Sección legible del enriquecimiento para el cuerpo de la nota.

    Va delimitada por marcadores: es 100 % regenerable y el contenido
    original de la nota siempre puede recuperarse eliminándola. Usa
    callouts de Obsidian (en otros visores se leen como citas normales).
    """
    parts: list[str] = [ENRICH_START]
    if enrichment.get("summary"):
        parts.append(_callout("abstract", "Resumen", enrichment["summary"]))
    why = enrichment.get("why_relevant") or enrichment.get("relevance")
    if why:
        parts.append(_callout("quote", "Por qué merece quedarse", why))
    ideas = enrichment.get("key_ideas") or enrichment.get("learnings")
    if ideas:
        bullets = "\n".join(f"- {item}" for item in ideas)
        parts.append(_callout("tip", "Ideas clave", bullets))
    if enrichment.get("suggested_categories"):
        joined = ", ".join(f"`{s}`" for s in enrichment["suggested_categories"])
        parts.append(
            f"_Categorías sugeridas fuera de la taxonomía: {joined} — "
            "añádelas a `knowledge_model.md` si te encajan._"
        )
    parts.append(ENRICH_END)
    return "\n\n".join(parts)
