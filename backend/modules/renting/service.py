"""Renting module — service layer (Telegram bot flow, OCR, photo storage)."""
import os
import re
import json
import uuid
import base64
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import httpx

from db import db
from .models import (
    RentingStatus, WHEEL_POSITIONS, WHEEL_LABELS, SERVICE_TYPES,
    STATE_IDLE, STATE_WAIT_DRIVER_NAME, STATE_WAIT_DRIVER_PHONE,
    STATE_WAIT_RENTING_COMPANY, STATE_WAIT_PLATE_PHOTO, STATE_CONFIRM_PLATE,
    STATE_EDIT_PLATE, STATE_WAIT_KM_PHOTO, STATE_CONFIRM_KM, STATE_EDIT_KM,
    STATE_WHEEL_PHOTO_FULL, STATE_WHEEL_PHOTO_DOT, STATE_WHEEL_PHOTO_TREAD,
    STATE_CONFIRM_WHEEL, STATE_EDIT_WHEEL, STATE_WAIT_SERVICE,
    STATE_WAIT_OBSERVATIONS, STATE_COLLECT_OBS_TEXT, STATE_COLLECT_OBS_AUDIO,
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_RENTING_BOT_TOKEN", "")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
TELEGRAM_API = "https://api.telegram.org/bot"

MAX_PHOTO_SIZE_MB = 5
MAX_AUDIO_DURATION_SEC = 120
IMAGE_MAX_WIDTH = 1400
IMAGE_QUALITY = 80
INACTIVITY_TIMEOUT_SEC = 1800  # 30 minutes — drafts kept for resume

# Per-chat conversation state
_states = {}


# ============== TELEGRAM API ==============
async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> bool:
    if not BOT_TOKEN:
        logger.error("[RENTING_BOT] TELEGRAM_RENTING_BOT_TOKEN not configured")
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage", json=payload)
            if r.status_code != 200:
                logger.error(f"[RENTING_BOT] sendMessage failed: {r.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[RENTING_BOT] sendMessage error: {e}")
        return False


async def download_telegram_photo(file_id: str) -> Optional[bytes]:
    if not BOT_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{TELEGRAM_API}{BOT_TOKEN}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                return None
            file_path = r.json().get("result", {}).get("file_path")
            if not file_path:
                return None
            r2 = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}")
            if r2.status_code == 200:
                return r2.content
    except Exception as e:
        logger.error(f"[RENTING_BOT] download photo error: {e}")
    return None


async def download_telegram_file(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    if not BOT_TOKEN:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{TELEGRAM_API}{BOT_TOKEN}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                return None, None
            file_path = r.json().get("result", {}).get("file_path")
            if not file_path:
                return None, None
            ext = file_path.split(".")[-1].lower() if "." in file_path else "bin"
            r2 = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}")
            if r2.status_code == 200:
                return r2.content, ext
    except Exception as e:
        logger.error(f"[RENTING_BOT] download file error: {e}")
    return None, None


# ============== IMAGE PROCESSING ==============
def _process_image(image_bytes: bytes) -> bytes:
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width > IMAGE_MAX_WIDTH:
            ratio = IMAGE_MAX_WIDTH / img.width
            img = img.resize((IMAGE_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=IMAGE_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[RENTING_IMG] process failed: {e}")
        return image_bytes


async def store_photo(image_bytes: bytes, prefix: str, telegram_file_id: str = None) -> dict:
    image_bytes = _process_image(image_bytes)
    photo_id = str(uuid.uuid4())
    record = {
        "id": photo_id,
        "filename": f"{photo_id}.jpg",
        "file_type": "image/jpeg",
        "file_size": len(image_bytes),
        "storage_path": None,
        "telegram_file_id": telegram_file_id,
        "base64_data": None,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from services.storage_service import put_object
        path = f"renting/{prefix}/{photo_id}.jpg"
        put_object(path, image_bytes, "image/jpeg")
        record["storage_path"] = path
        return record
    except Exception as e:
        logger.warning(f"[RENTING_STORAGE] Object Storage failed: {e}")
    if len(image_bytes) < 5 * 1024 * 1024:
        record["base64_data"] = base64.b64encode(image_bytes).decode("utf-8")
    return record


async def store_audio(audio_bytes: bytes, ext: str, telegram_file_id: str = None) -> dict:
    audio_id = str(uuid.uuid4())
    ext = ext or "ogg"
    content_type = f"audio/{ext}" if ext in ("ogg", "mp3", "m4a", "wav", "webm") else "audio/ogg"
    record = {
        "id": audio_id,
        "filename": f"{audio_id}.{ext}",
        "file_type": content_type,
        "file_size": len(audio_bytes),
        "storage_path": None,
        "telegram_file_id": telegram_file_id,
        "base64_data": None,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from services.storage_service import put_object
        path = f"renting/audio/{audio_id}.{ext}"
        put_object(path, audio_bytes, content_type)
        record["storage_path"] = path
        return record
    except Exception as e:
        logger.warning(f"[RENTING_STORAGE] Audio storage failed: {e}")
    if len(audio_bytes) < 5 * 1024 * 1024:
        record["base64_data"] = base64.b64encode(audio_bytes).decode("utf-8")
    return record


# ============== AI / OCR ==============
async def _llm_extract(image_bytes: bytes, prompt: str) -> Optional[dict]:
    """Generic GPT-5.2 Vision JSON extractor."""
    if not EMERGENT_LLM_KEY:
        logger.warning("[RENTING_AI] No EMERGENT_LLM_KEY")
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"renting-{uuid.uuid4().hex[:8]}",
            system_message="Extrais dados técnicos de imagens de oficina. Responde APENAS JSON válido."
        ).with_model("openai", "gpt-5.2")
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_base64)])),
            timeout=20
        )
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        return json.loads(text)
    except Exception as e:
        logger.error(f"[RENTING_AI] extract error: {e}")
        return None


async def ocr_plate(image_bytes: bytes) -> Optional[str]:
    data = await _llm_extract(image_bytes, """Extrai a matrícula da viatura visível nesta imagem.

JSON:
{"license_plate": "XX-XX-XX ou null"}

Regras:
- Formato português (ex: AA-00-AA, 00-AA-00)
- Devolve null se ilegível
- Devolve APENAS JSON""")
    return (data or {}).get("license_plate")


async def ocr_km(image_bytes: bytes) -> Optional[int]:
    data = await _llm_extract(image_bytes, """Extrai a quilometragem visível no painel/odómetro nesta imagem.

JSON:
{"km": 123456 ou null}

Regras:
- Apenas dígitos (sem separadores)
- null se ilegível
- Devolve APENAS JSON""")
    val = (data or {}).get("km")
    try:
        return int(val) if val is not None else None
    except Exception:
        return None


async def extract_tire_data(photo_full: bytes, photo_dot: bytes, photo_tread: bytes) -> dict:
    """Extract tire technical data from 3 photos. Returns dict (any field may be None)."""
    result = {"size": None, "brand": None, "model": None, "load_speed": None, "dot": None, "tread_mm": None}

    # Full tire photo: extract size + brand
    d1 = await _llm_extract(photo_full, """Analisa este pneu de viatura. Extrai dados visíveis no flanco.

JSON:
{
  "size": "ex: 205/55 R16 ou null",
  "brand": "ex: Michelin / Continental / null",
  "model": "ex: Primacy 4 / null",
  "load_speed": "ex: 91V / null"
}

Devolve APENAS JSON. null se ilegível.""")
    if d1:
        for k in ("size", "brand", "model", "load_speed"):
            if d1.get(k):
                result[k] = d1[k]

    # DOT photo
    d2 = await _llm_extract(photo_dot, """Extrai o código DOT (4 dígitos finais que indicam semana e ano).

JSON:
{"dot": "ex: 2523 ou null"}

Devolve APENAS JSON. null se ilegível.""")
    if d2 and d2.get("dot"):
        result["dot"] = d2["dot"]

    # Tread depth photo
    d3 = await _llm_extract(photo_tread, """Lê o valor de profundidade do piso (em mm) no medidor presente na imagem.

JSON:
{"tread_mm": 5.5 ou null}

Devolve APENAS JSON. null se ilegível.""")
    if d3:
        val = d3.get("tread_mm")
        try:
            result["tread_mm"] = float(val) if val is not None else None
        except Exception:
            pass

    return result


# ============== STATE HELPERS ==============
def _get_state(chat_id: int) -> dict:
    if chat_id not in _states:
        _states[chat_id] = {
            "state": STATE_IDLE,
            "draft_id": None,
            "wheel_index": 0,
            "user_info": {},
            "last_activity": datetime.now(timezone.utc).timestamp(),
            "watchdog_task": None,
        }
    return _states[chat_id]


def _reset(chat_id: int):
    s = _states.get(chat_id)
    if s:
        t = s.get("watchdog_task")
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if t and not t.done() and t is not current:
            t.cancel()
    _states[chat_id] = {
        "state": STATE_IDLE,
        "draft_id": None,
        "wheel_index": 0,
        "user_info": {},
        "last_activity": datetime.now(timezone.utc).timestamp(),
        "watchdog_task": None,
    }


async def _watchdog(chat_id: int):
    try:
        await asyncio.sleep(INACTIVITY_TIMEOUT_SEC)
    except asyncio.CancelledError:
        return
    s = _states.get(chat_id)
    if not s or s.get("state") == STATE_IDLE:
        return
    await send_message(chat_id, "⏱️ Sessão pausada por inatividade. Use /retomar para continuar (em breve) ou /novo_renting para começar de novo.")
    _reset(chat_id)


def _arm_watchdog(chat_id: int):
    s = _get_state(chat_id)
    t = s.get("watchdog_task")
    try:
        current = asyncio.current_task()
    except RuntimeError:
        current = None
    if t and not t.done() and t is not current:
        t.cancel()
    if s["state"] == STATE_IDLE:
        s["watchdog_task"] = None
        return
    s["watchdog_task"] = asyncio.create_task(_watchdog(chat_id))


def _transition(chat_id: int, new_state: str):
    s = _get_state(chat_id)
    s["state"] = new_state
    s["last_activity"] = datetime.now(timezone.utc).timestamp()
    _arm_watchdog(chat_id)


# ============== DRAFT CRUD ==============
async def _create_draft(chat_id: int, user_info: dict) -> str:
    draft_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": draft_id,
        "status": RentingStatus.DRAFT.value,
        "telegram_chat_id": chat_id,
        "created_by_telegram": user_info,
        "driver_name": None,
        "driver_phone": None,
        "renting_company": None,
        "license_plate": None,
        "license_plate_photo": None,
        "km": None,
        "km_photo": None,
        "wheels": [],  # list of dicts with position + photos + data
        "service_type": None,
        "service_type_label": None,
        "observations": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    await db.renting_records.insert_one(doc)
    return draft_id


async def _update_draft(draft_id: str, updates: dict):
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.renting_records.update_one({"id": draft_id}, {"$set": updates})


async def _get_draft(draft_id: str) -> Optional[dict]:
    return await db.renting_records.find_one({"id": draft_id}, {"_id": 0})


async def _append_wheel(draft_id: str, wheel: dict):
    await db.renting_records.update_one(
        {"id": draft_id},
        {"$push": {"wheels": wheel}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )


async def _update_last_wheel(draft_id: str, updates: dict):
    """Update the last wheel in the array (positional $)."""
    draft = await _get_draft(draft_id)
    if not draft or not draft.get("wheels"):
        return
    idx = len(draft["wheels"]) - 1
    set_doc = {f"wheels.{idx}.{k}": v for k, v in updates.items()}
    set_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.renting_records.update_one({"id": draft_id}, {"$set": set_doc})


# ============== TELEGRAM FLOW ==============
async def start_new_session(chat_id: int, user_info: dict):
    """Handle /novo_renting command."""
    _reset(chat_id)
    s = _get_state(chat_id)
    s["user_info"] = user_info
    draft_id = await _create_draft(chat_id, user_info)
    s["draft_id"] = draft_id
    _transition(chat_id, STATE_WAIT_DRIVER_NAME)
    await send_message(
        chat_id,
        "🚗 <b>Novo Renting</b>\n\nVamos começar.\n\n1️⃣ Qual é o <b>nome do condutor</b>?"
    )


async def cancel_session(chat_id: int):
    s = _get_state(chat_id)
    draft_id = s.get("draft_id")
    if draft_id:
        await db.renting_records.delete_one({"id": draft_id, "status": RentingStatus.DRAFT.value})
    _reset(chat_id)
    await send_message(chat_id, "❌ Sessão cancelada. Use /novo_renting para começar de novo.")


def _wheel_progress_text(wheels_done: int) -> str:
    icons = []
    for i, pos in enumerate(WHEEL_POSITIONS):
        icon = "✓" if i < wheels_done else " "
        icons.append(f"[{icon}] {pos}")
    return "  ".join(icons)


async def handle_text(chat_id: int, user_info: dict, text: str):
    s = _get_state(chat_id)
    s["user_info"] = user_info
    state = s["state"]
    draft_id = s.get("draft_id")

    if state == STATE_WAIT_DRIVER_NAME:
        await _update_draft(draft_id, {"driver_name": text.strip()})
        _transition(chat_id, STATE_WAIT_DRIVER_PHONE)
        await send_message(chat_id, "2️⃣ Qual é o <b>telefone do condutor</b>?")
        return

    if state == STATE_WAIT_DRIVER_PHONE:
        await _update_draft(draft_id, {"driver_phone": text.strip()})
        _transition(chat_id, STATE_WAIT_RENTING_COMPANY)
        await send_message(chat_id, "3️⃣ Qual é a <b>empresa de renting</b>? (ex: ALD, Arval, LeasePlan...)")
        return

    if state == STATE_WAIT_RENTING_COMPANY:
        await _update_draft(draft_id, {"renting_company": text.strip()})
        _transition(chat_id, STATE_WAIT_PLATE_PHOTO)
        await send_message(chat_id, "4️⃣ Envie a <b>foto da matrícula</b> da viatura.")
        return

    if state == STATE_EDIT_PLATE:
        await _update_draft(draft_id, {"license_plate": text.strip().upper()})
        _transition(chat_id, STATE_CONFIRM_PLATE)
        await _ask_confirm_plate(chat_id, text.strip().upper())
        return

    if state == STATE_EDIT_KM:
        try:
            km = int(re.sub(r'\D', '', text))
            await _update_draft(draft_id, {"km": km})
            _transition(chat_id, STATE_CONFIRM_KM)
            await _ask_confirm_km(chat_id, km)
        except Exception:
            await send_message(chat_id, "⚠️ Por favor envie apenas números (ex: 45230).")
        return

    if state == STATE_EDIT_WHEEL:
        await _save_wheel_edit_text(chat_id, text)
        return

    if state == STATE_COLLECT_OBS_TEXT:
        await _save_observations(chat_id, comment_type="text", text=text[:2000])
        return

    if state == STATE_COLLECT_OBS_AUDIO:
        await send_message(chat_id, "A aguardar áudio. Envie uma mensagem de voz, ou /cancelar.")
        return

    # Unknown text in other states
    await send_message(chat_id, "Por favor envie o pedido conforme indicado, ou use /cancelar.")


async def handle_photo(chat_id: int, user_info: dict, photo: dict):
    s = _get_state(chat_id)
    s["user_info"] = user_info
    state = s["state"]
    draft_id = s.get("draft_id")

    image_bytes = await download_telegram_photo(photo["file_id"])
    if not image_bytes:
        await send_message(chat_id, "⚠️ Não consegui baixar a foto. Tente novamente.")
        return

    if state == STATE_WAIT_PLATE_PHOTO:
        photo_rec = await store_photo(image_bytes, "plates", photo["file_id"])
        await send_message(chat_id, "🔎 A ler a matrícula...")
        plate = await ocr_plate(image_bytes)
        await _update_draft(draft_id, {"license_plate_photo": photo_rec, "license_plate": plate})
        _transition(chat_id, STATE_CONFIRM_PLATE)
        await _ask_confirm_plate(chat_id, plate)
        return

    if state == STATE_WAIT_KM_PHOTO:
        photo_rec = await store_photo(image_bytes, "km", photo["file_id"])
        await send_message(chat_id, "🔎 A ler a quilometragem...")
        km = await ocr_km(image_bytes)
        await _update_draft(draft_id, {"km_photo": photo_rec, "km": km})
        _transition(chat_id, STATE_CONFIRM_KM)
        await _ask_confirm_km(chat_id, km)
        return

    if state == STATE_WHEEL_PHOTO_FULL:
        photo_rec = await store_photo(image_bytes, f"wheels/{s['wheel_index']}/full", photo["file_id"])
        pos = WHEEL_POSITIONS[s["wheel_index"]]
        await _append_wheel(draft_id, {
            "position": pos,
            "label": WHEEL_LABELS[pos],
            "photo_full": photo_rec,
            "photo_dot": None,
            "photo_tread": None,
            "data": {},
            "_full_bytes_size": len(image_bytes),
        })
        # Cache bytes in state to avoid re-downloading for AI extraction
        s["_full_bytes"] = image_bytes
        _transition(chat_id, STATE_WHEEL_PHOTO_DOT)
        await send_message(chat_id, f"📸 Agora envie a <b>foto do DOT</b> ({WHEEL_LABELS[pos]}).")
        return

    if state == STATE_WHEEL_PHOTO_DOT:
        photo_rec = await store_photo(image_bytes, f"wheels/{s['wheel_index']}/dot", photo["file_id"])
        await _update_last_wheel(draft_id, {"photo_dot": photo_rec})
        s["_dot_bytes"] = image_bytes
        pos = WHEEL_POSITIONS[s["wheel_index"]]
        _transition(chat_id, STATE_WHEEL_PHOTO_TREAD)
        await send_message(chat_id, f"📏 Agora envie a <b>foto do piso com medidor</b> ({WHEEL_LABELS[pos]}).")
        return

    if state == STATE_WHEEL_PHOTO_TREAD:
        photo_rec = await store_photo(image_bytes, f"wheels/{s['wheel_index']}/tread", photo["file_id"])
        await _update_last_wheel(draft_id, {"photo_tread": photo_rec})
        pos = WHEEL_POSITIONS[s["wheel_index"]]
        await send_message(chat_id, f"🔎 A extrair dados do pneu {WHEEL_LABELS[pos]}...")
        # Run AI extraction
        data = await extract_tire_data(
            s.get("_full_bytes", b""),
            s.get("_dot_bytes", b""),
            image_bytes
        )
        await _update_last_wheel(draft_id, {"data": data})
        s["_full_bytes"] = None
        s["_dot_bytes"] = None
        _transition(chat_id, STATE_CONFIRM_WHEEL)
        await _ask_confirm_wheel(chat_id, pos, data)
        return

    await send_message(chat_id, "Não estava à espera de uma foto neste passo. Use os botões ou /cancelar.")


async def handle_voice(chat_id: int, user_info: dict, voice: dict):
    s = _get_state(chat_id)
    if s["state"] != STATE_COLLECT_OBS_AUDIO:
        await send_message(chat_id, "Áudios só são aceites no passo de observações.")
        return
    duration = voice.get("duration", 0)
    if duration > MAX_AUDIO_DURATION_SEC:
        await send_message(chat_id, f"⚠️ Áudio demasiado longo (máx {MAX_AUDIO_DURATION_SEC}s).")
        return
    audio_bytes, ext = await download_telegram_file(voice["file_id"])
    if not audio_bytes:
        await send_message(chat_id, "⚠️ Não consegui baixar o áudio. Tente novamente.")
        return
    audio_rec = await store_audio(audio_bytes, ext or "ogg", voice["file_id"])
    # Try transcription
    transcript = None
    status = "not_applicable"
    try:
        from modules.telegram.service import transcribe_audio_with_whisper
        transcript = await transcribe_audio_with_whisper(audio_bytes, ext or "ogg")
        status = "success" if transcript else "failed"
    except Exception as e:
        logger.warning(f"[RENTING_AUDIO] Whisper error: {e}")
        status = "failed"
    await _save_observations(chat_id, comment_type="audio", text=transcript or "", audio=audio_rec, transcription_status=status)


# ============== PROMPT / CONFIRMATION HELPERS ==============
async def _ask_confirm_plate(chat_id: int, plate: Optional[str]):
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    text = (
        f"✅ Matrícula extraída: <b>{plate}</b>\n\nEstá correta?"
        if plate
        else "⚠️ Não consegui ler a matrícula. Escreva-a manualmente."
    )
    if plate:
        await send_message(chat_id, text, reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"plate_ok:{draft_id}"},
            {"text": "✏️ Corrigir", "callback_data": f"plate_edit:{draft_id}"},
        ]]})
    else:
        _transition(chat_id, STATE_EDIT_PLATE)


async def _ask_confirm_km(chat_id: int, km: Optional[int]):
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    if km:
        await send_message(chat_id, f"✅ KM extraído: <b>{km:,}</b>\n\nEstá correto?".replace(",", " "), reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"km_ok:{draft_id}"},
            {"text": "✏️ Corrigir", "callback_data": f"km_edit:{draft_id}"},
        ]]})
    else:
        await send_message(chat_id, "⚠️ Não consegui ler os KM. Escreva manualmente (apenas dígitos):")
        _transition(chat_id, STATE_EDIT_KM)


async def _start_wheel_collection(chat_id: int):
    s = _get_state(chat_id)
    s["wheel_index"] = 0
    await _prompt_wheel_full(chat_id)


async def _prompt_wheel_full(chat_id: int):
    s = _get_state(chat_id)
    progress = _wheel_progress_text(s["wheel_index"])
    pos = WHEEL_POSITIONS[s["wheel_index"]]
    _transition(chat_id, STATE_WHEEL_PHOTO_FULL)
    await send_message(
        chat_id,
        f"🛞 <b>Roda {WHEEL_LABELS[pos]}</b>\n\nProgresso: {progress}\n\n"
        f"📸 Envie a <b>foto completa do pneu</b> (mostrar flanco com medida e marca)."
    )


async def _ask_confirm_wheel(chat_id: int, pos: str, data: dict):
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    rows = [
        f"• Medida: <b>{data.get('size') or '—'}</b>",
        f"• Marca/Modelo: <b>{(data.get('brand') or '—')} {data.get('model') or ''}</b>".strip(),
        f"• Índice C/V: <b>{data.get('load_speed') or '—'}</b>",
        f"• DOT: <b>{data.get('dot') or '—'}</b>",
        f"• Piso: <b>{data.get('tread_mm') if data.get('tread_mm') is not None else '—'} mm</b>",
    ]
    await send_message(
        chat_id,
        f"📋 <b>{WHEEL_LABELS[pos]}</b> — dados extraídos:\n\n" + "\n".join(rows) + "\n\nEstá correto?",
        reply_markup={"inline_keyboard": [
            [{"text": "✅ Confirmar", "callback_data": f"wheel_ok:{draft_id}"}],
            [{"text": "✏️ Editar manualmente", "callback_data": f"wheel_edit:{draft_id}"}],
            [{"text": "🔁 Repetir fotos", "callback_data": f"wheel_redo:{draft_id}"}],
        ]}
    )


async def _save_wheel_edit_text(chat_id: int, text: str):
    """Parse user-typed wheel data. Expected format: size|brand|model|load_speed|dot|tread_mm separated by |"""
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    parts = [p.strip() for p in text.split("|")]
    keys = ["size", "brand", "model", "load_speed", "dot", "tread_mm"]
    data = {}
    for i, k in enumerate(keys):
        if i < len(parts) and parts[i]:
            if k == "tread_mm":
                try:
                    data[k] = float(parts[i].replace(",", "."))
                except Exception:
                    data[k] = None
            else:
                data[k] = parts[i]
    await _update_last_wheel(draft_id, {"data": data})
    pos = WHEEL_POSITIONS[s["wheel_index"]]
    _transition(chat_id, STATE_CONFIRM_WHEEL)
    await _ask_confirm_wheel(chat_id, pos, data)


async def _advance_after_wheel(chat_id: int):
    s = _get_state(chat_id)
    s["wheel_index"] += 1
    if s["wheel_index"] >= len(WHEEL_POSITIONS):
        # All wheels done — ask for service
        _transition(chat_id, STATE_WAIT_SERVICE)
        draft_id = s["draft_id"]
        rows = [[{"text": lbl, "callback_data": f"svc:{key}:{draft_id}"}] for key, lbl in SERVICE_TYPES]
        await send_message(
            chat_id,
            "✅ Todas as rodas registadas!\n\nQual o <b>serviço a executar</b>?",
            reply_markup={"inline_keyboard": rows}
        )
    else:
        await _prompt_wheel_full(chat_id)


async def _ask_observations_choice(chat_id: int):
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    _transition(chat_id, STATE_WAIT_OBSERVATIONS)
    await send_message(
        chat_id,
        "💬 Quer adicionar <b>observações</b>?",
        reply_markup={"inline_keyboard": [
            [{"text": "📝 Texto", "callback_data": f"obs_text:{draft_id}"}],
            [{"text": "🎤 Áudio", "callback_data": f"obs_audio:{draft_id}"}],
            [{"text": "Sem observações", "callback_data": f"obs_none:{draft_id}"}],
        ]}
    )


async def _save_observations(chat_id: int, comment_type: str, text: str = "", audio: dict = None, transcription_status: str = "not_applicable"):
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    obs = {
        "type": comment_type,
        "text": text or None,
        "audio": audio,
        "transcription_status": transcription_status,
        "internal_only": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _update_draft(draft_id, {"observations": obs})
    await _finalize(chat_id)


async def _finalize(chat_id: int):
    s = _get_state(chat_id)
    draft_id = s["draft_id"]
    now = datetime.now(timezone.utc).isoformat()
    await db.renting_records.update_one(
        {"id": draft_id},
        {"$set": {"status": RentingStatus.COMPLETED.value, "completed_at": now, "updated_at": now}}
    )
    draft = await _get_draft(draft_id)
    plate = draft.get("license_plate") or "—"
    company = draft.get("renting_company") or "—"
    await send_message(
        chat_id,
        f"✅ <b>Registo Renting concluído!</b>\n\n"
        f"Matrícula: <b>{plate}</b>\n"
        f"Renting: {company}\n\n"
        f"Pode consultá-lo no sistema. Use /novo_renting para começar outro."
    )
    _reset(chat_id)


# ============== CALLBACK ROUTER ==============
async def handle_callback(chat_id: int, data: str):
    s = _get_state(chat_id)
    parts = data.split(":")
    action = parts[0]
    draft_id = parts[-1] if len(parts) > 1 else None

    if s.get("draft_id") != draft_id and draft_id:
        # State drifted — silently ignore
        return

    if action == "plate_ok":
        _transition(chat_id, STATE_WAIT_KM_PHOTO)
        await send_message(chat_id, "5️⃣ Agora envie a <b>foto dos quilómetros</b> (painel/odómetro).")
        return

    if action == "plate_edit":
        _transition(chat_id, STATE_EDIT_PLATE)
        await send_message(chat_id, "Escreva a matrícula correta (ex: AA-00-AA):")
        return

    if action == "km_ok":
        await _start_wheel_collection(chat_id)
        return

    if action == "km_edit":
        _transition(chat_id, STATE_EDIT_KM)
        await send_message(chat_id, "Escreva os KM corretos (apenas números):")
        return

    if action == "wheel_ok":
        await _advance_after_wheel(chat_id)
        return

    if action == "wheel_edit":
        _transition(chat_id, STATE_EDIT_WHEEL)
        await send_message(
            chat_id,
            "Envie os dados separados por <b>|</b> nesta ordem:\n\n"
            "<code>medida|marca|modelo|índice|DOT|piso_mm</code>\n\n"
            "Exemplo: <code>205/55 R16|Michelin|Primacy 4|91V|2523|5.5</code>\n\n"
            "Pode deixar campos vazios entre os | se não souber."
        )
        return

    if action == "wheel_redo":
        # Remove the last wheel entry and re-prompt from full photo
        draft = await _get_draft(s["draft_id"])
        if draft and draft.get("wheels"):
            wheels = draft["wheels"][:-1]
            await _update_draft(s["draft_id"], {"wheels": wheels})
        await _prompt_wheel_full(chat_id)
        return

    if action == "svc":
        # data format: svc:<key>:<draft_id>
        if len(parts) >= 3:
            key = parts[1]
            label = dict(SERVICE_TYPES).get(key, key)
            await _update_draft(s["draft_id"], {"service_type": key, "service_type_label": label})
            await _ask_observations_choice(chat_id)
        return

    if action == "obs_text":
        _transition(chat_id, STATE_COLLECT_OBS_TEXT)
        await send_message(chat_id, "Envie o texto das observações (máx 2000 caracteres):")
        return

    if action == "obs_audio":
        _transition(chat_id, STATE_COLLECT_OBS_AUDIO)
        await send_message(chat_id, f"Envie a mensagem de áudio (máx {MAX_AUDIO_DURATION_SEC}s):")
        return

    if action == "obs_none":
        await _save_observations(chat_id, comment_type="none")
        return


# ============== ADMIN CRUD ==============
async def list_records(status: Optional[str] = None, renting_company: Optional[str] = None,
                       search: Optional[str] = None, page: int = 1, page_size: int = 50) -> Tuple[List[dict], int]:
    query = {}
    if status:
        query["status"] = status
    if renting_company:
        query["renting_company"] = renting_company
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [
            {"license_plate": rx},
            {"driver_phone": rx},
            {"driver_name": rx},
            {"renting_company": rx},
        ]
    total = await db.renting_records.count_documents(query)
    skip = (page - 1) * page_size
    items = await db.renting_records.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return items, total


async def get_record(record_id: str) -> Optional[dict]:
    return await db.renting_records.find_one({"id": record_id}, {"_id": 0})


async def update_record(record_id: str, updates: dict) -> Optional[dict]:
    if "id" in updates:
        del updates["id"]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.renting_records.update_one({"id": record_id}, {"$set": updates})
    return await get_record(record_id)


async def delete_record(record_id: str) -> bool:
    r = await db.renting_records.delete_one({"id": record_id})
    return r.deleted_count > 0


async def get_stats() -> dict:
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    rows = await db.renting_records.aggregate(pipeline).to_list(10)
    stats = {"draft": 0, "completed": 0, "total": 0}
    for r in rows:
        s = r["_id"] or "draft"
        if s in stats:
            stats[s] = r["count"]
        stats["total"] += r["count"]
    # Incomplete = drafts that have at least driver_name (started but not finished)
    stats["incomplete"] = await db.renting_records.count_documents({
        "status": "draft",
        "driver_name": {"$ne": None}
    })
    return stats


# ============== WEBHOOK ==============
async def setup_webhook(webhook_url: str) -> dict:
    if not BOT_TOKEN:
        return {"success": False, "error": "TELEGRAM_RENTING_BOT_TOKEN not configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{TELEGRAM_API}{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]}
            )
            return {"success": r.json().get("ok", False), "result": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}
