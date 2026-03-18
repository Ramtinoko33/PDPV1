"""
Intake Module - Service
Business logic for intake requests.
"""
import uuid
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from math import ceil

from db import db
from .models import IntakeStatus, IntakeSourceType


async def create_intake_request(
    source: str,
    sender_name: str,
    sender_contact: str,
    raw_text: str,
    source_type: IntakeSourceType = IntakeSourceType.MANUAL,
    sender_email: Optional[str] = None,
    telegram_username: Optional[str] = None,
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
        "source_type": source_type.value if isinstance(source_type, IntakeSourceType) else source_type,
        "sender_name": sender_name,
        "sender_contact": sender_contact,  # Phone number only
        "sender_email": sender_email,
        "telegram_username": telegram_username,  # Telegram username stored separately
        "raw_text": raw_text,
        "license_plate": license_plate,
        "tire_size": tire_size,
        "attachments": attachments or [],
        "status": IntakeStatus.PENDING.value,
        "created_at": now,
        # Review fields
        "review_notes": [],
        "reviewed_by": None,
        "reviewed_at": None,
        # Conversion tracking
        "converted_ticket_id": None,
        "converted_ticket_number": None,
        "converted_at": None,
        "converted_by": None
    }
    
    await db.intake_requests.insert_one(doc)
    return doc


async def get_intake_request(intake_id: str) -> Optional[dict]:
    """Get intake request by ID."""
    return await db.intake_requests.find_one({"id": intake_id}, {"_id": 0})


async def list_intake_requests(
    status: Optional[str] = None,
    source: Optional[str] = None,
    source_type: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
) -> Tuple[list, int]:
    """
    List intake requests with filters, search, and pagination.
    Returns (items, total_count).
    """
    query = {}
    
    # Status filter
    if status:
        query["status"] = status
    
    # Source filter
    if source:
        query["source"] = source
    
    # Source type filter
    if source_type:
        query["source_type"] = source_type
    
    # Date range filter
    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to
    
    # Global text search across multiple fields
    if search:
        search_regex = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [
            {"sender_name": search_regex},
            {"sender_contact": search_regex},
            {"license_plate": search_regex},
            {"tire_size": search_regex},
            {"raw_text": search_regex}
        ]
    
    # Get total count
    total = await db.intake_requests.count_documents(query)
    
    # Calculate skip
    skip = (page - 1) * page_size
    
    # Fetch items
    cursor = db.intake_requests.find(query, {"_id": 0})
    cursor = cursor.sort("created_at", -1).skip(skip).limit(page_size)
    items = await cursor.to_list(page_size)
    
    return items, total


async def update_intake_request(intake_id: str, updates: dict) -> Optional[dict]:
    """Update intake request."""
    result = await db.intake_requests.update_one(
        {"id": intake_id},
        {"$set": updates}
    )
    if result.modified_count > 0 or result.matched_count > 0:
        return await get_intake_request(intake_id)
    return None


async def delete_intake_request(intake_id: str) -> bool:
    """Delete intake request."""
    result = await db.intake_requests.delete_one({"id": intake_id})
    return result.deleted_count > 0


async def add_review_note(
    intake_id: str,
    note: str,
    author_id: str,
    author_name: str
) -> Optional[dict]:
    """Add a review note to an intake request."""
    now = datetime.now(timezone.utc).isoformat()
    
    review_note = {
        "note": note,
        "author_id": author_id,
        "author_name": author_name,
        "created_at": now
    }
    
    result = await db.intake_requests.update_one(
        {"id": intake_id},
        {
            "$push": {"review_notes": review_note},
            "$set": {
                "reviewed_by": author_id,
                "reviewed_at": now
            }
        }
    )
    
    if result.modified_count > 0:
        return await get_intake_request(intake_id)
    return None


async def mark_as_converted(
    intake_id: str,
    ticket_id: str,
    ticket_number: str,
    converted_by: str
) -> Optional[dict]:
    """Mark intake request as converted to ticket with full tracking."""
    now = datetime.now(timezone.utc).isoformat()
    return await update_intake_request(intake_id, {
        "status": IntakeStatus.CONVERTED.value,
        "converted_ticket_id": ticket_id,
        "converted_ticket_number": ticket_number,
        "converted_at": now,
        "converted_by": converted_by
    })


async def get_intake_stats() -> dict:
    """Get statistics for intake requests."""
    pipeline = [
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }
        }
    ]
    
    results = await db.intake_requests.aggregate(pipeline).to_list(10)
    
    stats = {
        "pending": 0,
        "processing": 0,
        "converted": 0,
        "rejected": 0,
        "total": 0
    }
    
    for r in results:
        status = r["_id"].lower() if r["_id"] else "pending"
        if status in stats:
            stats[status] = r["count"]
        stats["total"] += r["count"]
    
    return stats
