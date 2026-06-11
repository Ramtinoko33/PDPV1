"""WhatsApp Phase 1 validation tests.

Covers:
- Auth-required endpoints (templates, window)
- 503 when WhatsApp creds missing on outbound endpoints
- Webhook inbound -> creates intake_request (never a ticket), dedupe, plate suggestion,
  attaches to existing open ticket within 24h
- Webhook status updates the ticket_messages status
"""
import os
import time
import uuid
import asyncio
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/') or 'http://localhost:8001'
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ---------- helpers using direct mongo ----------
def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "test_database")]


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ===================== Templates =====================
class TestTemplates:
    def test_templates_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/whatsapp/templates", timeout=10)
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_templates_list_ok(self, headers):
        r = requests.get(f"{BASE_URL}/api/whatsapp/templates", headers=headers, timeout=10)
        assert r.status_code == 200, r.text
        ids = {t["id"] for t in r.json()}
        assert {"tire_size", "km_request", "quote_link", "received"}.issubset(ids), ids


# ===================== Ticket fixture =====================
@pytest.fixture(scope="session")
def test_ticket():
    """Insert a test ticket with last_inbound_whatsapp_at recent so window is OPEN."""
    tid = f"TEST-WA-{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": tid,
        "ticket_number": f"T-{tid}",
        "customer_phone": "351900111222",
        "customer_name": "TEST Cliente WA",
        "vehicle_plate": "22-AA-33",
        "status": "NOVO",
        "archived_at": None,
        "created_at": now_iso,
        "last_inbound_whatsapp_at": now_iso,
        "reply_token": uuid.uuid4().hex,
    }
    async def _ins():
        await _db().tickets.insert_one(doc)
    run(_ins())
    yield doc
    async def _del():
        await _db().tickets.delete_one({"id": tid})
        await _db().ticket_messages.delete_many({"ticket_id": tid})
    run(_del())


@pytest.fixture(scope="session")
def ticket_no_inbound():
    """Ticket WITHOUT last_inbound — window must be closed."""
    tid = f"TEST-WA-NOIN-{uuid.uuid4().hex[:6]}"
    doc = {
        "id": tid, "ticket_number": f"T-{tid}",
        "customer_phone": "351900333444", "customer_name": "TEST NoIn",
        "vehicle_plate": "44-BB-55", "status": "NOVO", "archived_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    async def _ins():
        await _db().tickets.insert_one(doc)
    run(_ins())
    yield doc
    async def _del():
        await _db().tickets.delete_one({"id": tid})
    run(_del())


# ===================== Window =====================
class TestWindow:
    def test_window_open(self, headers, test_ticket):
        r = requests.get(f"{BASE_URL}/api/whatsapp/tickets/{test_ticket['id']}/window",
                         headers=headers, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["active"] is True
        assert d["last_inbound_at"] is not None
        assert d["expires_at"] is not None

    def test_window_closed_no_inbound(self, headers, ticket_no_inbound):
        r = requests.get(f"{BASE_URL}/api/whatsapp/tickets/{ticket_no_inbound['id']}/window",
                         headers=headers, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["active"] is False
        assert d["last_inbound_at"] is None
        assert d["reason"]

    def test_window_404(self, headers):
        r = requests.get(f"{BASE_URL}/api/whatsapp/tickets/nope-xyz/window",
                         headers=headers, timeout=10)
        assert r.status_code == 404


# ===================== Send endpoints: 503 (creds missing) =====================
class TestSendBlocked:
    def test_send_message_503(self, headers, test_ticket):
        r = requests.post(f"{BASE_URL}/api/whatsapp/tickets/{test_ticket['id']}/messages",
                          json={"body": "Olá teste"}, headers=headers, timeout=10)
        # In preview, no WHATSAPP_ACCESS_TOKEN => must be 503 (not 500, not 200)
        assert r.status_code == 503, f"Expected 503 got {r.status_code} body={r.text}"
        assert "not configured" in r.text.lower()

    def test_send_quote_link_503(self, headers, test_ticket):
        r = requests.post(f"{BASE_URL}/api/whatsapp/tickets/{test_ticket['id']}/send-quote-link",
                          json={}, headers=headers, timeout=10)
        assert r.status_code == 503, f"Expected 503 got {r.status_code} body={r.text}"


# ===================== Webhook flows =====================
def _inbound_payload(phone, wamid, text):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WA_BIZ_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "351900000000", "phone_number_id": "PHONE_ID"},
                    "contacts": [{"profile": {"name": "Cliente Teste"}, "wa_id": phone}],
                    "messages": [{"from": phone, "id": wamid, "timestamp": "1709000000",
                                  "type": "text", "text": {"body": text}}]
                },
                "field": "messages"
            }]
        }]
    }


def _status_payload(wamid, status):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WA_BIZ_ID", "changes": [{"value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "351900000000", "phone_number_id": "PHONE_ID"},
            "statuses": [{"id": wamid, "status": status, "timestamp": "1709000060",
                          "recipient_id": "351912345678"}]
        }, "field": "messages"}]}]
    }


class TestWebhookInbound:
    @pytest.fixture(scope="class")
    def cleanup(self):
        yield
        async def _clean():
            await _db().intake_requests.delete_many({"sender_phone": {"$regex": "^351777"}})
            await _db().ticket_messages.delete_many({"external_message_id": {"$regex": "^wamid.TEST"}})
        run(_clean())

    def test_inbound_creates_intake_not_ticket(self, cleanup):
        phone = "351777000111"
        wamid = f"wamid.TEST_{uuid.uuid4().hex[:8]}"
        # snapshot
        async def _count_tickets():
            return await _db().tickets.count_documents({"customer_phone": phone})
        before = run(_count_tickets())
        r = requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                          json=_inbound_payload(phone, wamid, "Bom dia"), timeout=10)
        assert r.status_code == 200
        time.sleep(1.5)
        # Verify NO ticket created
        after = run(_count_tickets())
        assert after == before, f"webhook created a ticket! before={before} after={after}"
        # Verify intake_request created
        async def _find_intake():
            return await _db().intake_requests.find_one(
                {"sender_phone": phone, "source_bot": "whatsapp_meta"}, {"_id": 0})
        intake = run(_find_intake())
        assert intake is not None, "no intake_request created"
        assert intake["channel"] == "WHATSAPP"
        assert intake["status"] == "PENDING"
        assert intake["source"] == "whatsapp"
        assert intake["sender_phone"] == phone
        # Verify ticket_messages entry was saved with intake_id
        async def _find_msg():
            return await _db().ticket_messages.find_one(
                {"external_message_id": wamid}, {"_id": 0})
        msg = run(_find_msg())
        assert msg is not None
        assert msg["channel"] == "whatsapp"
        assert msg["intake_id"] == intake["id"]
        assert msg.get("raw_payload_id"), "raw_payload_id missing"

    def test_inbound_dedupe(self, cleanup):
        phone = "351777000222"
        wamid = f"wamid.TEST_DEDUPE_{uuid.uuid4().hex[:6]}"
        for _ in range(2):
            r = requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                              json=_inbound_payload(phone, wamid, "dup"), timeout=10)
            assert r.status_code == 200
        time.sleep(1.5)
        async def _count():
            return await _db().ticket_messages.count_documents({"external_message_id": wamid})
        cnt = run(_count())
        assert cnt == 1, f"dedupe failed: count={cnt}"

    def test_inbound_second_msg_attaches_to_existing_intake(self, cleanup):
        phone = "351777000333"
        wamid1 = f"wamid.TEST_A_{uuid.uuid4().hex[:6]}"
        wamid2 = f"wamid.TEST_B_{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                      json=_inbound_payload(phone, wamid1, "primeira"), timeout=10)
        time.sleep(1.0)
        requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                      json=_inbound_payload(phone, wamid2, "segunda"), timeout=10)
        time.sleep(1.5)
        async def _count_intakes():
            return await _db().intake_requests.count_documents(
                {"sender_phone": phone, "source_bot": "whatsapp_meta"})
        intake_count = run(_count_intakes())
        assert intake_count == 1, f"second message created a new intake (count={intake_count})"

    def test_inbound_with_plate_suggests_ticket(self, cleanup):
        # Pre-create open ticket with plate 22-AA-33
        tid = f"TEST-WA-PLATE-{uuid.uuid4().hex[:6]}"
        async def _ins_ticket():
            await _db().tickets.insert_one({
                "id": tid, "ticket_number": f"T-{tid}",
                "customer_phone": "351888000999",
                "customer_name": "TEST Plate",
                "vehicle_plate": "22-AA-33",
                "status": "NOVO", "archived_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        run(_ins_ticket())
        phone = "351777000444"
        wamid = f"wamid.TEST_PLATE_{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                      json=_inbound_payload(phone, wamid, "minha matricula 22-AA-33"), timeout=10)
        time.sleep(1.5)
        async def _find_intake():
            return await _db().intake_requests.find_one(
                {"sender_phone": phone}, {"_id": 0})
        intake = run(_find_intake())
        assert intake is not None
        assert intake.get("suggested_plate") == "22-AA-33"
        assert intake.get("suggested_ticket_id") == tid
        # cleanup
        async def _clean():
            await _db().tickets.delete_one({"id": tid})
        run(_clean())

    def test_inbound_attaches_to_existing_open_ticket_within_24h(self, cleanup):
        # Pre-create open ticket recent for phone X
        tid = f"TEST-WA-OPENT-{uuid.uuid4().hex[:6]}"
        phone = "351777000555"
        async def _ins_ticket():
            await _db().tickets.insert_one({
                "id": tid, "ticket_number": f"T-{tid}",
                "customer_phone": phone,
                "customer_name": "TEST Open",
                "vehicle_plate": "11-AA-22",
                "status": "NOVO", "archived_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        run(_ins_ticket())
        wamid = f"wamid.TEST_OPENT_{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                      json=_inbound_payload(phone, wamid, "estou aqui"), timeout=10)
        time.sleep(1.5)
        # Must NOT create intake
        async def _intake_count():
            return await _db().intake_requests.count_documents(
                {"sender_phone": phone, "source_bot": "whatsapp_meta"})
        n_intake = run(_intake_count())
        assert n_intake == 0, f"intake unexpectedly created for phone with open ticket: {n_intake}"
        # Message must be attached to ticket
        async def _find_msg():
            return await _db().ticket_messages.find_one(
                {"external_message_id": wamid}, {"_id": 0})
        msg = run(_find_msg())
        assert msg is not None
        assert msg["ticket_id"] == tid
        async def _clean():
            await _db().tickets.delete_one({"id": tid})
            await _db().ticket_messages.delete_many({"ticket_id": tid})
        run(_clean())


class TestWebhookStatus:
    def test_status_updates_message(self):
        # First, create an outbound-ish message via webhook inbound + then send status for it
        phone = "351777666111"
        wamid = f"wamid.TEST_STAT_{uuid.uuid4().hex[:6]}"
        # Insert outbound message directly so we can test status update logic
        async def _ins_msg():
            await _db().ticket_messages.insert_one({
                "id": str(uuid.uuid4()),
                "ticket_id": "fake-ticket",
                "intake_id": None,
                "direction": "outbound",
                "channel": "whatsapp",
                "external_message_id": wamid,
                "status": "pending",
                "body": "test",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        run(_ins_msg())
        r = requests.post(f"{BASE_URL}/api/whatsapp/webhook",
                          json=_status_payload(wamid, "delivered"), timeout=10)
        assert r.status_code == 200
        time.sleep(1.5)
        async def _find():
            return await _db().ticket_messages.find_one(
                {"external_message_id": wamid}, {"_id": 0})
        msg = run(_find())
        assert msg is not None
        assert msg["status"] == "delivered", f"status not updated: {msg.get('status')}"
        async def _clean():
            await _db().ticket_messages.delete_one({"external_message_id": wamid})
        run(_clean())
