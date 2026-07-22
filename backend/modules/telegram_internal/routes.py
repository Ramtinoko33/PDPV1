"""PDPV Bot Interno — FastAPI routes.

Webhook: POST /api/telegram/internal/webhook  (public, validated via secret token)
Admin:   /api/telegram/internal/authorized-users (CRUD; requires JWT auth)

CAREFUL: this module is fully isolated from the 3 existing Telegram bots.
"""
import os
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from core.security import get_current_user
from db import db
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
    in_production = (os.environ.get("ENVIRONMENT", "development").strip().lower()
                     in ("prod", "production"))
    if not expected_secret:
        if in_production:
            logger.error(
                "Internal bot webhook in production but TELEGRAM_INTERNAL_WEBHOOK_SECRET unset; rejecting"
            )
            raise HTTPException(status_code=503, detail="Bot not configured")
        logger.warning(
            "Internal bot webhook: TELEGRAM_INTERNAL_WEBHOOK_SECRET unset — accepting "
            "request without secret validation (dev mode)"
        )
    elif x_telegram_bot_api_secret_token != expected_secret:
        logger.warning("Internal bot webhook rejected: bad/missing secret token")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        update = await request.json()
    except Exception:
        return {"status": "ok"}  # never let Telegram retry on parse errors

    # ── Atomic update_id deduplication (spec P0) ─────────────────────────
    # Insert-first pattern with UNIQUE index → race-safe. If we see the same
    # update_id twice (Telegram retries or dual delivery), the second insert
    # raises DuplicateKeyError and we skip processing entirely.
    from pymongo.errors import DuplicateKeyError
    from db import db as _db
    update_id = update.get("update_id")
    if update_id is not None:
        try:
            await _db.telegram_processed_updates.insert_one({
                "update_id": int(update_id),
                "bot": "pdpv_interno_bot",
                "status": "processing",
                "received_at": datetime.now(timezone.utc),
            })
        except DuplicateKeyError:
            logger.info("internal bot: duplicate update_id=%s ignored", update_id)
            return {"status": "duplicate"}

    try:
        await _dispatch_update(update)
        if update_id is not None:
            await _db.telegram_processed_updates.update_one(
                {"update_id": int(update_id)},
                {"$set": {"status": "done", "processed_at": datetime.now(timezone.utc)}},
            )
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
    user_id: str = Field(..., min_length=1, description="UUID of the linked system user (users.id). REQUIRED for new/updated entries.")
    name: str = Field(..., min_length=1)
    role: str = Field("AGENT")
    allowed_flows: List[str] = Field(default_factory=lambda: ["pre_ticket", "renting", "assistencias", "mech_alert"])
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
    # Validate that user_id points to an existing user (defensive).
    sys_user = await db.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1})
    if not sys_user:
        raise HTTPException(status_code=422, detail=f"user_id {body.user_id!r} não existe em users")
    return await auth_mgr.upsert_authorized_user(
        telegram_user_id=body.telegram_user_id,
        user_id=body.user_id,
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


@router.get("/pending-users")
async def list_pending_users(current_user: dict = Depends(get_current_user)):
    """List Telegram users who recently tried to use the internal bot but were
    NOT authorized. Useful to grant access without checking logs manually.
    """
    _require_admin(current_user)
    from db import db as _db
    pipeline = [
        {"$match": {"message_type": "unauthorized"}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$telegram_user_id",
            "first_name": {"$first": "$error"},
            "last_attempt_at": {"$first": "$created_at"},
            "attempts": {"$sum": 1},
        }},
        {"$sort": {"last_attempt_at": -1}},
        {"$limit": 50},
    ]
    rows = await _db.telegram_internal_logs.aggregate(pipeline).to_list(50)
    return [
        {
            "telegram_user_id": r["_id"],
            "first_name": r.get("first_name") or "",
            "attempts": r["attempts"],
            "last_attempt_at": r.get("last_attempt_at"),
        }
        for r in rows
    ]


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


# ============== PRE-TICKETS DASHBOARD ENDPOINTS ==============

@router.get("/pre-tickets/stats")
async def pre_tickets_stats(current_user: dict = Depends(get_current_user)):
    """Counts by status for the dashboard pre-tickets section."""
    from db import db as _db
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    rows = await _db.pre_tickets.aggregate(pipeline).to_list(20)
    stats = {"NOVO": 0, "EM_VALIDACAO": 0, "CONVERTIDO": 0, "DESCARTADO": 0, "total": 0}
    for r in rows:
        s = r.get("_id") or "NOVO"
        if s in stats:
            stats[s] = r["n"]
        stats["total"] += r["n"]
    return stats


@router.get("/pre-tickets")
async def list_pre_tickets(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    current_user: dict = Depends(get_current_user),
):
    from db import db as _db
    q = {}
    if status:
        q["status"] = status
    cursor = _db.pre_tickets.find(q, {"_id": 0}).sort("created_at", -1)
    total = await _db.pre_tickets.count_documents(q)
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    items = await cursor.skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/pre-tickets/{pre_ticket_id}")
async def get_pre_ticket(pre_ticket_id: str, current_user: dict = Depends(get_current_user)):
    from db import db as _db
    doc = await _db.pre_tickets.find_one({"id": pre_ticket_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Pré-ticket não encontrado")
    return doc


class PreTicketUpdate(BaseModel):
    ai_extracted: Optional[dict] = None
    status: Optional[str] = None
    validated_by: Optional[str] = None
    notes: Optional[str] = None


@router.put("/pre-tickets/{pre_ticket_id}")
async def update_pre_ticket(
    pre_ticket_id: str,
    body: PreTicketUpdate,
    current_user: dict = Depends(get_current_user),
):
    from db import db as _db
    from datetime import datetime, timezone
    updates = body.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Sem alterações")
    valid_status = {"NOVO", "EM_VALIDACAO", "CONVERTIDO", "DESCARTADO"}
    if "status" in updates and updates["status"] not in valid_status:
        raise HTTPException(status_code=400, detail="Estado inválido")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await _db.pre_tickets.update_one({"id": pre_ticket_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pré-ticket não encontrado")
    return await _db.pre_tickets.find_one({"id": pre_ticket_id}, {"_id": 0})


@router.get("/pre-tickets/{pre_ticket_id}/attachments/{attachment_id}")
async def proxy_pre_ticket_attachment(
    pre_ticket_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Stream-proxy an attachment from Telegram CDN through the backend.

    The dashboard calls this endpoint with JWT; it never exposes the bot token.
    """
    from db import db as _db
    from fastapi.responses import Response
    from .bot_api import download_file as _dl
    doc = await _db.pre_tickets.find_one({"id": pre_ticket_id}, {"_id": 0, "attachments": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Pré-ticket não encontrado")
    att = next((a for a in (doc.get("attachments") or []) if a.get("id") == attachment_id), None)
    if not att:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    file_id = att.get("telegram_file_id")
    if not file_id:
        raise HTTPException(status_code=404, detail="Anexo sem file_id")
    data = await _dl(file_id)
    if not data:
        raise HTTPException(status_code=502, detail="Falha a obter ficheiro do Telegram")
    media_type = att.get("mime_type") or {
        "photo": "image/jpeg",
        "voice": "audio/ogg",
        "audio": "audio/mpeg",
        "document": "application/octet-stream",
    }.get(att.get("kind"), "application/octet-stream")
    headers = {}
    if att.get("file_name"):
        headers["Content-Disposition"] = f'inline; filename="{att["file_name"]}"'
    return Response(content=data, media_type=media_type, headers=headers)


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
        # Extract first name so we can identify the user later
        user_obj = (
            (update.get("message") or {}).get("from")
            or (update.get("callback_query") or {}).get("from")
            or {}
        )
        first_name = user_obj.get("first_name") or user_obj.get("username") or ""
        logger.warning(
            "Internal bot: UNAUTHORIZED user tried to access — telegram_user_id=%s first_name=%r",
            user_id, first_name,
        )
        await menu_mgr.send_unauthorized(chat_id, user_id=user_id, user_name=first_name)
        await log_event(user_id, chat_id, "unauthorized", success=False, error=first_name)
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
        if cmd == "/help":
            allowed = user_auth.get("allowed_flows") or list(FLOW_REGISTRY.keys())
            flow_labels = {"pre_ticket": "📋 Pré-tickets", "renting": "🚗 Renting",
                           "assistencias": "🚨 Assistências", "mech_alert": "🔧 Alertas Mecânica"}
            lines = ["<b>ℹ️ Ajuda — Bot Interno PDPV</b>", "", "<b>Módulos autorizados:</b>"]
            lines += [f"• {flow_labels.get(f, f)}" for f in allowed]
            lines += ["", "<b>Comandos:</b>",
                      "/start ou /menu — abrir menu principal",
                      "/cancel — cancelar operação em curso",
                      "/help — esta ajuda"]
            await send_message(chat_id, "\n".join(lines))
            await log_event(user_id, chat_id, "command", current_step=cmd, success=True)
            return

    # Detect expired flow: a state existed but was just auto-cleared by get_state()
    raw_state = await state_mgr.db_state_raw(user_id) if hasattr(state_mgr, "db_state_raw") else None
    state = await state_mgr.get_state(user_id)
    expired = raw_state and not state  # had state, now None → was expired

    if expired:
        await send_message(chat_id, "⏰ Este processo expirou. Vamos começar novamente.")
        await menu_mgr.send_main_menu(chat_id, user_auth)
        await log_event(user_id, chat_id, "timeout", success=True)
        return

    # Forward to active flow if any
    if state and state.get("active_flow"):
        flow_key = state["active_flow"]
        flow_mod = FLOW_REGISTRY.get(flow_key)
        if not flow_mod:
            return

        # Try the attachment-raw handler first (voice/audio/document) when the flow
        # supports it (currently pre_ticket only).
        consumed = False
        if hasattr(flow_mod, "handle_attachment_raw"):
            try:
                consumed = await flow_mod.handle_attachment_raw(chat_id, user_id, message, state)
            except Exception as e:
                logger.warning("attachment_raw handler failed: %s", e)
                consumed = False
        if consumed:
            return
        # Per-module isolation: an exception in one flow must not affect others
        try:
            await flow_mod.handle_message(chat_id, user_id, text, photo_file_id, state)
            await log_event(user_id, chat_id, "message",
                            active_flow=state.get("active_flow"),
                            current_step=state.get("current_step"), success=True)
        except Exception as exc:
            import uuid as _uuid
            error_id = _uuid.uuid4().hex[:12]
            logger.error("[error_id=%s] flow=%s handler crashed: %s", error_id, flow_key, exc, exc_info=True)
            await log_event(user_id, chat_id, "message_error",
                            active_flow=flow_key,
                            current_step=state.get("current_step"),
                            success=False,
                            error=f"{error_id}: {type(exc).__name__}")
            await send_message(chat_id,
                f"⚠️ Ocorreu um erro. Referência: <code>{error_id}</code>\n"
                "Envia /menu para recomeçar ou avisa o administrador.")
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

    # ── System-namespace navigation (spec §5) ──────────────────────────
    if data.startswith("system:"):
        action = data.split(":", 1)[1]
        if action == "menu":
            await state_mgr.reset_state(user_id)
            await menu_mgr.send_main_menu(chat_id, user_auth)
        elif action == "cancel":
            await menu_mgr.cancel_flow(chat_id, user_id, user_auth)
        elif action == "back":
            # Safe fallback: go to menu (per spec, when no safe prior step exists)
            await menu_mgr.send_main_menu(chat_id, user_auth)
        elif action == "help":
            allowed = user_auth.get("allowed_flows") or list(FLOW_REGISTRY.keys())
            flow_labels = {"pre_ticket": "📋 Pré-tickets", "renting": "🚗 Renting",
                           "assistencias": "🚨 Assistências", "mech_alert": "🔧 Alertas Mecânica"}
            lines = ["<b>ℹ️ Ajuda</b>", "", "<b>Módulos:</b>"] + \
                    [f"• {flow_labels.get(f, f)}" for f in allowed] + \
                    ["", "<b>Comandos:</b> /menu · /cancel · /help"]
            await send_message(chat_id, "\n".join(lines))
        return

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
            "assistencias": "assistencias",
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

    # Forward to active flow's callback handler (with per-module isolation)
    state = await state_mgr.get_state(user_id)
    if state and state.get("active_flow"):
        flow_key = state["active_flow"]
        flow_mod = FLOW_REGISTRY.get(flow_key)
        if flow_mod:
            try:
                await flow_mod.handle_callback(chat_id, user_id, data, user_auth, state)
                await log_event(user_id, chat_id, "callback",
                                active_flow=flow_key,
                                current_step=state.get("current_step"), success=True)
            except Exception as exc:
                import uuid as _uuid
                error_id = _uuid.uuid4().hex[:12]
                logger.error("[error_id=%s] flow=%s callback crashed data=%r: %s",
                             error_id, flow_key, data, exc, exc_info=True)
                await log_event(user_id, chat_id, "callback_error",
                                active_flow=flow_key,
                                current_step=state.get("current_step"),
                                success=False,
                                error=f"{error_id}: {type(exc).__name__}")
                await send_message(chat_id,
                    f"⚠️ Esta ação não foi processada. Referência: <code>{error_id}</code>\n"
                    "Volta ao menu com /menu.")
