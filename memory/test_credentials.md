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
    `WHATSAPP_VERIFY_TOKEN` (strong random — NEVER reuse the legacy default),
    `WHATSAPP_APP_SECRET`, `WHATSAPP_ENABLED` (true/false hard kill-switch).
- ⚠️ Security guardrails active in code:
  - The webhook GET handler refuses to verify in production (`ENVIRONMENT=production`)
    if `WHATSAPP_VERIFY_TOKEN` is empty or matches a known weak value
    (legacy `pdpv_whatsapp_verify_2024`, "verify", "test", "changeme", ...).
  - Slot in `.env` is now empty by default; must be filled per environment.
- To generate a strong verify token:
  `python /app/backend/scripts/gen_whatsapp_verify_token.py`
- Smoke-test post go-live (credentials read from env vars, never from CLI args
  to keep them out of shell history):
  ```bash
  export TEST_ADMIN_EMAIL=admin@pdpv.pt
  export TEST_ADMIN_PASSWORD=...
  export WHATSAPP_VERIFY_TOKEN=<the strong token configured on Meta>
  python /app/backend/scripts/whatsapp_smoke_test.py \
      --base-url "$REACT_APP_BACKEND_URL" --phone 351XXXXXXXXX
  ```
- ⚠️ The admin password listed at the top of this file is the seed/test password.
  It MUST be rotated before opening the system to real customers.

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
