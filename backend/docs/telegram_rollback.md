# Telegram Bot Rollback Procedure

If the consolidated `@pdpv_interno_bot` needs to be rolled back (bug, downtime,
or emergency), follow the steps below to restore one of the legacy bots as the
primary receiver. The four legacy bots are still registered in Telegram; only
their webhooks were deleted.

**Never commit real tokens to this document or to any file that is tracked by
git.** Load tokens exclusively from environment variables or a secret manager.

## Prerequisites

- Access to BotFather in Telegram (to fetch or rotate tokens).
- SSH / kubectl access to the production backend pod (for `curl` calls to the
  Telegram Bot API).
- Legacy `/webhook/legacy` routes are preserved for each old bot module
  (`modules/telegram/routes.py`, `modules/telegram_alerts/routes.py`,
  `modules/renting/routes.py`, `modules/assistencias/routes.py`).

## Rollback plan (per legacy bot)

For each bot to reactivate:

1. **Fetch the current bot token** from BotFather → `/mybots` → select bot →
   `API Token`. If the token has been rotated, regenerate it via
   `Revoke current token`. Store the value ONLY in the pod's env vars:
   - `TELEGRAM_BOT_TOKEN` (Principal)
   - `TELEGRAM_ALERTS_BOT_TOKEN` (Alertas)
   - `TELEGRAM_RENTING_BOT_TOKEN` (Renting)
   - `TELEGRAM_ASSISTENCIAS_BOT_TOKEN` (Assistências)

2. **Restore the webhook route** — the legacy behaviour is preserved at
   `/api/<module>/webhook/legacy`. Point Telegram to that path (or rename it
   back to `/webhook` in the module `routes.py` while commenting out the
   deprecation stub).

3. **Register the webhook** in Telegram — from inside the pod:
   ```bash
   curl -X POST \
     "https://api.telegram.org/bot$TELEGRAM_<BOT>_BOT_TOKEN/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://tickets.pneusdpedrov.com/api/<module>/webhook/legacy",
          "secret_token": "'"$WEBHOOK_SECRET_ENV_VAR"'",
          "allowed_updates": ["message","callback_query"]}'
   ```

4. **Disable the consolidated bot webhook** so mechanics don't get updates on
   both channels:
   ```bash
   curl -X POST \
     "https://api.telegram.org/bot$TELEGRAM_INTERNAL_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
   ```

## Post-rollback validation

- `GET /api/health` → `HTTP 200`.
- `POST getWebhookInfo` for the legacy bot: `url` is not empty, `pending_update_count == 0`.
- Send `/start` to the legacy bot; verify the expected reply.
- `POST getWebhookInfo` for `@pdpv_interno_bot`: `url` is empty.

## Reverting the rollback (going back to consolidated bot)

1. `deleteWebhook` on the legacy bot's token.
2. `setWebhook` on `@pdpv_interno_bot` pointing to
   `https://tickets.pneusdpedrov.com/api/telegram/internal/webhook` with the
   secret from `TELEGRAM_INTERNAL_WEBHOOK_SECRET`.
3. Confirm `getWebhookInfo` for the internal bot.

## Data considerations

- The rollback does NOT touch MongoDB. Records already created by
  `@pdpv_interno_bot` (pre-tickets, assistances, drafts, alerts) remain
  intact and visible in the dashboard.
- The `telegram_processed_updates` collection has a 7-day TTL and is safe
  to leave populated after rollback.
- `telegram_alerts_states` persists mid-flow conversations. If mechanics were
  mid-conversation when the rollback happens, they may need to restart with
  `/start` on the legacy bot.
