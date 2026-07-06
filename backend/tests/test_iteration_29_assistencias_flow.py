"""
Iteration 29 – PDPV Telegram Internal Bot: 'Assistências' flow added (Phase 1 redirect).

Covers the review request:
  1. Unit-level: assistencias module exists with start/handle_message/handle_callback
  2. Unit-level: REGISTRY includes 'assistencias'
  3. Unit-level: auth.ALL_FLOWS == ['pre_ticket','renting','assistencias','mech_alert']
  4. Unit-level: menu.main_menu_markup returns buttons in the correct order and
     respects allowed_flows (user WITHOUT 'assistencias' must NOT see the button).
  5. API-level: POST /api/telegram/internal/authorized-users
        - accepts allowed_flows=['assistencias']
        - default allowed_flows (omitted in body) is the 4-flow list including assistencias
  6. API-level: webhook callback 'menu:assistencias'
        - for user WITH assistencias permission -> 200
        - for user WITHOUT assistencias permission (seeded 999000111) -> 200 (denies but must not crash)
  7. Regression: pending-users, authorized-users, webhook secret validation still ok
  8. Regression: Finance /dashboard, /data-health still 200 for admin
"""
from __future__ import annotations

import os
import sys
import time
import uuid
import pytest
import requests

# Allow importing backend modules for unit tests
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
INTERNAL_WEBHOOK_SECRET = os.environ.get(
    "TELEGRAM_INTERNAL_WEBHOOK_SECRET", "pdpv_internal_webhook_2026"
)

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@pdpv.pt")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "HCNMEnKMLq")
AGENT_EMAIL = os.environ.get("TEST_AGENT_EMAIL", "cobranca.teste@pdpv.pt")
AGENT_PASSWORD = os.environ.get("TEST_AGENT_PASSWORD", "TesteFin2026!")

SEEDED_USER_ID = 999000111  # allowed_flows=[pre_ticket, renting, mech_alert] per test_credentials.md


# ============ shared fixtures ============

def _login(email: str, password: str) -> str | None:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    return r.json().get("token")


@pytest.fixture(scope="module")
def admin_token():
    tk = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not tk:
        pytest.skip("Admin login failed – cannot run suite")
    return tk


@pytest.fixture(scope="module")
def agent_token():
    tk = _login(AGENT_EMAIL, AGENT_PASSWORD)
    if not tk:
        pytest.skip("Agent login failed – cannot run agent-403 test")
    return tk


@pytest.fixture
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    })
    return s


@pytest.fixture
def agent_client(agent_token):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {agent_token}",
    })
    return s


# ============ 1. Unit: assistencias module structure ============
class TestAssistenciasModule:
    def test_module_import_and_public_api(self):
        from modules.telegram_internal.flows import assistencias
        # FLOW constant
        assert getattr(assistencias, "FLOW", None) == "assistencias"
        # Callables
        assert callable(assistencias.start)
        assert callable(assistencias.handle_message)
        assert callable(assistencias.handle_callback)

    def test_module_has_bot_url(self):
        from modules.telegram_internal.flows import assistencias
        # Default URL points to the dedicated bot
        assert "pdpv_assistencias_bot" in assistencias.ASSISTENCIAS_BOT_URL


# ============ 2. Unit: REGISTRY ============
class TestFlowsRegistry:
    def test_registry_keys(self):
        from modules.telegram_internal.flows import REGISTRY
        assert set(REGISTRY.keys()) == {"pre_ticket", "renting", "assistencias", "mech_alert"}

    def test_registry_assistencias_module(self):
        from modules.telegram_internal.flows import REGISTRY, assistencias as assist_mod
        assert REGISTRY["assistencias"] is assist_mod


# ============ 3. Unit: ALL_FLOWS ordering ============
class TestAllFlowsList:
    def test_all_flows_order(self):
        from modules.telegram_internal.auth import ALL_FLOWS
        assert ALL_FLOWS == ["pre_ticket", "renting", "assistencias", "mech_alert"]


# ============ 4. Unit: main_menu_markup ordering & permissions ============
class TestMainMenuMarkup:
    def _button_texts(self, markup):
        """Extract flat list of button texts from inline_keyboard markup."""
        rows = markup.get("inline_keyboard") or []
        out = []
        for row in rows:
            for btn in row:
                out.append(btn.get("text"))
        return out

    def _button_callbacks(self, markup):
        rows = markup.get("inline_keyboard") or []
        out = []
        for row in rows:
            for btn in row:
                cb = btn.get("callback_data")
                if cb:
                    out.append(cb)
        return out

    def test_menu_order_with_all_flows(self):
        from modules.telegram_internal.menu import main_menu_markup
        markup = main_menu_markup({
            "allowed_flows": ["pre_ticket", "renting", "assistencias", "mech_alert"]
        })
        callbacks = self._button_callbacks(markup)
        # Expected order per PRD
        assert callbacks == [
            "menu:pre_ticket",
            "menu:renting",
            "menu:assistencias",
            "menu:mech_alert",
            "menu:cancel",
        ], f"unexpected order: {callbacks}"

    def test_menu_order_when_no_flows_key(self):
        """When allowed_flows is empty/None, all 4 flows should be visible."""
        from modules.telegram_internal.menu import main_menu_markup
        markup = main_menu_markup({})  # empty user_auth
        callbacks = self._button_callbacks(markup)
        assert callbacks == [
            "menu:pre_ticket",
            "menu:renting",
            "menu:assistencias",
            "menu:mech_alert",
            "menu:cancel",
        ]

    def test_menu_hides_assistencias_when_not_allowed(self):
        """User with allowed_flows=['pre_ticket'] must NOT see the Assistência button."""
        from modules.telegram_internal.menu import main_menu_markup
        markup = main_menu_markup({"allowed_flows": ["pre_ticket"]})
        callbacks = self._button_callbacks(markup)
        assert "menu:assistencias" not in callbacks, \
            f"assistencias button should be hidden for user without permission, got {callbacks}"
        assert "menu:pre_ticket" in callbacks
        # Only pre_ticket + cancel visible
        assert callbacks == ["menu:pre_ticket", "menu:cancel"], \
            f"only pre_ticket + cancel expected, got {callbacks}"

    def test_menu_shows_assistencias_when_only_that_flow(self):
        from modules.telegram_internal.menu import main_menu_markup
        markup = main_menu_markup({"allowed_flows": ["assistencias"]})
        callbacks = self._button_callbacks(markup)
        assert callbacks == ["menu:assistencias", "menu:cancel"]
        texts = self._button_texts(markup)
        # sanity: label matches user-facing "Registar Assistência"
        assert any("Assist" in t for t in texts), f"no Assistência label found: {texts}"

    def test_button_label_registar_assistencia(self):
        from modules.telegram_internal.menu import main_menu_markup
        markup = main_menu_markup({
            "allowed_flows": ["pre_ticket", "renting", "assistencias", "mech_alert"]
        })
        texts = self._button_texts(markup)
        # third button (index 2) should be Assistência
        assert "Assist" in texts[2], f"3rd button not Assistência: {texts}"


# ============ 5. API: authorized-users accepts assistencias flow ============
class TestAuthorizedUsersAssistencias:
    def test_create_user_with_only_assistencias_flow(self, admin_client):
        test_id = 700_100_000 + (int(time.time()) % 100_000)
        payload = {
            "telegram_user_id": test_id,
            "name": "TEST_assistencias_only",
            "role": "AGENT",
            "allowed_flows": ["assistencias"],
            "active": True,
        }
        r = admin_client.post(
            f"{BASE_URL}/api/telegram/internal/authorized-users", json=payload
        )
        assert r.status_code == 200, f"upsert failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body.get("telegram_user_id") == test_id
        assert body.get("allowed_flows") == ["assistencias"]
        # Verify via GET
        r2 = admin_client.get(f"{BASE_URL}/api/telegram/internal/authorized-users")
        assert r2.status_code == 200
        found = next(
            (u for u in r2.json() if u.get("telegram_user_id") == test_id), None
        )
        assert found is not None, f"upserted user not found in list"
        assert found.get("allowed_flows") == ["assistencias"]
        # Cleanup
        admin_client.delete(
            f"{BASE_URL}/api/telegram/internal/authorized-users/{test_id}"
        )

    def test_default_allowed_flows_includes_assistencias(self, admin_client):
        """Body omits allowed_flows -> Pydantic default_factory should give all 4 flows."""
        test_id = 700_200_000 + (int(time.time()) % 100_000)
        payload = {
            "telegram_user_id": test_id,
            "name": "TEST_default_flows",
            "role": "AGENT",
            # allowed_flows intentionally omitted
            "active": True,
        }
        r = admin_client.post(
            f"{BASE_URL}/api/telegram/internal/authorized-users", json=payload
        )
        assert r.status_code == 200, f"upsert failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        flows = body.get("allowed_flows")
        assert flows == ["pre_ticket", "renting", "assistencias", "mech_alert"], (
            f"default allowed_flows must include assistencias in order: {flows}"
        )
        # Cleanup
        admin_client.delete(
            f"{BASE_URL}/api/telegram/internal/authorized-users/{test_id}"
        )


# ============ 6. Webhook: callback_query menu:assistencias ============
class TestWebhookAssistenciasCallback:
    @pytest.fixture(scope="class")
    def assist_user_id(self):
        """Create a fresh authorized user with only 'assistencias' allowed."""
        tk = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        if not tk:
            pytest.skip("admin login failed")
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json",
                          "Authorization": f"Bearer {tk}"})
        uid = 700_300_000 + (int(time.time()) % 100_000)
        r = s.post(
            f"{BASE_URL}/api/telegram/internal/authorized-users",
            json={
                "telegram_user_id": uid,
                "name": "TEST_assist_webhook",
                "role": "AGENT",
                "allowed_flows": ["assistencias"],
                "active": True,
            },
        )
        assert r.status_code == 200, f"failed to seed assist user: {r.text[:200]}"
        yield uid
        # Teardown
        try:
            s.delete(f"{BASE_URL}/api/telegram/internal/authorized-users/{uid}")
        except Exception:
            pass

    def _callback_payload(self, user_id: int, data: str) -> dict:
        return {
            "update_id": int(time.time() * 1000) % 2_000_000_000,
            "callback_query": {
                "id": str(uuid.uuid4()),
                "from": {"id": user_id, "first_name": "TESTCB"},
                "message": {
                    "message_id": 1,
                    "chat": {"id": user_id, "type": "private"},
                },
                "data": data,
            },
        }

    def test_callback_assistencias_authorized_user_returns_200(self, assist_user_id):
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json=self._callback_payload(assist_user_id, "menu:assistencias"),
            headers={"X-Telegram-Bot-Api-Secret-Token": INTERNAL_WEBHOOK_SECRET},
            timeout=20,
        )
        # Telegram MUST always get 200 to avoid retries
        assert r.status_code == 200, f"expected 200, got {r.status_code} {r.text[:200]}"
        assert r.json().get("status") == "ok"

    def test_callback_assistencias_seeded_user_without_permission_returns_200(self):
        """Seeded user 999000111 has allowed_flows=[pre_ticket, renting, mech_alert]
        (no assistencias). The webhook must still return 200 (does not crash)."""
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json=self._callback_payload(SEEDED_USER_ID, "menu:assistencias"),
            headers={"X-Telegram-Bot-Api-Secret-Token": INTERNAL_WEBHOOK_SECRET},
            timeout=20,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code} {r.text[:200]}"
        assert r.json().get("status") == "ok"

    def test_callback_assistencias_unauthorized_user_returns_200(self):
        """Random telegram user_id (not in DB and not in env) -> unauthorized path,
        must still return 200 and log a pending user."""
        random_uid = 800_500_000 + (int(time.time()) % 100_000)
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json=self._callback_payload(random_uid, "menu:assistencias"),
            headers={"X-Telegram-Bot-Api-Secret-Token": INTERNAL_WEBHOOK_SECRET},
            timeout=20,
        )
        assert r.status_code == 200

    def test_callback_menu_start_still_works(self, assist_user_id):
        """/start command still returns 200 (regression)."""
        payload = {
            "update_id": int(time.time() * 1000) % 2_000_000_000,
            "message": {
                "message_id": 99,
                "from": {"id": assist_user_id, "first_name": "TESTCB"},
                "chat": {"id": assist_user_id, "type": "private"},
                "text": "/start",
            },
        }
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": INTERNAL_WEBHOOK_SECRET},
            timeout=20,
        )
        assert r.status_code == 200


# ============ 7. Regression: secret & auth matrix ============
class TestRegression:
    def test_webhook_wrong_secret_403(self):
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_authorized_users_admin_ok(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/telegram/internal/authorized-users")
        assert r.status_code == 200
        ids = [u.get("telegram_user_id") for u in r.json()]
        assert SEEDED_USER_ID in ids

    def test_authorized_users_agent_forbidden(self, agent_client):
        r = agent_client.get(f"{BASE_URL}/api/telegram/internal/authorized-users")
        assert r.status_code == 403

    def test_pending_users_admin_ok(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/telegram/internal/pending-users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============ 8. Regression: Finance smoke ============
class TestFinanceSmoke:
    def test_finance_data_health(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/finance/data-health")
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_finance_dashboard(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/finance/dashboard")
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
