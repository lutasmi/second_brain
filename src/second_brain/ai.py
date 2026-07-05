"""Capa fina sobre los proveedores de IA (OpenAI / Anthropic).

El resto del sistema no sabe qué proveedor hay detrás: pide una clasificación
JSON o una descripción de imagen. El proveedor se elige por configuración
(`AI_PROVIDER`) o, en modo `auto`, según la clave disponible — OpenAI tiene
prioridad si hay ambas. Cambiar de proveedor es cambiar una variable de
entorno: ninguna nota depende de quién la enriqueció.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

DEFAULT_MODELS = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-opus-4-8",
}

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def provider(config) -> str | None:
    """Proveedor activo, o None si no hay ninguna clave configurada."""
    if config.ai_provider in DEFAULT_MODELS:
        return config.ai_provider
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def model_for(config, prov: str) -> str:
    return config.ai_model or DEFAULT_MODELS[prov]


def classify_json(prompt: str, schema: dict, config) -> dict:
    """Petición de clasificación con salida JSON garantizada por esquema."""
    prov = provider(config)
    if prov is None:
        raise RuntimeError(
            "sin clave de IA configurada (OPENAI_API_KEY o ANTHROPIC_API_KEY)"
        )

    if prov == "openai":
        from openai import OpenAI

        response = OpenAI().chat.completions.create(
            model=model_for(config, prov),
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "resultado", "strict": True, "schema": schema},
            },
        )
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise RuntimeError(f"el modelo rechazó la petición: {message.refusal}")
        return json.loads(message.content)

    import anthropic

    response = anthropic.Anthropic().messages.create(
        model=model_for(config, prov),
        max_tokens=2000,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def describe_image(path: Path, prompt: str, config) -> str:
    """Descripción de una imagen local con el proveedor activo."""
    prov = provider(config)
    if prov is None:
        raise RuntimeError(
            "sin clave de IA configurada (OPENAI_API_KEY o ANTHROPIC_API_KEY)"
        )
    media_type = MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise RuntimeError(f"formato no soportado para descripción IA: {path.suffix}")
    data = base64.standard_b64encode(path.read_bytes()).decode()

    if prov == "openai":
        from openai import OpenAI

        response = OpenAI().chat.completions.create(
            model=model_for(config, prov),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{data}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()

    import anthropic

    response = anthropic.Anthropic().messages.create(
        model=model_for(config, prov),
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()
