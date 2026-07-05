"""Procesadores de capturas: convierten una Capture en contenido Markdown.

Cada tipo de entrada es un módulo independiente. Para añadir un tipo nuevo
(PDF, audio, ...), crea un módulo con `process(capture, ctx) -> ProcessResult`
y regístralo en PROCESSORS. El resto del sistema no cambia.
"""

from second_brain.processors import image, text, url

PROCESSORS = {
    "text": text.process,
    "url": url.process,
    "image": image.process,
}


def get_processor(kind: str):
    try:
        return PROCESSORS[kind]
    except KeyError:
        raise ValueError(f"Tipo de captura desconocido: {kind!r}") from None
