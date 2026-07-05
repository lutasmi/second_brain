from dataclasses import replace
from datetime import datetime

import second_brain.enrich.enricher as enricher
import second_brain.enrich.knowledge_model as km
from second_brain.models import Capture
from second_brain.pipeline import Pipeline
from second_brain.storage import markdown


def _now():
    return datetime(2026, 7, 5, 10, 0, 0).astimezone()


def _fake_enrichment(**overrides):
    base = {
        "categories": ["ia"],
        "summary": "Resumen de prueba.",
        "why_relevant": "Conecta con tus intereses en IA.",
        "key_ideas": ["aprender siempre"],
        "entities": {"people": ["Ada Lovelace"]},
        "keywords": ["algoritmos"],
        "language": "es",
        "extraction_confidence": 0.95,
        "classification_confidence": 0.9,
        "provider": "openai",
        "model": "gpt-5-mini",
        "enriched_at": "2026-07-05T10:00:00+02:00",
        "knowledge_model": "deadbeef",
        "version": enricher.ENRICHMENT_VERSION,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------- #
# Modelo de conocimiento                                                 #
# --------------------------------------------------------------------- #
def test_knowledge_model_created_and_parsed(tmp_path):
    model = km.ensure_model(tmp_path)
    assert "ia" in model.slugs
    assert km.model_path(tmp_path).exists()
    # las categorías llevan descripción que guía al clasificador
    assert any(desc for _, desc in model.categories)


def test_knowledge_model_hash_changes_on_edit(tmp_path):
    before = km.ensure_model(tmp_path)
    path = km.model_path(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8") + "- jardineria — huertos y plantas\n",
        encoding="utf-8",
    )
    after = km.ensure_model(tmp_path)
    assert "jardineria" in after.slugs
    assert before.hash != after.hash


def test_knowledge_model_without_categories_fails(tmp_path):
    km.model_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    km.model_path(tmp_path).write_text("# vacío\n", encoding="utf-8")
    try:
        km.ensure_model(tmp_path)
        assert False, "debería fallar sin categorías"
    except ValueError:
        pass


def test_enricher_validates_against_official_categories(config, tmp_path, monkeypatch):
    model = km.ensure_model(tmp_path)

    def fake_classify(prompt, schema, cfg):
        return {
            "categories": ["ia", "inventada", "SALUD"],  # inventada se descarta
            "suggested_categories": ["Física Nuclear", "ia", ""],  # ia ya es oficial
            "content_type": "articulo",
            "summary": "  Un resumen.  ",
            "why_relevant": " Te interesa la historia de la ciencia. ",
            "key_ideas": ["La perseverancia importa", "la perseverancia importa"],
            "entities": {"people": [" Marie Curie ", "marie curie", ""]},
            "concepts": [],
            "keywords": ["Radio", "física"],
            "related_topics": ["premios nobel"],
            "language": "ES",
            "extraction_confidence": -0.3,  # se recorta a 0.0
            "classification_confidence": 1.7,  # se recorta a 1.0
        }

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import second_brain.ai as ai

    monkeypatch.setattr(ai, "classify_json", fake_classify)
    result = enricher.enrich("Título", "Cuerpo", model, config)

    assert result["categories"] == ["ia", "salud"]
    assert result["suggested_categories"] == ["fisica-nuclear"]  # slug + sin oficiales
    assert result["content_type"] == "articulo"
    assert result["summary"] == "Un resumen."
    assert result["why_relevant"] == "Te interesa la historia de la ciencia."
    assert result["key_ideas"] == ["La perseverancia importa"]  # dedup
    assert result["entities"]["people"] == ["Marie Curie"]  # dedup + limpieza
    assert "concepts" not in result  # las listas vacías no ensucian la nota
    assert result["extraction_confidence"] == 0.0
    assert result["classification_confidence"] == 1.0
    assert result["language"] == "es"
    assert result["knowledge_model"] == model.hash
    assert result["version"] == enricher.ENRICHMENT_VERSION
    assert result["provider"] == "openai"


# --------------------------------------------------------------------- #
# Pipeline: captura con enriquecimiento                                  #
# --------------------------------------------------------------------- #
def test_capture_gets_enrichment_and_tags(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda title, body, model, cfg: _fake_enrichment(categories=["ia", "ciencia"]),
    )
    pipeline = Pipeline(replace(config, ai_enrich=True))
    outcome = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="Nota sobre IA #ml")
    )
    assert outcome.status == "complete"
    frontmatter, _ = markdown.parse_note(outcome.path)
    assert frontmatter["tags"] == ["ciencia", "ia", "ml"]  # categorías + hashtag
    assert frontmatter["enrichment"]["summary"] == "Resumen de prueba."


def test_enrichment_failure_never_blocks_capture(config, monkeypatch):
    def boom(title, body, model, cfg):
        raise RuntimeError("api caída")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(enricher, "enrich", boom)
    pipeline = Pipeline(replace(config, ai_enrich=True))
    outcome = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="no me pierdas")
    )
    # la captura queda completa; el enriquecimiento se reintenta con `enrich`
    assert outcome.status == "complete"
    frontmatter, body = markdown.parse_note(outcome.path)
    assert "api caída" in frontmatter["enrichment_error"]
    assert "no me pierdas" in body


def test_no_key_skips_enrichment_silently(config, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pipeline = Pipeline(replace(config, ai_enrich=True))
    outcome = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="sin clave")
    )
    frontmatter, _ = markdown.parse_note(outcome.path)
    assert outcome.status == "complete"
    assert "enrichment" not in frontmatter
    assert "enrichment_error" not in frontmatter


# --------------------------------------------------------------------- #
# enrich_library: regeneración sin tocar el contenido                    #
# --------------------------------------------------------------------- #
def test_enrich_library_preserves_original_content(config, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pipeline = Pipeline(replace(config, ai_enrich=True))
    outcome = pipeline.process(
        Capture(
            kind="text",
            source="cli",
            captured_at=_now(),
            text="Idea original\n\nCon un segundo párrafo que no debe cambiar.",
        )
    )
    body_before = markdown.parse_note(outcome.path)[1]

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        enricher, "enrich", lambda t, b, m, c: _fake_enrichment(categories=["idea-propia"])
    )
    results = pipeline.enrich_library()
    assert [s for _, s in results] == ["enriched"]

    frontmatter, body_after = markdown.parse_note(outcome.path)
    # inmutabilidad: el contenido original se recupera exacto quitando la sección
    from second_brain.pipeline import _original_content

    assert _original_content(body_after) == _original_content(body_before)
    assert "Con un segundo párrafo que no debe cambiar." in body_after
    # la sección legible está presente y delimitada
    assert markdown.ENRICH_START in body_after and markdown.ENRICH_END in body_after
    assert "Por qué merece quedarse" in body_after
    assert frontmatter["enrichment"]["categories"] == ["idea-propia"]
    assert frontmatter["tags"] == ["idea-propia"]

    # regenerar otra vez no duplica la sección (idempotente)
    results = pipeline.enrich_library(force=True)
    assert [s for _, s in results] == ["enriched"]
    _, body_again = markdown.parse_note(outcome.path)
    assert body_again.count(markdown.ENRICH_START) == 1
    assert _original_content(body_again) == _original_content(body_before)


def test_enrich_library_only_reprocesses_stale_notes(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = km.ensure_model(config.library_dir)
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda t, b, m, c: _fake_enrichment(knowledge_model=m.hash),
    )
    pipeline = Pipeline(replace(config, ai_enrich=True))
    pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="nota al día")
    )

    # nada obsoleto → no hay trabajo
    assert pipeline.enrich_library() == []
    # editar el knowledge model deja la nota obsoleta → se re-enriquece
    path = km.model_path(config.library_dir)
    path.write_text(
        path.read_text(encoding="utf-8") + "- nueva-categoria — algo\n",
        encoding="utf-8",
    )
    results = pipeline.enrich_library()
    assert [s for _, s in results] == ["enriched"]
    # --all fuerza aunque esté al día
    assert [s for _, s in pipeline.enrich_library(force=True)] == ["enriched"]


def test_enrichment_version_bump_marks_notes_stale(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = km.ensure_model(config.library_dir)
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda t, b, m, c: _fake_enrichment(knowledge_model=m.hash),
    )
    pipeline = Pipeline(replace(config, ai_enrich=True))
    pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="nota versionada")
    )
    assert pipeline.enrich_library() == []  # al día

    # una versión vieja del enriquecedor deja la nota obsoleta
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda t, b, m, c: _fake_enrichment(knowledge_model=m.hash, version=1),
    )
    pipeline.enrich_library(force=True)
    monkeypatch.setattr(
        enricher,
        "enrich",
        lambda t, b, m, c: _fake_enrichment(knowledge_model=m.hash),
    )
    assert [s for _, s in pipeline.enrich_library()] == ["enriched"]


def test_render_section_and_strip_roundtrip():
    section = enricher.render_section(_fake_enrichment(suggested_categories=["nueva"]))
    assert section.startswith(markdown.ENRICH_START)
    assert section.endswith(markdown.ENRICH_END)
    assert "Resumen" in section and "Ideas clave" in section and "nueva" in section

    original = "Contenido original\n\ncon dos párrafos."
    body = f"{section}\n\n{original}"
    assert markdown.strip_enrichment_section(body).strip() == original


def test_render_section_backwards_compatible_with_v2_fields():
    legacy = {
        "summary": "Resumen viejo.",
        "relevance": "Motivo antiguo.",
        "learnings": ["lección antigua"],
    }
    section = enricher.render_section(legacy)
    assert "Motivo antiguo." in section
    assert "lección antigua" in section


def test_content_source_distinct_from_capture_source(config, monkeypatch):
    from second_brain.pipeline import Pipeline as P

    pipeline = P(config)
    text_note = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="idea propia")
    )
    fm, _ = markdown.parse_note(text_note.path)
    assert fm["source"] == "cli"
    assert fm["content_source"] == "nota-personal"

    import second_brain.processors.url as url_processor
    from second_brain.processors.url.base import Extraction

    monkeypatch.setitem(
        url_processor.EXTRACTORS,
        "twitter",
        lambda url: Extraction(title="Tuit", content="texto", meta={}),
    )
    tweet_note = pipeline.process(
        Capture(
            kind="url",
            source="cli",
            captured_at=_now(),
            url="https://x.com/a/status/123",
        )
    )
    fm, _ = markdown.parse_note(tweet_note.path)
    assert fm["source"] == "cli"
    assert fm["content_source"] == "twitter"


def test_enrich_migrates_old_notes_to_v3(config, monkeypatch):
    """Una nota con enriquecimiento v2 (sin content_source, con relevance)
    queda migrada al esquema v3 con un simple `enrich`."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pipeline = Pipeline(replace(config, ai_enrich=True))
    outcome = pipeline.process(
        Capture(kind="text", source="cli", captured_at=_now(), text="nota antigua")
    )
    # simular estado v2: bloque viejo y sin content_source
    fm, body = markdown.parse_note(outcome.path)
    fm.pop("content_source", None)
    fm["enrichment"] = {"relevance": "viejo", "version": 2, "knowledge_model": "x"}
    markdown.write_note(
        outcome.path,
        markdown.render_note(fm, str(fm["title"]), "nota antigua"),
    )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(enricher, "enrich", lambda t, b, m, c: _fake_enrichment())
    results = pipeline.enrich_library()  # sin --all: la versión vieja basta
    assert [s for _, s in results] == ["enriched"]

    fm, body = markdown.parse_note(outcome.path)
    assert fm["content_source"] == "nota-personal"
    assert fm["enrichment"]["why_relevant"]
    assert "relevance" not in fm["enrichment"]
    assert "nota antigua" in body


def test_enrich_library_without_key_raises(config):
    import os

    env_backup = {
        k: os.environ.pop(k, None) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    }
    try:
        Pipeline(config).enrich_library()
        assert False, "debería fallar sin clave"
    except RuntimeError:
        pass
    finally:
        for k, v in env_backup.items():
            if v is not None:
                os.environ[k] = v
