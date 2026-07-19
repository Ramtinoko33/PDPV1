"""Renting flow — Option A (delegação leve).

Delega para `modules.renting.service` (o service standalone), que agora envia
mensagens via TELEGRAM_INTERNAL_BOT_TOKEN (unificado no .env). Fluxo end-to-end
dentro do bot interno sem port do código.
"""
import logging
from typing import Optional

from modules.renting import service as rent_service
from .. import state as state_mgr

logger = logging.getLogger(__name__)

FLOW = "renting"


def _user_info(user_id: int, chat_id: int, user_auth: dict) -> dict:
    return {
        "user_id": user_id,
        "username": None,
        "name": user_auth.get("name") or f"Op {user_id}",
        "chat_id": chat_id,
    }


async def _maybe_finalize(user_id: int, chat_id: int) -> None:
    """Renting stores state in draft records (renting_records with status="draft").
    The draft's chat is stored in `telegram_chat_id`. If no draft exists for
    this chat, the flow finished — clear internal state.
    """
    from db import db as _db
    draft = await _db.renting_records.find_one(
        {"telegram_chat_id": int(chat_id), "status": "draft"}, {"_id": 1}
    )
    if not draft:
        await state_mgr.reset_state(user_id)


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    await state_mgr.start_flow(
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        flow=FLOW,
        initial_step="wait_start",
        initial_payload={"delegated": True},
    )
    await rent_service.start_new_session(chat_id, _user_info(telegram_user_id, chat_id, user_auth))
    await _maybe_finalize(telegram_user_id, chat_id)


async def handle_attachment_raw(chat_id: int, user_id: int, message: dict, state: dict) -> bool:
    from_user = message.get("from") or {}
    user_info = _user_info(user_id, chat_id, {"name": from_user.get("first_name") or ""})

    voice = message.get("voice") or message.get("audio")
    if voice:
        await rent_service.handle_voice(chat_id, user_info, voice)
        await _maybe_finalize(user_id, chat_id)
        return True

    photo = message.get("photo")
    if photo:
        best = max(photo, key=lambda p: p.get("file_size", 0))
        await rent_service.handle_photo(
            chat_id, user_info,
            {"file_id": best["file_id"], "file_size": best.get("file_size", 0)},
        )
        await _maybe_finalize(user_id, chat_id)
        return True

    doc = message.get("document")
    if doc and (doc.get("mime_type") or "").startswith("image/"):
        await rent_service.handle_photo(
            chat_id, user_info,
            {"file_id": doc["file_id"], "file_size": doc.get("file_size", 0)},
        )
        await _maybe_finalize(user_id, chat_id)
        return True

    return False


async def handle_message(chat_id: int, user_id: int, text: Optional[str],
                        photo_file_id: Optional[str], state: dict) -> None:
    user_info = _user_info(user_id, chat_id, {"name": ""})
    if photo_file_id:
        await rent_service.handle_photo(chat_id, user_info, {"file_id": photo_file_id, "file_size": 0})
    elif text:
        await rent_service.handle_text(chat_id, user_info, text)
    await _maybe_finalize(user_id, chat_id)


async def handle_callback(chat_id: int, user_id: int, data: str,
                          user_auth: dict, state: dict) -> None:
    await rent_service.handle_callback(chat_id, data)
    await _maybe_finalize(user_id, chat_id)
