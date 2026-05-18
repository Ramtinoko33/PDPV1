"""
WhatsApp Business Cloud API - Routes
Webhook endpoints for receiving and sending messages
"""
import os
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

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


def _is_production() -> bool:
    """Return True when running in a production environment.

    Looks at ENVIRONMENT/APP_ENV/NODE_ENV env vars. Defaults to development
    so local tests never inadvertently block on missing app secret.
    """
    env = (
        os.environ.get("ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or os.environ.get("NODE_ENV")
        or "development"
    ).strip().lower()
    return env in ("prod", "production")


def _verify_meta_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Validate the `X-Hub-Signature-256` header against `WHATSAPP_APP_SECRET`.

    Returns True when the header matches the HMAC SHA-256 digest of the raw body.
    Returns False otherwise (missing header, wrong format, mismatch).
    """
    app_secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not app_secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received = signature_header.split("=", 1)[1].strip()
    expected = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


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

    Security:
    - In production (`ENVIRONMENT=production`), `X-Hub-Signature-256` MUST be present
      and HMAC SHA-256(WHATSAPP_APP_SECRET, raw_body) MUST match. Otherwise → 403.
    - In development, when `WHATSAPP_APP_SECRET` is unset, the signature check is
      skipped but a clear warning is logged on every request.

    Returns 200 immediately and processes the payload in a background task.
    """
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256") or request.headers.get(
        "X-Hub-Signature-256"
    )
    app_secret_present = bool(os.environ.get("WHATSAPP_APP_SECRET"))
    in_production = _is_production()

    # Enforce signature in production
    if in_production:
        if not app_secret_present:
            logger.error(
                "WhatsApp webhook in production but WHATSAPP_APP_SECRET is missing; rejecting"
            )
            raise HTTPException(status_code=503, detail="WhatsApp not configured")
        if not _verify_meta_signature(raw_body, signature):
            logger.warning(
                "Rejecting WhatsApp webhook: invalid or missing X-Hub-Signature-256"
            )
            raise HTTPException(status_code=403, detail="Invalid signature")
    else:
        # Development / test: validate only if both secret and header present, warn otherwise
        if app_secret_present and signature:
            if not _verify_meta_signature(raw_body, signature):
                logger.warning(
                    "Rejecting WhatsApp webhook in dev: signature header present but invalid"
                )
                raise HTTPException(status_code=403, detail="Invalid signature")
        else:
            logger.warning(
                "WhatsApp webhook: skipping signature check (development mode; "
                "app_secret_present=%s, signature_present=%s)",
                app_secret_present,
                bool(signature),
            )

    try:
        import json as _json
        data = _json.loads(raw_body or b"{}")
        logger.info("WhatsApp webhook accepted (%d bytes)", len(raw_body or b""))
        background_tasks.add_task(process_webhook_payload, data)
        return {"status": "ok"}
    except Exception as e:
        # Always return 200 to avoid Meta retries, but log the failure
        logger.error("Error parsing WhatsApp webhook payload: %s", e)
        return {"status": "ok"}


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
        if is_new:
            logger.info(
                "WhatsApp ticket created: %s (phone=%s, type=%s)",
                ticket.get("ticket_number"), from_phone, message_type,
            )
        else:
            logger.info(
                "WhatsApp ticket reused: %s (phone=%s)",
                ticket.get("ticket_number"), from_phone,
            )

        # Save message (service already de-duplicates by external_message_id)
        saved = await service.save_ticket_message(
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
        if saved and saved.get("external_message_id") == message_id and saved.get("body") == body:
            # save_ticket_message returns existing doc when duplicate
            pass
        
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


class WhatsAppReplyBody(BaseModel):
    body: str = Field(..., min_length=1, description="Message text to send to the customer")


@router.post("/tickets/{ticket_id}/messages")
async def send_reply_message(
    ticket_id: str,
    payload: Optional[WhatsAppReplyBody] = None,
    body: Optional[str] = Query(None, min_length=1, description="DEPRECATED: use JSON body instead"),
    current_user: dict = Depends(get_current_user)
):
    """Send a reply message to the customer via WhatsApp.

    Accepts JSON body: ``{"body": "..."}`` (preferred).
    Also accepts the legacy ``?body=`` query param for backwards compatibility — this
    will be removed once all callers migrate to JSON.

    Errors:
    - 400 if no body provided in either format.
    - 404 if ticket not found.
    - 503 ``WhatsApp not configured`` when access token / phone number id missing.
    - 502 ``WhatsApp upstream error`` when Meta Graph API rejects the request.
    """
    # Resolve message text from JSON body or legacy query param
    message_text = (payload.body if payload else None) or body
    if not message_text or not message_text.strip():
        raise HTTPException(status_code=400, detail="Body required")

    # Fail fast if WhatsApp not configured (avoid generic 500)
    if not service.is_whatsapp_configured():
        logger.error(
            "WhatsApp reply blocked: credentials missing (ticket=%s, user=%s)",
            ticket_id, current_user.get("id"),
        )
        raise HTTPException(status_code=503, detail="WhatsApp not configured")

    # Get ticket
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")

    phone = ticket.get("customer_phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Ticket sem número de telefone")

    # Send via WhatsApp
    try:
        result = await service.send_whatsapp_message(phone, message_text)
    except service.WhatsAppNotConfiguredError:
        raise HTTPException(status_code=503, detail="WhatsApp not configured")

    if not result:
        raise HTTPException(status_code=502, detail="WhatsApp upstream error")

    # Save outbound message
    message_id = result.get("messages", [{}])[0].get("id")

    await service.save_ticket_message(
        ticket_id=ticket_id,
        body=message_text,
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
