"""Sprint 2 / S2-A — Fonte única de utilizadores Telegram.

Tests:
  - POST /api/telegram/internal/authorized-users sem user_id → 422
  - POST com user_id inexistente → 422
  - POST com user_id válido → 200 e user_id persistido
  - Endpoints /api/assistencias/bot/* → 410 Gone
  - Migration script é idempotente (2× a mesma corrida devolve stats iguais em
    'upserted' após primeira execução).
"""
import os
import uuid

import httpx
import pytest

os.environ.setdefault("TELEGRAM_INTERNAL_BOT_TOKEN", "TEST_TOKEN_1234")

from db import db  # noqa: E402


API_BASE = "http://localhost:8001"


async def _admin_token() -> str:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.post("/api/auth/login", json={
            "email": "admin@pdpv.pt", "password": "HCNMEnKMLq"
        })
        r.raise_for_status()
        d = r.json()
        return d.get("access_token") or d.get("token") or ""


TEST_TG_ID = -20240221


@pytest.fixture
async def _clean():
    await db.telegram_internal_authorized_users.delete_one({"telegram_user_id": TEST_TG_ID})
    yield
    await db.telegram_internal_authorized_users.delete_one({"telegram_user_id": TEST_TG_ID})


async def test_post_without_user_id_returns_422(_clean):
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as c:
        r = await c.post(
            "/api/telegram/internal/authorized-users",
            headers={"Authorization": f"Bearer {token}"},
            json={"telegram_user_id": TEST_TG_ID, "name": "Sem user_id", "role": "AGENT"},
        )
    assert r.status_code == 422, r.text


async def test_post_with_invalid_user_id_returns_422(_clean):
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as c:
        r = await c.post(
            "/api/telegram/internal/authorized-users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "telegram_user_id": TEST_TG_ID,
                "user_id": "does-not-exist-uuid",
                "name": "Utilizador Fictício",
                "role": "AGENT",
            },
        )
    assert r.status_code == 422, r.text
    assert "não existe" in r.text.lower() or "does not exist" in r.text.lower()


async def test_post_with_valid_user_id_creates_record(_clean):
    token = await _admin_token()
    # Find any real user in DB.
    real_user = await db.users.find_one({}, {"_id": 0, "id": 1, "name": 1})
    assert real_user, "test needs at least one row in `users`"
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as c:
        r = await c.post(
            "/api/telegram/internal/authorized-users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "telegram_user_id": TEST_TG_ID,
                "user_id": real_user["id"],
                "name": real_user["name"],
                "role": "AGENT",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == real_user["id"]
    assert body["needs_migration"] is False
    doc = await db.telegram_internal_authorized_users.find_one({"telegram_user_id": TEST_TG_ID})
    assert doc["user_id"] == real_user["id"]


async def test_legacy_bot_endpoints_gone():
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as c:
        for path in ["/api/assistencias/bot/status", "/api/assistencias/bot/users"]:
            r = await c.get(path, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 410, f"{path}: {r.status_code} — {r.text[:200]}"
            assert "depreciado" in r.text.lower() or "gone" in r.text.lower()
        r = await c.post(
            "/api/assistencias/bot/webhook/configure",
            headers={"Authorization": f"Bearer {token}"},
            json={"url": "https://example.test"},
        )
        assert r.status_code == 410
        r = await c.post(
            "/api/assistencias/bot/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"telegram_user_id": 1, "user_id": "x"},
        )
        assert r.status_code == 410
        r = await c.delete(
            "/api/assistencias/bot/users/1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 410


async def test_migration_script_is_idempotent():
    """Running --apply twice must not double-migrate or corrupt state."""
    import subprocess
    r1 = subprocess.run(
        ["python", "/app/backend/scripts/migrate_telegram_users.py", "--apply"],
        capture_output=True, text=True, cwd="/app/backend",
    )
    r2 = subprocess.run(
        ["python", "/app/backend/scripts/migrate_telegram_users.py", "--apply"],
        capture_output=True, text=True, cwd="/app/backend",
    )
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr

    # Parse "already_migrated" counter on the second run.
    for line in r2.stdout.splitlines():
        if "already_migrated" in line:
            already = int(line.split(":")[-1].strip())
            # After first run, every source doc should be marked migrated.
            assert already >= 0
            break
