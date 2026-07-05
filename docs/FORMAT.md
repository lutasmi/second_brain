# Formato de las notas Markdown

Este documento define el formato estable de las notas. Está pensado para
durar años: cualquier cambio incompatible incrementará el campo `schema`
y vendrá acompañado de una migración documentada.

## Principios

- Una nota = un fichero Markdown legible por cualquier editor de texto.
- El frontmatter YAML contiene todos los metadatos necesarios para búsquedas
  futuras y para regenerar cualquier índice.
- Los binarios (imágenes) viven junto a la nota, en `media/`, y se enlazan
  con rutas relativas: mover un mes completo de directorio no rompe nada.

## Estructura de carpetas

```
library/
├── 2026/
│   ├── 07/
│   │   ├── 20260702T153001-a1b2-titulo-de-la-nota.md
│   │   ├── ...
│   │   └── media/
│   │       └── 20260702T153001-a1b2.jpg
│   └── 08/
└── .index/            # índice SQLite regenerable (ignorable, borrable)
    └── notes.db
```

- Particionado `AÑO/MES`: ningún directorio crece sin límite; escala a
  cientos de miles de documentos.
- Nombre de fichero: `<id>-<slug>.md`. El `id`
  (`AAAAMMDDTHHMMSS-xxxx`) es único, ordenable cronológicamente y estable
  para siempre; el slug es solo legibilidad humana.

## Frontmatter

Campos comunes a todas las notas:

| Campo         | Tipo   | Descripción                                             |
|---------------|--------|---------------------------------------------------------|
| `id`          | str    | Identificador único y estable de la nota                |
| `type`        | str    | `text` \| `url` \| `image` \| `audio` \| `pdf` \| `file` (comodín) |
| `source`      | str    | **Vía de captura**: por dónde entró (`telegram`, `cli`, ...) |
| `content_source` | str | **Origen real del contenido**: `twitter` \| `youtube` \| `linkedin` \| `web` \| `nota-personal` \| `imagen` \| `nota-de-voz` \| `documento` \| `archivo`. Determinista (derivado del tipo y la URL), siempre regenerable |
| `captured_at` | str    | ISO 8601 con zona horaria                               |
| `status`      | str    | `complete` \| `pending` (extracción pendiente)          |
| `title`       | str    | Título legible                                          |
| `tags`        | [str]  | Hashtags del usuario + etiquetas IA de la taxonomía     |
| `schema`      | int    | Versión del formato (actualmente `1`)                   |

Campos según tipo:

| Campo         | Tipos     | Descripción                                          |
|---------------|-----------|------------------------------------------------------|
| `url`         | url       | URL original capturada (nunca se pierde)             |
| `url_type`    | url       | `web` \| `twitter` \| `youtube` \| `linkedin`        |
| `extraction`  | url       | Metadatos extraídos (autor, fecha, sitio...)         |
| `attachments` | image     | Rutas relativas de los binarios de la nota           |
| `caption`     | image     | Texto que acompañaba a la imagen                     |
| `ocr`         | image     | `done` \| `empty` (sin texto legible)                |
| `description_model` | image | Modelo de IA usado para la descripción            |
| `related`     | cualquiera| Wikilinks `[[nota\|Título]]` a notas con etiquetas comunes (Obsidian los muestra como enlaces reales en grafo y backlinks) |
| `mime_type` / `pages` | adjuntos | Tipo MIME del adjunto / páginas del PDF        |
| `enrichment`  | cualquiera| Bloque de enriquecimiento IA (ver sección propia)    |
| `enrichment_error` | cualquiera | Motivo del último fallo de enriquecimiento      |
| `errors`      | cualquiera| Fallos de captura/extracción (solo si hubo alguno)   |
| `telegram`/`cli` | cualquiera | Metadatos de la fuente (chat, mensaje, remitente) |

## Modelo de conocimiento y enriquecimiento

La estructura de conocimiento es un **activo del proyecto**, no del modelo
de IA: vive en `<library>/knowledge_model.md`. Su sección `## Categorías`
define la taxonomía oficial (`- slug — descripción`); la IA clasifica
eligiendo **exclusivamente** de esa lista y nunca inventa categorías.
Editar el archivo + `second-brain enrich` reclasifica la biblioteca: cada
nota registra el hash del modelo con que fue enriquecida, así que solo se
reprocesa lo obsoleto (con `--all` se fuerza todo).

La taxonomía **aprende del uso**: las `suggested_categories` de las notas
se agregan y, cuando un tema se repite, se propone (`/sugerencias` en
Telegram, `second-brain suggest` en CLI, y aviso en el parte diario al
llegar a 3 notas). `/aprobar <categoria>` la incorpora a la sección oficial;
`/descartar <categoria>` la registra en la sección `## Descartadas` del
mismo archivo y no vuelve a proponerse (ni por el agregador ni por el
modelo de IA).

Cada nota completa lleva un bloque `enrichment` en el frontmatter:

```yaml
enrichment:
  categories: [ia, producto]      # SOLO de la taxonomía oficial → tags
  suggested_categories: [robotica] # propuestas FUERA de la taxonomía: tu cola
                                  # de revisión para hacer crecer knowledge_model.md
  content_type: articulo          # articulo|video|audio|hilo-social|idea-propia|
                                  # imagen|documento|herramienta|referencia|otro
  summary: Resumen fiel de 1-3 frases.
  why_relevant: Por qué este documento debería seguir existiendo dentro de
    diez años en la biblioteca.
  key_ideas:                      # lo que merece la pena recordar; no un
    - los agentes necesitan objetivos verificables  # resumen: aprendizajes,
                                  # inspiración, decisiones, hipótesis, contexto
  entities:                       # metadatos abiertos (no taxonomía)
    people: [Sam Altman]
    organizations: [OpenAI]
    technologies: [GPT-5]
    products: []
    places: []
  concepts: [agentes autónomos]
  keywords: [llm, orquestación]
  related_topics: [automatización del trabajo]
  language: es
  extraction_confidence: 0.95     # ¿el contenido presente es completo y fiel?
  classification_confidence: 0.92 # ¿las categorías elegidas son correctas?
  provider: openai                # trazabilidad del enriquecimiento
  model: gpt-5-mini
  enriched_at: '2026-07-05T10:00:00+02:00'
  knowledge_model: 3fa1b2c8       # hash del knowledge_model.md usado
  version: 3                      # versión del esquema de enriquecimiento
```

Además del frontmatter, cada nota enriquecida lleva una **sección legible**
al principio del cuerpo, delimitada por los marcadores
`<!-- enriquecimiento:inicio -->` / `<!-- enriquecimiento:fin -->`:
resumen, por qué se guardó y aprendizajes, en callouts de Obsidian (en
cualquier otro visor se leen como citas). La sección es 100 % regenerable;
eliminar el bloque devuelve el contenido original exacto.

**Inmutabilidad**: el enriquecimiento vive solo en el frontmatter; el cuerpo
de la nota es siempre el contenido original capturado, intacto y
recuperable. Todo el bloque es regenerable en cualquier momento (cambio de
modelo, proveedor o taxonomía) sin pérdida de información. Si el
enriquecimiento falla, la captura se guarda igualmente y el campo
`enrichment_error` registra el motivo hasta el siguiente `enrich`.

`tags` (nivel superior) = hashtags del usuario + `enrichment.categories`.
Obsidian lo lee de forma nativa: panel de etiquetas, búsqueda `tag:#ia` y
grafo (con "mostrar etiquetas") relacionan las notas por temática.

## Estados y reintentos

- `complete`: la nota tiene todo el contenido que el sistema pudo aportar.
- `pending`: la captura está a salvo, pero falta enriquecimiento (extracción
  web fallida, OCR sin tesseract, descripción IA sin clave...). El campo
  `errors` explica el motivo. `second-brain reprocess` reintenta todas las
  notas `pending` conservando `id`, fichero y metadatos de origen.

## Cuerpo

Siempre empieza con `# <título>`. Después, según el tipo:

**Texto** — el mensaje íntegro, sin transformar.

**URL** — cita con la fuente y el contenido extraído en Markdown:

```markdown
# Título del artículo

> Fuente: <https://ejemplo.com/articulo>

Contenido extraído...
```

**Imagen** — imagen original enlazada + secciones opcionales:

```markdown
# Título (caption o fecha)

![imagen](media/20260702T153001-a1b2.jpg)

## Nota del usuario
...caption...

## Descripción
...descripción generada por IA...

## Texto extraído (OCR)
...texto visible en la imagen...
```

## Ejemplo completo

```markdown
---
id: 20260702T153001-a1b2
type: url
source: telegram
captured_at: '2026-07-02T15:30:01+02:00'
status: complete
title: Example Domain
tags: []
url: https://example.com/
url_type: web
extraction:
  sitename: Example
telegram:
  chat_id: 123456
  message_id: 42
  sender: lutasmi
schema: 1
---

# Example Domain

> Fuente: <https://example.com/>

This domain is for use in illustrative examples in documents...
```
