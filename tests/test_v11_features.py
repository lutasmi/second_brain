"""Tests de las mejoras v1.1: nuevos procesadores, dedupe, relaciones,
guardia anti-degradación, índice incremental y parte de estado."""

from dataclasses import replace
from datetime import datetime

import second_brain.ai as ai
import second_brain.enrich.enricher as enricher
import second_brain.processors.url as url_processor
from second_brain import report
from second_brain.index import sqlite_index
from second_brain.models import Capture
from second_brain.pipeline import Pipeline
from second_brain.processors.url.base import Extraction, ExtractionError
from second_brain.storage import markdown


def _now():
    return datetime(2026, 7, 5, 12, 0, 0).astimezone()


# --------------------------------------------------------------------- #
# Guardia anti-degradación                                               #
# --------------------------------------------------------------------- #
def test_reprocess_never_downgrades_complete_notes(config, monkeypatch):
    monkeypatch.setitem(
        url_processor.EXTRACTORS,
        "web",
        lambda url: Extraction(title="Vivo", content="Contenido valioso", meta={}),
    )
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(kind="url", source="cli", captured_at=_now(), url="https://example.com/a")
    )
    assert outcome.status == "complete"

    # la web muere; un reprocess --all NO debe pisar el contenido bueno
    def dead(url):
        raise ExtractionError("la web ya no existe")

    monkeypatch.setitem(url_processor.EXTRACTORS, "web", dead)
    results = pipeline.reprocess(include_complete=True)
    assert [r.status for r in results] == ["complete"]
    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["status"] == "complete"
    assert "Contenido valioso" in body


# --------------------------------------------------------------------- #
# Procesadores nuevos                                                    #
# --------------------------------------------------------------------- #
def test_audio_capture_transcribed(config, monkeypatch):
    import second_brain.processors.audio  # noqa: F401 — asegura registro

    monkeypatch.setattr(ai, "transcribe_audio", lambda path, cfg: "Idea dictada al vuelo")
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="audio",
            source="cli",
            captured_at=_now(),
            file_bytes=b"OggS-fake",
            file_name="nota.oga",
            mime_type="audio/ogg",
        )
    )
    assert outcome.status == "complete"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["type"] == "audio"
    assert "Idea dictada al vuelo" in body
    assert "audio original" in body
    assert (outcome.path.parent / frontmatter["attachments"][0]).exists()


def test_audio_without_key_stays_pending(config, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="audio",
            source="cli",
            captured_at=_now(),
            file_bytes=b"OggS-fake",
            file_name="nota.oga",
        )
    )
    assert outcome.status == "pending"
    frontmatter, _ = markdown.parse_note(outcome.path)
    assert any("transcripcion" in e for e in frontmatter["errors"])
    assert (outcome.path.parent / frontmatter["attachments"][0]).exists()


def test_pdf_capture_extracts_text(config, monkeypatch):
    import second_brain.processors.pdf as pdf_processor

    monkeypatch.setattr(
        pdf_processor, "extract_text", lambda path: ("Texto del informe.", 3, "Informe X")
    )
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="pdf",
            source="cli",
            captured_at=_now(),
            file_bytes=b"%PDF-fake",
            file_name="informe.pdf",
        )
    )
    assert outcome.status == "complete"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["title"] == "Informe X"
    assert frontmatter["pages"] == 3
    assert "Texto del informe." in body


def test_scanned_pdf_stays_pending(config):
    from pypdf import PdfWriter
    import io

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="pdf",
            source="cli",
            captured_at=_now(),
            file_bytes=buffer.getvalue(),
            file_name="escaneado.pdf",
        )
    )
    assert outcome.status == "pending"
    frontmatter, _ = markdown.parse_note(outcome.path)
    assert any("sin capa de texto" in e for e in frontmatter["errors"])


def test_unsupported_file_saved_as_pending_stub(config):
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="file",
            source="cli",
            captured_at=_now(),
            text="un vídeo interesante",
            file_bytes=b"videobytes",
            file_name="clip.mp4",
            mime_type="video/mp4",
        )
    )
    assert outcome.status == "pending"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["mime"] == "video/mp4"
    assert (outcome.path.parent / frontmatter["attachments"][0]).exists()
    assert "archivo original" in body


# --------------------------------------------------------------------- #
# Índice incremental, dedupe y relaciones                                #
# --------------------------------------------------------------------- #
def test_index_upsert_keeps_index_fresh_and_dedupes(config, monkeypatch):
    pipeline = Pipeline(config)
    sqlite_index.rebuild(config.library_dir)  # índice vacío existente

    monkeypatch.setitem(
        url_processor.EXTRACTORS,
        "web",
        lambda url: Extraction(title="Artículo", content="Cuerpo", meta={}),
    )
    pipeline.process(
        Capture(kind="url", source="cli", captured_at=_now(), url="https://example.com/x")
    )
    # sin reconstruir el índice: la nota ya es localizable
    duplicate = pipeline.find_duplicate_url("https://example.com/x")
    assert duplicate and duplicate["title"] == "Artículo"
    assert pipeline.find_duplicate_url("https://example.com/otra") is None


def test_related_wikilinks_between_notes_sharing_tags(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda t, b, m, c: {
            "categories": ["salud"],
            "summary": "x",
            "knowledge_model": m.hash,
            "provider": "openai",
            "model": "gpt-5-mini",
            "enriched_at": "2026-07-05T12:00:00+02:00",
        },
    )
    pipeline = Pipeline(replace(config, ai_enrich=True))
    sqlite_index.rebuild(config.library_dir)

    first = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="Nota A sobre nutrición")
    )
    second = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="Nota B sobre ayuno")
    )
    fm_second, _ = markdown.parse_note(second.path)
    assert fm_second["related"] == [f"[[{first.path.stem}|Nota A sobre nutrición]]"]
    # la primera nota no conocía a la segunda; enrich la actualiza
    outcomes = pipeline.enrich_library(force=True)
    assert all(s == "enriched" for _, s in outcomes)
    fm_first, _ = markdown.parse_note(first.path)
    assert any(second.path.stem in link for link in fm_first["related"])


# --------------------------------------------------------------------- #
# Parte de estado                                                        #
# --------------------------------------------------------------------- #
def test_report_counts_and_sync_health(config):
    pipeline = Pipeline(config)
    pipeline.process(
        Capture(kind="text", source="cli", captured_at=datetime.now().astimezone(), text="hoy")
    )
    pipeline.process(
        Capture(kind="file", source="cli", captured_at=_now(), file_bytes=b"x", file_name="v.mp4")
    )

    stats = report.collect_stats(config)
    assert stats["total"] == 2
    assert stats["today"] >= 1
    assert stats["pending"] == 1
    assert stats["sync_age"] is None

    marker = config.library_dir / ".sync" / "last_ok"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("2026-07-05T10:00:00Z")
    text = report.build_report(config)
    assert "Notas: 2" in text
    assert "Espejo Drive" in text
    assert "/reprocess" in text


def test_safe_query_neutralizes_fts_syntax():
    assert sqlite_index.safe_query('salud AND "hígado" OR x*') == '"salud" "AND" "hígado" "OR" "x"'
    assert sqlite_index.safe_query("") == '""'
