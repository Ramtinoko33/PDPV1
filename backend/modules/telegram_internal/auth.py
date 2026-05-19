"""Authorization for PDPV Bot Interno.

Two layers:
- ENV bootstrap: TELEGRAM_INTERNAL_ALLOWED_USER_IDS (CSV of telegram_user_id)
  Always authorized (full access). Lets you grant first access without DB writes.
- DB collection `telegram_internal_authorized_users`:
    { telegram_user_id, name, role, allowed_flows: [...], active: bool, created_at }
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, List

from db import db

logger = logging.getLogger(__name__)

ALL_FLOWS = ["pre_ticket", "renting", "mech_alert"]


def _env_allowed_ids() -> set:
    raw = os.environ.get("TELEGRAM_INTERNAL_ALLOWED_USER_IDS", "") or ""
    out = set()
    for token in raw.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(int(token))
        except ValueError:
            logger.warning("Ignoring invalid telegram_user_id in env: %r", token)
    return out


async def get_authorized(telegram_user_id: int) -> Optional[dict]:
    """Return the user's authorization doc, or a synthetic one if env-bootstrapped.
    Returns None when the user is not allowed.
    """
    if telegram_user_id in _env_allowed_ids():
        return {
            "telegram_user_id": telegram_user_id,
            "name": "Env Admin",
            "role": "ADMIN",
            "allowed_flows": ALL_FLOWS,
            "active": True,
            "source": "env",
        }
    doc = await db.telegram_internal_authorized_users.find_one(
        {"telegram_user_id": telegram_user_id, "active": True},
        {"_id": 0},
    )
    if doc:
        doc["source"] = "db"
    return doc


async def is_flow_allowed(user_auth: dict, flow: str) -> bool:
    flows = user_auth.get("allowed_flows") or ALL_FLOWS
    return flow in flows


async def upsert_authorized_user(
    telegram_user_id: int,
    name: str,
    role: str = "AGENT",
    allowed_flows: Optional[List[str]] = None,
    active: bool = True,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    flows = list(allowed_flows) if allowed_flows else ALL_FLOWS
    doc = {
        "telegram_user_id": telegram_user_id,
        "name": name,
        "role": role,
        "allowed_flows": flows,
        "active": active,
        "updated_at": now,
    }
    await db.telegram_internal_authorized_users.update_one(
        {"telegram_user_id": telegram_user_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return doc


async def deactivate_user(telegram_user_id: int) -> bool:
    r = await db.telegram_internal_authorized_users.update_one(
        {"telegram_user_id": telegram_user_id},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return r.modified_count > 0


async def list_authorized() -> List[dict]:
    cursor = db.telegram_internal_authorized_users.find({}, {"_id": 0}).sort("name", 1)
    items = await cursor.to_list(200)
    return items
