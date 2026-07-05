from pathlib import Path

import pytest

from second_brain.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        library_dir=tmp_path / "library",
        telegram_token=None,
        allowed_user_ids=frozenset(),
        ai_provider="auto",
        ai_model=None,
        ai_descriptions=False,
        ai_enrich=False,
    )
