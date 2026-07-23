"""Structured logging for the internal bot.

Sprint 2 / S2-C — every log doc now carries a `module` field. Never stores
tokens, URLs, file_paths, base64 payloads or full message content.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from db import db

logger = logging.getLogger(__name__)

# Modules allowed in logs. `unknown` is a fallback for legacy events / edge cases.
ALLOWED_MODULES = {"pre_ticket", "renting", "assistencias", "mech_alert", "admin", "unknown"}

# Map of active_flow → module. Keep 1:1 so future flows can be added easily.
FLOW_TO_MODULE = {
    "pre_ticket":   "pre_ticket",
    "renting":      "renting",
    "assistencias": "assistencias",
    "mech_alert":   "mech_alert",
}


def module_for(active_flow: Optional[str], explicit: Optional[str] = None) -> str:
    """Return a validated module name.

    Priority: explicit → derived from active_flow → 'unknown'.
    """
    if explicit and explicit in ALLOWED_MODULES:
        return explicit
    if active_flow and active_flow in FLOW_TO_MODULE:
        return FLOW_TO_MODULE[active_flow]
    return "unknown"


async def log_event(
    telegram_user_id: Optional[int],
    chat_id: Optional[int],
    message_type: str,
    active_flow: Optional[str] = None,
    current_step: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
    extra: Optional[dict] = None,
    module: Optional[str] = None,
    callback_action: Optional[str] = None,
    internal_user_id: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
    error_id: Optional[str] = None,
) -> None:
    """Persist a single log row. Best-effort — never raises upstream."""
    try:
        # Sanitize `extra` — refuse well-known dangerous fields.
        BLOCKED_KEYS = {"token", "bot_token", "file_path", "url_with_token", "bytes", "base64"}
        clean_extra = None
        if extra:
            clean_extra = {k: v for k, v in extra.items() if k not in BLOCKED_KEYS}
        doc = {
            "id": str(uuid.uuid4()),
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "message_type": message_type,
            "module": module_for(active_flow, module),
            "active_flow": active_flow,
            "current_step": current_step,
            "callback_action": callback_action,
            "internal_user_id": internal_user_id,
            "processing_time_ms": processing_time_ms,
            "error_id": error_id,
            "success": success,
            "error": error,
            "extra": clean_extra or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.telegram_internal_logs.insert_one(doc)
    except Exception as e:
        logger.warning("telegram_internal log failed: %s", e)
