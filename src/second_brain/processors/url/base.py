"""Tipos comunes para los extractores de URLs."""

from dataclasses import dataclass, field


class ExtractionError(Exception):
    """La extracción falló; la nota quedará pendiente de reintento."""


@dataclass
class Extraction:
    title: str | None
    content: str | None  # markdown
    meta: dict = field(default_factory=dict)
