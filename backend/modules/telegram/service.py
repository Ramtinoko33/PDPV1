"""
Telegram Module Service v3
Business logic for Telegram bot integration with image support.
"""
import os
import re
import base64
import httpx
import logging
from typing import Optional, Tuple, List
from datetime import datetime, timezone

from db import db
from modules.intake.service import create_intake_request
from modules.intake.models import IntakeSourceType

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


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
        # Step 1: Get file path from Telegram
        get_file_url = f"{TELEGRAM_API_URL}{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(get_file_url, timeout=10.0)
            
            if response.status_code != 200:
                logger.error(f"[TELEGRAM] Failed to get file info: {response.text}")
                return None
            
            data = response.json()
            if not data.get("ok"):
                logger.error(f"[TELEGRAM] getFile failed: {data}")
                return None
            
            file_path = data.get("result", {}).get("file_path")
            if not file_path:
                logger.error("[TELEGRAM] No file_path in response")
                return None
            
            # Step 2: Download the file
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            
            download_response = await client.get(download_url, timeout=30.0)
            
            if download_response.status_code == 200:
                file_bytes = download_response.content
                logger.info(f"[TELEGRAM] Downloaded file: {len(file_bytes)} bytes")
                return file_bytes
            else:
                logger.error(f"[TELEGRAM] Failed to download file: {download_response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"[TELEGRAM] Error downloading file: {e}", exc_info=True)
        return None


async def analyze_image_with_gemini(image_bytes: bytes) -> dict:
    """
    Use Gemini Vision to analyze an image.
    Extracts: license plate, tire size, tire condition, brand.
    """
    if not GEMINI_API_KEY:
        logger.warning("[TELEGRAM] Gemini API key not configured")
        return {}
    
    # Convert image to base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = """Analisa esta imagem de um contexto automóvel/oficina.
Extrai as seguintes informações se visíveis:

1. Matrícula do veículo (formato português: AA-00-AA ou 00-AA-00)
2. Medida de pneu (exemplo: 205/55 R16, 225/45R17) - procura no flanco do pneu
3. Marca do pneu (Michelin, Continental, Pirelli, Bridgestone, etc.)
4. Estado do pneu (bom, desgastado, danificado)
5. Descrição breve do que vês na imagem

Responde APENAS em formato JSON válido:
{"license_plate": "XX-00-XX ou null", "tire_size": "000/00 R00 ou null", "tire_brand": "marca ou null", "tire_condition": "estado ou null", "description": "descrição breve"}
"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": image_base64
                                }
                            }
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 512
                    }
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                result_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                
                # Parse JSON from response
                import json
                result_text = result_text.strip()
                if result_text.startswith("```"):
                    result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
                    result_text = re.sub(r'\s*```$', '', result_text)
                
                extracted = json.loads(result_text)
                logger.info(f"[TELEGRAM] Gemini Vision extracted: {extracted}")
                return extracted
            else:
                logger.error(f"[TELEGRAM] Gemini Vision API error: {response.status_code} - {response.text}")
                return {}
                
    except Exception as e:
        logger.error(f"[TELEGRAM] Error calling Gemini Vision: {e}", exc_info=True)
        return {}


async def extract_info_with_gemini(text: str) -> dict:
    """
    Use Gemini to extract structured information from message text.
    Extracts: license plate, tire size, service type, urgency.
    """
    if not GEMINI_API_KEY:
        logger.warning("[TELEGRAM] Gemini API key not configured, using regex fallback")
        return extract_info_with_regex(text)
    
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
{{"license_plate": "XX-00-XX ou null", "tire_size": "000/00 R00 ou null", "service_type": "tipo ou null", "urgency": "urgente/normal/baixa", "summary": "resumo breve"}}
"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 256
                    }
                },
                timeout=15.0
            )
            
            if response.status_code == 200:
                data = response.json()
                result_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                
                import json
                result_text = result_text.strip()
                if result_text.startswith("```"):
                    result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
                    result_text = re.sub(r'\s*```$', '', result_text)
                
                extracted = json.loads(result_text)
                logger.info(f"[TELEGRAM] Gemini extracted: {extracted}")
                return extracted
            else:
                logger.error(f"[TELEGRAM] Gemini API error: {response.status_code} - {response.text}")
                return extract_info_with_regex(text)
                
    except Exception as e:
        logger.error(f"[TELEGRAM] Error calling Gemini: {e}")
        return extract_info_with_regex(text)


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
    photo_file_ids: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """
    Process incoming Telegram message with optional photos:
    1. Download and analyze photos if present
    2. Extract information using Gemini
    3. Lookup customer by plate if found
    4. Create intake request
    5. Send confirmation to user
    """
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
    
    # Process photos first
    if photo_file_ids:
        logger.info(f"[TELEGRAM] Processing {len(photo_file_ids)} photos")
        
        for i, file_id in enumerate(photo_file_ids[:3]):  # Max 3 photos
            image_bytes = await download_telegram_file(file_id)
            
            if image_bytes:
                image_info = await analyze_image_with_gemini(image_bytes)
                
                if image_info:
                    # Merge extracted info (prefer first found values)
                    if not extracted["license_plate"] and image_info.get("license_plate"):
                        extracted["license_plate"] = image_info["license_plate"]
                    if not extracted["tire_size"] and image_info.get("tire_size"):
                        extracted["tire_size"] = image_info["tire_size"]
                    
                    # Collect descriptions
                    if image_info.get("description"):
                        desc = image_info["description"]
                        if image_info.get("tire_brand"):
                            desc += f" (Marca: {image_info['tire_brand']})"
                        if image_info.get("tire_condition"):
                            desc += f" (Estado: {image_info['tire_condition']})"
                        image_descriptions.append(desc)
            else:
                logger.warning(f"[TELEGRAM] Could not download photo {i+1}")
    
    # Extract info from text
    if message_text:
        text_extracted = await extract_info_with_gemini(message_text)
        
        # Merge with photo info (text takes precedence if photo didn't find)
        if not extracted["license_plate"]:
            extracted["license_plate"] = text_extracted.get("license_plate")
        if not extracted["tire_size"]:
            extracted["tire_size"] = text_extracted.get("tire_size")
        extracted["service_type"] = text_extracted.get("service_type")
        extracted["urgency"] = text_extracted.get("urgency", "normal")
        extracted["summary"] = text_extracted.get("summary", "")
    
    # Build combined description
    combined_text = message_text or ""
    if image_descriptions:
        if combined_text:
            combined_text += "\n\n📸 Análise das imagens:\n"
        else:
            combined_text = "📸 Análise das imagens:\n"
        combined_text += "\n".join(f"- {desc}" for desc in image_descriptions)
    
    # Lookup customer by license plate
    customer_info = None
    if extracted.get("license_plate"):
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
            attachments=[]  # Could store photo URLs here in the future
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
        if extracted.get("summary"):
            confirmation += f"\n📝 {extracted['summary']}\n"
        
        confirmation += "\nA nossa equipa irá contactá-lo em breve. Obrigado!"
        
        await send_telegram_message(chat_id, confirmation)
        
        logger.info(f"[TELEGRAM] Created intake {intake_id} from user {sender_name} ({len(photo_file_ids)} photos)")
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
