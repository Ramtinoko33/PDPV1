"""PDPV Bot Interno — FastAPI routes.

Webhook: POST /api/telegram/internal/webhook  (public, validated via secret token)
Admin:   /api/telegram/internal/authorized-users (CRUD; requires JWT auth)

CAREFUL: this module is fully isolated from the 3 existing Telegram bots.
"""
import os
import logging
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from core.security import get_current_user
from . import state as state_mgr
from . import auth as auth_mgr
from . import menu as menu_mgr
from .bot_api import send_message, answer_callback_query, set_webhook, get_me, is_configured
from .flows import REGISTRY as FLOW_REGISTRY
from .logs import log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram/internal", tags=["telegram-internal"])


# ============== WEBHOOK ==============

@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """Receive updates from Telegram for the internal bot.

    Security: validates the `X-Telegram-Bot-Api-Secret-Token` header against
    `TELEGRAM_INTERNAL_WEBHOOK_SECRET` when set. If the env var is unset, we
    skip the check (development convenience) but log a warning.
    """
    expected_secret = os.environ.get("TELEGRAM_INTERNAL_WEBHOOK_SECRET", "")
    if expected_secret:
        if x_telegram_bot_api_secret_token != expected_secret:
            logger.warning("Internal bot webhook rejected: bad/missing secret token")
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    else:
        logger.warning(
            "Internal bot webhook: TELEGRAM_INTERNAL_WEBHOOK_SECRET unset — accepting "
            "request without secret validation (dev mode)"
        )

    try:
        update = await request.json()
    except Exception:
        return {"status": "ok"}  # never let Telegram retry on parse errors

    try:
        await _dispatch_update(update)
    except Exception as e:
        logger.error("internal bot update handler crashed: %s", e, exc_info=True)
        try:
            await log_event(
                telegram_user_id=_extract_user_id(update),
                chat_id=_extract_chat_id(update),
                message_type="exception",
                success=False,
                error=str(e),
            )
        except Exception:
            pass
    return {"status": "ok"}


# ============== ADMIN ENDPOINTS ==============

class AuthorizedUserIn(BaseModel):
    telegram_user_id: int = Field(..., description="Numeric Telegram user id")
    name: str = Field(..., min_length=1)
    role: str = Field("AGENT")
    allowed_flows: List[str] = Field(default_factory=lambda: ["pre_ticket", "renting", "mech_alert"])
    active: bool = True


def _require_admin(current_user: dict):
    if current_user.get("role") not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Apenas administradores")


@router.get("/authorized-users")
async def list_authorized_users(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return await auth_mgr.list_authorized()


@router.post("/authorized-users")
async def upsert_authorized_user(body: AuthorizedUserIn, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return await auth_mgr.upsert_authorized_user(
        telegram_user_id=body.telegram_user_id,
        name=body.name,
        role=body.role,
        allowed_flows=body.allowed_flows,
        active=body.active,
    )


@router.delete("/authorized-users/{telegram_user_id}")
async def remove_authorized_user(telegram_user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    ok = await auth_mgr.deactivate_user(telegram_user_id)
    return {"deactivated": ok}


# ============== BOT INFO (admin-only smoke test) ==============

@router.get("/info")
async def bot_info(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    if not is_configured():
        return {"configured": False, "reason": "TELEGRAM_INTERNAL_BOT_TOKEN missing"}
    info = await get_me() or {}
    return {"configured": True, "telegram_getMe": info.get("result") or info}


class SetWebhookIn(BaseModel):
    url: str


@router.post("/webhook/configure")
async def configure_webhook(body: SetWebhookIn, current_user: dict = Depends(get_current_user)):
    """Register/refresh the webhook URL with Telegram. Admin-only.

    Pass the full public URL e.g. https://tickets.pneusdpedrov.com/api/telegram/internal/webhook
    """
    _require_admin(current_user)
    if not is_configured():
        raise HTTPException(status_code=503, detail="Bot not configured")
    secret = os.environ.get("TELEGRAM_INTERNAL_WEBHOOK_SECRET") or None
    res = await set_webhook(body.url, secret_token=secret)
    if not res:
        raise HTTPException(status_code=502, detail="Telegram setWebhook failed")
    return res


# ============== DISPATCH ==============

def _extract_user_id(update: dict) -> Optional[int]:
    if "message" in update:
        return (update["message"].get("from") or {}).get("id")
    if "callback_query" in update:
        return (update["callback_query"].get("from") or {}).get("id")
    return None


def _extract_chat_id(update: dict) -> Optional[int]:
    if "message" in update:
        return ((update["message"].get("chat") or {})).get("id")
    if "callback_query" in update:
        msg = update["callback_query"].get("message") or {}
        return (msg.get("chat") or {}).get("id")
    return None


async def _dispatch_update(update: dict) -> None:
    user_id = _extract_user_id(update)
    chat_id = _extract_chat_id(update)
    if not user_id or not chat_id:
        return

    user_auth = await auth_mgr.get_authorized(user_id)
    if not user_auth:
        await menu_mgr.send_unauthorized(chat_id)
        await log_event(user_id, chat_id, "unauthorized", success=False)
        return

    if "message" in update:
        await _handle_message(update["message"], user_auth)
    elif "callback_query" in update:
        await _handle_callback(update["callback_query"], user_auth)


async def _handle_message(message: dict, user_auth: dict) -> None:
    chat_id = (message.get("chat") or {}).get("id")
    user_id = (message.get("from") or {}).get("id")
    text = message.get("text")
    photo_file_id = None
    if message.get("photo"):
        # Largest size
        photo_file_id = message["photo"][-1].get("file_id")

    # Commands always work
    if text and text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd in ("/start", "/menu"):
            await menu_mgr.send_main_menu(chat_id, user_auth)
            await log_event(user_id, chat_id, "command", current_step=cmd, success=True)
            return
        if cmd == "/cancel":
            await menu_mgr.cancel_flow(chat_id, user_id, user_auth)
            await log_event(user_id, chat_id, "command", current_step=cmd, success=True)
            return

    # Forward to active flow if any
    state = await state_mgr.get_state(user_id)
    if state and state.get("active_flow"):
        flow_mod = FLOW_REGISTRY.get(state["active_flow"])
        if flow_mod:
            await flow_mod.handle_message(chat_id, user_id, text, photo_file_id, state)
            await log_event(user_id, chat_id, "message",
                            active_flow=state.get("active_flow"),
                            current_step=state.get("current_step"), success=True)
            return

    # No active flow: just show menu
    await menu_mgr.send_main_menu(chat_id, user_auth)


async def _handle_callback(cb: dict, user_auth: dict) -> None:
    chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
    user_id = (cb.get("from") or {}).get("id")
    data = cb.get("data") or ""
    callback_query_id = cb.get("id")

    # Always answer the callback so the spinner clears
    if callback_query_id:
        await answer_callback_query(callback_query_id)

    # Main menu entries
    if data.startswith("menu:"):
        choice = data.split(":", 1)[1]
        if choice == "cancel":
            await menu_mgr.cancel_flow(chat_id, user_id, user_auth)
            return
        if choice == "back":
            await menu_mgr.send_main_menu(chat_id, user_auth)
            return
        # Mapping menu callback -> flow key
        flow_key = {
            "mech_alert": "mech_alert",
            "renting": "renting",
            "pre_ticket": "pre_ticket",
        }.get(choice)
        if not flow_key:
            return
        # Permission check
        if not await auth_mgr.is_flow_allowed(user_auth, flow_key):
            await send_message(chat_id, "⛔ Não tens permissão para este fluxo.")
            return
        # Conflict check
        active = await state_mgr.get_state(user_id)
        if active and active.get("active_flow") and active.get("active_flow") != flow_key:
            # Store the requested next flow so the conflict resolver can use it
            await state_mgr.update_state(user_id, payload_merge={"_pending_flow": flow_key})
            await menu_mgr.send_active_flow_conflict(
                chat_id, active.get("active_flow"), active.get("current_step") or "—"
            )
            return
        # Start fresh
        await state_mgr.reset_state(user_id)
        flow_mod = FLOW_REGISTRY[flow_key]
        await flow_mod.start(chat_id, user_id, user_auth)
        return

    # Conflict resolver
    if data == "conflict:continue":
        active = await state_mgr.get_state(user_id)
        if active:
            await send_message(
                chat_id,
                f"▶️ Continua o teu fluxo (etapa <code>{active.get('current_step')}</code>).",
            )
        else:
            await menu_mgr.send_main_menu(chat_id, user_auth)
        return

    if data == "conflict:cancel_new":
        active = await state_mgr.get_state(user_id)
        pending = (active or {}).get("temporary_payload", {}).get("_pending_flow")
        await state_mgr.reset_state(user_id)
        if pending and pending in FLOW_REGISTRY:
            flow_mod = FLOW_REGISTRY[pending]
            await flow_mod.start(chat_id, user_id, user_auth)
        else:
            await menu_mgr.send_main_menu(chat_id, user_auth)
        return

    # Forward to active flow's callback handler
    state = await state_mgr.get_state(user_id)
    if state and state.get("active_flow"):
        flow_mod = FLOW_REGISTRY.get(state["active_flow"])
        if flow_mod:
            await flow_mod.handle_callback(chat_id, user_id, data, user_auth, state)
