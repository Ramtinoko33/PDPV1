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
    STATE_WHEEL_PHOTO_FULL, STATE_CONFIRM_FULL, STATE_EDIT_FULL_SIZE,
    STATE_EDIT_FULL_BRAND, STATE_EDIT_FULL_LOAD_SPEED,
    STATE_WHEEL_PHOTO_DOT, STATE_CONFIRM_DOT, STATE_EDIT_DOT,
    STATE_WHEEL_PHOTO_TREAD, STATE_CONFIRM_TREAD, STATE_EDIT_TREAD,
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


async def extract_full_tire(image_bytes: bytes) -> dict:
    """Read sidewall: size, brand, model, load_speed. Returns dict with values + confidence."""
    prompt = """Analisa o flanco deste pneu. Procura APENAS o padrão oficial de medida e índice de carga/velocidade.

REGRAS DURAS:
- MEDIDA: 3 dígitos / 2 dígitos R 2 dígitos (ex: 195/50 R16, 205/55 R16, 225/45 R17)
  Aceita variações: "195/50R16", "195/50 R16", "195 50 R16". Devolve sempre formatado como "205/55 R16".
- ÍNDICE C/V: 2 ou 3 dígitos + 1 letra (ex: 88V, 91V, 94W, 98W, 110T). DEVE estar perto da medida.
- IGNORA SEMPRE: "TUBELESS", "OUTSIDE", "RADIAL", "STEEL", "E4", "EXTRA LOAD", "MAX LOAD", "MAX PRESS", "DOT", "M+S", logos de aprovação.
- MARCA/MODELO: nome do fabricante grande (ex: Michelin, Continental, Yokohama) e modelo se visível (ex: Primacy 4, BluEarth).
- Se um campo tiver baixa visibilidade ou estiver tapado, devolve null e confidence "low" PARA ESSE CAMPO.
- NUNCA inventes. Se não vês claramente, devolve null.

JSON:
{
  "size": "ex: 205/55 R16 ou null",
  "size_confidence": "high|medium|low",
  "brand": "ex: Yokohama ou null",
  "model": "ex: BluEarth ou null",
  "brand_confidence": "high|medium|low",
  "load_speed": "ex: 91V ou null",
  "load_speed_confidence": "high|medium|low"
}

Devolve APENAS JSON válido."""
    data = await _llm_extract(image_bytes, prompt) or {}
    # Post-validate size via regex
    size = data.get("size")
    if size:
        m = re.search(r'(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})', str(size).upper())
        if m:
            data["size"] = f"{m.group(1)}/{m.group(2)} R{m.group(3)}"
        else:
            data["size"] = None
            data["size_confidence"] = "low"
    # Post-validate load_speed via regex
    ls = data.get("load_speed")
    if ls:
        m = re.search(r'\b(\d{2,3}[A-Z])\b', str(ls).upper())
        if m:
            data["load_speed"] = m.group(1)
        else:
            data["load_speed"] = None
            data["load_speed_confidence"] = "low"
    return {
        "size": data.get("size"),
        "size_confidence": data.get("size_confidence") or ("low" if not data.get("size") else "high"),
        "brand": data.get("brand"),
        "model": data.get("model"),
        "brand_confidence": data.get("brand_confidence") or ("low" if not data.get("brand") else "high"),
        "load_speed": data.get("load_speed"),
        "load_speed_confidence": data.get("load_speed_confidence") or ("low" if not data.get("load_speed") else "high"),
    }


async def extract_dot(image_bytes: bytes) -> dict:
    """Read DOT code. Returns {dot: 4 digits or None, confidence}."""
    prompt = """Procura o código DOT neste flanco de pneu.

REGRAS DURAS:
- DOT são os 4 ÚLTIMOS dígitos dentro ou imediatamente após o bloco "DOT ...".
- Os primeiros 2 dígitos representam a SEMANA (01–53).
- Os últimos 2 dígitos representam o ANO (10–30).
- Exemplos válidos: 1923, 3620, 4973.
- IGNORA: códigos de homologação ("E4 12345"), pressão (MAX PRESS), carga (MAX LOAD).
- NUNCA confundas códigos longos (8+ caracteres) com DOT.
- Se não tiveres CERTEZA dos 4 dígitos, devolve null com confidence "low".

JSON:
{"dot": "1923 ou null", "confidence": "high|medium|low"}

Devolve APENAS JSON válido."""
    data = await _llm_extract(image_bytes, prompt) or {}
    dot = data.get("dot")
    conf = data.get("confidence") or "low"
    if dot:
        m = re.search(r'(\d{4})', str(dot))
        if m:
            digits = m.group(1)
            wk = int(digits[:2])
            yr = int(digits[2:])
            if 1 <= wk <= 53 and 10 <= yr <= 30:
                return {"dot": digits, "confidence": conf if conf in ("high", "medium", "low") else "high"}
        # invalid → low
        return {"dot": None, "confidence": "low"}
    return {"dot": None, "confidence": "low"}


async def extract_tread(image_bytes: bytes) -> dict:
    """Read tread depth (mm) from a gauge in the photo.

    CRITICAL: The gauge has reference labels '1.6MM' and '4 MM' printed on it.
    These are NOT the reading — they are LIMITS. The actual reading is at the
    position of the cursor/probe along the scale.
    """
    prompt = """Analisa esta imagem de um pneu com profundímetro/medidor de piso.

REGRAS CRÍTICAS:
- O medidor tem marcas IMPRESSAS de referência: "1,6 MM" (limite legal) e "4 MM" (alerta).
- ESTAS MARCAS NÃO SÃO LEITURAS. NÃO podes devolvê-las como valor.
- A LEITURA real é a POSIÇÃO do indicador/cursor na escala vertical (lateral) do medidor — onde a régua entra no sulco.
- A escala tem traços pequenos numerados de 0 a ~8 mm. Lê o valor onde o cursor para.
- Se o cursor não estiver visível, ou se a única coisa que vês são as marcas impressas "1,6 MM"/"4 MM", devolve null.
- NUNCA estimes pelo aspecto visual do pneu.
- Se houver dúvida, devolve null e confidence "low".

JSON:
{"tread_mm": 5.5 ou null, "confidence": "high|medium|low"}

Devolve APENAS JSON válido."""
    data = await _llm_extract(image_bytes, prompt) or {}
    val = data.get("tread_mm")
    conf = data.get("confidence") or "low"
    try:
        if val is not None:
            fval = float(val)
            # Sanity: realistic tread is 0-12mm. Block exact 1.6 or 4.0 returns (gauge labels).
            if 0 <= fval <= 12 and fval not in (1.6, 4.0):
                return {"tread_mm": fval, "confidence": conf if conf in ("high", "medium", "low") else "high"}
            return {"tread_mm": None, "confidence": "low"}
    except Exception:
        pass
    return {"tread_mm": None, "confidence": "low"}


# Legacy combined function (kept for backward compatibility — not used in new per-photo flow)
async def extract_tire_data(photo_full: bytes, photo_dot: bytes, photo_tread: bytes) -> dict:
    f = await extract_full_tire(photo_full)
    d = await extract_dot(photo_dot)
    t = await extract_tread(photo_tread)
    return {
        "size": f.get("size"), "brand": f.get("brand"), "model": f.get("model"),
        "load_speed": f.get("load_speed"), "dot": d.get("dot"), "tread_mm": t.get("tread_mm"),
    }


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

    if state == STATE_EDIT_FULL_SIZE:
        # Validate size regex
        m = re.search(r'(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})', text.upper())
        size = f"{m.group(1)}/{m.group(2)} R{m.group(3)}" if m else None
        draft = await _get_draft(draft_id)
        cur = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur["size"] = size or text.strip()
        cur["size_confidence"] = "high"
        cur["size_confirmed_by_human"] = True
        await _update_last_wheel(draft_id, {"data": cur})
        _transition(chat_id, STATE_CONFIRM_FULL)
        await _ask_confirm_full(chat_id)
        return

    if state == STATE_EDIT_FULL_BRAND:
        # Expect "Marca | Modelo" or just brand
        parts = [p.strip() for p in text.split("|")]
        brand = parts[0] if parts else text.strip()
        model = parts[1] if len(parts) > 1 else None
        draft = await _get_draft(draft_id)
        cur = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur["brand"] = brand or None
        cur["model"] = model
        cur["brand_confidence"] = "high"
        cur["brand_confirmed_by_human"] = True
        await _update_last_wheel(draft_id, {"data": cur})
        _transition(chat_id, STATE_CONFIRM_FULL)
        await _ask_confirm_full(chat_id)
        return

    if state == STATE_EDIT_FULL_LOAD_SPEED:
        m = re.search(r'(\d{2,3}[A-Z])', text.upper())
        ls = m.group(1) if m else None
        draft = await _get_draft(draft_id)
        cur = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur["load_speed"] = ls or text.strip().upper()
        cur["load_speed_confidence"] = "high"
        cur["load_speed_confirmed_by_human"] = True
        await _update_last_wheel(draft_id, {"data": cur})
        _transition(chat_id, STATE_CONFIRM_FULL)
        await _ask_confirm_full(chat_id)
        return

    if state == STATE_EDIT_DOT:
        m = re.search(r'(\d{4})', text)
        dot = m.group(1) if m else None
        if dot:
            wk, yr = int(dot[:2]), int(dot[2:])
            if not (1 <= wk <= 53 and 10 <= yr <= 30):
                await send_message(chat_id, "⚠️ DOT inválido. Os primeiros 2 dígitos devem ser semana (01–53) e os últimos 2 anos (10–30). Tente novamente:")
                return
        draft = await _get_draft(draft_id)
        cur = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur["dot"] = dot
        cur["dot_confidence"] = "high"
        cur["dot_confirmed_by_human"] = True
        await _update_last_wheel(draft_id, {"data": cur})
        _transition(chat_id, STATE_CONFIRM_DOT)
        await _ask_confirm_dot(chat_id)
        return

    if state == STATE_EDIT_TREAD:
        try:
            val = float(text.replace(",", ".").strip())
            if not 0 <= val <= 12:
                raise ValueError
        except Exception:
            await send_message(chat_id, "⚠️ Valor inválido. Envie apenas o número em mm (ex: 5.5).")
            return
        draft = await _get_draft(draft_id)
        cur = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur["tread_mm"] = val
        cur["tread_confidence"] = "high"
        cur["tread_confirmed_by_human"] = True
        await _update_last_wheel(draft_id, {"data": cur})
        _transition(chat_id, STATE_CONFIRM_TREAD)
        await _ask_confirm_tread(chat_id)
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
        })
        await send_message(chat_id, "🔎 A ler o flanco do pneu...")
        result = await extract_full_tire(image_bytes)
        wheel_data = {
            "size": result["size"],
            "size_confidence": result["size_confidence"],
            "size_confirmed_by_human": False,
            "brand": result["brand"],
            "model": result["model"],
            "brand_confidence": result["brand_confidence"],
            "brand_confirmed_by_human": False,
            "load_speed": result["load_speed"],
            "load_speed_confidence": result["load_speed_confidence"],
            "load_speed_confirmed_by_human": False,
        }
        await _update_last_wheel(draft_id, {"data": wheel_data})
        _transition(chat_id, STATE_CONFIRM_FULL)
        await _ask_confirm_full(chat_id)
        return

    if state == STATE_WHEEL_PHOTO_DOT:
        photo_rec = await store_photo(image_bytes, f"wheels/{s['wheel_index']}/dot", photo["file_id"])
        await _update_last_wheel(draft_id, {"photo_dot": photo_rec})
        await send_message(chat_id, "🔎 A ler o DOT...")
        result = await extract_dot(image_bytes)
        draft = await _get_draft(draft_id)
        cur_data = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur_data["dot"] = result["dot"]
        cur_data["dot_confidence"] = result["confidence"]
        cur_data["dot_confirmed_by_human"] = False
        await _update_last_wheel(draft_id, {"data": cur_data})
        _transition(chat_id, STATE_CONFIRM_DOT)
        await _ask_confirm_dot(chat_id)
        return

    if state == STATE_WHEEL_PHOTO_TREAD:
        photo_rec = await store_photo(image_bytes, f"wheels/{s['wheel_index']}/tread", photo["file_id"])
        await _update_last_wheel(draft_id, {"photo_tread": photo_rec})
        await send_message(chat_id, "🔎 A ler o piso...")
        result = await extract_tread(image_bytes)
        draft = await _get_draft(draft_id)
        cur_data = (draft.get("wheels") or [{}])[-1].get("data", {}) if draft else {}
        cur_data["tread_mm"] = result["tread_mm"]
        cur_data["tread_confidence"] = result["confidence"]
        cur_data["tread_confirmed_by_human"] = False
        await _update_last_wheel(draft_id, {"data": cur_data})
        _transition(chat_id, STATE_CONFIRM_TREAD)
        await _ask_confirm_tread(chat_id)
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
        f"📸 Fotografe o <b>flanco</b> com a medida bem visível, perto e com luz."
    )


async def _prompt_wheel_dot(chat_id: int):
    s = _get_state(chat_id)
    pos = WHEEL_POSITIONS[s["wheel_index"]]
    _transition(chat_id, STATE_WHEEL_PHOTO_DOT)
    await send_message(
        chat_id,
        f"📸 Fotografe o <b>DOT de perto</b>, com os 4 últimos dígitos nítidos. ({WHEEL_LABELS[pos]})"
    )


async def _prompt_wheel_tread(chat_id: int):
    s = _get_state(chat_id)
    pos = WHEEL_POSITIONS[s["wheel_index"]]
    _transition(chat_id, STATE_WHEEL_PHOTO_TREAD)
    await send_message(
        chat_id,
        f"📏 Encoste o <b>profundímetro</b> ao sulco principal, mantenha a escala direita e visível, com boa luz. ({WHEEL_LABELS[pos]})"
    )


def _conf_emoji(conf: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf or "low", "🔴")


async def _ask_confirm_full(chat_id: int):
    s = _get_state(chat_id)
    draft = await _get_draft(s["draft_id"])
    w = (draft.get("wheels") or [{}])[-1]
    d = w.get("data", {})
    size_low = d.get("size_confidence") == "low"
    bm_low = d.get("brand_confidence") == "low"
    ls_low = d.get("load_speed_confidence") == "low"
    rows = [
        f"{_conf_emoji(d.get('size_confidence'))} Medida: <b>{d.get('size') or '—'}</b>",
        f"{_conf_emoji(d.get('brand_confidence'))} Marca/Modelo: <b>{(d.get('brand') or '—')} {d.get('model') or ''}</b>".strip(),
        f"{_conf_emoji(d.get('load_speed_confidence'))} Índice C/V: <b>{d.get('load_speed') or '—'}</b>",
    ]
    buttons = []
    any_low = size_low or bm_low or ls_low
    if not any_low and d.get("size") and d.get("brand") and d.get("load_speed"):
        buttons.append([{"text": "✅ Confirmar", "callback_data": f"full_ok:{s['draft_id']}"}])
    buttons.append([{"text": "✏️ Editar medida", "callback_data": f"full_edit_size:{s['draft_id']}"}])
    buttons.append([{"text": "✏️ Editar marca/modelo", "callback_data": f"full_edit_brand:{s['draft_id']}"}])
    buttons.append([{"text": "✏️ Editar índice C/V", "callback_data": f"full_edit_speed:{s['draft_id']}"}])
    buttons.append([{"text": "🔁 Repetir foto", "callback_data": f"full_redo:{s['draft_id']}"}])
    warning = "\n\n⚠️ Não consegui ler com segurança algum campo. Edite manualmente ou repita a foto." if any_low else ""
    await send_message(chat_id, "📋 <b>Dados do flanco:</b>\n\n" + "\n".join(rows) + warning, reply_markup={"inline_keyboard": buttons})


async def _ask_confirm_dot(chat_id: int):
    s = _get_state(chat_id)
    draft = await _get_draft(s["draft_id"])
    w = (draft.get("wheels") or [{}])[-1]
    d = w.get("data", {})
    low = d.get("dot_confidence") == "low"
    txt = f"{_conf_emoji(d.get('dot_confidence'))} DOT: <b>{d.get('dot') or '—'}</b>"
    buttons = []
    if not low and d.get("dot"):
        buttons.append([{"text": "✅ Confirmar", "callback_data": f"dot_ok:{s['draft_id']}"}])
    buttons.append([{"text": "✏️ Editar DOT", "callback_data": f"dot_edit:{s['draft_id']}"}])
    buttons.append([{"text": "🔁 Repetir foto", "callback_data": f"dot_redo:{s['draft_id']}"}])
    warning = "\n\n⚠️ Não consegui ler o DOT com segurança. Edite manualmente ou repita a foto." if low else ""
    await send_message(chat_id, txt + warning, reply_markup={"inline_keyboard": buttons})


async def _ask_confirm_tread(chat_id: int):
    s = _get_state(chat_id)
    draft = await _get_draft(s["draft_id"])
    w = (draft.get("wheels") or [{}])[-1]
    d = w.get("data", {})
    low = d.get("tread_confidence") == "low"
    val = d.get("tread_mm")
    txt = f"{_conf_emoji(d.get('tread_confidence'))} Piso: <b>{val if val is not None else '—'} mm</b>"
    buttons = []
    if not low and val is not None:
        buttons.append([{"text": "✅ Confirmar", "callback_data": f"tread_ok:{s['draft_id']}"}])
    buttons.append([{"text": "✏️ Inserir manualmente", "callback_data": f"tread_edit:{s['draft_id']}"}])
    buttons.append([{"text": "🔁 Repetir foto", "callback_data": f"tread_redo:{s['draft_id']}"}])
    warning = "\n\n⚠️ Não consegui ler o piso com segurança." if low else ""
    await send_message(chat_id, txt + warning, reply_markup={"inline_keyboard": buttons})


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

    # --- Per-photo confirmation: FULL ---
    if action == "full_ok":
        await _prompt_wheel_dot(chat_id)
        return
    if action == "full_edit_size":
        _transition(chat_id, STATE_EDIT_FULL_SIZE)
        await send_message(chat_id, "Escreva a <b>medida</b> (ex: <code>205/55 R16</code>):")
        return
    if action == "full_edit_brand":
        _transition(chat_id, STATE_EDIT_FULL_BRAND)
        await send_message(chat_id, "Escreva a <b>marca</b> e opcionalmente o <b>modelo</b> separados por <b>|</b>.\n\nExemplo: <code>Yokohama | BluEarth</code>")
        return
    if action == "full_edit_speed":
        _transition(chat_id, STATE_EDIT_FULL_LOAD_SPEED)
        await send_message(chat_id, "Escreva o <b>índice C/V</b> (ex: <code>91V</code>):")
        return
    if action == "full_redo":
        # Remove the last wheel entry (with all photos) and re-prompt full
        draft = await _get_draft(s["draft_id"])
        if draft and draft.get("wheels"):
            wheels = draft["wheels"][:-1]
            await _update_draft(s["draft_id"], {"wheels": wheels})
        await _prompt_wheel_full(chat_id)
        return

    # --- Per-photo confirmation: DOT ---
    if action == "dot_ok":
        await _prompt_wheel_tread(chat_id)
        return
    if action == "dot_edit":
        _transition(chat_id, STATE_EDIT_DOT)
        await send_message(chat_id, "Escreva o <b>DOT</b> (4 dígitos finais, ex: <code>3620</code>):")
        return
    if action == "dot_redo":
        # Re-prompt DOT photo (keep full data)
        await _prompt_wheel_dot(chat_id)
        return

    # --- Per-photo confirmation: TREAD ---
    if action == "tread_ok":
        # All 3 done — show final wheel review
        draft = await _get_draft(s["draft_id"])
        w = (draft.get("wheels") or [{}])[-1]
        pos = w.get("position") or WHEEL_POSITIONS[s["wheel_index"]]
        _transition(chat_id, STATE_CONFIRM_WHEEL)
        await _ask_confirm_wheel(chat_id, pos, w.get("data", {}))
        return
    if action == "tread_edit":
        _transition(chat_id, STATE_EDIT_TREAD)
        await send_message(chat_id, "Escreva a <b>profundidade do piso em mm</b> (ex: <code>5.5</code>):")
        return
    if action == "tread_redo":
        await _prompt_wheel_tread(chat_id)
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
