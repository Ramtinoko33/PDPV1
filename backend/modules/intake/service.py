"""
Intake Module - Service
Business logic for intake requests.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from db import db
from .models import IntakeStatus


async def create_intake_request(
    source: str,
    sender_name: str,
    sender_contact: str,
    raw_text: str,
    license_plate: Optional[str] = None,
    tire_size: Optional[str] = None,
    attachments: list = None
) -> dict:
    """Create a new intake request."""
    now = datetime.now(timezone.utc).isoformat()
    intake_id = str(uuid.uuid4())
    
    doc = {
        "id": intake_id,
        "source": source,
        "sender_name": sender_name,
        "sender_contact": sender_contact,
        "raw_text": raw_text,
        "license_plate": license_plate,
        "tire_size": tire_size,
        "attachments": attachments or [],
        "status": IntakeStatus.PENDING.value,
        "created_at": now,
        "converted_ticket_id": None,
        "converted_at": None
    }
    
    await db.intake_requests.insert_one(doc)
    return doc


async def get_intake_request(intake_id: str) -> Optional[dict]:
    """Get intake request by ID."""
    return await db.intake_requests.find_one({"id": intake_id}, {"_id": 0})


async def list_intake_requests(
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> list:
    """List intake requests with optional filters."""
    query = {}
    if status:
        query["status"] = status
    if source:
        query["source"] = source
    
    cursor = db.intake_requests.find(query, {"_id": 0})
    cursor = cursor.sort("created_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(limit)


async def update_intake_request(intake_id: str, updates: dict) -> Optional[dict]:
    """Update intake request."""
    result = await db.intake_requests.update_one(
        {"id": intake_id},
        {"$set": updates}
    )
    if result.modified_count > 0:
        return await get_intake_request(intake_id)
    return None


async def delete_intake_request(intake_id: str) -> bool:
    """Delete intake request."""
    result = await db.intake_requests.delete_one({"id": intake_id})
    return result.deleted_count > 0


async def mark_as_converted(intake_id: str, ticket_id: str) -> Optional[dict]:
    """Mark intake request as converted to ticket."""
    now = datetime.now(timezone.utc).isoformat()
    return await update_intake_request(intake_id, {
        "status": IntakeStatus.CONVERTED.value,
        "converted_ticket_id": ticket_id,
        "converted_at": now
    })
