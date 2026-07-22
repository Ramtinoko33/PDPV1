"""Telegram Bot API client — scoped to TELEGRAM_INTERNAL_BOT_TOKEN.

Sprint 1 / Phase 0: consolidated adapter for ALL outbound Telegram calls.
Regras:
  - Nunca devolver URLs Telegram (contêm o token).
  - Nunca fazer log de tokens, URLs completas, file_path bruto, bytes ou conteúdo.
  - Logging estruturado com schema fechado (ver `_log_call`).
  - Retry único em 5xx/timeout; zero retry em 4xx.
"""
import os
import time
import uuid
import logging
import mimetypes
from typing import Optional, List, Dict, Any, Tuple, Set

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
_TIMEOUT = 15
_DOWNLOAD_TIMEOUT = 30
_MAX_RETRIES = 1
_RETRY_BACKOFF_S = 0.5


def _token() -> str:
    return os.environ.get("TELEGRAM_INTERNAL_BOT_TOKEN", "")


def is_configured() -> bool:
    return bool(_token())


# ============== STRUCTURED LOGGING ==============
def _log_call(
    direction: str,
    method: str,
    module: str,
    chat_id: Optional[int],
    success: bool,
    http_status: Optional[int],
    processing_time_ms: int,
    error_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Emit a structured log line. Schema is closed: no free-form strings.

    Never accepts tokens, URLs, file_paths, message content or bytes.
    """
    record = {
        "direction": direction,
        "method": method,
        "module": module,
        "chat_id": chat_id,
        "success": success,
        "http_status": http_status,
        "processing_time_ms": processing_time_ms,
        "error_id": error_id,
        "extra": extra or {},
    }
    if success:
        logger.debug("tg_adapter %s", record)
    else:
        logger.warning("tg_adapter %s", record)


async def _post(
    method: str,
    payload: dict,
    module: str = "unknown",
    chat_id: Optional[int] = None,
) -> Optional[dict]:
    token = _token()
    if not token:
        _log_call("out", method, module, chat_id, False, None, 0,
                  error_id="no_token", extra={"reason": "TELEGRAM_INTERNAL_BOT_TOKEN missing"})
        return None
    url = f"{API_BASE}/bot{token}/{method}"

    attempts = 0
    start = time.perf_counter()
    while True:
        attempts += 1
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(url, json=payload)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                if r.status_code >= 500 and attempts <= _MAX_RETRIES:
                    _log_call("out", method, module, chat_id, False,
                              r.status_code, elapsed_ms,
                              error_id="retry_5xx",
                              extra={"attempt": attempts})
                    await _sleep(_RETRY_BACKOFF_S)
                    continue
                if r.status_code >= 400:
                    err_id = uuid.uuid4().hex[:8]
                    _log_call("out", method, module, chat_id, False,
                              r.status_code, elapsed_ms, error_id=err_id,
                              extra={"attempt": attempts})
                    return None
                _log_call("out", method, module, chat_id, True,
                          r.status_code, elapsed_ms,
                          extra={"attempt": attempts})
                return r.json()
        except (httpx.TimeoutException, httpx.TransportError) as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if attempts <= _MAX_RETRIES:
                _log_call("out", method, module, chat_id, False, None,
                          elapsed_ms, error_id="retry_transport",
                          extra={"exc": type(e).__name__})
                await _sleep(_RETRY_BACKOFF_S)
                continue
            err_id = uuid.uuid4().hex[:8]
            _log_call("out", method, module, chat_id, False, None,
                      elapsed_ms, error_id=err_id,
                      extra={"exc": type(e).__name__})
            return None
        except Exception as e:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            err_id = uuid.uuid4().hex[:8]
            _log_call("out", method, module, chat_id, False, None,
                      elapsed_ms, error_id=err_id,
                      extra={"exc": type(e).__name__})
            return None


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


# ============== PUBLIC API — messaging ==============
async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
    disable_web_page_preview: bool = True,
    module: str = "unknown",
) -> Optional[dict]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await _post("sendMessage", payload, module=module, chat_id=chat_id)


async def answer_callback_query(
    callback_query_id: str,
    text: Optional[str] = None,
    module: str = "unknown",
) -> Optional[dict]:
    payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return await _post("answerCallbackQuery", payload, module=module)


async def answer_callback_query_ok(callback_query_id: str, module: str = "unknown") -> None:
    """Wrapper conveniente: responde OK sem alerta."""
    if not callback_query_id:
        return
    await answer_callback_query(callback_query_id, text=None, module=module)


async def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
    module: str = "unknown",
) -> Optional[dict]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await _post("editMessageText", payload, module=module, chat_id=chat_id)


def inline_keyboard(rows: List[List[Dict[str, str]]]) -> dict:
    return {"inline_keyboard": rows}


# ============== PUBLIC API — media out ==============
async def send_document(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str = "",
    parse_mode: str = "HTML",
    module: str = "unknown",
) -> Optional[dict]:
    token = _token()
    if not token:
        _log_call("out", "sendDocument", module, chat_id, False, None, 0,
                  error_id="no_token")
        return None
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
            files = {"document": (filename, file_bytes, "application/octet-stream")}
            data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": parse_mode}
            r = await client.post(
                f"{API_BASE}/bot{token}/sendDocument", data=data, files=files
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            success = r.status_code < 400
            _log_call("out", "sendDocument", module, chat_id, success,
                      r.status_code, elapsed_ms,
                      extra={"size": len(file_bytes)})
            return r.json() if success else None
    except Exception as e:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        _log_call("out", "sendDocument", module, chat_id, False, None,
                  elapsed_ms, error_id=uuid.uuid4().hex[:8],
                  extra={"exc": type(e).__name__})
        return None


async def send_photo(
    chat_id: int,
    photo_bytes: bytes,
    filename: str = "photo.jpg",
    caption: str = "",
    parse_mode: str = "HTML",
    module: str = "unknown",
) -> Optional[dict]:
    token = _token()
    if not token:
        _log_call("out", "sendPhoto", module, chat_id, False, None, 0,
                  error_id="no_token")
        return None
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
            files = {"photo": (filename, photo_bytes, "image/jpeg")}
            data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": parse_mode}
            r = await client.post(
                f"{API_BASE}/bot{token}/sendPhoto", data=data, files=files
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            success = r.status_code < 400
            _log_call("out", "sendPhoto", module, chat_id, success,
                      r.status_code, elapsed_ms,
                      extra={"size": len(photo_bytes)})
            return r.json() if success else None
    except Exception as e:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        _log_call("out", "sendPhoto", module, chat_id, False, None,
                  elapsed_ms, error_id=uuid.uuid4().hex[:8],
                  extra={"exc": type(e).__name__})
        return None


# ============== PUBLIC API — webhook / info ==============
async def set_webhook(url: str, secret_token: Optional[str] = None) -> Optional[dict]:
    payload: Dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return await _post("setWebhook", payload, module="admin")


async def get_me() -> Optional[dict]:
    return await _post("getMe", {}, module="admin")


async def get_webhook_info() -> Optional[dict]:
    return await _post("getWebhookInfo", {}, module="admin")


# ============== PUBLIC API — media in ==============
# Mime derived from file_path extension only. file_path itself is NEVER
# returned or logged. Any callers that need MIME receive it explicitly.
_EXT_TO_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif",
    "ogg": "audio/ogg", "oga": "audio/ogg",
    "mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav",
    "opus": "audio/ogg",
    "pdf": "application/pdf",
    "mp4": "video/mp4", "mov": "video/quicktime",
    "txt": "text/plain",
}


def _mime_from_file_path(file_path: str) -> str:
    if "." in file_path:
        ext = file_path.rsplit(".", 1)[-1].lower()
        m = _EXT_TO_MIME.get(ext)
        if m:
            return m
    guessed, _ = mimetypes.guess_type(file_path)
    return guessed or "application/octet-stream"


async def download_media(
    file_id: str,
    max_bytes: int = 20 * 1024 * 1024,
    allowed_mimes: Optional[Set[str]] = None,
    module: str = "unknown",
) -> Optional[Tuple[bytes, str]]:
    """Download a Telegram file safely.

    - Never returns a URL. Never logs the file_path.
    - Enforces max_bytes BEFORE downloading (via getFile.file_size).
    - If allowed_mimes is given and the file's mime is not in it, returns None.
    Returns (bytes, mime_type) or None.
    """
    token = _token()
    if not token or not file_id:
        _log_call("in", "getFile", module, None, False, None, 0,
                  error_id="no_token_or_id")
        return None

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
            meta = await client.get(
                f"{API_BASE}/bot{token}/getFile", params={"file_id": file_id}
            )
            if meta.status_code >= 400:
                _log_call("in", "getFile", module, None, False,
                          meta.status_code,
                          int((time.perf_counter() - start) * 1000),
                          error_id=uuid.uuid4().hex[:8])
                return None
            result = (meta.json() or {}).get("result") or {}
            file_path = result.get("file_path")
            file_size = int(result.get("file_size") or 0)
            if not file_path:
                _log_call("in", "getFile", module, None, False, None,
                          int((time.perf_counter() - start) * 1000),
                          error_id="no_file_path")
                return None
            if file_size and file_size > max_bytes:
                _log_call("in", "getFile", module, None, False, 200,
                          int((time.perf_counter() - start) * 1000),
                          error_id="size_exceeded",
                          extra={"file_size": file_size, "max_bytes": max_bytes})
                return None

            mime = _mime_from_file_path(file_path)
            if allowed_mimes is not None and mime not in allowed_mimes:
                _log_call("in", "getFile", module, None, False, 200,
                          int((time.perf_counter() - start) * 1000),
                          error_id="mime_not_allowed",
                          extra={"mime": mime})
                return None

            r = await client.get(f"{API_BASE}/file/bot{token}/{file_path}")
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if r.status_code >= 400:
                _log_call("in", "downloadFile", module, None, False,
                          r.status_code, elapsed_ms,
                          error_id=uuid.uuid4().hex[:8])
                return None
            data = r.content
            if len(data) > max_bytes:
                _log_call("in", "downloadFile", module, None, False, 200,
                          elapsed_ms, error_id="size_exceeded_actual",
                          extra={"downloaded": len(data), "max_bytes": max_bytes})
                return None
            _log_call("in", "downloadFile", module, None, True,
                      r.status_code, elapsed_ms,
                      extra={"size": len(data), "mime": mime})
            return data, mime
    except Exception as e:  # noqa: BLE001
        _log_call("in", "getFile", module, None, False, None,
                  int((time.perf_counter() - start) * 1000),
                  error_id=uuid.uuid4().hex[:8],
                  extra={"exc": type(e).__name__})
        return None


async def download_file(file_id: str, module: str = "unknown") -> Optional[bytes]:
    """Backwards-compatible wrapper: returns bytes only.
    Uses the safe download_media internally.
    """
    result = await download_media(file_id, module=module)
    if result is None:
        return None
    return result[0]
