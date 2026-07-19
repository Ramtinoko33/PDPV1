"""Assistências module — service layer (Telegram bot flow, storage, DB ops)."""
import os
import uuid
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from db import db
from . import bot_api
from .models import (
    AssistenciaStatus, ALLOWED_STATUS_TRANSITIONS, AUDITED_FIELDS,
    NON_BILLABLE_REASONS, ADDITIONAL_PHOTO_CATEGORIES, MAX_ADDITIONAL_PHOTOS,
    STATE_IDLE, STATE_WAIT_LOCATION, STATE_WAIT_PLATE, STATE_CONFIRM_PLATE,
    STATE_EDIT_PLATE, STATE_WAIT_WORKSHEET, STATE_ASK_ADDITIONAL,
    STATE_COLLECT_ADDITIONAL, STATE_ASK_NOTES, STATE_COLLECT_TEXT_NOTES,
    STATE_COLLECT_AUDIO_NOTES,
)

logger = logging.getLogger(__name__)


# ============== Helpers ==============
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_audit_entry(action: str, user: dict, details: dict = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "action": action,
        "user_id": user.get("id") if isinstance(user, dict) else None,
        "user_name": user.get("name") if isinstance(user, dict) else str(user),
        "timestamp": _now_iso(),
        "details": details or {},
    }


# ============== Storage helpers ==============
async def _store_image(image_bytes: bytes, prefix: str, content_type: str = "image/jpeg") -> dict:
    """Store image to object storage; fallback to base64 if storage fails."""
    photo_id = str(uuid.uuid4())
    ext = "jpg" if "jpeg" in content_type or "jpg" in content_type else "png"
    record = {
        "id": photo_id,
        "file_size": len(image_bytes),
        "content_type": content_type,
        "storage_path": None,
        "base64_data": None,
        "stored_at": _now_iso(),
    }
    try:
        from services.storage_service import put_object
        path = f"assistencias/{prefix}/{photo_id}.{ext}"
        put_object(path, image_bytes, content_type)
        record["storage_path"] = path
        return record
    except Exception as e:
        logger.warning(f"[ASSIST_STORE] storage failed, falling back to base64: {e}")
    if len(image_bytes) < 4 * 1024 * 1024:
        record["base64_data"] = base64.b64encode(image_bytes).decode("utf-8")
    return record


async def _store_audio(audio_bytes: bytes, content_type: str = "audio/ogg") -> dict:
    audio_id = str(uuid.uuid4())
    ext_map = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav"}
    ext = ext_map.get(content_type, "ogg")
    record = {
        "id": audio_id,
        "file_size": len(audio_bytes),
        "content_type": content_type,
        "storage_path": None,
        "base64_data": None,
        "stored_at": _now_iso(),
    }
    try:
        from services.storage_service import put_object
        path = f"assistencias/audio/{audio_id}.{ext}"
        put_object(path, audio_bytes, content_type)
        record["storage_path"] = path
        return record
    except Exception as e:
        logger.warning(f"[ASSIST_STORE] audio storage failed: {e}")
    if len(audio_bytes) < 5 * 1024 * 1024:
        record["base64_data"] = base64.b64encode(audio_bytes).decode("utf-8")
    return record


async def _store_pdf(pdf_bytes: bytes) -> dict:
    pdf_id = str(uuid.uuid4())
    record = {
        "id": pdf_id,
        "file_size": len(pdf_bytes),
        "content_type": "application/pdf",
        "storage_path": None,
        "base64_data": None,
        "stored_at": _now_iso(),
    }
    try:
        from services.storage_service import put_object
        path = f"assistencias/invoices/{pdf_id}.pdf"
        put_object(path, pdf_bytes, "application/pdf")
        record["storage_path"] = path
        return record
    except Exception as e:
        logger.warning(f"[ASSIST_STORE] PDF storage failed: {e}")
    if len(pdf_bytes) < 8 * 1024 * 1024:
        record["base64_data"] = base64.b64encode(pdf_bytes).decode("utf-8")
    return record


async def get_file_bytes(file_record: dict) -> Optional[bytes]:
    if not file_record:
        return None
    if file_record.get("storage_path"):
        try:
            from services.storage_service import get_object
            data, _ = get_object(file_record["storage_path"])
            if data:
                return data
        except Exception as e:
            logger.warning(f"[ASSIST_STORE] storage fetch failed: {e}")
    if file_record.get("base64_data"):
        try:
            return base64.b64decode(file_record["base64_data"])
        except Exception:
            pass
    return None


# ============== OCR: Plate ==============
async def ocr_plate(image_bytes: bytes) -> Optional[str]:
    """Extract Portuguese license plate via GPT-4o vision. Returns string or None."""
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        import json
        import re
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"assist-plate-{uuid.uuid4().hex[:6]}",
            system_message="Extrais matrículas portuguesas de fotos. Responde APENAS JSON."
        ).with_model("openai", "gpt-4o")
        prompt = (
            "Extrai a matrícula portuguesa visível. Formato: AA-00-AA ou 00-AA-00. "
            'Devolve JSON: {"plate":"XX-XX-XX ou null"}'
        )
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        resp = await chat.send_message(
            UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        )
        text = str(resp).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            return data.get("plate") or None
    except Exception as e:
        logger.error(f"[ASSIST_OCR] plate error: {e}")
    return None


# ============== Telegram bot state (persisted in MongoDB so multi-pod / restarts don't lose context) ==============

async def _load_state(chat_id: int) -> dict:
    rec = await db.assistencias_bot_state.find_one({"chat_id": int(chat_id)}, {"_id": 0})
    if not rec:
        return {"state": STATE_IDLE, "draft": {}}
    return {"state": rec.get("state", STATE_IDLE), "draft": rec.get("draft", {})}


async def _save_state(chat_id: int, state: dict) -> None:
    await db.assistencias_bot_state.update_one(
        {"chat_id": int(chat_id)},
        {"$set": {
            "chat_id": int(chat_id),
            "state": state.get("state", STATE_IDLE),
            "draft": state.get("draft", {}),
            "updated_at": _now_iso(),
        }},
        upsert=True,
    )


async def _reset_state(chat_id: int) -> None:
    await db.assistencias_bot_state.delete_one({"chat_id": int(chat_id)})


# ============== Authorized employees ==============
async def get_employee_for_chat(telegram_user_id: int) -> Optional[dict]:
    """Look up the linked employee (User) for this Telegram user id.

    Two sources are considered so the flow works whether the user was
    onboarded via the legacy standalone bot OR through the consolidated
    internal bot (@pdpv_interno_bot):
      1) assistencias_bot_users → users (legacy)
      2) telegram_internal_authorized_users with 'assistencias' in
         allowed_flows (new consolidated path). A synthetic minimal
         employee dict is returned in that case.
    """
    rec = await db.assistencias_bot_users.find_one(
        {"telegram_user_id": telegram_user_id, "active": True}, {"_id": 0}
    )
    if rec:
        user = await db.users.find_one({"id": rec.get("user_id")}, {"_id": 0, "password_hash": 0})
        if user and (
            user.get("role") in ("ADMIN", "SUPERVISOR")
            or user.get("has_assistencias_access")
        ):
            return user

    # Fallback: internal bot authorization
    internal_rec = await db.telegram_internal_authorized_users.find_one(
        {"telegram_user_id": telegram_user_id, "active": True}, {"_id": 0}
    )
    if internal_rec and "assistencias" in (internal_rec.get("allowed_flows") or []):
        return {
            "id": f"internal-{telegram_user_id}",
            "name": internal_rec.get("name") or f"Op {telegram_user_id}",
            "role": internal_rec.get("role") or "AGENT",
            "email": f"telegram-{telegram_user_id}@pdpv.internal",
            "has_assistencias_access": True,
        }
    return None


# ============== Bot flow ==============
async def start_new_assistance(chat_id: int, telegram_user: dict) -> None:
    """Entry point: /nova_assistencia or /start."""
    employee = await get_employee_for_chat(telegram_user["id"])
    if not employee:
        await bot_api.send_message(
            chat_id,
            "❌ Não está autorizado a usar este bot.\n"
            "Peça ao administrador para o autorizar no painel "
            "<b>Assistências → Utilizadores</b>.",
        )
        return
    await _reset_state(chat_id)
    state = await _load_state(chat_id)
    state["state"] = STATE_WAIT_LOCATION
    state["draft"] = {
        "employee_id": employee["id"],
        "employee_name": employee.get("name"),
        "telegram_chat_id": chat_id,
        "telegram_user_id": telegram_user["id"],
    }
    await _save_state(chat_id, state)
    await bot_api.send_message(
        chat_id,
        "🚐 <b>Nova Assistência</b>\n\n"
        "📍 <b>Passo 1/3:</b> Partilhe a sua <b>localização atual</b>.\n\n"
        "No Telegram: <i>clip 📎 → Localização → Enviar a minha localização</i>.\n\n"
        "Esta etapa é obrigatória.",
    )


async def cancel_session(chat_id: int) -> None:
    await _reset_state(chat_id)
    await bot_api.send_message(chat_id, "❌ Sessão cancelada. Use /nova_assistencia para começar de novo.")


async def handle_location(chat_id: int, telegram_user: dict, location: dict) -> None:
    state = await _load_state(chat_id)
    if state["state"] != STATE_WAIT_LOCATION:
        await bot_api.send_message(chat_id, "Use /nova_assistencia para começar.")
        return
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is None or lon is None:
        await bot_api.send_message(chat_id, "❌ Localização inválida. Tente novamente.")
        return
    state["draft"]["latitude"] = lat
    state["draft"]["longitude"] = lon
    state["draft"]["google_maps_url"] = f"https://www.google.com/maps?q={lat},{lon}"
    state["draft"]["location_timestamp"] = _now_iso()
    state["state"] = STATE_WAIT_PLATE
    await _save_state(chat_id, state)
    await bot_api.send_message(
        chat_id,
        "✅ Localização recebida.\n\n"
        "🚛 <b>Passo 2/3:</b> Envie uma <b>foto da matrícula</b> "
        "do veículo/camião/tractor, ou escreva-a manualmente (ex: AA-00-AA).",
    )


async def handle_photo(chat_id: int, telegram_user: dict, photo: dict) -> None:
    state = await _load_state(chat_id)
    if state["state"] == STATE_WAIT_PLATE:
        img_bytes, _ = await bot_api.download_file(photo["file_id"])
        if not img_bytes:
            await bot_api.send_message(chat_id, "❌ Falha a transferir a foto. Tente novamente.")
            return
        photo_rec = await _store_image(img_bytes, "plates")
        state["draft"]["plate_photo"] = photo_rec
        await bot_api.send_message(chat_id, "🔍 A analisar a matrícula...")
        plate = await ocr_plate(img_bytes)
        if plate:
            state["draft"]["registration_plate_ocr"] = plate
            state["draft"]["registration_plate"] = plate
            state["state"] = STATE_CONFIRM_PLATE
            await _save_state(chat_id, state)
            kb = {"inline_keyboard": [
                [{"text": f"✅ Confirmar {plate}", "callback_data": "plate_ok"}],
                [{"text": "✏️ Corrigir manualmente", "callback_data": "plate_edit"}],
            ]}
            await bot_api.send_message(chat_id, f"Matrícula detectada: <b>{plate}</b>", reply_markup=kb)
        else:
            state["state"] = STATE_EDIT_PLATE
            await _save_state(chat_id, state)
            await bot_api.send_message(
                chat_id, "Não consegui ler a matrícula automaticamente. Por favor escreva-a (ex: AA-00-AA)."
            )
        return

    if state["state"] == STATE_WAIT_WORKSHEET:
        img_bytes, _ = await bot_api.download_file(photo["file_id"])
        if not img_bytes:
            await bot_api.send_message(chat_id, "❌ Falha a transferir. Tente novamente.")
            return
        rec = await _store_image(img_bytes, "worksheets")
        state["draft"]["worksheet_photo"] = rec
        state["state"] = STATE_ASK_ADDITIONAL
        await _save_state(chat_id, state)
        kb = {"inline_keyboard": [
            [{"text": "📷 Sim, anexar fotos", "callback_data": "addl_yes"}],
            [{"text": "⏭️ Não, continuar", "callback_data": "addl_no"}],
        ]}
        await bot_api.send_message(
            chat_id,
            "✅ Folha de obra recebida.\n\n"
            "Quer anexar fotos adicionais do serviço (pneus montados, etiquetas, avaria, etc.)?",
            reply_markup=kb,
        )
        return

    if state["state"] == STATE_COLLECT_ADDITIONAL:
        img_bytes, _ = await bot_api.download_file(photo["file_id"])
        if not img_bytes:
            return
        rec = await _store_image(img_bytes, "additional")
        state["draft"].setdefault("additional_photos", []).append(rec)
        count = len(state["draft"]["additional_photos"])
        await _save_state(chat_id, state)
        if count >= MAX_ADDITIONAL_PHOTOS:
            await bot_api.send_message(chat_id, f"📷 {count}/{MAX_ADDITIONAL_PHOTOS} fotos recebidas. Limite atingido.")
            await _ask_notes(chat_id)
        else:
            kb = {"inline_keyboard": [
                [{"text": f"✅ Concluído ({count}/{MAX_ADDITIONAL_PHOTOS})", "callback_data": "addl_done"}]
            ]}
            await bot_api.send_message(
                chat_id,
                f"📷 Foto {count}/{MAX_ADDITIONAL_PHOTOS} recebida. Envie mais ou toque em concluído.",
                reply_markup=kb,
            )
        return

    await bot_api.send_message(chat_id, "Não esperava uma foto neste momento. Use /nova_assistencia para começar.")


async def handle_voice(chat_id: int, telegram_user: dict, voice: dict) -> None:
    state = await _load_state(chat_id)
    if state["state"] not in (STATE_COLLECT_AUDIO_NOTES, STATE_ASK_NOTES):
        await bot_api.send_message(chat_id, "Áudio recebido fora de contexto.")
        return
    audio_bytes, mime = await bot_api.download_file(voice["file_id"])
    if not audio_bytes:
        await bot_api.send_message(chat_id, "❌ Falha a transferir áudio.")
        return
    rec = await _store_audio(audio_bytes, mime or "audio/ogg")
    state["draft"]["audio_file"] = rec
    try:
        from modules.telegram.service import transcribe_audio_with_whisper
        ext = "ogg"
        if mime and "mpeg" in mime:
            ext = "mp3"
        elif mime and "mp4" in mime:
            ext = "m4a"
        transcript = await transcribe_audio_with_whisper(audio_bytes, ext)
        if transcript:
            state["draft"]["audio_transcription"] = transcript
    except Exception as e:
        logger.warning(f"[ASSIST_BOT] transcription failed: {e}")
    await _save_state(chat_id, state)
    await _finalize_creation(chat_id)


async def handle_text(chat_id: int, telegram_user: dict, text: str) -> None:
    state = await _load_state(chat_id)
    if state["state"] in (STATE_WAIT_PLATE, STATE_EDIT_PLATE):
        import re
        plate_clean = re.sub(r"\s+", "", text.upper())
        state["draft"]["registration_plate"] = plate_clean
        state["state"] = STATE_WAIT_WORKSHEET
        await _save_state(chat_id, state)
        await bot_api.send_message(
            chat_id,
            f"✅ Matrícula registada: <b>{plate_clean}</b>\n\n"
            "📄 <b>Passo 3/3:</b> Envie a <b>foto da folha de obra preenchida</b>.",
        )
        return

    if state["state"] == STATE_COLLECT_TEXT_NOTES:
        state["draft"]["text_notes"] = text.strip()
        await _save_state(chat_id, state)
        await _finalize_creation(chat_id)
        return

    await bot_api.send_message(
        chat_id,
        "Comandos disponíveis:\n/nova_assistencia — começar\n/cancelar — cancelar sessão atual"
    )


async def handle_callback(chat_id: int, data: str, callback_id: str = "") -> None:
    state = await _load_state(chat_id)
    await bot_api.answer_callback_query(callback_id)

    if data == "plate_ok" and state["state"] == STATE_CONFIRM_PLATE:
        state["state"] = STATE_WAIT_WORKSHEET
        await _save_state(chat_id, state)
        await bot_api.send_message(
            chat_id,
            "📄 <b>Passo 3/3:</b> Envie a <b>foto da folha de obra preenchida</b>.",
        )
        return

    if data == "plate_edit" and state["state"] == STATE_CONFIRM_PLATE:
        state["state"] = STATE_EDIT_PLATE
        await _save_state(chat_id, state)
        await bot_api.send_message(chat_id, "Escreva a matrícula correcta (ex: AA-00-AA).")
        return

    if data == "addl_yes" and state["state"] == STATE_ASK_ADDITIONAL:
        state["state"] = STATE_COLLECT_ADDITIONAL
        await _save_state(chat_id, state)
        await bot_api.send_message(
            chat_id, f"📷 Envie até {MAX_ADDITIONAL_PHOTOS} fotos. Toque em concluído quando terminar."
        )
        return

    if data == "addl_no" and state["state"] == STATE_ASK_ADDITIONAL:
        await _ask_notes(chat_id)
        return

    if data == "addl_done" and state["state"] == STATE_COLLECT_ADDITIONAL:
        await _ask_notes(chat_id)
        return

    if data == "notes_text" and state["state"] == STATE_ASK_NOTES:
        state["state"] = STATE_COLLECT_TEXT_NOTES
        await _save_state(chat_id, state)
        await bot_api.send_message(chat_id, "✏️ Escreva as observações.")
        return

    if data == "notes_voice" and state["state"] == STATE_ASK_NOTES:
        state["state"] = STATE_COLLECT_AUDIO_NOTES
        await _save_state(chat_id, state)
        await bot_api.send_message(chat_id, "🎤 Grave e envie a sua mensagem de voz.")
        return

    if data == "notes_skip" and state["state"] == STATE_ASK_NOTES:
        await _finalize_creation(chat_id)
        return

    # Delivery confirmation callback (after invoice sent)
    if data.startswith("delivered:"):
        assist_id = data.split(":", 1)[1]
        await confirm_delivery_from_bot(assist_id, chat_id)
        return


async def _ask_notes(chat_id: int) -> None:
    state = await _load_state(chat_id)
    state["state"] = STATE_ASK_NOTES
    await _save_state(chat_id, state)
    kb = {"inline_keyboard": [
        [{"text": "📝 Texto", "callback_data": "notes_text"}],
        [{"text": "🎤 Voz", "callback_data": "notes_voice"}],
        [{"text": "⏭️ Saltar", "callback_data": "notes_skip"}],
    ]}
    await bot_api.send_message(chat_id, "Quer adicionar observações?", reply_markup=kb)


async def _finalize_creation(chat_id: int) -> None:
    state = await _load_state(chat_id)
    draft = state.get("draft", {})

    # Validate mandatory fields
    has_location = draft.get("latitude") is not None and draft.get("longitude") is not None
    has_plate = bool(draft.get("registration_plate"))
    has_worksheet = bool(draft.get("worksheet_photo"))

    initial_status = AssistenciaStatus.AGUARDA_FATURACAO.value
    if not (has_location and has_plate and has_worksheet):
        initial_status = AssistenciaStatus.DADOS_INCOMPLETOS.value

    record = {
        "id": str(uuid.uuid4()),
        "employee_id": draft.get("employee_id"),
        "employee_name": draft.get("employee_name"),
        "telegram_chat_id": draft.get("telegram_chat_id"),
        "telegram_user_id": draft.get("telegram_user_id"),
        "created_at": _now_iso(),
        "latitude": draft.get("latitude"),
        "longitude": draft.get("longitude"),
        "approximate_address": draft.get("approximate_address"),
        "google_maps_url": draft.get("google_maps_url"),
        "location_timestamp": draft.get("location_timestamp"),
        "registration_plate": draft.get("registration_plate"),
        "registration_plate_ocr": draft.get("registration_plate_ocr"),
        "plate_photo": draft.get("plate_photo"),
        "worksheet_photo": draft.get("worksheet_photo"),
        "additional_photos": draft.get("additional_photos", []),
        "text_notes": draft.get("text_notes"),
        "audio_file": draft.get("audio_file"),
        "audio_transcription": draft.get("audio_transcription"),
        "status": initial_status,
        "invoice_number": None,
        "invoice_total": None,
        "invoice_date": None,
        "invoice_customer": None,
        "invoice_nif": None,
        "invoice_pdf": None,
        "invoice_extracted": None,
        "billed_by": None,
        "billed_at": None,
        "delivery_confirmed_at": None,
        "non_billable_reason": None,
        "non_billable_approved_by": None,
        "internal_note": None,
        "audit_logs": [
            _make_audit_entry(
                "created_via_bot",
                {"id": draft.get("employee_id"), "name": draft.get("employee_name")},
                {"initial_status": initial_status},
            )
        ],
    }
    await db.assistencias.insert_one(record)
    await _reset_state(chat_id)

    # Notify office (admins + supervisors) about the new assistance
    try:
        from services.notification_service import notify_supervisors
        plate = record["registration_plate"] or "—"
        msg_body = f"{record.get('employee_name') or 'Funcionário'} criou assistência {plate}"
        if initial_status == AssistenciaStatus.DADOS_INCOMPLETOS.value:
            msg_body += " (dados incompletos)"
        await notify_supervisors(
            title="Nova Assistência",
            body=msg_body,
            notification_type="info",
        )
    except Exception as e:
        logger.warning(f"[ASSIST_BOT] notify_supervisors failed: {e}")

    summary_lines = [
        "✅ <b>Assistência registada com sucesso!</b>",
        f"<b>Matrícula:</b> {record['registration_plate']}",
        f"<b>Localização:</b> {record['google_maps_url']}",
    ]
    if record["additional_photos"]:
        summary_lines.append(f"<b>Fotos:</b> {len(record['additional_photos'])}")
    if record.get("text_notes"):
        summary_lines.append(f"<b>Notas:</b> {record['text_notes'][:80]}")
    if record.get("audio_transcription"):
        summary_lines.append(f"<b>Áudio:</b> {record['audio_transcription'][:80]}")
    summary_lines.append("")
    summary_lines.append(f"Estado: <b>{initial_status}</b>")
    if initial_status == AssistenciaStatus.DADOS_INCOMPLETOS.value:
        summary_lines.append("⚠️ Há dados em falta — o escritório vai contactá-lo.")
    await bot_api.send_message(chat_id, "\n".join(summary_lines))


async def confirm_delivery_from_bot(assist_id: str, chat_id: int) -> None:
    rec = await db.assistencias.find_one({"id": assist_id}, {"_id": 0})
    if not rec:
        await bot_api.send_message(chat_id, "❌ Assistência não encontrada.")
        return
    if rec.get("status") != AssistenciaStatus.ENVIADA_FUNCIONARIO.value:
        await bot_api.send_message(chat_id, "ℹ️ Esta assistência ainda não está pronta para confirmar entrega.")
        return
    audit = _make_audit_entry(
        "delivery_confirmed_via_bot",
        {"id": rec.get("employee_id"), "name": rec.get("employee_name")},
    )
    await db.assistencias.update_one(
        {"id": assist_id},
        {"$set": {
            "status": AssistenciaStatus.FATURADA_CONCLUIDA.value,
            "delivery_confirmed_at": _now_iso(),
        }, "$push": {"audit_logs": audit}},
    )
    await bot_api.send_message(
        chat_id, "✅ Entrega confirmada. Obrigado! Assistência marcada como concluída."
    )


# ============== Dashboard / API operations ==============
async def list_records(
    status: Optional[str], employee_id: Optional[str], plate: Optional[str],
    invoice_number: Optional[str], search: Optional[str], page: int, page_size: int,
) -> Tuple[List[dict], int]:
    query: dict = {}
    if status:
        query["status"] = status
    if employee_id:
        query["employee_id"] = employee_id
    if plate:
        query["registration_plate"] = {"$regex": plate.upper().strip(), "$options": "i"}
    if invoice_number:
        query["invoice_number"] = {"$regex": invoice_number.strip(), "$options": "i"}
    if search:
        s = search.strip()
        query["$or"] = [
            {"registration_plate": {"$regex": s, "$options": "i"}},
            {"invoice_number": {"$regex": s, "$options": "i"}},
            {"invoice_customer": {"$regex": s, "$options": "i"}},
            {"employee_name": {"$regex": s, "$options": "i"}},
            {"text_notes": {"$regex": s, "$options": "i"}},
        ]
    total = await db.assistencias.count_documents(query)
    cursor = db.assistencias.find(query, {"_id": 0}).sort("created_at", -1) \
        .skip((page - 1) * page_size).limit(page_size)
    items = await cursor.to_list(page_size)
    return items, total


async def get_record(record_id: str) -> Optional[dict]:
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def get_stats(record_filter: dict = None) -> dict:
    """Aggregated counters for dashboard cards."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    pipeline = [
        {"$facet": {
            "by_status": [{"$group": {"_id": "$status", "n": {"$sum": 1}}}],
            "today": [
                {"$match": {"created_at": {"$gte": today_start}}},
                {"$count": "n"},
            ],
        }}
    ]
    agg = await db.assistencias.aggregate(pipeline).to_list(1)
    out = {"today": 0}
    for s in AssistenciaStatus:
        out[s.value] = 0
    if agg:
        for row in agg[0].get("by_status", []):
            out[row["_id"]] = row["n"]
        if agg[0].get("today"):
            out["today"] = agg[0]["today"][0]["n"]
    return out


async def get_stats_advanced(start: Optional[str], end: Optional[str]) -> dict:
    """Per-employee, per-status, monthly aggregates + totals."""
    match: dict = {}
    if start:
        match.setdefault("created_at", {})["$gte"] = start
    if end:
        match.setdefault("created_at", {})["$lte"] = end + "T23:59:59"
    base = [{"$match": match}] if match else []
    pipeline = base + [{"$facet": {
        "by_employee": [
            {"$group": {
                "_id": {"id": "$employee_id", "name": "$employee_name"},
                "count": {"$sum": 1},
                "billed_total": {"$sum": {"$ifNull": ["$invoice_total", 0]}},
                "billed_count": {"$sum": {"$cond": [{"$eq": ["$status", "FATURADA_CONCLUIDA"]}, 1, 0]}},
            }},
            {"$sort": {"count": -1}},
        ],
        "by_status": [{"$group": {"_id": "$status", "n": {"$sum": 1}}}],
        "by_month": [
            {"$addFields": {"month": {"$substr": ["$created_at", 0, 7]}}},
            {"$group": {
                "_id": "$month",
                "count": {"$sum": 1},
                "billed_total": {"$sum": {"$ifNull": ["$invoice_total", 0]}},
            }},
            {"$sort": {"_id": 1}},
        ],
        "totals": [
            {"$group": {
                "_id": None,
                "count": {"$sum": 1},
                "billed_total": {"$sum": {"$ifNull": ["$invoice_total", 0]}},
            }},
        ],
    }}]
    agg = await db.assistencias.aggregate(pipeline).to_list(1)
    res = agg[0] if agg else {}
    employees = [
        {"employee_id": r["_id"].get("id"), "employee_name": r["_id"].get("name"),
         "count": r["count"], "billed_total": round(r["billed_total"], 2),
         "billed_count": r["billed_count"]}
        for r in res.get("by_employee", [])
    ]
    return {
        "by_employee": employees,
        "by_status": {r["_id"]: r["n"] for r in res.get("by_status", [])},
        "by_month": [
            {"month": r["_id"], "count": r["count"], "billed_total": round(r["billed_total"], 2)}
            for r in res.get("by_month", [])
        ],
        "totals": (res.get("totals") or [{}])[0],
    }


async def export_csv(status: Optional[str], employee_id: Optional[str],
                     start: Optional[str], end: Optional[str]) -> bytes:
    import io
    import csv as _csv
    query: dict = {}
    if status:
        query["status"] = status
    if employee_id:
        query["employee_id"] = employee_id
    if start:
        query.setdefault("created_at", {})["$gte"] = start
    if end:
        query.setdefault("created_at", {})["$lte"] = end + "T23:59:59"
    rows = await db.assistencias.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    buf = io.StringIO()
    writer = _csv.writer(buf, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
    writer.writerow([
        "Data Criação", "Funcionário", "Matrícula", "Estado",
        "Latitude", "Longitude", "Google Maps",
        "Nº Fatura", "Data Fatura", "Total €", "Cliente", "NIF",
        "Motivo Não Faturável", "Entrega Confirmada", "Observações",
    ])
    for r in rows:
        writer.writerow([
            r.get("created_at", ""),
            r.get("employee_name", ""),
            r.get("registration_plate", ""),
            r.get("status", ""),
            r.get("latitude", ""),
            r.get("longitude", ""),
            r.get("google_maps_url", ""),
            r.get("invoice_number", ""),
            r.get("invoice_date", ""),
            r.get("invoice_total", ""),
            r.get("invoice_customer", ""),
            r.get("invoice_nif", ""),
            r.get("non_billable_reason", ""),
            r.get("delivery_confirmed_at", ""),
            (r.get("text_notes") or "").replace("\n", " ")[:300],
        ])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


async def update_status(record_id: str, new_status: str, user: dict) -> Optional[dict]:
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    old_status = rec.get("status")
    if new_status not in ALLOWED_STATUS_TRANSITIONS.get(old_status, set()):
        return {"error": f"Transição não permitida: {old_status} → {new_status}"}
    audit = _make_audit_entry("status_change", user, {"from": old_status, "to": new_status})
    await db.assistencias.update_one(
        {"id": record_id},
        {"$set": {"status": new_status}, "$push": {"audit_logs": audit}},
    )
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def update_record(record_id: str, updates: dict, user: dict) -> Optional[dict]:
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    changed = {k: v for k, v in updates.items() if k in AUDITED_FIELDS and rec.get(k) != v}
    if not changed and not updates:
        return rec
    audit_entries = [
        _make_audit_entry("field_update", user, {"field": k, "from": rec.get(k), "to": v})
        for k, v in changed.items()
    ]
    set_doc = {k: v for k, v in updates.items() if k in (AUDITED_FIELDS + ["approximate_address"])}
    push_doc = {"audit_logs": {"$each": audit_entries}} if audit_entries else None
    update_op = {"$set": set_doc} if set_doc else {}
    if push_doc:
        update_op["$push"] = push_doc
    if update_op:
        await db.assistencias.update_one({"id": record_id}, update_op)
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def delete_record(record_id: str, user: dict) -> bool:
    res = await db.assistencias.delete_one({"id": record_id})
    return res.deleted_count > 0


# ============== Invoice upload + extraction ==============
async def attach_invoice_and_extract(record_id: str, pdf_bytes: bytes, user: dict) -> Optional[dict]:
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    pdf_record = await _store_pdf(pdf_bytes)
    from .pdf_extraction import extract_invoice_fields
    extracted = await extract_invoice_fields(pdf_bytes)
    audit = _make_audit_entry("invoice_uploaded", user, {"pdf_id": pdf_record["id"]})
    audit2 = _make_audit_entry("invoice_extracted", user, {
        "confidence": extracted.get("confidence"),
        "fields": {k: extracted.get(k) for k in (
            "invoice_number", "invoice_date", "invoice_total",
            "invoice_customer", "invoice_nif", "registration_plate"
        )},
    })
    await db.assistencias.update_one(
        {"id": record_id},
        {"$set": {
            "invoice_pdf": pdf_record,
            "invoice_extracted": extracted,
            "status": AssistenciaStatus.FATURA_ANALISADA.value,
        }, "$push": {"audit_logs": {"$each": [audit, audit2]}}},
    )
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def confirm_invoice(record_id: str, fields: dict, user: dict) -> Optional[dict]:
    """Office confirms (and possibly corrects) extracted invoice fields."""
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    audit_entries = []
    extracted = rec.get("invoice_extracted") or {}
    for k in ("invoice_number", "invoice_date", "invoice_total",
              "invoice_customer", "invoice_nif"):
        new_val = fields.get(k)
        if extracted.get(k) is not None and new_val != extracted.get(k):
            audit_entries.append(_make_audit_entry(
                "invoice_field_corrected", user,
                {"field": k, "ai_value": extracted.get(k), "confirmed_value": new_val},
            ))
    audit_entries.append(_make_audit_entry("invoice_confirmed", user))
    update_set = {
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "invoice_total": fields.get("invoice_total"),
        "invoice_customer": fields.get("invoice_customer"),
        "invoice_nif": fields.get("invoice_nif"),
        "billed_by": user.get("id"),
        "billed_at": _now_iso(),
        "status": AssistenciaStatus.FATURA_CONFIRMADA.value,
    }
    await db.assistencias.update_one(
        {"id": record_id},
        {"$set": update_set, "$push": {"audit_logs": {"$each": audit_entries}}},
    )
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def send_invoice_to_employee(record_id: str, user: dict) -> Optional[dict]:
    """Auto-send the invoice PDF back to the employee via Telegram."""
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    if not rec.get("invoice_pdf"):
        return {"error": "Sem PDF de fatura anexado"}
    chat_id = rec.get("telegram_chat_id")
    if not chat_id:
        return {"error": "Funcionário não tem chat Telegram associado"}
    pdf_bytes = await get_file_bytes(rec["invoice_pdf"])
    if not pdf_bytes:
        return {"error": "Falha ao recuperar PDF da fatura"}
    caption = (
        "🧾 <b>Fatura emitida com sucesso</b>\n"
        f"<b>Nº:</b> {rec.get('invoice_number') or '—'}\n"
        f"<b>Total:</b> {rec.get('invoice_total'):.2f} €" if rec.get('invoice_total') else
        f"<b>Nº:</b> {rec.get('invoice_number') or '—'}"
    )
    filename = f"Fatura_{rec.get('invoice_number') or rec['id'][:8]}.pdf"
    ok = await bot_api.send_document(chat_id, pdf_bytes, filename, caption)
    if not ok:
        return {"error": "Falha a enviar pelo Telegram"}
    # Inline button for delivery confirmation
    kb = {"inline_keyboard": [
        [{"text": "✅ Entreguei ao cliente", "callback_data": f"delivered:{record_id}"}]
    ]}
    await bot_api.send_message(
        chat_id,
        "Quando entregar a fatura ao cliente, confirme aqui:",
        reply_markup=kb,
    )
    audit = _make_audit_entry("invoice_sent_to_employee", user)
    await db.assistencias.update_one(
        {"id": record_id},
        {"$set": {"status": AssistenciaStatus.ENVIADA_FUNCIONARIO.value},
         "$push": {"audit_logs": audit}},
    )
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def confirm_delivery(record_id: str, user: dict) -> Optional[dict]:
    """Office-side manual delivery confirmation (mirrors bot button)."""
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    audit = _make_audit_entry("delivery_confirmed", user)
    await db.assistencias.update_one(
        {"id": record_id},
        {"$set": {
            "status": AssistenciaStatus.FATURADA_CONCLUIDA.value,
            "delivery_confirmed_at": _now_iso(),
        }, "$push": {"audit_logs": audit}},
    )
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


async def mark_non_billable(record_id: str, reason_code: str, internal_note: str, user: dict) -> Optional[dict]:
    rec = await db.assistencias.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        return None
    valid = {c for c, _ in NON_BILLABLE_REASONS}
    if reason_code not in valid:
        return {"error": "Motivo inválido"}
    audit = _make_audit_entry("marked_non_billable", user, {
        "reason": reason_code, "internal_note": internal_note,
    })
    await db.assistencias.update_one(
        {"id": record_id},
        {"$set": {
            "status": AssistenciaStatus.NAO_FATURAVEL.value,
            "non_billable_reason": reason_code,
            "internal_note": internal_note,
            "non_billable_approved_by": user.get("id"),
        }, "$push": {"audit_logs": audit}},
    )
    return await db.assistencias.find_one({"id": record_id}, {"_id": 0})


# ============== Authorized employees CRUD ==============
async def list_bot_users() -> list:
    return await db.assistencias_bot_users.find({}, {"_id": 0}).to_list(500)


async def add_bot_user(telegram_user_id: int, user_id: str, by: dict) -> dict:
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise ValueError("Utilizador não encontrado")
    record = {
        "id": str(uuid.uuid4()),
        "telegram_user_id": int(telegram_user_id),
        "user_id": user_id,
        "user_name": user.get("name"),
        "active": True,
        "added_at": _now_iso(),
        "added_by": by.get("id"),
    }
    await db.assistencias_bot_users.update_one(
        {"telegram_user_id": int(telegram_user_id)},
        {"$set": record},
        upsert=True,
    )
    return record


async def remove_bot_user(telegram_user_id: int) -> bool:
    res = await db.assistencias_bot_users.delete_one(
        {"telegram_user_id": int(telegram_user_id)}
    )
    return res.deleted_count > 0
