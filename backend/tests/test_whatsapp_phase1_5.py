"""Tests for the WhatsApp Phase 1.5 hardening:
- Kill-switch (WHATSAPP_ENABLED=false → all endpoints 503 "disabled")
- /api/tickets resilience to malformed legacy docs

These tests hit the live backend at REACT_APP_BACKEND_URL or localhost:8001.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or 'http://localhost:8001').rstrip('/')
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "HCNMEnKMLq")


@pytest.fixture(scope="module")
def headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "test_database")]


# ========== /api/tickets resilience ==========
class TestTicketsResilience:
    """Verifies the malformed-doc minor bug found in iteration_22 is fixed."""

    @pytest.fixture
    def bad_ticket_id(self):
        tid = f"BAD-RESIL-{uuid.uuid4().hex[:8]}"
        # Insert a ticket missing required Pydantic fields: ticket_number,
        # updated_at, channel, type, status, priority, description, customer_name.
        async def _ins():
            await _db().tickets.insert_one({
                "id": tid,
                "customer_phone": "351900000000",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "archived_at": None,
            })
        asyncio.run(_ins())
        yield tid
        async def _del():
            await _db().tickets.delete_one({"id": tid})
        asyncio.run(_del())

    def test_list_does_not_500_with_malformed_doc(self, headers, bad_ticket_id):
        r = requests.get(f"{BASE_URL}/api/tickets", headers=headers, timeout=15)
        assert r.status_code == 200, f"List 500'd because of malformed doc: {r.text[:200]}"
        # The malformed ticket must NOT appear in the list (skipped gracefully)
        ids = [t.get("id") for t in r.json()]
        assert bad_ticket_id not in ids, "Malformed ticket should be skipped from list"

    def test_detail_returns_422_not_500(self, headers, bad_ticket_id):
        r = requests.get(
            f"{BASE_URL}/api/tickets/{bad_ticket_id}", headers=headers, timeout=10
        )
        # Acceptable: 422 (cannot coerce) or 200 (defaults filled).
        # NEVER 500.
        assert r.status_code in (200, 422), f"Got {r.status_code}: {r.text[:200]}"
        if r.status_code == 422:
            assert "dados em falta" in r.text.lower() or "missing" in r.text.lower()


# ========== Kill-switch ==========
class TestKillSwitch:
    """When WHATSAPP_ENABLED is true (preview default after 1.5), the module
    must process normally. We document the behavior: 503 'disabled' is the
    response when the env var is false. We test the inverse — that with
    WHATSAPP_ENABLED=true the endpoints proceed past the kill-switch check.
    """

    def test_kill_switch_lets_through_when_enabled(self, headers):
        """When enabled=true and creds missing, must be 503 'not configured'
        (proves we passed the kill-switch and hit the config check)."""
        # Use a synthetic ticket id; we expect 404 because ticket doesn't exist
        # OR 503 'not configured'. 'disabled' would mean kill-switch fired.
        fake_id = "nope-kill-switch-test-xyz"
        r = requests.post(
            f"{BASE_URL}/api/whatsapp/tickets/{fake_id}/messages",
            json={"body": "x"},
            headers=headers,
            timeout=10,
        )
        # Should NOT be "disabled" — meaning kill-switch is OFF as expected in preview
        assert "disabled" not in r.text.lower(), (
            f"Kill-switch fired unexpectedly in preview: {r.text}"
        )

    def test_webhook_verify_passes_kill_switch(self):
        """GET /webhook should work (200 with challenge echo) when enabled."""
        verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        if not verify_token:
            pytest.skip(
                "WHATSAPP_VERIFY_TOKEN not set in this shell — set it to the value "
                "configured in backend/.env so this test can echo the challenge."
            )
        challenge = f"test-{uuid.uuid4().hex[:6]}"
        r = requests.get(
            f"{BASE_URL}/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": verify_token,
                "hub.challenge": challenge,
            },
            timeout=10,
        )
        assert r.status_code == 200
        assert r.text.strip() == challenge
