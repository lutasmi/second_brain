from datetime import datetime

from PIL import Image

import second_brain.processors.image as image_processor
import second_brain.processors.url as url_processor
from second_brain.models import Capture
from second_brain.pipeline import Pipeline
from second_brain.processors.url.base import Extraction, ExtractionError
from second_brain.storage import markdown


def _now():
    return datetime(2026, 7, 2, 15, 30, 1).astimezone()


def _png_bytes():
    import io

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_text_capture_creates_complete_note(config):
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="text",
            source="cli",
            captured_at=_now(),
            text="Una idea #producto\n\nCon detalle.",
        )
    )
    assert outcome.status == "complete"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["type"] == "text"
    assert frontmatter["status"] == "complete"
    assert frontmatter["tags"] == ["producto"]
    assert frontmatter["schema"] == 1
    assert "Con detalle." in body


def test_url_capture_failure_never_loses_url(config, monkeypatch):
    def boom(url):
        raise ExtractionError("sin red")

    monkeypatch.setitem(url_processor.EXTRACTORS, "web", boom)
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(kind="url", source="cli", captured_at=_now(), url="https://example.com/x")
    )
    assert outcome.status == "pending"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["url"] == "https://example.com/x"
    assert frontmatter["status"] == "pending"
    assert frontmatter["errors"]
    assert "https://example.com/x" in body


def test_processor_crash_still_writes_note(config, monkeypatch):
    def crash(capture, ctx):
        raise RuntimeError("bug inesperado")

    monkeypatch.setitem(
        __import__("second_brain.processors", fromlist=["PROCESSORS"]).PROCESSORS,
        "text",
        crash,
    )
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="no me pierdas")
    )
    assert outcome.status == "pending"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert "no me pierdas" in body
    assert any("procesador" in e for e in frontmatter["errors"])


def test_image_capture_saves_original_even_if_enrichment_fails(config, monkeypatch):
    def no_ocr(path):
        raise RuntimeError("tesseract no está instalado")

    monkeypatch.setattr(image_processor, "run_ocr", no_ocr)
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(
            kind="image",
            source="cli",
            captured_at=_now(),
            text="captura de pantalla #ocr",
            file_bytes=_png_bytes(),
            file_name="pantalla.png",
        )
    )
    assert outcome.status == "pending"
    frontmatter, body = markdown.parse_note(outcome.path)
    attachment = outcome.path.parent / frontmatter["attachments"][0]
    assert attachment.exists()
    assert frontmatter["caption"] == "captura de pantalla #ocr"
    assert "![imagen](media/" in body


def test_image_capture_complete_with_ocr(config, monkeypatch):
    monkeypatch.setattr(image_processor, "run_ocr", lambda path: "TEXTO VISIBLE")
    pipeline = Pipeline(config)  # ai_descriptions=False en el fixture
    outcome = pipeline.process(
        Capture(
            kind="image",
            source="cli",
            captured_at=_now(),
            file_bytes=_png_bytes(),
            file_name="foto.png",
        )
    )
    assert outcome.status == "complete"
    _, body = markdown.parse_note(outcome.path)
    assert "TEXTO VISIBLE" in body


def test_reprocess_completes_pending_url_note(config, monkeypatch):
    def boom(url):
        raise ExtractionError("sin red")

    monkeypatch.setitem(url_processor.EXTRACTORS, "web", boom)
    pipeline = Pipeline(config)
    outcome = pipeline.process(
        Capture(kind="url", source="cli", captured_at=_now(), url="https://example.com/a")
    )
    assert outcome.status == "pending"

    monkeypatch.setitem(
        url_processor.EXTRACTORS,
        "web",
        lambda url: Extraction(title="Artículo", content="Cuerpo extraído", meta={"sitename": "Example"}),
    )
    results = pipeline.reprocess()
    assert len(results) == 1
    assert results[0].status == "complete"
    assert results[0].path == outcome.path  # misma nota, mismo fichero

    frontmatter, body = markdown.parse_note(outcome.path)
    assert frontmatter["status"] == "complete"
    assert frontmatter["id"] == outcome.path.name.split("-")[0] + "-" + outcome.path.name.split("-")[1]
    assert "Cuerpo extraído" in body
    assert "errors" not in frontmatter


def test_reprocess_ignores_complete_notes(config):
    pipeline = Pipeline(config)
    pipeline.process(Capture(kind="text", source="cli", captured_at=_now(), text="hola"))
    assert pipeline.reprocess() == []
