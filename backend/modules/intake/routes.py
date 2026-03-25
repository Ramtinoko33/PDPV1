"""
Intake Module - Routes
API endpoints for intake requests.
Only loaded if module is enabled in config/modules.json
"""
import uuid
from datetime import datetime, timezone, timedelta, date, time
from typing import Optional, List, Tuple
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query

from db import db
from core.security import get_current_user
from .models import (
    IntakeRequestCreate,
    IntakeRequestUpdate,
    IntakeRequestResponse,
    IntakeListResponse,
    ConvertToTicketRequest,
    ReviewNoteCreate,
    IntakeStatus,
    IntakeSourceType
)
from . import service

router = APIRouter(prefix="/intake", tags=["intake"])

# ============== SLA BUSINESS HOURS (duplicated from server.py for module isolation) ==============
BUSINESS_HOURS = {
    0: (time(8, 30), time(18, 30)),   # Monday
    1: (time(8, 30), time(18, 30)),   # Tuesday
    2: (time(8, 30), time(18, 30)),   # Wednesday
    3: (time(8, 30), time(18, 30)),   # Thursday
    4: (time(8, 30), time(18, 30)),   # Friday
    5: (time(8, 30), time(13, 0)),    # Saturday
    6: None,                           # Sunday (closed)
}

SLA_TARGETS_MINUTES = {
    "ORCAMENTO_PNEUS": 480,      # 8 hours
    "ORCAMENTO_MECANICA": 480,   # 8 hours
    "INFORMACAO": 120,           # 2 hours
    "RECLAMACAO": 120,           # 2 hours
    "MARCACAO": 180,             # 3 hours
    "INTERNO": 480,              # 8 hours
}

HOLIDAYS: list[date] = []

def get_business_hours_for_day(d: date) -> Tuple[time, time] | None:
    if d in HOLIDAYS:
        return None
    return BUSINESS_HOURS.get(d.weekday())

def add_business_minutes(start_dt: datetime, minutes_to_add: int) -> datetime:
    if minutes_to_add <= 0:
        return start_dt
    current_dt = start_dt
    remaining_minutes = minutes_to_add
    max_iterations = 365
    iterations = 0
    while remaining_minutes > 0 and iterations < max_iterations:
        iterations += 1
        current_date = current_dt.date()
        current_time = current_dt.time()
        hours = get_business_hours_for_day(current_date)
        if not hours:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        biz_start, biz_end = hours
        if current_time < biz_start:
            current_dt = datetime.combine(current_date, biz_start, tzinfo=current_dt.tzinfo)
            current_time = biz_start
        if current_time >= biz_end:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        current_minutes = current_time.hour * 60 + current_time.minute
        end_minutes = biz_end.hour * 60 + biz_end.minute
        available_minutes = end_minutes - current_minutes
        if remaining_minutes <= available_minutes:
            final_minutes = current_minutes + remaining_minutes
            final_hour = final_minutes // 60
            final_minute = final_minutes % 60
            return datetime.combine(current_date, time(final_hour, final_minute), tzinfo=current_dt.tzinfo)
        else:
            remaining_minutes -= available_minutes
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
    return current_dt

def compute_sla_due(ticket_type: str = "INFORMACAO", created_at: datetime = None) -> Tuple[datetime, int, str]:
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    target_minutes = SLA_TARGETS_MINUTES.get(ticket_type, 120)
    policy_key = f"SLA_{ticket_type}_{target_minutes}min"
    sla_due = add_business_minutes(created_at, target_minutes)
    return sla_due, target_minutes, policy_key
# ============== END SLA BUSINESS HOURS ==============


@router.get("/pending-count")
async def get_pending_count(current_user: dict = Depends(get_current_user)):
    """Get count of pending intake requests for sidebar badge."""
    count = await db.intake_requests.count_documents({"status": "PENDING"})
    return {"count": count}


@router.get("/stats")
async def get_intake_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get intake statistics."""
    return await service.get_intake_stats()


@router.get("", response_model=IntakeListResponse)
async def list_intake_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    search: Optional[str] = Query(None, description="Search in name, contact, plate, tire, message"),
    date_from: Optional[str] = Query(None, description="Filter from date (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter to date (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: dict = Depends(get_current_user)
):
    """List all intake requests with filters, search and pagination."""
    items, total = await service.list_intake_requests(
        status=status,
        source=source,
        source_type=source_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size
    )
    
    total_pages = ceil(total / page_size) if total > 0 else 1
    
    return IntakeListResponse(
        items=[IntakeRequestResponse(**r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{intake_id}", response_model=IntakeRequestResponse)
async def get_intake_request(
    intake_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific intake request."""
    request = await service.get_intake_request(intake_id)
    if not request:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return IntakeRequestResponse(**request)


@router.post("", response_model=IntakeRequestResponse)
async def create_intake_request(
    data: IntakeRequestCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new intake request manually."""
    request = await service.create_intake_request(
        source=data.source,
        source_type=data.source_type,
        sender_name=data.sender_name,
        sender_contact=data.sender_contact,
        sender_email=data.sender_email,
        telegram_username=data.telegram_username,
        raw_text=data.raw_text,
        license_plate=data.license_plate,
        tire_size=data.tire_size,
        attachments=data.attachments
    )
    return IntakeRequestResponse(**request)


@router.put("/{intake_id}", response_model=IntakeRequestResponse)
async def update_intake_request(
    intake_id: str,
    data: IntakeRequestUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an intake request."""
    existing = await service.get_intake_request(intake_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if existing["status"] == IntakeStatus.CONVERTED.value:
        raise HTTPException(status_code=400, detail="Pedido já convertido em ticket")
    
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    updated = await service.update_intake_request(intake_id, updates)
    return IntakeRequestResponse(**updated)


@router.delete("/{intake_id}")
async def delete_intake_request(
    intake_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete an intake request."""
    existing = await service.get_intake_request(intake_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if existing["status"] == IntakeStatus.CONVERTED.value:
        raise HTTPException(status_code=400, detail="Não é possível eliminar pedido já convertido")
    
    await service.delete_intake_request(intake_id)
    return {"message": "Pedido eliminado"}


@router.post("/{intake_id}/notes", response_model=IntakeRequestResponse)
async def add_review_note(
    intake_id: str,
    data: ReviewNoteCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add a review note to an intake request."""
    existing = await service.get_intake_request(intake_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if not data.note.strip():
        raise HTTPException(status_code=400, detail="Nota não pode estar vazia")
    
    updated = await service.add_review_note(
        intake_id=intake_id,
        note=data.note.strip(),
        author_id=current_user["id"],
        author_name=current_user.get("name", current_user.get("email", "Unknown"))
    )
    
    if not updated:
        raise HTTPException(status_code=500, detail="Erro ao adicionar nota")
    
    return IntakeRequestResponse(**updated)


@router.post("/{intake_id}/convert_to_ticket")
async def convert_to_ticket(
    intake_id: str,
    data: ConvertToTicketRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Convert intake request to a regular ticket.
    Creates ticket with full traceability back to intake.
    Auto-creates customer and vehicle if they don't exist.
    """
    from services.customer_service import find_or_create_customer_vehicle
    
    # Get intake request
    intake = await service.get_intake_request(intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if intake["status"] == IntakeStatus.CONVERTED.value:
        raise HTTPException(status_code=400, detail="Pedido já convertido em ticket")
    
    # Prepare ticket data using intake data or overrides
    customer_name = data.customer_name or intake["sender_name"]
    customer_phone = data.customer_phone or intake.get("sender_contact") or ""
    customer_email = data.customer_email or intake.get("sender_email")
    vehicle_plate = data.vehicle_plate or intake.get("license_plate")
    description = data.description or intake["raw_text"]
    
    # Append tire_size and vehicle_info to description if available
    extra_info = []
    if intake.get("tire_size"):
        extra_info.append(f"Medida: {intake['tire_size']}")
    if intake.get("vehicle_brand") or intake.get("vehicle_model"):
        vehicle_info = " ".join(filter(None, [intake.get("vehicle_brand"), intake.get("vehicle_model")]))
        if vehicle_info:
            extra_info.append(f"Veículo: {vehicle_info}")
    
    if extra_info and description:
        description = f"{description} | {' | '.join(extra_info)}"
    elif extra_info:
        description = " | ".join(extra_info)
    
    # Auto-create customer and vehicle if plate provided
    customer_id, vehicle_id, was_created = await find_or_create_customer_vehicle(
        license_plate=vehicle_plate,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        source="intake_conversion"
    )
    
    # Determine created_by_name - for Telegram, use the sender from intake
    if intake["source"] == "telegram":
        created_by_name = f"Telegram: {intake.get('sender_name', 'Desconhecido')}"
    else:
        created_by_name = current_user.get("name", current_user.get("email", "Sistema"))
    
    # Create ticket
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    ticket_number = f"TK{now.strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
    
    # Map source to channel
    source_to_channel = {
        "telegram": "TELEGRAM",
        "whatsapp": "WHATSAPP",
        "email": "EMAIL",
        "web_form": "FORMULARIO",
        "telefone": "TELEFONE",
        "manual": "FORMULARIO"
    }
    channel = source_to_channel.get(intake["source"], "FORMULARIO")
    
    # Get assigned user name if assigning
    assigned_to_name = None
    if data.assigned_to:
        assigned_user = await db.users.find_one({"id": data.assigned_to})
        if assigned_user:
            assigned_to_name = assigned_user.get("name")
    
    # Set status based on assignment
    initial_status = "EM_TRATAMENTO" if data.assigned_to else "ABERTO"
    
    # Calculate SLA based on ticket type and business hours
    sla_due, sla_target_minutes, sla_policy_key = compute_sla_due(
        ticket_type=data.ticket_type,
        created_at=now
    )
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": channel,
        "type": data.ticket_type,
        "status": initial_status,
        "priority": "NORMAL",
        "description": description,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "vehicle_plate": vehicle_plate,
        "assigned_to_user_id": data.assigned_to,
        "assigned_to_name": assigned_to_name,
        "created_by_user_id": current_user["id"],
        "created_by_name": created_by_name,  # NEW: Store creator name
        "customer_id": customer_id,          # Link to auto-created customer
        "vehicle_id": vehicle_id,            # Link to auto-created vehicle
        "first_response_done": False,
        "sla_due": sla_due.isoformat(),
        # New SLA fields
        "sla_started_at": now.isoformat(),
        "sla_paused_at": None,
        "sla_paused_minutes": 0,
        "sla_breached": False,
        "sla_breached_at": None,
        "sla_target_minutes": sla_target_minutes,
        "sla_policy_key": sla_policy_key,
        # End new SLA fields
        "quote_sent": False,
        "quote_value": None,
        # Traceability - link back to intake
        "intake_request_id": intake_id,
        "intake_source": intake["source"],
        "intake_source_type": intake.get("source_type", "manual"),
        "telegram_username": intake.get("telegram_username")
    }
    
    await db.tickets.insert_one(ticket_doc)
    
    # Mark intake as converted with full tracking
    await service.mark_as_converted(
        intake_id=intake_id,
        ticket_id=ticket_id,
        ticket_number=ticket_number,
        converted_by=current_user["id"]
    )
    
    # Return created ticket info
    return {
        "message": "Ticket criado com sucesso",
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "intake_id": intake_id,
        "customer_created": was_created
    }
