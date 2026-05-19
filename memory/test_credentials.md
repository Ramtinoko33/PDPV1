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

## PDPV Bot Interno (Telegram)
- Webhook: `POST /api/telegram/internal/webhook` requires header
  `X-Telegram-Bot-Api-Secret-Token: <TELEGRAM_INTERNAL_WEBHOOK_SECRET>`.
- Dev env (preview) uses `TELEGRAM_INTERNAL_WEBHOOK_SECRET=pdpv_internal_webhook_2026`.
  In production this MUST be replaced by a different strong random secret.
- Authorized test users live in collection `telegram_internal_authorized_users`
  (admin endpoints under `/api/telegram/internal/authorized-users`).
