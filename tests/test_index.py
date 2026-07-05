from datetime import datetime

from second_brain.index import sqlite_index
from second_brain.models import Capture
from second_brain.pipeline import Pipeline


def test_rebuild_and_search(config):
    pipeline = Pipeline(config)
    now = datetime(2026, 7, 2, 10, 0, 0).astimezone()
    pipeline.process(
        Capture(kind="text", source="cli", captured_at=now, text="Apuntes sobre jardinería urbana")
    )
    pipeline.process(
        Capture(kind="text", source="cli", captured_at=now, text="Receta de pan de centeno")
    )

    count = sqlite_index.rebuild(config.library_dir)
    assert count == 2

    results = sqlite_index.search(config.library_dir, "jardinería")
    assert len(results) == 1
    assert "jardinería" in results[0]["title"].lower() or "jardinería" in results[0]["snippet"].lower()


def test_index_is_fully_regenerable(config):
    pipeline = Pipeline(config)
    now = datetime(2026, 7, 2, 10, 0, 0).astimezone()
    pipeline.process(Capture(kind="text", source="cli", captured_at=now, text="nota uno"))
    sqlite_index.rebuild(config.library_dir)

    # Borrar el índice no pierde nada: se regenera desde los Markdown
    sqlite_index.db_path(config.library_dir).unlink()
    count = sqlite_index.rebuild(config.library_dir)
    assert count == 1
    assert sqlite_index.search(config.library_dir, "uno")


def test_search_without_index_raises(config, tmp_path):
    try:
        sqlite_index.search(config.library_dir, "algo")
        assert False, "debería fallar sin índice"
    except FileNotFoundError:
        pass
