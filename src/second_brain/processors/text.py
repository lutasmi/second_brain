"""Procesador de texto plano: guarda el mensaje íntegro, sin transformarlo."""

from second_brain.models import Capture, ProcessContext, ProcessResult

_TITLE_MAX = 80


def make_title(text: str, fallback: str = "Nota") -> str:
    """Primera línea no vacía del texto, truncada, como título de la nota."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = first.lstrip("#").strip()
    if not first:
        return fallback
    return first if len(first) <= _TITLE_MAX else first[: _TITLE_MAX - 1] + "…"


def process(capture: Capture, ctx: ProcessContext) -> ProcessResult:
    text = (capture.text or "").strip()
    return ProcessResult(title=make_title(text), body=text)
