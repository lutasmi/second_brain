"""Extractor genérico de páginas web mediante trafilatura."""

from second_brain.processors.url.base import Extraction, ExtractionError


def extract(url: str) -> Extraction:
    import trafilatura

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ExtractionError("no se pudo descargar la página")

    try:
        content = trafilatura.extract(
            downloaded, output_format="markdown", include_links=True, url=url
        )
    except Exception:  # noqa: BLE001 — versiones antiguas sin salida markdown
        content = None
    if not content:
        content = trafilatura.extract(downloaded, url=url)

    metadata = None
    try:
        metadata = trafilatura.extract_metadata(downloaded)
    except Exception:  # noqa: BLE001 — los metadatos son opcionales
        pass

    title = metadata.title if metadata else None
    if not content and not title:
        raise ExtractionError("no se pudo extraer contenido de la página")

    meta = {}
    if metadata:
        for key in ("author", "date", "sitename", "description"):
            value = getattr(metadata, key, None)
            if value:
                meta[key] = str(value)
    return Extraction(title=title, content=content, meta=meta)
