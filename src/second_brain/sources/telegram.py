"""Fuente Telegram: bot de captura basado en long polling.

No requiere servidor público ni webhook. Además de capturar (texto, URLs,
imágenes, notas de voz, PDFs y cualquier otro archivo como comodín), el bot
es la consola de operación del usuario: /buscar, /estado, /enrich,
/reprocess, y un parte de estado diario.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import mimetypes
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from second_brain import report
from second_brain.config import Config
from second_brain.models import Capture
from second_brain.pipeline import Pipeline
from second_brain.processors.url import is_probable_url, normalize_url

log = logging.getLogger(__name__)

REPORT_TIME = dt.time(hour=21, minute=0, tzinfo=ZoneInfo("Europe/Madrid"))
MAX_DOWNLOAD_BYTES = 19_000_000  # límite práctico de la Bot API (20 MB)

WELCOME = (
    "Hola 👋 Envíame cualquier cosa y la guardaré en tu biblioteca como "
    "Markdown enriquecido:\n\n"
    "• Texto → nota literal\n"
    "• URL → contenido extraído (web, X/Twitter, YouTube...)\n"
    "• Imagen → original + OCR + descripción IA\n"
    "• Nota de voz o audio → transcripción\n"
    "• PDF → texto extraído\n"
    "• Otros archivos → se guardan a la espera de soporte\n\n"
    "Comandos:\n"
    "/buscar <términos> — buscar en la biblioteca\n"
    "/estado — salud del sistema\n"
    "/sugerencias — temas recurrentes sin categoría\n"
    "/aprobar <categoria> — añadirla a tu taxonomía\n"
    "/descartar <categoria> — no volver a proponerla\n"
    "/reprocess — reintentar notas pendientes\n"
    "/enrich — re-enriquecer notas obsoletas"
)

COMMANDS = [
    BotCommand("buscar", "Buscar en la biblioteca"),
    BotCommand("estado", "Estado del sistema"),
    BotCommand("sugerencias", "Temas recurrentes sin categoría"),
    BotCommand("aprobar", "Añadir categoría a la taxonomía"),
    BotCommand("descartar", "Descartar una categoría sugerida"),
    BotCommand("reprocess", "Reintentar notas pendientes"),
    BotCommand("enrich", "Re-enriquecer notas obsoletas"),
    BotCommand("start", "Ayuda"),
]


class TelegramSource:
    def __init__(self, config: Config):
        self.config = config
        self.pipeline = Pipeline(config)

    # -- helpers ----------------------------------------------------------
    def _authorized(self, update: Update) -> bool:
        allowed = self.config.allowed_user_ids
        if not allowed:
            return True
        user = update.effective_user
        if user and user.id in allowed:
            return True
        log.warning("Mensaje rechazado de usuario no autorizado: %s", user)
        return False

    @staticmethod
    def _metadata(update: Update) -> dict:
        msg, user = update.effective_message, update.effective_user
        return {
            "chat_id": msg.chat_id,
            "message_id": msg.message_id,
            "sender": (user.username or user.full_name) if user else None,
        }

    def _rel(self, path) -> str:
        try:
            return str(path.relative_to(self.config.library_dir))
        except ValueError:
            return str(path)

    async def _capture_and_reply(self, update: Update, capture: Capture) -> None:
        outcome = await asyncio.to_thread(self.pipeline.process, capture)
        rel = self._rel(outcome.path)
        if outcome.status == "complete":
            await update.effective_message.reply_text(f"✅ Guardado: {rel}")
        else:
            await update.effective_message.reply_text(
                f"📥 Guardado (procesado pendiente): {rel}\n"
                "Envía /reprocess para reintentarlo."
            )

    async def _download(self, attachment) -> bytes | None:
        size = getattr(attachment, "file_size", 0) or 0
        if size >= MAX_DOWNLOAD_BYTES:
            return None
        file = await attachment.get_file()
        return bytes(await file.download_as_bytearray())

    # -- capturas ----------------------------------------------------------
    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = update.effective_message.text or ""
        now = datetime.now().astimezone()
        if is_probable_url(text):
            url = normalize_url(text)
            duplicate = await asyncio.to_thread(self.pipeline.find_duplicate_url, url)
            if duplicate:
                await update.effective_message.reply_text(
                    f"🔁 Ya está en tu biblioteca: «{duplicate['title']}»\n"
                    f"{duplicate['path']}"
                )
                return
            capture = Capture(
                kind="url",
                source="telegram",
                captured_at=now,
                url=url,
                metadata=self._metadata(update),
            )
        else:
            capture = Capture(
                kind="text",
                source="telegram",
                captured_at=now,
                text=text,
                metadata=self._metadata(update),
            )
        await self._capture_and_reply(update, capture)

    async def on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        msg = update.effective_message
        photo = msg.photo[-1]  # mayor resolución disponible
        data = await self._download(photo)
        capture = Capture(
            kind="image",
            source="telegram",
            captured_at=datetime.now().astimezone(),
            text=msg.caption,
            file_bytes=data,
            file_name=f"{photo.file_unique_id}.jpg",
            mime_type="image/jpeg",
            metadata=self._metadata(update),
        )
        await self._capture_and_reply(update, capture)

    async def on_image_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._document_capture(update, kind="image")

    async def on_pdf_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._document_capture(update, kind="pdf")

    async def _document_capture(self, update: Update, kind: str) -> None:
        if not self._authorized(update):
            return
        msg = update.effective_message
        document = msg.document
        data = await self._download(document)
        if data is None:
            await msg.reply_text("⚠️ Archivo demasiado grande (límite 20 MB).")
            return
        capture = Capture(
            kind=kind,
            source="telegram",
            captured_at=datetime.now().astimezone(),
            text=msg.caption,
            file_bytes=data,
            file_name=document.file_name or f"{document.file_unique_id}.bin",
            mime_type=document.mime_type,
            metadata=self._metadata(update),
        )
        await self._capture_and_reply(update, capture)

    async def on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        msg = update.effective_message
        media = msg.voice or msg.audio
        data = await self._download(media)
        if data is None:
            await msg.reply_text("⚠️ Audio demasiado grande (límite 20 MB).")
            return
        file_name = getattr(media, "file_name", None) or f"{media.file_unique_id}.oga"
        capture = Capture(
            kind="audio",
            source="telegram",
            captured_at=datetime.now().astimezone(),
            text=msg.caption,
            file_bytes=data,
            file_name=file_name,
            mime_type=getattr(media, "mime_type", None),
            metadata=self._metadata(update),
        )
        await self._capture_and_reply(update, capture)

    async def on_unsupported(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Comodín: nunca ignorar un mensaje en silencio."""
        if not self._authorized(update):
            return
        msg = update.effective_message
        attachment = msg.effective_attachment
        if isinstance(attachment, tuple):  # p. ej. photos ya cubiertas
            attachment = attachment[-1] if attachment else None

        data = None
        file_name = None
        mime = getattr(attachment, "mime_type", None) if attachment else None
        if attachment is not None and getattr(attachment, "file_id", None):
            try:
                data = await self._download(attachment)
            except Exception:  # noqa: BLE001
                data = None
            if data is not None:
                ext = mimetypes.guess_extension(mime or "") or ".bin"
                file_name = (
                    getattr(attachment, "file_name", None)
                    or f"{attachment.file_unique_id}{ext}"
                )

        caption = msg.caption or msg.text
        if data is None and not caption:
            await msg.reply_text(
                "🤷 Este tipo de mensaje aún no puedo procesarlo y no contiene "
                "nada que pueda guardar."
            )
            return

        capture = Capture(
            kind="file" if data is not None else "text",
            source="telegram",
            captured_at=datetime.now().astimezone(),
            text=caption,
            file_bytes=data,
            file_name=file_name,
            mime_type=mime,
            metadata=self._metadata(update),
        )
        await self._capture_and_reply(update, capture)

    # -- comandos ----------------------------------------------------------
    async def on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.effective_message.reply_text(WELCOME)

    async def on_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        query = " ".join(context.args or [])
        if not query:
            await update.effective_message.reply_text("Uso: /buscar <términos>")
            return
        from second_brain.index import sqlite_index

        def _search():
            try:
                return sqlite_index.search(
                    self.config.library_dir, sqlite_index.safe_query(query), limit=5
                )
            except FileNotFoundError:
                sqlite_index.rebuild(self.config.library_dir)
                return sqlite_index.search(
                    self.config.library_dir, sqlite_index.safe_query(query), limit=5
                )

        results = await asyncio.to_thread(_search)
        if not results:
            await update.effective_message.reply_text(f"Sin resultados para «{query}».")
            return
        blocks = [
            f"• {r['title']}  [{r['type']}]\n  {r['snippet']}\n  📄 {r['path']}"
            for r in results
        ]
        await update.effective_message.reply_text(
            f"🔎 Resultados para «{query}»:\n\n" + "\n\n".join(blocks)
        )

    async def on_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = await asyncio.to_thread(report.build_report, self.config)
        await update.effective_message.reply_text(text)

    async def on_reprocess(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._authorized(update):
            return
        outcomes = await asyncio.to_thread(self.pipeline.reprocess)
        if not outcomes:
            await update.effective_message.reply_text("No hay notas pendientes. ✅")
            return
        still = sum(1 for o in outcomes if o.status == "pending")
        await update.effective_message.reply_text(
            f"♻️ Reprocesadas {len(outcomes)} notas · siguen pendientes: {still}"
        )

    async def on_enrich(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        await update.effective_message.reply_text("🧠 Enriqueciendo…")
        try:
            outcomes = await asyncio.to_thread(self.pipeline.enrich_library)
        except RuntimeError as exc:
            await update.effective_message.reply_text(f"⚠️ {exc}")
            return
        if not outcomes:
            await update.effective_message.reply_text(
                "Todo al día con el modelo de conocimiento. ✅"
            )
            return
        errors = sum(1 for _, s in outcomes if s == "error")
        await update.effective_message.reply_text(
            f"🧠 Enriquecidas {len(outcomes) - errors} notas · errores: {errors}"
        )

    async def on_suggestions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._authorized(update):
            return
        from second_brain.enrich import knowledge_model, suggestions

        def _collect():
            model = knowledge_model.ensure_model(self.config.library_dir)
            return suggestions.aggregate(self.config.library_dir, model)

        found = await asyncio.to_thread(_collect)
        if not found:
            await update.effective_message.reply_text(
                "No hay temas recurrentes sin categoría por ahora. "
                "Las propuestas aparecen cuando varios contenidos piden lo mismo."
            )
            return
        blocks = [
            f"• `{s.slug}` — {s.count} notas\n  p. ej.: " + "; ".join(s.titles)
            for s in found[:8]
        ]
        await update.effective_message.reply_text(
            "💡 Temas recurrentes sin categoría oficial:\n\n"
            + "\n\n".join(blocks)
            + "\n\nAñade con /aprobar <categoria> o silencia con /descartar <categoria>."
        )

    async def on_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        slug = " ".join(context.args or []).strip()
        if not slug:
            await update.effective_message.reply_text("Uso: /aprobar <categoria>")
            return
        from second_brain.enrich import knowledge_model

        try:
            await asyncio.to_thread(
                knowledge_model.approve_category, self.config.library_dir, slug
            )
        except ValueError as exc:
            await update.effective_message.reply_text(f"⚠️ {exc}")
            return
        await update.effective_message.reply_text(
            f"✅ «{slug}» añadida a tu taxonomía (knowledge_model.md).\n"
            "Envía /enrich cuando quieras reclasificar la biblioteca con ella."
        )

    async def on_dismiss(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        slug = " ".join(context.args or []).strip()
        if not slug:
            await update.effective_message.reply_text("Uso: /descartar <categoria>")
            return
        from second_brain.enrich import knowledge_model

        try:
            await asyncio.to_thread(
                knowledge_model.dismiss_category, self.config.library_dir, slug
            )
        except ValueError as exc:
            await update.effective_message.reply_text(f"⚠️ {exc}")
            return
        await update.effective_message.reply_text(
            f"🔕 «{slug}» descartada: no volverá a proponerse."
        )

    # -- parte diario --------------------------------------------------------
    async def daily_report(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = await asyncio.to_thread(report.build_report, self.config)
        await context.bot.send_message(chat_id=context.job.chat_id, text=text)


def build_application(config: Config) -> Application:
    source = TelegramSource(config)

    async def post_init(app: Application) -> None:
        try:
            await app.bot.set_my_commands(COMMANDS)
        except Exception:  # noqa: BLE001
            log.warning("No se pudieron registrar los comandos del bot")
        # índice fresco al arrancar: habilita /buscar, dedupe y relaciones
        from second_brain.index import sqlite_index

        count = await asyncio.to_thread(sqlite_index.rebuild, config.library_dir)
        log.info("Índice reconstruido al arrancar: %d notas", count)

    app = ApplicationBuilder().token(config.telegram_token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", source.on_start))
    app.add_handler(CommandHandler("buscar", source.on_search))
    app.add_handler(CommandHandler("estado", source.on_status))
    app.add_handler(CommandHandler("sugerencias", source.on_suggestions))
    app.add_handler(CommandHandler("aprobar", source.on_approve))
    app.add_handler(CommandHandler("descartar", source.on_dismiss))
    app.add_handler(CommandHandler("reprocess", source.on_reprocess))
    app.add_handler(CommandHandler("enrich", source.on_enrich))
    app.add_handler(MessageHandler(filters.PHOTO, source.on_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, source.on_image_document))
    app.add_handler(MessageHandler(filters.Document.PDF, source.on_pdf_document))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, source.on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, source.on_text))
    # comodín: SIEMPRE el último — solo recibe lo que nadie más atendió
    app.add_handler(MessageHandler(~filters.COMMAND, source.on_unsupported))

    if config.allowed_user_ids and app.job_queue:
        app.job_queue.run_daily(
            source.daily_report,
            time=REPORT_TIME,
            chat_id=sorted(config.allowed_user_ids)[0],
        )

    return app


def run_bot(config: Config) -> None:
    if not config.telegram_token:
        raise SystemExit(
            "Falta TELEGRAM_BOT_TOKEN. Crea un bot con @BotFather y configura .env "
            "(ver .env.example)."
        )
    if not config.allowed_user_ids:
        log.warning(
            "TELEGRAM_ALLOWED_USER_IDS está vacío: CUALQUIER usuario de Telegram "
            "podrá escribir en tu biblioteca. Configúralo en .env."
        )
    app = build_application(config)
    log.info("Bot iniciado. Biblioteca: %s", config.library_dir.resolve())
    app.run_polling(allowed_updates=Update.ALL_TYPES)
