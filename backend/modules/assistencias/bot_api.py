"""Assistências module — Telegram Bot API wrapper.

Sprint 1 / Phase 0: refactored to delegate ALL outbound Telegram calls to the
unified adapter (modules.telegram_internal.bot_api) using
TELEGRAM_INTERNAL_BOT_TOKEN. The public API of this module is preserved so
that no caller in modules/assistencias/service.py needs to change.
"""
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# LEGACY placeholders — kept only to allow `git revert` rollback of Sprint 1.
# Not read by any runtime code; every function below delegates to the
# unified adapter which uses only TELEGRAM_INTERNAL_BOT_TOKEN.
BOT_TOKEN = os.environ.get("TELEGRAM_ASSISTENCIAS_BOT_TOKEN", "")  # deprecated
WEBHOOK_SECRET = os.environ.get("TELEGRAM_ASSISTENCIAS_WEBHOOK_SECRET", "")  # deprecated
TELEGRAM_API = "https://api.telegram.org/bot"  # deprecated


def is_configured() -> bool:
    from modules.telegram_internal import bot_api as _adapter
    return _adapter.is_configured()


async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> bool:
    from modules.telegram_internal import bot_api as _adapter
    resp = await _adapter.send_message(
        chat_id=chat_id, text=text, reply_markup=reply_markup, module="assistencias"
    )
    return resp is not None


async def send_document(
    chat_id: int, file_bytes: bytes, filename: str, caption: str = ""
) -> bool:
    from modules.telegram_internal import bot_api as _adapter
    resp = await _adapter.send_document(
        chat_id=chat_id, file_bytes=file_bytes, filename=filename,
        caption=caption, module="assistencias",
    )
    return resp is not None


async def answer_callback_query(callback_id: str, text: str = "OK") -> None:
    from modules.telegram_internal import bot_api as _adapter
    if not callback_id:
        return
    await _adapter.answer_callback_query(callback_id, text=text, module="assistencias")


async def download_file(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Returns (bytes, mime_type) or (None, None)."""
    from modules.telegram_internal import bot_api as _adapter
    result = await _adapter.download_media(
        file_id, max_bytes=20 * 1024 * 1024, module="assistencias"
    )
    if not result:
        return None, None
    return result[0], result[1]


async def set_webhook(url: str) -> Optional[dict]:
    """Deprecated. Real setup: /api/telegram/internal/webhook/configure."""
    from modules.telegram_internal import bot_api as _adapter
    # Still callable so the legacy admin UI (AdminAssistenciasUsers.js) does
    # not 500; but it now configures the INTERNAL bot's webhook.
    return await _adapter.set_webhook(url, secret_token=None)


async def get_me() -> Optional[dict]:
    from modules.telegram_internal import bot_api as _adapter
    return await _adapter.get_me()
