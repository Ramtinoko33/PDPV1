"""Startup helpers for the internal bot module."""
import asyncio
import logging
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)


async def ensure_indexes():
    """Idempotent index creation for internal bot collections.

    - telegram_processed_updates.update_id UNIQUE (dedupe race-safe)
    - telegram_processed_updates.received_at TTL 7d (cleanup)
    - telegram_alerts_states.chat_id UNIQUE (state persistence)
    - telegram_internal_logs.update_id ASC (debug lookup)
    - renting_bot_state.chat_id UNIQUE (Sprint 1 phase 0B)
    - renting_bot_state.updated_at DESC (analytics / debug)
    - renting_bot_state.expires_at ASC (TTL index CREATED but not activated;
      expireAfterSeconds is set to a very large value to keep it inert until
      real flow-duration is measured in Sprint 2).
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
        # Renting bot state (Sprint 1 phase 0B).
        await db.renting_bot_state.create_index(
            [("chat_id", ASCENDING)], unique=True, name="uniq_chat_id"
        )
        await db.renting_bot_state.create_index(
            [("updated_at", DESCENDING)], name="idx_updated_at"
        )
        # TTL index: created with a very large expireAfterSeconds so it is
        # effectively inert until Sprint 2, where we will measure the p95
        # flow duration and adjust it. Docs still get `expires_at` written.
        await db.renting_bot_state.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=365 * 86400,   # 1 year — inert placeholder
            name="ttl_expires_at_inert"
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


async def prime_renting_state_cache():
    """Load persisted Renting states into memory on startup.

    Also rearms watchdog tasks for any non-idle state based on last_activity.
    """
    try:
        from modules.renting import service as _renting
        await _renting._states.ensure_loaded()
        rearmed = 0
        now_ts = datetime.now(timezone.utc).timestamp()
        for chat_id, state in list(_renting._states.items()):
            if not state:
                continue
            current = state.get("state")
            if current is None or current == _renting.STATE_IDLE:
                continue
            last_activity = float(state.get("last_activity") or now_ts)
            elapsed = now_ts - last_activity
            remaining = _renting.INACTIVITY_TIMEOUT_SEC - elapsed
            if remaining <= 0:
                # Session already stale on restart — reset silently, keep the
                # draft in `renting_records` for manual resume.
                _renting._reset(int(chat_id))
                continue
            # Rearm a fresh watchdog. We cannot restore the previous asyncio
            # Task; a brand-new one is scheduled for the remaining time.
            try:
                task = asyncio.get_event_loop().create_task(
                    _renting._watchdog(int(chat_id))
                )
                state["watchdog_task"] = task
                rearmed += 1
            except RuntimeError:
                pass  # no running loop in test context
        logger.info("Renting states loaded (%d rearmed watchdogs)", rearmed)
    except Exception as e:
        logger.warning("prime_renting_state_cache failed: %s", e)
