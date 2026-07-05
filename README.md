# second_brain / Biblioteca de Ideas

Sistema de captura, almacenamiento y consulta de conocimiento personal
pensado para perdurar durante décadas.

No es una aplicación de notas. No es un gestor de favoritos. Es una
biblioteca documental donde toda la información capturada permanece
disponible independientemente de la IA, la aplicación o la tecnología
usada para consultarla.

**Los datos son el activo. La aplicación es reemplazable. La IA es
reemplazable.**

```
Telegram ──▶ Procesamiento ──▶ Markdown (fuente maestra) ──▶ Índice (opcional)
```

## Qué hace la V1

Envías un mensaje al bot de Telegram y aparece automáticamente un fichero
Markdown en tu biblioteca:

- **Texto** → nota literal, íntegra.
- **URL** → detecta el tipo de enlace (web, X/Twitter, YouTube, LinkedIn) y
  extrae el contenido: artículo en Markdown, texto del tuit, título y
  transcripción del vídeo. Si la extracción falla, **la URL se guarda
  igualmente** y se reintenta después. URLs repetidas se detectan y no se
  duplican.
- **Imagen** → guarda el original, aplica OCR (tesseract) y genera una
  descripción con IA. Todo queda reflejado en el Markdown.
- **Nota de voz / audio** → guarda el original y lo transcribe (Whisper).
- **PDF** → guarda el original y extrae el texto.
- **Cualquier otro archivo** → se guarda como pendiente: nada se ignora.

El bot es también tu consola: `/buscar` consulta la biblioteca desde el
móvil, `/estado` muestra la salud del sistema (incluido el espejo en Drive),
`/reprocess` y `/enrich` reintentan pendientes, y cada noche a las 21:00
recibes un parte de estado automático.

Cada captura se **enriquece automáticamente** con IA: categorías de una
taxonomía oficial que es un activo del proyecto (`library/knowledge_model.md`,
editable por ti — el modelo nunca inventa categorías), resumen, entidades
(personas, organizaciones, tecnologías...), palabras clave, temas
relacionados y confianza. Todo como metadatos: el contenido original es
inmutable y el enriquecimiento puede regenerarse entero con `second-brain
enrich` (cambio de taxonomía, de modelo o de proveedor, sin perder nada).
Las notas quedan relacionadas por temática y listas para Obsidian (tags
nativos en el frontmatter → panel de etiquetas y grafo).

También hay captura directa desde la terminal (`second-brain add`), reintento
de notas pendientes (`reprocess`) y búsqueda de texto completo (`index` +
`search`, que cubre también el enriquecimiento) sobre un índice SQLite 100 %
regenerable desde los Markdown.

## Principios innegociables

- Los archivos **Markdown son la única fuente de verdad**. Se abren con
  cualquier editor; Obsidian sirve como visor, nunca como dependencia.
- Las bases de datos son **solo índices**: puedes borrar `library/.index/`
  cuando quieras y regenerarlo con `second-brain index`.
- **Nunca se pierde una captura**: si algo falla, la nota se escribe con lo
  que haya, queda en estado `pending` y `reprocess` la reintenta.
- Portable y sin bloqueo de proveedor: Python + ficheros de texto plano.

## Instalación

Requisitos: Python 3.11+. Opcional: [tesseract](https://tesseract-ocr.github.io/)
para OCR de imágenes (`brew install tesseract tesseract-lang` en macOS).

```bash
git clone <este-repo> && cd second_brain
./scripts/install.sh
```

El script crea `.venv`, instala dependencias y copia `.env.example` a `.env`.

## Configuración de Telegram

1. Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el token.
2. Habla con [@userinfobot](https://t.me/userinfobot) para conocer tu id numérico.
3. Edita `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:AAF...tu-token
TELEGRAM_ALLOWED_USER_IDS=11111111        # tu id; sin esto cualquiera podría escribir
LIBRARY_DIR=library                       # dónde vive tu biblioteca
# ANTHROPIC_API_KEY=sk-ant-...            # opcional: descripción IA de imágenes
```

## Ejecución

```bash
source .venv/bin/activate
second-brain run          # arranca el bot (long polling; no necesita servidor)
```

Envía al bot un texto, una URL o una foto y verás aparecer la nota en
`library/AAAA/MM/`. El bot responde con la ruta del fichero creado.

### Resto de comandos

```bash
second-brain add "una idea suelta #tag"        # captura texto desde la terminal
second-brain add https://ejemplo.com/articulo  # captura una URL
second-brain add --file foto.png "caption"     # captura una imagen
second-brain reprocess                         # reintenta notas pendientes
second-brain enrich                            # re-enriquece lo obsoleto (--all: todo)
second-brain index                             # (re)construye el índice de búsqueda
second-brain search jardinería                 # busca en toda la biblioteca
```

## Estructura de la biblioteca

```
library/
├── 2026/
│   └── 07/
│       ├── 20260702T153001-a1b2-titulo-de-la-nota.md
│       └── media/
│           └── 20260702T153001-a1b2.jpg
└── .index/notes.db      # índice regenerable; borrable sin pérdida
```

El formato de las notas (frontmatter, estados, reintentos) está especificado
en [docs/FORMAT.md](docs/FORMAT.md). Hay notas reales de ejemplo en
[examples/](examples/).

## Estructura del repositorio

```
src/second_brain/
├── sources/          # adaptadores de entrada (telegram; añade aquí los futuros)
├── pipeline.py       # núcleo: captura → nota Markdown, sin pérdidas
├── processors/       # un módulo por tipo: text, image, url/{web,twitter,youtube,linkedin}
├── storage/          # formato Markdown + estructura física de la biblioteca
├── index/            # índice SQLite FTS5 opcional y regenerable
└── cli.py            # run · add · reprocess · index · search
docs/                 # FORMAT.md (formato estable) · ARCHITECTURE.md (decisiones)
examples/             # notas reales generadas por el sistema
tests/                # pytest, sin dependencias de red
```

La arquitectura, los puntos de extensión (nuevas fuentes, nuevos tipos,
nuevos extractores) y las decisiones técnicas están documentados en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Despliegue en la nube (24/7, sin ordenador encendido)

El bot puede correr en cualquier servidor Linux pequeño con Docker, con la
biblioteca replicada automáticamente en Google Drive (espejo `rclone` cada
5 minutos): guía completa en [docs/DEPLOY.md](docs/DEPLOY.md).

## Tests

```bash
./.venv/bin/pytest
```

## Evolución prevista

- **Fase 3**: PDFs, audio (transcripción), más extractores de URL.
- **Fase 4**: embeddings, búsqueda semántica y chat sobre la biblioteca —
  todo derivable de los Markdown, sin migraciones.

Antes de añadir funcionalidades: la captura funciona, los Markdown son
correctos, la información nunca se pierde y el sistema corre de extremo a
extremo.
