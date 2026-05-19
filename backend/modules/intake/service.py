"""
Intake Module - Service
Business logic for intake requests.
"""
import uuid
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any

from db import db
from .models import IntakeStatus, IntakeSourceType


def _split_make_model(make_model: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort split "Opel Astra" → ("Opel", "Astra")."""
    if not make_model or not isinstance(make_model, str):
        return None, None
    parts = make_model.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


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
    attachments: list = None,
    # Legacy single-image vision analysis fields
    analysis_status: str = "pending",
    analysis_error: Optional[str] = None,
    raw_vision_output: Optional[str] = None,
    # Extra extracted data
    customer_phone: Optional[str] = None,
    vehicle_brand: Optional[str] = None,
    vehicle_model: Optional[str] = None,
    # ============== Open-flow AI fields (new internal bot) ==============
    source_bot: Optional[str] = None,
    origin_channel: Optional[str] = None,
    reference: Optional[str] = None,
    created_by_name: Optional[str] = None,
    telegram_user_id: Optional[int] = None,
    telegram_chat_id: Optional[int] = None,
    texts: Optional[List[str]] = None,
    audio_transcripts: Optional[List[str]] = None,
    image_hints: Optional[List[str]] = None,
    ai_extracted: Optional[Dict[str, Any]] = None,
) -> dict:
    """Create a new intake request.

    Supports legacy single-message flow (existing bot/website) and the
    new open-flow pre-ticket flow coming from the PDPV internal bot.
    """
    now = datetime.now(timezone.utc).isoformat()
    intake_id = str(uuid.uuid4())

    # Use customer_phone if provided and sender_contact is empty
    final_contact = sender_contact or customer_phone or ""

    # Apply AI fallbacks for top-level fields, but ONLY when the original
    # caller did not supply them (so the manual flow stays untouched).
    if ai_extracted and isinstance(ai_extracted, dict):
        if not sender_name:
            ai_name = ai_extracted.get("customer_name")
            if isinstance(ai_name, str) and ai_name.strip():
                sender_name = ai_name.strip()
        if not final_contact:
            ai_phone = ai_extracted.get("customer_phone")
            if isinstance(ai_phone, str) and ai_phone.strip():
                final_contact = ai_phone.strip()
        if not license_plate:
            ai_plate = ai_extracted.get("vehicle_plate")
            if isinstance(ai_plate, str) and ai_plate.strip():
                license_plate = ai_plate.strip().upper()
        if not (vehicle_brand or vehicle_model):
            mk, md = _split_make_model(ai_extracted.get("vehicle_make_model"))
            vehicle_brand = vehicle_brand or mk
            vehicle_model = vehicle_model or md

    doc = {
        "id": intake_id,
        "source": source,
        "source_type": source_type.value if isinstance(source_type, IntakeSourceType) else source_type,
        "source_bot": source_bot,
        "origin_channel": origin_channel,
        "reference": reference,
        "sender_name": sender_name or "",
        "sender_contact": final_contact,
        "sender_email": sender_email,
        "telegram_username": telegram_username,
        "raw_text": raw_text or "",
        "license_plate": license_plate,
        "tire_size": tire_size,
        "attachments": attachments or [],
        "status": IntakeStatus.PENDING.value,
        "created_at": now,
        "updated_at": now,
        # Review fields
        "review_notes": [],
        "reviewed_by": None,
        "reviewed_at": None,
        # Conversion tracking
        "converted_ticket_id": None,
        "converted_ticket_number": None,
        "converted_at": None,
        "converted_by": None,
        # Legacy analysis tracking
        "analysis_status": analysis_status,
        "analysis_error": analysis_error,
        "raw_vision_output": raw_vision_output,
        # Extra vehicle data
        "vehicle_brand": vehicle_brand,
        "vehicle_model": vehicle_model,
        # Open-flow AI fields
        "created_by_name": created_by_name,
        "telegram_user_id": telegram_user_id,
        "telegram_chat_id": telegram_chat_id,
        "texts": texts or [],
        "audio_transcripts": audio_transcripts or [],
        "image_hints": image_hints or [],
        "ai_extracted": ai_extracted,
        "validated_by": None,
    }

    await db.intake_requests.insert_one(doc)
    # Strip Mongo _id added by insert before returning
    doc.pop("_id", None)
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
            {"raw_text": search_regex},
            {"reference": search_regex},
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
    updates = dict(updates)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
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
                "reviewed_at": now,
                "updated_at": now,
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
