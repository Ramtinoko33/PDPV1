"""
Telegram Module Routes
API endpoints for Telegram bot webhook and management.
"""
import logging
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional

from core.security import get_current_user
from .models import TelegramUpdate, WebhookSetupRequest
from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/setup-webhook")
async def auto_setup_webhook(request: Request):
    """
    Auto-configure Telegram webhook based on request host.
    PUBLIC endpoint for easy setup.
    """
    # Get the host from the request
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
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.
    Receives updates from Telegram and processes messages.
    This endpoint is PUBLIC (no auth) - called by Telegram servers.
    """
    try:
        # Parse the incoming update
        body = await request.json()
        logger.info(f"[TELEGRAM] Received webhook: {body}")
        
        update = TelegramUpdate(**body)
        
        if update.message:
            msg = update.message
            
            # Skip if no text and no caption
            text = msg.text or msg.caption
            if not text:
                logger.info("[TELEGRAM] Message has no text, skipping")
                return {"ok": True, "action": "skipped", "reason": "no_text"}
            
            # Get user info
            user = msg.from_user
            if not user:
                logger.warning("[TELEGRAM] Message has no sender info")
                return {"ok": True, "action": "skipped", "reason": "no_user"}
            
            # Process the message
            success, result = await service.process_telegram_message(
                chat_id=msg.chat.id,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                message_text=text
            )
            
            return {
                "ok": True,
                "action": "processed",
                "success": success,
                "intake_id": result if success else None
            }
        
        return {"ok": True, "action": "skipped", "reason": "not_a_message"}
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Webhook error: {e}")
        # Always return 200 to Telegram to avoid retries
        return {"ok": False, "error": str(e)}


@router.get("/status")
async def get_telegram_status(current_user: dict = Depends(get_current_user)):
    """Get Telegram bot status and webhook info."""
    webhook_info = await service.get_webhook_info()
    
    return {
        "bot_configured": bool(service.get_bot_token()),
        "gemini_configured": bool(service.GEMINI_API_KEY),
        "webhook": webhook_info
    }


@router.post("/webhook/setup")
async def setup_telegram_webhook(
    data: WebhookSetupRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Setup Telegram webhook URL.
    Only admins can configure the webhook.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem configurar o webhook")
    
    success, message = await service.setup_webhook(data.webhook_url)
    
    if success:
        return {"ok": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.delete("/webhook")
async def delete_telegram_webhook(current_user: dict = Depends(get_current_user)):
    """Delete Telegram webhook."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem remover o webhook")
    
    success, message = await service.delete_webhook()
    
    if success:
        return {"ok": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/test")
async def test_telegram_message(current_user: dict = Depends(get_current_user)):
    """
    Test Telegram bot by sending a test message.
    Uses the admin's Telegram ID if configured.
    """
    # For testing, we'll just verify the bot token is valid
    webhook_info = await service.get_webhook_info()
    
    if "error" in webhook_info:
        raise HTTPException(status_code=400, detail=webhook_info["error"])
    
    return {
        "ok": True,
        "message": "Bot está configurado corretamente",
        "webhook_url": webhook_info.get("url", "Not set"),
        "pending_update_count": webhook_info.get("pending_update_count", 0)
    }
