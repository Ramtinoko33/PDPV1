"""Assistências module — Telegram Bot API wrapper (lightweight, mirrors renting style)."""
import os
import json
import logging
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_ASSISTENCIAS_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_ASSISTENCIAS_WEBHOOK_SECRET", "")
TELEGRAM_API = "https://api.telegram.org/bot"


def is_configured() -> bool:
    return bool(BOT_TOKEN)


async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> bool:
    if not BOT_TOKEN:
        logger.error("[ASSIST_BOT] TELEGRAM_ASSISTENCIAS_BOT_TOKEN not configured")
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage", json=payload)
            if r.status_code != 200:
                logger.error(f"[ASSIST_BOT] sendMessage failed: {r.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[ASSIST_BOT] sendMessage error: {e}")
        return False


async def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str = "") -> bool:
    if not BOT_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            files = {"document": (filename, file_bytes, "application/pdf")}
            data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"}
            r = await client.post(
                f"{TELEGRAM_API}{BOT_TOKEN}/sendDocument", data=data, files=files
            )
            if r.status_code != 200:
                logger.error(f"[ASSIST_BOT] sendDocument failed: {r.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[ASSIST_BOT] sendDocument error: {e}")
        return False


async def answer_callback_query(callback_id: str, text: str = "OK") -> None:
    if not BOT_TOKEN or not callback_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{TELEGRAM_API}{BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text},
            )
    except Exception:
        pass


async def download_file(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Returns (bytes, mime_type) or (None, None)."""
    if not BOT_TOKEN:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{TELEGRAM_API}{BOT_TOKEN}/getFile", params={"file_id": file_id}
            )
            if r.status_code != 200:
                return None, None
            file_path = r.json().get("result", {}).get("file_path")
            if not file_path:
                return None, None
            r2 = await client.get(
                f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            )
            if r2.status_code == 200:
                ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
                mime_map = {
                    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg",
                    "m4a": "audio/mp4", "wav": "audio/wav",
                }
                return r2.content, mime_map.get(ext, "application/octet-stream")
    except Exception as e:
        logger.error(f"[ASSIST_BOT] download_file error: {e}")
    return None, None


async def set_webhook(url: str) -> Optional[dict]:
    if not BOT_TOKEN:
        return None
    payload = {"url": url, "allowed_updates": ["message", "callback_query"]}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{TELEGRAM_API}{BOT_TOKEN}/setWebhook", json=payload)
            return r.json()
    except Exception as e:
        logger.error(f"[ASSIST_BOT] setWebhook error: {e}")
        return None


async def get_me() -> Optional[dict]:
    if not BOT_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{TELEGRAM_API}{BOT_TOKEN}/getMe")
            return r.json()
    except Exception:
        return None
