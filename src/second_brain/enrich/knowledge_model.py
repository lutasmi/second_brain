"""El modelo de conocimiento: la estructura oficial de la biblioteca.

Vive en `<library>/knowledge_model.md` — es un ACTIVO del proyecto, no del
modelo de IA. Define las categorías oficiales con las que se clasifica todo.
Editarlo no requiere tocar código ni prompts: basta ejecutar
`second-brain enrich` y las notas obsoletas se reclasifican (cada nota
registra el hash del modelo con el que fue enriquecida).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_MODEL_FILE = "knowledge_model.md"

_SEED = """# Modelo de conocimiento

Este archivo define la estructura oficial de la biblioteca y es un activo
del proyecto: la IA lo usa como referencia obligatoria para clasificar y
NUNCA inventa categorías fuera de él.

Cómo evolucionarlo:

1. Edita la sección **Categorías** (una por línea: `- slug — descripción`).
   El slug es la etiqueta (minúsculas, guiones); la descripción ayuda a la
   IA a clasificar mejor.
2. Ejecuta `second-brain enrich`: las notas clasificadas con una versión
   anterior del modelo se reclasifican automáticamente.

Solo la sección "Categorías" es leída por el sistema; el resto del archivo
es documentación libre.

## Categorías

- ia — inteligencia artificial, modelos de lenguaje, agentes, automatización
- tecnologia — software, hardware, programación, ingeniería
- producto — diseño y gestión de producto, UX, estrategia de producto
- negocio — emprendimiento, estrategia empresarial, gestión, startups
- marketing — ventas, comunicación, marcas, crecimiento
- finanzas — inversión, economía, dinero personal
- productividad — hábitos, gestión del tiempo, métodos de trabajo
- desarrollo-personal — crecimiento personal, filosofía de vida, motivación
- salud — medicina, nutrición, ejercicio, longevidad
- ciencia — investigación, física, biología, matemáticas
- psicologia — mente, comportamiento, relaciones
- educacion — aprendizaje, enseñanza, divulgación
- historia — pasado, biografías, civilizaciones
- arte — cultura, literatura, música, cine, diseño
- sociedad — política, actualidad, tendencias sociales
- idea-propia — pensamientos e ideas originales propias
"""

_CATEGORY_LINE = re.compile(r"^-\s+([a-z0-9][a-z0-9-]*)\s*(?:[—–:]\s*(.*))?$")


@dataclass(frozen=True)
class KnowledgeModel:
    categories: list[tuple[str, str]]  # (slug, descripción)
    dismissed: list[str]  # categorías que el usuario decidió NO incorporar
    hash: str  # hash corto del archivo: trazabilidad del enriquecimiento

    @property
    def slugs(self) -> list[str]:
        return [slug for slug, _ in self.categories]


def model_path(library_dir: Path) -> Path:
    return library_dir / KNOWLEDGE_MODEL_FILE


def ensure_model(library_dir: Path) -> KnowledgeModel:
    """Carga el modelo de conocimiento, creándolo con la semilla si no existe."""
    path = model_path(library_dir)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_SEED, encoding="utf-8")

    raw = path.read_text(encoding="utf-8")
    categories: list[tuple[str, str]] = []
    dismissed: list[str] = []
    section = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            lowered = stripped.lower()
            if "descartad" in lowered:
                section = "dismissed"
            elif "categor" in lowered:
                section = "categories"
            else:
                section = None
            continue
        match = _CATEGORY_LINE.match(stripped)
        if not match:
            continue
        if section == "categories":
            categories.append((match.group(1), (match.group(2) or "").strip()))
        elif section == "dismissed":
            dismissed.append(match.group(1))

    if not categories:
        raise ValueError(
            f"{path} no contiene categorías válidas en la sección '## Categorías'"
        )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return KnowledgeModel(categories=categories, dismissed=dismissed, hash=digest)


def _valid_slug(slug: str) -> str:
    import re

    slug = slug.strip().lower().lstrip("#")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,29}", slug):
        raise ValueError(
            f"categoría no válida: {slug!r} (usa minúsculas, números y guiones)"
        )
    return slug


def approve_category(library_dir: Path, slug: str, description: str = "") -> None:
    """Añade una categoría a la sección oficial del knowledge model."""
    slug = _valid_slug(slug)
    model = ensure_model(library_dir)
    if slug in model.slugs:
        return
    path = model_path(library_dir)
    lines = path.read_text(encoding="utf-8").splitlines()

    section = None
    last_category_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            lowered = stripped.lower()
            section = "categories" if (
                "categor" in lowered and "descartad" not in lowered
            ) else None
            continue
        if section == "categories" and _CATEGORY_LINE.match(stripped):
            last_category_line = i
    if last_category_line is None:
        raise ValueError(f"{path} no tiene sección '## Categorías'")

    entry = f"- {slug} — {description}" if description else f"- {slug}"
    lines.insert(last_category_line + 1, entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dismiss_category(library_dir: Path, slug: str) -> None:
    """Registra una categoría como descartada (no volverá a proponerse)."""
    slug = _valid_slug(slug)
    model = ensure_model(library_dir)
    if slug in model.dismissed:
        return
    path = model_path(library_dir)
    content = path.read_text(encoding="utf-8").rstrip("\n")
    if not any("descartad" in l.lower() and l.startswith("## ") for l in content.splitlines()):
        content += (
            "\n\n## Descartadas\n\n"
            "Temas que decidiste no incorporar como categoría (el sistema no\n"
            "volverá a proponerlos):\n"
        )
    content += f"\n- {slug}"
    path.write_text(content + "\n", encoding="utf-8")
