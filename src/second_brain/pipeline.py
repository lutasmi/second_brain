"""Núcleo del sistema: convierte capturas en notas Markdown.

Garantías:
- Ninguna captura se pierde: si el procesador falla, la nota se escribe
  igualmente con lo que haya y queda en estado `pending`.
- Los adjuntos se guardan en disco ANTES de intentar el enriquecimiento.
- `reprocess()` reintenta las notas pendientes sin perder id ni metadatos;
  con `include_complete=True` re-enriquece toda la biblioteca.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from second_brain.config import Config
from second_brain.models import Capture, ProcessContext, ProcessOutcome, ProcessResult
from second_brain.processors import get_processor
from second_brain.storage import library, markdown

SCHEMA_VERSION = 1

_HASHTAG_RE = re.compile(r"#([\wáéíóúñü]+)", re.IGNORECASE)


def _hashtags(text: str | None) -> list[str]:
    if not text:
        return []
    return sorted({t.lower() for t in _HASHTAG_RE.findall(text)})


def _slug_source(capture: Capture) -> str:
    if capture.kind == "url" and capture.url:
        return urlparse(capture.url).hostname or "enlace"
    if capture.kind == "image":
        return capture.text or capture.file_name or "imagen"
    return capture.text or "nota"


def _strip_title_heading(body: str) -> str:
    """Quita el `# título` inicial del cuerpo para recuperar el texto original."""
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


class Pipeline:
    def __init__(self, config: Config):
        self.config = config

    # ------------------------------------------------------------------ #
    # Captura nueva                                                       #
    # ------------------------------------------------------------------ #
    def process(self, capture: Capture) -> ProcessOutcome:
        note_id = library.new_note_id(capture.captured_at)
        slug = library.slugify(_slug_source(capture)[:80])
        path = library.note_path(
            self.config.library_dir, capture.captured_at, note_id, slug
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        ctx = ProcessContext(config=self.config)
        if capture.file_bytes is not None:
            rel = library.save_attachment(
                path, note_id, capture.file_name, capture.file_bytes
            )
            ctx.attachment_rel = rel
            ctx.attachment_abs = path.parent / rel

        result = self._run_processor(capture, ctx)
        self._apply_enrichment(result)
        frontmatter = self._frontmatter(note_id, capture, ctx, result)
        markdown.write_note(
            path, markdown.render_note(frontmatter, result.title, result.body)
        )
        return ProcessOutcome(path=path, status=result.status, title=result.title)

    # ------------------------------------------------------------------ #
    # Reintento / re-enriquecimiento                                      #
    # ------------------------------------------------------------------ #
    def reprocess(self, include_complete: bool = False) -> list[ProcessOutcome]:
        outcomes = []
        for path in library.iter_notes(self.config.library_dir):
            frontmatter, body = markdown.parse_note(path)
            if not frontmatter.get("id"):
                continue  # no es una nota del sistema (p. ej. taxonomia.md)
            if not include_complete and frontmatter.get("status") != "pending":
                continue
            outcomes.append(self.reprocess_note(path, frontmatter, body))
        return outcomes

    def reprocess_note(
        self, path: Path, frontmatter: dict | None = None, body: str | None = None
    ) -> ProcessOutcome:
        if frontmatter is None or body is None:
            frontmatter, body = markdown.parse_note(path)
        capture = self._capture_from_frontmatter(frontmatter, body)

        ctx = ProcessContext(config=self.config)
        attachments = frontmatter.get("attachments") or []
        if attachments:
            ctx.attachment_rel = attachments[0]
            ctx.attachment_abs = path.parent / attachments[0]

        result = self._run_processor(capture, ctx)
        self._apply_enrichment(result)
        new_frontmatter = self._frontmatter(
            str(frontmatter["id"]), capture, ctx, result
        )
        markdown.write_note(
            path, markdown.render_note(new_frontmatter, result.title, result.body)
        )
        return ProcessOutcome(path=path, status=result.status, title=result.title)

    # ------------------------------------------------------------------ #
    # Internos                                                            #
    # ------------------------------------------------------------------ #
    def _run_processor(self, capture: Capture, ctx: ProcessContext) -> ProcessResult:
        try:
            return get_processor(capture.kind)(capture, ctx)
        except Exception as exc:  # noqa: BLE001 — nunca perder la captura
            return self._fallback_result(capture, ctx, exc)

    def _apply_enrichment(self, result: ProcessResult) -> None:
        """Enriquecimiento IA (solo notas completas). Su fallo nunca bloquea
        la captura: queda registrado y `second-brain enrich` lo reintenta."""
        from second_brain import ai

        if (
            not self.config.ai_enrich
            or ai.provider(self.config) is None
            or result.status != "complete"
        ):
            return
        try:
            from second_brain.enrich import enricher, knowledge_model

            model = knowledge_model.ensure_model(self.config.library_dir)
            result.extra["enrichment"] = enricher.enrich(
                result.title, result.body, model, self.config
            )
            result.extra.pop("enrichment_error", None)
        except Exception as exc:  # noqa: BLE001 — se reintenta con `enrich`
            result.extra["enrichment_error"] = str(exc)

    def enrich_library(self, force: bool = False) -> list[tuple[Path, str]]:
        """(Re)enriquece las notas SIN volver a extraer su contenido.

        Enriquece las notas completas que no tienen enriquecimiento o cuyo
        enriquecimiento se hizo con una versión anterior del modelo de
        conocimiento. Con `force`, re-enriquece todas. El cuerpo de la nota
        (contenido original) no se toca jamás.
        """
        from second_brain import ai
        from second_brain.enrich import enricher, knowledge_model

        if ai.provider(self.config) is None:
            raise RuntimeError(
                "sin clave de IA configurada (OPENAI_API_KEY o ANTHROPIC_API_KEY)"
            )
        model = knowledge_model.ensure_model(self.config.library_dir)

        outcomes: list[tuple[Path, str]] = []
        for path in library.iter_notes(self.config.library_dir):
            frontmatter, body = markdown.parse_note(path)
            if not frontmatter.get("id") or frontmatter.get("status") != "complete":
                continue
            existing = frontmatter.get("enrichment") or {}
            if not force and existing.get("knowledge_model") == model.hash:
                continue

            title = str(frontmatter.get("title", ""))
            content = _strip_title_heading(body)
            try:
                frontmatter["enrichment"] = enricher.enrich(
                    title, content, model, self.config
                )
                frontmatter.pop("enrichment_error", None)
                user_text = (
                    frontmatter.get("caption")
                    if frontmatter.get("type") == "image"
                    else content if frontmatter.get("type") == "text" else None
                )
                frontmatter["tags"] = sorted(
                    set(_hashtags(user_text))
                    | set(frontmatter["enrichment"].get("categories", []))
                )
                status = "enriched"
            except Exception as exc:  # noqa: BLE001
                frontmatter["enrichment_error"] = str(exc)
                status = "error"
            markdown.write_note(path, markdown.render_note(frontmatter, title, content))
            outcomes.append((path, status))
        return outcomes

    @staticmethod
    def _fallback_result(
        capture: Capture, ctx: ProcessContext, exc: Exception
    ) -> ProcessResult:
        parts = []
        if capture.url:
            parts.append(f"> Fuente: <{capture.url}>")
        if ctx.attachment_rel:
            parts.append(f"![imagen]({ctx.attachment_rel})")
        if capture.text:
            parts.append(capture.text)
        title = capture.url or capture.text or capture.file_name or "Captura"
        return ProcessResult(
            title=str(title)[:80],
            body="\n\n".join(parts),
            status="pending",
            errors=[f"procesador: {exc}"],
        )

    def _frontmatter(
        self, note_id: str, capture: Capture, ctx: ProcessContext, result: ProcessResult
    ) -> dict:
        categories = (result.extra.get("enrichment") or {}).get("categories", [])
        fm: dict = {
            "id": note_id,
            "type": capture.kind,
            "source": capture.source,
            "captured_at": capture.captured_at.isoformat(timespec="seconds"),
            "status": result.status,
            "title": result.title,
            "tags": sorted(set(_hashtags(capture.text)) | set(categories)),
        }
        if capture.url:
            fm["url"] = capture.url
        if ctx.attachment_rel:
            fm["attachments"] = [ctx.attachment_rel]
        if capture.kind == "image" and capture.text:
            fm["caption"] = capture.text
        fm.update(result.extra)
        if capture.metadata:
            fm[capture.source] = capture.metadata
        if result.errors:
            fm["errors"] = result.errors
        fm["schema"] = SCHEMA_VERSION
        return fm

    def _capture_from_frontmatter(self, fm: dict, body: str) -> Capture:
        source = str(fm.get("source", "unknown"))
        kind = str(fm.get("type", "text"))
        captured_at = fm["captured_at"]
        if not isinstance(captured_at, datetime):
            captured_at = datetime.fromisoformat(str(captured_at))
        if kind == "image":
            text = fm.get("caption")
        elif kind == "text":
            text = _strip_title_heading(body)
        else:
            text = None
        return Capture(
            kind=kind,
            source=source,
            captured_at=captured_at,
            text=text,
            url=fm.get("url"),
            metadata=fm.get(source) or {},
        )
