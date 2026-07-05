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
    in_categories = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_categories = "categor" in stripped.lower()
            continue
        if not in_categories:
            continue
        match = _CATEGORY_LINE.match(stripped)
        if match:
            categories.append((match.group(1), (match.group(2) or "").strip()))

    if not categories:
        raise ValueError(
            f"{path} no contiene categorías válidas en la sección '## Categorías'"
        )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return KnowledgeModel(categories=categories, hash=digest)
