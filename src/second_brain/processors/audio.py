"""Procesador de audio: transcripción automática de notas de voz.

El audio original ya está persistido cuando este procesador se ejecuta; si
la transcripción falla (sin clave de OpenAI, error de red), la nota queda
`pending` y `reprocess` la reintentará. La transcripción usa la API de audio
de OpenAI (Anthropic no ofrece transcripción).
"""

from second_brain.models import Capture, ProcessContext, ProcessResult
from second_brain.processors.text import make_title


def process(capture: Capture, ctx: ProcessContext) -> ProcessResult:
    from second_brain import ai

    caption = (capture.text or "").strip()
    header = f"[🎙 audio original]({ctx.attachment_rel})"
    try:
        transcript = ai.transcribe_audio(ctx.attachment_abs, ctx.config)
    except Exception as exc:  # noqa: BLE001 — se reintenta en reprocess
        parts = [header]
        if caption:
            parts.append(f"## Nota del usuario\n\n{caption}")
        return ProcessResult(
            title=make_title(caption, fallback="")
            or f"Audio {capture.captured_at:%Y-%m-%d %H:%M}",
            body="\n\n".join(parts),
            status="pending",
            errors=[f"transcripcion: {exc}"],
        )

    parts = [header]
    if caption:
        parts.append(f"## Nota del usuario\n\n{caption}")
    parts.append(f"## Transcripción\n\n{transcript}")
    title = make_title(caption, fallback="") or make_title(
        transcript, fallback=f"Audio {capture.captured_at:%Y-%m-%d %H:%M}"
    )
    return ProcessResult(title=title, body="\n\n".join(parts))
