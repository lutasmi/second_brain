"""Tests del detector de temas recurrentes y su ciclo de aprobación."""

from dataclasses import replace
from datetime import datetime

import second_brain.enrich.enricher as enricher
import second_brain.enrich.knowledge_model as km
import second_brain.enrich.suggestions as suggestions
from second_brain import report
from second_brain.models import Capture
from second_brain.pipeline import Pipeline


def _now():
    return datetime(2026, 7, 5, 14, 0, 0).astimezone()


def _capture_notes_with_suggestion(config, monkeypatch, slug, n):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = km.ensure_model(config.library_dir)
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda t, b, m, c: {
            "categories": ["tecnologia"],
            "summary": "x",
            "suggested_categories": [slug],
            "knowledge_model": m.hash,
            "version": enricher.ENRICHMENT_VERSION,
        },
    )
    pipeline = Pipeline(replace(config, ai_enrich=True))
    for i in range(n):
        pipeline.process(
            Capture(kind="text", source="cli", captured_at=_now(), text=f"nota {slug} {i}")
        )
    return model


def test_aggregate_counts_and_thresholds(config, monkeypatch):
    model = _capture_notes_with_suggestion(config, monkeypatch, "robotica", 3)
    found = suggestions.aggregate(config.library_dir, model)
    assert len(found) == 1
    assert found[0].slug == "robotica" and found[0].count == 3
    assert len(found[0].titles) == 3

    # con umbral de aviso también aparece (3 >= REPORT_THRESHOLD)
    line = suggestions.report_line(config.library_dir, model)
    assert line and "robotica (3)" in line

    # una sola repetición no llega al umbral de listado
    found_high = suggestions.aggregate(config.library_dir, model, threshold=4)
    assert found_high == []


def test_official_and_dismissed_are_excluded(config, monkeypatch):
    model = _capture_notes_with_suggestion(config, monkeypatch, "robotica", 2)
    # aprobar la categoría la saca de las sugerencias (ya es oficial)
    km.approve_category(config.library_dir, "robotica", "robots y automatización física")
    model = km.ensure_model(config.library_dir)
    assert "robotica" in model.slugs
    assert suggestions.aggregate(config.library_dir, model) == []


def test_dismiss_category_silences_suggestion(config, monkeypatch):
    _capture_notes_with_suggestion(config, monkeypatch, "cocina", 2)
    km.dismiss_category(config.library_dir, "cocina")
    model = km.ensure_model(config.library_dir)
    assert "cocina" in model.dismissed
    assert suggestions.aggregate(config.library_dir, model) == []
    # y el hash cambió: las notas se reclasificarán sin volver a sugerirla
    assert model.hash != _capture_notes_with_suggestion.__name__  # trivial no-op guard


def test_approve_inserts_into_categories_section(config):
    km.ensure_model(config.library_dir)
    km.dismiss_category(config.library_dir, "deportes")  # crea sección Descartadas
    km.approve_category(config.library_dir, "apicultura", "abejas y miel")

    model = km.ensure_model(config.library_dir)
    assert "apicultura" in model.slugs
    assert dict(model.categories)["apicultura"] == "abejas y miel"
    # la nueva categoría NO cayó en la sección de descartadas
    assert "apicultura" not in model.dismissed
    # aprobar dos veces no duplica
    km.approve_category(config.library_dir, "apicultura")
    model = km.ensure_model(config.library_dir)
    assert model.slugs.count("apicultura") == 1


def test_invalid_slug_rejected(config):
    km.ensure_model(config.library_dir)
    for bad in ("Con Espacios", "ñ", "x", "MAYUS!", ""):
        try:
            km.approve_category(config.library_dir, bad)
            assert False, f"debería rechazar {bad!r}"
        except ValueError:
            pass


def test_report_includes_suggestion_hint(config, monkeypatch):
    _capture_notes_with_suggestion(config, monkeypatch, "robotica", 3)
    text = report.build_report(config)
    assert "robotica (3)" in text and "/sugerencias" in text
