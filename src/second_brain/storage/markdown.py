"""Lectura y escritura de notas Markdown con frontmatter YAML.

El formato está documentado en docs/FORMAT.md. La escritura es atómica
(fichero temporal + rename) para no dejar nunca notas a medias en disco.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


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
