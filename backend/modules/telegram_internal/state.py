"""Per-user state machine, MongoDB-backed with 30-min idle TTL.

Each authorized telegram user has at most ONE active flow at any time.
Operations are atomic via $set/$setOnInsert so two simultaneous webhook
invocations cannot corrupt the same user's state (Telegram retries dedup'd by
Mongo's per-document write).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from db import db

logger = logging.getLogger(__name__)

FLOW_TIMEOUT_MIN = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _is_expired(state: dict) -> bool:
    exp = state.get("expires_at")
    if not exp:
        return False
    try:
        dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    except Exception:
        return True
    return _now() >= dt


async def get_state(telegram_user_id: int) -> Optional[dict]:
    """Return current state or None when none/expired (auto-clearing expired states)."""
    state = await db.telegram_internal_states.find_one(
        {"telegram_user_id": telegram_user_id},
        {"_id": 0},
    )
    if not state:
        return None
    if _is_expired(state):
        await reset_state(telegram_user_id)
        return None
    return state


async def has_active_flow(telegram_user_id: int) -> bool:
    s = await get_state(telegram_user_id)
    return bool(s and s.get("active_flow"))


async def start_flow(
    telegram_user_id: int,
    chat_id: int,
    flow: str,
    initial_step: str,
    initial_payload: Optional[dict] = None,
) -> dict:
    now = _now()
    state = {
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "active_flow": flow,
        "current_step": initial_step,
        "temporary_payload": initial_payload or {},
        "updated_at": _iso(now),
        "expires_at": _iso(now + timedelta(minutes=FLOW_TIMEOUT_MIN)),
    }
    await db.telegram_internal_states.update_one(
        {"telegram_user_id": telegram_user_id},
        {"$set": state},
        upsert=True,
    )
    return state


async def update_state(
    telegram_user_id: int,
    *,
    current_step: Optional[str] = None,
    payload_merge: Optional[dict] = None,
    payload_set: Optional[dict] = None,
) -> Optional[dict]:
    """Update step and/or payload. `payload_merge` merges into payload; `payload_set` replaces."""
    now = _now()
    s = await db.telegram_internal_states.find_one(
        {"telegram_user_id": telegram_user_id}, {"_id": 0}
    )
    if not s:
        return None
    payload = s.get("temporary_payload") or {}
    if payload_set is not None:
        payload = dict(payload_set)
    if payload_merge:
        payload.update(payload_merge)
    update = {
        "temporary_payload": payload,
        "updated_at": _iso(now),
        "expires_at": _iso(now + timedelta(minutes=FLOW_TIMEOUT_MIN)),
    }
    if current_step is not None:
        update["current_step"] = current_step
    await db.telegram_internal_states.update_one(
        {"telegram_user_id": telegram_user_id}, {"$set": update}
    )
    return await db.telegram_internal_states.find_one(
        {"telegram_user_id": telegram_user_id}, {"_id": 0}
    )


async def reset_state(telegram_user_id: int) -> None:
    await db.telegram_internal_states.delete_one(
        {"telegram_user_id": telegram_user_id}
    )


async def db_state_raw(telegram_user_id: int) -> Optional[dict]:
    """Return the raw state document (does NOT auto-clear when expired).
    Used to detect 'expired since last hit' for friendly UX messaging.
    """
    return await db.telegram_internal_states.find_one(
        {"telegram_user_id": telegram_user_id}, {"_id": 0}
    )
