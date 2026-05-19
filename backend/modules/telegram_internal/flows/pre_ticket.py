"""Pré-ticket flow — creates a ticket in the existing `tickets` collection
(via the normal flow) with channel='TELEGRAM_INTERNAL_BOT'.

State steps:
  customer_name -> customer_phone -> plate -> request_type -> description
  -> attachments_question -> attachments_collect -> summary -> done
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from db import db
from ..bot_api import send_message, inline_keyboard
from .. import state as state_mgr
from ..menu import created_record_keyboard, main_menu_markup
from ..logs import log_event

FLOW = "pre_ticket"

REQUEST_TYPES = [
    ("tires", "🛞 Pneus"),
    ("service", "🔧 Serviço"),
    ("info", "ℹ️ Informação"),
    ("quote", "📝 Orçamento"),
    ("other", "📦 Outro"),
]

PLATE_RE = re.compile(r"^[A-Z0-9]{2}-?[A-Z0-9]{2}-?[A-Z0-9]{2}$", re.IGNORECASE)


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    await state_mgr.start_flow(
        telegram_user_id,
        chat_id,
        flow=FLOW,
        initial_step="customer_name",
        initial_payload={"_created_by": user_auth.get("name"),
                         "_attachments": []},
    )
    await send_message(
        chat_id,
        "📋 <b>Novo Pré-ticket</b>\n\n"
        "1️⃣ Qual o <b>nome do cliente</b>?\n"
        "<i>(escreve /cancel para sair)</i>",
    )


async def handle_message(chat_id: int, telegram_user_id: int, text: Optional[str],
                         photo_file_id: Optional[str], state: dict) -> None:
    step = state.get("current_step")
    payload = state.get("temporary_payload") or {}

    if step == "customer_name":
        if not text or len(text.strip()) < 2:
            await send_message(chat_id, "⚠️ Nome inválido. Indica o nome completo do cliente.")
            return
        await state_mgr.update_state(telegram_user_id, current_step="customer_phone",
                                     payload_merge={"customer_name": text.strip()})
        await send_message(chat_id, "2️⃣ <b>Contacto telefónico</b> do cliente?")
        return

    if step == "customer_phone":
        digits = re.sub(r"\D+", "", text or "")
        if len(digits) < 9:
            await send_message(chat_id, "⚠️ Contacto inválido. Indica pelo menos 9 dígitos.")
            return
        await state_mgr.update_state(telegram_user_id, current_step="plate",
                                     payload_merge={"customer_phone": digits})
        await send_message(chat_id, "3️⃣ <b>Matrícula</b> da viatura? <i>(formato XX-XX-XX)</i>")
        return

    if step == "plate":
        plate = (text or "").upper().strip().replace(" ", "")
        if not PLATE_RE.match(plate):
            await send_message(chat_id, "⚠️ Matrícula inválida. Exemplo: <code>AB-12-CD</code>")
            return
        # normalize with dashes
        clean = plate.replace("-", "")
        plate = f"{clean[0:2]}-{clean[2:4]}-{clean[4:6]}"
        await state_mgr.update_state(telegram_user_id, current_step="request_type",
                                     payload_merge={"plate": plate})
        markup = inline_keyboard(
            [[{"text": label, "callback_data": f"preticket:type:{key}"}]
             for key, label in REQUEST_TYPES]
        )
        await send_message(chat_id, "4️⃣ Qual o <b>tipo de pedido</b>?", reply_markup=markup)
        return

    if step == "description":
        if not text or len(text.strip()) < 3:
            await send_message(chat_id, "⚠️ Descrição muito curta. Diz-me um pouco mais.")
            return
        await state_mgr.update_state(telegram_user_id, current_step="attachments_question",
                                     payload_merge={"description": text.strip()})
        markup = inline_keyboard(
            [
                [{"text": "📎 Sim, adicionar anexos", "callback_data": "preticket:att:yes"}],
                [{"text": "⏭ Continuar sem anexos", "callback_data": "preticket:att:no"}],
            ]
        )
        await send_message(chat_id, "6️⃣ Queres <b>anexar fotos</b>?", reply_markup=markup)
        return

    if step == "attachments_collect":
        # Photos arrive on the photo branch; here we treat text == "pronto" or /done
        if text and text.strip().lower() in ("/done", "pronto", "ok", "fim"):
            await _show_summary(chat_id, telegram_user_id, state)
            return
        if photo_file_id:
            atts = list(payload.get("_attachments") or [])
            atts.append({"telegram_file_id": photo_file_id, "added_at": datetime.now(timezone.utc).isoformat()})
            await state_mgr.update_state(telegram_user_id, payload_merge={"_attachments": atts})
            await send_message(
                chat_id,
                f"📎 Foto registada ({len(atts)} no total). Envia mais ou escreve <b>pronto</b> para terminar.",
            )
            return
        await send_message(chat_id, "⚠️ Envia uma foto ou escreve <b>pronto</b> para terminar.")
        return

    if step == "summary_confirm":
        await send_message(
            chat_id,
            "⚠️ Usa os botões de confirmação acima ou /cancel.",
        )
        return

    # Fallback
    await send_message(chat_id, "⚠️ Etapa desconhecida. Usa /cancel para reiniciar.")


async def handle_callback(chat_id: int, telegram_user_id: int, data: str,
                          user_auth: dict, state: dict) -> None:
    if data.startswith("preticket:type:"):
        type_key = data.split(":", 2)[2]
        type_label = next((label for key, label in REQUEST_TYPES if key == type_key), type_key)
        await state_mgr.update_state(
            telegram_user_id, current_step="description",
            payload_merge={"request_type": type_key, "request_type_label": type_label},
        )
        await send_message(
            chat_id,
            f"5️⃣ Descreve o pedido em poucas palavras.\n<i>(Tipo: {type_label})</i>",
        )
        return

    if data == "preticket:att:yes":
        await state_mgr.update_state(telegram_user_id, current_step="attachments_collect")
        await send_message(
            chat_id,
            "📎 Envia até 4 fotos. Quando terminares, escreve <b>pronto</b>.",
        )
        return

    if data == "preticket:att:no":
        await _show_summary(chat_id, telegram_user_id, state)
        return

    if data == "preticket:confirm":
        await _finalize(chat_id, telegram_user_id, user_auth, state)
        return

    if data == "preticket:edit":
        await send_message(
            chat_id,
            "✏️ Para alterar agora, usa /cancel e cria de novo. (Edição inline ficará para uma próxima versão.)",
        )
        return


async def _show_summary(chat_id: int, telegram_user_id: int, state: dict) -> None:
    payload = state.get("temporary_payload") or {}
    atts = payload.get("_attachments") or []
    summary = (
        "📋 <b>Resumo do Pré-ticket</b>\n\n"
        f"👤 Cliente: <b>{payload.get('customer_name','—')}</b>\n"
        f"📞 Contacto: <b>{payload.get('customer_phone','—')}</b>\n"
        f"🚘 Matrícula: <b>{payload.get('plate','—')}</b>\n"
        f"🏷 Tipo: <b>{payload.get('request_type_label','—')}</b>\n"
        f"📝 Descrição: <i>{payload.get('description','—')}</i>\n"
        f"📎 Anexos: <b>{len(atts)}</b>\n"
    )
    await state_mgr.update_state(telegram_user_id, current_step="summary_confirm")
    markup = inline_keyboard(
        [
            [{"text": "✅ Confirmar e criar", "callback_data": "preticket:confirm"}],
            [{"text": "❌ Cancelar", "callback_data": "menu:cancel"}],
        ]
    )
    await send_message(chat_id, summary, reply_markup=markup)


async def _generate_ticket_number() -> str:
    """Use the same numbering style as the rest of the system: TKYYYYMMDDXXXXXX (uppercase hex)."""
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:6].upper()
    return f"TK{now.strftime('%Y%m%d')}{suffix}"


async def _finalize(chat_id: int, telegram_user_id: int, user_auth: dict, state: dict) -> None:
    payload = state.get("temporary_payload") or {}
    now = datetime.now(timezone.utc).isoformat()
    ticket_id = str(uuid.uuid4())
    ticket_number = await _generate_ticket_number()

    # Build a minimal ticket compatible with the existing schema. The dashboard
    # treats `channel="TELEGRAM_INTERNAL_BOT"` as a marker for triage.
    doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "channel": "TELEGRAM_INTERNAL_BOT",
        "status": "NOVO",
        "priority": "NORMAL",
        "customer_name": payload.get("customer_name"),
        "customer_phone": payload.get("customer_phone"),
        "vehicle_plate": payload.get("plate"),
        "request_type": payload.get("request_type"),
        "subject": f"[Telegram Interno] {payload.get('request_type_label','Pré-ticket')}",
        "description": payload.get("description"),
        "attachments": [
            {
                "id": str(uuid.uuid4()),
                "telegram_file_id": a.get("telegram_file_id"),
                "added_at": a.get("added_at"),
                "source": "telegram_internal_bot",
            }
            for a in (payload.get("_attachments") or [])
        ],
        "created_by_telegram": {
            "telegram_user_id": telegram_user_id,
            "name": user_auth.get("name"),
        },
        "created_at": now,
        "updated_at": now,
        "first_response_done": False,
        "archived_at": None,
    }
    try:
        await db.tickets.insert_one(doc)
    except Exception as e:
        await log_event(telegram_user_id, chat_id, "flow_error",
                        active_flow=FLOW, current_step="finalize",
                        success=False, error=str(e))
        await send_message(chat_id, "❌ Erro ao criar pré-ticket. Tenta novamente.")
        return

    await state_mgr.reset_state(telegram_user_id)
    await log_event(telegram_user_id, chat_id, "flow_done",
                    active_flow=FLOW, current_step="finalize", success=True,
                    extra={"ticket_id": ticket_id, "ticket_number": ticket_number})

    await send_message(
        chat_id,
        (
            f"✅ <b>Pré-ticket criado com sucesso.</b>\n\n"
            f"Tipo: 📋 Pré-ticket\n"
            f"Referência: <b>#{ticket_number}</b>\n\n"
            f"Para acompanhar ou tratar, abre na dashboard."
        ),
        reply_markup=created_record_keyboard("ticket", f"/tickets/{ticket_id}"),
    )
    # Send menu again
    await send_message(chat_id, "Pronto para outro pedido?", reply_markup=main_menu_markup(user_auth))
