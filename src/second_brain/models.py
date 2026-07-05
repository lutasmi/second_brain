"""Modelos de datos compartidos por todo el sistema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Capture:
    """Una captura entrante, tal y como llega desde una fuente.

    Es el contrato entre las fuentes (Telegram, CLI, ...) y el pipeline:
    añadir una fuente nueva consiste únicamente en construir Captures.
    """

    kind: str  # "text" | "url" | "image"
    source: str  # "telegram" | "cli" | ...
    captured_at: datetime
    text: str | None = None  # texto del mensaje o caption de la imagen
    url: str | None = None  # solo kind == "url"
    file_bytes: bytes | None = None  # solo kind == "image"
    file_name: str | None = None
    metadata: dict = field(default_factory=dict)  # datos propios de la fuente


@dataclass
class ProcessResult:
    """Resultado de procesar una captura: contenido listo para el Markdown."""

    title: str
    body: str  # cuerpo markdown, sin el título H1
    status: str = "complete"  # "complete" | "pending"
    extra: dict = field(default_factory=dict)  # frontmatter adicional
    errors: list[str] = field(default_factory=list)


@dataclass
class ProcessContext:
    """Contexto que el pipeline entrega a los procesadores."""

    config: object
    attachment_rel: str | None = None  # ruta del adjunto relativa a la nota
    attachment_abs: Path | None = None  # ruta absoluta del adjunto


@dataclass
class ProcessOutcome:
    """Resultado final de una captura ya persistida en disco."""

    path: Path
    status: str
    title: str
