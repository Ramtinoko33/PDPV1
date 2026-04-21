from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Header, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Set, Any
import uuid
from datetime import datetime, timezone, timedelta, date, time
from passlib.context import CryptContext
import jwt
from enum import Enum
from typing import Tuple
import shutil
import asyncio
import json
from pywebpush import webpush, WebPushException
import resend
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import modular components
from db import db, client
from schemas.user import UserRole, UserCreate, UserLogin, UserResponse, UserUpdate, DashboardConfigUpdate
from schemas.ticket import (
    TicketChannel, TicketType, TicketStatus, TicketPriority,
    MessageDirection, MessageChannel, AlertType,
    TicketCreate, TicketUpdate, TicketResponse, TicketStatusHistoryResponse,
    MessageCreate, MessageResponse, NoteCreate, NoteResponse, AlertResponse,
    ReminderCreate, ReminderResponse, AttachmentResponse, DashboardStats
)
from schemas.customer import (
    VehicleCreate, VehicleResponse, CustomerCreate, CustomerUpdate,
    CustomerResponse, CustomerSearchResult, WhatsAppWebhook, TelegramWebhook
)
from core.security import (
    SECRET_KEY, ALGORITHM, pwd_context,
    create_access_token, create_refresh_token, get_current_user,
    hash_password, verify_password
)
from routes.auth import router as auth_router
from routes.customers import router as customers_router
from routes.users import router as users_router
from routes.vehicles import router as vehicles_router
from routes.tickets import router as tickets_router
from routes.admin import router as admin_router
from routes.quotes import router as quotes_router
from routes.normalization_config import router as norm_config_router

# Helper function to convert URLs in text to clickable links
def convert_urls_to_links(text: str) -> str:
    """Convert plain text URLs to HTML anchor tags"""
    url_pattern = r'(https?://[^\s<>"\']+)'
    def replace_url(match):
        url = match.group(1)
        return f'<a href="{url}" style="color: #f97316; text-decoration: underline;">{url}</a>'
    return re.sub(url_pattern, replace_url, text)

# Resend config
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'onboarding@resend.dev')
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# File storage - imported from services.storage_service
from services.storage_service import (
    UPLOAD_DIR, APP_NAME,
    init_storage, put_object, get_object,
    get_storage_client, is_storage_available
)

# Frontend URL for email links
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://tickets.pneusdpedrov.com')

# VAPID Config for Web Push (strip any surrounding quotes from env vars)
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '').strip().strip('"').strip("'")
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '').strip().strip('"').strip("'")
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@pdpv.pt').strip().strip('"').strip("'")

# VAPID key validation will be done after logger is initialized
VAPID_KEYS_VALID = False

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_id -> websocket
        self.user_roles: Dict[str, str] = {}  # user_id -> role
    
    async def connect(self, websocket: WebSocket, user_id: str, role: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_roles[user_id] = role
        logger.info(f"WebSocket connected: {user_id} ({role})")
    
    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_roles:
            del self.user_roles[user_id]
        logger.info(f"WebSocket disconnected: {user_id}")
    
    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending to {user_id}: {e}")
    
    async def send_to_role(self, role: str, message: dict):
        for user_id, user_role in self.user_roles.items():
            if user_role == role:
                await self.send_to_user(user_id, message)
    
    async def send_to_supervisors(self, message: dict):
        await self.send_to_role("SUPERVISOR", message)
        await self.send_to_role("ADMIN", message)
    
    async def broadcast(self, message: dict, exclude_user: str = None):
        for user_id in self.active_connections:
            if user_id != exclude_user:
                await self.send_to_user(user_id, message)

manager = ConnectionManager()

# Create the main app
app = FastAPI(title="PDPV Tickets API")

# Health check endpoint (for Kubernetes/container orchestration)
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "service": "pdpv-tickets-api"}

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Health check on /api prefix as well
@api_router.get("/health")
async def api_health_check():
    """API health check endpoint."""
    return {"status": "healthy", "service": "pdpv-tickets-api"}

# Modules status endpoint
@api_router.get("/modules/status")
async def modules_status():
    """Get status of all optional modules."""
    try:
        from modules import get_enabled_modules
        modules = get_enabled_modules()
        return {
            "modules": modules,
            "enabled_count": sum(1 for v in modules.values() if v)
        }
    except Exception as e:
        return {"modules": {}, "enabled_count": 0, "error": str(e)}

# ============== ENUMS & MODELS ==============
# All enums and models are imported from schemas package:
# - schemas.user: UserRole, UserCreate, UserLogin, UserResponse, UserUpdate, DashboardConfigUpdate
# - schemas.ticket: TicketChannel, TicketType, TicketStatus, TicketPriority, MessageDirection,
#                   MessageChannel, AlertType, TicketCreate, TicketUpdate, TicketResponse, etc.
# - schemas.customer: VehicleCreate, VehicleResponse, CustomerCreate, CustomerUpdate,
#                     CustomerResponse, CustomerSearchResult, WhatsAppWebhook, TelegramWebhook

# ============== TICKET HELPERS (imported from services.ticket_service) ==============
from services.ticket_service import (
    generate_ticket_number,
    log_status_change,
    log_quote_change,
    get_or_create_reply_token,
    REJECTION_REASON_CODES
)

# ============== SLA CONFIGURATION (imported from services.sla_service) ==============
from services.sla_service import (
    BUSINESS_HOURS, SLA_TARGETS_MINUTES, SLA_DEFAULT_MINUTES,
    SLA_USE_BUSINESS_HOURS, SLA_PAUSE_ON_AGUARDA_CLIENTE,
    parse_time_string, load_sla_config_from_db as _load_sla_config,
    load_holidays_from_db as _load_holidays,
    is_business_day, get_business_hours_for_day, get_business_minutes_in_day,
    add_business_minutes, calculate_business_minutes_between,
    compute_sla_due, compute_sla_due_simple,
    check_ticket_overdue, calculate_sla_elapsed_minutes
)

# Wrapper to use db from this module
async def load_sla_config_from_db():
    """Load SLA configuration from database."""
    await _load_sla_config(db)

async def load_holidays_from_db():
    """Load holidays from database."""
    await _load_holidays(db)


# ============== AUTH ROUTES ==============
# Auth routes (register, login, refresh, logout, /me) are in routes/auth.py

# ============== CUSTOMER/USER/VEHICLE ROUTES ==============
# Customer routes are in routes/customers.py
# User management routes are in routes/users.py
# Vehicle routes are in routes/vehicles.py

# ============== TICKET ROUTES ==============
# Ticket routes (CRUD, archive, status-history) are in routes/tickets.py

# ============== PUBLIC TICKET CONFIG (for authenticated users) ==============
@api_router.get("/ticket-statuses")
async def list_ticket_statuses(current_user: dict = Depends(get_current_user)):
    """List all ticket statuses - available to all authenticated users"""
    statuses = await db.ticket_statuses.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)
    
    if not statuses:
        # Return default statuses if none exist
        default_statuses = [
            {"id": str(uuid.uuid4()), "code": "ABERTO", "label": "Aberto", "color": "#3b82f6", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "EM_TRATAMENTO", "label": "Em Tratamento", "color": "#f59e0b", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGUARDA_CLIENTE", "label": "Aguarda Cliente", "color": "#8b5cf6", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGENDADO", "label": "Agendado", "color": "#10b981", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "FECHADO", "label": "Fechado", "color": "#6b7280", "is_final": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ACEITE_LINK", "label": "Aceite (Link)", "color": "#22c55e", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "REJEITADO_LINK", "label": "Rejeitado (Link)", "color": "#ef4444", "is_final": True, "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        await db.ticket_statuses.insert_many(default_statuses)
        statuses = default_statuses
    
    return statuses


@api_router.get("/ticket-types")
async def list_ticket_types(current_user: dict = Depends(get_current_user)):
    """List all ticket types - available to all authenticated users"""
    types = await db.ticket_types.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)
    
    if not types:
        # Return default types if none exist
        default_types = [
            {"id": str(uuid.uuid4()), "code": "ORCAMENTO_PNEUS", "label": "Orçamento Pneus", "color": "#f97316", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ORCAMENTO_MECANICA", "label": "Orçamento Mecânica", "color": "#3b82f6", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "MARCACAO", "label": "Marcação", "color": "#10b981", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "INFORMACAO", "label": "Informação", "color": "#8b5cf6", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "INTERNO", "label": "Interno", "color": "#6b7280", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "RECLAMACAO", "label": "Reclamação", "color": "#ef4444", "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        await db.ticket_types.insert_many(default_types)
        types = default_types
    
    return types

# ============== MESSAGES ==============
@api_router.post("/tickets/{ticket_id}/messages", response_model=MessageResponse)
async def create_message(ticket_id: str, message_data: MessageCreate, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    now = datetime.now(timezone.utc)
    message_id = str(uuid.uuid4())
    
    message_doc = {
        "id": message_id,
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "direction": MessageDirection.OUTBOUND.value,
        "channel": message_data.channel.value,
        "body": message_data.body,
        "from_text": user["email"],
        "to_text": ticket.get("customer_email") or ticket.get("customer_phone"),
        "created_by_user_id": user["id"],
        "attachment_ids": message_data.attachment_ids
    }
    await db.messages.insert_one(message_doc)
    
    # Update ticket
    update_doc = {
        "updated_at": now.isoformat(),
        "last_public_message_at": now.isoformat(),
        "first_response_done": True
    }
    
    # If this is a quote response, change status to AGUARDA_CLIENTE
    if message_data.is_quote_response:
        update_doc["status"] = TicketStatus.AGUARDA_CLIENTE.value
        update_doc["quote_sent"] = True
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": update_doc})
    
    # Send email via Resend if customer has email and API key is configured
    customer_email = ticket.get("customer_email")
    if customer_email and RESEND_API_KEY:
        try:
            subject = f"[Ticket #{ticket['ticket_number']}] Resposta ao seu pedido"
            
            # Get reply link + branding for email
            try:
                email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
                await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
                reply_frontend_url = email_settings.get("frontend_url", FRONTEND_URL) if email_settings else FRONTEND_URL
                email_from = email_settings.get("email_from", EMAIL_FROM) if email_settings else EMAIL_FROM
            except Exception:
                reply_frontend_url = FRONTEND_URL
                email_from = EMAIL_FROM
            
            reply_token = await get_or_create_reply_token(ticket_id)
            reply_link_url = f"{reply_frontend_url}/ticket/reply/{reply_token}"
            
            # Extract quote link from message if present and remove from visible text
            message_body = message_data.body
            quote_link = None
            quote_link_match = re.search(r'(https?://[^\s]+/quote/[^\s]+)', message_body)
            if quote_link_match:
                quote_link = quote_link_match.group(1)
                # Remove the URL from message body
                message_body = re.sub(r'https?://[^\s]+/quote/[^\s]+', '', message_body).strip()
            
            # Clean up message - convert newlines to <br> and remove empty lines
            message_html = message_body.replace(chr(10), '<br>')
            message_html = re.sub(r'(<br>\s*){3,}', '<br><br>', message_html)  # Max 2 line breaks
            
            # Logo URL (white text version)
            logo_url = "https://customer-assets.emergentagent.com/job_808588e9-0bee-4c5b-a24f-c36fa11718a7/artifacts/bstd2ega_logotipo%20de%20letras%20brancas.png"
            
            # Build quote button HTML (only if quote_link exists) - Mobile optimized
            quote_button_html = ""
            if quote_link:
                quote_button_html = f'''
                    <!--[if mso]>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr><td align="center" style="padding: 20px 0 12px 0;">
                    <![endif]-->
                    <div style="text-align: center; margin: 20px 0 12px 0;">
                        <a href="{quote_link}" style="background-color: #F4B400; color: #0B2E4F; padding: 14px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; min-width: 200px; box-sizing: border-box;">
                            Ver Proposta / Orçamento
                        </a>
                    </div>
                    <!--[if mso]>
                    </td></tr></table>
                    <![endif]-->
                '''
            
            # Build HTML content with compact responsive design
            html_content = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Gestor De Pedidos</title>
            </head>
            <body style="margin: 0; padding: 0; background-color: #f4f4f4;">
            <!--[if mso]>
            <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" align="center">
            <tr><td>
            <![endif]-->
            <div style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; width: 100%; margin: 0 auto; background-color: #f9fafb;">
                <!-- Header with Logo -->
                <div style="background-color: #0B2E4F; padding: 16px 20px; text-align: center;">
                    <img src="{logo_url}" alt="Pneus D. Pedro V" style="max-width: 140px; height: auto; margin-bottom: 8px;" />
                    <p style="color: white; font-size: 18px; font-weight: bold; margin: 0;">Gestor De Pedidos</p>
                </div>
                
                <!-- Body -->
                <div style="padding: 20px 18px; background-color: #f9fafb;">
                    <p style="color: #333; font-size: 15px; margin: 0 0 14px 0; line-height: 1.4;">Olá <strong>{ticket['customer_name']}</strong>,</p>
                    <p style="color: #333; font-size: 15px; margin: 0 0 16px 0; line-height: 1.4;">Recebeu uma nova resposta ao seu pedido:</p>
                    
                    <!-- Message Box -->
                    <div style="background-color: white; padding: 14px 16px; border-left: 4px solid #F4B400; margin: 0 0 16px 0; border-radius: 0 6px 6px 0;">
                        <p style="color: #333; font-size: 14px; line-height: 1.6; margin: 0;">{message_html}</p>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 13px; margin: 0 0 6px 0;">
                        Referência: <strong>{ticket['ticket_number']}</strong>
                    </p>
                    {f'<p style="color: #6b7280; font-size: 13px; margin: 0 0 12px 0;">Este email inclui {len(message_data.attachment_ids)} anexo(s).</p>' if message_data.attachment_ids else ''}
                    
                    <!-- Primary Button: Quote (only if quote_link exists) -->
                    {quote_button_html}
                    
                    <!-- Secondary Button: Reply -->
                    <!--[if mso]>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr><td align="center" style="padding: 12px 0 6px 0;">
                    <![endif]-->
                    <div style="text-align: center; margin: 12px 0 6px 0;">
                        <a href="{reply_link_url}" style="background-color: #0F5132; color: #FFFFFF; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-size: 13px; display: inline-block;">
                            Responder / Enviar documentos
                        </a>
                    </div>
                    <!--[if mso]>
                    </td></tr></table>
                    <![endif]-->
                </div>
                
                <!-- Footer -->
                <div style="background-color: #0B2E4F; padding: 10px 16px; text-align: center;">
                    <p style="color: #9ca3af; font-size: 11px; margin: 0;">
                        Email automático | Pneus D. Pedro V.
                    </p>
                </div>
            </div>
            <!--[if mso]>
            </td></tr></table>
            <![endif]-->
            </body>
            </html>
            '''
            
            params = {
                "from": email_from,
                "to": [customer_email],
                "subject": subject,
                "html": html_content
            }
            
            # Send email in background (non-blocking)
            email_result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"[RESEND] Email sent to {customer_email}, ID: {email_result.get('id')}")
        except Exception as e:
            logger.error(f"[RESEND] Failed to send email to {customer_email}: {str(e)}")
    else:
        attachments_info = f" (com {len(message_data.attachment_ids)} anexo(s))" if message_data.attachment_ids else ""
        logger.info(f"[EMAIL NOT SENT] No email or API key. Would send to {message_doc['to_text']}: {message_data.body[:100]}{attachments_info}")
    
    message_doc["created_by_name"] = user["name"]
    return MessageResponse(**message_doc)

@api_router.get("/tickets/{ticket_id}/messages", response_model=List[MessageResponse])
async def list_messages(ticket_id: str, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    messages = await db.messages.find({"ticket_id": ticket_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    
    # Get user names
    user_ids = list(set([m.get("created_by_user_id") for m in messages if m.get("created_by_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    for m in messages:
        m["created_by_name"] = users_map.get(m.get("created_by_user_id"))
    
    return [MessageResponse(**m) for m in messages]

# ============== NOTES ==============
@api_router.post("/tickets/{ticket_id}/notes", response_model=NoteResponse)
async def create_note(ticket_id: str, note_data: NoteCreate, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    now = datetime.now(timezone.utc)
    note_id = str(uuid.uuid4())
    
    note_doc = {
        "id": note_id,
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "created_by_user_id": user["id"],
        "body": note_data.body,
        "is_system": False
    }
    await db.notes.insert_one(note_doc)
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": {"updated_at": now.isoformat()}})
    
    note_doc["created_by_name"] = user["name"]
    return NoteResponse(**note_doc)

@api_router.get("/tickets/{ticket_id}/notes", response_model=List[NoteResponse])
async def list_notes(ticket_id: str, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    notes = await db.notes.find({"ticket_id": ticket_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    
    # Get user names
    user_ids = list(set([n.get("created_by_user_id") for n in notes if n.get("created_by_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    for n in notes:
        n["created_by_name"] = users_map.get(n.get("created_by_user_id"))
    
    return [NoteResponse(**n) for n in notes]

# ============== ALERTS ==============
@api_router.get("/tickets/{ticket_id}/alerts", response_model=List[AlertResponse])
async def list_alerts(ticket_id: str, current_user: dict = Depends(get_current_user)):
    current_user
    
    alerts = await db.alerts.find({"ticket_id": ticket_id, "source": {"$ne": "telegram_alerts"}}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [AlertResponse(**a) for a in alerts]

@api_router.put("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    current_user
    
    result = await db.alerts.update_one({"id": alert_id}, {"$set": {"is_resolved": True}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return {"message": "Alerta resolvido"}

# ============== REMINDERS ==============
@api_router.get("/tickets/{ticket_id}/reminders", response_model=List[ReminderResponse])
async def list_reminders(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """List all reminders for a ticket"""
    reminders = await db.reminders.find({"ticket_id": ticket_id}, {"_id": 0}).sort("due_at", 1).to_list(100)
    
    now = datetime.now(timezone.utc)
    result = []
    for r in reminders:
        # Get assigned user name
        if r.get("assigned_to_user_id"):
            user = await db.users.find_one({"id": r["assigned_to_user_id"]}, {"_id": 0, "name": 1})
            r["assigned_to_name"] = user["name"] if user else None
        # Get creator name
        if r.get("created_by_user_id"):
            creator = await db.users.find_one({"id": r["created_by_user_id"]}, {"_id": 0, "name": 1})
            r["created_by_name"] = creator["name"] if creator else None
        # Check if overdue
        try:
            due_at = datetime.fromisoformat(r["due_at"].replace("Z", "+00:00"))
            r["is_overdue"] = not r.get("is_done", False) and due_at < now
        except:
            r["is_overdue"] = False
        result.append(ReminderResponse(**r))
    return result

# General reminders (not tied to a ticket)
@api_router.get("/reminders", response_model=List[ReminderResponse])
async def list_all_reminders(
    filter: str = "all",  # all, today, week, overdue
    current_user: dict = Depends(get_current_user)
):
    """List all reminders for current user or all (for supervisors)"""
    user = current_user
    now = datetime.now(timezone.utc)
    
    # Build query
    query = {}
    
    # Agents only see their own reminders
    if user["role"] == UserRole.AGENT.value:
        query["assigned_to_user_id"] = user["id"]
    
    # Apply filters
    if filter == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        query["due_at"] = {"$gte": today_start.isoformat(), "$lt": today_end.isoformat()}
        query["is_done"] = False
    elif filter == "week":
        week_end = now + timedelta(days=7)
        query["due_at"] = {"$lt": week_end.isoformat()}
        query["is_done"] = False
    elif filter == "overdue":
        query["due_at"] = {"$lt": now.isoformat()}
        query["is_done"] = False
    elif filter == "pending":
        query["is_done"] = False
    
    reminders = await db.reminders.find(query, {"_id": 0}).sort("due_at", 1).to_list(200)
    
    result = []
    for r in reminders:
        # Get ticket info if associated
        if r.get("ticket_id"):
            ticket = await db.tickets.find_one({"id": r["ticket_id"]}, {"_id": 0, "ticket_number": 1})
            r["ticket_number"] = ticket["ticket_number"] if ticket else None
        # Get assigned user name
        if r.get("assigned_to_user_id"):
            assigned = await db.users.find_one({"id": r["assigned_to_user_id"]}, {"_id": 0, "name": 1})
            r["assigned_to_name"] = assigned["name"] if assigned else None
        # Get creator name
        if r.get("created_by_user_id"):
            creator = await db.users.find_one({"id": r["created_by_user_id"]}, {"_id": 0, "name": 1})
            r["created_by_name"] = creator["name"] if creator else None
        # Check if overdue
        try:
            due_at = datetime.fromisoformat(r["due_at"].replace("Z", "+00:00"))
            r["is_overdue"] = not r.get("is_done", False) and due_at < now
        except:
            r["is_overdue"] = False
        result.append(ReminderResponse(**r))
    
    return result

@api_router.post("/reminders", response_model=ReminderResponse)
async def create_general_reminder(data: ReminderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new reminder (optionally linked to a ticket)"""
    user = current_user
    
    # Check permissions
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    # If ticket_id provided, validate it exists
    ticket_number = None
    if data.ticket_id:
        ticket = await db.tickets.find_one({"id": data.ticket_id}, {"_id": 0, "ticket_number": 1})
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket não encontrado")
        ticket_number = ticket["ticket_number"]
    
    now = datetime.now(timezone.utc)
    assigned_to = data.assigned_to_user_id or user["id"]
    
    reminder_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": data.ticket_id,  # Can be None
        "description": data.description,
        "due_at": data.due_at,
        "assigned_to_user_id": assigned_to,
        "is_done": False,
        "created_by_user_id": user["id"],
        "created_at": now.isoformat(),
        "completed_at": None
    }
    await db.reminders.insert_one(reminder_doc)
    
    # Get names for response
    assigned_user = await db.users.find_one({"id": assigned_to}, {"_id": 0, "name": 1})
    reminder_doc["assigned_to_name"] = assigned_user["name"] if assigned_user else None
    reminder_doc["created_by_name"] = user["name"]
    reminder_doc["ticket_number"] = ticket_number
    reminder_doc["is_overdue"] = False
    
    return ReminderResponse(**reminder_doc)

@api_router.post("/tickets/{ticket_id}/reminders", response_model=ReminderResponse)
async def create_reminder(ticket_id: str, data: ReminderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new reminder for a ticket"""
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    now = datetime.now(timezone.utc)
    assigned_to = data.assigned_to_user_id or user["id"]
    
    reminder_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "description": data.description,
        "due_at": data.due_at,
        "assigned_to_user_id": assigned_to,
        "is_done": False,
        "created_by_user_id": user["id"],
        "created_at": now.isoformat(),
        "completed_at": None
    }
    await db.reminders.insert_one(reminder_doc)
    
    # Get names for response
    assigned_user = await db.users.find_one({"id": assigned_to}, {"_id": 0, "name": 1})
    reminder_doc["assigned_to_name"] = assigned_user["name"] if assigned_user else None
    reminder_doc["created_by_name"] = user["name"]
    reminder_doc["is_overdue"] = False
    
    return ReminderResponse(**reminder_doc)

@api_router.put("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a reminder as done"""
    user = current_user
    
    reminder = await db.reminders.find_one({"id": reminder_id}, {"_id": 0})
    if not reminder:
        raise HTTPException(status_code=404, detail="Lembrete não encontrado")
    
    # Only assigned user or supervisor/admin can complete
    is_assigned = reminder.get("assigned_to_user_id") == user["id"]
    is_supervisor = user["role"] in [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]
    
    if not is_assigned and not is_supervisor:
        raise HTTPException(status_code=403, detail="Sem permissão para concluir este lembrete")
    
    now = datetime.now(timezone.utc)
    await db.reminders.update_one(
        {"id": reminder_id},
        {"$set": {"is_done": True, "completed_at": now.isoformat()}}
    )
    return {"message": "Lembrete concluído"}

@api_router.put("/reminders/{reminder_id}/reopen")
async def reopen_reminder(reminder_id: str, current_user: dict = Depends(get_current_user)):
    """Reopen a completed reminder"""
    user = current_user
    
    reminder = await db.reminders.find_one({"id": reminder_id}, {"_id": 0})
    if not reminder:
        raise HTTPException(status_code=404, detail="Lembrete não encontrado")
    
    # Only assigned user or supervisor/admin can reopen
    is_assigned = reminder.get("assigned_to_user_id") == user["id"]
    is_supervisor = user["role"] in [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]
    
    if not is_assigned and not is_supervisor:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    await db.reminders.update_one(
        {"id": reminder_id},
        {"$set": {"is_done": False, "completed_at": None}}
    )
    return {"message": "Lembrete reaberto"}

@api_router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a reminder"""
    user = current_user
    
    reminder = await db.reminders.find_one({"id": reminder_id}, {"_id": 0})
    if not reminder:
        raise HTTPException(status_code=404, detail="Lembrete não encontrado")
    
    # Only creator or supervisor/admin can delete
    is_creator = reminder.get("created_by_user_id") == user["id"]
    is_supervisor = user["role"] in [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]
    
    if not is_creator and not is_supervisor:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    await db.reminders.delete_one({"id": reminder_id})
    return {"message": "Lembrete eliminado"}

@api_router.get("/reminders/my-today", response_model=List[ReminderResponse])
async def get_my_reminders_today(current_user: dict = Depends(get_current_user)):
    """Get current user's reminders for today (not done)"""
    user = current_user
    
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Get reminders assigned to current user, due today or overdue, not done
    reminders = await db.reminders.find({
        "assigned_to_user_id": user["id"],
        "is_done": False,
        "due_at": {"$lt": today_end.isoformat()}
    }, {"_id": 0}).sort("due_at", 1).to_list(50)
    
    result = []
    for r in reminders:
        # Get ticket info
        ticket = await db.tickets.find_one({"id": r["ticket_id"]}, {"_id": 0, "ticket_number": 1})
        r["ticket_number"] = ticket["ticket_number"] if ticket else None
        # Check if overdue
        try:
            due_at = datetime.fromisoformat(r["due_at"].replace("Z", "+00:00"))
            r["is_overdue"] = due_at < now
        except:
            r["is_overdue"] = False
        r["assigned_to_name"] = user["name"]
        result.append(ReminderResponse(**r))
    
    return result

# ============== ATTACHMENTS ==============
@api_router.post("/tickets/{ticket_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment(ticket_id: str, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Generate unique filename
    attachment_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    stored_filename = f"{attachment_id}{file_ext}"
    content_type = file.content_type or "application/octet-stream"
    
    # Try to upload to object storage first (persistent)
    storage_path = None
    try:
        if init_storage():
            storage_path = f"{APP_NAME}/attachments/{ticket_id}/{stored_filename}"
            put_object(storage_path, content, content_type)
            logger.info(f"File uploaded to object storage: {storage_path}")
    except Exception as e:
        logger.warning(f"Object storage upload failed, using local storage: {e}")
        storage_path = None
    
    # Also save locally for quick access (cache)
    file_path = UPLOAD_DIR / stored_filename
    with open(file_path, "wb") as f:
        f.write(content)
    
    now = datetime.now(timezone.utc)
    attachment_doc = {
        "id": attachment_id,
        "ticket_id": ticket_id,
        "filename": stored_filename,
        "original_filename": file.filename,
        "file_type": content_type,
        "file_size": file_size,
        "uploaded_at": now.isoformat(),
        "uploaded_by_user_id": user["id"],
        "storage_path": storage_path  # Object storage path (if available)
    }
    await db.attachments.insert_one(attachment_doc)
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": {"updated_at": now.isoformat()}})
    
    attachment_doc["uploaded_by_name"] = user["name"]
    return AttachmentResponse(**attachment_doc)

@api_router.get("/tickets/{ticket_id}/attachments", response_model=List[AttachmentResponse])
async def list_attachments(ticket_id: str, current_user: dict = Depends(get_current_user)):
    current_user
    
    attachments = await db.attachments.find({"ticket_id": ticket_id}, {"_id": 0}).sort("uploaded_at", -1).to_list(1000)
    
    # Get user names
    user_ids = list(set([a.get("uploaded_by_user_id") for a in attachments if a.get("uploaded_by_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    for a in attachments:
        a["uploaded_by_name"] = users_map.get(a.get("uploaded_by_user_id"))
    
    return [AttachmentResponse(**a) for a in attachments]

@api_router.get("/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: str, current_user: dict = Depends(get_current_user)):
    current_user
    
    attachment = await db.attachments.find_one({"id": attachment_id}, {"_id": 0})
    if not attachment:
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado")
    
    file_path = UPLOAD_DIR / attachment["filename"]
    
    # Try local file first
    if file_path.exists():
        return FileResponse(
            path=str(file_path),
            filename=attachment["original_filename"],
            media_type=attachment["file_type"]
        )
    
    # Try object storage
    storage_path = attachment.get("storage_path")
    if storage_path:
        try:
            content, content_type = get_object(storage_path)
            # Cache locally for future requests
            with open(file_path, "wb") as f:
                f.write(content)
            return Response(
                content=content,
                media_type=attachment.get("file_type", content_type),
                headers={"Content-Disposition": f'attachment; filename="{attachment["original_filename"]}"'}
            )
        except Exception as e:
            logger.error(f"Failed to download from object storage: {e}")
    
    raise HTTPException(status_code=404, detail="Ficheiro não encontrado no servidor. Os ficheiros podem ter sido perdidos após um deployment. Por favor, carregue o ficheiro novamente.")

# ============== DASHBOARD ==============
@api_router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    user = current_user
    
    # Base query: exclude archived tickets
    base_query = {"archived_at": None}
    
    # Role-based filtering
    if user["role"] == UserRole.AGENT.value:
        base_query["assigned_to_user_id"] = user["id"]
    elif user["role"] == UserRole.INTERNAL_CREATOR.value:
        return DashboardStats()
    
    # Apply dashboard preferences
    if user.get("dashboard_only_mine") and user["role"] != UserRole.AGENT.value:
        base_query["assigned_to_user_id"] = user["id"]
    pref_types = user.get("dashboard_default_types", [])
    if pref_types:
        base_query["type"] = {"$in": pref_types}
    
    # Count stats with new statuses
    novos = await db.tickets.count_documents({**base_query, "status": TicketStatus.ABERTO.value})
    aguarda_cliente = await db.tickets.count_documents({**base_query, "status": TicketStatus.AGUARDA_CLIENTE.value})
    em_tratamento = await db.tickets.count_documents({**base_query, "status": TicketStatus.EM_TRATAMENTO.value})
    
    # Count overdue using simplified SLA
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    
    # Query for overdue (not closed and past SLA due date without first response)
    atrasados = await db.tickets.count_documents({
        **base_query,
        "status": {"$ne": TicketStatus.FECHADO.value},
        "first_response_done": False,
        "sla_due": {"$lt": now_iso}
    })
    
    total = await db.tickets.count_documents(base_query)
    
    return DashboardStats(
        novos=novos,
        atrasados_sla=atrasados,
        aguarda_cliente=aguarda_cliente,
        em_tratamento=em_tratamento,
        total=total
    )

@api_router.get("/dashboard/customer-stats")
async def get_customer_stats(current_user: dict = Depends(get_current_user)):
    """Get customer statistics for dashboard."""
    from services.customer_service import get_customer_stats as fetch_customer_stats
    
    stats = await fetch_customer_stats()
    return stats

# ============== WEBHOOKS ==============
@api_router.post("/webhook/whatsapp/inbound")
async def whatsapp_webhook(data: WhatsAppWebhook):
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=48)
    
    # Find existing open ticket for this phone (excluding archived and closed)
    existing_ticket = await db.tickets.find_one({
        "customer_phone": data.phone,
        "status": {"$ne": TicketStatus.FECHADO.value},
        "archived_at": None,
        "created_at": {"$gte": threshold.isoformat()}
    }, {"_id": 0}, sort=[("created_at", -1)])
    
    if existing_ticket:
        # Add message to existing ticket
        message_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": existing_ticket["id"],
            "created_at": now.isoformat(),
            "direction": MessageDirection.INBOUND.value,
            "channel": MessageChannel.WHATSAPP.value,
            "body": data.message_text,
            "from_text": data.phone,
            "to_text": None,
            "created_by_user_id": None
        }
        await db.messages.insert_one(message_doc)
        
        await db.tickets.update_one(
            {"id": existing_ticket["id"]},
            {"$set": {"last_public_message_at": now.isoformat(), "updated_at": now.isoformat()}}
        )
        
        # Create notification for unassigned tickets
        if not existing_ticket.get("assigned_to_user_id"):
            alert_doc = {
                "id": str(uuid.uuid4()),
                "ticket_id": existing_ticket["id"],
                "created_at": now.isoformat(),
                "alert_type": AlertType.FOLLOWUP.value,
                "body": f"Nova mensagem WhatsApp de {data.name} ({data.phone})",
                "is_resolved": False
            }
            await db.alerts.insert_one(alert_doc)
        
        return {"status": "message_added", "ticket_id": existing_ticket["id"]}
    else:
        # Create new ticket
        ticket_id = str(uuid.uuid4())
        ticket_number = generate_ticket_number()
        
        # Calculate SLA based on ticket type (INFORMACAO default) and business hours
        sla_due, sla_target_minutes, sla_policy_key = compute_sla_due(
            ticket_type=TicketType.INFORMACAO.value,
            created_at=now
        )
        
        ticket_doc = {
            "id": ticket_id,
            "ticket_number": ticket_number,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "channel": TicketChannel.WHATSAPP.value,
            "type": TicketType.INFORMACAO.value,
            "status": TicketStatus.ABERTO.value,
            "priority": TicketPriority.NORMAL.value,
            "description": data.message_text,
            "customer_name": data.name,
            "customer_phone": data.phone,
            "customer_email": None,
            "vehicle_plate": None,
            "assigned_to_user_id": None,
            "last_public_message_at": now.isoformat(),
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
            "created_by_user_id": None,
            "archived_at": None,
            "archived_by": None
        }
        await db.tickets.insert_one(ticket_doc)
        
        # Add inbound message
        message_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "created_at": now.isoformat(),
            "direction": MessageDirection.INBOUND.value,
            "channel": MessageChannel.WHATSAPP.value,
            "body": data.message_text,
            "from_text": data.phone,
            "to_text": None,
            "created_by_user_id": None
        }
        await db.messages.insert_one(message_doc)
        
        # Create alert for new ticket
        alert_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "created_at": now.isoformat(),
            "alert_type": AlertType.FOLLOWUP.value,
            "body": f"Novo ticket WhatsApp de {data.name} ({data.phone})",
            "is_resolved": False
        }
        await db.alerts.insert_one(alert_doc)
        
        # Notify supervisors
        asyncio.create_task(notify_supervisors(
            title="Novo Ticket WhatsApp",
            body=f"Mensagem de {data.name} ({data.phone})",
            notification_type="warning",
            ticket_id=ticket_id,
            ticket_number=ticket_number
        ))
        
        return {"status": "ticket_created", "ticket_id": ticket_id, "ticket_number": ticket_number}

@api_router.post("/webhook/telegram/transcribed")
async def telegram_webhook(data: TelegramWebhook):
    now = datetime.now(timezone.utc)
    
    ticket_id = str(uuid.uuid4())
    ticket_number = generate_ticket_number()
    
    # Calculate SLA based on ticket type (INTERNO) and business hours
    sla_due, sla_target_minutes, sla_policy_key = compute_sla_due(
        ticket_type=TicketType.INTERNO.value,
        created_at=now
    )
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": TicketChannel.TELEGRAM.value,
        "type": TicketType.INTERNO.value,
        "status": TicketStatus.ABERTO.value,
        "priority": TicketPriority.NORMAL.value,
        "description": data.transcript_text,
        "customer_name": data.sender_name,
        "customer_phone": data.sender_id,
        "customer_email": None,
        "vehicle_plate": None,
        "assigned_to_user_id": None,
        "last_public_message_at": None,
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
        "created_by_user_id": None,
        "archived_at": None,
        "archived_by": None
    }
    await db.tickets.insert_one(ticket_doc)
    
    # Create alert
    alert_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "alert_type": AlertType.FOLLOWUP.value,
        "body": f"Novo ticket interno via Telegram de {data.sender_name}",
        "is_resolved": False
    }
    await db.alerts.insert_one(alert_doc)
    
    return {"status": "ticket_created", "ticket_id": ticket_id, "ticket_number": ticket_number}

# ============== EXPORT ==============
@api_router.get("/export/tickets")
async def export_tickets(current_user: dict = Depends(get_current_user)):
    user = current_user
    
    if user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem exportar")
    
    tickets = await db.tickets.find({}, {"_id": 0}).to_list(100000)
    
    # Convert to CSV format
    import io
    import csv
    
    output = io.StringIO()
    if tickets:
        writer = csv.DictWriter(output, fieldnames=tickets[0].keys())
        writer.writeheader()
        writer.writerows(tickets)
    
    csv_content = output.getvalue()
    
    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets_export.csv"}
    )

# ============== SEED DATA ==============
@api_router.post("/seed")
async def seed_data():
    # Check if admin exists
    admin = await db.users.find_one({"email": "admin@pdpv.pt"})
    if admin:
        return {"message": "Dados já existem"}
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Create admin user
    admin_doc = {
        "id": str(uuid.uuid4()),
        "email": "admin@pdpv.pt",
        "password_hash": pwd_context.hash("HCNMEnKMLq"),
        "name": "Administrador",
        "role": UserRole.ADMIN.value,
        "created_at": now
    }
    await db.users.insert_one(admin_doc)
    
    # Create supervisor
    supervisor_doc = {
        "id": str(uuid.uuid4()),
        "email": "supervisor@pdpv.pt",
        "password_hash": pwd_context.hash("super123"),
        "name": "Maria Silva",
        "role": UserRole.SUPERVISOR.value,
        "created_at": now
    }
    await db.users.insert_one(supervisor_doc)
    
    # Create agent
    agent_doc = {
        "id": str(uuid.uuid4()),
        "email": "agente@pdpv.pt",
        "password_hash": pwd_context.hash("agente123"),
        "name": "João Santos",
        "role": UserRole.AGENT.value,
        "created_at": now
    }
    await db.users.insert_one(agent_doc)
    
    return {"message": "Dados de seed criados com sucesso"}

# ============== NOTIFICATIONS API ==============
class NotificationCreate(BaseModel):
    title: str
    body: str
    type: str = "info"  # info, warning, success, error
    ticket_id: Optional[str] = None
    ticket_number: Optional[str] = None

class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    title: str
    body: str
    type: str
    ticket_id: Optional[str] = None
    ticket_number: Optional[str] = None
    created_at: str
    read: bool = False

@api_router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(current_user: dict = Depends(get_current_user), limit: int = 50):
    notifications = await db.notifications.find(
        {"user_id": current_user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return [NotificationResponse(**n) for n in notifications]

@api_router.get("/notifications/unread-count")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    count = await db.notifications.count_documents({
        "user_id": current_user["id"],
        "read": False
    })
    return {"count": count}

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.update_one(
        {"id": notification_id, "user_id": current_user["id"]},
        {"$set": {"read": True}}
    )
    return {"message": "Notificação marcada como lida"}

@api_router.put("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    await db.notifications.update_many(
        {"user_id": current_user["id"], "read": False},
        {"$set": {"read": True}}
    )
    return {"message": "Todas as notificações marcadas como lidas"}

# ============== WEB PUSH NOTIFICATIONS ==============
class PushSubscription(BaseModel):
    endpoint: str
    keys: dict  # Contains p256dh and auth keys

@api_router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key for the frontend to use"""
    return {"publicKey": VAPID_PUBLIC_KEY}

@api_router.post("/admin/webpush/generate-keys")
async def admin_generate_vapid_keys(current_user: dict = Depends(get_current_user)):
    """Admin: generate new VAPID keys and store in DB"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin only")
    global VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_KEYS_VALID
    try:
        keys = await generate_and_store_vapid_keys()
        from py_vapid import Vapid
        Vapid.from_string(private_key=keys["vapid_private_key"])
        VAPID_PUBLIC_KEY = keys["vapid_public_key"]
        VAPID_PRIVATE_KEY = keys["vapid_private_key"]
        VAPID_KEYS_VALID = True
        logger.info(f"[VAPID] Admin {current_user['email']} regenerated VAPID keys")
        sync_vapid_to_notification_service()
        return {"status": "success", "public_key": VAPID_PUBLIC_KEY}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar chaves: {str(e)}")


@api_router.delete("/admin/clear-all-tickets")
async def admin_clear_all_tickets(current_user: dict = Depends(get_current_user)):
    """Admin: Clear all tickets and related data for fresh start"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin only")
    
    collections_to_clear = [
        'tickets',
        'messages', 
        'notes',
        'attachments',
        'alerts',
        'quote_options',
        'quote_links',
        'quote_history',
        'reminders',
        'reply_links',
        'notifications',
        'ticket_status_history'
    ]
    
    total_deleted = 0
    results = {}
    
    for collection in collections_to_clear:
        try:
            result = await db[collection].delete_many({})
            results[collection] = result.deleted_count
            total_deleted += result.deleted_count
        except Exception as e:
            results[collection] = f"error: {str(e)}"
    
    logger.info(f"[ADMIN] {current_user['email']} cleared all tickets. Total: {total_deleted} records deleted")
    
    return {
        "status": "success",
        "total_deleted": total_deleted,
        "details": results
    }


@api_router.get("/admin/push-stats")
async def get_push_stats(current_user: dict = Depends(get_current_user)):
    """Get push notification statistics - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver estatísticas de push")
    
    count = await db.push_subscriptions.count_documents({})
    return {"subscriptions_count": count, "vapid_configured": VAPID_KEYS_VALID}

@api_router.post("/push/subscribe")
async def subscribe_to_push(subscription: PushSubscription, current_user: dict = Depends(get_current_user)):
    """Save a user's push subscription"""
    subscription_doc = {
        "user_id": current_user["id"],
        "endpoint": subscription.endpoint,
        "keys": subscription.keys,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Upsert - update if exists, insert if not
    await db.push_subscriptions.update_one(
        {"user_id": current_user["id"], "endpoint": subscription.endpoint},
        {"$set": subscription_doc},
        upsert=True
    )
    
    return {"message": "Subscrição guardada com sucesso"}

@api_router.delete("/push/unsubscribe")
async def unsubscribe_from_push(subscription: PushSubscription, current_user: dict = Depends(get_current_user)):
    """Remove a user's push subscription"""
    await db.push_subscriptions.delete_one({
        "user_id": current_user["id"],
        "endpoint": subscription.endpoint
    })
    return {"message": "Subscrição removida"}

@api_router.post("/push/cleanup")
async def cleanup_invalid_push_subscriptions(current_user: dict = Depends(get_current_user)):
    """Remove all invalid/expired push subscriptions (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores")
    
    # Remove subscriptions with invalid endpoints
    result1 = await db.push_subscriptions.delete_many({
        "$or": [
            {"endpoint": {"$regex": "permanently-removed"}},
            {"endpoint": {"$regex": "invalid"}},
            {"endpoint": {"$not": {"$regex": "^https://"}}},
            {"endpoint": None},
            {"endpoint": ""}
        ]
    })
    
    # Remove subscriptions without required keys
    result2 = await db.push_subscriptions.delete_many({
        "$or": [
            {"keys": None},
            {"keys": {}},
            {"keys.p256dh": None},
            {"keys.auth": None}
        ]
    })
    
    total_removed = result1.deleted_count + result2.deleted_count
    return {"message": f"Removidas {total_removed} subscrições inválidas"}

# Web push function imported from notification_service
from services.notification_service import send_web_push_to_user

# Helper function to create and send notification
async def create_notification(user_id: str, title: str, body: str, notification_type: str = "info", ticket_id: str = None, ticket_number: str = None):
    now = datetime.now(timezone.utc)
    notification_id = str(uuid.uuid4())
    
    notification_doc = {
        "id": notification_id,
        "user_id": user_id,
        "title": title,
        "body": body,
        "type": notification_type,
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "read": False
    }
    await db.notifications.insert_one(notification_doc)
    
    # Send via WebSocket
    await manager.send_to_user(user_id, {
        "type": "notification",
        "data": notification_doc
    })
    
    # Send via Web Push (in background to not block)
    url = f"/tickets/{ticket_id}" if ticket_id else "/"
    asyncio.create_task(send_web_push_to_user(user_id, title, body, url))
    
    return notification_doc

async def notify_supervisors(title: str, body: str, notification_type: str = "info", ticket_id: str = None, ticket_number: str = None):
    # Get all supervisors and admins
    supervisors = await db.users.find(
        {"role": {"$in": [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]}},
        {"_id": 0, "id": 1}
    ).to_list(100)
    
    for sup in supervisors:
        await create_notification(sup["id"], title, body, notification_type, ticket_id, ticket_number)

# ============== ADMIN SETTINGS ==============
# Admin settings routes are in routes/admin.py
# (ticket-types, ticket-statuses, sla-config, email-config, branding, reports)

# ============== QUOTE OPTIONS ==============
# Quote routes moved to routes/quotes.py

class PublicReplyTicketData(BaseModel):
    ticket_number: str
    customer_name: str
    vehicle_plate: Optional[str] = None
    ticket_type: str
    status: str
    description: Optional[str] = None
    company_name: str = "PDPV Tickets"
    primary_color: str = "#f97316"
    logo_url: Optional[str] = None

@api_router.post("/tickets/{ticket_id}/generate-reply-link")
async def generate_reply_link(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Generate (or return existing) public reply link for a ticket"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    token = await get_or_create_reply_token(ticket_id)
    reply_link = await db.reply_links.find_one({"token": token}, {"_id": 0})
    return {"token": token, "expires_at": reply_link["expires_at"]}

# Quote link generation, quote versioning, public quote, PDF, and branding
# endpoints have been moved to routes/quotes.py

# ============== PUBLIC REPLY ENDPOINTS ==============
@api_router.get("/public/reply/{token}", response_model=PublicReplyTicketData)
async def get_public_reply(token: str):
    """Get ticket info for public reply page - NO AUTH REQUIRED"""
    reply_link = await db.reply_links.find_one({"token": token}, {"_id": 0})
    if not reply_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    ticket = await db.tickets.find_one({"id": reply_link["ticket_id"]}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    branding = await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
    return PublicReplyTicketData(
        ticket_number=ticket["ticket_number"],
        customer_name=ticket["customer_name"],
        vehicle_plate=ticket.get("vehicle_plate"),
        ticket_type=ticket.get("type", ""),
        status=ticket.get("status", ""),
        description=ticket.get("description"),
        company_name=branding.get("company_name", "PDPV Tickets"),
        primary_color=branding.get("primary_color", "#f97316"),
        logo_url=branding.get("logo_url")
    )

@api_router.post("/public/reply/{token}/submit")
async def submit_public_reply(
    token: str,
    body: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    """Customer submits a reply with optional file uploads - NO AUTH REQUIRED"""
    reply_link = await db.reply_links.find_one({"token": token}, {"_id": 0})
    if not reply_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")

    ticket_id = reply_link["ticket_id"]
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")

    now = datetime.now(timezone.utc)

    # Save uploaded files as attachments
    attachment_ids = []
    for file in (files or []):
        if file and file.filename:
            attachment_id = str(uuid.uuid4())
            file_ext = Path(file.filename).suffix
            stored_filename = f"{attachment_id}{file_ext}"
            file_path = UPLOAD_DIR / stored_filename
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            attachment_doc = {
                "id": attachment_id,
                "ticket_id": ticket_id,
                "filename": stored_filename,
                "original_filename": file.filename,
                "file_type": file.content_type or "application/octet-stream",
                "file_size": len(content),
                "uploaded_at": now.isoformat(),
                "uploaded_by_user_id": None,
                "from_customer": True
            }
            await db.attachments.insert_one(attachment_doc)
            attachment_ids.append(attachment_id)

    # Create inbound message from customer
    message_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "direction": MessageDirection.INBOUND.value,
        "channel": MessageChannel.EMAIL.value,
        "body": body,
        "from_text": ticket.get("customer_name"),
        "to_text": None,
        "created_by_user_id": None,
        "from_customer": True,
        "attachment_ids": attachment_ids
    }
    await db.messages.insert_one(message_doc)

    # Update ticket: if AGUARDA_CLIENTE → EM_TRATAMENTO
    update_doc = {"updated_at": now.isoformat(), "last_public_message_at": now.isoformat()}
    if ticket.get("status") == TicketStatus.AGUARDA_CLIENTE.value:
        update_doc["status"] = TicketStatus.EM_TRATAMENTO.value
    await db.tickets.update_one({"id": ticket_id}, {"$set": update_doc})

    # Notify assigned agent + supervisors/admins
    notification_title = f"Resposta do cliente - {ticket['ticket_number']}"
    notification_body = f"O cliente {ticket['customer_name']} respondeu ao ticket {ticket['ticket_number']}"
    if files:
        notification_body += f" ({len(attachment_ids)} ficheiro(s) enviado(s))"
    try:
        # Notify the assigned agent directly
        if ticket.get("assigned_to_user_id"):
            await create_notification(
                ticket["assigned_to_user_id"],
                notification_title,
                notification_body,
                "info",
                ticket_id=ticket_id,
                ticket_number=ticket["ticket_number"]
            )
        # Notify supervisors/admins
        await notify_supervisors(
            notification_title,
            notification_body,
            "info",
            ticket_id=ticket_id,
            ticket_number=ticket["ticket_number"]
        )
    except Exception as e:
        logger.warning(f"Notification error on public reply: {e}")

    return {"status": "success", "message": "Resposta enviada com sucesso", "attachment_count": len(attachment_ids)}

# ============== SLA BACKGROUND JOB ==============
async def run_sla_check():
    """Background task to check and mark overdue tickets"""
    while True:
        try:
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            
            # Find tickets that are overdue (SLA due passed, no first response, not closed, not archived)
            overdue_tickets = await db.tickets.find({
                "archived_at": None,
                "status": {"$ne": TicketStatus.FECHADO.value},
                "first_response_done": False,
                "sla_due": {"$lt": now_iso, "$ne": None}
            }, {"_id": 0, "id": 1, "ticket_number": 1, "assigned_to_user_id": 1}).to_list(1000)
            
            if overdue_tickets:
                logger.info(f"[SLA CHECK] Found {len(overdue_tickets)} overdue tickets")
                
                # Notify assigned users or supervisors about overdue tickets
                for ticket in overdue_tickets:
                    if ticket.get("assigned_to_user_id"):
                        # Notify assigned user
                        await create_notification(
                            user_id=ticket["assigned_to_user_id"],
                            title="Ticket em Atraso SLA",
                            body=f"O ticket {ticket['ticket_number']} está em atraso no SLA",
                            notification_type="warning",
                            ticket_id=ticket["id"],
                            ticket_number=ticket["ticket_number"]
                        )
                    else:
                        # Notify supervisors if no one assigned
                        await notify_supervisors(
                            title="Ticket em Atraso SLA",
                            body=f"O ticket {ticket['ticket_number']} está em atraso e não tem responsável",
                            notification_type="warning",
                            ticket_id=ticket["id"],
                            ticket_number=ticket["ticket_number"]
                        )
            
        except Exception as e:
            logger.error(f"[SLA CHECK] Error: {str(e)}")
        
        # Wait 15 minutes before next check
        await asyncio.sleep(15 * 60)

# Include the routers
# Include all modular routers under /api prefix
api_router.include_router(auth_router)
api_router.include_router(customers_router)
api_router.include_router(users_router)
api_router.include_router(vehicles_router)
api_router.include_router(tickets_router)
api_router.include_router(admin_router)
api_router.include_router(quotes_router)
api_router.include_router(norm_config_router)

# Load optional modules (intake, telegram, whatsapp, etc.)
# Modules are only loaded if enabled in config/modules.json
try:
    from modules import register_modules
    enabled_modules = register_modules(api_router)
    if enabled_modules:
        logging.info(f"[MODULES] Enabled modules: {enabled_modules}")
except Exception as e:
    logging.warning(f"[MODULES] Failed to load modules: {e}")

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate VAPID keys now that logger is available
def validate_vapid_keys():
    global VAPID_KEYS_VALID
    
    # Check if web push is explicitly disabled
    if os.environ.get('DISABLE_WEB_PUSH', 'false').lower() == 'true':
        logger.info("[VAPID] Web Push explicitly disabled via DISABLE_WEB_PUSH env var")
        VAPID_KEYS_VALID = False
        return
    
    if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY:
        try:
            from py_vapid import Vapid
            # Try to validate the key format
            Vapid.from_string(private_key=VAPID_PRIVATE_KEY)
            VAPID_KEYS_VALID = True
            logger.info("[VAPID] Keys validated successfully - Web Push enabled")
        except ValueError as e:
            logger.warning(f"[VAPID] Invalid key format (ValueError), Web Push disabled: {e}")
            VAPID_KEYS_VALID = False
        except Exception as e:
            logger.warning(f"[VAPID] Key validation failed, Web Push disabled: {e}")
            VAPID_KEYS_VALID = False
    else:
        logger.info("[VAPID] Keys not configured - Web Push disabled")
        VAPID_KEYS_VALID = False

validate_vapid_keys()

# Sync VAPID state to notification_service module
from services.notification_service import set_vapid_keys_valid as ns_set_valid, set_vapid_keys as ns_set_keys

def sync_vapid_to_notification_service():
    """Sync VAPID keys and validity to notification_service module."""
    ns_set_valid(VAPID_KEYS_VALID)
    if VAPID_KEYS_VALID:
        ns_set_keys(VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY)

sync_vapid_to_notification_service()

# ============== VAPID DB FALLBACK + AUTO-GENERATE ==============
async def generate_and_store_vapid_keys() -> dict:
    """Generate new VAPID keys and persist in DB."""
    from py_vapid import Vapid
    import base64
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption
    )
    v = Vapid()
    v.generate_keys()
    priv_der = v.private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    priv_key = base64.urlsafe_b64encode(priv_der).rstrip(b'=').decode()
    pub_raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    pub_key = base64.urlsafe_b64encode(pub_raw).rstrip(b'=').decode()
    await db.settings.update_one(
        {"type": "webpush_config"},
        {"$set": {
            "type": "webpush_config",
            "vapid_public_key": pub_key,
            "vapid_private_key": priv_key,
            "vapid_claims_email": VAPID_CLAIMS_EMAIL or "admin@pdpv.pt",
            "generated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    return {"vapid_public_key": pub_key, "vapid_private_key": priv_key}


async def load_and_validate_vapid_keys():
    """Called on startup: env vars → DB → auto-generate. Sets globals."""
    global VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_KEYS_VALID
    if os.environ.get('DISABLE_WEB_PUSH', 'false').lower() == 'true':
        return
    if VAPID_KEYS_VALID:
        logger.info("[VAPID] Env var keys already valid, skipping DB check")
        return
    # Try DB
    try:
        config = await db.settings.find_one({"type": "webpush_config"}, {"_id": 0})
        if config and config.get("vapid_private_key") and config.get("vapid_public_key"):
            from py_vapid import Vapid
            Vapid.from_string(private_key=config["vapid_private_key"])
            VAPID_PUBLIC_KEY = config["vapid_public_key"]
            VAPID_PRIVATE_KEY = config["vapid_private_key"]
            VAPID_KEYS_VALID = True
            logger.info("[VAPID] Loaded keys from DB - Web Push enabled")
            sync_vapid_to_notification_service()
            return
    except Exception as e:
        logger.warning(f"[VAPID] DB key load failed: {e}")
    # Auto-generate
    try:
        keys = await generate_and_store_vapid_keys()
        from py_vapid import Vapid
        Vapid.from_string(private_key=keys["vapid_private_key"])
        VAPID_PUBLIC_KEY = keys["vapid_public_key"]
        VAPID_PRIVATE_KEY = keys["vapid_private_key"]
        VAPID_KEYS_VALID = True
        logger.info("[VAPID] Auto-generated new VAPID keys - Web Push enabled")
        sync_vapid_to_notification_service()
    except Exception as e:
        logger.error(f"[VAPID] Auto-generate failed: {e}")
        VAPID_KEYS_VALID = False


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        # Validate token
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        
        if not user_id:
            await websocket.close(code=4001)
            return
        
        await manager.connect(websocket, user_id, role)
        
        try:
            while True:
                # Keep connection alive, receive any messages (ping/pong)
                data = await websocket.receive_text()
                # Echo back for ping
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(user_id)
    except jwt.PyJWTError:
        await websocket.close(code=4001)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup"""
    # Initialize object storage
    storage_key = init_storage()
    if storage_key:
        logger.info("[STARTUP] Object storage initialized successfully")
    else:
        logger.warning("[STARTUP] Object storage not available - using local storage only")
    
    # Load SLA configuration from database
    await load_sla_config_from_db()
    logger.info("[STARTUP] SLA configuration loaded from database")
    
    # Load holidays from database
    await load_holidays_from_db()
    logger.info("[STARTUP] Holidays loaded from database")
    
    # Create TTL index for login attempts cleanup (30 days)
    try:
        await db.auth_login_attempts.create_index(
            "updated_at",
            expireAfterSeconds=30 * 24 * 60 * 60  # 30 days
        )
        logger.info("[STARTUP] TTL index created for auth_login_attempts (30 days)")
    except Exception as e:
        logger.warning(f"[STARTUP] TTL index may already exist: {e}")
    
    # Start SLA check background task
    asyncio.create_task(run_sla_check())
    logger.info("[STARTUP] SLA background check started (runs every 15 minutes)")
    # Load/validate VAPID keys (DB fallback + auto-generate if missing)
    await load_and_validate_vapid_keys()
    logger.info(f"[STARTUP] Web Push status: {'enabled' if VAPID_KEYS_VALID else 'disabled'}")
