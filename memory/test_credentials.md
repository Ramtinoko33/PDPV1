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
