"""IA + audio helpers for pre-ticket extraction.

- transcribe_audio: Whisper via Emergent integrations (ogg/mp3/m4a).
- analyze_image: OCR/visual hints via GPT-4o.
- extract_pre_ticket_fields: structured extraction from raw_text into
  {customer_name, customer_phone, vehicle_plate, vehicle_make_model,
   request_type, description, urgency, preferred_contact_channel,
   internal_notes, missing_fields, confidence_score}.
"""
import os
import json
import re
import base64
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

ALL_FIELDS = [
    "customer_name",
    "customer_phone",
    "vehicle_plate",
    "vehicle_make_model",
    "request_type",
    "description",
    "urgency",
    "preferred_contact_channel",
    "internal_notes",
]

REQUEST_TYPES_HINT = "tires | service | quote | info | other"
URGENCY_HINT = "low | normal | high | urgent"
CHANNEL_HINT = "phone | whatsapp | email | telegram"

PLATE_RE = re.compile(r"\b([A-Z0-9]{2}-[A-Z0-9]{2}-[A-Z0-9]{2})\b")
PHONE_RE = re.compile(r"(?<!\d)((?:\+?351[-\s]?)?9\d{2}[-\s]?\d{3}[-\s]?\d{3})(?!\d)")


def _plate_fallback(text: str) -> Optional[str]:
    """Best-effort PT plate detection from raw text (used if IA misses it)."""
    if not text:
        return None
    upper = text.upper()
    m = PLATE_RE.search(upper)
    if m:
        return m.group(1)
    # try compact like AB12CD or AB 12 CD
    compact = re.search(r"\b([A-Z0-9]{2})\s*-?\s*([A-Z0-9]{2})\s*-?\s*([A-Z0-9]{2})\b", upper)
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}-{compact.group(3)}"
    return None


def _phone_fallback(text: str) -> Optional[str]:
    if not text:
        return None
    m = PHONE_RE.search(text)
    if not m:
        return None
    return re.sub(r"\D+", "", m.group(1))[-9:]


async def transcribe_audio(audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
    """Transcribe audio via the existing helper (Whisper, Emergent LLM key)."""
    try:
        from modules.telegram.service import transcribe_audio_with_whisper
        return await transcribe_audio_with_whisper(audio_bytes, file_extension)
    except Exception as e:
        logger.warning("transcribe_audio failed: %s", e)
        return None


async def analyze_image(image_bytes: bytes) -> Optional[str]:
    """Return a short text describing what is visible in the image (OCR + hints).

    Best-effort: any failure returns None.
    """
    if not EMERGENT_LLM_KEY or not image_bytes:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="preticket-vision",
            system_message=(
                "És um assistente que analisa fotos para um serviço automóvel. "
                "Extrai apenas o que está visível: matrícula, marca/modelo, KM, "
                "código de avaria, texto legível, ou descrição breve da cena. "
                "Resposta em português, máximo 4 linhas. Sem inventar dados."
            ),
        ).with_model("openai", "gpt-4o")
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        resp = await chat.send_message(
            UserMessage(text="Descreve esta foto em poucas palavras.",
                        file_contents=[ImageContent(image_base64=b64)])
        )
        text = (resp or "").strip()
        return text or None
    except Exception as e:
        logger.warning("analyze_image failed: %s", e)
        return None


def _safe_json_parse(raw: str) -> Optional[dict]:
    if not raw:
        return None
    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        # try to find an inner JSON object
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


async def extract_pre_ticket_fields(raw_text: str, image_hints: List[str] = None) -> Dict[str, Any]:
    """Extract structured fields from a free-form raw text.

    Returns a dict with all ALL_FIELDS, plus `missing_fields` (list) and
    `confidence_score` (0..1). Never raises — returns a best-effort dict.
    """
    image_hints = image_hints or []
    result: Dict[str, Any] = {k: None for k in ALL_FIELDS}
    result["missing_fields"] = []
    result["confidence_score"] = 0.0

    if not raw_text and not image_hints:
        result["missing_fields"] = list(ALL_FIELDS)
        return result

    combined = (raw_text or "").strip()
    if image_hints:
        combined += "\n\n[Hints from images]\n" + "\n".join(image_hints)

    if EMERGENT_LLM_KEY:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id="preticket-extract",
                system_message=(
                    "És um assistente que extrai dados estruturados de mensagens "
                    "soltas enviadas por mecânicos de uma oficina de pneus. "
                    "Responde sempre em JSON estrito, sem markdown. "
                    "Se não souberes um campo, mete null. NUNCA inventes dados. "
                    "Os campos são exactamente: "
                    f"{ALL_FIELDS + ['missing_fields','confidence_score']}. "
                    f"`request_type` tem de ser um de: {REQUEST_TYPES_HINT}. "
                    f"`urgency` tem de ser um de: {URGENCY_HINT}. "
                    f"`preferred_contact_channel` tem de ser um de: {CHANNEL_HINT}. "
                    "`missing_fields` é uma lista com os nomes dos campos que ficaram a null. "
                    "`confidence_score` é um número entre 0 e 1 que reflecte a confiança global."
                ),
            ).with_model("openai", "gpt-4o")
            resp = await chat.send_message(UserMessage(text=combined))
            parsed = _safe_json_parse(resp or "")
            if parsed and isinstance(parsed, dict):
                for k in ALL_FIELDS:
                    v = parsed.get(k)
                    if isinstance(v, str):
                        v = v.strip() or None
                    result[k] = v
                # missing_fields
                mf = parsed.get("missing_fields") or []
                if isinstance(mf, list):
                    result["missing_fields"] = [str(x) for x in mf]
                # confidence
                cs = parsed.get("confidence_score")
                try:
                    cs = float(cs)
                    result["confidence_score"] = max(0.0, min(1.0, cs))
                except Exception:
                    result["confidence_score"] = 0.5
        except Exception as e:
            logger.warning("extract_pre_ticket_fields IA failed: %s", e)

    # Regex fallbacks for plate/phone if IA missed
    if not result.get("vehicle_plate"):
        result["vehicle_plate"] = _plate_fallback(combined)
    if not result.get("customer_phone"):
        result["customer_phone"] = _phone_fallback(combined)

    # Re-compute missing_fields based on final values
    result["missing_fields"] = [k for k in ALL_FIELDS if not result.get(k)]
    # Confidence floor if many missing
    if result["confidence_score"] == 0 and combined:
        filled = sum(1 for k in ALL_FIELDS if result.get(k))
        result["confidence_score"] = round(min(0.9, filled / max(1, len(ALL_FIELDS))), 2)

    return result
