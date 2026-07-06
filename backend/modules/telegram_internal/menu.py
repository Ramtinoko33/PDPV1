"""Main menu rendering and callback handling for PDPV Bot Interno."""
import os
from .bot_api import send_message, inline_keyboard, edit_message_text
from . import state as state_mgr
from . import auth as auth_mgr


def _frontend_base_url() -> str:
    return os.environ.get("FRONTEND_URL") or os.environ.get(
        "REACT_APP_BACKEND_URL", "https://tickets.pneusdpedrov.com"
    )


def main_menu_markup(user_auth: dict) -> dict:
    """Render the main menu keyboard, respecting allowed_flows of the user."""
    allowed = set(user_auth.get("allowed_flows") or [])
    rows = []
    # Ordem pedida pelo utilizador: pré-ticket, renting, assistências, alertas mecânica
    if "pre_ticket" in allowed or not allowed:
        rows.append([{"text": "📋 Criar Pré-ticket", "callback_data": "menu:pre_ticket"}])
    if "renting" in allowed or not allowed:
        rows.append([{"text": "🚗 Criar Pedido Renting", "callback_data": "menu:renting"}])
    if "assistencias" in allowed or not allowed:
        rows.append([{"text": "🚨 Registar Assistência", "callback_data": "menu:assistencias"}])
    if "mech_alert" in allowed or not allowed:
        rows.append([{"text": "🔧 Criar Alerta Mecânica", "callback_data": "menu:mech_alert"}])
    rows.append([{"text": "❌ Cancelar fluxo atual", "callback_data": "menu:cancel"}])
    return inline_keyboard(rows)


WELCOME_TEMPLATE = (
    "👋 Olá. O que queres fazer?\n\n"
    "<i>Telegram serve para criar/capturar informação rapidamente. "
    "Para gerir, validar e concluir pedidos abre a dashboard.</i>"
)


async def send_main_menu(chat_id: int, user_auth: dict) -> None:
    await send_message(chat_id, WELCOME_TEMPLATE, reply_markup=main_menu_markup(user_auth))


CONFLICT_MARKUP = inline_keyboard(
    [
        [{"text": "▶️ Continuar", "callback_data": "conflict:continue"}],
        [{"text": "🔄 Cancelar e começar novo", "callback_data": "conflict:cancel_new"}],
    ]
)


async def send_active_flow_conflict(chat_id: int, current_flow: str, current_step: str) -> None:
    await send_message(
        chat_id,
        (
            "⚠️ Já tens um processo em curso.\n"
            f"<b>Fluxo:</b> {current_flow}\n"
            f"<b>Etapa:</b> <code>{current_step}</code>\n\n"
            "Queres continuar ou cancelar e começar novo?"
        ),
        reply_markup=CONFLICT_MARKUP,
    )


async def cancel_flow(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    await state_mgr.reset_state(telegram_user_id)
    await send_message(chat_id, "❌ Processo cancelado.")
    await send_main_menu(chat_id, user_auth)


def created_record_keyboard(record_type: str, dashboard_path: str) -> dict:
    base = _frontend_base_url().rstrip("/")
    return inline_keyboard(
        [[{"text": "🔗 Abrir na dashboard", "url": f"{base}{dashboard_path}"}]]
    )


async def send_unauthorized(chat_id: int, user_id: int = None, user_name: str = None) -> None:
    """Reply to an unauthorized user with their own Telegram ID so the admin
    can be given the exact number to add to the authorized list.
    """
    parts = [
        "⛔ <b>Utilizador não autorizado.</b>",
        "",
        "Envia esta informação ao administrador da PDPV para pedires acesso:",
    ]
    if user_id is not None:
        parts.append(f"• <b>ID Telegram:</b> <code>{user_id}</code>")
    if user_name:
        parts.append(f"• <b>Nome:</b> {user_name}")
    parts.append("")
    parts.append("Tira <i>screenshot</i> desta mensagem e envia-o ao administrador.")
    await send_message(chat_id, "\n".join(parts))
