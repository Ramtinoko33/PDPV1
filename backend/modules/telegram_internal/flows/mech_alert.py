"""Mech Alert flow — Option A (delegação leve).

Delega para `modules.telegram_alerts.service` que envia via
TELEGRAM_INTERNAL_BOT_TOKEN (unificado). Todos os callbacks
(assign:, photos_done:, photos_yes/no:, note_*, comment_*, add_photo:,
new_alert:) são forwardados aos handlers originais.
"""
import logging
from typing import Optional

from modules.telegram_alerts import service as alerts_service
from .. import state as state_mgr

logger = logging.getLogger(__name__)

FLOW = "mech_alert"


def _user_info(user_id: int, user_auth: dict, message: dict = None) -> dict:
    """Build user_info dict expected by telegram_alerts service."""
    if message:
        from_user = message.get("from") or {}
        return {
            "user_id": from_user.get("id") or user_id,
            "username": from_user.get("username"),
            "first_name": from_user.get("first_name", "") or user_auth.get("name", ""),
            "last_name": from_user.get("last_name", ""),
        }
    return {
        "user_id": user_id,
        "username": None,
        "first_name": user_auth.get("name") or f"Op {user_id}",
        "last_name": "",
    }


async def _maybe_finalize(user_id: int, chat_id: int) -> None:
    """Alerts service uses in-memory _conversation_states dict. Peek at it
    directly to know if the flow finished. If dict missing or state is IDLE,
    clear internal state so /start goes back to menu.
    """
    try:
        state_dict = alerts_service._conversation_states.get(int(chat_id))  # noqa: SLF001
        if not state_dict or state_dict.get("state") in (None, "IDLE"):
            await state_mgr.reset_state(user_id)
    except Exception:
        # Never fail the caller because of finalize best-effort logic
        pass


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    """Entry from menu → 🔧 Criar Alerta Mecânica.

    The alerts service has no explicit 'start_new_alert' — the flow begins
    when the mechanic sends text/photo/voice describing the problem. We
    prompt the user here and forward subsequent messages.
    """
    await state_mgr.start_flow(
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        flow=FLOW,
        initial_step="wait_input",
        initial_payload={"delegated": True},
    )
    from ..bot_api import send_message, inline_keyboard
    await send_message(
        chat_id,
        (
            "🔧 <b>Novo Alerta Mecânica</b>\n\n"
            "Envia agora o alerta:\n"
            "• Texto descrevendo o problema\n"
            "• Foto (com legenda opcional)\n"
            "• Nota de voz\n\n"
            "Pode enviar vários — envia <b>Concluir</b> quando terminar ou escolhe uma ação abaixo."
        ),
        reply_markup=inline_keyboard([
            [{"text": "🔙 Cancelar", "callback_data": "menu:cancel"}],
        ]),
    )


async def handle_attachment_raw(chat_id: int, user_id: int, message: dict, state: dict) -> bool:
    user_info = _user_info(user_id, {"name": ""}, message)

    voice = message.get("voice") or message.get("audio")
    if voice:
        await alerts_service.handle_incoming_voice(chat_id, user_info, voice)
        await _maybe_finalize(user_id, chat_id)
        return True

    photo = message.get("photo")
    if photo:
        best = max(photo, key=lambda p: p.get("file_size", 0))
        caption = message.get("caption")
        await alerts_service.handle_incoming_photo(chat_id, user_info, best, caption=caption)
        await _maybe_finalize(user_id, chat_id)
        return True

    doc = message.get("document")
    if doc and (doc.get("mime_type") or "").startswith("image/"):
        await alerts_service.handle_incoming_photo(chat_id, user_info, doc, caption=message.get("caption"))
        await _maybe_finalize(user_id, chat_id)
        return True

    return False


async def handle_message(chat_id: int, user_id: int, text: Optional[str],
                        photo_file_id: Optional[str], state: dict) -> None:
    user_info = _user_info(user_id, {"name": ""})
    if text:
        await alerts_service.handle_incoming_text(chat_id, user_info, text)
    elif photo_file_id:
        await alerts_service.handle_incoming_photo(chat_id, user_info, {"file_id": photo_file_id})
    await _maybe_finalize(user_id, chat_id)


async def handle_callback(chat_id: int, user_id: int, data: str,
                          user_auth: dict, state: dict) -> None:
    """Route by callback prefix to the corresponding alerts service handler."""
    try:
        if data.startswith("assign:"):
            parts = data.split(":", 2)
            if len(parts) == 3:
                await alerts_service.handle_assign_callback(chat_id, parts[1], parts[2])
        elif data.startswith("photos_done:"):
            await alerts_service.handle_photos_done_callback(chat_id, data.split(":", 1)[1])
        elif data.startswith("photos_"):
            verb, _, alert_id = data.partition(":")
            action = "yes" if "yes" in verb else "no"
            await alerts_service.handle_photos_callback(chat_id, action, alert_id)
        elif data.startswith("note_"):
            verb, _, alert_id = data.partition(":")
            action = "yes" if "yes" in verb else "no"
            await alerts_service.handle_note_callback(chat_id, action, alert_id)
        elif data.startswith("comment_"):
            verb, _, alert_id = data.partition(":")
            action_map = {"comment_text": "text", "comment_audio": "audio", "comment_none": "none"}
            await alerts_service.handle_comment_callback(chat_id, action_map.get(verb, "none"), alert_id)
        elif data.startswith("add_photo:"):
            await alerts_service.handle_add_photo_callback(chat_id, data.split(":", 1)[1])
        elif data.startswith("new_alert:"):
            await alerts_service.handle_new_alert_callback(chat_id, data.split(":", 1)[1])
    except Exception as e:
        logger.warning("mech_alert callback failed for data=%r: %s", data, e)
    await _maybe_finalize(user_id, chat_id)
