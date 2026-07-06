"""Assistências flow — Phase 1 redirects to the dedicated @pdpv_assistencias_bot.

Same rationale as renting.py and mech_alert.py: the existing dedicated bot already
implements the full state machine (localização → matrícula (com OCR) → folha de obra
→ fotos adicionais → notas texto/áudio → criação do registo). Inlining ~900 linhas
de service.py é Fase 2 (extração para módulo partilhado) — fora do âmbito da Fase 1.
"""
import os
from ..bot_api import send_message, inline_keyboard
from .. import state as state_mgr


FLOW = "assistencias"

ASSISTENCIAS_BOT_URL = os.environ.get(
    "TELEGRAM_ASSISTENCIAS_BOT_DEEPLINK", "https://t.me/pdpv_assistencias_bot"
)


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    # No inline state machine yet — redirect to the dedicated bot.
    await state_mgr.reset_state(telegram_user_id)
    await send_message(
        chat_id,
        (
            "🚨 As <b>Assistências</b> continuam temporariamente no bot dedicado.\n\n"
            "Carrega no botão abaixo para abrir."
        ),
        reply_markup=inline_keyboard(
            [
                [{"text": "Abrir Bot Assistências", "url": ASSISTENCIAS_BOT_URL}],
                [{"text": "🔙 Voltar ao menu", "callback_data": "menu:back"}],
            ]
        ),
    )


async def handle_message(*args, **kwargs):
    return None


async def handle_callback(*args, **kwargs):
    return None
