# Changelog

## v1.0.0 — Primera versión funcional completa (5 de julio de 2026)

Primera release del **segundo cerebro**: una biblioteca documental personal
pensada para durar décadas, donde todo lo capturado se convierte
automáticamente en Markdown enriquecido, clasificado y consultable.
Esta versión valida el ciclo completo de extremo a extremo, en producción.

### Qué hace

**Captura sin fricción.** Envías cualquier cosa al bot de Telegram
(@SecondoCerebro_bot) y aparece como nota Markdown en la biblioteca:

- **Texto** → nota literal, íntegra, con los hashtags convertidos en tags.
- **URL** → detecta el tipo de enlace y extrae el contenido:
  - páginas web → artículo completo en Markdown (trafilatura)
  - X/Twitter → texto del tuit, autor, fecha (vía FxTwitter)
  - YouTube → título, canal y transcripción si existe (oEmbed + subtítulos)
  - LinkedIn → se detecta y guarda; la extracción queda pendiente (bloquea
    el scraping sin sesión)
- **Imagen** → guarda el original + OCR del texto visible (tesseract es/en)
  + descripción generada por IA.

**Enriquecimiento automático con IA.** Cada nota completa recibe un bloque
`enrichment` en su frontmatter: categorías, resumen (1–3 frases), entidades
(personas, organizaciones, tecnologías, productos, lugares), conceptos,
palabras clave, temas relacionados, idioma y confianza de la clasificación.
Además registra proveedor, modelo, fecha y versión de la taxonomía usada
(trazabilidad total).

**La estructura de conocimiento es un activo, no una ocurrencia del modelo.**
La taxonomía oficial vive en `library/knowledge_model.md` (sección
`## Categorías`, formato `- slug — descripción`). La IA clasifica
**exclusivamente** dentro de esa lista y nunca inventa categorías; los
metadatos abiertos (entidades, keywords...) van aparte. Para evolucionar la
estructura: editar el archivo y ejecutar `second-brain enrich` — cada nota
guarda el hash del modelo con que fue clasificada, así que solo se
reprocesa lo obsoleto.

**Garantías de diseño:**

- Los **Markdown son la única fuente de verdad**; se abren con cualquier
  editor. Obsidian funciona como visor nativo (tags en frontmatter → panel
  de etiquetas y grafo), nunca como dependencia.
- **Ninguna captura se pierde**: si una extracción falla, la nota se guarda
  igualmente con la URL/imagen y estado `pending`; `reprocess` la reintenta.
- **El contenido original es inmutable**: el enriquecimiento vive solo en
  metadatos y es 100 % regenerable (cambio de modelo, proveedor o taxonomía
  sin pérdida de información). Re-enriquecer nunca re-extrae las URLs.
- **El índice de búsqueda es desechable**: SQLite FTS5 en
  `library/.index/`, regenerable por completo desde los Markdown
  (`second-brain index`); la búsqueda cubre contenido y enriquecimiento.
- **La IA es reemplazable**: capa de proveedor conmutable entre OpenAI y
  Anthropic solo con variables de entorno (`AI_PROVIDER`, `AI_MODEL`).
- **Modularidad**: nueva fuente = construir `Capture`s (sources/); nuevo
  tipo de contenido = un procesador (processors/); nuevo sitio web = un
  extractor (processors/url/). El núcleo no se toca.

### Infraestructura en producción

- **Bot 24/7** en Google Cloud: VM `second-brain` (e2-micro, capa gratuita,
  zona `us-central1-a`, proyecto `project-1ef80bd3-869b-4d36-a90`, cuenta
  `secondocerebrolutas@gmail.com`). Corre con Docker Compose: servicio
  `bot` + servicio `sync`. El código vive en `~/second_brain` de la VM.
- **Fuente de verdad**: disco de la VM (`~/second_brain/library`).
- **Espejo en Google Drive**: `rclone copy` cada 5 minutos hacia
  `second_brain/library` (solo añade/actualiza, nunca borra) → copia de
  seguridad + lectura desde cualquier dispositivo con la app de Drive.
- **Secretos**: solo en el `.env` de la VM (token de Telegram, clave de
  OpenAI) y en `rclone/rclone.conf` (token de Drive). Nunca en el repo.
- **IA**: OpenAI `gpt-5-mini` (elección del usuario; conmutable).
- El ordenador personal **no interviene** en nada: capturar, procesar y
  sincronizar ocurre íntegramente en la nube.

### Configuración (`.env`)

| Variable | Uso |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot (@BotFather) |
| `TELEGRAM_ALLOWED_USER_IDS` | Ids autorizados (7086357140) |
| `LIBRARY_DIR` | Ruta de la biblioteca |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Clave del proveedor de IA |
| `AI_PROVIDER` | `auto` (OpenAI si hay clave) \| `openai` \| `anthropic` |
| `AI_MODEL` | Vacío = `gpt-5-mini` / `claude-opus-4-8` |
| `AI_DESCRIPTIONS` / `AI_ENRICH` | `off` para desactivar |

### Comandos

| Comando | Qué hace |
|---|---|
| `second-brain run` | Arranca el bot (long polling, sin servidor público) |
| `second-brain add "..."` / `--file foto.jpg` | Captura desde terminal |
| `second-brain reprocess` | Reintenta notas `pending` (re-extrae contenido) |
| `second-brain enrich [--all]` | Re-enriquece lo obsoleto (o todo) sin tocar contenido |
| `second-brain index` / `search "..."` | Reconstruye el índice / busca |

En la VM se ejecutan con: `sudo docker compose exec -T bot second-brain <cmd>`

### Recuperación ante desastres

La biblioteca completa está en Google Drive. Si el servidor desaparece:
crear otra VM → seguir `docs/DEPLOY.md` (pasos 2–4) →
`rclone copy gdrive:second_brain/library library/` → `docker compose up -d`.
No hay ninguna base de datos que migrar.

### Limitaciones conocidas

- LinkedIn: sin extracción de contenido (las notas quedan `pending` con la
  URL a salvo, a la espera de un extractor viable).
- X/Twitter depende de FxTwitter (servicio de terceros gratuito); si cae,
  las capturas quedan `pending` y se reintentarán.
- Las relaciones entre notas son por etiquetas compartidas (grafo de tags
  de Obsidian); aún no hay enlaces `[[wikilink]]` ni similitud semántica.
- Solo puede correr **una** instancia del bot a la vez (Telegram devuelve
  409 con dos consumidores del mismo token).
- La IP pública de la VM puede suponer ~2–3 €/mes cuando se agoten los
  créditos de prueba de Google Cloud (octubre de 2026); revisar entonces.

### Documentación

- `README.md` — visión, instalación y uso
- `docs/FORMAT.md` — formato estable de las notas (frontmatter, estados,
  enriquecimiento, versión de esquema)
- `docs/ARCHITECTURE.md` — módulos, decisiones y puntos de extensión
- `docs/DEPLOY.md` — despliegue en la nube paso a paso
- `AGENTS.md` — principios de desarrollo del proyecto

### Próximos pasos previstos

1. Enlaces `[[Relacionadas]]` entre notas que comparten etiquetas
2. Obsidian como visor sobre la carpeta de Drive
3. Embeddings y búsqueda semántica
4. Chat sobre la biblioteca (RAG)
5. Destilados periódicos por temática (Maps of Content)
