"""Assistências flow — Option A (delegação leve).

Em vez de duplicar ~950 linhas de state machine, delegamos aos handlers do
módulo standalone `modules.assistencias.service`, que agora envia mensagens
via TELEGRAM_INTERNAL_BOT_TOKEN (unificado no .env). Fluxo end-to-end fica
dentro do bot interno sem port do código.
"""
import logging
from typing import Optional

from modules.assistencias import service as assist_service
from .. import state as state_mgr

logger = logging.getLogger(__name__)

FLOW = "assistencias"


def _tg_user(user_id: int, user_auth: dict) -> dict:
    """Build the tg_user dict expected by the standalone service."""
    return {
        "id": user_id,
        "username": None,
        "name": user_auth.get("name") or f"Op {user_id}",
    }


async def _maybe_finalize(user_id: int) -> None:
    """If the standalone service reset its state (session ended/idle), clear
    the internal bot's active_flow so /start goes back to menu cleanly.
    Correct collection: `assistencias_bot_state`.
    """
    from db import db as _db
    st = await _db.assistencias_bot_state.find_one({"chat_id": int(user_id)}, {"state": 1, "_id": 0})
    if not st or st.get("state") in (None, "IDLE"):
        await state_mgr.reset_state(user_id)


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    """Entry point from menu → 🚨 Registar Assistência."""
    await state_mgr.start_flow(
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        flow=FLOW,
        initial_step="wait_location",
        initial_payload={"delegated": True},
    )
    await assist_service.start_new_assistance(chat_id, _tg_user(telegram_user_id, user_auth))
    await _maybe_finalize(telegram_user_id)


async def handle_attachment_raw(chat_id: int, user_id: int, message: dict, state: dict) -> bool:
    """Consume location/voice/photo/document directly from raw message."""
    tg_user = _tg_user(user_id, {"name": ((message.get("from") or {}).get("first_name") or "")})

    location = message.get("location")
    if location:
        await assist_service.handle_location(chat_id, tg_user, location)
        await _maybe_finalize(user_id)
        return True

    voice = message.get("voice") or message.get("audio")
    if voice:
        await assist_service.handle_voice(chat_id, tg_user, voice)
        await _maybe_finalize(user_id)
        return True

    photo = message.get("photo")
    if photo:
        best = max(photo, key=lambda p: p.get("file_size", 0))
        await assist_service.handle_photo(chat_id, tg_user, {"file_id": best["file_id"]})
        await _maybe_finalize(user_id)
        return True

    doc = message.get("document")
    if doc and (doc.get("mime_type") or "").startswith("image/"):
        await assist_service.handle_photo(chat_id, tg_user, {"file_id": doc["file_id"]})
        await _maybe_finalize(user_id)
        return True

    return False  # not consumed → falls through to handle_message


async def handle_message(chat_id: int, user_id: int, text: Optional[str],
                        photo_file_id: Optional[str], state: dict) -> None:
    """Text-only fallback (attachments already handled above)."""
    if text is None and photo_file_id is None:
        return
    tg_user = _tg_user(user_id, {"name": ""})
    if photo_file_id:
        # Should not happen usually because handle_attachment_raw catches photos,
        # but keep as safety net.
        await assist_service.handle_photo(chat_id, tg_user, {"file_id": photo_file_id})
    elif text:
        await assist_service.handle_text(chat_id, tg_user, text)
    await _maybe_finalize(user_id)


async def handle_callback(chat_id: int, user_id: int, data: str,
                          user_auth: dict, state: dict) -> None:
    """Inline keyboard callbacks (plate_ok / plate_edit / addl_yes / etc.)."""
    await assist_service.handle_callback(chat_id, data, cb_id=None)
    await _maybe_finalize(user_id)
