"""
WhatsApp Business Cloud API - Service
Handles message processing, ticket creation, and WhatsApp API calls
"""
import os
import re
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


def is_whatsapp_configured() -> bool:
    """Return True only when both Meta credentials are present.

    Re-reads env vars so tests can mutate them at runtime.
    """
    return bool(
        os.environ.get("WHATSAPP_ACCESS_TOKEN")
        and os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    )


class WhatsAppNotConfiguredError(RuntimeError):
    """Raised when WhatsApp send/receive cannot proceed due to missing credentials."""
    pass


async def get_or_create_ticket_for_whatsapp(
    phone: str,
    name: str,
    message_text: str,
    message_type: str = "text"
) -> Tuple[dict, bool]:
    """
    DEPRECATED in Phase 1 — kept for callers we haven't migrated yet.
    New routing logic lives in `route_inbound_message`. This function now
    only attaches to existing open tickets, NEVER creates a new ticket.
    Returns (ticket-or-None, is_new=False).
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=24)
    existing_ticket = await db.tickets.find_one({
        "customer_phone": phone,
        "status": {"$nin": ["FECHADO", "REJEITADO_LINK"]},
        "archived_at": None,
        "created_at": {"$gte": threshold.isoformat()}
    }, {"_id": 0}, sort=[("created_at", -1)])
    if existing_ticket:
        await db.tickets.update_one(
            {"id": existing_ticket["id"]},
            {"$set": {
                "last_public_message_at": now.isoformat(),
                "last_inbound_whatsapp_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }}
        )
        return existing_ticket, False
    return None, False


PORTUGUESE_PLATE_RE = re.compile(r"\b([0-9]{2}-[0-9]{2}-[A-Z]{2}|[0-9]{2}-[A-Z]{2}-[0-9]{2}|[A-Z]{2}-[0-9]{2}-[0-9]{2}|[A-Z]{2}-[0-9]{2}-[A-Z]{2})\b")


def extract_plate_from_text(text: str) -> Optional[str]:
    """Best-effort extraction of a Portuguese license plate from free text."""
    if not text:
        return None
    m = PORTUGUESE_PLATE_RE.search(text.upper().replace(" ", "-"))
    return m.group(1) if m else None


async def route_inbound_message(
    phone: str,
    name: str,
    message_text: str,
    message_type: str,
) -> Tuple[str, dict, bool]:
    """Route an inbound WhatsApp message to the correct container.

    Order:
      1. Open ticket for this phone in last 24h → attach
      2. Open intake_request (pre-ticket) for this phone → attach
      3. (no match) → create new intake_request (NEVER a final ticket)

    Returns: (parent_kind, parent_doc, is_new)
      parent_kind ∈ {"ticket", "intake"}
    """
    now = datetime.now(timezone.utc)
    threshold_24h = (now - timedelta(hours=24)).isoformat()

    # 1) Existing open ticket within 24h
    ticket = await db.tickets.find_one(
        {
            "customer_phone": phone,
            "status": {"$nin": ["FECHADO", "REJEITADO_LINK"]},
            "archived_at": None,
            "created_at": {"$gte": threshold_24h},
        },
        {"_id": 0}, sort=[("last_public_message_at", -1), ("created_at", -1)],
    )
    if ticket:
        await db.tickets.update_one(
            {"id": ticket["id"]},
            {"$set": {
                "last_public_message_at": now.isoformat(),
                "last_inbound_whatsapp_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }},
        )
        return "ticket", ticket, False

    # 2) Existing open intake (pre-ticket) for same phone
    intake = await db.intake_requests.find_one(
        {
            "$or": [{"sender_phone": phone}, {"sender_contact": phone}],
            "status": {"$in": ["PENDING", "PROCESSING", "NEW", "REVIEW", "TRIAGED"]},
        },
        {"_id": 0}, sort=[("created_at", -1)],
    )
    if intake:
        await db.intake_requests.update_one(
            {"id": intake["id"]},
            {"$set": {
                "last_inbound_whatsapp_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }},
        )
        return "intake", intake, False

    # 3) Create new intake_request (pre-ticket) — never a final ticket
    suggested_plate = extract_plate_from_text(message_text)
    suggested_ticket = None
    if suggested_plate:
        threshold_3d = (now - timedelta(days=3)).isoformat()
        suggested_ticket = await db.tickets.find_one(
            {
                "vehicle_plate": suggested_plate,
                "status": {"$nin": ["FECHADO", "REJEITADO_LINK"]},
                "archived_at": None,
                "created_at": {"$gte": threshold_3d},
            },
            {"_id": 0}, sort=[("created_at", -1)],
        )
    intake_doc = {
        "id": str(uuid.uuid4()),
        "source": "whatsapp",
        "source_type": "bot_whatsapp",
        "origin_channel": "WHATSAPP",
        "channel": "WHATSAPP",
        "source_bot": "whatsapp_meta",
        "sender_name": name or f"WhatsApp {phone[-4:]}",
        "sender_phone": phone,
        "sender_contact": phone,
        "raw_text": (message_text or "")[:2000],
        "description": (message_text or "")[:1000],
        "texts": [message_text] if message_text else [],
        "image_hints": [],
        "audio_transcripts": [],
        "attachments": [],
        "ai_extracted": None,
        "status": "PENDING",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "last_inbound_whatsapp_at": now.isoformat(),
        "suggested_plate": suggested_plate,
        "suggested_ticket_id": suggested_ticket.get("id") if suggested_ticket else None,
        "suggested_ticket_number": suggested_ticket.get("ticket_number") if suggested_ticket else None,
    }
    await db.intake_requests.insert_one(intake_doc)
    logger.info(
        "WhatsApp intake (pre-ticket) created: %s phone=%s plate=%s suggest=%s",
        intake_doc["id"], phone, suggested_plate,
        intake_doc.get("suggested_ticket_number"),
    )
    return "intake", intake_doc, True


# ============== Window 24h ==============
async def get_whatsapp_window(ticket: dict) -> dict:
    """Return WhatsApp 24h window state for a ticket-like container."""
    last_iso = ticket.get("last_inbound_whatsapp_at")
    now = datetime.now(timezone.utc)
    if not last_iso:
        return {"active": False, "last_inbound_at": None, "expires_at": None,
                "reason": "Sem mensagens inbound — janela fechada"}
    try:
        last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
    except Exception:
        return {"active": False, "last_inbound_at": last_iso, "expires_at": None,
                "reason": "Data inválida"}
    expires = last + timedelta(hours=24)
    active = now < expires
    return {
        "active": active,
        "last_inbound_at": last_iso,
        "expires_at": expires.isoformat(),
        "reason": None if active else "Mais de 24h desde a última mensagem do cliente",
    }


# ============== Templates (internal, not Meta-approved) ==============
INTERNAL_TEMPLATES = {
    "tire_size": {
        "id": "tire_size",
        "label": "Pedido de medida pneus",
        "text": "Para conseguirmos dar orçamento, envie por favor a medida dos pneus. Exemplo: 225/45R17. Também pode enviar uma foto da lateral do pneu.",
    },
    "km_request": {
        "id": "km_request",
        "label": "Pedido de KM",
        "text": "Para orçamento de mecânica, indique por favor os quilómetros atuais da viatura. Pode ser valor aproximado.",
    },
    "quote_link": {
        "id": "quote_link",
        "label": "Link de orçamento",
        "text": "Olá {{nome}}, já temos o orçamento preparado para a viatura {{matricula}}. Pode consultar e responder aqui: {{link_resposta}}\n\nObrigado,\nPneus D. Pedro V",
        "placeholders": ["nome", "matricula", "link_resposta"],
    },
    "received": {
        "id": "received",
        "label": "Pedido recebido",
        "text": "Obrigado. O seu pedido foi recebido e será analisado pela nossa equipa. Responderemos assim que possível.",
    },
}


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
    created_by_user_id: Optional[str] = None,
    channel: str = "whatsapp",
    phone_to: Optional[str] = None,
    status: str = "delivered",
    raw_payload_id: Optional[str] = None,
    template_name: Optional[str] = None,
    parent_kind: str = "ticket",
) -> dict:
    """
    Save a message to ticket_messages.
    - parent_kind="ticket" stores ticket_id field; parent_kind="intake" also stores intake_id.
    - Dedupes by external_message_id.
    - channel/phone_to/status/raw_payload_id/template_name are Phase-1 additions.
    """
    if external_message_id:
        existing = await db.ticket_messages.find_one(
            {"external_message_id": external_message_id}, {"_id": 0}
        )
        if existing:
            logger.info(
                "WhatsApp duplicate ignored (external_message_id=%s, parent=%s)",
                external_message_id, existing.get("ticket_id") or existing.get("intake_id"),
            )
            return existing

    now = datetime.now(timezone.utc)
    message_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id if parent_kind == "ticket" else None,
        "intake_id": ticket_id if parent_kind == "intake" else None,
        "body": body,
        "direction": direction.value,
        "channel": channel,
        "message_type": message_type,
        "external_message_id": external_message_id,
        "media_url": media_url,
        "media_type": media_type,
        "sender_phone": sender_phone,
        "phone_to": phone_to,
        "sender_name": sender_name,
        "status": status,
        "status_updated_at": now.isoformat(),
        "raw_payload_id": raw_payload_id,
        "template_name": template_name,
        "error": None,
        "created_at": now.isoformat(),
        "created_by_user_id": created_by_user_id,
    }
    try:
        await db.ticket_messages.insert_one(message_doc)
    except Exception as e:
        # Catch DuplicateKeyError from the unique index on external_message_id
        # (race between two webhook deliveries of the same wamid).
        if "duplicate key" in str(e).lower() and external_message_id:
            logger.info(
                "WhatsApp dedupe via unique index (external_message_id=%s)",
                external_message_id,
            )
            existing = await db.ticket_messages.find_one(
                {"external_message_id": external_message_id}, {"_id": 0}
            )
            if existing:
                return existing
        raise

    # Legacy mirror only for ticket-attached messages (kept for backward compat with other modules)
    if parent_kind == "ticket":
        legacy_msg = {
            "id": message_doc["id"],
            "ticket_id": ticket_id,
            "created_at": now.isoformat(),
            "direction": direction.value,
            "channel": "WHATSAPP",
            "body": body,
            "from_text": sender_phone if direction == TicketMessageDirection.INBOUND else None,
            "to_text": phone_to or (sender_phone if direction == TicketMessageDirection.OUTBOUND else None),
            "created_by_user_id": created_by_user_id,
        }
        await db.messages.insert_one(legacy_msg)

    return message_doc


async def save_raw_payload(payload: dict) -> str:
    """Persist the raw webhook payload (auditing). TTL index drops old docs."""
    rid = str(uuid.uuid4())
    await db.whatsapp_raw_payloads.insert_one({
        "id": rid,
        "payload": payload,
        "received_at": datetime.now(timezone.utc),
    })
    return rid


async def ensure_indexes() -> None:
    """Create TTL + helper indexes on first use. Safe to call multiple times."""
    try:
        await db.whatsapp_raw_payloads.create_index(
            "received_at", expireAfterSeconds=90 * 24 * 3600,
        )
        # Unique sparse index — DB-level guarantee against duplicate Meta wamid
        # (belt + suspenders alongside the application-level dedupe in save_ticket_message).
        await db.ticket_messages.create_index(
            "external_message_id",
            unique=True,
            sparse=True,
            name="external_message_id_unique",
        )
        await db.ticket_messages.create_index("ticket_id", sparse=True)
        await db.ticket_messages.create_index("intake_id", sparse=True)
    except Exception as e:
        logger.warning(f"[WA] ensure_indexes: {e}")


async def get_ticket_messages(ticket_id: str, limit: int = 100, parent_kind: str = "ticket") -> list:
    """Get all messages for a ticket OR pre-ticket (intake)."""
    field = "ticket_id" if parent_kind == "ticket" else "intake_id"
    messages = await db.ticket_messages.find(
        {field: ticket_id},
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
    Returns the API response or None on a transport/Meta error.
    Raises WhatsAppNotConfiguredError when credentials are missing.
    """
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
    default_phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    if not access_token:
        logger.error("WhatsApp send aborted: WHATSAPP_ACCESS_TOKEN not configured")
        raise WhatsAppNotConfiguredError("WHATSAPP_ACCESS_TOKEN missing")
    phone_id = phone_number_id or default_phone_id
    if not phone_id:
        logger.error("WhatsApp send aborted: WHATSAPP_PHONE_NUMBER_ID not configured")
        raise WhatsAppNotConfiguredError("WHATSAPP_PHONE_NUMBER_ID missing")
    
    url = f"{WHATSAPP_API_BASE}/{phone_id}/messages"
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message_text}
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
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
