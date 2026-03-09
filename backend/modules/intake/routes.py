"""
Intake Module - Routes
API endpoints for intake requests.
Only loaded if module is enabled in config/modules.json
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query

from db import db
from core.security import get_current_user
from .models import (
    IntakeRequestCreate,
    IntakeRequestUpdate,
    IntakeRequestResponse,
    ConvertToTicketRequest,
    IntakeStatus
)
from . import service

router = APIRouter(prefix="/intake", tags=["intake"])


@router.get("", response_model=List[IntakeRequestResponse])
async def list_intake_requests(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    skip: int = Query(0),
    current_user: dict = Depends(get_current_user)
):
    """List all intake requests."""
    requests = await service.list_intake_requests(
        status=status,
        source=source,
        limit=limit,
        skip=skip
    )
    return [IntakeRequestResponse(**r) for r in requests]


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
        sender_name=data.sender_name,
        sender_contact=data.sender_contact,
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


@router.post("/{intake_id}/convert_to_ticket")
async def convert_to_ticket(
    intake_id: str,
    data: ConvertToTicketRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Convert intake request to a regular ticket.
    Uses existing ticket creation logic.
    """
    # Get intake request
    intake = await service.get_intake_request(intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if intake["status"] == IntakeStatus.CONVERTED.value:
        raise HTTPException(status_code=400, detail="Pedido já convertido em ticket")
    
    # Prepare ticket data using intake data or overrides
    customer_name = data.customer_name or intake["sender_name"]
    customer_phone = data.customer_phone or intake["sender_contact"]
    vehicle_plate = data.vehicle_plate or intake.get("license_plate")
    description = data.description or intake["raw_text"]
    
    # Create ticket using existing logic (import from db, create directly)
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    ticket_number = f"TK{now.strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
    
    # Map source to channel
    source_to_channel = {
        "telegram": "TELEGRAM",
        "whatsapp": "WHATSAPP",
        "email": "EMAIL",
        "web_form": "FORMULARIO"
    }
    channel = source_to_channel.get(intake["source"], "FORMULARIO")
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": channel,
        "type": data.ticket_type,
        "status": "ABERTO",
        "priority": "NORMAL",
        "description": description,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": data.customer_email,
        "vehicle_plate": vehicle_plate,
        "assigned_to_user_id": None,
        "created_by_user_id": current_user["id"],
        "first_response_done": False,
        "sla_due": (now + __import__('datetime').timedelta(hours=2)).isoformat(),
        "quote_sent": False,
        "quote_value": None,
        "intake_request_id": intake_id  # Link back to intake
    }
    
    await db.tickets.insert_one(ticket_doc)
    
    # Mark intake as converted
    await service.mark_as_converted(intake_id, ticket_id)
    
    # Return created ticket info
    return {
        "message": "Ticket criado com sucesso",
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "intake_id": intake_id
    }
