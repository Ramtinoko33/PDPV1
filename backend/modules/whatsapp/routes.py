"""
WhatsApp Business Cloud API - Routes
Webhook endpoints for receiving and sending messages
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse

from db import db
from core.security import get_current_user
from .models import (
    WhatsAppWebhookPayload,
    WhatsAppMessageType,
    TicketMessageDirection,
    TicketMessageResponse
)
from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Configuration
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "pdpv_whatsapp_verify_2024")


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Webhook verification endpoint for WhatsApp Cloud API.
    Meta sends GET request with hub.mode, hub.verify_token, and hub.challenge.
    """
    logger.info("WhatsApp webhook verification request received")
    
    # Validate parameters
    if not all([hub_mode, hub_verify_token, hub_challenge]):
        logger.warning("Missing verification parameters")
        raise HTTPException(status_code=400, detail="Missing required parameters")
    
    if hub_mode != "subscribe":
        logger.warning(f"Invalid hub.mode: {hub_mode}")
        raise HTTPException(status_code=400, detail="Invalid hub.mode")
    
    if hub_verify_token != WHATSAPP_VERIFY_TOKEN:
        logger.warning("Invalid verification token")
        raise HTTPException(status_code=403, detail="Invalid verification token")
    
    logger.info("WhatsApp webhook verified successfully")
    return PlainTextResponse(hub_challenge)


@router.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive incoming WhatsApp messages and status updates.
    Returns 200 immediately and processes in background.
    """
    try:
        data = await request.json()
        logger.info(f"WhatsApp webhook received")
        
        # Process in background to return quickly
        background_tasks.add_task(process_webhook_payload, data)
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return {"status": "ok"}  # Always return 200 to avoid retries


async def process_webhook_payload(data: dict):
    """Process the webhook payload in background"""
    try:
        # Validate object type
        if data.get("object") != "whatsapp_business_account":
            logger.debug(f"Ignoring non-WhatsApp object: {data.get('object')}")
            return
        
        # Process each entry
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # Get phone number ID from metadata
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                
                # Process messages
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])
                
                for message in messages:
                    await process_incoming_message(message, contacts, phone_number_id)
                
                # Process status updates (optional)
                statuses = value.get("statuses", [])
                for status in statuses:
                    await process_status_update(status)
    
    except Exception as e:
        logger.error(f"Error processing webhook payload: {e}")


async def process_incoming_message(message: dict, contacts: list, phone_number_id: str):
    """Process a single incoming WhatsApp message"""
    try:
        from_phone = message.get("from")
        message_id = message.get("id")
        timestamp = message.get("timestamp")
        message_type = message.get("type", "unknown")
        
        # Get contact name if available
        sender_name = None
        for contact in contacts:
            if contact.get("wa_id") == from_phone:
                profile = contact.get("profile", {})
                sender_name = profile.get("name")
                break
        
        if not sender_name:
            sender_name = f"WhatsApp {from_phone[-4:]}"
        
        logger.info(f"Processing {message_type} message from {from_phone}")
        
        # Extract message content based on type
        body = ""
        media_url = None
        media_type = None
        
        if message_type == "text":
            text_content = message.get("text", {})
            body = text_content.get("body", "")
        
        elif message_type in ["image", "document", "audio", "video"]:
            media_content = message.get(message_type, {})
            media_id = media_content.get("id")
            media_type = media_content.get("mime_type")
            caption = media_content.get("caption", "")
            filename = media_content.get("filename", "")
            
            body = caption or f"[{message_type.upper()}] {filename or media_id}"
            
            # Download media if configured
            if media_id and os.environ.get("WHATSAPP_ACCESS_TOKEN"):
                content, content_type = await service.download_whatsapp_media(media_id)
                if content:
                    # Save to object storage or local
                    # For now, just note the media_id
                    media_url = f"whatsapp://media/{media_id}"
                    media_type = content_type
        
        elif message_type == "location":
            location = message.get("location", {})
            lat = location.get("latitude")
            lon = location.get("longitude")
            name = location.get("name", "")
            body = f"[LOCALIZAÇÃO] {name} ({lat}, {lon})" if name else f"[LOCALIZAÇÃO] ({lat}, {lon})"
        
        elif message_type == "contacts":
            body = "[CONTACTOS]"
        
        elif message_type == "sticker":
            body = "[STICKER]"
        
        else:
            body = f"[{message_type.upper()}]"
        
        # Get or create ticket
        ticket, is_new = await service.get_or_create_ticket_for_whatsapp(
            phone=from_phone,
            name=sender_name,
            message_text=body,
            message_type=message_type
        )
        
        # Save message
        await service.save_ticket_message(
            ticket_id=ticket["id"],
            body=body,
            direction=TicketMessageDirection.INBOUND,
            message_type=message_type,
            external_message_id=message_id,
            media_url=media_url,
            media_type=media_type,
            sender_phone=from_phone,
            sender_name=sender_name
        )
        
        # Mark as read
        await service.mark_message_as_read(message_id, phone_number_id)
        
        # Create notification for new tickets
        if is_new:
            await create_whatsapp_notification(ticket, sender_name, from_phone)
        
        logger.info(f"Message processed for ticket {ticket['ticket_number']}")
    
    except Exception as e:
        logger.error(f"Error processing message: {e}")


async def process_status_update(status: dict):
    """Process message delivery status update"""
    message_id = status.get("id")
    status_value = status.get("status")  # sent, delivered, read, failed
    timestamp = status.get("timestamp")
    
    logger.debug(f"Status update: {message_id} is {status_value}")
    
    # Optionally update message status in database
    if message_id and status_value:
        await db.ticket_messages.update_one(
            {"external_message_id": message_id},
            {"$set": {
                "delivery_status": status_value,
                "delivery_status_at": timestamp
            }}
        )


async def create_whatsapp_notification(ticket: dict, sender_name: str, phone: str):
    """Create alert for new WhatsApp ticket"""
    import uuid
    
    alert_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "alert_type": "FOLLOWUP",
        "body": f"Nova conversa WhatsApp de {sender_name} ({phone})",
        "is_resolved": False
    }
    await db.alerts.insert_one(alert_doc)


# ============== API ENDPOINTS ==============

@router.get("/tickets/{ticket_id}/messages", response_model=list[TicketMessageResponse])
async def get_conversation_messages(
    ticket_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user)
):
    """Get all messages for a ticket conversation"""
    messages = await service.get_ticket_messages(ticket_id, limit)
    return messages


@router.post("/tickets/{ticket_id}/messages")
async def send_reply_message(
    ticket_id: str,
    body: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user)
):
    """Send a reply message to the customer via WhatsApp"""
    # Get ticket
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    phone = ticket.get("customer_phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Ticket sem número de telefone")
    
    # Send via WhatsApp
    result = await service.send_whatsapp_message(phone, body)
    
    if not result:
        raise HTTPException(status_code=500, detail="Falha ao enviar mensagem WhatsApp")
    
    # Save outbound message
    message_id = result.get("messages", [{}])[0].get("id")
    
    await service.save_ticket_message(
        ticket_id=ticket_id,
        body=body,
        direction=TicketMessageDirection.OUTBOUND,
        message_type="text",
        external_message_id=message_id,
        sender_phone=None,
        sender_name=current_user.get("name"),
        created_by_user_id=current_user.get("id")
    )
    
    # Mark first response done
    if not ticket.get("first_response_done"):
        await db.tickets.update_one(
            {"id": ticket_id},
            {"$set": {"first_response_done": True}}
        )
    
    return {"success": True, "message_id": message_id}
