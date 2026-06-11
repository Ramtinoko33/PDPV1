#!/usr/bin/env python3
"""WhatsApp Phase 1.5 — post-deploy smoke test.

Run AFTER configuring Meta credentials and `WHATSAPP_ENABLED=true` to verify
that the webhook is reachable, signature-validated, and creates pré-tickets.

Credentials are read either from CLI flags OR from environment variables so
that you never need to paste real passwords in shell history:

    export TEST_ADMIN_EMAIL=admin@pdpv.pt
    export TEST_ADMIN_PASSWORD=...    # never commit this
    export WHATSAPP_VERIFY_TOKEN=...   # the strong token configured on Meta
    python whatsapp_smoke_test.py --base-url "$REACT_APP_BACKEND_URL" --phone 351XXXXXXXXX

Usage (production after go-live):
    python whatsapp_smoke_test.py \\
        --base-url https://tickets.pneusdpedrov.com \\
        --phone 3519XXXXXXXX \\
        --check-signature  # only if WHATSAPP_APP_SECRET is exposed locally

The script does NOT call the real Meta Graph API; it only validates the
webhook path with synthetic payloads. Outbound real send must be tested
manually from the UI (TicketDetail > tab WhatsApp).

Exit code: 0 = all green, 1 = any check failed.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from typing import Optional

import httpx

CHECKS = []


def _record(name: str, ok: bool, detail: str = ""):
    CHECKS.append((name, ok, detail))
    mark = "OK  " if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  — {detail}" if detail else ""))


def login(base_url: str, email: str, password: str) -> Optional[str]:
    r = httpx.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    if r.status_code != 200:
        _record("admin login", False, f"status={r.status_code} body={r.text[:120]}")
        return None
    token = r.json().get("token") or r.json().get("access_token")
    _record("admin login", bool(token))
    return token


def check_verify(base_url: str, verify_token: str):
    challenge = f"smoke-{uuid.uuid4().hex[:8]}"
    r = httpx.get(
        f"{base_url}/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": verify_token,
            "hub.challenge": challenge,
        },
        timeout=15,
    )
    ok = r.status_code == 200 and r.text.strip() == challenge
    _record(
        "GET /webhook (verify)",
        ok,
        f"status={r.status_code} echo={'match' if r.text.strip() == challenge else 'mismatch'}",
    )


def build_inbound_payload(phone: str, wamid: str, body: str = "Bom dia") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WA_BIZ_ID_SMOKE",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "351900000000",
                        "phone_number_id": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "PHONE_ID"),
                    },
                    "contacts": [{
                        "profile": {"name": "Smoke Test"},
                        "wa_id": phone,
                    }],
                    "messages": [{
                        "from": phone,
                        "id": wamid,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
                "field": "messages",
            }],
        }],
    }


def post_webhook(base_url: str, payload: dict, app_secret: Optional[str]) -> httpx.Response:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if app_secret:
        sig = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={sig}"
    return httpx.post(
        f"{base_url}/api/whatsapp/webhook",
        content=body,
        headers=headers,
        timeout=20,
    )


def list_intakes(base_url: str, token: str, phone: str) -> list:
    r = httpx.get(
        f"{base_url}/api/intake",
        params={"page": 1, "page_size": 50},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if r.status_code != 200:
        print(f"  (debug) /api/intake -> {r.status_code} {r.text[:200]}")
        return []
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    return [i for i in items if i.get("sender_phone") == phone or i.get("sender_contact") == phone]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-email",
                        default=os.environ.get("TEST_ADMIN_EMAIL"),
                        help="Admin email — or set TEST_ADMIN_EMAIL env var")
    parser.add_argument("--admin-password",
                        default=os.environ.get("TEST_ADMIN_PASSWORD"),
                        help="Admin password — or set TEST_ADMIN_PASSWORD env var")
    parser.add_argument("--phone", required=True,
                        help="Test customer phone (E.164 no '+', e.g. 351912345678)")
    parser.add_argument("--verify-token",
                        default=os.environ.get("WHATSAPP_VERIFY_TOKEN", ""))
    parser.add_argument("--app-secret",
                        default=os.environ.get("WHATSAPP_APP_SECRET"))
    parser.add_argument("--check-signature", action="store_true",
                        help="Send X-Hub-Signature-256 — requires --app-secret")
    args = parser.parse_args()

    if not args.admin_email or not args.admin_password:
        print("ERROR: missing admin credentials. Pass --admin-email/--admin-password "
              "or set TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD env vars.", file=sys.stderr)
        sys.exit(2)
    if not args.verify_token:
        print("ERROR: missing --verify-token (and WHATSAPP_VERIFY_TOKEN env var). "
              "Generate one with: python -c \"import secrets;print(secrets.token_urlsafe(32))\"",
              file=sys.stderr)
        sys.exit(2)

    base_url = args.base_url.rstrip("/")
    print(f"== WhatsApp smoke test against {base_url} ==\n")

    # 1) Login admin
    token = login(base_url, args.admin_email, args.admin_password)
    if not token:
        sys.exit(1)

    # 2) Webhook GET verify
    check_verify(base_url, args.verify_token)

    # 3) Webhook POST inbound — should accept (200) and create pré-ticket
    wamid_1 = f"wamid.SMOKE.{uuid.uuid4().hex[:10]}"
    app_secret = args.app_secret if args.check_signature else None
    payload_1 = build_inbound_payload(args.phone, wamid_1, "Bom dia — smoke test 1")
    r1 = post_webhook(base_url, payload_1, app_secret)
    _record(
        "POST /webhook inbound #1",
        r1.status_code == 200,
        f"status={r1.status_code}",
    )

    # Give the background task time to insert
    time.sleep(2)

    # 4) Pré-ticket created
    intakes = list_intakes(base_url, token, args.phone)
    created = next(
        (i for i in intakes if (i.get("source_bot") == "whatsapp_meta" or i.get("channel") == "WHATSAPP")),
        None,
    )
    _record(
        "intake_request created (source_bot=whatsapp_meta)",
        bool(created),
        f"id={created.get('id') if created else 'none'}",
    )

    # 5) Second message → no new intake
    wamid_2 = f"wamid.SMOKE.{uuid.uuid4().hex[:10]}"
    payload_2 = build_inbound_payload(args.phone, wamid_2, "Smoke test 2 — same number")
    r2 = post_webhook(base_url, payload_2, app_secret)
    time.sleep(2)
    intakes_after = list_intakes(base_url, token, args.phone)
    _record(
        "2nd inbound attaches to existing intake (no duplicate)",
        len(intakes_after) == len(intakes),
        f"before={len(intakes)} after={len(intakes_after)}",
    )

    # 6) Dedupe: re-send wamid_1 → still no extra ticket_message
    payload_dupe = build_inbound_payload(args.phone, wamid_1, "duplicate")
    r3 = post_webhook(base_url, payload_dupe, app_secret)
    _record(
        "duplicate wamid accepted (200) without crashing",
        r3.status_code == 200,
        f"status={r3.status_code}",
    )

    # 7) Signature enforcement in production
    if args.check_signature and args.app_secret:
        # Send with WRONG signature → should be 403 in production, 200/warn in dev
        body = json.dumps(payload_1).encode("utf-8")
        bad_sig = "sha256=" + "0" * 64
        r4 = httpx.post(
            f"{base_url}/api/whatsapp/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": bad_sig},
            timeout=10,
        )
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if env in ("production", "prod"):
            _record(
                "invalid signature rejected (prod)",
                r4.status_code == 403,
                f"status={r4.status_code}",
            )
        else:
            _record(
                "invalid signature warning (dev)",
                r4.status_code in (200, 403),
                f"status={r4.status_code} env={env}",
            )

    # Summary
    print()
    fails = [c for c in CHECKS if not c[1]]
    print(f"== {len(CHECKS) - len(fails)}/{len(CHECKS)} checks passed ==")
    if fails:
        for n, _, d in fails:
            print(f"  FAIL: {n} — {d}")
        sys.exit(1)
    print("All checks green.")
    sys.exit(0)


if __name__ == "__main__":
    main()
