"""Iteration 36 — Deprecation of the 4 old bot webhook handlers.

Verifies:
 1. The 4 old @router.post("/webhook") handlers (telegram, telegram_alerts,
    renting, assistencias) now return 200 + {status:"deprecated", message
    containing "@pdpv_interno_bot"}.
 2. The original logic is preserved at /webhook/legacy on the same routers
    (endpoint must exist / must NOT 404).
 3. Regression: /api/telegram/internal/webhook (the consolidated bot) still
    works — secret check, and the 3 delegated flows (assistencias, renting,
    mech_alert) still create the expected state / draft rows.
 4. Regression: admin-facing endpoints of the deprecated modules are NOT
    affected (list-records for renting/assistencias, list-alerts for
    telegram-alerts) — plus finance dashboard / overdue-evolution / tickets
    overdue.

Runs against LOCAL http://localhost:8001 (webhook secret) with fallback
to REACT_APP_BACKEND_URL for the auth-required admin endpoints.
"""
import os
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from pymongo import MongoClient  # noqa: E402

LOCAL_URL = "http://localhost:8001"
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", LOCAL_URL).rstrip("/")

WEBHOOK_SECRET = os.environ.get("TELEGRAM_INTERNAL_WEBHOOK_SECRET", "pdpv_internal_webhook_2026")
INTERNAL_WEBHOOK = f"{LOCAL_URL}/api/telegram/internal/webhook"

TEST_USER_ID = 999000111
TEST_CHAT_ID = 999000111

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_mongo = MongoClient(MONGO_URL)
_db = _mongo[DB_NAME]


# ============== helpers ==============
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
def _seed_user():
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
    _reset_state()
    yield
    _reset_state()


@pytest.fixture(autouse=True)
def _clean():
    _reset_state()
    yield
    _reset_state()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{LOCAL_URL}/api/auth/login",
        json={
            "email": "admin@pdpv.pt",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "HCNMEnKMLq"),
        },
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("access_token") or r.json().get("token")
    assert token, f"no token in login response: {r.json()}"
    return token


# ============== 1. Deprecated webhooks ==============

DEPRECATED_ENDPOINTS = [
    "/api/telegram/webhook",
    "/api/telegram-alerts/webhook",
    "/api/renting/webhook",
    "/api/assistencias/webhook",
]


class TestDeprecatedWebhooks:
    """The 4 old /webhook endpoints must respond 200 with a deprecation JSON."""

    @pytest.mark.parametrize("endpoint", DEPRECATED_ENDPOINTS)
    def test_deprecated_webhook_returns_200_and_json(self, endpoint):
        url = f"{LOCAL_URL}{endpoint}"
        r = requests.post(url, json={"any": "payload"}, timeout=10)
        assert r.status_code == 200, f"{endpoint} -> {r.status_code}: {r.text[:200]}"

        body = r.json()
        assert body.get("status") == "deprecated", (
            f"{endpoint} did not return status=deprecated: {body}"
        )
        assert "@pdpv_interno_bot" in (body.get("message") or ""), (
            f"{endpoint} message missing @pdpv_interno_bot: {body}"
        )

    @pytest.mark.parametrize("endpoint", DEPRECATED_ENDPOINTS)
    def test_deprecated_webhook_ignores_content(self, endpoint):
        """Even with a valid Telegram-shaped payload it must NOT process it."""
        payload = _callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:assistencias")
        r = requests.post(f"{LOCAL_URL}{endpoint}", json=payload, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "deprecated"
        # No state should have been created via these old endpoints
        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is None, (
            f"Deprecated endpoint {endpoint} should NOT touch internal state: {st}"
        )


# ============== 2. Legacy routes still registered ==============

LEGACY_ENDPOINTS = [
    "/api/telegram/webhook/legacy",
    "/api/telegram-alerts/webhook/legacy",
    "/api/renting/webhook/legacy",
    "/api/assistencias/webhook/legacy",
]


class TestLegacyRoutesExist:
    """The original code was moved to /webhook/legacy. Route must exist (not 404)."""

    @pytest.mark.parametrize("endpoint", LEGACY_ENDPOINTS)
    def test_legacy_route_registered(self, endpoint):
        url = f"{LOCAL_URL}{endpoint}"
        r = requests.post(url, json={}, timeout=10)
        # We accept 200 (empty payload handled) OR 4xx (validation/secret),
        # but NOT 404 which would mean the route disappeared.
        assert r.status_code != 404, (
            f"Legacy route {endpoint} is missing! -> 404 {r.text[:200]}"
        )
        assert r.status_code < 500, (
            f"Legacy route {endpoint} returned server error: {r.status_code} {r.text[:200]}"
        )


# ============== 3. Regression: internal webhook + delegation ==============

class TestInternalWebhookRegression:
    def test_valid_secret_200(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:cancel"))
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_bad_secret_403(self):
        r = _post_internal(
            _callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:cancel"),
            secret="WRONG_SECRET",
        )
        assert r.status_code == 403

    def test_menu_assistencias_delegates(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:assistencias"))
        assert r.status_code == 200

        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None, "internal state not created"
        assert st.get("active_flow") == "assistencias"

        abs_ = _db.assistencias_bot_state.find_one({"chat_id": TEST_CHAT_ID})
        assert abs_ is not None, "assistencias_bot_state row not created (delegation broken)"
        assert abs_.get("state") == "WAIT_LOCATION"

    def test_menu_renting_creates_draft(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:renting"))
        assert r.status_code == 200

        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None
        assert st.get("active_flow") == "renting"

        draft = _db.renting_records.find_one(
            {"telegram_chat_id": TEST_CHAT_ID, "status": "draft"}
        )
        assert draft is not None, "renting draft NOT created"

    def test_menu_mech_alert_sets_active_flow(self):
        r = _post_internal(_callback_update(TEST_USER_ID, TEST_CHAT_ID, "menu:mech_alert"))
        assert r.status_code == 200

        st = _db.telegram_internal_states.find_one({"telegram_user_id": TEST_USER_ID})
        assert st is not None
        assert st.get("active_flow") == "mech_alert"


# ============== 4. Regression: admin endpoints of deprecated modules ==============

class TestAdminEndpointsUnaffected:
    def _auth(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}

    def test_pending_users(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/telegram/internal/pending-users",
            headers=self._auth(admin_token),
            timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        assert isinstance(r.json(), list)

    def test_finance_dashboard(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/finance/dashboard",
            headers=self._auth(admin_token),
            timeout=20,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_finance_overdue_evolution(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/finance/overdue-evolution?days=30",
            headers=self._auth(admin_token),
            timeout=20,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_tickets_overdue(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/tickets?overdue=true",
            headers=self._auth(admin_token),
            timeout=20,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_assistencias_records(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/assistencias/records",
            headers=self._auth(admin_token),
            timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "items" in body or "total" in body, f"unexpected shape: {body}"

    def test_renting_records(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/renting/records",
            headers=self._auth(admin_token),
            timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "items" in body or "total" in body, f"unexpected shape: {body}"

    def test_telegram_alerts_list(self, admin_token):
        r = requests.get(
            f"{LOCAL_URL}/api/telegram-alerts/alerts",
            headers=self._auth(admin_token),
            timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "alerts" in body or "total" in body, f"unexpected shape: {body}"
