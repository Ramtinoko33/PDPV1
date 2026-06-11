"""
Ticket routes module.
Contains endpoints for ticket CRUD, archive, status history, messages, notes, alerts, reminders, attachments.
"""
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import ValidationError

from db import db
from schemas.user import UserRole
from schemas.ticket import (
    TicketCreate, TicketUpdate, TicketResponse, TicketStatusHistoryResponse,
    MessageCreate, MessageResponse, NoteCreate, NoteResponse, AlertResponse,
    ReminderCreate, ReminderResponse, AttachmentResponse,
    TicketStatus, TicketType, MessageDirection, MessageChannel, AlertType
)
from core.security import get_current_user
from services.ticket_service import generate_ticket_number, log_status_change, log_quote_change
from services.sla_service import (
    compute_sla_due, check_ticket_overdue, 
    calculate_sla_elapsed_minutes, add_business_minutes,
    calculate_business_minutes_between, SLA_PAUSE_ON_AGUARDA_CLIENTE
)
from services.storage_service import UPLOAD_DIR, APP_NAME, put_object, get_object

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


# Defaults applied when legacy/seeded tickets are missing required fields.
# This keeps list/detail endpoints resilient instead of returning 500 because
# of a single malformed doc. Real writes still go through TicketCreate.
_TICKET_RESPONSE_DEFAULTS = {
    "ticket_number": "—",
    "channel": "WEB",
    "type": "ORCAMENTO",
    "status": "ABERTO",
    "priority": "MEDIA",
    "description": "",
    "customer_name": "—",
    "customer_phone": "—",
}


def _safe_ticket_response(t: dict) -> Optional[TicketResponse]:
    """Build TicketResponse tolerating legacy docs with missing fields.

    Returns None when even after defaults the doc cannot be coerced (e.g. no id).
    Logs the malformed ticket id so it can be fixed in the DB.
    """
    if not t.get("id"):
        logger.warning("Skipping ticket without id during response build")
        return None
    patched = {**t}
    # updated_at falls back to created_at, then to now()
    if not patched.get("updated_at"):
        patched["updated_at"] = patched.get("created_at") or datetime.now(timezone.utc).isoformat()
    if not patched.get("created_at"):
        patched["created_at"] = datetime.now(timezone.utc).isoformat()
    for key, default in _TICKET_RESPONSE_DEFAULTS.items():
        if patched.get(key) in (None, ""):
            patched[key] = default
    try:
        return TicketResponse(**patched)
    except ValidationError as e:
        logger.warning(
            "Skipping malformed ticket id=%s: %s",
            patched.get("id"), e.errors(),
        )
        return None


# ============== TICKET CRUD ==============
@router.post("", response_model=TicketResponse)
async def create_ticket(ticket_data: TicketCreate, current_user: dict = Depends(get_current_user)):
    from services.customer_service import find_or_create_customer_vehicle
    from core.notifications import notify_supervisors, create_notification
    
    user = current_user
    
    # INTERNAL_CREATOR can only create INTERNO tickets
    if user["role"] == UserRole.INTERNAL_CREATOR.value and ticket_data.type != TicketType.INTERNO:
        raise HTTPException(status_code=403, detail="Apenas pode criar tickets internos")
    
    # AGENT without can_create_tickets cannot assign to other users
    if user["role"] == UserRole.AGENT.value and not user.get("can_create_tickets"):
        if ticket_data.assigned_to_user_id and ticket_data.assigned_to_user_id != user["id"]:
            raise HTTPException(status_code=403, detail="Sem permissão para atribuir tickets a outros utilizadores")
    
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    ticket_number = generate_ticket_number()
    
    # Calculate SLA based on ticket type and business hours
    sla_due, sla_target_minutes, sla_policy_key = compute_sla_due(
        ticket_type=ticket_data.type.value,
        created_at=now
    )
    
    # Set status to EM_TRATAMENTO if assigned to someone, otherwise ABERTO
    initial_status = TicketStatus.EM_TRATAMENTO.value if ticket_data.assigned_to_user_id else TicketStatus.ABERTO.value
    
    # Get assigned user name if assigning
    assigned_to_name = None
    if ticket_data.assigned_to_user_id:
        assigned_user = await db.users.find_one({"id": ticket_data.assigned_to_user_id})
        if assigned_user:
            assigned_to_name = assigned_user.get("name")
    
    # Auto-create customer and vehicle if plate provided
    customer_id, vehicle_id, was_created = await find_or_create_customer_vehicle(
        license_plate=ticket_data.vehicle_plate,
        customer_name=ticket_data.customer_name,
        customer_phone=ticket_data.customer_phone,
        customer_email=ticket_data.customer_email,
        source="ticket_manual"
    )
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": ticket_data.channel.value,
        "type": ticket_data.type.value,
        "status": initial_status,
        "priority": ticket_data.priority.value,
        "description": ticket_data.description,
        "customer_name": ticket_data.customer_name,
        "customer_phone": ticket_data.customer_phone,
        "customer_email": ticket_data.customer_email,
        "vehicle_plate": ticket_data.vehicle_plate,
        "assigned_to_user_id": ticket_data.assigned_to_user_id if ticket_data.assigned_to_user_id else None,
        "assigned_to_name": assigned_to_name,
        "last_public_message_at": None,
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
        "quote_locked_at": None,
        "quote_decided_at": None,
        "quote_decision": None,
        "created_by_user_id": user["id"],
        "created_by_name": user.get("name", user.get("email", "Sistema")),
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "archived_at": None,
        "archived_by": None
    }
    await db.tickets.insert_one(ticket_doc)
    
    # Log initial status in history
    await log_status_change(ticket_id, None, initial_status, user["id"])
    
    # Notify supervisors about new ticket
    asyncio.create_task(notify_supervisors(
        title="Novo Ticket",
        body=f"Ticket {ticket_number} criado - {ticket_data.customer_name}",
        notification_type="info",
        ticket_id=ticket_id,
        ticket_number=ticket_number
    ))
    
    # If assigned, notify the assigned user
    if ticket_data.assigned_to_user_id:
        asyncio.create_task(create_notification(
            user_id=ticket_data.assigned_to_user_id,
            title="Ticket Atribuído",
            body=f"O ticket {ticket_number} foi-lhe atribuído",
            notification_type="info",
            ticket_id=ticket_id,
            ticket_number=ticket_number
        ))
    
    ticket_doc["is_overdue"] = check_ticket_overdue(ticket_doc)
    return TicketResponse(**ticket_doc)


@router.get("", response_model=List[TicketResponse])
async def list_tickets(
    current_user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    channel: Optional[str] = None,
    overdue: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    user = current_user
    
    # Base query: exclude archived tickets
    query = {"archived_at": None}
    
    # Role-based filtering
    if user["role"] == UserRole.AGENT.value:
        query["$or"] = [
            {"assigned_to_user_id": user["id"]},
            {"assigned_to_user_id": None},
            {"assigned_to_user_id": {"$exists": False}}
        ]
    elif user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão para ver tickets")
    
    # Apply filters
    if status:
        query["status"] = status
    if type:
        query["type"] = type
    if assigned_to:
        query["assigned_to_user_id"] = assigned_to
    if channel:
        query["channel"] = channel
    if search:
        query["$or"] = [
            {"customer_phone": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"vehicle_plate": {"$regex": search, "$options": "i"}},
            {"ticket_number": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    
    tickets = await db.tickets.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Get assigned user names
    user_ids = list(set([t.get("assigned_to_user_id") for t in tickets if t.get("assigned_to_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    result = []
    for t in tickets:
        t["assigned_to_name"] = users_map.get(t.get("assigned_to_user_id"))
        t["is_overdue"] = check_ticket_overdue(t)
        
        # Filter by overdue if requested
        if overdue is not None:
            if overdue and not t["is_overdue"]:
                continue
            elif not overdue and t["is_overdue"]:
                continue
        
        resp = _safe_ticket_response(t)
        if resp is not None:
            result.append(resp)
    
    return result


@router.get("/archived", response_model=List[TicketResponse])
async def list_archived_tickets(
    current_user: dict = Depends(get_current_user),
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """List archived tickets - only ADMIN and SUPERVISOR can view"""
    user = current_user
    
    if user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver tickets arquivados")
    
    query = {"archived_at": {"$ne": None}}
    
    if search:
        query["$or"] = [
            {"customer_phone": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"vehicle_plate": {"$regex": search, "$options": "i"}},
            {"ticket_number": {"$regex": search, "$options": "i"}}
        ]
    
    tickets = await db.tickets.find(query, {"_id": 0}).sort("archived_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Get assigned user names
    user_ids = list(set([t.get("assigned_to_user_id") for t in tickets if t.get("assigned_to_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    result = []
    for t in tickets:
        t["assigned_to_name"] = users_map.get(t.get("assigned_to_user_id"))
        t["is_overdue"] = check_ticket_overdue(t)
        resp = _safe_ticket_response(t)
        if resp is not None:
            result.append(resp)
    
    return result


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check if user is the creator (within 5 min window)
    is_creator = ticket.get("created_by_user_id") == user["id"]
    creator_can_view = False
    if is_creator:
        try:
            created_at = datetime.fromisoformat(ticket["created_at"].replace("Z", "+00:00"))
            time_since_creation = datetime.now(timezone.utc) - created_at
            creator_can_view = time_since_creation.total_seconds() <= 300
        except:
            creator_can_view = False
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value:
        is_assigned_to_agent = ticket.get("assigned_to_user_id") == user["id"]
        is_unassigned = ticket.get("assigned_to_user_id") is None
        if not is_assigned_to_agent and not is_unassigned and not creator_can_view:
            raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        if not creator_can_view:
            raise HTTPException(status_code=403, detail="Só pode ver tickets que criou nos primeiros 5 minutos")
    
    # Get assigned user name
    if ticket.get("assigned_to_user_id"):
        assigned_user = await db.users.find_one({"id": ticket["assigned_to_user_id"]}, {"_id": 0, "name": 1})
        ticket["assigned_to_name"] = assigned_user["name"] if assigned_user else None
    
    ticket["creator_can_edit"] = creator_can_view and is_creator
    ticket["is_overdue"] = check_ticket_overdue(ticket)
    resp = _safe_ticket_response(ticket)
    if resp is None:
        raise HTTPException(
            status_code=422,
            detail="Ticket com dados em falta — contacte o administrador",
        )
    return resp


@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: str, ticket_data: TicketUpdate, current_user: dict = Depends(get_current_user)):
    from core.notifications import create_notification
    
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if ticket.get("archived_at"):
        raise HTTPException(status_code=400, detail="Não é possível editar um ticket arquivado")
    
    # Check if creator can edit (within 5 minutes of creation)
    is_creator = ticket.get("created_by_user_id") == user["id"]
    creator_can_edit = False
    if is_creator:
        try:
            created_at = datetime.fromisoformat(ticket["created_at"].replace("Z", "+00:00"))
            time_since_creation = datetime.now(timezone.utc) - created_at
            creator_can_edit = time_since_creation.total_seconds() <= 300
        except:
            creator_can_edit = False
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value:
        if ticket.get("assigned_to_user_id") != user["id"]:
            if ticket.get("assigned_to_user_id") is None and ticket_data.assigned_to_user_id == user["id"]:
                pass  # Allow self-assignment
            elif creator_can_edit:
                pass
            else:
                raise HTTPException(status_code=403, detail="Sem permissão para editar este ticket")
        if ticket_data.assigned_to_user_id is not None and ticket_data.assigned_to_user_id != user["id"] and ticket_data.assigned_to_user_id != "":
            raise HTTPException(status_code=403, detail="Agentes só podem atribuir tickets a si próprios")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        if not creator_can_edit:
            raise HTTPException(status_code=403, detail="Só pode editar tickets que criou nos primeiros 5 minutos")
    
    update_doc = {"updated_at": datetime.now(timezone.utc).isoformat()}
    old_status = ticket.get("status")
    old_assigned = ticket.get("assigned_to_user_id")
    
    if ticket_data.status is not None:
        valid_status = await db.ticket_statuses.find_one({"code": ticket_data.status})
        if not valid_status:
            raise HTTPException(status_code=400, detail=f"Estado '{ticket_data.status}' não existe")
        update_doc["status"] = ticket_data.status
    if ticket_data.assigned_to_user_id is not None:
        update_doc["assigned_to_user_id"] = ticket_data.assigned_to_user_id if ticket_data.assigned_to_user_id != "" else None
    if ticket_data.priority is not None:
        update_doc["priority"] = ticket_data.priority.value
    if ticket_data.quote_sent is not None:
        update_doc["quote_sent"] = ticket_data.quote_sent
    if ticket_data.quote_value is not None:
        update_doc["quote_value"] = ticket_data.quote_value
    if ticket_data.description is not None:
        update_doc["description"] = ticket_data.description
    if ticket_data.customer_name is not None:
        update_doc["customer_name"] = ticket_data.customer_name
    if ticket_data.customer_phone is not None:
        update_doc["customer_phone"] = ticket_data.customer_phone
    if ticket_data.customer_email is not None:
        update_doc["customer_email"] = ticket_data.customer_email if ticket_data.customer_email != "" else None
    if ticket_data.vehicle_plate is not None:
        update_doc["vehicle_plate"] = ticket_data.vehicle_plate if ticket_data.vehicle_plate != "" else None
    if ticket_data.type is not None:
        update_doc["type"] = ticket_data.type.value
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": update_doc})
    
    # Log quote value change to history
    old_quote_value = ticket.get("quote_value")
    if ticket_data.quote_value is not None and ticket_data.quote_value != old_quote_value:
        await log_quote_change(ticket_id, old_quote_value, ticket_data.quote_value, user["id"])
        note_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by_user_id": user["id"],
            "body": f"Valor do orçamento alterado de {old_quote_value or 0:.2f}€ para {ticket_data.quote_value:.2f}€",
            "is_system": True
        }
        await db.notes.insert_one(note_doc)
    
    # Log status change to history
    if ticket_data.status and ticket_data.status != old_status:
        await log_status_change(ticket_id, old_status, ticket_data.status, user["id"])
        note_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by_user_id": user["id"],
            "body": f"Estado alterado de {old_status} para {ticket_data.status}",
            "is_system": True
        }
        await db.notes.insert_one(note_doc)
        
        # SLA PAUSE/RESUME LOGIC
        now = datetime.now(timezone.utc)
        new_status = ticket_data.status
        
        if SLA_PAUSE_ON_AGUARDA_CLIENTE:
            sla_pause_statuses = [TicketStatus.AGUARDA_CLIENTE.value, TicketStatus.AGENDADO.value]
            sla_resume_statuses = [
                TicketStatus.EM_TRATAMENTO.value,
                TicketStatus.ACEITE_LINK.value,
                TicketStatus.ABERTO.value,
            ]
            sla_final_statuses = [
                TicketStatus.FECHADO.value,
                TicketStatus.REJEITADO_LINK.value,
            ]
            
            # Check if we need to PAUSE SLA
            if new_status in sla_pause_statuses and old_status not in sla_pause_statuses:
                if not ticket.get("sla_paused_at") and not ticket.get("first_response_done"):
                    sla_pause_update = {"sla_paused_at": now.isoformat()}
                    await db.tickets.update_one({"id": ticket_id}, {"$set": sla_pause_update})
                    
                    pause_reason = "aguarda resposta do cliente" if new_status == TicketStatus.AGUARDA_CLIENTE.value else "ticket agendado"
                    pause_note = {
                        "id": str(uuid.uuid4()),
                        "ticket_id": ticket_id,
                        "created_at": now.isoformat(),
                        "created_by_user_id": user["id"],
                        "body": f"⏸️ SLA pausado - {pause_reason}",
                        "is_system": True
                    }
                    await db.notes.insert_one(pause_note)
            
            # Check if we need to RESUME SLA
            elif new_status in sla_resume_statuses and old_status in sla_pause_statuses:
                if ticket.get("sla_paused_at") and not ticket.get("first_response_done"):
                    try:
                        pause_start = datetime.fromisoformat(ticket["sla_paused_at"].replace("Z", "+00:00"))
                        paused_business_minutes = calculate_business_minutes_between(pause_start, now)
                        
                        current_paused_minutes = ticket.get("sla_paused_minutes", 0)
                        new_paused_total = current_paused_minutes + paused_business_minutes
                        
                        old_sla_due_str = ticket.get("sla_due")
                        if old_sla_due_str:
                            old_sla_due = datetime.fromisoformat(old_sla_due_str.replace("Z", "+00:00"))
                            new_sla_due = add_business_minutes(old_sla_due, paused_business_minutes)
                        else:
                            target_minutes = ticket.get("sla_target_minutes", 120)
                            elapsed = calculate_sla_elapsed_minutes(ticket)
                            remaining = max(0, target_minutes - elapsed)
                            new_sla_due = add_business_minutes(now, remaining)
                        
                        sla_resume_update = {
                            "sla_paused_at": None,
                            "sla_paused_minutes": new_paused_total,
                            "sla_due": new_sla_due.isoformat()
                        }
                        await db.tickets.update_one({"id": ticket_id}, {"$set": sla_resume_update})
                        
                        resume_note = {
                            "id": str(uuid.uuid4()),
                            "ticket_id": ticket_id,
                            "created_at": now.isoformat(),
                            "created_by_user_id": user["id"],
                            "body": f"▶️ SLA retomado - pausa de {paused_business_minutes} minutos úteis",
                            "is_system": True
                        }
                        await db.notes.insert_one(resume_note)
                    except (ValueError, TypeError):
                        pass
            
            # Check if SLA tracking should stop (final status)
            if new_status in sla_final_statuses:
                if ticket.get("sla_paused_at"):
                    await db.tickets.update_one({"id": ticket_id}, {"$set": {"sla_paused_at": None}})
    
    if ticket_data.assigned_to_user_id is not None and ticket_data.assigned_to_user_id != old_assigned:
        assigned_name = "Ninguém"
        if ticket_data.assigned_to_user_id:
            assigned_user = await db.users.find_one({"id": ticket_data.assigned_to_user_id}, {"_id": 0, "name": 1})
            assigned_name = assigned_user["name"] if assigned_user else ticket_data.assigned_to_user_id
            
            # Auto-change status from ABERTO to EM_TRATAMENTO when assigning
            current_ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0, "status": 1})
            if current_ticket and current_ticket.get("status") == "ABERTO" and not ticket_data.status:
                await db.tickets.update_one({"id": ticket_id}, {"$set": {"status": "EM_TRATAMENTO"}})
                await log_status_change(ticket_id, "ABERTO", "EM_TRATAMENTO", user["id"])
                auto_status_note = {
                    "id": str(uuid.uuid4()),
                    "ticket_id": ticket_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by_user_id": user["id"],
                    "body": "Estado alterado automaticamente para Em Tratamento (ticket atribuído)",
                    "is_system": True
                }
                await db.notes.insert_one(auto_status_note)
            
            # Notify assigned user
            asyncio.create_task(create_notification(
                user_id=ticket_data.assigned_to_user_id,
                title="Ticket Atribuído",
                body=f"O ticket {ticket['ticket_number']} foi-lhe atribuído",
                notification_type="info",
                ticket_id=ticket_id,
                ticket_number=ticket["ticket_number"]
            ))
        note_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by_user_id": user["id"],
            "body": f"Ticket atribuído a {assigned_name}",
            "is_system": True
        }
        await db.notes.insert_one(note_doc)
    
    updated_ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if updated_ticket.get("assigned_to_user_id"):
        assigned_user = await db.users.find_one({"id": updated_ticket["assigned_to_user_id"]}, {"_id": 0, "name": 1})
        updated_ticket["assigned_to_name"] = assigned_user["name"] if assigned_user else None
    updated_ticket["is_overdue"] = check_ticket_overdue(updated_ticket)
    
    return TicketResponse(**updated_ticket)


# ============== ARCHIVE SYSTEM ==============
@router.post("/{ticket_id}/archive")
async def archive_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Archive a ticket - only ADMIN and SUPERVISOR can archive"""
    user = current_user
    
    if user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para arquivar tickets")
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if ticket.get("archived_at"):
        raise HTTPException(status_code=400, detail="Ticket já está arquivado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "archived_at": now,
            "archived_by": user["id"],
            "updated_at": now
        }}
    )
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now,
        "created_by_user_id": user["id"],
        "body": "Ticket arquivado",
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    return {"message": "Ticket arquivado com sucesso", "archived_at": now}


@router.post("/{ticket_id}/restore")
async def restore_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Restore an archived ticket - only ADMIN and SUPERVISOR can restore"""
    user = current_user
    
    if user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para restaurar tickets")
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if not ticket.get("archived_at"):
        raise HTTPException(status_code=400, detail="Ticket não está arquivado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "archived_at": None,
            "archived_by": None,
            "updated_at": now
        }}
    )
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now,
        "created_by_user_id": user["id"],
        "body": "Ticket restaurado do arquivo",
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    return {"message": "Ticket restaurado com sucesso"}


@router.get("/{ticket_id}/status-history", response_model=List[TicketStatusHistoryResponse])
async def get_ticket_status_history(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Get status change history for a ticket"""
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão para ver tickets")
    
    history = await db.ticket_status_history.find(
        {"ticket_id": ticket_id}, 
        {"_id": 0}
    ).sort("changed_at", -1).to_list(1000)
    
    user_ids = list(set([h.get("changed_by_user_id") for h in history if h.get("changed_by_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    for h in history:
        h["changed_by_name"] = users_map.get(h.get("changed_by_user_id"))
    
    return [TicketStatusHistoryResponse(**h) for h in history]
