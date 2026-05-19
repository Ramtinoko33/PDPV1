"""Structured logging for the internal bot.

Writes one document per inbound update (or relevant step transition) to
`telegram_internal_logs`. Designed to be lightweight (best-effort, never fails
the webhook).
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from db import db

logger = logging.getLogger(__name__)


async def log_event(
    telegram_user_id: Optional[int],
    chat_id: Optional[int],
    message_type: str,
    active_flow: Optional[str] = None,
    current_step: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "message_type": message_type,
            "active_flow": active_flow,
            "current_step": current_step,
            "success": success,
            "error": error,
            "extra": extra or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.telegram_internal_logs.insert_one(doc)
    except Exception as e:
        # Never let logging fail the bot
        logger.warning("telegram_internal log failed: %s", e)
