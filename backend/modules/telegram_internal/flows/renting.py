"""Renting flow — Phase 1 redirects to the dedicated @pdpv_rentingpneus_bot.

In Phase 2 the full state machine (driver / plate OCR / 4 wheels with 3 photos each /
service type / observations / audio Whisper transcription) will be inlined here by
extracting the existing logic into a shared service. For now we point users at the
existing dedicated bot to avoid duplicating ~1500 lines of state machine and risking
regressions on the production renting flow.
"""
import os
from ..bot_api import send_message, inline_keyboard
from .. import state as state_mgr


FLOW = "renting"

RENTING_BOT_URL = os.environ.get(
    "TELEGRAM_RENTING_BOT_DEEPLINK", "https://t.me/pdpv_rentingpneus_bot"
)


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    # We do not register an active flow because there is no inline state machine yet.
    await state_mgr.reset_state(telegram_user_id)
    await send_message(
        chat_id,
        (
            "🚗 <b>Pedido Renting</b>\n\n"
            "O fluxo completo de Renting (com fotos das 4 rodas, OCR de matrícula e KM, "
            "marca/modelo/DOT/piso por pneu) está disponível no bot dedicado.\n\n"
            "Toca no botão para o abrir e enviar <code>/novo_renting</code>:"
        ),
        reply_markup=inline_keyboard(
            [
                [{"text": "➡️ Abrir @pdpv_rentingpneus_bot", "url": RENTING_BOT_URL}],
                [{"text": "🔙 Voltar ao menu", "callback_data": "menu:back"}],
            ]
        ),
    )


async def handle_message(*args, **kwargs):
    return None


async def handle_callback(*args, **kwargs):
    return None
