"""PDPV Bot Interno — new unified bot for internal team (5-10 users).

This module is FULLY ISOLATED from the existing 3 bots:
- @pdpv_alerts_bot  (modules/telegram_alerts)
- @pdpv_rentingpneus_bot  (modules/renting)
- legacy ticket bot (modules/telegram)

It uses its own:
- Env vars: TELEGRAM_INTERNAL_BOT_TOKEN, TELEGRAM_INTERNAL_WEBHOOK_SECRET, TELEGRAM_INTERNAL_ALLOWED_USER_IDS
- Webhook: POST /api/telegram/internal/webhook
- Collections: telegram_internal_states, telegram_internal_authorized_users, telegram_internal_logs
- State machine: Mongo-backed per-user, 30-min TTL
"""
from .routes import router

__all__ = ["router"]
