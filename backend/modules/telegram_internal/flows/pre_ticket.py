"""Pré-ticket — open free-form flow.

User clicks 📋 → bot says "Envia tudo o que tiveres" and accumulates:
- text → texts[]
- photo → attachments[] (downloaded immediately + saved to storage)
- document → attachments[]
- voice/audio → attachments[] + audio_transcripts[]

When user clicks ✅ Criar pré-ticket:
1. Concatenate texts + transcripts → raw_text
2. Run IA extraction (extract_pre_ticket_fields)
3. Optionally analyze first image for OCR hints
4. Insert into `pre_tickets` collection (NEVER `tickets`)
5. Reset state, send summary + dashboard link

ABSOLUTE RULES:
- Never writes to `tickets`
- Never auto-converts
- The dashboard is responsible for validation + conversion
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from db import db
from ..bot_api import send_message, inline_keyboard, download_file
from .. import state as state_mgr
from ..menu import created_record_keyboard, main_menu_markup
from ..logs import log_event
from .. import ai as ai_mod

logger = logging.getLogger(__name__)

FLOW = "pre_ticket"
STEP_COLLECTING = "collecting"
STEP_FINALIZING = "finalizing"

INSTRUCTIONS = (
    "📋 <b>Novo pré-ticket</b>\n\n"
    "Envia tudo o que tiveres sobre o pedido:\n"
    "- texto\n"
    "- áudio (voice)\n"
    "- fotos\n"
    "- documentos\n\n"
    "Podes enviar várias mensagens.\n"
    "Quando terminares, carrega em <b>✅ Criar pré-ticket</b>."
)

ACTION_MARKUP = inline_keyboard([
    [{"text": "✅ Criar pré-ticket", "callback_data": "preticket:finalize"}],
    [{"text": "❌ Cancelar", "callback_data": "menu:cancel"}],
])


def _empty_payload(user_auth: dict) -> dict:
    return {
        "_created_by": user_auth.get("name"),
        "texts": [],
        "attachments": [],
        "audio_transcripts": [],
        "image_hints": [],
    }


async def start(chat_id: int, telegram_user_id: int, user_auth: dict) -> None:
    await state_mgr.start_flow(
        telegram_user_id, chat_id,
        flow=FLOW, initial_step=STEP_COLLECTING,
        initial_payload=_empty_payload(user_auth),
    )
    await send_message(chat_id, INSTRUCTIONS, reply_markup=ACTION_MARKUP)
    await log_event(telegram_user_id, chat_id, "flow_start", FLOW, STEP_COLLECTING, success=True)


async def handle_message(chat_id: int, telegram_user_id: int, text: Optional[str],
                         photo_file_id: Optional[str], state: dict) -> None:
    payload = state.get("temporary_payload") or {}
    step = state.get("current_step")

    # We accept anything during STEP_COLLECTING; during STEP_FINALIZING we ignore
    if step == STEP_FINALIZING:
        await send_message(chat_id, "⏳ A processar o pré-ticket. Aguarda um momento…")
        return

    # If the user sent text, accumulate
    if text:
        texts = list(payload.get("texts") or [])
        texts.append(text.strip())
        await state_mgr.update_state(telegram_user_id, payload_merge={"texts": texts})
        await log_event(telegram_user_id, chat_id, "text_received", FLOW, step,
                        success=True, extra={"len": len(text)})
        await send_message(
            chat_id,
            "✅ Informação recebida. Podes enviar mais informação ou criar o pré-ticket.",
            reply_markup=ACTION_MARKUP,
        )
        return

    if photo_file_id:
        # Photo → download bytes for IA + save metadata
        bytes_ = await download_file(photo_file_id)
        att = {
            "id": str(uuid.uuid4()),
            "kind": "photo",
            "telegram_file_id": photo_file_id,
            "size_bytes": len(bytes_) if bytes_ else None,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        atts = list(payload.get("attachments") or [])
        atts.append(att)
        merge = {"attachments": atts}
        # Best-effort image hint via GPT-4o (does not block on failure)
        hints = list(payload.get("image_hints") or [])
        if bytes_:
            hint = await ai_mod.analyze_image(bytes_)
            if hint:
                hints.append(hint)
                merge["image_hints"] = hints
        await state_mgr.update_state(telegram_user_id, payload_merge=merge)
        await log_event(telegram_user_id, chat_id, "photo_received", FLOW, step,
                        success=True, extra={"file_id": photo_file_id})
        await send_message(
            chat_id,
            "📎 Anexo recebido. Podes enviar mais informação ou criar o pré-ticket.",
            reply_markup=ACTION_MARKUP,
        )
        return

    # Fallback (no text and no photo handled here — voice/doc handled in routes via raw)
    await send_message(chat_id, "ℹ️ Envia texto, foto, áudio ou documento.")


async def handle_attachment_raw(chat_id: int, telegram_user_id: int, message: dict, state: dict) -> bool:
    """Handle voice/audio/document messages that arrive in the raw Telegram message.

    Returns True if it consumed the message, False otherwise (so caller can keep dispatching).
    """
    if state.get("current_step") != STEP_COLLECTING:
        return False
    payload = state.get("temporary_payload") or {}

    voice = message.get("voice")
    audio = message.get("audio")
    document = message.get("document")

    if voice or audio:
        media = voice or audio
        file_id = media.get("file_id")
        ext = "ogg" if voice else (media.get("mime_type", "").split("/")[-1] or "mp3")
        att = {
            "id": str(uuid.uuid4()),
            "kind": "voice" if voice else "audio",
            "telegram_file_id": file_id,
            "mime_type": media.get("mime_type"),
            "duration_sec": media.get("duration"),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        atts = list(payload.get("attachments") or [])
        atts.append(att)
        merge = {"attachments": atts}

        # Try Whisper transcription
        transcripts = list(payload.get("audio_transcripts") or [])
        bytes_ = await download_file(file_id)
        transcript = await ai_mod.transcribe_audio(bytes_, ext) if bytes_ else None

        if transcript:
            transcripts.append(transcript)
            att["transcript"] = transcript
            merge["audio_transcripts"] = transcripts
            await state_mgr.update_state(telegram_user_id, payload_merge=merge)
            await log_event(telegram_user_id, chat_id, "audio_transcribed", FLOW,
                            state.get("current_step"), success=True,
                            extra={"file_id": file_id, "len": len(transcript)})
            await send_message(
                chat_id,
                "🎙️ Áudio recebido e transcrito. Podes enviar mais informação ou criar o pré-ticket.",
                reply_markup=ACTION_MARKUP,
            )
        else:
            await state_mgr.update_state(telegram_user_id, payload_merge=merge)
            await log_event(telegram_user_id, chat_id, "audio_received_no_transcript", FLOW,
                            state.get("current_step"), success=False,
                            error="whisper_failed", extra={"file_id": file_id})
            await send_message(
                chat_id,
                "🎙️ Áudio recebido, mas não consegui transcrever automaticamente. "
                "O ficheiro ficará anexado ao pré-ticket.",
                reply_markup=ACTION_MARKUP,
            )
        return True

    if document:
        att = {
            "id": str(uuid.uuid4()),
            "kind": "document",
            "telegram_file_id": document.get("file_id"),
            "file_name": document.get("file_name"),
            "mime_type": document.get("mime_type"),
            "size_bytes": document.get("file_size"),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        atts = list(payload.get("attachments") or [])
        atts.append(att)
        await state_mgr.update_state(telegram_user_id, payload_merge={"attachments": atts})
        await log_event(telegram_user_id, chat_id, "document_received", FLOW,
                        state.get("current_step"), success=True,
                        extra={"file_id": document.get("file_id")})
        await send_message(
            chat_id,
            "📎 Anexo recebido. Podes enviar mais informação ou criar o pré-ticket.",
            reply_markup=ACTION_MARKUP,
        )
        return True

    return False


async def handle_callback(chat_id: int, telegram_user_id: int, data: str,
                          user_auth: dict, state: dict) -> None:
    if data == "preticket:finalize":
        await _finalize(chat_id, telegram_user_id, user_auth, state)


def _build_reference() -> str:
    now = datetime.now(timezone.utc)
    return f"PT{now.strftime('%Y%m%d')}{uuid.uuid4().hex[:5].upper()}"


async def _finalize(chat_id: int, telegram_user_id: int, user_auth: dict, state: dict) -> None:
    payload = state.get("temporary_payload") or {}

    # Need at least one piece of information to create a pre-ticket
    texts = payload.get("texts") or []
    transcripts = payload.get("audio_transcripts") or []
    attachments = payload.get("attachments") or []
    image_hints = payload.get("image_hints") or []

    if not texts and not transcripts and not attachments:
        await send_message(
            chat_id,
            "⚠️ Ainda não enviaste nada. Manda texto, áudio, foto ou documento primeiro.",
            reply_markup=ACTION_MARKUP,
        )
        return

    await state_mgr.update_state(telegram_user_id, current_step=STEP_FINALIZING)

    raw_text_parts = []
    if texts:
        raw_text_parts.append("\n".join(texts))
    if transcripts:
        raw_text_parts.append("\n".join(f"[áudio] {t}" for t in transcripts))
    raw_text = "\n\n".join(raw_text_parts)

    # IA extraction (never raises)
    try:
        extracted = await ai_mod.extract_pre_ticket_fields(raw_text, image_hints=image_hints)
    except Exception as e:
        extracted = {k: None for k in ai_mod.ALL_FIELDS}
        extracted["missing_fields"] = list(ai_mod.ALL_FIELDS)
        extracted["confidence_score"] = 0.0
        await log_event(telegram_user_id, chat_id, "ai_error", FLOW, STEP_FINALIZING,
                        success=False, error=str(e))

    reference = _build_reference()

    # Normalize attachments into a stable structured shape that the dashboard
    # frontend can render directly. The proxy endpoint uses `telegram_file_id`.
    normalized_attachments = []
    for a in attachments or []:
        if not isinstance(a, dict):
            continue
        normalized_attachments.append({
            "id": a.get("id") or str(uuid.uuid4()),
            "kind": a.get("kind") or "document",
            "telegram_file_id": a.get("telegram_file_id"),
            "url": None,  # served via /api/intake/{id}/attachments/{aid} proxy
            "filename": a.get("file_name") or a.get("filename"),
            "mime_type": a.get("mime_type"),
            "size": a.get("size_bytes") or a.get("size"),
            "duration_sec": a.get("duration_sec"),
            "transcript": a.get("transcript"),
            "created_at": a.get("received_at") or datetime.now(timezone.utc).isoformat(),
        })

    # === Map open-flow payload → intake_requests (unified module) ===
    # `sender_*` represents the CUSTOMER (extracted by AI). `created_by_name`
    # represents the INTERNAL EMPLOYEE that submitted via the Telegram bot.
    try:
        from modules.intake.service import create_intake_request as create_intake
        from modules.intake.models import IntakeSourceType

        ai_customer_name = (extracted.get("customer_name") or "").strip() if extracted else ""
        ai_customer_phone = (extracted.get("customer_phone") or "").strip() if extracted else ""

        intake_doc = await create_intake(
            source="telegram",
            source_type=IntakeSourceType.TELEGRAM_INTERNAL_BOT,
            sender_name=ai_customer_name,           # may be "" → frontend shows "—" + missing_fields
            sender_contact=ai_customer_phone,       # may be ""
            raw_text=raw_text,
            attachments=normalized_attachments,
            source_bot="PDPV_INTERNAL_BOT",
            origin_channel="TELEGRAM_INTERNAL_BOT",
            reference=reference,
            created_by_name=user_auth.get("name"),
            telegram_user_id=telegram_user_id,
            telegram_chat_id=chat_id,
            texts=texts,
            audio_transcripts=transcripts,
            image_hints=image_hints,
            ai_extracted=extracted,
        )
        intake_id = intake_doc["id"]
    except Exception as e:
        await log_event(telegram_user_id, chat_id, "create_error", FLOW, STEP_FINALIZING,
                        success=False, error=str(e))
        logger.error("intake create failed: %s", e, exc_info=True)
        await send_message(chat_id, "❌ Erro ao criar pré-ticket. Tenta novamente.")
        return

    await state_mgr.reset_state(telegram_user_id)
    await log_event(telegram_user_id, chat_id, "preticket_created", FLOW, STEP_FINALIZING,
                    success=True, extra={"reference": reference, "id": intake_id,
                                          "collection": "intake_requests"})

    low_confidence = (extracted.get("confidence_score") or 0) < 0.5
    missing = extracted.get("missing_fields") or []

    if low_confidence:
        text = (
            f"⚠️ <b>Pré-ticket criado, mas alguns dados precisam de validação.</b>\n"
            f"Referência: <b>{reference}</b>\n"
        )
        if missing:
            text += f"\nCampos em falta: <i>{', '.join(missing)}</i>"
        text += "\n\nValida e trata na dashboard."
    else:
        text = (
            f"✅ <b>Pré-ticket criado com sucesso.</b>\n"
            f"Referência: <b>{reference}</b>\n\n"
            f"A IA preencheu os dados possíveis.\n"
            f"Valida e trata na dashboard."
        )

    await send_message(
        chat_id, text,
        reply_markup=created_record_keyboard("pre_ticket", f"/intake?focus={intake_id}"),
    )
    await send_message(chat_id, "Pronto para outro pedido?", reply_markup=main_menu_markup(user_auth))
