"""Iteration 37 — Telegram consolidation: dedupe + alerts state persistence
+ isolamento de erros + navegação system:* + segurança tokens.

Reference: /app/backend/modules/telegram_internal/routes.py (dedupe insert-first,
system:* callbacks, granular try/except), startup.py (indexes + prime cache),
telegram_alerts/service.py (_MongoBackedStates).

Runs against LOCAL http://localhost:8001 for the webhook (bypasses ingress and
uses the private webhook secret).
"""
import asyncio
import os
import sys
import time
import uuid
import subprocess

import pytest
import requests

sys.path.insert(0, "/app/backend")

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from pymongo import MongoClient  # noqa: E402

LOCAL_URL = "http://localhost:8001"
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", LOCAL_URL).rstrip("/")

WEBHOOK_SECRET = os.environ.get(
    "TELEGRAM_INTERNAL_WEBHOOK_SECRET", "pdpv_internal_webhook_2026"
)
INTERNAL_WEBHOOK = f"{LOCAL_URL}/api/telegram/internal/webhook"

TEST_USER_ID = 999000111
TEST_CHAT_ID = 999000111

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_mongo = MongoClient(MONGO_URL)
_db = _mongo[DB_NAME]


# ============== helpers ==============
def _unique_update_id() -> int:
    # Unique enough across the test run to avoid colliding with earlier runs
    return int(time.time() * 1000) * 1000 + int(uuid.uuid4().int % 1000)


def _message_update(user_id: int, chat_id: int, text: str,
                    update_id: int = None) -> dict:
    return {
        "update_id": update_id if update_id is not None else _unique_update_id(),
        "message": {
            "message_id": int(time.time() * 1000) % 1_000_000,
            "from": {"id": user_id, "first_name": "Test", "username": "test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": int(time.time()),
            "text": text,
        },
    }


def _callback_update(user_id: int, chat_id: int, data: str,
                     update_id: int = None) -> dict:
    return {
        "update_id": update_id if update_id is not None else _unique_update_id(),
        "callback_query": {
            "id": str(uuid.uuid4()),
            "from": {"id": user_id, "first_name": "Test", "username": "test"},
            "message": {
                "message_id": 1,
                "chat": {"id": chat_id, "type": "private"},
                "text": "menu",
            },
            "data": data,
        },
    }


def _post_internal(update: dict, secret: str = WEBHOOK_SECRET):
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return requests.post(INTERNAL_WEBHOOK, json=update, headers=headers, timeout=15)


def _reset_state():
    _db.telegram_internal_states.delete_many({"telegram_user_id": TEST_USER_ID})
    _db.assistencias_bot_state.delete_many({"chat_id": TEST_USER_ID})
    _db.renting_records.delete_many(
        {"telegram_chat_id": TEST_USER_ID, "status": "draft"}
    )


@pytest.fixture(scope="module", autouse=True)
def _seed_authorized_user():
    """Ensure the test operator is authorized for all flows before running."""
    now = "2026-01-01T00:00:00+00:00"
    _db.telegram_internal_authorized_users.update_one(
        {"telegram_user_id": TEST_USER_ID},
        {
            "$set": {
                "telegram_user_id": TEST_USER_ID,
                "name": "Test Operator",
                "role": "ADMIN",
                "allowed_flows": ["pre_ticket", "renting", "assistencias", "mech_alert"],
                "active": True,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    yield
    _reset_state()


@pytest.fixture(autouse=True)
def _clean_state_between_tests():
    _reset_state()
    yield
    _reset_state()


# ============== 1. DEDUPE — sequential ==============
class TestDedupeSequential:
    """Same update_id twice sequentially → 1st ok, 2nd duplicate."""

    def test_sequential_same_update_id(self):
        update_id = _unique_update_id()
        # Use a plain /help message so no state side-effects are needed
        update = _message_update(TEST_USER_ID, TEST_CHAT_ID, "/help", update_id=update_id)

        r1 = _post_internal(update)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("status") == "ok", r1.json()

        r2 = _post_internal(update)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("status") == "duplicate", r2.json()

        # Exactly 1 row for this update_id
        n = _db.telegram_processed_updates.count_documents({"update_id": int(update_id)})
        assert n == 1, f"expected 1 row for update_id={update_id}, found {n}"

        # Cleanup
        _db.telegram_processed_updates.delete_many({"update_id": int(update_id)})


# ============== 2. DEDUPE — concurrent ==============
class TestDedupeConcurrent:
    """Two concurrent requests with same update_id → exactly one processed."""

    def test_concurrent_same_update_id(self):
        import concurrent.futures as cf
        update_id = _unique_update_id()
        update = _message_update(TEST_USER_ID, TEST_CHAT_ID, "/help", update_id=update_id)

        def do_post():
            return _post_internal(update)

        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(do_post), ex.submit(do_post)]
            results = [f.result() for f in futs]

        statuses = sorted([r.json().get("status") for r in results if r.status_code == 200])
        # Race-safe: one ok, one duplicate (order doesn't matter)
        assert statuses == ["duplicate", "ok"], f"unexpected: {statuses}"

        # Exactly 1 row for the update_id
        n = _db.telegram_processed_updates.count_documents({"update_id": int(update_id)})
        assert n == 1, f"expected exactly 1 processed row, found {n}"

        _db.telegram_processed_updates.delete_many({"update_id": int(update_id)})


# ============== 3. NO update_id fallback ==============
class TestNoUpdateIdFallback:
    def test_missing_update_id_processes(self):
        # Build without update_id
        u = {
            "message": {
                "message_id": 42,
                "from": {"id": TEST_USER_ID, "first_name": "T"},
                "chat": {"id": TEST_CHAT_ID, "type": "private"},
                "date": int(time.time()),
                "text": "/help",
            }
        }
        r = _post_internal(u)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ============== 4. /help command ==============
class TestHelpCommand:
    def test_help_command_logs_event(self):
        update = _message_update(TEST_USER_ID, TEST_CHAT_ID, "/help")
        r = _post_internal(update)
        assert r.status_code == 200

        # A 'command' log_event should exist with current_step=/help
        time.sleep(0.4)
        log = _db.telegram_internal_logs.find_one(
            {
                "telegram_user_id": TEST_USER_ID,
                "message_type": "command",
                "current_step": "/help",
            },
            sort=[("created_at", -1)],
        )
        assert log is not None, "no command log_event for /help found"
        assert log.get("success") is True


# ============== 5. system:* callbacks ==============
class TestSystemCallbacks:
    def test_system_menu_clears_state(self):
        # Seed active flow state
        _db.telegram_internal_states.update_one(
            {"telegram_user_id": TEST_USER_ID},
            {"$set": {
                "telegram_user_id": TEST_USER_ID,
                "chat_id": TEST_CHAT_ID,
                "active_flow": "pre_ticket",
                "current_step": "WAIT_TEXT",
                "temporary_payload": {},
                "updated_at": "2030-01-01T00:00:00+00:00",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }},
            upsert=True,
        )
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "system:menu"))
        assert r.status_code == 200
        # State cleared
        s = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert s is None, f"state not cleared by system:menu: {s}"

    def test_system_cancel(self):
        _db.telegram_internal_states.update_one(
            {"telegram_user_id": TEST_USER_ID},
            {"$set": {
                "telegram_user_id": TEST_USER_ID,
                "chat_id": TEST_CHAT_ID,
                "active_flow": "renting",
                "current_step": "STEP1",
                "temporary_payload": {},
                "updated_at": "2030-01-01T00:00:00+00:00",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }},
            upsert=True,
        )
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "system:cancel"))
        assert r.status_code == 200
        s = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert s is None, "state not cleared by system:cancel"

    def test_system_help(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "system:help"))
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_system_back_fallback(self):
        # No state, no active flow → falls back to main menu
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "system:back"))
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ============== 6. Error isolation with error_id ==============
class TestErrorIsolation:
    """Simulate a runtime error in the pre_ticket flow handle_message.

    We can't reach into the running backend to monkeypatch (it's a separate
    process). So we validate error isolation by pushing an intentionally
    malformed callback into an active flow's callback handler — flows may raise
    a natural exception on unexpected data. But a more robust approach is to
    check the CODE PATHS via existence of the log_event 'message_error' /
    'callback_error' in the routes, and to trigger a real error path by
    submitting a callback whose data pattern the callback handler doesn't
    recognize AFTER seeding an active flow state.

    Since we cannot force RuntimeError from outside, we settle for verifying:
    - webhook always returns 200 even under crafted edge inputs
    - the granular try/except code paths exist (structural test)
    """

    def test_webhook_never_500_on_edge_input(self):
        # Seed a live pre_ticket state and send arbitrary junk callback
        _db.telegram_internal_states.update_one(
            {"telegram_user_id": TEST_USER_ID},
            {"$set": {
                "telegram_user_id": TEST_USER_ID,
                "chat_id": TEST_CHAT_ID,
                "active_flow": "pre_ticket",
                "current_step": "WAIT_TEXT",
                "temporary_payload": {},
                "updated_at": "2030-01-01T00:00:00+00:00",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }},
            upsert=True,
        )
        # Send unknown callback data; flow's handle_callback may raise but the
        # webhook must still return 200 (per iteration 37 isolation).
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "pre_ticket:__NONEXISTENT_ACTION__"))
        assert r.status_code == 200, r.text

    def test_error_isolation_code_paths_present(self):
        """Static check: the try/except with error_id UUID is wired for both
        message and callback handlers in routes.py (proxy of runtime behavior).
        """
        with open("/app/backend/modules/telegram_internal/routes.py") as f:
            src = f.read()
        assert 'log_event(user_id, chat_id, "message_error"' in src
        assert 'log_event(user_id, chat_id, "callback_error"' in src
        assert "_uuid.uuid4().hex[:12]" in src
        assert "Referência: <code>{error_id}</code>" in src


# ============== 7. Indexes ==============
class TestIndexes:
    def test_processed_updates_indexes(self):
        idx = _db.telegram_processed_updates.index_information()
        assert "uniq_update_id" in idx
        assert idx["uniq_update_id"].get("unique") is True
        assert idx["uniq_update_id"]["key"] == [("update_id", 1)]
        assert "ttl_received_at_7d" in idx
        assert idx["ttl_received_at_7d"].get("expireAfterSeconds") == 604800

    def test_alerts_states_indexes(self):
        idx = _db.telegram_alerts_states.index_information()
        assert "uniq_chat_id" in idx
        assert idx["uniq_chat_id"].get("unique") is True

    def test_internal_logs_indexes(self):
        idx = _db.telegram_internal_logs.index_information()
        assert "lookup_update_id" in idx


# ============== 8. _MongoBackedStates persistence ==============
class TestAlertsStatePersistence:
    def test_set_persists_del_removes_and_restart_reloads(self):
        """Directly exercise the _MongoBackedStates dict via async context."""
        import asyncio as _asyncio

        async def scenario():
            # Ensure PYTHONPATH sees /app/backend
            from modules.telegram_alerts.service import _conversation_states
            await _conversation_states.ensure_loaded()

            chat_id = 987654321  # dedicated test chat id
            # cleanup first
            _db.telegram_alerts_states.delete_many({"chat_id": chat_id})

            # SET → should persist upsert
            _conversation_states[chat_id] = {"state": "IDLE",
                                             "active_alert_id": None,
                                             "problem_images_count": 0}
            await _asyncio.sleep(0.4)
            doc = _db.telegram_alerts_states.find_one({"chat_id": chat_id})
            assert doc is not None, "SET did not persist to telegram_alerts_states"
            assert doc.get("state") == "IDLE"

            # DEL → should remove doc
            del _conversation_states[chat_id]
            await _asyncio.sleep(0.4)
            doc = _db.telegram_alerts_states.find_one({"chat_id": chat_id})
            assert doc is None, "DEL did not remove doc from telegram_alerts_states"

            # Simulate restart: create fresh instance and reload from Mongo
            _db.telegram_alerts_states.insert_one(
                {"chat_id": chat_id, "state": "COLLECTING_PROBLEM_PHOTOS",
                 "problem_images_count": 2}
            )
            from modules.telegram_alerts.service import _MongoBackedStates
            fresh = _MongoBackedStates()
            await fresh.ensure_loaded()
            assert chat_id in fresh, "ensure_loaded did not restore persisted state"
            assert fresh[chat_id].get("state") == "COLLECTING_PROBLEM_PHOTOS"

            # cleanup
            _db.telegram_alerts_states.delete_many({"chat_id": chat_id})

        _asyncio.run(scenario())


# ============== 9. Regression: menu:* still delegates ==============
class TestMenuDelegationRegression:
    def test_menu_pre_ticket_creates_state(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:pre_ticket"))
        assert r.status_code == 200
        time.sleep(0.4)
        s = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert s is not None
        assert s.get("active_flow") == "pre_ticket"

    def test_menu_renting_creates_state(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:renting"))
        assert r.status_code == 200
        time.sleep(0.4)
        s = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert s is not None
        assert s.get("active_flow") == "renting"

    def test_menu_mech_alert_creates_state(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:mech_alert"))
        assert r.status_code == 200
        time.sleep(0.4)
        s = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert s is not None
        assert s.get("active_flow") == "mech_alert"

    def test_menu_assistencias_creates_state(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:assistencias"))
        assert r.status_code == 200
        time.sleep(0.4)
        # Iteration 32 delegation → state carries active_flow=assistencias
        s = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert s is not None
        assert s.get("active_flow") == "assistencias"


# ============== 10. Security: token scan ==============
class TestTokenSecurity:
    """No real Telegram bot tokens should be checked in anywhere in /app."""

    def test_no_bot_tokens_in_repo(self):
        # Telegram token pattern: <digits>:AA<base64ish, min 30 chars>
        # We exclude node_modules, .venv, .env (real .env is expected to hold tokens)
        cmd = [
            "bash", "-c",
            r"grep -rE '[0-9]{10}:AA[A-Za-z0-9_-]{30,}' /app "
            r"--include='*.md' --include='*.py' --include='*.js' "
            r"2>/dev/null | grep -v node_modules | grep -v '/\.venv/' || true"
        ]
        out = subprocess.check_output(cmd).decode()
        assert out.strip() == "", f"Bot tokens leaked in repo:\n{out}"

    def test_test_credentials_redacted(self):
        p = "/app/memory/test_credentials.md"
        assert os.path.exists(p), "test_credentials.md missing"
        content = open(p).read()
        # Must NOT contain a real token pattern
        import re as _re
        assert _re.search(r"[0-9]{10}:AA[A-Za-z0-9_-]{30,}", content) is None, \
            "test_credentials.md still contains a real bot token"
        assert "[REDACTED" in content, "expected redaction marker in credentials file"

    def test_gitignore_covers_test_credentials(self):
        gi = open("/app/.gitignore").read()
        assert "memory/test_credentials.md" in gi

    def test_rollback_docs_exist_no_tokens(self):
        p = "/app/backend/docs/telegram_rollback.md"
        assert os.path.exists(p), "rollback docs missing"
        content = open(p).read()
        import re as _re
        assert _re.search(r"[0-9]{10}:AA[A-Za-z0-9_-]{30,}", content) is None, \
            "rollback docs contain a real bot token"
