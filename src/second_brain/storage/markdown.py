"""Lectura y escritura de notas Markdown con frontmatter YAML.

El formato está documentado en docs/FORMAT.md. La escritura es atómica
(fichero temporal + rename) para no dejar nunca notas a medias en disco.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

# Delimitan la sección de enriquecimiento visible dentro del cuerpo.
# Todo lo que hay entre ellos es regenerable; el contenido original de la
# nota es SIEMPRE recuperable eliminando el bloque.
ENRICH_START = "<!-- enriquecimiento:inicio -->"
ENRICH_END = "<!-- enriquecimiento:fin -->"

_ENRICH_BLOCK = re.compile(
    re.escape(ENRICH_START) + r".*?" + re.escape(ENRICH_END) + r"\n*",
    re.DOTALL,
)


def strip_enrichment_section(body: str) -> str:
    """Elimina la sección de enriquecimiento, devolviendo el resto intacto."""
    return _ENRICH_BLOCK.sub("", body).lstrip("\n")


def render_note(frontmatter: dict, title: str, body: str) -> str:
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{fm}\n---\n\n# {title}\n"
    if body.strip():
        content += f"\n{body.strip()}\n"
    return content


def write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def parse_note(path: Path) -> tuple[dict, str]:
    """Devuelve (frontmatter, cuerpo). Tolerante con notas sin frontmatter."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end == -1:
        return {}, raw
    frontmatter = yaml.safe_load(raw[4:end]) or {}
    body = raw[end + 5 :].lstrip("\n")
    return frontmatter, body
