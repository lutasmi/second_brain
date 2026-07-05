# Arquitectura

## Flujo

```
Fuente (Telegram, CLI, ...)          construye Capture
        │
        ▼
Pipeline                             guarda adjuntos → procesa → escribe nota
        │
        ▼
Markdown (library/AAAA/MM/*.md)      FUENTE DE VERDAD
        │
        ▼ (opcional, regenerable)
Índice SQLite FTS5 (.index/notes.db) búsqueda de texto completo
```

## Módulos

| Módulo                    | Responsabilidad                                                       |
|---------------------------|-----------------------------------------------------------------------|
| `sources/`                | Adaptadores de entrada. Convierten mensajes en `Capture`.             |
| `pipeline.py`             | Núcleo: adjuntos → procesador → nota Markdown. Garantiza no perder nada. |
| `processors/`             | Un módulo por tipo de contenido (`text`, `url`, `image`).             |
| `processors/url/`         | Un extractor por tipo de enlace (`web`, `twitter`, `youtube`, `linkedin`). |
| `enrich/`                 | Enriquecimiento IA: `knowledge_model.py` (taxonomía oficial como activo) + `enricher.py` (categorías, resumen, entidades...) + `relations.py` (wikilinks por etiquetas compartidas). |
| `report.py`               | Parte de estado: salud de biblioteca y espejo (para /estado y el parte diario). |
| `ai.py`                   | Capa de proveedor de IA (OpenAI/Anthropic), conmutable por `.env`.    |
| `storage/`                | Formato Markdown + estructura física de la biblioteca.                |
| `index/`                  | Índice SQLite FTS5, 100 % regenerable desde los Markdown.             |
| `cli.py`                  | Comandos: `run`, `add`, `reprocess`, `index`, `search`.               |

## Puntos de extensión

**Nueva fuente** (correo, RSS, WhatsApp, Discord...): crea un módulo en
`sources/` que construya objetos `Capture` y llame a `Pipeline.process()`.
Nada más cambia. La CLI (`second-brain add`) es la segunda fuente y sirve
de ejemplo mínimo.

**Nuevo tipo de contenido** (PDF, audio, vídeo...): crea un módulo en
`processors/` con `process(capture, ctx) -> ProcessResult` y regístralo en
`processors/PROCESSORS`.

**Nuevo extractor de URL** (Reddit, HN, Substack...): crea un módulo en
`processors/url/` con `extract(url) -> Extraction` y regístralo en
`EXTRACTORS`, añadiendo su detección en `detect_url_type()`.

## Decisiones y razones

- **Python 3.11 + librerías maduras**: `python-telegram-bot` (bot),
  `trafilatura` (extracción web, estado del arte en contenido principal),
  `pytesseract` (OCR), SDK oficial `anthropic` (descripción de imágenes).
- **Long polling, no webhook**: cero infraestructura pública; corre en
  cualquier portátil o mini-PC.
- **Markdown como única fuente de verdad**: la base de datos SQLite solo
  indexa; borrarla no pierde nada (`second-brain index` la regenera).
- **Captura antes que enriquecimiento**: los adjuntos se escriben en disco
  antes de intentar OCR/IA; si un procesador falla, la nota se escribe
  igualmente con estado `pending` y `errors`, y `reprocess` la reintenta.
- **Escritura atómica** (tmp + rename): nunca quedan notas a medias.
- **X/Twitter vía FxTwitter**: la API oficial es de pago. FxTwitter es un
  tercero gratuito; si desaparece, las notas quedan `pending` (la URL nunca
  se pierde) y un extractor futuro las completará.
- **LinkedIn**: bloquea el scraping sin sesión. Se detecta el tipo, se
  guarda la URL y la nota queda `pending` a la espera de un extractor viable.
- **IA conmutable por configuración**: `ai.py` abstrae el proveedor
  (OpenAI o Anthropic, elegido con `AI_PROVIDER`/`AI_MODEL` en `.env`).
  Ninguna nota depende de quién la enriqueció: el bloque `enrichment`
  registra proveedor, modelo y fecha, y es 100 % regenerable.
- **La estructura de conocimiento es un activo**: `knowledge_model.md` vive
  en la biblioteca, versionado por hash. La IA clasifica solo dentro de esa
  taxonomía (nunca inventa categorías); los metadatos abiertos (entidades,
  conceptos, keywords) van aparte. Editar el archivo + `second-brain enrich`
  actualiza la biblioteca sin tocar código, prompts ni contenido original.
- **Sin base de datos de estado**: el estado (`pending`) vive en el
  frontmatter de cada nota; los reintentos no dependen de nada externo.
