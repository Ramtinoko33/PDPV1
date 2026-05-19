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
    if "mech_alert" in allowed or not allowed:
        rows.append([{"text": "🔧 Criar Alerta Mecânica", "callback_data": "menu:mech_alert"}])
    if "renting" in allowed or not allowed:
        rows.append([{"text": "🚗 Criar Pedido Renting", "callback_data": "menu:renting"}])
    if "pre_ticket" in allowed or not allowed:
        rows.append([{"text": "📋 Criar Pré-ticket", "callback_data": "menu:pre_ticket"}])
    rows.append([{"text": "❌ Cancelar fluxo atual", "callback_data": "menu:cancel"}])
    return inline_keyboard(rows)


WELCOME_TEMPLATE = (
    "👋 Olá <b>{name}</b>!\n\n"
    "Sou o <b>PDPV Bot Interno</b>. Escolhe uma opção abaixo:\n\n"
    "<i>Lembrete:</i> usa este bot apenas para <b>criar</b> pedidos rapidamente. "
    "Para consultar, filtrar e tratar pedidos abre a dashboard."
)


async def send_main_menu(chat_id: int, user_auth: dict) -> None:
    text = WELCOME_TEMPLATE.format(name=user_auth.get("name") or "equipa PDPV")
    await send_message(chat_id, text, reply_markup=main_menu_markup(user_auth))


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
    had = await state_mgr.has_active_flow(telegram_user_id)
    await state_mgr.reset_state(telegram_user_id)
    msg = "🚫 Fluxo cancelado." if had else "ℹ️ Não tinhas nenhum fluxo ativo."
    await send_message(chat_id, msg, reply_markup=main_menu_markup(user_auth))


def created_record_keyboard(record_type: str, dashboard_path: str) -> dict:
    base = _frontend_base_url().rstrip("/")
    return inline_keyboard(
        [[{"text": "🔗 Abrir na dashboard", "url": f"{base}{dashboard_path}"}]]
    )


async def send_unauthorized(chat_id: int) -> None:
    await send_message(
        chat_id,
        "⛔ <b>Utilizador não autorizado.</b>\nContacta o administrador.",
    )
