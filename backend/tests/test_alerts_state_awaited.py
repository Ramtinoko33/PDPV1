"""Sprint 1 / Phase 0B — Alerts critical transitions are awaited.

Verifies:
  - _MongoBackedStates.set() awaits the MongoDB write.
  - _transition() writes state to MongoDB BEFORE returning (critical path).
"""
import os

import pytest

os.environ.setdefault("TELEGRAM_INTERNAL_BOT_TOKEN", "TEST_TOKEN_1234")

from db import db  # noqa: E402
from modules.telegram_alerts import service as alerts  # noqa: E402


TEST_CHAT_ID = -999888777


@pytest.mark.asyncio
async def test_states_set_is_awaited():
    await db.telegram_alerts_states.delete_one({"chat_id": TEST_CHAT_ID})
    await alerts._conversation_states.set(TEST_CHAT_ID, {"state": alerts.STATE_IDLE, "foo": "bar"})
    doc = await db.telegram_alerts_states.find_one({"chat_id": TEST_CHAT_ID})
    # Persisted BEFORE the await returned — no polling needed.
    assert doc is not None
    assert doc["state"] == alerts.STATE_IDLE
    assert doc["foo"] == "bar"


@pytest.mark.asyncio
async def test_transition_is_async_and_persists():
    # Ensure state exists in memory.
    alerts._conversation_states[TEST_CHAT_ID] = {
        "state": alerts.STATE_IDLE,
        "active_alert_id": None,
        "problem_images_count": 0,
        "timer_task": None,
        "watchdog_task": None,
        "pending_photo": None,
        "user_info": {},
        "last_activity": 0.0,
        "initial_buffer": None,
    }
    await alerts._transition(TEST_CHAT_ID, alerts.STATE_COLLECTING_PROBLEM_IMAGES, action="test")
    doc = await db.telegram_alerts_states.find_one({"chat_id": TEST_CHAT_ID})
    # Await returned only after MongoDB write.
    assert doc is not None
    assert doc["state"] == alerts.STATE_COLLECTING_PROBLEM_IMAGES


@pytest.mark.asyncio
async def test_states_delete_is_awaited():
    await alerts._conversation_states.delete(TEST_CHAT_ID)
    doc = await db.telegram_alerts_states.find_one({"chat_id": TEST_CHAT_ID})
    assert doc is None
