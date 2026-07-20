"""
Telegram Module Routes v3
API endpoints for Telegram bot webhook with message buffering.
Waits 15 seconds to collect multiple messages from the same user before processing.
"""
import logging
import os
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from typing import Optional, Dict, List
from datetime import datetime, timezone

from core.security import get_current_user
from .models import TelegramUpdate, WebhookSetupRequest, TelegramPhoto
from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Message buffer: chat_id -> {messages: [], photos: [], timer_task: asyncio.Task, last_update: datetime}
message_buffer: Dict[int, dict] = {}
BUFFER_WAIT_SECONDS = 15


async def process_buffered_messages(chat_id: int):
    """Process all buffered messages for a chat after the wait period."""
    await asyncio.sleep(BUFFER_WAIT_SECONDS)
    
    if chat_id not in message_buffer:
        return
    
    buffer = message_buffer.pop(chat_id)
    messages = buffer.get("messages", [])
    photos = buffer.get("photos", [])
    voice = buffer.get("voice")
    user_info = buffer.get("user_info", {})
    
    if not messages and not photos and not voice:
        return
    
    logger.info(f"[TELEGRAM] Processing buffer for chat {chat_id}: {len(messages)} texts, {len(photos)} photos, voice={bool(voice)}")
    
    # Combine all text messages
    combined_text = "\n".join(messages)
    
    # Process with service
    try:
        success, result = await service.process_telegram_message(
            chat_id=chat_id,
            user_id=user_info.get("user_id", 0),
            username=user_info.get("username"),
            first_name=user_info.get("first_name", "Cliente"),
            last_name=user_info.get("last_name"),
            message_text=combined_text,
            photo_file_ids=photos,
            voice_file_id=voice
        )
        logger.info(f"[TELEGRAM] Buffer processed: success={success}, result={result}")
    except Exception as e:
        logger.error(f"[TELEGRAM] Error processing buffer: {e}")


def add_to_buffer(chat_id: int, text: Optional[str], photo_file_id: Optional[str], voice_file_id: Optional[str], user_info: dict):
    """Add a message, photo, or voice to the buffer and reset the timer."""
    if chat_id not in message_buffer:
        message_buffer[chat_id] = {
            "messages": [],
            "photos": [],
            "voice": None,
            "user_info": user_info,
            "timer_task": None
        }
    
    buffer = message_buffer[chat_id]
    
    # Cancel existing timer
    if buffer["timer_task"] and not buffer["timer_task"].done():
        buffer["timer_task"].cancel()
    
    # Add content
    if text:
        buffer["messages"].append(text)
    if photo_file_id:
        buffer["photos"].append(photo_file_id)
    if voice_file_id:
        buffer["voice"] = voice_file_id  # Only keep the last voice message
    
    # Update user info (in case it changed)
    buffer["user_info"] = user_info
    
    # Start new timer
    buffer["timer_task"] = asyncio.create_task(process_buffered_messages(chat_id))
    
    logger.info(f"[TELEGRAM] Added to buffer for chat {chat_id}: text={bool(text)}, photo={bool(photo_file_id)}, voice={bool(voice_file_id)}, "
                f"total_messages={len(buffer['messages'])}, total_photos={len(buffer['photos'])}")


@router.post("/setup-webhook")
async def auto_setup_webhook(request: Request):
    """
    Auto-configure Telegram webhook based on request host.
    PUBLIC endpoint for easy setup.
    """
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", "https")
    
    if not host:
        raise HTTPException(status_code=400, detail="Could not determine host")
    
    webhook_url = f"{scheme}://{host}/api/telegram/webhook"
    
    success, message = await service.setup_webhook(webhook_url)
    
    if success:
        return {
            "ok": True,
            "message": "Webhook configurado com sucesso",
            "webhook_url": webhook_url
        }
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/webhook")
async def telegram_webhook_deprecated(request: Request):
    """DEPRECATED — Principal bot (@PDPV_OFICINA_BOT) consolidated into @pdpv_interno_bot.
    Returns 200 OK so Telegram stops retrying.
    """
    return {"status": "deprecated", "message": "Bot consolidated into @pdpv_interno_bot"}


@router.post("/webhook/legacy")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Telegram webhook endpoint v3 with message buffering (LEGACY, unrouted).
    Waits 15 seconds to collect multiple messages before processing.
    Supports: text, photos, voice messages, and audio files.
    """
    try:
        body = await request.json()
        logger.info(f"[TELEGRAM] Received webhook: {body}")
        
        update = TelegramUpdate(**body)
        
        if update.message:
            msg = update.message
            user = msg.from_user
            
            if not user:
                logger.warning("[TELEGRAM] Message has no sender info")
                return {"ok": True, "action": "skipped", "reason": "no_user"}
            
            # Get text (from text or caption)
            text = msg.text or msg.caption
            
            # Get photo file_id (use largest photo)
            photo_file_id = None
            if msg.photo and len(msg.photo) > 0:
                largest_photo = max(msg.photo, key=lambda p: p.file_size or 0)
                photo_file_id = largest_photo.file_id
                print(f"[TELEGRAM] Photo received, file_id: {photo_file_id[:30]}..., size: {largest_photo.file_size}")
                logger.info(f"[TELEGRAM] Photo received: {photo_file_id}")
            
            # Get voice/audio file_id
            voice_file_id = None
            if msg.voice:
                voice_file_id = msg.voice.file_id
                print(f"[TELEGRAM] Voice message received, file_id: {voice_file_id[:30]}..., duration: {msg.voice.duration}s")
                logger.info(f"[TELEGRAM] Voice message received: {voice_file_id}")
            elif msg.audio:
                voice_file_id = msg.audio.file_id
                print(f"[TELEGRAM] Audio file received, file_id: {voice_file_id[:30]}..., duration: {msg.audio.duration}s")
                logger.info(f"[TELEGRAM] Audio file received: {voice_file_id}")
            
            # Skip if no content at all
            if not text and not photo_file_id and not voice_file_id:
                logger.info("[TELEGRAM] Message has no processable content, skipping")
                return {"ok": True, "action": "skipped", "reason": "no_content"}
            
            # Handle bot commands
            if text and text.startswith("/"):
                logger.info(f"[TELEGRAM] Bot command: {text.split()[0]}")
                
                if text.lower().startswith("/start"):
                    first_name = user.first_name if user else "Cliente"
                    welcome_msg = f"""👋 <b>Bem-vindo aos Pneus D. Pedro V!</b>

Olá {first_name}! Sou o assistente virtual da oficina.

📝 <b>Como posso ajudar?</b>
Envie-me uma mensagem com:
• A matrícula do seu veículo
• A medida dos pneus (ex: 205/55 R16)
• O que precisa (orçamento, marcação, etc.)

📸 <b>Pode também enviar:</b>
• Fotos do pneu ou matrícula
• 🎤 Mensagens de voz

Exemplo:
<i>"Preciso de orçamento para 4 pneus 205/55 R16 para o carro AA-00-BB"</i>

A nossa equipa responderá brevemente! 🚗"""
                    await service.send_telegram_message(msg.chat.id, welcome_msg)
                
                return {"ok": True, "action": "skipped", "reason": "bot_command"}
            
            # Prepare user info
            user_info = {
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
            
            # Add to buffer (this resets the 15-second timer)
            add_to_buffer(
                chat_id=msg.chat.id,
                text=text,
                photo_file_id=photo_file_id,
                voice_file_id=voice_file_id,
                user_info=user_info
            )
            
            return {
                "ok": True,
                "action": "buffered",
                "buffer_size": len(message_buffer.get(msg.chat.id, {}).get("messages", [])),
                "photos_count": len(message_buffer.get(msg.chat.id, {}).get("photos", [])),
                "has_voice": message_buffer.get(msg.chat.id, {}).get("voice") is not None
            }
        
        return {"ok": True, "action": "skipped", "reason": "not_a_message"}
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Webhook error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


@router.get("/status")
async def get_telegram_status(current_user: dict = Depends(get_current_user)):
    """Get Telegram bot status and webhook info."""
    webhook_info = await service.get_webhook_info()
    
    return {
        "bot_configured": bool(service.get_bot_token()),
        "llm_configured": bool(service.EMERGENT_LLM_KEY),
        "llm_provider": f"{service.LLM_PROVIDER}/{service.LLM_MODEL}",
        "webhook": webhook_info,
        "buffer_info": {
            "active_buffers": len(message_buffer),
            "buffer_wait_seconds": BUFFER_WAIT_SECONDS
        },
        "features": {
            "text_analysis": True,
            "image_vision": True,
            "audio_transcription": True
        }
    }


@router.post("/webhook/setup")
async def setup_telegram_webhook(
    data: WebhookSetupRequest,
    current_user: dict = Depends(get_current_user)
):
    """Setup Telegram webhook URL. Admin only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem configurar o webhook")
    
    success, message = await service.setup_webhook(data.webhook_url)
    
    if success:
        return {"ok": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.delete("/webhook")
async def delete_telegram_webhook(current_user: dict = Depends(get_current_user)):
    """Delete Telegram webhook. Admin only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem remover o webhook")
    
    success, message = await service.delete_webhook()
    
    if success:
        return {"ok": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/test")
async def test_telegram_message(current_user: dict = Depends(get_current_user)):
    """Test Telegram bot configuration."""
    webhook_info = await service.get_webhook_info()
    
    if "error" in webhook_info:
        raise HTTPException(status_code=400, detail=webhook_info["error"])
    
    return {
        "ok": True,
        "message": "Bot está configurado corretamente",
        "webhook_url": webhook_info.get("url", "Not set"),
        "pending_update_count": webhook_info.get("pending_update_count", 0)
    }
