"""
Telegram Module Service v3
Business logic for Telegram bot integration with Emergent LLM Key.
Supports: text analysis, image vision, and audio transcription.
"""
import os
import re
import json
import base64
import httpx
import logging
import uuid
import tempfile
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from db import db
from modules.intake.service import create_intake_request
from modules.intake.models import IntakeSourceType

# Import Emergent integrations
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from emergentintegrations.llm.openai import OpenAISpeechToText

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# LLM Configuration - using GPT-5.2 for best results
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-5.2"


def get_bot_token() -> str:
    """Get Telegram bot token from environment."""
    return TELEGRAM_BOT_TOKEN


async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("[TELEGRAM] Bot token not configured")
        return False
    
    url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"[TELEGRAM] Message sent to chat {chat_id}")
                return True
            else:
                logger.error(f"[TELEGRAM] Failed to send message: {response.text}")
                return False
    except Exception as e:
        logger.error(f"[TELEGRAM] Error sending message: {e}")
        return False


async def download_telegram_file(file_id: str) -> Optional[bytes]:
    """
    Download a file from Telegram servers.
    Returns the file bytes or None on failure.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("[TELEGRAM] ERROR: Bot token not configured")
        logger.error("[TELEGRAM] Bot token not configured")
        return None
    
    try:
        get_file_url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        print(f"[TELEGRAM] Downloading file: {file_id[:30]}...")
        logger.info(f"[TELEGRAM] Downloading file: {file_id[:20]}...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(get_file_url, timeout=10.0)
            
            if response.status_code != 200:
                print(f"[TELEGRAM] ERROR: getFile failed with HTTP {response.status_code}")
                logger.error(f"[TELEGRAM] Failed to get file info: HTTP {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            print(f"[TELEGRAM] getFile response: ok={data.get('ok')}, file_path={data.get('result', {}).get('file_path')}")
            logger.info(f"[TELEGRAM] getFile response: ok={data.get('ok')}")
            
            if not data.get("ok"):
                print(f"[TELEGRAM] ERROR: getFile not ok: {data}")
                logger.error(f"[TELEGRAM] getFile failed: {data}")
                return None
            
            file_path = data.get("result", {}).get("file_path")
            file_size = data.get("result", {}).get("file_size", 0)
            if not file_path:
                print("[TELEGRAM] ERROR: No file_path in response")
                logger.error("[TELEGRAM] No file_path in response")
                return None
            
            print(f"[TELEGRAM] File path: {file_path}, size: {file_size} bytes")
            logger.info(f"[TELEGRAM] File path: {file_path}, size: {file_size} bytes")
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            
            download_response = await client.get(download_url, timeout=30.0)
            
            if download_response.status_code == 200:
                file_bytes = download_response.content
                print(f"[TELEGRAM] SUCCESS: Downloaded file: {len(file_bytes)} bytes")
                logger.info(f"[TELEGRAM] ✅ Downloaded file successfully: {len(file_bytes)} bytes")
                return file_bytes
            else:
                print(f"[TELEGRAM] ERROR: Failed to download file: HTTP {download_response.status_code}")
                logger.error(f"[TELEGRAM] ❌ Failed to download file: HTTP {download_response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"[TELEGRAM] ❌ Error downloading file: {e}", exc_info=True)
        return None


async def analyze_image_with_llm(image_bytes: bytes) -> dict:
    """
    Analyze image using GPT-5.2 Vision via Emergent LLM Key.
    Returns structured data extracted from the image.
    """
    print(f"[VISION] Starting image analysis: {len(image_bytes)} bytes")
    
    if not EMERGENT_LLM_KEY:
        print("[VISION] ERROR: EMERGENT_LLM_KEY not configured")
        logger.error("[VISION] EMERGENT_LLM_KEY not configured")
        return {"error": "LLM key not configured", "success": False}
    
    print(f"[VISION] EMERGENT_LLM_KEY is set: {EMERGENT_LLM_KEY[:15]}...")
    logger.info(f"[VISION] Analyzing image: {len(image_bytes)} bytes")
    
    try:
        # Convert image to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        print(f"[VISION] Image converted to base64: {len(image_base64)} chars")
        
        # Create chat instance
        print(f"[VISION] Creating LlmChat with model: {LLM_PROVIDER}/{LLM_MODEL}")
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"vision-{uuid.uuid4().hex[:8]}",
            system_message="Extrais dados de imagens. Responde APENAS com JSON válido, sem texto extra."
        ).with_model(LLM_PROVIDER, LLM_MODEL)
        
        prompt = """Analisa esta imagem e extrai os dados visíveis.
Devolve APENAS este JSON (sem markdown, sem texto extra):
{
  "customer_name": "",
  "customer_phone": "",
  "email": "",
  "vehicle_brand": "",
  "vehicle_model": "",
  "license_plate": "",
  "tire_size": "",
  "quantity": "",
  "subject": "",
  "message": "",
  "confidence": 0
}

Regras:
- Se não conseguires ler um campo, deixa string vazia ""
- confidence: 0-100 (quão certo estás da extração)
- license_plate: formato português (AA-00-AA ou 00-AA-00)
- tire_size: formato como 205/55 R16
- NÃO inventes dados"""

        # Use file_contents with ImageContent (correct method per playbook)
        print("[VISION] Creating UserMessage with ImageContent...")
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text=prompt,
            file_contents=[image_content]
        )
        
        # Send to LLM
        print("[VISION] Sending to LLM...")
        response = await chat.send_message(user_message)
        
        print(f"[VISION] LLM Response: {response[:300] if response else 'EMPTY'}")
        print(f"[VISION] LLM Response: {response[:300] if response else 'EMPTY'}")
        logger.info(f"[VISION] Raw response: {response[:300] if response else 'EMPTY'}")
        
        # Parse JSON
        result_text = response.strip()
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)
        
        print(f"[VISION] Parsing JSON: {result_text[:200]}")
        extracted = json.loads(result_text)
        extracted["success"] = True
        extracted["raw_response"] = response[:500]
        
        print(f"[VISION] SUCCESS: plate={extracted.get('license_plate')}, tire={extracted.get('tire_size')}, conf={extracted.get('confidence')}")
        logger.info(f"[VISION] Extracted: plate={extracted.get('license_plate')}, tire={extracted.get('tire_size')}, conf={extracted.get('confidence')}")
        return extracted
        
    except json.JSONDecodeError as e:
        print(f"[VISION] ERROR: JSON parse error: {e}")
        logger.error(f"[VISION] JSON parse error: {e}")
        return {"error": f"JSON parse error: {e}", "success": False, "raw_response": response[:500] if 'response' in dir() else ""}
    except Exception as e:
        print(f"[VISION] ERROR: {type(e).__name__}: {e}")
        logger.error(f"[VISION] Error: {type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}", "success": False}


async def extract_info_with_llm(text: str) -> dict:
    """
    Use Emergent LLM (GPT-5.2) to extract structured information from message text.
    Extracts: license plate, tire size, service type, urgency.
    """
    if not EMERGENT_LLM_KEY:
        logger.warning("[TELEGRAM] EMERGENT_LLM_KEY not configured, using regex fallback")
        return extract_info_with_regex(text)
    
    try:
        # Create chat instance
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"telegram-text-{uuid.uuid4().hex[:8]}",
            system_message="És um assistente especializado em extrair informações de mensagens de clientes de oficinas automóveis em Portugal. Responde sempre em JSON válido."
        ).with_model(LLM_PROVIDER, LLM_MODEL)
        
        prompt = f"""Analisa a seguinte mensagem de um cliente de uma oficina de pneus/mecânica em Portugal.
Extrai as seguintes informações se presentes:

1. Matrícula do veículo (formato português: AA-00-AA ou 00-AA-00)
2. Medida de pneu (exemplo: 205/55 R16, 225/45R17)
3. Tipo de serviço (orçamento pneus, mecânica, marcação, informação, reclamação)
4. Urgência (urgente, normal, baixa)
5. Resumo breve do pedido (máximo 50 palavras)

Mensagem do cliente:
"{text}"

Responde APENAS em formato JSON válido com estas chaves:
{{"license_plate": "XX-00-XX ou null", "tire_size": "000/00 R00 ou null", "service_type": "tipo ou null", "urgency": "urgente/normal/baixa", "summary": "resumo breve"}}"""
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Parse JSON from response
        result_text = response.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)
        
        extracted = json.loads(result_text)
        logger.info(f"[TELEGRAM] LLM extracted: {extracted}")
        return extracted
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Error calling LLM: {e}")
        return extract_info_with_regex(text)


async def transcribe_audio_with_whisper(audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
    """
    Use OpenAI Whisper (via Emergent) to transcribe audio to text.
    Supports: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg
    """
    print(f"[WHISPER] Starting transcription: {len(audio_bytes)} bytes, format: {file_extension}")
    
    if not EMERGENT_LLM_KEY:
        print("[WHISPER] ERROR: EMERGENT_LLM_KEY not configured")
        logger.error("[TELEGRAM] ❌ EMERGENT_LLM_KEY not configured for audio transcription")
        return None
    
    print(f"[WHISPER] EMERGENT_LLM_KEY is set: {EMERGENT_LLM_KEY[:15]}...")
    logger.info(f"[TELEGRAM] 🎤 Starting audio transcription with Whisper ({len(audio_bytes)} bytes, format: {file_extension})")
    
    try:
        import os as os_module
        
        # Write audio to temp file (Whisper needs a file)
        with tempfile.NamedTemporaryFile(suffix=f".{file_extension}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name
        
        print(f"[WHISPER] Audio saved to temp file: {temp_path}")
        logger.info(f"[TELEGRAM] Audio saved to temp file: {temp_path}")
        
        try:
            # Initialize Whisper
            print("[WHISPER] Initializing OpenAISpeechToText...")
            stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
            print("[WHISPER] Calling transcribe()...")
            logger.info("[TELEGRAM] Whisper STT initialized, starting transcription...")
            
            # Transcribe with Portuguese language hint
            with open(temp_path, "rb") as audio_file:
                response = await stt.transcribe(
                    file=audio_file,
                    model="whisper-1",
                    response_format="json",
                    language="pt"  # Portuguese
                )
            
            transcribed_text = response.text
            print(f"[WHISPER] SUCCESS: Transcribed text: '{transcribed_text[:100]}...'")
            logger.info(f"[TELEGRAM] ✅ Whisper transcribed successfully: '{transcribed_text[:100]}...'")
            return transcribed_text
            
        finally:
            # Clean up temp file
            os_module.unlink(temp_path)
            print("[WHISPER] Temp file cleaned up")
            logger.info("[TELEGRAM] Temp audio file cleaned up")
            
    except Exception as e:
        print(f"[WHISPER] ERROR: {type(e).__name__}: {e}")
        logger.error(f"[TELEGRAM] ❌ Error transcribing audio: {type(e).__name__}: {e}", exc_info=True)
        return None


def extract_info_with_regex(text: str) -> dict:
    """Fallback extraction using regex patterns."""
    result = {
        "license_plate": None,
        "tire_size": None,
        "service_type": None,
        "urgency": "normal",
        "summary": text[:100] if len(text) > 100 else text
    }
    
    # License plate patterns (Portuguese)
    plate_patterns = [
        r'\b([A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{2})\b',
        r'\b(\d{2}[-\s]?[A-Z]{2}[-\s]?\d{2})\b',
        r'\b([A-Z]{2}[-\s]?\d{2}[-\s]?\d{2})\b',
    ]
    for pattern in plate_patterns:
        match = re.search(pattern, text.upper())
        if match:
            result["license_plate"] = match.group(1).replace(" ", "-")
            break
    
    # Tire size pattern
    tire_pattern = r'\b(\d{3})[/\\](\d{2,3})\s*[RrZz]?\s*(\d{2})\b'
    tire_match = re.search(tire_pattern, text)
    if tire_match:
        result["tire_size"] = f"{tire_match.group(1)}/{tire_match.group(2)} R{tire_match.group(3)}"
    
    # Urgency detection
    if any(word in text.lower() for word in ["urgente", "urgência", "rápido", "hoje", "agora"]):
        result["urgency"] = "urgente"
    
    return result


async def lookup_customer_by_plate(license_plate: str) -> Optional[dict]:
    """
    Lookup customer information by license plate.
    Searches in vehicles, customers, and tickets collections.
    """
    if not license_plate:
        return None
    
    plate = license_plate.upper().replace(" ", "-")
    
    try:
        # 1. Search in vehicles collection
        vehicle = await db.vehicles.find_one(
            {"plate": {"$regex": f"^{plate}$", "$options": "i"}},
            {"_id": 0, "customer_id": 1}
        )
        
        if vehicle and vehicle.get("customer_id"):
            customer = await db.customers.find_one(
                {"id": vehicle["customer_id"]},
                {"_id": 0, "name": 1, "phone": 1, "email": 1}
            )
            if customer:
                logger.info(f"[TELEGRAM] Found customer via vehicle: {customer.get('name')}")
                return customer
        
        # 2. Search in tickets collection by vehicle_plate
        ticket = await db.tickets.find_one(
            {"vehicle_plate": {"$regex": f"^{plate}$", "$options": "i"}},
            {"_id": 0, "customer_name": 1, "customer_phone": 1, "customer_email": 1}
        )
        
        if ticket and ticket.get("customer_name"):
            logger.info(f"[TELEGRAM] Found customer via ticket: {ticket.get('customer_name')}")
            return {
                "name": ticket["customer_name"], 
                "phone": ticket.get("customer_phone"),
                "email": ticket.get("customer_email")
            }
        
        # 3. Search in customers collection directly
        customer = await db.customers.find_one(
            {"$or": [
                {"vehicle_plate": {"$regex": f"^{plate}$", "$options": "i"}},
                {"plates": {"$elemMatch": {"$regex": f"^{plate}$", "$options": "i"}}}
            ]},
            {"_id": 0, "name": 1, "phone": 1, "email": 1}
        )
        
        if customer:
            logger.info(f"[TELEGRAM] Found customer directly: {customer.get('name')}")
            return customer
        
        logger.info(f"[TELEGRAM] No customer found for plate: {plate}")
        return None
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Error looking up customer: {e}")
        return None


async def process_telegram_message(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    first_name: str,
    last_name: Optional[str],
    message_text: str,
    photo_file_ids: Optional[List[str]] = None,
    voice_file_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Process incoming Telegram message with optional photos and voice.
    Creates an intake request with extracted data.
    """
    logger.info(f"[TELEGRAM] Processing: chat={chat_id}, photos={len(photo_file_ids or [])}, voice={bool(voice_file_id)}")
    
    telegram_username = f"@{username}" if username else None
    photo_file_ids = photo_file_ids or []
    combined_text = message_text or ""
    
    # Analysis tracking
    analysis_status = "pending"
    analysis_error = None
    raw_vision_output = None
    
    # Extracted data from images
    vision_data = {}
    
    # Process voice message first
    if voice_file_id:
        voice_bytes = await download_telegram_file(voice_file_id)
        if voice_bytes:
            transcribed = await transcribe_audio_with_whisper(voice_bytes, "ogg")
            if transcribed:
                combined_text = (combined_text + "\n\n" + transcribed).strip() if combined_text else transcribed
                logger.info(f"[TELEGRAM] Voice transcribed: {len(transcribed)} chars")
    
    # Process photos - this is the key part
    if photo_file_ids:
        logger.info(f"[TELEGRAM] Processing {len(photo_file_ids)} photo(s)")
        
        for i, file_id in enumerate(photo_file_ids[:3]):
            logger.info(f"[VISION] Photo {i+1}: file_id={file_id[:20]}...")
            
            image_bytes = await download_telegram_file(file_id)
            if not image_bytes:
                analysis_error = f"Failed to download photo {i+1}"
                logger.error(f"[VISION] {analysis_error}")
                continue
            
            logger.info(f"[VISION] Photo {i+1}: downloaded {len(image_bytes)} bytes")
            
            # Analyze image
            result = await analyze_image_with_llm(image_bytes)
            
            if result.get("success"):
                analysis_status = "success"
                raw_vision_output = result.get("raw_response", "")
                
                # Merge data (first valid value wins)
                for field in ["license_plate", "tire_size", "customer_name", "customer_phone", 
                              "email", "vehicle_brand", "vehicle_model", "message", "quantity"]:
                    if not vision_data.get(field) and result.get(field):
                        vision_data[field] = result[field]
                
                logger.info(f"[VISION] Photo {i+1} extracted: plate={result.get('license_plate')}, tire={result.get('tire_size')}")
            else:
                analysis_status = "failed"
                analysis_error = result.get("error", "Unknown error")
                raw_vision_output = result.get("raw_response", "")
                logger.error(f"[VISION] Photo {i+1} failed: {analysis_error}")
    
    # Extract from text if we have any and no vision data yet
    text_extracted = {}
    if combined_text and not vision_data.get("license_plate"):
        text_extracted = await extract_info_with_llm(combined_text)
    
    # Build final message text
    if vision_data.get("message"):
        combined_text = (combined_text + "\n\n" + vision_data["message"]).strip() if combined_text else vision_data["message"]
    
    # Lookup customer by license plate
    license_plate = vision_data.get("license_plate") or text_extracted.get("license_plate")
    customer_info = await lookup_customer_by_plate(license_plate) if license_plate else None
    
    # Determine final values
    sender_name = vision_data.get("customer_name") or (customer_info or {}).get("name") or first_name
    if last_name and sender_name == first_name:
        sender_name = f"{first_name} {last_name}"
    
    sender_contact = vision_data.get("customer_phone") or (customer_info or {}).get("phone") or ""
    sender_email = vision_data.get("email") or (customer_info or {}).get("email")
    tire_size = vision_data.get("tire_size") or text_extracted.get("tire_size")
    
    logger.info(f"[TELEGRAM] Final data: name={sender_name}, plate={license_plate}, tire={tire_size}, status={analysis_status}")
    
    # Create intake request
    try:
        intake = await create_intake_request(
            source="telegram",
            source_type=IntakeSourceType.BOT_TELEGRAM,
            sender_name=sender_name,
            sender_contact=sender_contact,
            sender_email=sender_email,
            telegram_username=telegram_username,
            raw_text=combined_text or "(sem texto)",
            license_plate=license_plate,
            tire_size=tire_size,
            attachments=[],
            # New fields
            analysis_status=analysis_status,
            analysis_error=analysis_error,
            raw_vision_output=raw_vision_output,
            customer_phone=vision_data.get("customer_phone"),
            vehicle_brand=vision_data.get("vehicle_brand"),
            vehicle_model=vision_data.get("vehicle_model")
        )
        
        intake_id = intake.get("id", "")[:8]
        logger.info(f"[TELEGRAM] Created intake: {intake_id}")
        
        # Send confirmation
        confirmation = f"""✅ <b>Pedido recebido!</b>

Olá {first_name}, recebemos o seu pedido.

📋 <b>Referência:</b> #{intake_id}"""
        
        if license_plate:
            confirmation += f"\n🚗 <b>Matrícula:</b> {license_plate}"
        if tire_size:
            confirmation += f"\n🔘 <b>Medida:</b> {tire_size}"
        if photo_file_ids:
            confirmation += f"\n📸 <b>Fotos:</b> {len(photo_file_ids)}"
        if voice_file_id:
            confirmation += f"\n🎤 <b>Áudio:</b> Transcrito"
        
        confirmation += "\n\nA nossa equipa irá contactá-lo em breve!"
        
        await send_telegram_message(chat_id, confirmation)
        return True, intake_id
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Error creating intake: {e}")
        await send_telegram_message(chat_id, f"⚠️ Erro ao processar pedido. Tente novamente.")
        return False, str(e)


async def setup_webhook(webhook_url: str) -> Tuple[bool, str]:
    """Setup Telegram webhook."""
    if not TELEGRAM_BOT_TOKEN:
        return False, "Bot token not configured"
    
    url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/setWebhook"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"url": webhook_url},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    logger.info(f"[TELEGRAM] Webhook set to: {webhook_url}")
                    return True, "Webhook configured successfully"
                else:
                    return False, data.get("description", "Unknown error")
            else:
                return False, f"HTTP {response.status_code}: {response.text}"
                
    except Exception as e:
        logger.error(f"[TELEGRAM] Error setting webhook: {e}")
        return False, str(e)


async def get_webhook_info() -> dict:
    """Get current webhook info."""
    if not TELEGRAM_BOT_TOKEN:
        return {"error": "Bot token not configured"}
    
    url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                return response.json().get("result", {})
            return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


async def delete_webhook() -> Tuple[bool, str]:
    """Delete current webhook."""
    if not TELEGRAM_BOT_TOKEN:
        return False, "Bot token not configured"
    
    url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return True, "Webhook deleted"
                return False, data.get("description", "Unknown error")
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)
