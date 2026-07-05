"""Procesador de URLs: detecta el tipo de enlace y delega en un extractor.

Principio: nunca perder la captura. Si la extracción falla, la nota se guarda
igualmente con la URL y queda en estado `pending` para reintentos posteriores
(`second-brain reprocess`). Añadir soporte para un sitio nuevo consiste en
crear un extractor y registrarlo en EXTRACTORS.
"""

from __future__ import annotations

from urllib.parse import urlparse

from second_brain.models import Capture, ProcessContext, ProcessResult
from second_brain.processors.url import linkedin, twitter, web, youtube

EXTRACTORS = {
    "twitter": twitter.extract,
    "youtube": youtube.extract,
    "linkedin": linkedin.extract,
    "web": web.extract,
}


def is_probable_url(text: str) -> bool:
    """True si el mensaje completo es una única URL."""
    t = text.strip()
    if " " in t or "\n" in t:
        return False
    return t.startswith(("http://", "https://", "www."))


def normalize_url(text: str) -> str:
    t = text.strip()
    return t if t.startswith("http") else f"https://{t}"


def detect_url_type(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host in {"twitter.com", "x.com", "mobile.twitter.com"}:
        return "twitter"
    if host in {"youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"}:
        return "youtube"
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    return "web"


def process(capture: Capture, ctx: ProcessContext) -> ProcessResult:
    url = (capture.url or "").strip()
    url_type = detect_url_type(url)
    header = f"> Fuente: <{url}>"
    fallback_title = urlparse(url).hostname or url

    try:
        extraction = EXTRACTORS[url_type](url)
    except Exception as exc:  # noqa: BLE001 — la captura nunca se pierde
        body = (
            f"{header}\n\n"
            "_Contenido no extraído todavía; `second-brain reprocess` lo reintentará._"
        )
        return ProcessResult(
            title=fallback_title,
            body=body,
            status="pending",
            extra={"url_type": url_type},
            errors=[f"extraccion: {exc}"],
        )

    body = header
    if extraction.content and extraction.content.strip():
        body += f"\n\n{extraction.content.strip()}"
    extra = {"url_type": url_type}
    if extraction.meta:
        extra["extraction"] = extraction.meta
    return ProcessResult(
        title=extraction.title or fallback_title, body=body, extra=extra
    )
