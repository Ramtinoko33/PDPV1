"""Startup helpers for the internal bot module."""
import logging
from pymongo import ASCENDING

logger = logging.getLogger(__name__)


async def ensure_indexes():
    """Idempotent index creation for internal bot collections.

    - telegram_processed_updates.update_id UNIQUE (dedupe race-safe)
    - telegram_processed_updates.received_at TTL 7d (cleanup)
    - telegram_alerts_states.chat_id UNIQUE (state persistence)
    - telegram_internal_logs.update_id ASC (debug lookup)
    """
    from db import db
    try:
        await db.telegram_processed_updates.create_index(
            [("update_id", ASCENDING)], unique=True, name="uniq_update_id"
        )
        await db.telegram_processed_updates.create_index(
            [("received_at", ASCENDING)], expireAfterSeconds=7 * 86400,
            name="ttl_received_at_7d"
        )
        await db.telegram_alerts_states.create_index(
            [("chat_id", ASCENDING)], unique=True, name="uniq_chat_id"
        )
        await db.telegram_internal_logs.create_index(
            [("update_id", ASCENDING)], name="lookup_update_id"
        )
        logger.info("Telegram internal indexes ensured")
    except Exception as e:
        logger.warning("ensure_indexes failed (non-fatal): %s", e)


async def prime_alerts_state_cache():
    """Load persisted alerts states into memory on startup."""
    try:
        from modules.telegram_alerts.service import _conversation_states
        await _conversation_states.ensure_loaded()
        logger.info("Telegram alerts states loaded from MongoDB")
    except Exception as e:
        logger.warning("prime_alerts_state_cache failed: %s", e)
