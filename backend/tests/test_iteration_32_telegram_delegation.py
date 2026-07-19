"""Iteration 32 — Telegram Internal Bot delegation (Option A) tests.

Validates that the 3 rewritten flow stubs (assistencias, renting, mech_alert)
delegate to the standalone services and produce the expected side-effects in
MongoDB. Also runs the get_employee_for_chat fallback test and the regression
smoke tests on unrelated APIs (finance dashboard, tickets, pending/authorized
users).

Notes for the reader:
- The user_id 999000111 does NOT exist in real Telegram, so sendMessage will
  return an error (chat not found) — this is EXPECTED and swallowed by
  bot_api. We only check DB side-effects.
- Uses localhost:8001 for the webhook (preview ingress may 403 the raw
  webhook; localhost is the tested path).
"""
import asyncio
import os
import sys
import time
import uuid

import pytest
import requests

# Backend importable path
sys.path.insert(0, "/app/backend")

# Force env for db.py before importing it
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from pymongo import MongoClient  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
LOCAL_URL = "http://localhost:8001"
WEBHOOK_URL_LOCAL = f"{LOCAL_URL}/api/telegram/internal/webhook"
WEBHOOK_SECRET = "pdpv_internal_webhook_2026"

TEST_USER_ID = 999000111
TEST_CHAT_ID = 999000111  # same in the seeded fixture
UNAUTHORIZED_USER_ID = 999000222  # will be seeded with pre_ticket only

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# ---------- fixtures ----------
_mongo = MongoClient(MONGO_URL)
_db = _mongo[DB_NAME]


def _post_webhook(update: dict, secret: str = WEBHOOK_SECRET, use_local: bool = True):
    url = WEBHOOK_URL_LOCAL if use_local else f"{BASE_URL}/api/telegram/internal/webhook"
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return requests.post(url, json=update, headers=headers, timeout=15)


def _callback_update(user_id: int, chat_id: int, data: str) -> dict:
    return {
        "update_id": int(time.time() * 1000) % 1_000_000_000,
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


def _message_update(user_id: int, chat_id: int, text: str = None, location: dict = None) -> dict:
    msg = {
        "message_id": int(time.time() * 1000) % 1_000_000_000,
        "from": {"id": user_id, "first_name": "Test", "username": "test"},
        "chat": {"id": chat_id, "type": "private"},
        "date": int(time.time()),
    }
    if text is not None:
        msg["text"] = text
    if location is not None:
        msg["location"] = location
    return {"update_id": int(time.time() * 1000) % 1_000_000_000, "message": msg}


def _reset_all_state():
    """Fully clean any pre-existing state for our TEST_USER_ID."""
    _db.telegram_internal_states.delete_many({"telegram_user_id": {"$in": [TEST_USER_ID, UNAUTHORIZED_USER_ID]}})
    _db.assistencias_bot_state.delete_many({"chat_id": {"$in": [TEST_USER_ID, UNAUTHORIZED_USER_ID]}})
    _db.renting_records.delete_many(
        {"telegram_chat_id": {"$in": [TEST_USER_ID, UNAUTHORIZED_USER_ID]}, "status": "draft"}
    )


@pytest.fixture(scope="module", autouse=True)
def _seed_users():
    """Ensure the two test authorized users exist."""
    now_iso = "2026-01-01T00:00:00+00:00"
    _db.telegram_internal_authorized_users.update_one(
        {"telegram_user_id": TEST_USER_ID},
        {"$set": {
            "telegram_user_id": TEST_USER_ID,
            "name": "Test",
            "role": "ADMIN",
            "allowed_flows": ["pre_ticket", "renting", "mech_alert", "assistencias"],
            "active": True,
            "updated_at": now_iso,
        }, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    _db.telegram_internal_authorized_users.update_one(
        {"telegram_user_id": UNAUTHORIZED_USER_ID},
        {"$set": {
            "telegram_user_id": UNAUTHORIZED_USER_ID,
            "name": "PreTicketOnly",
            "role": "AGENT",
            "allowed_flows": ["pre_ticket"],
            "active": True,
            "updated_at": now_iso,
        }, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    _reset_all_state()
    yield
    _reset_all_state()
    _db.telegram_internal_authorized_users.delete_one({"telegram_user_id": UNAUTHORIZED_USER_ID})


@pytest.fixture(autouse=True)
def _clean_between_tests():
    _reset_all_state()
    yield
    _reset_all_state()


# ============== 1. Webhook security ==============

class TestWebhookSecurity:
    def test_bad_secret_returns_403(self):
        r = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:pre_ticket"),
                          secret="WRONG_SECRET")
        assert r.status_code == 403

    def test_good_secret_returns_200(self):
        r = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:cancel"))
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ============== 2. Menu delegation ==============

class TestMenuAssistencias:
    def test_menu_assistencias_creates_state_and_wait_location(self):
        r = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:assistencias"))
        assert r.status_code == 200

        # internal state must have active_flow=assistencias
        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None, "telegram_internal_states row missing"
        assert st.get("active_flow") == "assistencias", f"active_flow != assistencias: {st}"
        assert st.get("current_step") == "wait_location"

        # standalone service state
        abs_ = _db.assistencias_bot_state.find_one({"chat_id": TEST_CHAT_ID})
        assert abs_ is not None, "assistencias_bot_state row missing (get_employee_for_chat fallback likely broken)"
        assert abs_.get("state") == "WAIT_LOCATION", f"assist state != WAIT_LOCATION: {abs_}"

    def test_menu_assistencias_forbidden_for_pre_ticket_only_user(self):
        r = _post_webhook(_callback_update(UNAUTHORIZED_USER_ID, UNAUTHORIZED_USER_ID, "menu:assistencias"))
        # Webhook always returns 200 (Telegram wants that). We assert side-effect: no state created.
        assert r.status_code == 200
        st = _db.telegram_internal_states.find_one({"telegram_user_id": UNAUTHORIZED_USER_ID})
        assert st is None, f"Unauthorized user got a state row: {st}"
        abs_ = _db.assistencias_bot_state.find_one({"chat_id": UNAUTHORIZED_USER_ID})
        assert abs_ is None, f"Unauthorized user got assistencias_bot_state: {abs_}"


class TestMenuRenting:
    def test_menu_renting_creates_state_and_draft(self):
        r = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:renting"))
        assert r.status_code == 200

        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None
        assert st.get("active_flow") == "renting", f"active_flow != renting: {st}"

        draft = _db.renting_records.find_one({"telegram_chat_id": TEST_CHAT_ID, "status": "draft"})
        assert draft is not None, "renting_records draft NOT created"
        assert draft.get("status") == "draft"


class TestMenuMechAlert:
    def test_menu_mech_alert_creates_state(self):
        r = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:mech_alert"))
        assert r.status_code == 200

        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None, "telegram_internal_states row missing"
        assert st.get("active_flow") == "mech_alert"
        assert st.get("current_step") == "wait_input"


class TestMenuPreTicketRegression:
    def test_menu_pre_ticket_still_inline(self):
        r = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:pre_ticket"))
        assert r.status_code == 200

        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None
        assert st.get("active_flow") == "pre_ticket", f"pre_ticket regression: {st}"


class TestMenuCancel:
    def test_menu_cancel_clears_state(self):
        # First create a state via menu:mech_alert
        r1 = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:mech_alert"))
        assert r1.status_code == 200
        st_before = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st_before is not None

        # Now cancel
        r2 = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:cancel"))
        assert r2.status_code == 200

        st_after = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st_after is None, f"menu:cancel did not clear state: {st_after}"


# ============== 3. Forward + attachment while assistencias is active ==============

class TestAssistenciasForwarding:
    def test_text_forwarded_to_delegate(self):
        # Start assistencias
        r1 = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:assistencias"))
        assert r1.status_code == 200
        abs_before = _db.assistencias_bot_state.find_one({"chat_id": TEST_CHAT_ID})
        assert abs_before and abs_before.get("state") == "WAIT_LOCATION"

        # Send a text message
        r2 = _post_webhook(_message_update(TEST_USER_ID, TEST_CHAT_ID, text="/nova_assistencia"))
        assert r2.status_code == 200

        # Service should still be in WAIT_LOCATION (text at WAIT_LOCATION prompts user)
        abs_after = _db.assistencias_bot_state.find_one({"chat_id": TEST_CHAT_ID})
        assert abs_after is not None, "assistencias state dropped unexpectedly"
        # Should still be in WAIT_LOCATION (text alone doesn't advance the flow)
        assert abs_after.get("state") == "WAIT_LOCATION"

    def test_location_attachment_consumed(self):
        # Start
        r1 = _post_webhook(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:assistencias"))
        assert r1.status_code == 200

        # Send location — should be consumed and move state past WAIT_LOCATION
        loc_update = _message_update(
            TEST_USER_ID, TEST_CHAT_ID,
            location={"latitude": 38.7223, "longitude": -9.1393},
        )
        r2 = _post_webhook(loc_update)
        assert r2.status_code == 200

        abs_after = _db.assistencias_bot_state.find_one({"chat_id": TEST_CHAT_ID})
        assert abs_after is not None
        # Once location handled, service transitions to WAIT_PLATE (or beyond)
        assert abs_after.get("state") != "WAIT_LOCATION", (
            f"location NOT consumed by handle_attachment_raw — state still WAIT_LOCATION: {abs_after}"
        )
        # And the draft should now contain lat/lon
        draft = abs_after.get("draft") or {}
        assert draft.get("latitude") == 38.7223, f"latitude not saved: {draft}"


# ============== 4. get_employee_for_chat fallback (direct import test) ==============

class TestGetEmployeeFallback:
    def test_get_employee_for_chat_uses_internal_bot_fallback(self):
        # Ensure NO legacy assistencias_bot_users doc exists for this user
        _db.assistencias_bot_users.delete_many({"telegram_user_id": TEST_USER_ID})

        from modules.assistencias.service import get_employee_for_chat

        loop = asyncio.new_event_loop()
        try:
            employee = loop.run_until_complete(get_employee_for_chat(TEST_USER_ID))
        finally:
            loop.close()

        assert employee is not None, "get_employee_for_chat returned None — fallback broken"
        assert employee.get("has_assistencias_access") is True
        assert employee.get("role") in ("ADMIN", "SUPERVISOR", "AGENT"), (
            f"unexpected role: {employee.get('role')}"
        )
        # Seeded user role in DB is ADMIN, fallback should surface it
        assert employee.get("role") == "ADMIN", f"fallback did not propagate role from internal auth doc: {employee}"
        assert employee.get("id") == f"internal-{TEST_USER_ID}"


# ============== 5. Regression: admin endpoints untouched ==============

class TestAdminEndpointRegressions:
    @pytest.fixture(scope="class")
    def admin_token(self):
        r = requests.post(
            f"{LOCAL_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "HCNMEnKMLq"},
            timeout=15,
        )
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
        return r.json().get("access_token") or r.json().get("token")

    def test_pending_users(self, admin_token):
        assert admin_token
        r = requests.get(
            f"{LOCAL_URL}/api/telegram/internal/pending-users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        assert isinstance(data, list)

    def test_authorized_users(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/telegram/internal/authorized-users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ids = [u.get("telegram_user_id") for u in data]
        assert TEST_USER_ID in ids

    def test_finance_dashboard(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/finance/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_tickets_overdue(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/tickets?overdue=true",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
