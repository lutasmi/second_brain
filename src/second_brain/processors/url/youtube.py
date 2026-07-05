"""Extractor de vídeos de YouTube.

Metadatos vía oEmbed (sin clave de API) y transcripción mejor-esfuerzo con
youtube-transcript-api: no todos los vídeos tienen subtítulos, así que su
ausencia no deja la nota pendiente, solo se anota.
"""

import re
from urllib.parse import parse_qs, urlparse

import httpx

from second_brain.processors.url.base import Extraction, ExtractionError


def video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.lstrip("/").split("/")[0] or None
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return (parse_qs(parsed.query).get("v") or [None])[0]
        match = re.match(r"^/(?:shorts|live|embed)/([\w-]{6,})", parsed.path)
        if match:
            return match.group(1)
    return None


def _transcript(vid: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        try:  # API >= 1.0
            fetched = YouTubeTranscriptApi().fetch(vid, languages=["es", "en"])
            snippets = getattr(fetched, "snippets", fetched)
            texts = [
                getattr(s, "text", None) or (s.get("text", "") if isinstance(s, dict) else "")
                for s in snippets
            ]
        except AttributeError:  # API < 1.0
            data = YouTubeTranscriptApi.get_transcript(vid, languages=["es", "en"])
            texts = [d["text"] for d in data]
        text = " ".join(t.strip() for t in texts if t and t.strip())
        return text or None
    except Exception:  # noqa: BLE001 — la transcripción es opcional
        return None


def extract(url: str) -> Extraction:
    vid = video_id(url)
    if not vid:
        raise ExtractionError("URL de YouTube sin id de vídeo")

    resp = httpx.get(
        "https://www.youtube.com/oembed",
        params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ExtractionError(f"oEmbed devolvió {resp.status_code}")
    info = resp.json()

    transcript = _transcript(vid)
    content = (
        f"## Transcripción\n\n{transcript}" if transcript else "_Transcripción no disponible._"
    )
    meta = {
        "author": info.get("author_name"),
        "video_id": vid,
        "transcript": "yes" if transcript else "no",
    }
    return Extraction(
        title=info.get("title"),
        content=content,
        meta={k: v for k, v in meta.items() if v},
    )
