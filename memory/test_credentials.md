# Test Credentials

## Admin Account
- Email: admin@pdpv.pt
- Password: HCNMEnKMLq
- Role: ADMIN

## Test environment variables (optional, for CI / shell-based tests)
- `TEST_ADMIN_PASSWORD` — defaults to "changeme" inside test files when unset
- `TEST_SUPERVISOR_PASSWORD` — same convention
- `TEST_AGENT_PASSWORD` — same convention

## WhatsApp hardening test (`tests/test_whatsapp_hardening.py`)
- Uses in-process FastAPI TestClient — no admin login required.
- Uses test-only `WHATSAPP_APP_SECRET = "test-app-secret-hardening-12345"` via `monkeypatch.setenv`.

## WhatsApp Phase 1.5 (preview/staging)
- Backend env vars expected (slots em `/app/backend/.env`):
  - `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`,
    `WHATSAPP_VERIFY_TOKEN` (default `pdpv_whatsapp_verify_2024`), `WHATSAPP_APP_SECRET`,
    `WHATSAPP_ENABLED` (true/false hard kill-switch).
- Preview currently: `WHATSAPP_ENABLED="true"` with empty Meta creds → webhook works,
  outbound send returns 503 `WhatsApp not configured` (expected).
- Smoke-test post go-live: `python /app/backend/scripts/whatsapp_smoke_test.py --base-url <URL> --admin-email admin@pdpv.pt --admin-password HCNMEnKMLq --phone <test_phone>`

## PDPV Bot Interno (Telegram)
- Webhook: `POST /api/telegram/internal/webhook` requires header
  `X-Telegram-Bot-Api-Secret-Token: <TELEGRAM_INTERNAL_WEBHOOK_SECRET>`.
- Dev env (preview) uses `TELEGRAM_INTERNAL_WEBHOOK_SECRET=pdpv_internal_webhook_2026`.
  In production this MUST be replaced by a different strong random secret.
- Authorized test users live in collection `telegram_internal_authorized_users`
  (admin endpoints under `/api/telegram/internal/authorized-users`).

### Seeded test operator for the internal bot
- `telegram_user_id=999000111`, `name="Test Operator"`, `role=AGENT`,
  `allowed_flows=[pre_ticket, renting, mech_alert]`, `active=true`.
- Used by `/app/backend/tests/test_intake_internal_bot.py` and webhook e2e shell tests.

### Where pré-tickets land
- Internal bot finalize → inserts into **`intake_requests`** (NOT `pre_tickets`)
  with `source_bot=PDPV_INTERNAL_BOT`. Visible in `/intake` UI.
