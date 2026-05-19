"""Alerta Mecânica flow — Phase 1 redirects to the dedicated @pdpv_alerts_bot.

Same rationale as renting.py: the existing dedicated bot already implements the
full state machine (GENES photo, IA analysis, multi-photo attachment, text/audio
comments with Whisper transcription, reception assignment). Inlining all of that
into the new bot is Phase 2 work that requires extracting the existing service
into a shared module — out of scope for the first delivery.
"""
import os
from ..bot_api import send_message, inline_keyboard
from .. import state as state_mgr

FLOW = "mech_alert"

ALERTS_BOT_URL = os.environ.get(
    "TELEGRAM_ALERTS_BOT_DEEPLINK", "https://t.me/pdpv_alerts_bot"
)


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    await state_mgr.reset_state(telegram_user_id)
    await send_message(
        chat_id,
        (
            "🔧 Os alertas de mecânica continuam temporariamente no bot antigo.\n\n"
            "Carrega no botão abaixo para abrir."
        ),
        reply_markup=inline_keyboard(
            [
                [{"text": "Abrir Bot Alertas Mecânica", "url": ALERTS_BOT_URL}],
                [{"text": "🔙 Voltar ao menu", "callback_data": "menu:back"}],
            ]
        ),
    )


async def handle_message(*args, **kwargs):
    return None


async def handle_callback(*args, **kwargs):
    return None
