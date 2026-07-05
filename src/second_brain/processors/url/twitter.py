"""Extractor de tuits vía la API pública de FxTwitter.

La API oficial de X requiere clave de pago; FxTwitter es un servicio de
terceros gratuito. Si algún día deja de funcionar, las notas quedan `pending`
y podrán reintentarse cuando exista otro extractor: la URL nunca se pierde.
"""

import re

import httpx

from second_brain.processors.url.base import Extraction, ExtractionError

_STATUS_RE = re.compile(r"/status(?:es)?/(\d+)")


def extract(url: str) -> Extraction:
    match = _STATUS_RE.search(url)
    if not match:
        raise ExtractionError("URL de X/Twitter sin id de tuit")

    resp = httpx.get(
        f"https://api.fxtwitter.com/i/status/{match.group(1)}",
        headers={"User-Agent": "second-brain/0.1"},
        timeout=15,
        follow_redirects=True,
    )
    try:
        data = resp.json()
    except ValueError as exc:
        raise ExtractionError(f"respuesta no válida de FxTwitter: {exc}") from exc
    if resp.status_code != 200 or data.get("code") != 200 or "tweet" not in data:
        raise ExtractionError(f"FxTwitter devolvió {data.get('code', resp.status_code)}")

    tweet = data["tweet"]
    author = tweet.get("author") or {}
    lines = [(tweet.get("text") or "").strip()]
    media = (tweet.get("media") or {}).get("all") or []
    media_urls = [item.get("url") for item in media if item.get("url")]
    if media_urls:
        lines.append("")
        lines.extend(f"- Media: {u}" for u in media_urls)

    name = author.get("name") or ""
    screen = author.get("screen_name") or ""
    title = f"{name} (@{screen})" if screen else (name or "Tuit")
    meta = {
        k: v
        for k, v in {
            "author": name,
            "handle": screen,
            "date": tweet.get("created_at"),
            "likes": tweet.get("likes"),
        }.items()
        if v not in (None, "")
    }
    return Extraction(title=title, content="\n".join(lines), meta=meta)
