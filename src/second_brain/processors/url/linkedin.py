"""LinkedIn bloquea el scraping sin sesión iniciada.

La URL se captura siempre y la nota queda `pending`: cuando exista un
extractor viable, `second-brain reprocess` completará esas notas.
"""

from second_brain.processors.url.base import Extraction, ExtractionError


def extract(url: str) -> Extraction:
    raise ExtractionError(
        "LinkedIn requiere sesión; extracción automática no disponible"
    )
