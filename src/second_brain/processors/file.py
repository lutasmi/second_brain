"""Procesador comodín para tipos de archivo aún no soportados.

Cumple el principio de nunca perder una captura: el binario se guarda junto
a la nota y esta queda `pending`. Cuando exista un procesador real para el
tipo (vídeo, epub...), `reprocess` completará estas notas.
"""

from second_brain.models import Capture, ProcessContext, ProcessResult
from second_brain.processors.text import make_title


def process(capture: Capture, ctx: ProcessContext) -> ProcessResult:
    caption = (capture.text or "").strip()
    kind = capture.mime_type or "desconocido"
    parts = []
    if ctx.attachment_rel:
        parts.append(f"[📎 archivo original]({ctx.attachment_rel})")
    if caption:
        parts.append(f"## Nota del usuario\n\n{caption}")
    title = (
        make_title(caption, fallback="")
        or capture.file_name
        or f"Archivo {capture.captured_at:%Y-%m-%d %H:%M}"
    )
    return ProcessResult(
        title=str(title)[:80],
        body="\n\n".join(parts),
        status="pending",
        extra={"mime": kind},
        errors=[f"archivo: tipo aún no soportado ({kind})"],
    )
