"""
Quotes Router Module.
Contains all quote-related endpoints: quote options CRUD, link generation,
public quote viewing/responding, PDF generation, and public branding.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import uuid
import os
import asyncio
import io
import logging
from datetime import datetime, timezone, timedelta

from db import db
from core.security import get_current_user
from schemas.user import UserRole
from schemas.ticket import TicketStatus
from services.quote_normalizer import normalize_description
from services.ticket_service import REJECTION_REASON_CODES
from services.storage_service import UPLOAD_DIR, get_object
from services.notification_service import create_notification, notify_supervisors

logger = logging.getLogger(__name__)

FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://tickets.pneusdpedrov.com')

router = APIRouter()


# ============== SCHEMAS ==============
class AttachmentPublicInfo(BaseModel):
    id: str
    original_filename: str

class QuoteOptionCreate(BaseModel):
    description: str
    amount: float
    attachment_ids: List[str] = []

class QuoteOptionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    description: str
    amount: float
    is_accepted: bool = False
    accepted_at: Optional[str] = None
    attachment_ids: List[str] = []

class QuoteOptionPublicResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    description: str
    amount: float
    is_accepted: bool = False
    accepted_at: Optional[str] = None
    attachments: List[AttachmentPublicInfo] = []
    display_title: Optional[str] = None
    display_type: Optional[str] = None
    display_includes: List[str] = []
    display_priority: Optional[str] = None

class QuoteOptionsUpdate(BaseModel):
    options: List[QuoteOptionCreate]

class QuoteResponseRequest(BaseModel):
    status: str  # ACCEPTED or REJECTED
    comments: Optional[str] = None
    accepted_option_ids: List[str] = []
    rejection_reason_code: Optional[str] = None
    rejection_reason_label: Optional[str] = None
    rejection_reason_note: Optional[str] = None
    # Acceptance intent fields
    acceptance_intent: Optional[str] = None  # "agendar", "avancar", "contactar"
    preferred_date: Optional[str] = None
    preferred_period: Optional[str] = None  # "manha", "tarde"

ACCEPTANCE_INTENT_CODES = {
    "agendar": "Quero agendar para uma data específica",
    "avancar": "Podem avançar com o serviço",
    "contactar": "Tenho dúvidas / Quero ser contactado",
}

class QuoteResponseData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ticket_number: str
    customer_name: str
    vehicle_plate: Optional[str] = None
    quote_value: float
    description: Optional[str] = None
    quote_sent_at: str
    response_status: Optional[str] = None
    response_at: Optional[str] = None
    quote_options: List[QuoteOptionPublicResponse] = []
    accepted_total: Optional[float] = None
    accepted_count: Optional[int] = None
    quote_valid_until: Optional[str] = None
    quote_decided_at: Optional[str] = None
    quote_decision: Optional[str] = None
    ticket_attachments: List[AttachmentPublicInfo] = []


# ============== QUOTE OPTIONS ENDPOINTS ==============
@router.get("/tickets/{ticket_id}/quote-options", response_model=List[QuoteOptionResponse])
async def get_quote_options(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Get all quote options for a ticket"""
    options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
    return options


@router.post("/tickets/{ticket_id}/quote-options", response_model=List[QuoteOptionResponse])
async def save_quote_options(ticket_id: str, data: QuoteOptionsUpdate, current_user: dict = Depends(get_current_user)):
    """Save/update quote options for a ticket (replaces all existing options)"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    if ticket.get("quote_locked_at"):
        raise HTTPException(status_code=409, detail="Orçamento bloqueado - já foi enviado ao cliente. Use 'Criar nova versão' para alterações.")
    
    await db.quote_options.delete_many({"ticket_id": ticket_id})
    
    new_options = []
    total_amount = 0
    for opt in data.options:
        option_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "description": opt.description,
            "amount": opt.amount,
            "is_accepted": False,
            "accepted_at": None,
            "attachment_ids": opt.attachment_ids
        }
        new_options.append(option_doc)
        total_amount += opt.amount
    
    if new_options:
        await db.quote_options.insert_many(new_options)
    
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "quote_value": total_amount,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_user_id": current_user["id"],
        "body": f"Orçamento atualizado: {len(new_options)} opções, total {total_amount:.2f}€",
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    return new_options


# ============== QUOTE LINK GENERATION ==============
@router.post("/tickets/{ticket_id}/generate-quote-link")
async def generate_quote_link(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Generate a unique link for client to respond to a quote"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    quote_options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
    if not quote_options and not ticket.get("quote_value"):
        raise HTTPException(status_code=400, detail="O ticket não tem opções de orçamento definidas")
    
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    quote_link_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "created_by_user_id": current_user["id"],
        "response_status": None,
        "response_at": None,
        "response_comments": None
    }
    await db.quote_links.insert_one(quote_link_doc)
    
    valid_until = datetime.now(timezone.utc) + timedelta(days=15)
    now = datetime.now(timezone.utc)
    update_fields = {
        "quote_sent": True,
        "quote_link_token": token,
        "quote_valid_until": valid_until.isoformat(),
        "updated_at": now.isoformat()
    }
    if not ticket.get("quote_locked_at"):
        update_fields["quote_locked_at"] = now.isoformat()
    
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": update_fields}
    )
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_user_id": current_user["id"],
        "body": f"Link de orçamento gerado (válido até {expires_at.strftime('%d/%m/%Y')})",
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    frontend_url = email_settings.get("frontend_url", FRONTEND_URL) if email_settings else FRONTEND_URL
    
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "link": f"/quote/{token}",
        "full_link": f"{frontend_url}/quote/{token}",
        "email_sent": False
    }


# ============== QUOTE NEW VERSION ==============
@router.post("/tickets/{ticket_id}/quote-new-version")
async def create_new_quote_version(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Create a new version of the quote - unlocks for editing and generates new link"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    if not ticket.get("quote_locked_at"):
        raise HTTPException(status_code=400, detail="Orçamento não está bloqueado")
    
    now = datetime.now(timezone.utc)
    
    previous_decision = ticket.get("quote_decision")
    previous_total = ticket.get("accepted_total")
    
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "quote_locked_at": None,
            "quote_decided_at": None,
            "quote_decision": None,
            "quote_response_status": None,
            "quote_response_at": None,
            "accepted_total": None,
            "accepted_count": None,
            "quote_link_token": None,
            "quote_valid_until": None,
            "updated_at": now.isoformat()
        }}
    )
    
    await db.quote_options.update_many(
        {"ticket_id": ticket_id},
        {"$set": {"is_accepted": False, "accepted_at": None}}
    )
    
    note_body = "Nova versão do orçamento criada - desbloqueado para edição"
    if previous_decision:
        note_body += f"\n(Decisão anterior: {previous_decision}"
        if previous_total:
            note_body += f", Total: {previous_total:.2f}€"
        note_body += ")"
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "created_by_user_id": current_user["id"],
        "body": note_body,
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    return {"status": "success", "message": "Orçamento desbloqueado para edição"}


# ============== PUBLIC QUOTE ENDPOINTS ==============
@router.get("/public/quote/{token}", response_model=QuoteResponseData)
async def get_public_quote(token: str):
    """Get quote details by public token - NO AUTH REQUIRED"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Link expirado")
    
    ticket = await db.tickets.find_one({"id": quote_link["ticket_id"]}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    quote_options = await db.quote_options.find({"ticket_id": quote_link["ticket_id"]}, {"_id": 0}).to_list(100)
    
    ticket_attachments_raw = await db.attachments.find(
        {"ticket_id": quote_link["ticket_id"], "source": {"$ne": "telegram_alert"}},
        {"_id": 0, "id": 1, "original_filename": 1}
    ).to_list(100)
    attachment_map = {a["id"]: a["original_filename"] for a in ticket_attachments_raw}
    
    accepted_options = [o for o in quote_options if o.get("is_accepted")]
    accepted_total = sum(o["amount"] for o in accepted_options) if accepted_options else None
    accepted_count = len(accepted_options) if accepted_options else None
    
    enriched_options = []
    for opt in quote_options:
        opt_attachments = [
            AttachmentPublicInfo(id=att_id, original_filename=attachment_map[att_id])
            for att_id in opt.get("attachment_ids", [])
            if att_id in attachment_map
        ]
        display = normalize_description(opt["description"])
        enriched_options.append(QuoteOptionPublicResponse(
            id=opt["id"],
            ticket_id=opt["ticket_id"],
            description=opt["description"],
            amount=opt["amount"],
            is_accepted=opt.get("is_accepted", False),
            accepted_at=opt.get("accepted_at"),
            attachments=opt_attachments,
            display_title=display["title"],
            display_type=display["type"],
            display_includes=display.get("includes", []),
            display_priority=display.get("priority", "normal"),
        ))
    
    return QuoteResponseData(
        ticket_number=ticket["ticket_number"],
        customer_name=ticket["customer_name"],
        vehicle_plate=ticket.get("vehicle_plate"),
        quote_value=ticket.get("quote_value", 0),
        description=ticket.get("description"),
        quote_sent_at=quote_link["created_at"],
        response_status=quote_link.get("response_status"),
        response_at=quote_link.get("response_at"),
        quote_options=enriched_options,
        accepted_total=accepted_total,
        accepted_count=accepted_count,
        quote_valid_until=ticket.get("quote_valid_until"),
        quote_decided_at=ticket.get("quote_decided_at"),
        quote_decision=ticket.get("quote_decision"),
        ticket_attachments=[AttachmentPublicInfo(id=a["id"], original_filename=a["original_filename"]) for a in ticket_attachments_raw]
    )


@router.post("/public/quote/{token}/respond")
async def respond_to_quote(token: str, response_data: QuoteResponseRequest):
    """Client responds to a quote - NO AUTH REQUIRED - ONE TIME ONLY"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Link expirado")
    
    if quote_link.get("response_status"):
        raise HTTPException(status_code=409, detail="Já respondeu a este orçamento")
    
    ticket_id = quote_link["ticket_id"]
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if ticket.get("quote_decided_at"):
        raise HTTPException(status_code=409, detail="Este orçamento já foi decidido anteriormente")
    
    if response_data.status not in ["ACCEPTED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Estado inválido")
    
    if response_data.status == "REJECTED":
        if response_data.rejection_reason_code:
            if response_data.rejection_reason_code not in REJECTION_REASON_CODES:
                raise HTTPException(status_code=400, detail="Código de motivo de rejeição inválido")
            if response_data.rejection_reason_code == "outro" and not response_data.rejection_reason_note:
                raise HTTPException(status_code=400, detail="Para 'Outro' motivo, a observação é obrigatória")
    
    if ticket.get("quote_valid_until"):
        valid_until_dt = datetime.fromisoformat(ticket["quote_valid_until"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > valid_until_dt:
            raise HTTPException(status_code=400, detail="Orçamento expirado. Contacte a oficina.")
    
    now = datetime.now(timezone.utc)
    
    quote_options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
    
    accepted_total = 0
    accepted_count = 0
    accepted_descriptions = []
    
    if response_data.status == "ACCEPTED" and quote_options:
        for opt in quote_options:
            if opt["id"] in response_data.accepted_option_ids:
                await db.quote_options.update_one(
                    {"id": opt["id"]},
                    {"$set": {"is_accepted": True, "accepted_at": now.isoformat()}}
                )
                accepted_total += opt["amount"]
                accepted_count += 1
                accepted_descriptions.append(f"{opt['description']} ({opt['amount']:.2f}€)")
        
        if accepted_count == 0 and not response_data.accepted_option_ids:
            for opt in quote_options:
                await db.quote_options.update_one(
                    {"id": opt["id"]},
                    {"$set": {"is_accepted": True, "accepted_at": now.isoformat()}}
                )
                accepted_total += opt["amount"]
                accepted_count += 1
                accepted_descriptions.append(f"{opt['description']} ({opt['amount']:.2f}€)")
    
    await db.quote_links.update_one(
        {"token": token},
        {"$set": {
            "response_status": response_data.status,
            "response_at": now.isoformat(),
            "response_comments": response_data.comments,
            "accepted_option_ids": response_data.accepted_option_ids
        }}
    )
    
    ticket_update = {
        "updated_at": now.isoformat(),
        "quote_response_status": response_data.status,
        "quote_response_at": now.isoformat(),
        "quote_decided_at": now.isoformat(),
        "quote_decision": response_data.status
    }
    
    if response_data.status == "ACCEPTED":
        ticket_update["status"] = TicketStatus.ACEITE_LINK.value
        if accepted_total > 0:
            ticket_update["accepted_total"] = accepted_total
            ticket_update["accepted_count"] = accepted_count
        # Save acceptance intent
        if response_data.acceptance_intent:
            ticket_update["acceptance_intent"] = response_data.acceptance_intent
            ticket_update["acceptance_intent_label"] = ACCEPTANCE_INTENT_CODES.get(
                response_data.acceptance_intent, response_data.acceptance_intent
            )
        if response_data.preferred_date:
            ticket_update["preferred_date"] = response_data.preferred_date
        if response_data.preferred_period:
            ticket_update["preferred_period"] = response_data.preferred_period
    else:
        ticket_update["status"] = TicketStatus.REJEITADO_LINK.value
        ticket_update["rejected_at"] = now.isoformat()
        ticket_update["rejected_via"] = "link"
        if response_data.rejection_reason_code:
            ticket_update["rejection_reason_code"] = response_data.rejection_reason_code
            ticket_update["rejection_reason_label"] = REJECTION_REASON_CODES.get(
                response_data.rejection_reason_code,
                response_data.rejection_reason_label or response_data.rejection_reason_code
            )
        if response_data.rejection_reason_note:
            ticket_update["rejection_reason_note"] = response_data.rejection_reason_note
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": ticket_update})
    
    # Build note
    status_text = "ACEITE" if response_data.status == "ACCEPTED" else "RECUSADO"
    if response_data.status == "ACCEPTED" and accepted_descriptions:
        note_body = f"Cliente respondeu ao orçamento: {status_text}\n"
        note_body += f"Opções aceites ({accepted_count} de {len(quote_options)}):\n"
        for desc in accepted_descriptions:
            note_body += f"  - {desc}\n"
        note_body += f"Total aceite: {accepted_total:.2f}€"
        # Add acceptance intent to note
        if response_data.acceptance_intent:
            intent_label = ACCEPTANCE_INTENT_CODES.get(response_data.acceptance_intent, response_data.acceptance_intent)
            note_body += f"\n\nIntenção: {intent_label}"
            if response_data.acceptance_intent == "agendar" and response_data.preferred_date:
                period_text = "Manhã" if response_data.preferred_period == "manha" else "Tarde" if response_data.preferred_period == "tarde" else ""
                note_body += f"\nData pretendida: {response_data.preferred_date}"
                if period_text:
                    note_body += f" ({period_text})"
    else:
        note_body = f"Cliente respondeu ao orçamento: {status_text}"
        if response_data.status == "ACCEPTED" and response_data.acceptance_intent:
            intent_label = ACCEPTANCE_INTENT_CODES.get(response_data.acceptance_intent, response_data.acceptance_intent)
            note_body += f"\nIntenção: {intent_label}"
            if response_data.acceptance_intent == "agendar" and response_data.preferred_date:
                period_text = "Manhã" if response_data.preferred_period == "manha" else "Tarde" if response_data.preferred_period == "tarde" else ""
                note_body += f"\nData pretendida: {response_data.preferred_date}"
                if period_text:
                    note_body += f" ({period_text})"
        if response_data.status == "REJECTED" and response_data.rejection_reason_code:
            reason_label = REJECTION_REASON_CODES.get(
                response_data.rejection_reason_code,
                response_data.rejection_reason_label or response_data.rejection_reason_code
            )
            note_body += f"\nMotivo: {reason_label}"
            if response_data.rejection_reason_note:
                note_body += f"\nObservação: {response_data.rejection_reason_note}"
    
    if response_data.comments:
        note_body += f"\nComentários: {response_data.comments}"
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "created_by_user_id": "CLIENTE",
        "body": note_body,
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    # Notify assigned user and supervisors
    notification_body = f"O cliente {ticket['customer_name']} {status_text.lower()} o orçamento do ticket {ticket['ticket_number']}"
    if accepted_total > 0:
        notification_body += f" (Total: {accepted_total:.2f}€)"
    if response_data.acceptance_intent:
        intent_label = ACCEPTANCE_INTENT_CODES.get(response_data.acceptance_intent, "")
        notification_body += f"\n{intent_label}"
        if response_data.acceptance_intent == "agendar" and response_data.preferred_date:
            period_text = "Manhã" if response_data.preferred_period == "manha" else "Tarde" if response_data.preferred_period == "tarde" else ""
            notification_body += f" - {response_data.preferred_date}"
            if period_text:
                notification_body += f" ({period_text})"
    
    if ticket.get("assigned_to_user_id"):
        asyncio.create_task(create_notification(
            user_id=ticket["assigned_to_user_id"],
            title=f"Orçamento {status_text}",
            body=notification_body,
            notification_type="success" if response_data.status == "ACCEPTED" else "warning",
            ticket_id=ticket["id"],
            ticket_number=ticket["ticket_number"]
        ))
    
    asyncio.create_task(notify_supervisors(
        title=f"Orçamento {status_text}",
        body=notification_body,
        notification_type="success" if response_data.status == "ACCEPTED" else "warning",
        ticket_id=ticket["id"],
        ticket_number=ticket["ticket_number"]
    ))
    
    # Notify mechanic via Telegram if ticket came from alert
    if ticket.get("source_alert_id"):
        asyncio.create_task(_notify_mechanic_quote_response(
            ticket=ticket,
            status_text=status_text,
            accepted_total=accepted_total,
        ))
    
    return {
        "status": "success",
        "message": f"Resposta registada: {status_text}"
    }


# ============== PUBLIC ATTACHMENT DOWNLOAD ==============
@router.get("/public/quote/{token}/attachments/{attachment_id}/download")
async def download_attachment_public(token: str, attachment_id: str):
    """Download attachment via public quote token - NO AUTH REQUIRED"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    ticket_id = quote_link["ticket_id"]
    attachment = None
    
    attachment = await db.attachments.find_one({"id": attachment_id, "ticket_id": ticket_id}, {"_id": 0})
    
    if not attachment:
        quote_options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
        for opt in quote_options:
            for att in opt.get("attachments", []):
                if att.get("id") == attachment_id:
                    attachment = att
                    break
            if attachment:
                break
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado")
    
    file_path = UPLOAD_DIR / attachment["filename"]
    
    if file_path.exists():
        return FileResponse(
            path=str(file_path),
            filename=attachment["original_filename"],
            media_type=attachment.get("file_type", "application/pdf")
        )
    
    storage_path = attachment.get("storage_path")
    if storage_path:
        try:
            content, content_type = get_object(storage_path)
            with open(file_path, "wb") as f:
                f.write(content)
            return Response(
                content=content,
                media_type=attachment.get("file_type", content_type),
                headers={"Content-Disposition": f'attachment; filename="{attachment["original_filename"]}"'}
            )
        except Exception as e:
            logger.error(f"Failed to download from object storage: {e}")
    
    return RedirectResponse(url=f"/api/public/quote/{token}/pdf", status_code=302)


# ============== PUBLIC PDF GENERATION ==============
@router.get("/public/quote/{token}/pdf")
async def generate_quote_pdf(token: str):
    """Generate PDF on-the-fly for public quote - NO AUTH REQUIRED"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.colors import HexColor
    
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=410, detail="Link expirado")
    
    ticket = await db.tickets.find_one({"id": quote_link["ticket_id"]}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    quote_options = await db.quote_options.find({"ticket_id": quote_link["ticket_id"]}, {"_id": 0}).to_list(100)
    
    branding = await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
    company_name = branding.get("company_name", "Pneus D. Pedro V")
    
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    NAVY = HexColor('#0B2E4F')
    YELLOW = HexColor('#F4B400')
    GRAY = HexColor('#666666')
    
    # Header
    c.setFillColor(NAVY)
    c.rect(0, height - 80, width, 80, fill=1, stroke=0)
    c.setFillColor(HexColor('#FFFFFF'))
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width/2, height - 45, company_name)
    c.setFont("Helvetica", 12)
    c.drawCentredString(width/2, height - 65, "Gestor De Pedidos")
    
    # Title
    y = height - 120
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, y, f"Orçamento #{ticket['ticket_number']}")
    
    # Customer info
    y -= 40
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(NAVY)
    c.drawString(40, y, "Cliente:")
    c.setFont("Helvetica", 12)
    c.setFillColor(GRAY)
    c.drawString(100, y, ticket.get("customer_name", "-"))
    
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(NAVY)
    c.drawString(40, y, "Telefone:")
    c.setFont("Helvetica", 12)
    c.setFillColor(GRAY)
    c.drawString(110, y, ticket.get("customer_phone", "-"))
    
    if ticket.get("vehicle_plate"):
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(NAVY)
        c.drawString(40, y, "Matrícula:")
        c.setFont("Helvetica", 12)
        c.setFillColor(GRAY)
        c.drawString(115, y, ticket.get("vehicle_plate", "-"))
    
    # Description
    if ticket.get("description"):
        y -= 35
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(NAVY)
        c.drawString(40, y, "Descrição:")
        y -= 18
        c.setFont("Helvetica", 10)
        c.setFillColor(GRAY)
        desc_lines = ticket["description"].split("\n")
        for line in desc_lines[:10]:
            if len(line) > 80:
                line = line[:80] + "..."
            c.drawString(40, y, line)
            y -= 14
    
    # Quote Options
    y -= 30
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Opções de Orçamento:")
    
    total = 0
    if quote_options:
        for i, opt in enumerate(quote_options, 1):
            y -= 25
            if y < 100:
                c.showPage()
                y = height - 50
            
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, f"Opção {i}:")
            
            c.setFont("Helvetica", 11)
            c.setFillColor(GRAY)
            desc = opt.get("description", "-")
            if len(desc) > 60:
                desc = desc[:60] + "..."
            c.drawString(100, y, desc)
            
            amount = float(opt.get("amount", 0) or 0)
            total += amount
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 11)
            c.drawRightString(width - 40, y, f"{amount:.2f} €")
    elif ticket.get("quote_value"):
        y -= 25
        total = float(ticket.get("quote_value", 0))
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 11)
        c.drawString(40, y, "Valor do orçamento")
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(width - 40, y, f"{total:.2f} €")
    
    # Total
    y -= 35
    c.setFillColor(YELLOW)
    c.rect(40, y - 5, width - 80, 25, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y + 3, "TOTAL:")
    c.drawRightString(width - 50, y + 3, f"{total:.2f} €")
    
    # Validity
    y -= 40
    valid_until = ticket.get("quote_valid_until", "")
    if valid_until:
        try:
            valid_date = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            c.setFillColor(GRAY)
            c.setFont("Helvetica", 10)
            c.drawString(40, y, f"Válido até: {valid_date.strftime('%d/%m/%Y')}")
        except Exception:
            pass
    
    # Footer
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width/2, 30, f"Gerado automaticamente em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}")
    
    c.save()
    
    buffer.seek(0)
    pdf_bytes = buffer.read()
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="orcamento_{ticket["ticket_number"]}.pdf"',
            "Content-Length": str(len(pdf_bytes))
        }
    )


# ============== PUBLIC BRANDING ==============
@router.get("/public/branding")
async def get_public_branding():
    """Get branding config for public pages - NO AUTH REQUIRED"""
    config = await db.settings.find_one({"type": "branding_config"}, {"_id": 0})
    if not config:
        return {
            "company_name": "PDPV Tickets",
            "primary_color": "#f97316",
            "logo_url": None,
            "quote_header_text": "Proposta de Orçamento",
            "quote_footer_text": "Obrigado pela sua preferência.",
            "company_phone": None,
            "company_email": None,
            "quote_page_accepted_title": None,
            "quote_page_accepted_message": None,
            "quote_page_rejected_title": None,
            "quote_page_rejected_message": None
        }
    return {
        "company_name": config.get("company_name", "PDPV Tickets"),
        "primary_color": config.get("primary_color", "#f97316"),
        "logo_url": config.get("logo_url"),
        "quote_header_text": config.get("quote_header_text", "Proposta de Orçamento"),
        "quote_footer_text": config.get("quote_footer_text", "Obrigado pela sua preferência."),
        "company_phone": config.get("company_phone"),
        "company_email": config.get("company_email"),
        "quote_page_accepted_title": config.get("quote_page_accepted_title"),
        "quote_page_accepted_message": config.get("quote_page_accepted_message"),
        "quote_page_rejected_title": config.get("quote_page_rejected_title"),
        "quote_page_rejected_message": config.get("quote_page_rejected_message")
    }



async def _notify_mechanic_quote_response(ticket: dict, status_text: str, accepted_total: float = 0):
    """Send Telegram message to mechanic when client accepts/rejects quote."""
    try:
        alert = await db.alerts.find_one(
            {"id": ticket["source_alert_id"], "source": "telegram_alerts"},
            {"_id": 0, "telegram_chat_id": 1, "license_plate": 1}
        )
        if not alert or not alert.get("telegram_chat_id"):
            return

        from modules.telegram_alerts.service import send_message

        plate = ticket.get("vehicle_plate") or alert.get("license_plate") or ""
        plate_text = f" ({plate})" if plate else ""
        ticket_num = ticket.get("ticket_number", "")
        customer = ticket.get("customer_name", "Cliente")

        if status_text == "ACEITE":
            total_text = f"\nValor aceite: {accepted_total:.2f}€" if accepted_total > 0 else ""
            await send_message(
                alert["telegram_chat_id"],
                f"✅ Orçamento <b>ACEITE</b> pelo cliente!\n"
                f"Ticket: {ticket_num}{plate_text}\n"
                f"Cliente: {customer}{total_text}"
            )
        else:
            await send_message(
                alert["telegram_chat_id"],
                f"❌ Orçamento <b>RECUSADO</b> pelo cliente.\n"
                f"Ticket: {ticket_num}{plate_text}\n"
                f"Cliente: {customer}"
            )
    except Exception as e:
        logging.warning(f"[QUOTES] Mechanic Telegram notify error: {e}")
