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


_ATTACHMENT_KINDS = {"image", "audio", "pdf", "file"}

# Origen real del contenido (content_source), distinto de la vía de captura
# (source: telegram/cli/...). Determinista y por tanto siempre regenerable.
_CONTENT_SOURCES = {
    "text": "nota-personal",
    "image": "imagen",
    "audio": "nota-de-voz",
    "pdf": "documento",
    "file": "archivo",
}


def _content_source(kind: str, url_type: str | None) -> str:
    if kind == "url":
        return url_type or "web"
    return _CONTENT_SOURCES.get(kind, "desconocido")


def _slug_source(capture: Capture) -> str:
    if capture.kind == "url" and capture.url:
        return urlparse(capture.url).hostname or "enlace"
    if capture.kind in _ATTACHMENT_KINDS:
        return capture.text or capture.file_name or capture.kind
    return capture.text or "nota"


def _strip_title_heading(body: str) -> str:
    """Quita el `# título` inicial del cuerpo para recuperar el texto original."""
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _original_content(body: str) -> str:
    """Contenido original de una nota: sin título ni sección de enriquecimiento."""
    return markdown.strip_enrichment_section(_strip_title_heading(body)).strip()


def _body_with_section(result_body: str, enrichment: dict | None) -> str:
    """Antepone la sección legible de enriquecimiento al contenido original."""
    if not enrichment:
        return result_body
    from second_brain.enrich import enricher

    section = enricher.render_section(enrichment)
    return f"{section}\n\n{result_body}" if result_body.strip() else section


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
        self._apply_relations(frontmatter, path)
        body = _body_with_section(result.body, frontmatter.get("enrichment"))
        markdown.write_note(path, markdown.render_note(frontmatter, result.title, body))
        self._update_index(path)
        return ProcessOutcome(path=path, status=result.status, title=result.title)

    def find_duplicate_url(self, url: str) -> dict | None:
        """Nota ya existente con esa URL (vía índice), o None."""
        try:
            from second_brain.index import sqlite_index

            return sqlite_index.find_by_url(self.config.library_dir, url)
        except Exception:  # noqa: BLE001 — la deduplicación es prescindible
            return None

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

        # Nunca degradar: si la nota ya estaba completa y el reintento de
        # extracción falla (p. ej. la web murió), se conserva la nota buena.
        if frontmatter.get("status") == "complete" and result.status == "pending":
            return ProcessOutcome(
                path=path, status="complete", title=str(frontmatter.get("title", ""))
            )

        self._apply_enrichment(result)
        new_frontmatter = self._frontmatter(
            str(frontmatter["id"]), capture, ctx, result
        )
        self._apply_relations(new_frontmatter, path)
        body = _body_with_section(result.body, new_frontmatter.get("enrichment"))
        markdown.write_note(
            path, markdown.render_note(new_frontmatter, result.title, body)
        )
        self._update_index(path)
        return ProcessOutcome(path=path, status=result.status, title=result.title)

    # ------------------------------------------------------------------ #
    # Internos                                                            #
    # ------------------------------------------------------------------ #
    def _run_processor(self, capture: Capture, ctx: ProcessContext) -> ProcessResult:
        try:
            return get_processor(capture.kind)(capture, ctx)
        except Exception as exc:  # noqa: BLE001 — nunca perder la captura
            return self._fallback_result(capture, ctx, exc)

    def _apply_relations(self, frontmatter: dict, path: Path) -> None:
        """Enlaza la nota con las que comparten etiquetas (campo `related`)."""
        try:
            from second_brain.enrich import relations

            rel = str(path.relative_to(self.config.library_dir))
            links = relations.related_wikilinks(
                self.config.library_dir, frontmatter.get("tags") or [], rel
            )
        except Exception:  # noqa: BLE001 — sin índice no hay relaciones
            return
        schema = frontmatter.pop("schema", SCHEMA_VERSION)
        if links:
            frontmatter["related"] = links
        else:
            frontmatter.pop("related", None)
        frontmatter["schema"] = schema

    def _update_index(self, path: Path) -> None:
        """Mantiene fresco el índice de búsqueda (si existe)."""
        try:
            from second_brain.index import sqlite_index

            sqlite_index.upsert(self.config.library_dir, path)
        except Exception:  # noqa: BLE001 — el índice es desechable
            pass

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
            up_to_date = (
                existing.get("knowledge_model") == model.hash
                and existing.get("version") == enricher.ENRICHMENT_VERSION
            )
            if not force and up_to_date:
                continue

            title = str(frontmatter.get("title", ""))
            content = _original_content(body)
            # migración: notas antiguas sin content_source lo reciben aquí
            frontmatter["content_source"] = _content_source(
                str(frontmatter.get("type", "text")), frontmatter.get("url_type")
            )
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
            self._apply_relations(frontmatter, path)
            new_body = _body_with_section(content, frontmatter.get("enrichment"))
            markdown.write_note(path, markdown.render_note(frontmatter, title, new_body))
            self._update_index(path)
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
            "source": capture.source,  # vía de captura (telegram, cli...)
            "content_source": _content_source(
                capture.kind, result.extra.get("url_type")
            ),
            "captured_at": capture.captured_at.isoformat(timespec="seconds"),
            "status": result.status,
            "title": result.title,
            "tags": sorted(set(_hashtags(capture.text)) | set(categories)),
        }
        if capture.url:
            fm["url"] = capture.url
        if ctx.attachment_rel:
            fm["attachments"] = [ctx.attachment_rel]
        if capture.kind in _ATTACHMENT_KINDS and capture.text:
            fm["caption"] = capture.text
        if capture.mime_type:
            fm["mime_type"] = capture.mime_type
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
        if kind in _ATTACHMENT_KINDS:
            text = fm.get("caption")
        elif kind == "text":
            text = _original_content(body)
        else:
            text = None
        return Capture(
            kind=kind,
            source=source,
            captured_at=captured_at,
            text=text,
            url=fm.get("url"),
            mime_type=fm.get("mime_type"),
            metadata=fm.get(source) or {},
        )
