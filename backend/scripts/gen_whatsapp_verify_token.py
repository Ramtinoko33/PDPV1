#!/usr/bin/env python3
"""Generate a strong random WhatsApp verify token for Meta webhook setup.

Usage:
    python /app/backend/scripts/gen_whatsapp_verify_token.py

Copy the printed value to:
  1) The Emergent env panel as `WHATSAPP_VERIFY_TOKEN`
  2) The Meta App > WhatsApp > Configuration > Webhook > Verify Token field
Both must match exactly for Meta to accept the webhook subscription.
"""
import secrets

if __name__ == "__main__":
    token = secrets.token_urlsafe(48)  # ~64 chars, URL-safe
    print(token)
