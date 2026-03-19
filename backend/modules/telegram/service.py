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
        logger.error("[TELEGRAM] Bot token not configured")
        return None
    
    try:
        get_file_url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        logger.info(f"[TELEGRAM] Downloading file: {file_id[:20]}...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(get_file_url, timeout=10.0)
            
            if response.status_code != 200:
                logger.error(f"[TELEGRAM] Failed to get file info: HTTP {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            logger.info(f"[TELEGRAM] getFile response: ok={data.get('ok')}")
            
            if not data.get("ok"):
                logger.error(f"[TELEGRAM] getFile failed: {data}")
                return None
            
            file_path = data.get("result", {}).get("file_path")
            file_size = data.get("result", {}).get("file_size", 0)
            if not file_path:
                logger.error("[TELEGRAM] No file_path in response")
                return None
            
            logger.info(f"[TELEGRAM] File path: {file_path}, size: {file_size} bytes")
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            
            download_response = await client.get(download_url, timeout=30.0)
            
            if download_response.status_code == 200:
                file_bytes = download_response.content
                logger.info(f"[TELEGRAM] ✅ Downloaded file successfully: {len(file_bytes)} bytes")
                return file_bytes
            else:
                logger.error(f"[TELEGRAM] ❌ Failed to download file: HTTP {download_response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"[TELEGRAM] ❌ Error downloading file: {e}", exc_info=True)
        return None


async def analyze_image_with_llm(image_bytes: bytes) -> dict:
    """
    Use Emergent LLM (GPT-5.2 Vision) to analyze an image.
    Extracts: license plate, tire size, tire condition, brand.
    """
    if not EMERGENT_LLM_KEY:
        logger.error("[TELEGRAM] ❌ EMERGENT_LLM_KEY not configured - cannot analyze image")
        return {}
    
    logger.info(f"[TELEGRAM] 🔍 Starting image analysis with GPT-5.2 Vision ({len(image_bytes)} bytes)")
    
    try:
        # Convert image to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        logger.info(f"[TELEGRAM] Image converted to base64: {len(image_base64)} chars")
        
        # Create chat instance with vision model
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"telegram-vision-{uuid.uuid4().hex[:8]}",
            system_message="És um assistente especializado em análise de imagens de veículos e pneus em Portugal. Responde sempre em JSON válido."
        ).with_model(LLM_PROVIDER, LLM_MODEL)
        
        logger.info(f"[TELEGRAM] LLM Chat created with model: {LLM_PROVIDER}/{LLM_MODEL}")
        
        prompt = """Analisa esta imagem de um contexto automóvel/oficina.
Extrai as seguintes informações se visíveis:

1. Matrícula do veículo (formato português: AA-00-AA ou 00-AA-00)
2. Medida de pneu (exemplo: 205/55 R16, 225/45R17) - procura no flanco do pneu
3. Marca do pneu (Michelin, Continental, Pirelli, Bridgestone, etc.)
4. Estado do pneu (bom, desgastado, danificado)
5. Descrição breve do que vês na imagem

Responde APENAS em formato JSON válido:
{"license_plate": "XX-00-XX ou null", "tire_size": "000/00 R00 ou null", "tire_brand": "marca ou null", "tire_condition": "estado ou null", "description": "descrição breve"}"""
        
        # Create message with image attachment
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text=prompt,
            image_content=[image_content]
        )
        
        logger.info("[TELEGRAM] Sending image to LLM for analysis...")
        
        # Send message and get response
        response = await chat.send_message(user_message)
        
        logger.info(f"[TELEGRAM] LLM Response received: {response[:200] if response else 'EMPTY'}...")
        
        # Parse JSON from response
        result_text = response.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)
        
        extracted = json.loads(result_text)
        logger.info(f"[TELEGRAM] ✅ LLM Vision extracted: plate={extracted.get('license_plate')}, tire={extracted.get('tire_size')}, brand={extracted.get('tire_brand')}")
        return extracted
        
    except json.JSONDecodeError as e:
        logger.error(f"[TELEGRAM] ❌ Failed to parse LLM response as JSON: {e}")
        logger.error(f"[TELEGRAM] Raw response was: {response[:500] if response else 'None'}")
        return {}
    except Exception as e:
        logger.error(f"[TELEGRAM] ❌ Error calling LLM Vision: {type(e).__name__}: {e}", exc_info=True)
        return {}


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
    if not EMERGENT_LLM_KEY:
        logger.error("[TELEGRAM] ❌ EMERGENT_LLM_KEY not configured for audio transcription")
        return None
    
    logger.info(f"[TELEGRAM] 🎤 Starting audio transcription with Whisper ({len(audio_bytes)} bytes, format: {file_extension})")
    
    try:
        import os as os_module
        
        # Write audio to temp file (Whisper needs a file)
        with tempfile.NamedTemporaryFile(suffix=f".{file_extension}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name
        
        logger.info(f"[TELEGRAM] Audio saved to temp file: {temp_path}")
        
        try:
            # Initialize Whisper
            stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
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
            logger.info(f"[TELEGRAM] ✅ Whisper transcribed successfully: '{transcribed_text[:100]}...'")
            return transcribed_text
            
        finally:
            # Clean up temp file
            os_module.unlink(temp_path)
            logger.info("[TELEGRAM] Temp audio file cleaned up")
            
    except Exception as e:
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
    Process incoming Telegram message with optional photos and voice:
    1. Transcribe voice message if present
    2. Download and analyze photos if present
    3. Extract information using LLM
    4. Lookup customer by plate if found
    5. Create intake request
    6. Send confirmation to user
    """
    logger.info(f"[TELEGRAM] ========== PROCESSING MESSAGE ==========")
    logger.info(f"[TELEGRAM] Chat: {chat_id}, User: {first_name} (@{username})")
    logger.info(f"[TELEGRAM] Text: {message_text[:100] if message_text else 'None'}...")
    logger.info(f"[TELEGRAM] Photos: {len(photo_file_ids) if photo_file_ids else 0}")
    logger.info(f"[TELEGRAM] Voice: {'Yes' if voice_file_id else 'No'}")
    logger.info(f"[TELEGRAM] EMERGENT_LLM_KEY configured: {bool(EMERGENT_LLM_KEY)}")
    
    telegram_username = f"@{username}" if username else None
    photo_file_ids = photo_file_ids or []
    
    # Initialize extracted info
    extracted = {
        "license_plate": None,
        "tire_size": None,
        "service_type": None,
        "urgency": "normal",
        "summary": ""
    }
    
    image_descriptions = []
    combined_text = message_text or ""
    
    # Process voice message first
    if voice_file_id:
        logger.info(f"[TELEGRAM] 🎤 Processing voice message: {voice_file_id[:20]}...")
        voice_bytes = await download_telegram_file(voice_file_id)
        
        if voice_bytes:
            logger.info(f"[TELEGRAM] Voice downloaded: {len(voice_bytes)} bytes, starting transcription...")
            transcribed = await transcribe_audio_with_whisper(voice_bytes, "ogg")
            if transcribed:
                if combined_text:
                    combined_text += "\n\n🎤 Mensagem de voz:\n" + transcribed
                else:
                    combined_text = transcribed
                logger.info(f"[TELEGRAM] ✅ Voice transcribed and added to text")
            else:
                logger.warning("[TELEGRAM] ⚠️ Voice transcription returned empty")
        else:
            logger.error("[TELEGRAM] ❌ Failed to download voice file")
    
    # Process photos
    if photo_file_ids:
        logger.info(f"[TELEGRAM] 📸 Processing {len(photo_file_ids)} photos...")
        
        for i, file_id in enumerate(photo_file_ids[:3]):  # Max 3 photos
            logger.info(f"[TELEGRAM] Processing photo {i+1}/{min(len(photo_file_ids), 3)}: {file_id[:20]}...")
            image_bytes = await download_telegram_file(file_id)
            
            if image_bytes:
                logger.info(f"[TELEGRAM] Photo {i+1} downloaded: {len(image_bytes)} bytes, analyzing with LLM...")
                image_info = await analyze_image_with_llm(image_bytes)
                
                if image_info:
                    logger.info(f"[TELEGRAM] Photo {i+1} analysis result: {image_info}")
                    # Merge extracted info (prefer first found values)
                    if not extracted["license_plate"] and image_info.get("license_plate"):
                        extracted["license_plate"] = image_info["license_plate"]
                        logger.info(f"[TELEGRAM] ✅ Found license plate from photo: {extracted['license_plate']}")
                    if not extracted["tire_size"] and image_info.get("tire_size"):
                        extracted["tire_size"] = image_info["tire_size"]
                        logger.info(f"[TELEGRAM] ✅ Found tire size from photo: {extracted['tire_size']}")
                    
                    # Collect descriptions
                    if image_info.get("description"):
                        desc = image_info["description"]
                        if image_info.get("tire_brand"):
                            desc += f" (Marca: {image_info['tire_brand']})"
                        if image_info.get("tire_condition"):
                            desc += f" (Estado: {image_info['tire_condition']})"
                        image_descriptions.append(desc)
                else:
                    logger.warning(f"[TELEGRAM] ⚠️ Photo {i+1} analysis returned empty")
            else:
                logger.error(f"[TELEGRAM] ❌ Could not download photo {i+1}")
    
    # Add image descriptions to combined text
    if image_descriptions:
        logger.info(f"[TELEGRAM] Adding {len(image_descriptions)} image descriptions to text")
        if combined_text:
            combined_text += "\n\n📸 Análise das imagens:\n"
        else:
            combined_text = "📸 Análise das imagens:\n"
        combined_text += "\n".join(f"- {desc}" for desc in image_descriptions)
    
    # Extract info from text (if we have any text to analyze)
    if combined_text:
        logger.info(f"[TELEGRAM] Extracting info from combined text ({len(combined_text)} chars)...")
        text_extracted = await extract_info_with_llm(combined_text)
        
        # Merge with photo info (photo takes precedence for visual info)
        if not extracted["license_plate"]:
            extracted["license_plate"] = text_extracted.get("license_plate")
        if not extracted["tire_size"]:
            extracted["tire_size"] = text_extracted.get("tire_size")
        extracted["service_type"] = text_extracted.get("service_type")
        extracted["urgency"] = text_extracted.get("urgency", "normal")
        extracted["summary"] = text_extracted.get("summary", "")
    
    logger.info(f"[TELEGRAM] Final extracted data: plate={extracted.get('license_plate')}, tire={extracted.get('tire_size')}")
    
    # Lookup customer by license plate
    customer_info = None
    if extracted.get("license_plate"):
        logger.info(f"[TELEGRAM] Looking up customer by plate: {extracted['license_plate']}")
        customer_info = await lookup_customer_by_plate(extracted["license_plate"])
    
    # Determine sender info
    if customer_info and customer_info.get("name"):
        sender_name = customer_info["name"]
        logger.info(f"[TELEGRAM] Using customer name from DB: {sender_name}")
    else:
        sender_name = first_name
        if last_name:
            sender_name = f"{first_name} {last_name}"
        logger.info(f"[TELEGRAM] Using Telegram name: {sender_name}")
    
    # Determine contact (phone only)
    sender_contact = ""
    if customer_info and customer_info.get("phone"):
        sender_contact = customer_info["phone"]
        logger.info(f"[TELEGRAM] Using phone from DB: {sender_contact}")
    
    # Determine email
    sender_email = None
    if customer_info and customer_info.get("email"):
        sender_email = customer_info["email"]
        logger.info(f"[TELEGRAM] Using email from DB: {sender_email}")
    
    # Create intake request
    try:
        intake = await create_intake_request(
            source="telegram",
            source_type=IntakeSourceType.BOT_TELEGRAM,
            sender_name=sender_name,
            sender_contact=sender_contact,
            sender_email=sender_email,
            telegram_username=telegram_username,
            raw_text=combined_text,
            license_plate=extracted.get("license_plate"),
            tire_size=extracted.get("tire_size"),
            attachments=[]
        )
        
        intake_id = intake.get("id", "")[:8]
        
        # Build confirmation message
        confirmation = f"""✅ <b>Pedido recebido!</b>

Olá {first_name}, recebemos o seu pedido e vamos analisá-lo brevemente.

📋 <b>Referência:</b> #{intake_id}
"""
        if extracted.get("license_plate"):
            confirmation += f"🚗 <b>Matrícula:</b> {extracted['license_plate']}\n"
        if extracted.get("tire_size"):
            confirmation += f"🔘 <b>Medida:</b> {extracted['tire_size']}\n"
        if photo_file_ids:
            confirmation += f"📸 <b>Fotos recebidas:</b> {len(photo_file_ids)}\n"
        if voice_file_id:
            confirmation += f"🎤 <b>Áudio transcrito:</b> Sim\n"
        if extracted.get("summary"):
            confirmation += f"\n📝 {extracted['summary']}\n"
        
        confirmation += "\nA nossa equipa irá contactá-lo em breve. Obrigado!"
        
        await send_telegram_message(chat_id, confirmation)
        
        logger.info(f"[TELEGRAM] Created intake {intake_id} from user {sender_name}")
        return True, intake_id
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Error creating intake: {e}", exc_info=True)
        
        error_msg = f"""⚠️ <b>Ocorreu um erro</b>

Olá {first_name}, pedimos desculpa mas ocorreu um erro ao processar o seu pedido.

Por favor, tente novamente ou contacte-nos através do telefone.

Obrigado pela compreensão!"""
        
        await send_telegram_message(chat_id, error_msg)
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
