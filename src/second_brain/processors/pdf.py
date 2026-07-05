"""Procesador de PDFs: extracción de texto con pypdf.

PDFs escaneados (sin capa de texto) quedan `pending` a la espera de OCR de
documentos (futuro). El PDF original siempre se conserva junto a la nota.
"""

from pathlib import Path

from second_brain.models import Capture, ProcessContext, ProcessResult
from second_brain.processors.text import make_title


def extract_text(path: Path) -> tuple[str, int, str | None]:
    """Devuelve (texto, nº de páginas, título de los metadatos del PDF)."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)
    meta_title = None
    if reader.metadata and reader.metadata.title:
        meta_title = str(reader.metadata.title).strip() or None
    return text.strip(), len(reader.pages), meta_title


def process(capture: Capture, ctx: ProcessContext) -> ProcessResult:
    caption = (capture.text or "").strip()
    header = f"[📄 PDF original]({ctx.attachment_rel})"
    fallback_title = (
        make_title(caption, fallback="")
        or (Path(capture.file_name).stem if capture.file_name else "")
        or f"PDF {capture.captured_at:%Y-%m-%d %H:%M}"
    )

    try:
        text, pages, meta_title = extract_text(ctx.attachment_abs)
    except Exception as exc:  # noqa: BLE001 — se reintenta en reprocess
        return ProcessResult(
            title=fallback_title,
            body=header,
            status="pending",
            errors=[f"pdf: {exc}"],
        )

    if not text:
        return ProcessResult(
            title=fallback_title,
            body=f"{header}\n\n_PDF sin capa de texto (¿escaneado?); pendiente de OCR._",
            status="pending",
            extra={"pages": pages},
            errors=["pdf: sin capa de texto (OCR de documentos no soportado todavía)"],
        )

    parts = [header]
    if caption:
        parts.append(f"## Nota del usuario\n\n{caption}")
    parts.append(text)
    return ProcessResult(
        title=meta_title or fallback_title,
        body="\n\n".join(parts),
        extra={"pages": pages},
    )
