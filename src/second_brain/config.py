"""Configuración del sistema, cargada desde variables de entorno y `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

@dataclass(frozen=True)
class Config:
    library_dir: Path
    telegram_token: str | None
    allowed_user_ids: frozenset[int]
    ai_provider: str  # "auto" | "openai" | "anthropic"
    ai_model: str | None  # None → modelo por defecto del proveedor
    ai_descriptions: bool
    ai_enrich: bool


def load_config(env_file: str | None = None) -> Config:
    load_dotenv(env_file or ".env")
    raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    ids = frozenset(
        int(part) for part in raw_ids.replace(";", ",").split(",") if part.strip()
    )
    return Config(
        library_dir=Path(os.getenv("LIBRARY_DIR", "library")).expanduser(),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        allowed_user_ids=ids,
        ai_provider=os.getenv("AI_PROVIDER", "auto").lower(),
        ai_model=os.getenv("AI_MODEL") or os.getenv("VISION_MODEL") or None,
        ai_descriptions=os.getenv("AI_DESCRIPTIONS", "auto").lower() != "off",
        ai_enrich=os.getenv("AI_ENRICH", os.getenv("AI_TAGS", "auto")).lower() != "off",
    )
