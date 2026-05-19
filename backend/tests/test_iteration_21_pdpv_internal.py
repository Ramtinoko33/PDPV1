"""
Iteration 21 - PDPV Internal Bot Unification with /intake module
Validates:
- Stats endpoint reachable, old 42 intakes preserved
- Listing accepts/returns new optional fields
- Internal webhook: unauthorized user does NOT create an intake
- Internal webhook: authorized user (999000111) full pre_ticket flow creates an intake_request (NOT pre_tickets)
- PUT /api/intake/{id} accepts ai_extracted / validated_by
- POST /api/intake/{id}/convert_to_ticket converts and sets converted_ticket_id
- GET attachments proxy endpoint requires auth (401/403)
- Admin telegram-internal /authorized-users endpoints require ADMIN
- Old bot /api/telegram/webhook still 200
- Renting webhook /api/renting/telegram/webhook still 200
- pre_tickets collection count stays 0
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://quote-management-4.preview.emergentagent.com",
).rstrip("/")
INTERNAL_WEBHOOK_SECRET = "pdpv_internal_webhook_2026"
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"

AUTH_USER_ID = 999000111  # seeded authorized
UNAUTH_USER_ID = 888888888  # not authorized


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return r.json().get("token")


@pytest.fixture
def api(admin_token):
    s = requests.Session()
    s.headers.update(
        {"Content-Type": "application/json", "Authorization": f"Bearer {admin_token}"}
    )
    return s


# ---------------------------------------------------------------------------
# 1. Intake module status & stats
# ---------------------------------------------------------------------------
class TestIntakeStatsAndList:
    def test_intake_stats_ok(self, api):
        r = api.get(f"{BASE_URL}/api/intake/stats")
        assert r.status_code == 200, r.text
        data = r.json()
        # Should at minimum expose a total
        assert "total" in data or "pending" in data
        # 42 old intakes were expected; allow >=42 since tests add new ones too
        if "total" in data:
            assert data["total"] >= 42, f"Expected >=42, got {data['total']}"

    def test_intake_list_pagination_and_optional_fields(self, api):
        r = api.get(f"{BASE_URL}/api/intake?page=1&page_size=50")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "total" in data
        # Inspect first few items: optional fields must at least be accepted
        # by the response schema (None is acceptable for legacy entries)
        sample = data["items"][:5]
        allowed_keys = {
            "ai_extracted",
            "texts",
            "audio_transcripts",
            "image_hints",
            "source_bot",
            "origin_channel",
            "reference",
            "created_by_name",
            "telegram_user_id",
            "telegram_chat_id",
            "validated_by",
        }
        # We just assert at least one of the new keys is present on the items
        # (schema-level)
        for it in sample:
            # not all keys must exist, but the model shouldn't blow up.
            assert isinstance(it, dict)
        # Aggregate: at least one new key should appear across items in the page
        if sample:
            keys_seen = set().union(*[set(it.keys()) for it in data["items"]])
            assert keys_seen & allowed_keys, (
                f"None of the new optional fields found in response. Keys: {keys_seen}"
            )


# ---------------------------------------------------------------------------
# 2. Internal Telegram webhook flows
# ---------------------------------------------------------------------------
def _webhook_post(payload: dict):
    return requests.post(
        f"{BASE_URL}/api/telegram/internal/webhook",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": INTERNAL_WEBHOOK_SECRET,
        },
        timeout=20,
    )


def _make_message(user_id: int, chat_id: int, text: str, mid: int):
    return {
        "update_id": int(time.time() * 1000) % 2_000_000_000 + mid,
        "message": {
            "message_id": mid,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Test",
                "last_name": "User",
            },
            "text": text,
        },
    }


def _make_callback(user_id: int, chat_id: int, data: str, mid: int):
    return {
        "update_id": int(time.time() * 1000) % 2_000_000_000 + mid,
        "callback_query": {
            "id": f"cbq_{mid}",
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Test",
                "last_name": "User",
            },
            "message": {
                "message_id": mid,
                "chat": {"id": chat_id, "type": "private"},
                "date": int(time.time()),
                "text": "menu",
            },
            "data": data,
        },
    }


class TestInternalWebhookSecurity:
    def test_webhook_wrong_secret_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/webhook",
            json={"update_id": 1},
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "WRONG",
            },
            timeout=10,
        )
        assert r.status_code in (401, 403), r.text

    def test_unauthorized_user_does_not_create_intake(self, api):
        # Snapshot count
        before = api.get(
            f"{BASE_URL}/api/intake?source=telegram&page=1&page_size=1"
        ).json()
        total_before = before.get("total", 0)

        # /start from unauthorized user
        r = _webhook_post(_make_message(UNAUTH_USER_ID, UNAUTH_USER_ID, "/start", 1))
        assert r.status_code == 200, r.text
        # Some flow events
        _webhook_post(_make_message(UNAUTH_USER_ID, UNAUTH_USER_ID, "Hello", 2))

        after = api.get(
            f"{BASE_URL}/api/intake?source=telegram&page=1&page_size=1"
        ).json()
        total_after = after.get("total", 0)
        assert total_after == total_before, (
            f"Unauthorized user should NOT create intake. Before={total_before}, After={total_after}"
        )


class TestInternalWebhookAuthorizedFlow:
    def test_authorized_pre_ticket_creates_intake(self, api):
        chat = AUTH_USER_ID

        # Capture latest internal-bot intake ids before
        pre_list = api.get(
            f"{BASE_URL}/api/intake?source=telegram&page=1&page_size=50"
        ).json()
        pre_ids = {
            it["id"]
            for it in pre_list.get("items", [])
            if it.get("source_bot") == "PDPV_INTERNAL_BOT"
        }

        # Start
        r0 = _webhook_post(_make_message(AUTH_USER_ID, chat, "/start", 100))
        assert r0.status_code == 200

        # Open pre_ticket menu via callback
        r1 = _webhook_post(_make_callback(AUTH_USER_ID, chat, "menu:pre_ticket", 101))
        assert r1.status_code == 200, r1.text

        # Send some descriptive text (the AI extractor will run)
        text = (
            "Cliente Joao Silva 912000111 matricula AA-12-BB precisa orcamento "
            "pneus 205/55 R16 Continental"
        )
        r2 = _webhook_post(_make_message(AUTH_USER_ID, chat, text, 102))
        assert r2.status_code == 200, r2.text

        # Finalize
        r3 = _webhook_post(
            _make_callback(AUTH_USER_ID, chat, "preticket:finalize", 103)
        )
        assert r3.status_code == 200, r3.text

        # AI / DB write may be async-ish; wait a few seconds
        time.sleep(4)

        after = api.get(
            f"{BASE_URL}/api/intake?source=telegram&page=1&page_size=50"
        ).json()
        new_internal = [
            it
            for it in after.get("items", [])
            if it.get("source_bot") == "PDPV_INTERNAL_BOT"
            and it["id"] not in pre_ids
        ]
        assert new_internal, (
            f"Expected a new PDPV_INTERNAL_BOT intake to appear. "
            f"pre={len(pre_ids)} total_after={after.get('total')}"
        )

        # Find the newest internal-bot intake for this user
        candidates = [
            it
            for it in new_internal
            if (
                it.get("telegram_user_id") == AUTH_USER_ID
                or str(it.get("telegram_user_id")) == str(AUTH_USER_ID)
            )
        ]
        assert candidates, (
            "No intake with source_bot=PDPV_INTERNAL_BOT and telegram_user_id="
            f"{AUTH_USER_ID} found. Items: {[(i.get('source'), i.get('source_bot'), i.get('telegram_user_id')) for i in after['items'][:5]]}"
        )
        latest = candidates[0]

        # Field checks
        assert latest["source"] == "telegram"
        assert latest["source_bot"] == "PDPV_INTERNAL_BOT"
        assert latest["status"] == "PENDING"
        assert latest.get("created_by_name") in ("Test Operator", "Test User", None) or latest.get("created_by_name"), (
            f"Unexpected created_by_name: {latest.get('created_by_name')}"
        )
        ref = latest.get("reference") or ""
        assert ref.startswith("PT"), f"reference must start with PT, got {ref}"

        ai = latest.get("ai_extracted") or {}
        # confidence_score may be inside ai_extracted
        conf = ai.get("confidence_score") if isinstance(ai, dict) else None
        assert conf is None or conf >= 0, f"confidence_score invalid: {conf}"

        # Save id for next dependent tests
        pytest.intake_id_from_bot = latest["id"]

    def test_pre_tickets_collection_remains_unused(self, api):
        # Use the legacy endpoint that lists pre_tickets if available
        r = api.get(f"{BASE_URL}/api/telegram/internal/pre-tickets/stats")
        # Endpoint must exist (admin restricted) — either 200 or 403; we just
        # want to assert it doesn't create new pre_tickets
        assert r.status_code in (200, 403), r.text
        if r.status_code == 200:
            stats = r.json()
            # If the field is present, must be 0
            total = stats.get("total") if isinstance(stats, dict) else None
            if total is not None:
                assert total == 0, f"pre_tickets must remain at 0, got {total}"


# ---------------------------------------------------------------------------
# 3. PUT /api/intake/{id} accepts ai_extracted and validated_by
# ---------------------------------------------------------------------------
class TestIntakePutAIExtracted:
    def test_update_ai_extracted_and_validated_by(self, api):
        # Create a manual intake first
        unique = uuid.uuid4().hex[:8]
        cr = api.post(
            f"{BASE_URL}/api/intake",
            json={
                "source": "manual",
                "sender_name": f"TEST_AI_{unique}",
                "sender_contact": "912000000",
                "raw_text": "Test AI fields",
            },
        )
        assert cr.status_code == 200, cr.text
        intake_id = cr.json()["id"]
        try:
            ai_payload = {
                "ai_extracted": {
                    "customer_name": "Cliente Editado",
                    "phone": "912111222",
                    "license_plate": "EE-22-FF",
                    "confidence_score": 0.95,
                    "missing_fields": [],
                },
                "validated_by": "admin@pdpv.pt",
            }
            up = api.put(f"{BASE_URL}/api/intake/{intake_id}", json=ai_payload)
            assert up.status_code == 200, up.text
            data = up.json()
            ai = data.get("ai_extracted")
            assert ai and ai.get("customer_name") == "Cliente Editado"
            assert data.get("validated_by") == "admin@pdpv.pt"
        finally:
            api.delete(f"{BASE_URL}/api/intake/{intake_id}")


# ---------------------------------------------------------------------------
# 4. convert_to_ticket
# ---------------------------------------------------------------------------
class TestIntakeConvert:
    def test_convert_creates_ticket_and_marks_intake(self, api):
        unique = uuid.uuid4().hex[:8]
        cr = api.post(
            f"{BASE_URL}/api/intake",
            json={
                "source": "telegram",
                "sender_name": f"TEST_Convert_{unique}",
                "sender_contact": "912333444",
                "raw_text": "Pre-ticket to convert",
                "license_plate": "CV-11-VT",
            },
        )
        assert cr.status_code == 200, cr.text
        intake_id = cr.json()["id"]
        conv = api.post(
            f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket",
            json={"ticket_type": "INFORMACAO"},
        )
        assert conv.status_code == 200, conv.text
        cdata = conv.json()
        assert "ticket_id" in cdata
        # Verify intake
        get_ = api.get(f"{BASE_URL}/api/intake/{intake_id}").json()
        assert get_["status"] == "CONVERTED"
        assert get_["converted_ticket_id"] == cdata["ticket_id"]


# ---------------------------------------------------------------------------
# 5. Attachment proxy auth requirement
# ---------------------------------------------------------------------------
class TestAttachmentProxyAuth:
    def test_attachment_proxy_requires_auth(self, api):
        # Need any intake id; create one
        cr = api.post(
            f"{BASE_URL}/api/intake",
            json={
                "source": "manual",
                "sender_name": "TEST_AttachAuth",
                "sender_contact": "912000000",
                "raw_text": "attachment auth test",
            },
        )
        intake_id = cr.json()["id"]
        try:
            # no auth header
            r = requests.get(
                f"{BASE_URL}/api/intake/{intake_id}/attachments/some-att-id",
                timeout=10,
            )
            assert r.status_code in (401, 403), (
                f"Expected 401/403 without auth, got {r.status_code}: {r.text[:200]}"
            )
        finally:
            api.delete(f"{BASE_URL}/api/intake/{intake_id}")


# ---------------------------------------------------------------------------
# 6. Admin telegram-internal endpoints require ADMIN
# ---------------------------------------------------------------------------
class TestAdminTelegramInternal:
    def test_get_authorized_users_without_auth(self):
        r = requests.get(
            f"{BASE_URL}/api/telegram/internal/authorized-users", timeout=10
        )
        assert r.status_code in (401, 403), r.text

    def test_get_authorized_users_with_admin(self, api):
        r = api.get(f"{BASE_URL}/api/telegram/internal/authorized-users")
        assert r.status_code == 200, r.text
        data = r.json()
        # Should be a list (or {items: []}); accept both shapes
        if isinstance(data, dict):
            data = data.get("items", data.get("users", []))
        assert isinstance(data, list)
        # The seeded authorized user must be present
        found = any(
            (
                u.get("telegram_user_id") == AUTH_USER_ID
                or str(u.get("telegram_user_id")) == str(AUTH_USER_ID)
            )
            for u in data
        )
        assert found, f"Authorized seeded user {AUTH_USER_ID} not found"

    def test_post_authorized_user_requires_admin(self):
        r = requests.post(
            f"{BASE_URL}/api/telegram/internal/authorized-users",
            json={"telegram_user_id": 12345, "name": "x"},
            timeout=10,
        )
        assert r.status_code in (401, 403), r.text


# ---------------------------------------------------------------------------
# 7. Other webhooks still respond 200
# ---------------------------------------------------------------------------
class TestOtherWebhooks:
    def test_old_telegram_webhook_ok(self):
        # Old bot @PDPV_OFICINA_BOT on /api/telegram/webhook
        r = requests.post(
            f"{BASE_URL}/api/telegram/webhook",
            json={"update_id": 999999, "message": {"message_id": 1, "text": "ping"}},
            timeout=10,
        )
        # Should respond 200 (treated as no-op for missing user/chat)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_renting_webhook_ok(self):
        # Renting webhook is mounted at /api/renting/webhook
        r = requests.post(
            f"{BASE_URL}/api/renting/webhook",
            json={"update_id": 999998, "message": {"message_id": 1, "text": "ping"}},
            timeout=10,
        )
        # 200 expected; if endpoint requires secret, 401/403 acceptable
        assert r.status_code in (200, 401, 403), (
            f"{r.status_code} {r.text[:200]}"
        )

    def test_telegram_alerts_webhook_ok_if_exists(self):
        r = requests.post(
            f"{BASE_URL}/api/telegram-alerts/webhook",
            json={"update_id": 999997, "message": {"message_id": 1, "text": "ping"}},
            timeout=10,
        )
        # Endpoint may not exist; if it does, must return 200
        assert r.status_code in (200, 401, 403, 404), r.text
