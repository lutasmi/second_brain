"""Fuente Telegram: bot de captura basado en long polling.

No requiere servidor público ni webhook: el bot consulta a Telegram y
convierte cada mensaje (texto, URL o imagen) en una Capture para el pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from second_brain.config import Config
from second_brain.models import Capture
from second_brain.pipeline import Pipeline
from second_brain.processors.url import is_probable_url, normalize_url

log = logging.getLogger(__name__)

WELCOME = (
    "Hola 👋 Envíame texto, un enlace o una imagen y lo guardaré en tu "
    "biblioteca como Markdown.\n\n"
    "• Texto → nota literal\n"
    "• URL → contenido extraído (web, X/Twitter, YouTube, LinkedIn)\n"
    "• Imagen → original + OCR + descripción IA"
)


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

    async def _capture_and_reply(self, update: Update, capture: Capture) -> None:
        outcome = await asyncio.to_thread(self.pipeline.process, capture)
        try:
            rel = outcome.path.relative_to(self.config.library_dir)
        except ValueError:
            rel = outcome.path
        if outcome.status == "complete":
            await update.effective_message.reply_text(f"✅ Guardado: {rel}")
        else:
            await update.effective_message.reply_text(
                f"📥 Guardado con extracción pendiente: {rel}\n"
                "Se reintentará con `second-brain reprocess`."
            )

    # -- handlers ----------------------------------------------------------
    async def on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.effective_message.reply_text(WELCOME)

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = update.effective_message.text or ""
        now = datetime.now().astimezone()
        if is_probable_url(text):
            capture = Capture(
                kind="url",
                source="telegram",
                captured_at=now,
                url=normalize_url(text),
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
        file = await photo.get_file()
        data = bytes(await file.download_as_bytearray())
        capture = Capture(
            kind="image",
            source="telegram",
            captured_at=datetime.now().astimezone(),
            text=msg.caption,
            file_bytes=data,
            file_name=f"{photo.file_unique_id}.jpg",
            metadata=self._metadata(update),
        )
        await self._capture_and_reply(update, capture)

    async def on_image_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._authorized(update):
            return
        msg = update.effective_message
        document = msg.document
        file = await document.get_file()
        data = bytes(await file.download_as_bytearray())
        capture = Capture(
            kind="image",
            source="telegram",
            captured_at=datetime.now().astimezone(),
            text=msg.caption,
            file_bytes=data,
            file_name=document.file_name or f"{document.file_unique_id}.bin",
            metadata=self._metadata(update),
        )
        await self._capture_and_reply(update, capture)


def build_application(config: Config) -> Application:
    source = TelegramSource(config)
    app = ApplicationBuilder().token(config.telegram_token).build()
    app.add_handler(CommandHandler("start", source.on_start))
    app.add_handler(MessageHandler(filters.PHOTO, source.on_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, source.on_image_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, source.on_text))
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
