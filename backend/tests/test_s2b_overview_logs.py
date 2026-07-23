"""Sprint 2 / S2-B — Overview, Logs and permissions for the Telegram admin area."""
import os

import httpx
import pytest

os.environ.setdefault("TELEGRAM_INTERNAL_BOT_TOKEN", "TEST_TOKEN_1234")

API_BASE = "http://localhost:8001"


async def _admin_token() -> str:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.post("/api/auth/login", json={
            "email": "admin@pdpv.pt", "password": "HCNMEnKMLq"
        })
        r.raise_for_status()
        d = r.json()
        return d.get("access_token") or d.get("token") or ""


async def _finance_only_token() -> str:
    """Login as the FINANCE_ONLY test user (should be denied for /admin/telegram/*)."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.post("/api/auth/login", json={
            "email": "financeiro.teste@pdpv.pt", "password": "FinPuro2026!"
        })
        r.raise_for_status()
        d = r.json()
        return d.get("access_token") or d.get("token") or ""


async def test_overview_admin_success():
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.get(
            "/api/telegram/internal/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "bot" in data and "webhook" in data and "counters" in data and "modules" in data
    assert set(data["modules"].keys()) == {"pre_ticket", "renting", "assistencias", "mech_alert"}
    # Never leak the full webhook URL (should be url_display only)
    if data.get("webhook"):
        assert "url" not in data["webhook"], "raw webhook URL must not be exposed"
        assert "url_display" in data["webhook"]


async def test_overview_forbidden_for_non_admin():
    """FINANCE_ONLY (or any non-admin) must not reach overview."""
    token = await _finance_only_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.get(
            "/api/telegram/internal/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
    # FINANCE_ONLY is blocked by the finance-only middleware BEFORE reaching
    # the route; either 403 (route-level) or 403 (middleware) is acceptable.
    assert r.status_code in (401, 403), r.text


async def test_overview_no_auth_returns_401_or_403():
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as c:
        r = await c.get("/api/telegram/internal/overview")
    assert r.status_code in (401, 403)


async def test_logs_admin_ok_and_no_sensitive_fields():
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.get(
            "/api/telegram/internal/logs?limit=10",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    data = r.json()
    assert "logs" in data
    allowed = {
        "update_id", "message_type", "chat_id", "telegram_user_id",
        "module", "callback_action", "internal_user_id",
        "error", "error_id", "created_at", "processing_time_ms", "http_status",
    }
    for row in data["logs"]:
        # No key outside the allowlist is ever returned.
        extra = set(row.keys()) - allowed
        assert not extra, f"unexpected fields in log row: {extra}"
        # And no matter what, never a token or a raw URL leaks.
        blob = str(row)
        assert "TEST_TOKEN_1234" not in blob
        assert "https://api.telegram.org" not in blob


async def test_logs_filter_by_module_returns_only_that_module():
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.get(
            "/api/telegram/internal/logs?module=unknown&limit=50",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    for row in r.json().get("logs", []):
        # Rows without an explicit module get returned by module=unknown ONLY
        # when we start enriching logs in S2-C. Until then a filter with
        # a non-existing module simply returns [] — accept both cases.
        m = row.get("module")
        assert m in (None, "unknown")
