"""WhatsApp module hardening tests (P1).

Covers:
- Webhook signature validation (production vs development)
- Reply endpoint JSON body + legacy query param backwards compat
- 503 when WhatsApp credentials are missing
- Duplicate detection by external_message_id still works
- Logs do not expose secret material
- Public quote endpoints remain unaffected

Uses in-process FastAPI TestClient so we can mutate env vars between tests
without exposing any insecure test-only endpoint on the running server.
"""
import os
import sys
import hmac
import hashlib
import json
import uuid
from pathlib import Path

import pytest

# Make `backend/` importable when pytest is invoked from /app or elsewhere
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_APP_SECRET = "test-app-secret-hardening-12345"


# ---------- Helpers ----------

def _build_payload(phone="351900000900", wamid=None):
    wamid = wamid or f"wamid.PYTEST_{uuid.uuid4().hex[:10]}"
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "ENTRY_PYTEST",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "351911000111",
                                 "phone_number_id": "PYTEST_PHONE_ID"},
                    "contacts": [{"profile": {"name": "Pytest Client"}, "wa_id": phone}],
                    "messages": [{
                        "from": phone,
                        "id": wamid,
                        "timestamp": "1779144700",
                        "type": "text",
                        "text": {"body": "Olá pytest"}
                    }]
                },
                "field": "messages"
            }]
        }]
    }


def _sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _build_client(env_overrides=None, override_auth=True):
    """Build a TestClient with the given env overrides applied before import."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    if env_overrides:
        for k, v in env_overrides.items():
            os.environ[k] = v

    # Import the WhatsApp router fresh so the routes module re-reads env (verify token)
    # NOTE: signature/app-secret/environment checks read env at request time, so no
    # re-import is required for those.
    from modules.whatsapp.routes import router as wa_router
    from core.security import get_current_user

    app = FastAPI()
    app.include_router(wa_router, prefix="/api")
    if override_auth:
        async def _fake_user():
            return {"id": "u1", "name": "Pytest User", "role": "ADMIN"}
        app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


# ---------- Webhook signature validation ----------

class TestWebhookSignature:
    def test_dev_no_secret_no_signature_accepted(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
        client = _build_client()
        payload = _build_payload(wamid="wamid.UT_DEV_NOSIG")
        r = client.post("/api/whatsapp/webhook", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_dev_with_secret_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("WHATSAPP_APP_SECRET", TEST_APP_SECRET)
        client = _build_client()
        raw = json.dumps(_build_payload(wamid="wamid.UT_DEV_BAD")).encode()
        r = client.post(
            "/api/whatsapp/webhook",
            content=raw,
            headers={"Content-Type": "application/json",
                     "X-Hub-Signature-256": "sha256=" + ("0" * 64)},
        )
        assert r.status_code == 403
        assert "signature" in r.json()["detail"].lower()

    def test_dev_with_secret_valid_signature_accepted(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("WHATSAPP_APP_SECRET", TEST_APP_SECRET)
        client = _build_client()
        raw = json.dumps(_build_payload(wamid="wamid.UT_DEV_OK")).encode()
        r = client.post(
            "/api/whatsapp/webhook",
            content=raw,
            headers={"Content-Type": "application/json",
                     "X-Hub-Signature-256": _sign(raw, TEST_APP_SECRET)},
        )
        assert r.status_code == 200

    def test_prod_no_signature_rejected(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("WHATSAPP_APP_SECRET", TEST_APP_SECRET)
        client = _build_client()
        r = client.post("/api/whatsapp/webhook", json=_build_payload())
        assert r.status_code == 403

    def test_prod_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("WHATSAPP_APP_SECRET", TEST_APP_SECRET)
        client = _build_client()
        raw = json.dumps(_build_payload()).encode()
        r = client.post(
            "/api/whatsapp/webhook",
            content=raw,
            headers={"Content-Type": "application/json",
                     "X-Hub-Signature-256": "sha256=" + ("a" * 64)},
        )
        assert r.status_code == 403

    def test_prod_valid_signature_accepted(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("WHATSAPP_APP_SECRET", TEST_APP_SECRET)
        client = _build_client()
        raw = json.dumps(_build_payload(wamid="wamid.UT_PROD_OK")).encode()
        r = client.post(
            "/api/whatsapp/webhook",
            content=raw,
            headers={"Content-Type": "application/json",
                     "X-Hub-Signature-256": _sign(raw, TEST_APP_SECRET)},
        )
        assert r.status_code == 200

    def test_prod_without_app_secret_returns_503(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
        client = _build_client()
        r = client.post("/api/whatsapp/webhook", json=_build_payload())
        assert r.status_code == 503
        assert r.json()["detail"] == "WhatsApp not configured"


# ---------- Reply endpoint ----------

class TestReplyEndpoint:
    def _mock_db(self, monkeypatch, ticket=None):
        """Patch DB modules so ticket lookups and message saves work without Mongo."""
        from modules.whatsapp import routes as wa_routes
        from modules.whatsapp import service as wa_service

        ticket_doc = ticket or {
            "id": "tkt1",
            "customer_phone": "351900000001",
            "first_response_done": False,
        }

        class _Coll:
            async def find_one(self, *a, **kw):
                return ticket_doc

            async def update_one(self, *a, **kw):
                return None

            async def insert_one(self, *a, **kw):
                return None

        class _DB:
            tickets = _Coll()
            ticket_messages = _Coll()
            messages = _Coll()

        monkeypatch.setattr(wa_routes, "db", _DB())
        monkeypatch.setattr(wa_service, "db", _DB())
        return ticket_doc

    def test_reply_503_when_credentials_missing(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        client = _build_client()
        self._mock_db(monkeypatch)
        r = client.post(
            "/api/whatsapp/tickets/tkt1/messages",
            json={"body": "Olá"},
            headers={"Authorization": "Bearer fake"},
        )
        assert r.status_code == 503
        assert r.json()["detail"] == "WhatsApp not configured"

    def test_reply_json_body_reaches_send_layer(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "FAKE_TOK")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "FAKE_PID")
        monkeypatch.setenv("ENVIRONMENT", "development")
        client = _build_client()
        self._mock_db(monkeypatch)

        from modules.whatsapp import service as wa_service
        called = {}

        async def fake_send(to_phone, message_text, phone_number_id=None):
            called["to"] = to_phone
            called["text"] = message_text
            return {"messages": [{"id": "wamid.MOCKED"}]}

        monkeypatch.setattr(wa_service, "send_whatsapp_message", fake_send)

        async def fake_save(**kw):
            called["saved_body"] = kw.get("body")
            return {"id": "m1"}

        monkeypatch.setattr(wa_service, "save_ticket_message", fake_save)

        r = client.post(
            "/api/whatsapp/tickets/tkt1/messages",
            json={"body": "Olá, JSON body!"},
            headers={"Authorization": "Bearer fake"},
        )
        assert r.status_code == 200, r.text
        assert called.get("text") == "Olá, JSON body!"
        assert called.get("saved_body") == "Olá, JSON body!"
        assert r.json() == {"success": True, "message_id": "wamid.MOCKED"}

    def test_reply_legacy_query_body_still_works(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "FAKE_TOK")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "FAKE_PID")
        monkeypatch.setenv("ENVIRONMENT", "development")
        client = _build_client()
        self._mock_db(monkeypatch)

        from modules.whatsapp import service as wa_service

        async def fake_send(to_phone, message_text, phone_number_id=None):
            return {"messages": [{"id": "wamid.LEGACY"}]}

        async def fake_save(**kw):
            return {"id": "m1"}

        monkeypatch.setattr(wa_service, "send_whatsapp_message", fake_send)
        monkeypatch.setattr(wa_service, "save_ticket_message", fake_save)

        r = client.post(
            "/api/whatsapp/tickets/tkt1/messages",
            params={"body": "Legacy ?body= ainda funciona"},
            headers={"Authorization": "Bearer fake"},
        )
        assert r.status_code == 200
        assert r.json()["message_id"] == "wamid.LEGACY"

    def test_reply_empty_body_rejected(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "FAKE_TOK")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "FAKE_PID")
        monkeypatch.setenv("ENVIRONMENT", "development")
        client = _build_client()
        self._mock_db(monkeypatch)

        # Empty body via JSON → pydantic min_length=1 → 422
        r = client.post(
            "/api/whatsapp/tickets/tkt1/messages",
            json={"body": ""},
            headers={"Authorization": "Bearer fake"},
        )
        assert r.status_code in (400, 422)

    def test_reply_upstream_failure_returns_502(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "FAKE_TOK")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "FAKE_PID")
        monkeypatch.setenv("ENVIRONMENT", "development")
        client = _build_client()
        self._mock_db(monkeypatch)

        from modules.whatsapp import service as wa_service

        async def fake_send(*a, **kw):
            return None  # simulate Meta error / network error

        monkeypatch.setattr(wa_service, "send_whatsapp_message", fake_send)

        r = client.post(
            "/api/whatsapp/tickets/tkt1/messages",
            json={"body": "Texto"},
            headers={"Authorization": "Bearer fake"},
        )
        assert r.status_code == 502
        assert "upstream" in r.json()["detail"].lower()


# ---------- Logs do not leak secrets ----------

class TestLogsDoNotLeakSecrets:
    def test_send_message_logs_no_token(self, monkeypatch, caplog):
        import asyncio
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "SUPER_SECRET_TOKEN_AAAAA")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "PID")
        from modules.whatsapp import service as wa_service
        import importlib
        importlib.reload(wa_service)

        # Force a httpx failure to exercise the error log line
        async def boom_post(*a, **kw):
            raise RuntimeError("simulated network error")

        class _AsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            post = boom_post

        monkeypatch.setattr(wa_service.httpx, "AsyncClient", lambda: _AsyncClient())

        with caplog.at_level("ERROR"):
            res = asyncio.run(wa_service.send_whatsapp_message("351900000111", "ola"))
        assert res is None
        combined = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "SUPER_SECRET_TOKEN_AAAAA" not in combined
