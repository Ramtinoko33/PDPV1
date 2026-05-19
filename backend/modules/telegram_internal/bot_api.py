"""Telegram Bot API client — scoped to TELEGRAM_INTERNAL_BOT_TOKEN."""
import os
import logging
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def _token() -> str:
    return os.environ.get("TELEGRAM_INTERNAL_BOT_TOKEN", "")


def is_configured() -> bool:
    return bool(_token())


async def _post(method: str, payload: dict) -> Optional[dict]:
    token = _token()
    if not token:
        logger.error("TELEGRAM_INTERNAL_BOT_TOKEN missing; cannot call %s", method)
        return None
    url = f"{API_BASE}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.warning("Telegram %s -> %s: %s", method, r.status_code, r.text[:300])
                return None
            return r.json()
    except Exception as e:
        logger.error("Telegram %s failed: %s", method, e)
        return None


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
    disable_web_page_preview: bool = True,
) -> Optional[dict]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await _post("sendMessage", payload)


async def answer_callback_query(callback_query_id: str, text: Optional[str] = None) -> Optional[dict]:
    payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return await _post("answerCallbackQuery", payload)


async def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
) -> Optional[dict]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await _post("editMessageText", payload)


def inline_keyboard(rows: List[List[Dict[str, str]]]) -> dict:
    """Build an inline keyboard markup.

    Each row is a list of button dicts with at least {text, callback_data} or {text, url}.
    """
    return {"inline_keyboard": rows}


async def set_webhook(url: str, secret_token: Optional[str] = None) -> Optional[dict]:
    """Register the webhook URL with Telegram. Returns the API response or None."""
    payload: Dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return await _post("setWebhook", payload)


async def get_me() -> Optional[dict]:
    return await _post("getMe", {})


async def download_file(file_id: str) -> Optional[bytes]:
    """Download a file (photo/voice/document) using the internal bot's token.

    Returns bytes or None on failure. Never raises.
    """
    token = _token()
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            meta = await client.get(
                f"{API_BASE}/bot{token}/getFile", params={"file_id": file_id}
            )
            meta.raise_for_status()
            file_path = ((meta.json() or {}).get("result") or {}).get("file_path")
            if not file_path:
                return None
            r = await client.get(f"{API_BASE}/file/bot{token}/{file_path}")
            r.raise_for_status()
            return r.content
    except Exception as e:
        logger.warning("download_file %s failed: %s", file_id, e)
        return None
