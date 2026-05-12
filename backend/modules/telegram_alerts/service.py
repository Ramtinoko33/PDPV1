"""
Telegram Alerts Module - Service Layer
Handles: explicit conversation state machine, image processing, alert CRUD,
Telegram bot interaction, optional mechanic note (text or audio).
"""
import os
import re
import json
import uuid
import base64
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple

import httpx

from db import db
from .models import AlertStatus

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_ALERTS_BOT_TOKEN", "")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
TELEGRAM_API = "https://api.telegram.org/bot"

BUFFER_TIMEOUT_SECONDS = 10
PHOTO_COLLECTION_TIMEOUT = 10
NOTE_COLLECTION_TIMEOUT = 60
MAX_MESSAGES_PER_MIN = 10
MAX_PHOTO_SIZE_MB = 3
MAX_PROBLEM_PHOTOS = 4
MAX_AUDIO_DURATION_SEC = 60
MAX_NOTE_TEXT_LEN = 1000
IMAGE_MAX_WIDTH = 1200
IMAGE_QUALITY = 75

# Conversation states (per chat_id)
STATE_IDLE = "IDLE"
STATE_WAIT_PROBLEM_PHOTO_CONF = "WAITING_PROBLEM_PHOTO_CONFIRMATION"
STATE_COLLECTING_PROBLEM_IMAGES = "COLLECTING_PROBLEM_IMAGES"
STATE_WAIT_NOTE_CONF = "WAITING_MECHANIC_NOTE_CONFIRMATION"
STATE_COLLECTING_NOTE = "COLLECTING_MECHANIC_NOTE"
STATE_WAIT_ASSIGNEE = "WAITING_ASSIGNEE_SELECTION"

# Per-chat conversation state.
# Shape: {
#   "state": str,
#   "active_alert_id": str | None,
#   "problem_images_count": int,
#   "timer_task": asyncio.Task | None,
#   "user_info": dict,
#   "last_activity": float,
#   "initial_buffer": {"texts": [str], "photos": [dict]} | None,
# }
_conversation_states = {}

# Rate limiting: {chat_id: [timestamps]}
_rate_limits = {}


# ============== TELEGRAM API HELPERS ==============
async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> bool:
    if not BOT_TOKEN:
        logger.error("[ALERTS_BOT] Bot token not configured")
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage", json=payload)
            if r.status_code != 200:
                logger.error(f"[ALERTS_BOT] sendMessage failed: {r.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[ALERTS_BOT] sendMessage error: {e}")
        return False


async def download_telegram_photo(file_id: str) -> Optional[bytes]:
    if not BOT_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
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
        logger.error(f"[ALERTS_BOT] download photo error: {e}")
    return None


async def download_telegram_file(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Download any Telegram file. Returns (bytes, file_path_extension)."""
    if not BOT_TOKEN:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
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
        logger.error(f"[ALERTS_BOT] download file error: {e}")
    return None, None


async def get_system_users() -> List[dict]:
    """Get active AGENT users with alerts access to show as assignee options."""
    users = await db.users.find(
        {"is_active": {"$ne": False}, "role": "AGENT", "has_alerts_access": True},
        {"_id": 0, "id": 1, "name": 1, "role": 1}
    ).to_list(50)
    return users


async def send_assignee_buttons(chat_id: int):
    """Send inline keyboard with system users as assignee choices."""
    users = await get_system_users()
    if not users:
        await send_message(chat_id, "Nenhum rececionista disponível no sistema.")
        return

    buttons = []
    row = []
    for u in users:
        row.append({"text": u["name"], "callback_data": f"assign:{u['id']}:{u['name']}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await send_message(
        chat_id,
        "Escolha o rececionista para este alerta:",
        reply_markup={"inline_keyboard": buttons}
    )


# ============== RATE LIMITING ==============
def check_rate_limit(chat_id: int) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    if chat_id not in _rate_limits:
        _rate_limits[chat_id] = []
    _rate_limits[chat_id] = [t for t in _rate_limits[chat_id] if now - t < 60]
    if len(_rate_limits[chat_id]) >= MAX_MESSAGES_PER_MIN:
        return False
    _rate_limits[chat_id].append(now)
    return True


# ============== IMAGE ANALYSIS ==============
async def analyze_image(image_bytes: bytes) -> dict:
    """Analyze image using GPT-5.2 Vision via Emergent LLM Key."""
    if not EMERGENT_LLM_KEY:
        logger.warning("[ALERTS_VISION] No EMERGENT_LLM_KEY, skipping analysis")
        return {"success": False, "error": "LLM key not configured"}

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"alert-vision-{uuid.uuid4().hex[:8]}",
            system_message="Extrais dados de imagens de oficina mecânica. Responde APENAS com JSON válido."
        ).with_model("openai", "gpt-5.2")

        prompt = """Analisa esta imagem. É uma captura de ecrã do software CEINOR GENES com alertas?

Se SIM, extrai em JSON:
{
  "is_alert": true,
  "license_plate": "XX-XX-XX ou null",
  "client_name": "nome ou null",
  "items": [{"description": "texto do item"}]
}

Se NÃO:
{"is_alert": false}

Regras:
- Devolve APENAS JSON válido, sem markdown, sem texto extra
- license_plate: formato português (AA-00-AA ou 00-AA-00), null se não visível
- client_name: nome do cliente se visível, null se não
- items: lista de objetos com description (texto de cada item/serviço), lista vazia se nenhum
- NÃO inventes dados"""

        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_base64)])),
            timeout=15
        )

        result_text = response.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)

        extracted = json.loads(result_text)

        if isinstance(extracted.get("items"), list):
            normalized_items = []
            for item in extracted["items"]:
                if isinstance(item, dict):
                    normalized_items.append(item.get("description", str(item)))
                else:
                    normalized_items.append(str(item))
            extracted["items"] = normalized_items

        if extracted.get("is_alert") is False:
            extracted["success"] = False
            extracted["error"] = "Image is not a CEINOR GENES alert"
            extracted["raw_response"] = response[:500]
            return extracted

        extracted["success"] = True
        extracted["raw_response"] = response[:500]
        logger.info(f"[ALERTS_VISION] OK: plate={extracted.get('license_plate')}, items={len(extracted.get('items', []))}")
        return extracted

    except asyncio.TimeoutError:
        logger.warning("[ALERTS_VISION] Timeout (15s)")
        return {"success": False, "error": "Timeout"}
    except json.JSONDecodeError as e:
        logger.error(f"[ALERTS_VISION] JSON parse error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[ALERTS_VISION] Error: {e}")
        return {"success": False, "error": str(e)}


# ============== IMAGE PROCESSING & STORAGE ==============
def _process_image(image_bytes: bytes) -> bytes:
    """Resize, compress, strip EXIF. Returns optimized JPEG bytes."""
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if img.width > IMAGE_MAX_WIDTH:
            ratio = IMAGE_MAX_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((IMAGE_MAX_WIDTH, new_height), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=IMAGE_QUALITY, optimize=True)
        result = buf.getvalue()

        if len(result) > 300 * 1024:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=55, optimize=True)
            result = buf.getvalue()

        logger.info(f"[ALERTS_IMG] Processed: {len(image_bytes)} → {len(result)} bytes")
        return result
    except Exception as e:
        logger.warning(f"[ALERTS_IMG] Processing failed: {e}, using original")
        return image_bytes


async def store_photo(image_bytes: bytes, original_filename: str, telegram_file_id: str = None, role: str = "alert") -> dict:
    """Store photo. Compress and strip EXIF first. role: 'alert' (GENES) or 'problem' (faults)."""
    image_bytes = _process_image(image_bytes)

    attachment_id = str(uuid.uuid4())
    file_size = len(image_bytes)
    attachment = {
        "id": attachment_id,
        "filename": f"{attachment_id}.jpg",
        "original_filename": original_filename,
        "file_type": "image/jpeg",
        "file_size": file_size,
        "storage_path": None,
        "telegram_file_id": telegram_file_id,
        "base64_data": None,
        "role": role,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from services.storage_service import put_object
        path = f"alerts/{attachment_id}.jpg"
        put_object(path, image_bytes, "image/jpeg")
        attachment["storage_path"] = path
        logger.info(f"[ALERTS_STORAGE] Stored in Object Storage: {path}")
        return attachment
    except Exception as e:
        logger.warning(f"[ALERTS_STORAGE] Object Storage failed: {e}")

    if file_size < 5 * 1024 * 1024:
        attachment["base64_data"] = base64.b64encode(image_bytes).decode("utf-8")
        logger.info("[ALERTS_STORAGE] Stored as base64")
        return attachment

    logger.info("[ALERTS_STORAGE] Using telegram_file_id fallback")
    return attachment


async def store_audio(audio_bytes: bytes, ext: str, telegram_file_id: str = None) -> dict:
    """Store audio in object storage or fallback base64."""
    audio_id = str(uuid.uuid4())
    file_size = len(audio_bytes)
    content_type = f"audio/{ext}" if ext in ("ogg", "mp3", "m4a", "wav", "webm") else "audio/ogg"
    record = {
        "id": audio_id,
        "filename": f"{audio_id}.{ext}",
        "file_type": content_type,
        "file_size": file_size,
        "storage_path": None,
        "telegram_file_id": telegram_file_id,
        "base64_data": None,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from services.storage_service import put_object
        path = f"alerts/audio/{audio_id}.{ext}"
        put_object(path, audio_bytes, content_type)
        record["storage_path"] = path
        logger.info(f"[ALERTS_STORAGE] Audio stored: {path}")
        return record
    except Exception as e:
        logger.warning(f"[ALERTS_STORAGE] Audio Object Storage failed: {e}")

    if file_size < 5 * 1024 * 1024:
        record["base64_data"] = base64.b64encode(audio_bytes).decode("utf-8")
    return record


# ============== CONVERSATION STATE HELPERS ==============
def _get_state(chat_id: int) -> dict:
    if chat_id not in _conversation_states:
        _conversation_states[chat_id] = {
            "state": STATE_IDLE,
            "active_alert_id": None,
            "problem_images_count": 0,
            "timer_task": None,
            "user_info": {},
            "last_activity": datetime.now(timezone.utc).timestamp(),
            "initial_buffer": None,
        }
    return _conversation_states[chat_id]


def _cancel_timer(state: dict):
    t = state.get("timer_task")
    if t and not t.done():
        t.cancel()
    state["timer_task"] = None


def _reset_state(chat_id: int):
    state = _conversation_states.get(chat_id)
    if state:
        _cancel_timer(state)
    _conversation_states[chat_id] = {
        "state": STATE_IDLE,
        "active_alert_id": None,
        "problem_images_count": 0,
        "timer_task": None,
        "user_info": {},
        "last_activity": datetime.now(timezone.utc).timestamp(),
        "initial_buffer": None,
    }


def _touch(state: dict):
    state["last_activity"] = datetime.now(timezone.utc).timestamp()


# ============== ALERT CREATION (FROM INITIAL BUFFER) ==============
async def _create_alert_from_buffer(chat_id: int):
    """Build the alert from the initial IDLE buffer and move to WAITING_PROBLEM_PHOTO_CONFIRMATION."""
    state = _get_state(chat_id)
    buf = state.get("initial_buffer") or {}
    texts = buf.get("texts", [])
    photos = buf.get("photos", [])
    user_info = state.get("user_info", {})
    combined_text = "\n".join(texts).strip()

    if not combined_text and not photos:
        _reset_state(chat_id)
        return

    # Only first photo is the GENES screenshot. AI extraction runs ONLY on this image.
    alert_image = None
    vision_result = {}
    extraction_failed = False

    if photos:
        first_photo = photos[0]
        image_bytes = await download_telegram_photo(first_photo["file_id"])
        if image_bytes:
            alert_image = await store_photo(
                image_bytes,
                f"alerta_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jpg",
                first_photo["file_id"],
                role="alert"
            )
            vision_result = await analyze_image(image_bytes)
            if not vision_result.get("success"):
                extraction_failed = True

    now = datetime.now(timezone.utc).isoformat()
    alert_id = str(uuid.uuid4())

    alert_doc = {
        "id": alert_id,
        "source": "telegram_alerts",
        "status": AlertStatus.PENDING.value,
        "license_plate": vision_result.get("license_plate") or None,
        "client_name": vision_result.get("client_name") or None,
        "items": vision_result.get("items", []),
        "assigned_to": None,
        "assigned_to_name": None,
        "created_by": {
            "source": "telegram",
            "chat_id": chat_id,
            "user_id": user_info.get("user_id", 0),
            "username": user_info.get("username"),
            "name": user_info.get("name", "Desconhecido"),
        },
        "telegram_chat_id": chat_id,
        "alert_image": alert_image,
        "problem_images": [],
        "has_problem_images": False,
        "mechanic_comment": None,
        "attachments": ([alert_image] if alert_image else []),
        "extraction_failed": extraction_failed,
        "raw_text": combined_text or None,
        "raw_vision_output": vision_result.get("raw_response"),
        "converted": False,
        "ticket_id": None,
        "ticket_number": None,
        "created_at": now,
        "updated_at": now,
        "converted_at": None,
    }

    await db.alerts.insert_one(alert_doc)
    logger.info(f"[ALERTS] Created alert {alert_id} from chat {chat_id}")

    # Transition state
    state["active_alert_id"] = alert_id
    state["state"] = STATE_WAIT_PROBLEM_PHOTO_CONF
    state["problem_images_count"] = 0
    state["initial_buffer"] = None
    _cancel_timer(state)
    _touch(state)

    plate_text = f"\nMatrícula: <b>{alert_doc['license_plate']}</b>" if alert_doc.get("license_plate") else ""
    items_text = f"\nItens: {', '.join(alert_doc['items'])}" if alert_doc.get("items") else ""
    warn_text = "\n⚠️ Não consegui ler a imagem, mas o alerta foi criado." if extraction_failed else ""

    await send_message(
        chat_id,
        f"✅ Alerta registado!{plate_text}{items_text}{warn_text}\n\n"
        f"Quer adicionar fotos das avarias para anexar ao orçamento?",
        reply_markup={
            "inline_keyboard": [[
                {"text": "📸 Sim", "callback_data": f"photos_yes:{alert_id}"},
                {"text": "❌ Não", "callback_data": f"photos_no:{alert_id}"},
            ]]
        }
    )


async def _idle_buffer_timer(chat_id: int):
    """After BUFFER_TIMEOUT_SECONDS of inactivity in IDLE buffer, create alert."""
    try:
        await asyncio.sleep(BUFFER_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        return
    state = _conversation_states.get(chat_id)
    if not state or state.get("state") != STATE_IDLE or not state.get("initial_buffer"):
        return
    await _create_alert_from_buffer(chat_id)


# ============== INCOMING MESSAGE ROUTERS ==============
async def handle_incoming_text(chat_id: int, user_info: dict, text: str):
    """Route a text message based on current conversation state."""
    state = _get_state(chat_id)
    _touch(state)
    current = state["state"]

    if current == STATE_IDLE:
        # Buffer text and wait for possible photo. If nothing else arrives, create text-only alert.
        if not state.get("initial_buffer"):
            state["initial_buffer"] = {"texts": [], "photos": []}
        state["initial_buffer"]["texts"].append(text)
        state["user_info"] = user_info
        _cancel_timer(state)
        state["timer_task"] = asyncio.create_task(_idle_buffer_timer(chat_id))
        return

    if current == STATE_COLLECTING_NOTE:
        # Save as mechanic note (text)
        text = text[:MAX_NOTE_TEXT_LEN]
        await _save_mechanic_note(chat_id, comment_type="text", text=text)
        return

    if current in (STATE_WAIT_PROBLEM_PHOTO_CONF, STATE_WAIT_NOTE_CONF, STATE_WAIT_ASSIGNEE):
        await send_message(chat_id, "Por favor use os botões acima para continuar.")
        return

    if current == STATE_COLLECTING_PROBLEM_IMAGES:
        await send_message(chat_id, "A aguardar fotos das avarias. Envie imagens ou aguarde para terminar.")
        return


async def handle_incoming_photo(chat_id: int, user_info: dict, photo: dict, caption: str = None):
    """Route a photo based on current state."""
    state = _get_state(chat_id)
    _touch(state)
    current = state["state"]

    if current == STATE_IDLE:
        # GENES screenshot path
        if not state.get("initial_buffer"):
            state["initial_buffer"] = {"texts": [], "photos": []}
        state["initial_buffer"]["photos"].append(photo)
        if caption:
            state["initial_buffer"]["texts"].append(caption)
        state["user_info"] = user_info
        _cancel_timer(state)
        state["timer_task"] = asyncio.create_task(_idle_buffer_timer(chat_id))
        return

    if current == STATE_COLLECTING_PROBLEM_IMAGES:
        await _append_problem_photo(chat_id, photo)
        return

    if current == STATE_WAIT_PROBLEM_PHOTO_CONF:
        await send_message(chat_id, "Por favor responda Sim/Não acima antes de enviar fotos.")
        return

    if current == STATE_COLLECTING_NOTE:
        await send_message(chat_id, "A aguardar nota (texto ou áudio). As fotos não são guardadas neste passo.")
        return

    if current in (STATE_WAIT_NOTE_CONF, STATE_WAIT_ASSIGNEE):
        await send_message(chat_id, "Por favor use os botões acima para continuar.")
        return


async def handle_incoming_voice(chat_id: int, user_info: dict, voice: dict):
    """Route a voice/audio message based on current state."""
    state = _get_state(chat_id)
    _touch(state)
    current = state["state"]

    if current != STATE_COLLECTING_NOTE:
        await send_message(chat_id, "Áudios só são aceites no passo de nota do mecânico.")
        return

    duration = voice.get("duration", 0)
    if duration > MAX_AUDIO_DURATION_SEC:
        await send_message(chat_id, f"⚠️ Áudio demasiado longo (máx {MAX_AUDIO_DURATION_SEC}s).")
        return

    file_id = voice.get("file_id")
    audio_bytes, ext = await download_telegram_file(file_id)
    if not audio_bytes:
        await send_message(chat_id, "⚠️ Não foi possível baixar o áudio. Tente novamente.")
        return

    ext = ext or "ogg"
    audio_record = await store_audio(audio_bytes, ext, telegram_file_id=file_id)

    # Try transcription (Whisper via Emergent LLM Key) — reuse existing helper
    transcription_status = "not_applicable"
    transcript = None
    try:
        from modules.telegram.service import transcribe_audio_with_whisper
        transcript = await transcribe_audio_with_whisper(audio_bytes, ext)
        transcription_status = "success" if transcript else "failed"
    except Exception as e:
        logger.warning(f"[ALERTS_AUDIO] Transcription error: {e}")
        transcription_status = "failed"

    await _save_mechanic_note(
        chat_id,
        comment_type="audio",
        text=transcript or "",
        audio=audio_record,
        transcription_status=transcription_status,
    )


async def _save_mechanic_note(
    chat_id: int,
    comment_type: str,
    text: str = "",
    audio: dict = None,
    transcription_status: str = "not_applicable",
):
    """Persist mechanic note on the active alert and advance to assignee selection."""
    state = _get_state(chat_id)
    alert_id = state.get("active_alert_id")
    if not alert_id:
        await send_message(chat_id, "⚠️ Sessão expirou. Envie a nova captura para começar de novo.")
        _reset_state(chat_id)
        return

    user_info = state.get("user_info", {})
    comment = {
        "type": comment_type,
        "text": text or None,
        "audio": audio,
        "transcription_status": transcription_status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": {
            "user_id": user_info.get("user_id", 0),
            "username": user_info.get("username"),
            "name": user_info.get("name", "Desconhecido"),
        },
    }
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"mechanic_comment": comment, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    state["state"] = STATE_WAIT_ASSIGNEE
    _cancel_timer(state)
    _touch(state)

    if comment_type == "audio":
        if transcription_status == "success":
            await send_message(chat_id, f"🎤 Nota de áudio guardada. Transcrição:\n<i>{text[:200]}</i>")
        else:
            await send_message(chat_id, "🎤 Nota de áudio guardada (sem transcrição).")
    else:
        await send_message(chat_id, "📝 Nota guardada.")

    await send_assignee_buttons(chat_id)


# ============== PROBLEM PHOTO COLLECTION ==============
async def _append_problem_photo(chat_id: int, photo: dict):
    state = _get_state(chat_id)
    alert_id = state.get("active_alert_id")
    if not alert_id:
        await send_message(chat_id, "⚠️ Sessão expirou. Envie a nova captura para começar de novo.")
        _reset_state(chat_id)
        return

    if state["problem_images_count"] >= MAX_PROBLEM_PHOTOS:
        await send_message(chat_id, f"Máximo de {MAX_PROBLEM_PHOTOS} fotos atingido. A continuar...")
        await _end_problem_photos(chat_id)
        return

    image_bytes = await download_telegram_photo(photo["file_id"])
    if not image_bytes:
        await send_message(chat_id, "⚠️ Não consegui baixar a foto. Envie novamente.")
        return

    att = await store_photo(
        image_bytes,
        f"problema_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{state['problem_images_count']}.jpg",
        photo["file_id"],
        role="problem",
    )
    # Append to alert
    await db.alerts.update_one(
        {"id": alert_id},
        {
            "$push": {"problem_images": att, "attachments": att},
            "$set": {"has_problem_images": True, "updated_at": datetime.now(timezone.utc).isoformat()},
        },
    )
    state["problem_images_count"] += 1
    _touch(state)

    remaining = MAX_PROBLEM_PHOTOS - state["problem_images_count"]
    if remaining > 0:
        await send_message(chat_id, f"✅ Foto {state['problem_images_count']} guardada. Pode enviar mais {remaining}.")
        # Reset inactivity timer
        _cancel_timer(state)
        state["timer_task"] = asyncio.create_task(_problem_photos_timer(chat_id))
    else:
        await send_message(chat_id, f"✅ Foto {state['problem_images_count']} guardada. Máximo atingido.")
        await _end_problem_photos(chat_id)


async def _problem_photos_timer(chat_id: int):
    """Inactivity timer in COLLECTING_PROBLEM_IMAGES."""
    try:
        await asyncio.sleep(PHOTO_COLLECTION_TIMEOUT)
    except asyncio.CancelledError:
        return
    state = _conversation_states.get(chat_id)
    if not state or state.get("state") != STATE_COLLECTING_PROBLEM_IMAGES:
        return
    await _end_problem_photos(chat_id)


async def _end_problem_photos(chat_id: int):
    state = _get_state(chat_id)
    state["state"] = STATE_WAIT_NOTE_CONF
    _cancel_timer(state)
    _touch(state)
    await send_message(
        chat_id,
        "Quer adicionar alguma nota para a receção?",
        reply_markup={
            "inline_keyboard": [[
                {"text": "📝 Adicionar nota", "callback_data": f"note_yes:{state['active_alert_id']}"},
                {"text": "Sem nota", "callback_data": f"note_no:{state['active_alert_id']}"},
            ]]
        }
    )


async def _note_collection_timer(chat_id: int):
    """If user clicks 'Adicionar nota' but never sends, time out and continue to assignee."""
    try:
        await asyncio.sleep(NOTE_COLLECTION_TIMEOUT)
    except asyncio.CancelledError:
        return
    state = _conversation_states.get(chat_id)
    if not state or state.get("state") != STATE_COLLECTING_NOTE:
        return
    state["state"] = STATE_WAIT_ASSIGNEE
    _cancel_timer(state)
    await send_message(chat_id, "⏱️ Sem nota recebida. A prosseguir...")
    await send_assignee_buttons(chat_id)


# ============== CALLBACK HANDLERS ==============
async def handle_photos_callback(chat_id: int, action: str, alert_id: str):
    state = _get_state(chat_id)
    if state.get("state") != STATE_WAIT_PROBLEM_PHOTO_CONF or state.get("active_alert_id") != alert_id:
        # State drifted — ignore softly
        return

    if action == "yes":
        state["state"] = STATE_COLLECTING_PROBLEM_IMAGES
        _cancel_timer(state)
        _touch(state)
        await send_message(
            chat_id,
            f"📸 Envie até {MAX_PROBLEM_PHOTOS} fotos das avarias. Quando terminar, aguarde alguns segundos.",
        )
        state["timer_task"] = asyncio.create_task(_problem_photos_timer(chat_id))
    else:
        await _end_problem_photos(chat_id)


async def handle_note_callback(chat_id: int, action: str, alert_id: str):
    state = _get_state(chat_id)
    if state.get("state") != STATE_WAIT_NOTE_CONF or state.get("active_alert_id") != alert_id:
        return

    if action == "yes":
        state["state"] = STATE_COLLECTING_NOTE
        _cancel_timer(state)
        _touch(state)
        await send_message(
            chat_id,
            f"Envie uma mensagem de <b>texto</b> ou <b>áudio</b> com a explicação para a receção. "
            f"(máx {MAX_NOTE_TEXT_LEN} caracteres ou {MAX_AUDIO_DURATION_SEC}s de áudio)"
        )
        state["timer_task"] = asyncio.create_task(_note_collection_timer(chat_id))
    else:
        state["state"] = STATE_WAIT_ASSIGNEE
        _cancel_timer(state)
        _touch(state)
        await send_assignee_buttons(chat_id)


async def handle_assign_callback(chat_id: int, user_id: str, user_name: str) -> bool:
    state = _get_state(chat_id)
    alert_id = state.get("active_alert_id")

    if not alert_id:
        # Fallback: try to find latest pending unassigned
        alert = await db.alerts.find_one(
            {"telegram_chat_id": chat_id, "assigned_to": None, "status": AlertStatus.PENDING.value},
            {"_id": 0, "id": 1},
            sort=[("created_at", -1)]
        )
        if alert:
            alert_id = alert["id"]

    if not alert_id:
        await send_message(chat_id, "Nenhum alerta pendente para atribuir.")
        _reset_state(chat_id)
        return False

    now = datetime.now(timezone.utc).isoformat()
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"assigned_to": user_id, "assigned_to_name": user_name, "updated_at": now}}
    )

    # Reset conversation state — IDLE
    _reset_state(chat_id)

    await send_message(
        chat_id,
        f"✅ Alerta atribuído com sucesso a <b>{user_name}</b>.\n\nPode enviar nova captura para criar outro alerta."
    )

    # Notifications
    try:
        from services.notification_service import create_notification
        alert = await db.alerts.find_one({"id": alert_id}, {"_id": 0})
        plate_info = f" ({alert['license_plate']})" if alert and alert.get("license_plate") else ""
        mechanic_name = alert.get("created_by", {}).get("name", "Mecânico") if alert else "Mecânico"
        notif_body = f"Alerta de {mechanic_name}{plate_info} - atribuído a {user_name}"
        await create_notification(
            user_id=user_id,
            title="Novo Alerta Telegram",
            body=notif_body,
            notification_type="info",
        )
        admins = await db.users.find(
            {"role": "ADMIN", "is_active": {"$ne": False}},
            {"_id": 0, "id": 1}
        ).to_list(10)
        for admin in admins:
            if admin["id"] != user_id:
                await create_notification(
                    user_id=admin["id"],
                    title="Novo Alerta Telegram",
                    body=notif_body,
                    notification_type="info",
                )
    except Exception as e:
        logger.warning(f"[ALERTS] Notification error: {e}")

    logger.info(f"[ALERTS] Alert {alert_id} assigned to {user_name} ({user_id})")
    return True


# ============== PUBLIC: COMMAND /reset (manual recovery) ==============
async def handle_reset_command(chat_id: int):
    _reset_state(chat_id)
    await send_message(chat_id, "🔄 Conversa reiniciada. Envie a captura GENES para criar um novo alerta.")


# ============== ALERT CRUD ==============
async def get_alerts(
    status: str = None,
    assigned_to: str = None,
    page: int = 1,
    page_size: int = 50,
    user_role: str = None,
    user_id: str = None,
) -> Tuple[List[dict], int]:
    """List alerts with filters. Admins/Supervisors see all, others see only assigned."""
    query = {"source": "telegram_alerts"}
    if status:
        query["status"] = status
    if assigned_to:
        query["assigned_to"] = assigned_to
    elif user_role and user_role not in ("ADMIN", "SUPERVISOR"):
        query["assigned_to"] = user_id

    total = await db.alerts.count_documents(query)
    skip = (page - 1) * page_size
    items = await db.alerts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return items, total


async def get_alert(alert_id: str) -> Optional[dict]:
    return await db.alerts.find_one({"id": alert_id}, {"_id": 0})


async def update_alert(alert_id: str, updates: dict) -> Optional[dict]:
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.alerts.update_one({"id": alert_id}, {"$set": updates})
    if result.matched_count > 0:
        return await get_alert(alert_id)
    return None


async def delete_alert(alert_id: str) -> bool:
    result = await db.alerts.delete_one({"id": alert_id})
    return result.deleted_count > 0


async def dismiss_alert(alert_id: str) -> Optional[dict]:
    alert = await get_alert(alert_id)
    if not alert or alert.get("status") != AlertStatus.PENDING.value:
        return None
    now = datetime.now(timezone.utc).isoformat()
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"status": AlertStatus.DISMISSED.value, "updated_at": now}}
    )
    return await get_alert(alert_id)


async def convert_alert_to_ticket(alert_id: str, converted_by: str, data: dict = None) -> Optional[dict]:
    """Convert alert to a ticket. Transfers problem_images and mechanic_comment (internal only)."""
    alert = await get_alert(alert_id)
    if not alert:
        return None
    if alert.get("converted"):
        return None

    data = data or {}
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    ticket_number = f"TK{now.strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"

    customer_name = data.get("customer_name") or alert.get("client_name") or "Cliente (via Alerta)"
    customer_phone = data.get("customer_phone") or ""
    customer_email = data.get("customer_email") or ""
    vehicle_plate = data.get("vehicle_plate") or alert.get("license_plate") or ""
    description = data.get("description") or alert.get("raw_text") or ""
    ticket_type = data.get("ticket_type") or "ORCAMENTO_MECANICA"
    assigned_to = data.get("assigned_to") or alert.get("assigned_to")

    items_list = alert.get("items", [])
    if items_list:
        items_text = ", ".join(items_list)
        if description and items_text not in description:
            description = f"{description} | Itens: {items_text}"
        elif not description:
            description = f"Itens: {items_text}"

    customer_id = None
    vehicle_id = None
    was_created = False
    try:
        from services.customer_service import find_or_create_customer_vehicle
        customer_id, vehicle_id, was_created = await find_or_create_customer_vehicle(
            license_plate=vehicle_plate,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            source="alert_conversion"
        )
    except Exception as e:
        logger.warning(f"[ALERTS] Customer auto-create failed: {e}")

    assigned_to_name = None
    if assigned_to:
        user = await db.users.find_one({"id": assigned_to}, {"_id": 0, "name": 1})
        assigned_to_name = user.get("name") if user else None

    sla_due = None
    sla_target_minutes = 0
    sla_policy_key = None
    try:
        from modules.intake.routes import compute_sla_due as _compute_sla
        sla_due, sla_target_minutes, sla_policy_key = _compute_sla(
            ticket_type=ticket_type, created_at=now
        )
    except Exception as e:
        logger.warning(f"[ALERTS] SLA compute failed: {e}")
        sla_due = now + timedelta(hours=24)

    initial_status = "EM_TRATAMENTO" if assigned_to else "ABERTO"

    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": "TELEGRAM",
        "type": ticket_type,
        "status": initial_status,
        "priority": "NORMAL",
        "description": description,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "vehicle_plate": vehicle_plate,
        "assigned_to_user_id": assigned_to,
        "assigned_to_name": assigned_to_name,
        "created_by_user_id": converted_by,
        "created_by_name": f"Alerta Telegram: {alert.get('created_by', {}).get('name', 'Desconhecido')}",
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "first_response_done": False,
        "sla_due": sla_due.isoformat() if sla_due else None,
        "sla_started_at": now.isoformat(),
        "sla_paused_at": None,
        "sla_paused_minutes": 0,
        "sla_breached": False,
        "sla_breached_at": None,
        "sla_target_minutes": sla_target_minutes,
        "sla_policy_key": sla_policy_key,
        "quote_sent": False,
        "quote_value": None,
        "source_alert_id": alert_id,
        "quote_context": "diagnostic",
        "problem_images": [],
        "mechanic_comment": None,
    }

    # Transfer problem_images to ticket (internal, customer-hidden by default)
    problem_imgs = alert.get("problem_images", [])
    if problem_imgs:
        ticket_problem_images = []
        for img in problem_imgs:
            ticket_problem_images.append({
                "id": img.get("id", str(uuid.uuid4())),
                "url": img.get("storage_path") or "",
                "base64_data": img.get("base64_data"),
                "file_type": img.get("file_type", "image/jpeg"),
                "file_size": img.get("file_size", 0),
                "telegram_file_id": img.get("telegram_file_id"),
                "source": "telegram_alerts",
                "visible_to_customer": False,
                "created_at": img.get("stored_at", now.isoformat()),
            })
        ticket_doc["problem_images"] = ticket_problem_images

    # Transfer mechanic_comment as internal-only
    if alert.get("mechanic_comment"):
        ticket_doc["mechanic_comment"] = alert["mechanic_comment"]

    await db.tickets.insert_one(ticket_doc)

    # Transfer attachments (internal)
    for att in alert.get("attachments", []):
        att_doc = {
            "id": att.get("id", str(uuid.uuid4())),
            "ticket_id": ticket_id,
            "filename": att.get("filename", ""),
            "original_filename": att.get("original_filename", "photo.jpg"),
            "file_type": att.get("file_type", "image/jpeg"),
            "file_size": att.get("file_size", 0),
            "storage_path": att.get("storage_path"),
            "uploaded_by_user_id": converted_by,
            "uploaded_at": now.isoformat(),
            "source": "telegram_alert",
        }
        await db.attachments.insert_one(att_doc)

    # System note
    note_body = "Ticket criado a partir de alerta Telegram"
    if alert.get("license_plate"):
        note_body += f"\nMatrícula: {alert['license_plate']}"
    if items_list:
        note_body += f"\nItens: {', '.join(items_list)}"
    if alert.get("created_by", {}).get("name"):
        note_body += f"\nEnviado por: {alert['created_by']['name']}"
    mc = alert.get("mechanic_comment")
    if mc:
        if mc.get("type") == "text" and mc.get("text"):
            note_body += f"\n\nNota do mecânico: {mc['text']}"
        elif mc.get("type") == "audio":
            tr = mc.get("text") or "[áudio guardado]"
            note_body += f"\n\nNota de áudio do mecânico: {tr}"

    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "created_by_user_id": converted_by,
        "body": note_body,
        "is_system": True,
    }
    await db.notes.insert_one(note_doc)

    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {
            "status": AlertStatus.CONVERTED.value,
            "converted": True,
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "converted_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }}
    )

    logger.info(f"[ALERTS] Converted alert {alert_id} to ticket {ticket_number}")

    mechanic_chat_id = alert.get("telegram_chat_id")
    if mechanic_chat_id:
        plate_text = f" ({vehicle_plate})" if vehicle_plate else ""
        await send_message(
            mechanic_chat_id,
            f"📋 O seu alerta{plate_text} foi convertido no ticket <b>{ticket_number}</b>.\n"
            f"Cliente: {customer_name}"
        )

    return {"ticket_id": ticket_id, "ticket_number": ticket_number, "customer_created": was_created}


async def get_alert_stats() -> dict:
    pipeline = [
        {"$match": {"source": "telegram_alerts"}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    results = await db.alerts.aggregate(pipeline).to_list(10)
    stats = {"pending": 0, "converted": 0, "dismissed": 0, "total": 0}
    for r in results:
        s = (r["_id"] or "pending").lower()
        if s in stats:
            stats[s] = r["count"]
        stats["total"] += r["count"]
    return stats


async def setup_webhook(webhook_url: str) -> dict:
    if not BOT_TOKEN:
        return {"success": False, "error": "Bot token not configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{TELEGRAM_API}{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]}
            )
            data = r.json()
            logger.info(f"[ALERTS_BOT] setWebhook: {data}")
            return {"success": data.get("ok", False), "result": data}
    except Exception as e:
        logger.error(f"[ALERTS_BOT] setWebhook error: {e}")
        return {"success": False, "error": str(e)}
