"""Sprint 1 / Phase 0B — Renting state survives restart.

Uses a real MongoDB (motor) test collection with a stable chat_id.
Uses a session-scoped event loop to keep motor client alive across tests.
"""
import os

import pytest
import pytest_asyncio

os.environ.setdefault("TELEGRAM_INTERNAL_BOT_TOKEN", "TEST_TOKEN_1234")

from db import db  # noqa: E402
from modules.renting import service as renting  # noqa: E402

TEST_CHAT_ID = -987654321


@pytest_asyncio.fixture
async def _clean():
    await db.renting_bot_state.delete_one({"chat_id": TEST_CHAT_ID})
    yield
    await db.renting_bot_state.delete_one({"chat_id": TEST_CHAT_ID})
    renting._states.pop(TEST_CHAT_ID, None)


@pytest.mark.asyncio
async def test_state_persisted_and_recovered(_clean):
    """One integrated flow: write → flush → simulate restart → recover."""
    renting._states[TEST_CHAT_ID] = {
        "state": renting.STATE_WAIT_PLATE_PHOTO,
        "draft_id": None,
        "wheel_index": 0,
        "user_info": {"telegram_user_id": 11111},
        "last_activity": 12345.0,
        "watchdog_task": None,
    }
    await renting._states.flush(TEST_CHAT_ID)

    doc = await db.renting_bot_state.find_one({"chat_id": TEST_CHAT_ID})
    assert doc is not None
    assert doc["state"] == renting.STATE_WAIT_PLATE_PHOTO
    assert doc["user_info"]["telegram_user_id"] == 11111
    assert "watchdog_task" not in doc  # non-serializable stripped
    assert doc["expires_at"] > doc["updated_at"]

    # Simulate restart: clear in-memory cache and reload from Mongo.
    renting._states.clear()
    renting._states._loaded = False
    await renting._states.ensure_loaded()

    assert TEST_CHAT_ID in renting._states
    recovered = renting._states[TEST_CHAT_ID]
    assert recovered["state"] == renting.STATE_WAIT_PLATE_PHOTO
    assert recovered["watchdog_task"] is None


@pytest.mark.asyncio
async def test_delete_persists(_clean):
    """Deleting an in-memory state must remove it from MongoDB."""
    # First seed via awaitable path
    await renting._states._persist(TEST_CHAT_ID, {
        "state": renting.STATE_WAIT_PLATE_PHOTO,
        "user_info": {},
        "last_activity": 0.0,
    })
    doc = await db.renting_bot_state.find_one({"chat_id": TEST_CHAT_ID})
    assert doc is not None
    # Now use the awaitable delete path
    await renting._states._delete(TEST_CHAT_ID)
    doc = await db.renting_bot_state.find_one({"chat_id": TEST_CHAT_ID})
    assert doc is None
