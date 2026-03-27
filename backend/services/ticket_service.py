"""
Ticket Service Module.
Contains helper functions for ticket operations.
"""
import logging
import uuid
from datetime import datetime, timezone

from db import db

logger = logging.getLogger(__name__)


def generate_ticket_number():
    """Generate a unique ticket number."""
    now = datetime.now(timezone.utc)
    return f"TK{now.strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"


async def log_status_change(ticket_id: str, old_status: str | None, new_status: str, user_id: str):
    """Log a status change to the ticket_status_history collection"""
    history_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "old_status": old_status,
        "new_status": new_status,
        "changed_by_user_id": user_id,
        "changed_at": datetime.now(timezone.utc).isoformat()
    }
    await db.ticket_status_history.insert_one(history_doc)


async def log_quote_change(ticket_id: str, old_value: float | None, new_value: float, user_id: str, reason: str | None = None):
    """Log a quote value change to history"""
    history_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "old_value": old_value,
        "new_value": new_value,
        "changed_by_user_id": user_id,
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason
    }
    await db.quote_history.insert_one(history_doc)


async def get_or_create_reply_token(ticket_id: str) -> str:
    """Get existing reply token or create a new one for the ticket."""
    from datetime import timedelta
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0, "reply_link_token": 1})
    if ticket and ticket.get("reply_link_token"):
        return ticket["reply_link_token"]
    token = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    reply_link_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
        "created_by_user_id": None
    }
    await db.reply_links.insert_one(reply_link_doc)
    await db.tickets.update_one({"id": ticket_id}, {"$set": {"reply_link_token": token}})
    return token


# Rejection reason codes (centralized)
REJECTION_REASON_CODES = {
    "preco_alto": "Preço alto",
    "vai_pedir_outra_opiniao": "Vai pedir outra opinião/orçamento",
    "resolveu_noutro_local": "Já resolveu noutro local",
    "nao_quer_avancar": "Não quer avançar para já",
    "nao_entendeu": "Não entendeu o orçamento",
    "quer_falar_primeiro": "Quer falar com a oficina primeiro",
    "outro": "Outro"
}
