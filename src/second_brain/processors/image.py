"""Procesador de imágenes: guarda el original, aplica OCR y descripción IA.

La imagen ya está persistida en disco cuando este procesador se ejecuta:
si el OCR o la descripción fallan (falta tesseract, falta la clave de la API,
error de red...), la nota queda `pending` y `reprocess` lo reintentará.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from second_brain.models import Capture, ProcessContext, ProcessResult
from second_brain.processors.text import make_title

_DESCRIBE_PROMPT = (
    "Describe esta imagen en español, en un párrafo breve y concreto. "
    "Si contiene un concepto, diagrama o dato, explica qué aporta. "
    "No repitas literalmente el texto visible: eso lo cubre el OCR."
)


def run_ocr(path: Path) -> str:
    """Devuelve el texto visible en la imagen ('' si no hay texto legible)."""
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract no está instalado (macOS: brew install tesseract)")
    import pytesseract
    from PIL import Image

    with Image.open(path) as img:
        try:
            return pytesseract.image_to_string(img, lang="spa+eng").strip()
        except pytesseract.TesseractError:
            return pytesseract.image_to_string(img).strip()


def describe_image(path: Path, config) -> str:
    """Descripción de la imagen con el proveedor de IA configurado."""
    from second_brain import ai

    return ai.describe_image(path, _DESCRIBE_PROMPT, config)


def process(capture: Capture, ctx: ProcessContext) -> ProcessResult:
    caption = (capture.text or "").strip()
    errors: list[str] = []
    extra: dict = {}

    ocr_text: str | None = None
    try:
        ocr_text = run_ocr(ctx.attachment_abs)
        extra["ocr"] = "done" if ocr_text else "empty"
    except Exception as exc:  # noqa: BLE001 — el OCR se reintenta en reprocess
        errors.append(f"ocr: {exc}")

    description: str | None = None
    if ctx.config.ai_descriptions:
        try:
            from second_brain import ai

            description = describe_image(ctx.attachment_abs, ctx.config)
            prov = ai.provider(ctx.config)
            extra["description_model"] = ai.model_for(ctx.config, prov)
        except Exception as exc:  # noqa: BLE001 — la IA se reintenta en reprocess
            errors.append(f"descripcion: {exc}")
    else:
        extra["description"] = "off"

    parts = [f"![imagen]({ctx.attachment_rel})"]
    if caption:
        parts.append(f"## Nota del usuario\n\n{caption}")
    if description:
        parts.append(f"## Descripción\n\n{description}")
    if ocr_text:
        parts.append(f"## Texto extraído (OCR)\n\n{ocr_text}")

    title = make_title(caption, fallback="") or f"Imagen {capture.captured_at:%Y-%m-%d %H:%M}"
    return ProcessResult(
        title=title,
        body="\n\n".join(parts),
        status="pending" if errors else "complete",
        extra=extra,
        errors=errors,
    )
