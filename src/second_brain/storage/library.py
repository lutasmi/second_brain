"""Estructura física de la biblioteca: rutas, nombres y particionado.

Las notas se guardan en `<library>/<YYYY>/<MM>/` para que ningún directorio
crezca sin límite (escala a cientos de miles de documentos). Los binarios
van en el subdirectorio `media/` de cada mes, junto a sus notas.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterator

_SLUG_MAX = 60


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:_SLUG_MAX].rstrip("-") or "nota"


def new_note_id(captured_at: datetime) -> str:
    """Identificador único y ordenable: marca de tiempo + sufijo aleatorio."""
    return captured_at.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(2)


def month_dir(library_dir: Path, captured_at: datetime) -> Path:
    return library_dir / captured_at.strftime("%Y") / captured_at.strftime("%m")


def note_path(
    library_dir: Path, captured_at: datetime, note_id: str, slug: str
) -> Path:
    return month_dir(library_dir, captured_at) / f"{note_id}-{slug}.md"


def save_attachment(
    note_file: Path, note_id: str, file_name: str | None, data: bytes
) -> str:
    """Guarda un binario junto a la nota y devuelve su ruta relativa."""
    media = note_file.parent / "media"
    media.mkdir(parents=True, exist_ok=True)
    suffix = Path(file_name).suffix.lower() if file_name else ".bin"
    target = media / f"{note_id}{suffix}"
    target.write_bytes(data)
    return f"media/{target.name}"


def iter_notes(library_dir: Path) -> Iterator[Path]:
    """Recorre todas las notas Markdown de la biblioteca."""
    if not library_dir.exists():
        return
    yield from sorted(library_dir.rglob("*.md"))
