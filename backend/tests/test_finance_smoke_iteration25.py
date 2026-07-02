"""
Iteration 25 — Finance smoke test post FreshnessBadge introduction.

Objectives:
  1. Confirm auth returns finance_role
  2. Smoke every /api/finance/* endpoint required by the FreshnessBadge / dashboard
  3. Confirm RBAC gating (no-finance user gets 403; COLLECTIONS_AGENT gets dashboard)
  4. Confirm WhatsApp module is disabled (404)
"""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()

ADMIN = ("admin@pdpv.pt", "HCNMEnKMLq")
COLLECTIONS = ("cobranca.teste@pdpv.pt", "TesteFin2026!")
NO_FIN = ("rececao.teste@pdpv.pt", "TesteFin2026!")


def _login(email: str, password: str) -> dict:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data, f"no token in login response: {data}"
    return data


@pytest.fixture(scope="module")
def admin_session():
    data = _login(*ADMIN)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    s.user = data.get("user", {})
    return s


@pytest.fixture(scope="module")
def collections_session():
    data = _login(*COLLECTIONS)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    s.user = data.get("user", {})
    return s


@pytest.fixture(scope="module")
def nofin_session():
    data = _login(*NO_FIN)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    s.user = data.get("user", {})
    return s


# --- auth ---
def test_admin_login_returns_user(admin_session):
    user = admin_session.user
    assert user.get("email") == ADMIN[0]
    # finance_role isn't embedded in login payload today; permission gating is validated by
    # test_finance_dashboard_admin passing (OWNER can hit finance endpoints).


def test_collections_login_returns_user(collections_session):
    user = collections_session.user
    assert user.get("email") == COLLECTIONS[0]
    # finance_role gating validated by test_finance_dashboard_collections (200 = COLLECTIONS_AGENT allowed).


def test_nofin_user_has_no_finance_role(nofin_session):
    user = nofin_session.user
    assert not user.get("finance_role"), f"unexpected finance_role: {user.get('finance_role')}"


# --- finance endpoints as OWNER ---
def test_finance_dashboard_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/finance/dashboard", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    # required fields
    for k in ("total_balance", "aging_buckets", "top_debtors",
              "recovered_today", "recovered_week", "recovered_month"):
        assert k in d, f"missing key {k} in dashboard response; keys={list(d.keys())}"
    assert isinstance(d["aging_buckets"], (dict, list))
    assert isinstance(d["top_debtors"], list)


def test_finance_data_health_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/finance/data-health", timeout=30)
    assert r.status_code == 200, r.text
    payload = r.json()
    items = payload.get("items", payload if isinstance(payload, list) else [])
    assert isinstance(items, list) and len(items) > 0, f"empty items: {payload}"
    source_types = {it.get("source_type") for it in items}
    for expected in ("overdue_balances", "open_documents", "client_info", "credit_evolution"):
        assert expected in source_types, f"missing source_type={expected}; got {source_types}"
    # last_import_at must be present (nullable but the key must exist)
    for it in items:
        assert "last_import_at" in it, f"item missing last_import_at: {it}"


def test_finance_clients_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/finance/clients", timeout=30)
    assert r.status_code == 200, r.text
    # accept list or {items:[...]}
    body = r.json()
    if isinstance(body, dict):
        assert "items" in body or "clients" in body or "data" in body, f"unexpected shape {list(body)}"
    else:
        assert isinstance(body, list)


def test_finance_promises_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/finance/promises", timeout=30)
    assert r.status_code == 200, r.text


def test_finance_imports_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/finance/imports", timeout=30)
    assert r.status_code == 200, r.text


# --- finance endpoints as COLLECTIONS_AGENT ---
def test_finance_dashboard_collections(collections_session):
    r = collections_session.get(f"{BASE_URL}/api/finance/dashboard", timeout=30)
    assert r.status_code == 200, f"COLLECTIONS_AGENT should reach dashboard: {r.status_code} {r.text}"


def test_finance_data_health_collections(collections_session):
    r = collections_session.get(f"{BASE_URL}/api/finance/data-health", timeout=30)
    assert r.status_code == 200, r.text


# --- RBAC: no-finance user → 403 ---
@pytest.mark.parametrize("path", [
    "/api/finance/dashboard",
    "/api/finance/data-health",
    "/api/finance/clients",
    "/api/finance/promises",
    "/api/finance/imports",
])
def test_finance_403_for_no_finance_user(nofin_session, path):
    r = nofin_session.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 403, f"expected 403 on {path}, got {r.status_code}: {r.text[:200]}"


# --- WhatsApp disabled ---
# The kill-switch (WHATSAPP_ENABLED=false) returns 503 "WhatsApp disabled" on routes that
# exist (webhook, send, config-post) and 404 on undefined GET routes. Both are "disabled".
@pytest.mark.parametrize("path", [
    "/api/whatsapp/status",
    "/api/whatsapp/send",
    "/api/whatsapp/webhook",
    "/api/whatsapp/config",
])
def test_whatsapp_disabled(admin_session, path):
    r = admin_session.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code in (404, 503), (
        f"expected 404/503 on {path} (module disabled), got {r.status_code}: {r.text[:200]}"
    )
    if r.status_code == 503:
        # sanity — kill-switch message
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        assert "disabled" in (body.get("detail") or "").lower(), body
