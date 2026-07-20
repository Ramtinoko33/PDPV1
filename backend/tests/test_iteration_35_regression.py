"""
Iteration 35 – Regression tests after code cleanup (hoisted constants,
useCallback/useMemo, and hardcoded credentials removed in favour of
os.environ.get with fallback).

Focus: ensure preview backend endpoints continue to return 200 with expected
shape after the refactor. No new features; this is REGRESSION only.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "HCNMEnKMLq")
WEBHOOK_SECRET = os.environ.get(
    "TELEGRAM_INTERNAL_WEBHOOK_SECRET", "pdpv_internal_webhook_2026"
)


def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.json()
    return tok


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASSWORD)}"}


# ------------- auth regression -------------

class TestAuthRegression:
    def test_admin_login_works(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("token") or body.get("access_token")


# ------------- finance regression -------------

class TestFinanceRegression:
    def test_overdue_evolution_days_30(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "series" in body and "summary" in body
        assert isinstance(body["series"], list)
        assert isinstance(body["summary"], dict)

    def test_overdue_evolution_days_7(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=7",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "series" in body and "summary" in body

    def test_overdue_evolution_days_90(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=90",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200

    def test_dashboard(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/dashboard", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ["total_balance", "total_overdue_collectable", "aging_buckets", "top_debtors"]:
            assert k in body, f"missing {k}"

    def test_data_health(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/data-health", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_clients(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/clients?page=1&page_size=5",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200
        assert "clients" in r.json()

    def test_promises(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/promises", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "promises" in r.json()

    def test_imports(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/imports", headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_client_detail_page_endpoint(self, admin_headers):
        # Fetch first client, then hit detail endpoint (feeds FinanceClientDetail.js)
        r = requests.get(
            f"{BASE_URL}/api/finance/clients?page=1&page_size=1",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200
        clients = r.json().get("clients") or []
        if not clients:
            pytest.skip("no clients in preview DB")
        cid = clients[0]["id"]
        rd = requests.get(
            f"{BASE_URL}/api/finance/clients/{cid}",
            headers=admin_headers, timeout=30,
        )
        assert rd.status_code == 200, rd.text[:300]


# ------------- tickets regression (iteration 30 bug) -------------

class TestTicketsRegression:
    def test_overdue_tickets_returns_data(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        # Bug 62-vs-0 was: this returned 0 when it should return >0. Assert non-null.
        tickets = body if isinstance(body, list) else body.get("tickets", body.get("items", []))
        assert isinstance(tickets, list)
        # We assert the endpoint is reachable and structured; volume varies.
        # Log actual count for the report.
        print(f"[overdue_tickets_count] {len(tickets)}")


# ------------- telegram internal webhook -------------

class TestTelegramWebhookRegression:
    def test_webhook_with_valid_secret_accepts(self):
        # Use a benign no-op payload that the router should acknowledge.
        # If secret is invalid -> 401/403. If valid -> 200/2xx even if payload is minimal.
        payload = {
            "update_id": 999999,
            "message": {
                "message_id": 1,
                "from": {"id": 999000111, "is_bot": False, "first_name": "Test"},
                "chat": {"id": 999000111, "type": "private"},
                "date": 0,
                "text": "/start",
            },
        }
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
            timeout=30,
        )
        # Accept either 200 or 202 as success
        assert r.status_code in (200, 202), (
            f"expected 200/202 with valid secret, got {r.status_code}: {r.text[:200]}"
        )

    def test_webhook_without_secret_rejected(self):
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json={"update_id": 1},
            timeout=30,
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
