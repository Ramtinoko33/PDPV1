"""
WhatsApp Business Cloud API - Service
Handles message processing, ticket creation, and WhatsApp API calls
"""
import os
import uuid
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from db import db
from .models import WhatsAppMessageType, TicketMessageDirection

logger = logging.getLogger(__name__)

# WhatsApp API Configuration
WHATSAPP_API_VERSION = "v18.0"
WHATSAPP_API_BASE = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")


async def get_or_create_ticket_for_whatsapp(
    phone: str,
    name: str,
    message_text: str,
    message_type: str = "text"
) -> Tuple[dict, bool]:
    """
    Find existing open ticket for phone number or create new one.
    Returns (ticket, is_new)
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=48)  # 48h window for same conversation
    
    # Find existing open ticket for this phone
    existing_ticket = await db.tickets.find_one({
        "customer_phone": phone,
        "status": {"$nin": ["FECHADO", "REJEITADO_LINK", "AGENDADO"]},
        "archived_at": None,
        "created_at": {"$gte": threshold.isoformat()}
    }, {"_id": 0}, sort=[("created_at", -1)])
    
    if existing_ticket:
        # Update ticket timestamp
        await db.tickets.update_one(
            {"id": existing_ticket["id"]},
            {"$set": {
                "last_public_message_at": now.isoformat(),
                "updated_at": now.isoformat()
            }}
        )
        return existing_ticket, False
    
    # Create new ticket
    # Import here to avoid circular imports
    from server import generate_ticket_number, compute_sla_due
    
    ticket_id = str(uuid.uuid4())
    ticket_number = generate_ticket_number()
    sla_due, sla_target_minutes, sla_policy_key = compute_sla_due(
        ticket_type="INFORMACAO",
        created_at=now
    )
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": "WHATSAPP",
        "type": "INFORMACAO",
        "status": "ABERTO",
        "priority": "NORMAL",
        "description": message_text[:500] if message_text else f"Mensagem {message_type} via WhatsApp",
        "customer_name": name or f"WhatsApp {phone[-4:]}",
        "customer_phone": phone,
        "customer_email": None,
        "vehicle_plate": None,
        "assigned_to_user_id": None,
        "assigned_to_name": None,
        "last_public_message_at": now.isoformat(),
        "first_response_done": False,
        "sla_due": sla_due.isoformat(),
        "sla_started_at": now.isoformat(),
        "sla_paused_at": None,
        "sla_paused_minutes": 0,
        "sla_breached": False,
        "sla_breached_at": None,
        "sla_target_minutes": sla_target_minutes,
        "sla_policy_key": sla_policy_key,
        "quote_sent": False,
        "quote_value": None,
        "created_by_user_id": None,
        "created_by_name": "WhatsApp Bot",
        "customer_id": None,
        "vehicle_id": None,
        "archived_at": None,
        "archived_by": None,
        "whatsapp_conversation": True,  # Flag for WhatsApp tickets
        "origin": "whatsapp"
    }
    
    await db.tickets.insert_one(ticket_doc)
    logger.info(f"Created new WhatsApp ticket: {ticket_number} for phone {phone}")
    
    return ticket_doc, True


async def save_ticket_message(
    ticket_id: str,
    body: str,
    direction: TicketMessageDirection,
    message_type: str = "text",
    external_message_id: Optional[str] = None,
    media_url: Optional[str] = None,
    media_type: Optional[str] = None,
    sender_phone: Optional[str] = None,
    sender_name: Optional[str] = None,
    created_by_user_id: Optional[str] = None
) -> dict:
    """
    Save a message to the ticket_messages collection.
    Avoids duplicates by checking external_message_id.
    """
    # Check for duplicate by external_message_id
    if external_message_id:
        existing = await db.ticket_messages.find_one(
            {"external_message_id": external_message_id},
            {"_id": 0}
        )
        if existing:
            logger.debug(f"Duplicate message ignored: {external_message_id}")
            return existing
    
    now = datetime.now(timezone.utc)
    
    message_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "body": body,
        "direction": direction.value,
        "message_type": message_type,
        "external_message_id": external_message_id,
        "media_url": media_url,
        "media_type": media_type,
        "sender_phone": sender_phone,
        "sender_name": sender_name,
        "created_at": now.isoformat(),
        "created_by_user_id": created_by_user_id
    }
    
    await db.ticket_messages.insert_one(message_doc)
    
    # Also save to legacy messages collection for compatibility
    legacy_msg = {
        "id": message_doc["id"],
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "direction": direction.value,
        "channel": "WHATSAPP",
        "body": body,
        "from_text": sender_phone if direction == TicketMessageDirection.INBOUND else None,
        "to_text": sender_phone if direction == TicketMessageDirection.OUTBOUND else None,
        "created_by_user_id": created_by_user_id
    }
    await db.messages.insert_one(legacy_msg)
    
    return message_doc


async def get_ticket_messages(ticket_id: str, limit: int = 100) -> list:
    """Get all messages for a ticket"""
    messages = await db.ticket_messages.find(
        {"ticket_id": ticket_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    
    return messages


async def download_whatsapp_media(media_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Download media from WhatsApp servers.
    Returns (content_bytes, content_type) or (None, None) on failure.
    """
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN not configured")
        return None, None
    
    try:
        # Step 1: Get media URL
        url = f"{WHATSAPP_API_BASE}/{media_id}"
        headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            media_data = response.json()
            media_url = media_data.get("url")
            
            if not media_url:
                logger.error(f"No URL in media response for {media_id}")
                return None, None
            
            # Step 2: Download the actual file
            download_response = await client.get(
                media_url,
                headers=headers,
                timeout=60
            )
            download_response.raise_for_status()
            
            content_type = download_response.headers.get("Content-Type", "application/octet-stream")
            return download_response.content, content_type
    
    except Exception as e:
        logger.error(f"Error downloading media {media_id}: {e}")
        return None, None


async def send_whatsapp_message(
    to_phone: str,
    message_text: str,
    phone_number_id: Optional[str] = None
) -> Optional[dict]:
    """
    Send a text message via WhatsApp Cloud API.
    Returns the API response or None on failure.
    """
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN not configured")
        return None
    
    phone_id = phone_number_id or WHATSAPP_PHONE_NUMBER_ID
    if not phone_id:
        logger.error("WHATSAPP_PHONE_NUMBER_ID not configured")
        return None
    
    url = f"{WHATSAPP_API_BASE}/{phone_id}/messages"
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message_text}
    }
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            logger.info(f"WhatsApp message sent to {to_phone}")
            return result
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {to_phone}: {e}")
        return None


async def mark_message_as_read(message_id: str, phone_number_id: Optional[str] = None) -> bool:
    """Mark a WhatsApp message as read"""
    if not WHATSAPP_ACCESS_TOKEN:
        return False
    
    phone_id = phone_number_id or WHATSAPP_PHONE_NUMBER_ID
    if not phone_id:
        return False
    
    url = f"{WHATSAPP_API_BASE}/{phone_id}/messages"
    
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id
    }
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to mark message as read: {e}")
        return False
