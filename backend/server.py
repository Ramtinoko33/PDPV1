from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Header, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
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

# File storage
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Frontend URL for email links
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

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

# ============== HELPERS ==============
def generate_ticket_number():
    now = datetime.now(timezone.utc)
    return f"TK{now.strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"

# ============== SLA BUSINESS HOURS CONFIGURATION ==============
# Business hours configuration (Portugal timezone - Europe/Lisbon)
# Default values - can be overridden by database config
BUSINESS_HOURS = {
    0: (time(8, 30), time(18, 30)),   # Monday
    1: (time(8, 30), time(18, 30)),   # Tuesday
    2: (time(8, 30), time(18, 30)),   # Wednesday
    3: (time(8, 30), time(18, 30)),   # Thursday
    4: (time(8, 30), time(18, 30)),   # Friday
    5: (time(8, 30), time(13, 0)),    # Saturday
    6: None,                           # Sunday (closed)
}

# SLA targets in business minutes per ticket type - default values
SLA_TARGETS_MINUTES = {
    "ORCAMENTO_PNEUS": 480,      # 8 hours = 480 minutes
    "ORCAMENTO_MECANICA": 480,   # 8 hours = 480 minutes
    "INFORMACAO": 120,           # 2 hours = 120 minutes
    "RECLAMACAO": 120,           # 2 hours = 120 minutes
    "MARCACAO": 180,             # 3 hours = 180 minutes
    "INTERNO": 480,              # 8 hours (default for internal)
}

# SLA options - default values
SLA_DEFAULT_MINUTES = 120  # 2 hours fallback
SLA_USE_BUSINESS_HOURS = True
SLA_PAUSE_ON_AGUARDA_CLIENTE = True

# Holidays list (empty for now, to be configured later)
HOLIDAYS: list[date] = []

def parse_time_string(time_str: str) -> time:
    """Parse a time string like '08:30' into a time object."""
    try:
        parts = time_str.split(':')
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return time(8, 30)  # Default fallback

async def load_sla_config_from_db():
    """Load SLA configuration from database and update global variables."""
    global BUSINESS_HOURS, SLA_TARGETS_MINUTES, SLA_DEFAULT_MINUTES, SLA_USE_BUSINESS_HOURS, SLA_PAUSE_ON_AGUARDA_CLIENTE
    
    try:
        config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
        if not config:
            return  # Use defaults
        
        # Update business hours
        day_mapping = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        for day_name, day_num in day_mapping.items():
            day_config = config.get(day_name)
            if day_config:
                if day_config.get('closed', False):
                    BUSINESS_HOURS[day_num] = None
                else:
                    start = parse_time_string(day_config.get('start', '08:30'))
                    end = parse_time_string(day_config.get('end', '18:30'))
                    BUSINESS_HOURS[day_num] = (start, end)
        
        # Update SLA targets (convert hours to minutes)
        if 'sla_orcamento_mecanica' in config:
            SLA_TARGETS_MINUTES['ORCAMENTO_MECANICA'] = config['sla_orcamento_mecanica'] * 60
        if 'sla_orcamento_pneus' in config:
            SLA_TARGETS_MINUTES['ORCAMENTO_PNEUS'] = config['sla_orcamento_pneus'] * 60
        if 'sla_informacao' in config:
            SLA_TARGETS_MINUTES['INFORMACAO'] = config['sla_informacao'] * 60
        if 'sla_reclamacao' in config:
            SLA_TARGETS_MINUTES['RECLAMACAO'] = config['sla_reclamacao'] * 60
        if 'sla_marcacao' in config:
            SLA_TARGETS_MINUTES['MARCACAO'] = config['sla_marcacao'] * 60
        if 'sla_interno' in config:
            SLA_TARGETS_MINUTES['INTERNO'] = config['sla_interno'] * 60
        if 'sla_default' in config:
            SLA_DEFAULT_MINUTES = config['sla_default'] * 60
        
        # Update options
        if 'use_business_hours' in config:
            SLA_USE_BUSINESS_HOURS = config['use_business_hours']
        if 'pause_on_aguarda_cliente' in config:
            SLA_PAUSE_ON_AGUARDA_CLIENTE = config['pause_on_aguarda_cliente']
            
        logger.info(f"SLA config loaded from database: business_hours={SLA_USE_BUSINESS_HOURS}, pause_aguarda={SLA_PAUSE_ON_AGUARDA_CLIENTE}")
    except Exception as e:
        logger.error(f"Error loading SLA config: {e}")

def is_business_day(d: date) -> bool:
    """Check if a date is a business day (not weekend, not holiday)."""
    if d in HOLIDAYS:
        return False
    weekday = d.weekday()
    return BUSINESS_HOURS.get(weekday) is not None

def get_business_hours_for_day(d: date) -> Tuple[time, time] | None:
    """Get business hours (start, end) for a given date. Returns None if closed."""
    if d in HOLIDAYS:
        return None
    return BUSINESS_HOURS.get(d.weekday())

def get_business_minutes_in_day(d: date, start_time: time = None, end_time: time = None) -> int:
    """
    Calculate business minutes available in a day.
    If start_time is provided, start counting from that time.
    If end_time is provided, stop counting at that time.
    """
    hours = get_business_hours_for_day(d)
    if not hours:
        return 0
    
    biz_start, biz_end = hours
    
    # Effective start is max of business start and provided start
    effective_start = biz_start
    if start_time:
        effective_start = max(biz_start, start_time)
    
    # Effective end is min of business end and provided end
    effective_end = biz_end
    if end_time:
        effective_end = min(biz_end, end_time)
    
    # If effective start >= effective end, no business time available
    if effective_start >= effective_end:
        return 0
    
    # Calculate minutes
    start_minutes = effective_start.hour * 60 + effective_start.minute
    end_minutes = effective_end.hour * 60 + effective_end.minute
    
    return end_minutes - start_minutes

def add_business_minutes(start_dt: datetime, minutes_to_add: int) -> datetime:
    """
    Add business minutes to a datetime and return the resulting datetime.
    If start_dt is outside business hours, it advances to the next business period.
    """
    if minutes_to_add <= 0:
        return start_dt
    
    current_dt = start_dt
    remaining_minutes = minutes_to_add
    
    # Maximum iterations to prevent infinite loop (e.g., 365 days)
    max_iterations = 365
    iterations = 0
    
    while remaining_minutes > 0 and iterations < max_iterations:
        iterations += 1
        current_date = current_dt.date()
        current_time = current_dt.time()
        
        hours = get_business_hours_for_day(current_date)
        
        if not hours:
            # Not a business day, move to next day at midnight
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        biz_start, biz_end = hours
        
        # If current time is before business start, move to business start
        if current_time < biz_start:
            current_dt = datetime.combine(current_date, biz_start, tzinfo=current_dt.tzinfo)
            current_time = biz_start
        
        # If current time is after business end, move to next day
        if current_time >= biz_end:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        # Calculate available minutes until end of business day
        current_minutes = current_time.hour * 60 + current_time.minute
        end_minutes = biz_end.hour * 60 + biz_end.minute
        available_minutes = end_minutes - current_minutes
        
        if remaining_minutes <= available_minutes:
            # Can finish within this day
            final_minutes = current_minutes + remaining_minutes
            final_hour = final_minutes // 60
            final_minute = final_minutes % 60
            return datetime.combine(current_date, time(final_hour, final_minute), tzinfo=current_dt.tzinfo)
        else:
            # Use all available minutes and move to next day
            remaining_minutes -= available_minutes
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
    
    # Fallback if max iterations reached
    return current_dt

def calculate_business_minutes_between(start_dt: datetime, end_dt: datetime) -> int:
    """
    Calculate the number of business minutes between two datetimes.
    Used to calculate elapsed SLA time.
    """
    if end_dt <= start_dt:
        return 0
    
    total_minutes = 0
    current_dt = start_dt
    
    # Maximum iterations to prevent infinite loop
    max_iterations = 365
    iterations = 0
    
    while current_dt < end_dt and iterations < max_iterations:
        iterations += 1
        current_date = current_dt.date()
        current_time = current_dt.time()
        
        hours = get_business_hours_for_day(current_date)
        
        if not hours:
            # Not a business day, move to next day
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        biz_start, biz_end = hours
        
        # If current time is before business start, move to business start
        if current_time < biz_start:
            current_dt = datetime.combine(current_date, biz_start, tzinfo=current_dt.tzinfo)
            current_time = biz_start
        
        # If current time is after business end, move to next day
        if current_time >= biz_end:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        # Determine how far we can go today
        if end_dt.date() == current_date:
            # End is on the same day
            end_time_today = min(end_dt.time(), biz_end)
        else:
            # End is on a future day, count until business end
            end_time_today = biz_end
        
        # If end_time_today is before current time (shouldn't happen normally), skip
        if end_time_today <= current_time:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        # Calculate minutes in this segment
        current_minutes = current_time.hour * 60 + current_time.minute
        end_minutes_today = end_time_today.hour * 60 + end_time_today.minute
        segment_minutes = end_minutes_today - current_minutes
        total_minutes += segment_minutes
        
        # Move to end of this segment
        if end_dt.date() == current_date and end_dt.time() <= biz_end:
            # We've reached the end
            break
        else:
            # Move to next day
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
    
    return total_minutes

def compute_sla_due(ticket_type: str = "INFORMACAO", created_at: datetime = None) -> Tuple[datetime, int, str]:
    """
    Returns (SLA due datetime, target_minutes, policy_key) based on ticket type and business hours.
    If created_at is outside business hours, SLA starts at next business period.
    Uses SLA_DEFAULT_MINUTES as fallback if ticket type not found.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    
    # Get target minutes from config, use global default as fallback
    target_minutes = SLA_TARGETS_MINUTES.get(ticket_type, SLA_DEFAULT_MINUTES)
    policy_key = f"SLA_{ticket_type}_{target_minutes}min"
    
    # Check if business hours mode is enabled
    if SLA_USE_BUSINESS_HOURS:
        sla_due = add_business_minutes(created_at, target_minutes)
    else:
        # Simple calculation - just add minutes directly
        sla_due = created_at + timedelta(minutes=target_minutes)
    
    return sla_due, target_minutes, policy_key

def compute_sla_due_simple() -> datetime:
    """Legacy function for backwards compatibility - returns 2 hours from now (simple calculation)."""
    now = datetime.now(timezone.utc)
    return now + timedelta(hours=2)

# Token functions (create_access_token, create_refresh_token) are imported from core.security
# Auth dependency (get_current_user) is imported from core.security

def check_ticket_overdue(ticket: dict) -> bool:
    """
    Check if ticket is overdue based on SLA due date and first response status.
    Takes into account:
    - Ticket status (closed tickets are never overdue)
    - First response done flag
    - SLA breached flag (if already marked as breached)
    - SLA pause state
    """
    now = datetime.now(timezone.utc)
    
    # Closed tickets are never considered overdue
    if ticket.get("status") == TicketStatus.FECHADO.value:
        return False
    
    # If SLA already breached, return True
    if ticket.get("sla_breached"):
        return True
    
    # If first response already done, not overdue
    if ticket.get("first_response_done"):
        return False
    
    # If SLA is currently paused, not overdue (clock is stopped)
    if ticket.get("sla_paused_at"):
        return False
    
    # Check if current time exceeds SLA due
    if ticket.get("sla_due"):
        try:
            sla_due = datetime.fromisoformat(ticket["sla_due"].replace("Z", "+00:00"))
            if now > sla_due:
                return True
        except (ValueError, TypeError):
            pass
    
    return False

def calculate_sla_elapsed_minutes(ticket: dict) -> int:
    """
    Calculate total elapsed business minutes for SLA tracking.
    Takes into account pause periods.
    """
    created_at_str = ticket.get("sla_started_at") or ticket.get("created_at")
    if not created_at_str:
        return 0
    
    try:
        sla_start = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 0
    
    # Get paused time accumulated
    paused_minutes = ticket.get("sla_paused_minutes", 0)
    
    # If currently paused, calculate only up to pause start
    if ticket.get("sla_paused_at"):
        try:
            pause_start = datetime.fromisoformat(ticket["sla_paused_at"].replace("Z", "+00:00"))
            elapsed = calculate_business_minutes_between(sla_start, pause_start)
            return elapsed - paused_minutes
        except (ValueError, TypeError):
            pass
    
    # Calculate elapsed from start to now
    now = datetime.now(timezone.utc)
    elapsed = calculate_business_minutes_between(sla_start, now)
    
    return max(0, elapsed - paused_minutes)

async def log_status_change(ticket_id: str, old_status: Optional[str], new_status: str, user_id: str):
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

# ============== AUTH ROUTES ==============
# Auth routes (register, login, refresh, logout, /me) are in routes/auth.py

# ============== CUSTOMER/USER/VEHICLE ROUTES ==============
# Customer routes are in routes/customers.py
# User management routes are in routes/users.py
# Vehicle routes are in routes/vehicles.py

# ============== TICKET ROUTES ==============
@api_router.post("/tickets", response_model=TicketResponse)
async def create_ticket(ticket_data: TicketCreate, current_user: dict = Depends(get_current_user)):
    from services.customer_service import find_or_create_customer_vehicle
    
    user = current_user
    
    # INTERNAL_CREATOR can only create INTERNO tickets
    if user["role"] == UserRole.INTERNAL_CREATOR.value and ticket_data.type != TicketType.INTERNO:
        raise HTTPException(status_code=403, detail="Apenas pode criar tickets internos")
    
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
        "quote_locked_at": None,
        "quote_decided_at": None,
        "quote_decision": None,
        "created_by_user_id": user["id"],
        "created_by_name": user.get("name", user.get("email", "Sistema")),  # NEW: Store creator name
        "customer_id": customer_id,  # Link to auto-created customer
        "vehicle_id": vehicle_id,    # Link to auto-created vehicle
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

@api_router.get("/tickets", response_model=List[TicketResponse])
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
        # Agents can see: their assigned tickets OR unassigned tickets (to self-assign)
        query["$or"] = [
            {"assigned_to_user_id": user["id"]},
            {"assigned_to_user_id": None},
            {"assigned_to_user_id": {"$exists": False}}
        ]
    elif user["role"] == UserRole.INTERNAL_CREATOR.value:
        # Internal creators cannot browse tickets
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
        
        result.append(TicketResponse(**t))
    
    return result

# ============== ARCHIVE SYSTEM - GET (must come before /tickets/{ticket_id}) ==============
@api_router.get("/tickets/archived", response_model=List[TicketResponse])
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
        result.append(TicketResponse(**t))
    
    return result

@api_router.get("/tickets/{ticket_id}", response_model=TicketResponse)
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
            creator_can_view = time_since_creation.total_seconds() <= 300  # 5 minutes
        except:
            creator_can_view = False
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value:
        # Agents can see: their assigned tickets OR unassigned tickets (to self-assign) OR tickets they created (within 5 min)
        is_assigned_to_agent = ticket.get("assigned_to_user_id") == user["id"]
        is_unassigned = ticket.get("assigned_to_user_id") is None
        if not is_assigned_to_agent and not is_unassigned and not creator_can_view:
            raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        # Internal creators can only see tickets they created (within 5 min window)
        if not creator_can_view:
            raise HTTPException(status_code=403, detail="Só pode ver tickets que criou nos primeiros 5 minutos")
    
    # Get assigned user name
    if ticket.get("assigned_to_user_id"):
        assigned_user = await db.users.find_one({"id": ticket["assigned_to_user_id"]}, {"_id": 0, "name": 1})
        ticket["assigned_to_name"] = assigned_user["name"] if assigned_user else None
    
    # Add edit window info for frontend
    ticket["creator_can_edit"] = creator_can_view and is_creator
    
    ticket["is_overdue"] = check_ticket_overdue(ticket)
    return TicketResponse(**ticket)

@api_router.put("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: str, ticket_data: TicketUpdate, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check if ticket is archived
    if ticket.get("archived_at"):
        raise HTTPException(status_code=400, detail="Não é possível editar um ticket arquivado")
    
    # Check if creator can edit (within 5 minutes of creation)
    is_creator = ticket.get("created_by_user_id") == user["id"]
    creator_can_edit = False
    if is_creator:
        try:
            created_at = datetime.fromisoformat(ticket["created_at"].replace("Z", "+00:00"))
            time_since_creation = datetime.now(timezone.utc) - created_at
            creator_can_edit = time_since_creation.total_seconds() <= 300  # 5 minutes = 300 seconds
        except:
            creator_can_edit = False
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value:
        if ticket.get("assigned_to_user_id") != user["id"]:
            # Agent can only self-assign if ticket is unassigned
            if ticket.get("assigned_to_user_id") is None and ticket_data.assigned_to_user_id == user["id"]:
                pass  # Allow self-assignment
            # Creator can edit within 5 minutes
            elif creator_can_edit:
                pass  # Allow creator to edit
            else:
                raise HTTPException(status_code=403, detail="Sem permissão para editar este ticket")
        # Agents can only assign tickets to themselves, not to others
        if ticket_data.assigned_to_user_id is not None and ticket_data.assigned_to_user_id != user["id"] and ticket_data.assigned_to_user_id != "":
            raise HTTPException(status_code=403, detail="Agentes só podem atribuir tickets a si próprios")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        # Internal creators can only edit tickets they created within 5 minutes
        if not creator_can_edit:
            raise HTTPException(status_code=403, detail="Só pode editar tickets que criou nos primeiros 5 minutos")
    
    update_doc = {"updated_at": datetime.now(timezone.utc).isoformat()}
    old_status = ticket.get("status")
    old_assigned = ticket.get("assigned_to_user_id")
    
    if ticket_data.status is not None:
        # Validate status exists in database
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
        
        # ============== SLA PAUSE/RESUME LOGIC ==============
        now = datetime.now(timezone.utc)
        new_status = ticket_data.status
        
        # Check if SLA pause on AGUARDA_CLIENTE is enabled
        if SLA_PAUSE_ON_AGUARDA_CLIENTE:
            # Define statuses that pause SLA (clock stops when waiting for customer)
            sla_pause_statuses = [TicketStatus.AGUARDA_CLIENTE.value]
            # Define statuses that resume SLA (clock restarts when back in treatment)
            sla_resume_statuses = [
                TicketStatus.EM_TRATAMENTO.value,
                TicketStatus.ACEITE_LINK.value,
                TicketStatus.ABERTO.value,
            ]
            # Define final statuses (SLA tracking ends)
            sla_final_statuses = [
                TicketStatus.FECHADO.value,
                TicketStatus.REJEITADO_LINK.value,
                TicketStatus.AGENDADO.value,
            ]
            
            # Check if we need to PAUSE SLA
            if new_status in sla_pause_statuses and old_status not in sla_pause_statuses:
                # Only pause if not already paused and SLA not completed
                if not ticket.get("sla_paused_at") and not ticket.get("first_response_done"):
                    sla_pause_update = {
                        "sla_paused_at": now.isoformat()
                    }
                    await db.tickets.update_one({"id": ticket_id}, {"$set": sla_pause_update})
                    
                    # Add system note about SLA pause
                    pause_note = {
                        "id": str(uuid.uuid4()),
                        "ticket_id": ticket_id,
                        "created_at": now.isoformat(),
                        "created_by_user_id": user["id"],
                        "body": "⏸️ SLA pausado - aguarda resposta do cliente",
                        "is_system": True
                    }
                    await db.notes.insert_one(pause_note)
            
            # Check if we need to RESUME SLA
            elif new_status in sla_resume_statuses and old_status in sla_pause_statuses:
                # Resume SLA if it was paused
                if ticket.get("sla_paused_at") and not ticket.get("first_response_done"):
                    try:
                        pause_start = datetime.fromisoformat(ticket["sla_paused_at"].replace("Z", "+00:00"))
                        # Calculate business minutes during pause period
                        paused_business_minutes = calculate_business_minutes_between(pause_start, now)
                        
                        # Accumulate paused minutes and clear pause timestamp
                        current_paused_minutes = ticket.get("sla_paused_minutes", 0)
                        new_paused_total = current_paused_minutes + paused_business_minutes
                        
                        # Recalculate SLA due by extending it by the paused time
                        old_sla_due_str = ticket.get("sla_due")
                        if old_sla_due_str:
                            old_sla_due = datetime.fromisoformat(old_sla_due_str.replace("Z", "+00:00"))
                            # Add the paused business minutes to the SLA due
                            new_sla_due = add_business_minutes(old_sla_due, paused_business_minutes)
                        else:
                            # Fallback: recalculate from now
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
                        
                        # Add system note about SLA resume
                        resume_note = {
                            "id": str(uuid.uuid4()),
                            "ticket_id": ticket_id,
                            "created_at": now.isoformat(),
                            "created_by_user_id": user["id"],
                            "body": f"▶️ SLA retomado - pausa de {paused_business_minutes} minutos úteis",
                            "is_system": True
                        }
                        await db.notes.insert_one(resume_note)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error resuming SLA for ticket {ticket_id}: {e}")
            
            # Check if SLA tracking should stop (final status)
            if new_status in sla_final_statuses:
                # Clear any active pause state
                if ticket.get("sla_paused_at"):
                    await db.tickets.update_one({"id": ticket_id}, {"$set": {"sla_paused_at": None}})
        # ============== END SLA PAUSE/RESUME LOGIC ==============
    
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
@api_router.post("/tickets/{ticket_id}/archive")
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
    
    # Log the archive action in notes
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

@api_router.post("/tickets/{ticket_id}/restore")
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
    
    # Log the restore action in notes
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

@api_router.get("/tickets/{ticket_id}/status-history", response_model=List[TicketStatusHistoryResponse])
async def get_ticket_status_history(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Get status change history for a ticket"""
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão para ver tickets")
    
    history = await db.ticket_status_history.find(
        {"ticket_id": ticket_id}, 
        {"_id": 0}
    ).sort("changed_at", -1).to_list(1000)
    
    # Get user names
    user_ids = list(set([h.get("changed_by_user_id") for h in history if h.get("changed_by_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    for h in history:
        h["changed_by_name"] = users_map.get(h.get("changed_by_user_id"))
    
    return [TicketStatusHistoryResponse(**h) for h in history]

# ============== REPLY LINK HELPER ==============
async def get_or_create_reply_token(ticket_id: str) -> str:
    """Get existing reply token or create a new one for the ticket."""
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
                branding = await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
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
    
    alerts = await db.alerts.find({"ticket_id": ticket_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
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
    
    # Save file
    attachment_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    stored_filename = f"{attachment_id}{file_ext}"
    file_path = UPLOAD_DIR / stored_filename
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
        file_size = len(content)
    
    now = datetime.now(timezone.utc)
    attachment_doc = {
        "id": attachment_id,
        "ticket_id": ticket_id,
        "filename": stored_filename,
        "original_filename": file.filename,
        "file_type": file.content_type or "application/octet-stream",
        "file_size": file_size,
        "uploaded_at": now.isoformat(),
        "uploaded_by_user_id": user["id"]
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
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado no servidor. Os ficheiros podem ter sido perdidos após um deployment. Por favor, carregue o ficheiro novamente.")
    
    return FileResponse(
        path=str(file_path),
        filename=attachment["original_filename"],
        media_type=attachment["file_type"]
    )

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
        "password_hash": pwd_context.hash("admin123"),
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

async def send_web_push_to_user(user_id: str, title: str, body: str, url: str = None):
    """Send web push notification to all devices of a user"""
    # Check if VAPID keys are valid before attempting to send
    if not VAPID_KEYS_VALID:
        return  # Silently skip if keys not valid
    
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return
    
    try:
        subscriptions = await db.push_subscriptions.find(
            {"user_id": user_id}
        ).to_list(100)
        
        if not subscriptions:
            return
        
        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/logo192.png",
            "badge": "/logo192.png",
            "url": url or "/"
        })
        
        for sub in subscriptions:
            try:
                # Validate subscription has required fields
                if not sub.get("endpoint") or not sub.get("keys"):
                    logger.warning(f"Invalid subscription format for user {user_id}, removing")
                    await db.push_subscriptions.delete_one({"_id": sub.get("_id")})
                    continue
                
                # Skip invalid endpoints
                endpoint = sub["endpoint"]
                if "permanently-removed" in endpoint or "invalid" in endpoint or not endpoint.startswith("https://"):
                    logger.warning(f"Invalid endpoint for user {user_id}, removing subscription")
                    await db.push_subscriptions.delete_one({"endpoint": endpoint})
                    continue
                    
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": sub["keys"]
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"}
                )
                logger.info(f"Web push sent to user {user_id}")
            except WebPushException as e:
                # If subscription is expired/invalid (400, 404, 410), remove it silently
                if e.response and e.response.status_code in [400, 404, 410]:
                    await db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                    logger.debug(f"Removed expired subscription for user {user_id}")
                elif e.response is None:
                    # No response means connection failed - subscription is likely invalid
                    await db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                    logger.debug(f"Removed unreachable subscription for user {user_id}")
                else:
                    logger.warning(f"Web push failed for user {user_id}: {e.response.status_code}")
            except ValueError as e:
                # VAPID key format error - log and skip silently
                logger.warning(f"VAPID key format error, web push disabled: {e}")
                return  # Exit early, no point trying other subscriptions with invalid keys
            except Exception as e:
                # Catch any other unexpected errors - remove problematic subscription
                error_str = str(e)
                if "permanently-removed" in error_str or "NameResolutionError" in error_str:
                    await db.push_subscriptions.delete_one({"endpoint": sub.get("endpoint", "")})
                    logger.debug(f"Removed invalid subscription for user {user_id}")
                else:
                    logger.warning(f"Web push error for user {user_id}: {type(e).__name__}")
                continue
    except Exception as e:
        # Catch any top-level errors to prevent task crash
        logger.error(f"Web push task error for user {user_id}: {e}")

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

# ============== ADMIN SETTINGS - TICKET TYPES ==============
class TicketTypeCreate(BaseModel):
    code: str
    label: str
    color: str = "#f97316"

class TicketTypeUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None

class TicketTypeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    label: str
    color: str
    created_at: str

@api_router.get("/admin/ticket-types", response_model=List[TicketTypeResponse])
async def list_ticket_types(current_user: dict = Depends(get_current_user)):
    """List all ticket types - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver tipos")
    
    types = await db.ticket_types.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)
    
    # If no types in DB, return defaults
    if not types:
        default_types = [
            {"id": str(uuid.uuid4()), "code": "ORCAMENTO_PNEUS", "label": "Orçamento Pneus", "color": "#f97316", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ORCAMENTO_MECANICA", "label": "Orçamento Mecânica", "color": "#3b82f6", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "MARCACAO", "label": "Marcação", "color": "#10b981", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "INFORMACAO", "label": "Informação", "color": "#8b5cf6", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "INTERNO", "label": "Interno", "color": "#6b7280", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "RECLAMACAO", "label": "Reclamação", "color": "#ef4444", "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        # Insert defaults into DB
        await db.ticket_types.insert_many(default_types)
        types = default_types
    
    return [TicketTypeResponse(**t) for t in types]

@api_router.post("/admin/ticket-types", response_model=TicketTypeResponse)
async def create_ticket_type(type_data: TicketTypeCreate, current_user: dict = Depends(get_current_user)):
    """Create a new ticket type - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar tipos")
    
    # Check if code already exists
    existing = await db.ticket_types.find_one({"code": type_data.code})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um tipo com este código")
    
    type_doc = {
        "id": str(uuid.uuid4()),
        "code": type_data.code.upper().replace(" ", "_"),
        "label": type_data.label,
        "color": type_data.color,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.ticket_types.insert_one(type_doc)
    
    return TicketTypeResponse(**type_doc)

@api_router.put("/admin/ticket-types/{type_id}", response_model=TicketTypeResponse)
async def update_ticket_type(type_id: str, type_data: TicketTypeUpdate, current_user: dict = Depends(get_current_user)):
    """Update a ticket type - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar tipos")
    
    type_doc = await db.ticket_types.find_one({"id": type_id}, {"_id": 0})
    if not type_doc:
        raise HTTPException(status_code=404, detail="Tipo não encontrado")
    
    update_doc = {}
    if type_data.label:
        update_doc["label"] = type_data.label
    if type_data.color:
        update_doc["color"] = type_data.color
    
    if update_doc:
        await db.ticket_types.update_one({"id": type_id}, {"$set": update_doc})
    
    updated = await db.ticket_types.find_one({"id": type_id}, {"_id": 0})
    return TicketTypeResponse(**updated)

@api_router.delete("/admin/ticket-types/{type_id}")
async def delete_ticket_type(type_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a ticket type - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar tipos")
    
    # Check if type is being used by any tickets
    type_doc = await db.ticket_types.find_one({"id": type_id}, {"_id": 0})
    if not type_doc:
        raise HTTPException(status_code=404, detail="Tipo não encontrado")
    
    tickets_using = await db.tickets.count_documents({"type": type_doc["code"]})
    if tickets_using > 0:
        raise HTTPException(status_code=400, detail=f"Não é possível eliminar. {tickets_using} ticket(s) usam este tipo.")
    
    await db.ticket_types.delete_one({"id": type_id})
    return {"message": "Tipo eliminado"}

# ============== ADMIN SETTINGS - TICKET STATUSES ==============
class TicketStatusCreate(BaseModel):
    code: str
    label: str
    color: str = "#3b82f6"
    is_final: bool = False
    is_auto: bool = False

class TicketStatusUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    is_final: Optional[bool] = None
    is_auto: Optional[bool] = None
    order: Optional[int] = None

class TicketStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    label: str
    color: str
    is_final: bool
    is_auto: bool = False
    order: int = 0
    created_at: str

@api_router.get("/ticket-statuses", response_model=List[TicketStatusResponse])
async def list_ticket_statuses_for_users(current_user: dict = Depends(get_current_user)):
    """List all ticket statuses for all authenticated users"""
    statuses = await db.ticket_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    
    # If no statuses in DB, return defaults
    if not statuses:
        default_statuses = [
            {"id": str(uuid.uuid4()), "code": "ABERTO", "label": "Aberto", "color": "#22c55e", "is_final": False, "is_auto": False, "order": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "EM_TRATAMENTO", "label": "Em Tratamento", "color": "#3b82f6", "is_final": False, "is_auto": False, "order": 1, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGUARDA_CLIENTE", "label": "Aguarda Cliente", "color": "#f59e0b", "is_final": False, "is_auto": False, "order": 2, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ACEITE_LINK", "label": "Aceite (Link)", "color": "#10b981", "is_final": False, "is_auto": True, "order": 3, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "REJEITADO_LINK", "label": "Rejeitado (Link)", "color": "#ef4444", "is_final": False, "is_auto": True, "order": 4, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGENDADO", "label": "Agendado", "color": "#8b5cf6", "is_final": False, "is_auto": False, "order": 5, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "FECHADO", "label": "Fechado", "color": "#6b7280", "is_final": True, "is_auto": False, "order": 6, "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        await db.ticket_statuses.insert_many(default_statuses)
        statuses = default_statuses
    
    return [TicketStatusResponse(**s) for s in statuses]

@api_router.get("/admin/ticket-statuses", response_model=List[TicketStatusResponse])
async def list_ticket_statuses(current_user: dict = Depends(get_current_user)):
    """List all ticket statuses - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver estados")
    
    statuses = await db.ticket_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    
    # If no statuses in DB, return defaults
    if not statuses:
        default_statuses = [
            {"id": str(uuid.uuid4()), "code": "ABERTO", "label": "Aberto", "color": "#22c55e", "is_final": False, "is_auto": False, "order": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "EM_TRATAMENTO", "label": "Em Tratamento", "color": "#3b82f6", "is_final": False, "is_auto": False, "order": 1, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGUARDA_CLIENTE", "label": "Aguarda Cliente", "color": "#f59e0b", "is_final": False, "is_auto": False, "order": 2, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ACEITE_LINK", "label": "Aceite (Link)", "color": "#10b981", "is_final": False, "is_auto": True, "order": 3, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "REJEITADO_LINK", "label": "Rejeitado (Link)", "color": "#ef4444", "is_final": False, "is_auto": True, "order": 4, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGENDADO", "label": "Agendado", "color": "#8b5cf6", "is_final": False, "is_auto": False, "order": 5, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "FECHADO", "label": "Fechado", "color": "#6b7280", "is_final": True, "is_auto": False, "order": 6, "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        # Insert defaults into DB
        await db.ticket_statuses.insert_many(default_statuses)
        statuses = default_statuses
    
    return [TicketStatusResponse(**s) for s in statuses]

@api_router.post("/admin/ticket-statuses", response_model=TicketStatusResponse)
async def create_ticket_status(status_data: TicketStatusCreate, current_user: dict = Depends(get_current_user)):
    """Create a new ticket status - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar estados")
    
    # Check if code already exists
    existing = await db.ticket_statuses.find_one({"code": status_data.code})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um estado com este código")
    
    # Get max order
    max_order_doc = await db.ticket_statuses.find_one({}, sort=[("order", -1)])
    max_order = max_order_doc.get("order", -1) + 1 if max_order_doc else 0
    
    status_doc = {
        "id": str(uuid.uuid4()),
        "code": status_data.code.upper().replace(" ", "_"),
        "label": status_data.label,
        "color": status_data.color,
        "is_final": status_data.is_final,
        "order": max_order,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.ticket_statuses.insert_one(status_doc)
    
    return TicketStatusResponse(**status_doc)

@api_router.put("/admin/ticket-statuses/{status_id}", response_model=TicketStatusResponse)
async def update_ticket_status(status_id: str, status_data: TicketStatusUpdate, current_user: dict = Depends(get_current_user)):
    """Update a ticket status - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar estados")
    
    status_doc = await db.ticket_statuses.find_one({"id": status_id}, {"_id": 0})
    if not status_doc:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    update_doc = {}
    if status_data.label:
        update_doc["label"] = status_data.label
    if status_data.color:
        update_doc["color"] = status_data.color
    if status_data.is_final is not None:
        update_doc["is_final"] = status_data.is_final
    if status_data.is_auto is not None:
        update_doc["is_auto"] = status_data.is_auto
    if status_data.order is not None:
        update_doc["order"] = status_data.order
    
    if update_doc:
        await db.ticket_statuses.update_one({"id": status_id}, {"$set": update_doc})
    
    updated = await db.ticket_statuses.find_one({"id": status_id}, {"_id": 0})
    return TicketStatusResponse(**updated)

@api_router.delete("/admin/ticket-statuses/{status_id}")
async def delete_ticket_status(status_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a ticket status - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar estados")
    
    # Check if status is being used by any tickets
    status_doc = await db.ticket_statuses.find_one({"id": status_id}, {"_id": 0})
    if not status_doc:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    tickets_using = await db.tickets.count_documents({"status": status_doc["code"]})
    if tickets_using > 0:
        raise HTTPException(status_code=400, detail=f"Não é possível eliminar. {tickets_using} ticket(s) usam este estado.")
    
    await db.ticket_statuses.delete_one({"id": status_id})
    return {"message": "Estado eliminado"}

# ============== ADMIN SETTINGS - SLA CONFIG ==============
class BusinessHoursConfig(BaseModel):
    """Business hours for a single day"""
    start: str = "08:30"  # HH:MM format
    end: str = "18:30"    # HH:MM format
    closed: bool = False

class SlaConfigUpdate(BaseModel):
    # Business Hours
    monday: Optional[BusinessHoursConfig] = None
    tuesday: Optional[BusinessHoursConfig] = None
    wednesday: Optional[BusinessHoursConfig] = None
    thursday: Optional[BusinessHoursConfig] = None
    friday: Optional[BusinessHoursConfig] = None
    saturday: Optional[BusinessHoursConfig] = None
    sunday: Optional[BusinessHoursConfig] = None
    
    # SLA per ticket type (in hours)
    sla_orcamento_mecanica: Optional[int] = None
    sla_orcamento_pneus: Optional[int] = None
    sla_informacao: Optional[int] = None
    sla_reclamacao: Optional[int] = None
    sla_marcacao: Optional[int] = None
    sla_interno: Optional[int] = None
    sla_default: Optional[int] = None  # fallback
    
    # Legacy fields (for backwards compatibility)
    first_response_hours: Optional[int] = None
    quote_response_hours: Optional[int] = None
    enabled: Optional[bool] = None
    
    # New toggles
    use_business_hours: Optional[bool] = None  # count only in business hours
    pause_on_aguarda_cliente: Optional[bool] = None  # pause SLA when waiting for client

class SlaConfigResponse(BaseModel):
    # Business Hours
    monday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    tuesday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    wednesday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    thursday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    friday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    saturday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="13:00", closed=False)
    sunday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="13:00", closed=True)
    
    # SLA per ticket type (in hours)
    sla_orcamento_mecanica: int = 8
    sla_orcamento_pneus: int = 8
    sla_informacao: int = 2
    sla_reclamacao: int = 2
    sla_marcacao: int = 3
    sla_interno: int = 8
    sla_default: int = 2  # fallback
    
    # Legacy fields
    first_response_hours: int = 2
    quote_response_hours: int = 24
    enabled: bool = True
    
    # New toggles
    use_business_hours: bool = True
    pause_on_aguarda_cliente: bool = True

def build_sla_config_response(config: dict) -> SlaConfigResponse:
    """Build SLA config response from database document"""
    def get_day_config(config: dict, day: str, default_start: str, default_end: str, default_closed: bool) -> BusinessHoursConfig:
        day_data = config.get(day, {})
        if isinstance(day_data, dict):
            return BusinessHoursConfig(
                start=day_data.get("start", default_start),
                end=day_data.get("end", default_end),
                closed=day_data.get("closed", default_closed)
            )
        return BusinessHoursConfig(start=default_start, end=default_end, closed=default_closed)
    
    return SlaConfigResponse(
        monday=get_day_config(config, "monday", "08:30", "18:30", False),
        tuesday=get_day_config(config, "tuesday", "08:30", "18:30", False),
        wednesday=get_day_config(config, "wednesday", "08:30", "18:30", False),
        thursday=get_day_config(config, "thursday", "08:30", "18:30", False),
        friday=get_day_config(config, "friday", "08:30", "18:30", False),
        saturday=get_day_config(config, "saturday", "08:30", "13:00", False),
        sunday=get_day_config(config, "sunday", "08:30", "13:00", True),
        sla_orcamento_mecanica=config.get("sla_orcamento_mecanica", 8),
        sla_orcamento_pneus=config.get("sla_orcamento_pneus", 8),
        sla_informacao=config.get("sla_informacao", 2),
        sla_reclamacao=config.get("sla_reclamacao", 2),
        sla_marcacao=config.get("sla_marcacao", 3),
        sla_interno=config.get("sla_interno", 8),
        sla_default=config.get("sla_default", 2),
        first_response_hours=config.get("first_response_hours", 2),
        quote_response_hours=config.get("quote_response_hours", 24),
        enabled=config.get("enabled", True),
        use_business_hours=config.get("use_business_hours", True),
        pause_on_aguarda_cliente=config.get("pause_on_aguarda_cliente", True)
    )

@api_router.get("/admin/sla-config", response_model=SlaConfigResponse)
async def get_sla_config(current_user: dict = Depends(get_current_user)):
    """Get SLA configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração SLA")
    
    config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
    if not config:
        return SlaConfigResponse()
    
    return build_sla_config_response(config)

@api_router.put("/admin/sla-config", response_model=SlaConfigResponse)
async def update_sla_config(config_data: SlaConfigUpdate, current_user: dict = Depends(get_current_user)):
    """Update SLA configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configuração SLA")
    
    existing = await db.settings.find_one({"type": "sla_config"})
    
    update_doc = {"type": "sla_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    # Business hours
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        day_config = getattr(config_data, day, None)
        if day_config is not None:
            update_doc[day] = day_config.model_dump()
    
    # SLA per type
    if config_data.sla_orcamento_mecanica is not None:
        update_doc["sla_orcamento_mecanica"] = config_data.sla_orcamento_mecanica
    if config_data.sla_orcamento_pneus is not None:
        update_doc["sla_orcamento_pneus"] = config_data.sla_orcamento_pneus
    if config_data.sla_informacao is not None:
        update_doc["sla_informacao"] = config_data.sla_informacao
    if config_data.sla_reclamacao is not None:
        update_doc["sla_reclamacao"] = config_data.sla_reclamacao
    if config_data.sla_marcacao is not None:
        update_doc["sla_marcacao"] = config_data.sla_marcacao
    if config_data.sla_interno is not None:
        update_doc["sla_interno"] = config_data.sla_interno
    if config_data.sla_default is not None:
        update_doc["sla_default"] = config_data.sla_default
    
    # Legacy fields
    if config_data.first_response_hours is not None:
        update_doc["first_response_hours"] = config_data.first_response_hours
    if config_data.quote_response_hours is not None:
        update_doc["quote_response_hours"] = config_data.quote_response_hours
    if config_data.enabled is not None:
        update_doc["enabled"] = config_data.enabled
    
    # New toggles
    if config_data.use_business_hours is not None:
        update_doc["use_business_hours"] = config_data.use_business_hours
    if config_data.pause_on_aguarda_cliente is not None:
        update_doc["pause_on_aguarda_cliente"] = config_data.pause_on_aguarda_cliente
    
    if existing:
        await db.settings.update_one({"type": "sla_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    # Reload configuration into global variables
    await load_sla_config_from_db()
    
    config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
    return build_sla_config_response(config)

# ============== ADMIN SETTINGS - EMAIL CONFIG ==============
class EmailConfigUpdate(BaseModel):
    # SMTP Settings
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_use_tls: Optional[bool] = None
    # General Settings
    email_from: Optional[str] = None
    email_from_name: Optional[str] = None
    frontend_url: Optional[str] = None
    # Legacy Resend (optional)
    resend_api_key: Optional[str] = None

class EmailConfigResponse(BaseModel):
    # SMTP Settings
    smtp_configured: bool = False
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_use_ssl: bool = False
    smtp_use_tls: bool = True
    # General Settings
    email_from: Optional[str] = None
    email_from_name: Optional[str] = None
    frontend_url: Optional[str] = None
    # Legacy
    resend_configured: bool = False

@api_router.get("/admin/email-settings", response_model=EmailConfigResponse)
async def get_email_settings(current_user: dict = Depends(get_current_user)):
    """Get email settings - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configurações de email")
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    
    if not config:
        config = {}
    
    smtp_configured = bool(config.get("smtp_host") and config.get("smtp_port") and config.get("smtp_username"))
    
    return EmailConfigResponse(
        smtp_configured=smtp_configured,
        smtp_host=config.get("smtp_host"),
        smtp_port=config.get("smtp_port"),
        smtp_username=config.get("smtp_username"),
        smtp_use_ssl=config.get("smtp_use_ssl", False),
        smtp_use_tls=config.get("smtp_use_tls", True),
        email_from=config.get("email_from") or EMAIL_FROM,
        email_from_name=config.get("email_from_name", "PDPV Tickets"),
        frontend_url=config.get("frontend_url", FRONTEND_URL),
        resend_configured=bool(RESEND_API_KEY or config.get("resend_api_key"))
    )

@api_router.put("/admin/email-settings", response_model=EmailConfigResponse)
async def update_email_settings(config_data: EmailConfigUpdate, current_user: dict = Depends(get_current_user)):
    """Update email settings - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configurações de email")
    
    existing = await db.settings.find_one({"type": "email_config"})
    
    update_doc = {"type": "email_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    # SMTP Settings
    if config_data.smtp_host is not None:
        update_doc["smtp_host"] = config_data.smtp_host
    if config_data.smtp_port is not None:
        update_doc["smtp_port"] = config_data.smtp_port
    if config_data.smtp_username is not None:
        update_doc["smtp_username"] = config_data.smtp_username
    if config_data.smtp_password is not None:
        update_doc["smtp_password"] = config_data.smtp_password
    if config_data.smtp_use_ssl is not None:
        update_doc["smtp_use_ssl"] = config_data.smtp_use_ssl
    if config_data.smtp_use_tls is not None:
        update_doc["smtp_use_tls"] = config_data.smtp_use_tls
    
    # General Settings
    if config_data.email_from is not None:
        update_doc["email_from"] = config_data.email_from
    if config_data.email_from_name is not None:
        update_doc["email_from_name"] = config_data.email_from_name
    if config_data.frontend_url is not None:
        update_doc["frontend_url"] = config_data.frontend_url
    
    # Legacy Resend
    if config_data.resend_api_key is not None:
        update_doc["resend_api_key"] = config_data.resend_api_key
    
    if existing:
        await db.settings.update_one({"type": "email_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    smtp_configured = bool(config.get("smtp_host") and config.get("smtp_port") and config.get("smtp_username"))
    
    return EmailConfigResponse(
        smtp_configured=smtp_configured,
        smtp_host=config.get("smtp_host"),
        smtp_port=config.get("smtp_port"),
        smtp_username=config.get("smtp_username"),
        smtp_use_ssl=config.get("smtp_use_ssl", False),
        smtp_use_tls=config.get("smtp_use_tls", True),
        email_from=config.get("email_from") or EMAIL_FROM,
        email_from_name=config.get("email_from_name", "PDPV Tickets"),
        frontend_url=config.get("frontend_url", FRONTEND_URL),
        resend_configured=bool(RESEND_API_KEY or config.get("resend_api_key"))
    )

# ============== ADMIN SETTINGS - BRANDING & TEMPLATES ==============
class BrandingConfig(BaseModel):
    company_name: Optional[str] = "PDPV"
    company_subtitle: Optional[str] = "Pneus de Pedro V."
    company_logo_url: Optional[str] = None
    primary_color: Optional[str] = "#f97316"
    secondary_color: Optional[str] = "#1f2937"
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_address: Optional[str] = None
    company_website: Optional[str] = None

class EmailTemplateConfig(BaseModel):
    quote_email_subject: Optional[str] = "[Ticket #{ticket_number}] Orçamento - {quote_value}€"
    quote_email_greeting: Optional[str] = "Olá {customer_name},"
    quote_email_intro: Optional[str] = "Preparámos um orçamento para si referente ao seu pedido."
    quote_email_button_text: Optional[str] = "Ver Orçamento"
    quote_email_footer: Optional[str] = "Este link é válido até {expiry_date}."
    quote_page_accepted_title: Optional[str] = "Orçamento Aceite!"
    quote_page_accepted_message: Optional[str] = "Obrigado pela sua resposta. Entraremos em contacto em breve para agendar o serviço."
    quote_page_rejected_title: Optional[str] = "Orçamento Recusado"
    quote_page_rejected_message: Optional[str] = "Obrigado pela sua resposta. Se precisar de ajuda, não hesite em contactar-nos."

class BrandingResponse(BaseModel):
    company_name: str = "PDPV"
    company_subtitle: str = "Pneus de Pedro V."
    company_logo_url: Optional[str] = None
    primary_color: str = "#f97316"
    secondary_color: str = "#1f2937"
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_address: Optional[str] = None
    company_website: Optional[str] = None
    email_templates: dict = {}

@api_router.get("/admin/branding")
async def get_branding_config(current_user: dict = Depends(get_current_user)):
    """Get branding configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração de branding")
    
    config = await db.settings.find_one({"type": "branding_config"}, {"_id": 0})
    templates = await db.settings.find_one({"type": "email_templates"}, {"_id": 0})
    
    if not config:
        config = {}
    if not templates:
        templates = {}
    
    return {
        "company_name": config.get("company_name", "PDPV"),
        "company_subtitle": config.get("company_subtitle", "Pneus de Pedro V."),
        "company_logo_url": config.get("company_logo_url"),
        "primary_color": config.get("primary_color", "#f97316"),
        "secondary_color": config.get("secondary_color", "#1f2937"),
        "company_phone": config.get("company_phone"),
        "company_email": config.get("company_email"),
        "company_address": config.get("company_address"),
        "company_website": config.get("company_website"),
        "email_templates": {
            "quote_email_subject": templates.get("quote_email_subject", "[Ticket #{ticket_number}] Orçamento - {quote_value}€"),
            "quote_email_greeting": templates.get("quote_email_greeting", "Olá {customer_name},"),
            "quote_email_intro": templates.get("quote_email_intro", "Preparámos um orçamento para si referente ao seu pedido."),
            "quote_email_button_text": templates.get("quote_email_button_text", "Ver Orçamento"),
            "quote_email_footer": templates.get("quote_email_footer", "Este link é válido até {expiry_date}."),
            "quote_page_accepted_title": templates.get("quote_page_accepted_title", "Orçamento Aceite!"),
            "quote_page_accepted_message": templates.get("quote_page_accepted_message", "Obrigado pela sua resposta. Entraremos em contacto em breve para agendar o serviço."),
            "quote_page_rejected_title": templates.get("quote_page_rejected_title", "Orçamento Recusado"),
            "quote_page_rejected_message": templates.get("quote_page_rejected_message", "Obrigado pela sua resposta. Se precisar de ajuda, não hesite em contactar-nos.")
        }
    }

@api_router.put("/admin/branding")
async def update_branding_config(config_data: BrandingConfig, current_user: dict = Depends(get_current_user)):
    """Update branding configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configuração de branding")
    
    update_doc = {"type": "branding_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    for field in ["company_name", "company_subtitle", "company_logo_url", "primary_color", 
                  "secondary_color", "company_phone", "company_email", "company_address", "company_website"]:
        value = getattr(config_data, field, None)
        if value is not None:
            update_doc[field] = value
    
    existing = await db.settings.find_one({"type": "branding_config"})
    if existing:
        await db.settings.update_one({"type": "branding_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    return await get_branding_config(current_user)

@api_router.put("/admin/email-templates")
async def update_email_templates(templates: EmailTemplateConfig, current_user: dict = Depends(get_current_user)):
    """Update email templates - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar templates de email")
    
    update_doc = {"type": "email_templates", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    for field in ["quote_email_subject", "quote_email_greeting", "quote_email_intro", 
                  "quote_email_button_text", "quote_email_footer", "quote_page_accepted_title",
                  "quote_page_accepted_message", "quote_page_rejected_title", "quote_page_rejected_message"]:
        value = getattr(templates, field, None)
        if value is not None:
            update_doc[field] = value
    
    existing = await db.settings.find_one({"type": "email_templates"})
    if existing:
        await db.settings.update_one({"type": "email_templates"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    return {"message": "Templates atualizados com sucesso"}

# Public endpoint to get branding for quote page
@api_router.get("/public/branding")
async def get_public_branding():
    """Get public branding info for quote response page"""
    config = await db.settings.find_one({"type": "branding_config"}, {"_id": 0})
    templates = await db.settings.find_one({"type": "email_templates"}, {"_id": 0})
    
    if not config:
        config = {}
    if not templates:
        templates = {}
    
    return {
        "company_name": config.get("company_name", "PDPV"),
        "company_subtitle": config.get("company_subtitle", "Pneus de Pedro V."),
        "company_logo_url": config.get("company_logo_url"),
        "primary_color": config.get("primary_color", "#f97316"),
        "secondary_color": config.get("secondary_color", "#1f2937"),
        "company_phone": config.get("company_phone"),
        "company_email": config.get("company_email"),
        "quote_page_accepted_title": templates.get("quote_page_accepted_title", "Orçamento Aceite!"),
        "quote_page_accepted_message": templates.get("quote_page_accepted_message", "Obrigado pela sua resposta. Entraremos em contacto em breve para agendar o serviço."),
        "quote_page_rejected_title": templates.get("quote_page_rejected_title", "Orçamento Recusado"),
        "quote_page_rejected_message": templates.get("quote_page_rejected_message", "Obrigado pela sua resposta. Se precisar de ajuda, não hesite em contactar-nos.")
    }

# ============== QUOTE VALUE HISTORY ==============
class QuoteHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    old_value: Optional[float] = None
    new_value: float
    changed_by_user_id: str
    changed_by_name: Optional[str] = None
    changed_at: str
    reason: Optional[str] = None

@api_router.get("/tickets/{ticket_id}/quote-history", response_model=List[QuoteHistoryResponse])
async def get_quote_history(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Get quote value change history for a ticket"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão para ver tickets")
    
    history = await db.quote_history.find(
        {"ticket_id": ticket_id}, 
        {"_id": 0}
    ).sort("changed_at", -1).to_list(1000)
    
    # Get user names
    user_ids = list(set([h.get("changed_by_user_id") for h in history if h.get("changed_by_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    for h in history:
        h["changed_by_name"] = users_map.get(h.get("changed_by_user_id"))
    
    return [QuoteHistoryResponse(**h) for h in history]

async def log_quote_change(ticket_id: str, old_value: Optional[float], new_value: float, user_id: str, reason: Optional[str] = None):
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

# ============== ADMIN REPORTS ==============
class ReportFilters(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    assigned_to: Optional[str] = None
    channel: Optional[str] = None

class TicketMetrics(BaseModel):
    total_tickets: int = 0
    tickets_by_status: Dict[str, int] = {}
    tickets_by_type: Dict[str, int] = {}
    tickets_by_channel: Dict[str, int] = {}
    avg_resolution_time_hours: Optional[float] = None
    sla_compliance_rate: float = 0.0
    tickets_overdue: int = 0
    quotes_sent: int = 0
    quotes_accepted: int = 0
    quotes_rejected: int = 0
    total_quote_value: float = 0.0

class AgentPerformance(BaseModel):
    user_id: str
    user_name: str
    tickets_assigned: int = 0
    tickets_closed: int = 0
    avg_response_time_hours: Optional[float] = None
    sla_compliance_rate: float = 0.0

class ReportResponse(BaseModel):
    period: Dict[str, Optional[str]]
    metrics: TicketMetrics
    agent_performance: List[AgentPerformance] = []
    daily_ticket_counts: List[Dict[str, Any]] = []

@api_router.post("/admin/reports", response_model=ReportResponse)
async def generate_report(filters: ReportFilters, current_user: dict = Depends(get_current_user)):
    """Generate comprehensive admin reports - ADMIN/SUPERVISOR only"""
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver relatórios")
    
    # Build query
    query = {"archived_at": None}
    
    if filters.start_date:
        query["created_at"] = {"$gte": filters.start_date}
    if filters.end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = filters.end_date
        else:
            query["created_at"] = {"$lte": filters.end_date}
    if filters.status:
        query["status"] = filters.status
    if filters.type:
        query["type"] = filters.type
    if filters.assigned_to:
        query["assigned_to_user_id"] = filters.assigned_to
    if filters.channel:
        query["channel"] = filters.channel
    
    tickets = await db.tickets.find(query, {"_id": 0}).to_list(10000)
    
    # Calculate metrics
    metrics = TicketMetrics()
    metrics.total_tickets = len(tickets)
    
    status_counts = {}
    type_counts = {}
    channel_counts = {}
    overdue_count = 0
    quotes_sent = 0
    quotes_accepted = 0
    quotes_rejected = 0
    total_quote_value = 0.0
    sla_compliant = 0
    
    for t in tickets:
        # Status counts
        status = t.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Type counts
        ticket_type = t.get("type", "UNKNOWN")
        type_counts[ticket_type] = type_counts.get(ticket_type, 0) + 1
        
        # Channel counts
        channel = t.get("channel", "UNKNOWN")
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        
        # SLA compliance
        if t.get("first_response_done"):
            sla_compliant += 1
        elif t.get("sla_due"):
            try:
                sla_due = datetime.fromisoformat(t["sla_due"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > sla_due:
                    overdue_count += 1
            except ValueError:
                pass
        
        # Quote metrics
        if t.get("quote_sent"):
            quotes_sent += 1
            if t.get("quote_value"):
                total_quote_value += t["quote_value"]
        if t.get("quote_response_status") == "ACCEPTED":
            quotes_accepted += 1
        elif t.get("quote_response_status") == "REJECTED":
            quotes_rejected += 1
    
    metrics.tickets_by_status = status_counts
    metrics.tickets_by_type = type_counts
    metrics.tickets_by_channel = channel_counts
    metrics.tickets_overdue = overdue_count
    metrics.quotes_sent = quotes_sent
    metrics.quotes_accepted = quotes_accepted
    metrics.quotes_rejected = quotes_rejected
    metrics.total_quote_value = total_quote_value
    
    if metrics.total_tickets > 0:
        metrics.sla_compliance_rate = round((sla_compliant / metrics.total_tickets) * 100, 1)
    
    # Agent performance
    agent_performance = []
    agents = await db.users.find(
        {"role": {"$in": [UserRole.AGENT.value, UserRole.SUPERVISOR.value]}},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    
    for agent in agents:
        agent_tickets = [t for t in tickets if t.get("assigned_to_user_id") == agent["id"]]
        closed_tickets = [t for t in agent_tickets if t.get("status") == "FECHADO"]
        compliant = sum(1 for t in agent_tickets if t.get("first_response_done"))
        
        perf = AgentPerformance(
            user_id=agent["id"],
            user_name=agent["name"],
            tickets_assigned=len(agent_tickets),
            tickets_closed=len(closed_tickets),
            sla_compliance_rate=round((compliant / len(agent_tickets) * 100), 1) if agent_tickets else 0
        )
        agent_performance.append(perf)
    
    # Daily ticket counts (last 30 days)
    daily_counts = []
    if not filters.start_date:
        start = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        start = datetime.fromisoformat(filters.start_date.replace("Z", "+00:00"))
    
    end = datetime.now(timezone.utc) if not filters.end_date else datetime.fromisoformat(filters.end_date.replace("Z", "+00:00"))
    
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        day_count = sum(1 for t in tickets if t.get("created_at", "").startswith(date_str))
        daily_counts.append({"date": date_str, "count": day_count})
        current += timedelta(days=1)
    
    return ReportResponse(
        period={"start": filters.start_date, "end": filters.end_date},
        metrics=metrics,
        agent_performance=agent_performance,
        daily_ticket_counts=daily_counts[-30:]  # Last 30 entries
    )

# ============== TIRE SIZE ANALYSIS ==============
class TireSizeCount(BaseModel):
    size: str
    count: int
    percentage: float

class BrandCount(BaseModel):
    brand: str
    count: int

class TireAnalysisResponse(BaseModel):
    period: dict
    total_tickets_analyzed: int
    tickets_with_sizes: int
    tire_sizes: List[TireSizeCount]
    brands: List[BrandCount]
    keywords: List[dict]

@api_router.get("/admin/reports/tire-analysis")
async def analyze_tire_sizes(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Analyze tire sizes and brands from ticket descriptions"""
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    import re
    
    # Build query
    query = {"archived_at": None}
    
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    tickets = await db.tickets.find(query, {"_id": 0, "description": 1}).to_list(10000)
    
    # Regex patterns for tire sizes
    # Matches: 205/55R16, 225/45R17, 195/65R15, 205/55 R16, 205/55/R16, etc.
    tire_pattern = re.compile(r'\b(\d{3})[/\s]?(\d{2})[/\s]?[Rr]?(\d{2})\b')
    
    # Common tire brands
    brands_list = [
        'Michelin', 'Continental', 'Hankook', 'Bridgestone', 'Pirelli',
        'Goodyear', 'Dunlop', 'Firestone', 'Yokohama', 'Kumho',
        'Nexen', 'Falken', 'Toyo', 'BFGoodrich', 'Uniroyal',
        'Vredestein', 'Nokian', 'Maxxis', 'Laufenn', 'Barum'
    ]
    
    # Service keywords
    service_keywords = [
        ('revisão', 'Revisão'),
        ('travões', 'Travões'),
        ('travoes', 'Travões'),
        ('óleo', 'Mudança de Óleo'),
        ('oleo', 'Mudança de Óleo'),
        ('alinhamento', 'Alinhamento'),
        ('balanceamento', 'Balanceamento'),
        ('suspensão', 'Suspensão'),
        ('suspensao', 'Suspensão'),
        ('amortecedores', 'Amortecedores'),
        ('embraiagem', 'Embraiagem'),
        ('distribuição', 'Correia Distribuição'),
        ('bateria', 'Bateria'),
        ('escape', 'Escape'),
        ('ar condicionado', 'Ar Condicionado'),
        ('a/c', 'Ar Condicionado'),
        ('pneu', 'Pneus'),
        ('pneus', 'Pneus'),
    ]
    
    # Count occurrences
    size_counts = {}
    brand_counts = {}
    keyword_counts = {}
    tickets_with_sizes = 0
    
    for ticket in tickets:
        desc = ticket.get("description", "") or ""
        desc_lower = desc.lower()
        
        # Find tire sizes
        sizes_found = tire_pattern.findall(desc)
        if sizes_found:
            tickets_with_sizes += 1
            for match in sizes_found:
                # Normalize format: 205/55R16
                size = f"{match[0]}/{match[1]}R{match[2]}"
                size_counts[size] = size_counts.get(size, 0) + 1
        
        # Find brands (case insensitive)
        for brand in brands_list:
            if brand.lower() in desc_lower:
                brand_counts[brand] = brand_counts.get(brand, 0) + 1
        
        # Find service keywords
        for keyword, label in service_keywords:
            if keyword in desc_lower:
                keyword_counts[label] = keyword_counts.get(label, 0) + 1
    
    # Sort and format results
    total_sizes = sum(size_counts.values()) or 1
    sorted_sizes = sorted(size_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    tire_sizes = [
        TireSizeCount(
            size=size,
            count=count,
            percentage=round(count / total_sizes * 100, 1)
        )
        for size, count in sorted_sizes
    ]
    
    sorted_brands = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    brands = [BrandCount(brand=brand, count=count) for brand, count in sorted_brands]
    
    sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    keywords = [{"keyword": k, "count": c} for k, c in sorted_keywords]
    
    return TireAnalysisResponse(
        period={"start": start_date, "end": end_date},
        total_tickets_analyzed=len(tickets),
        tickets_with_sizes=tickets_with_sizes,
        tire_sizes=tire_sizes,
        brands=brands,
        keywords=keywords
    )

# ============== EMAIL TEST ==============
class TestEmailRequest(BaseModel):
    recipient_email: EmailStr

@api_router.post("/admin/test-email")
async def test_email(request: TestEmailRequest, current_user: dict = Depends(get_current_user)):
    """Send a test email to verify SMTP or Resend configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem testar email")
    
    # Get email settings from DB
    email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    branding = await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
    
    # Check if SMTP is configured
    smtp_configured = email_settings and email_settings.get("smtp_host") and email_settings.get("smtp_port") and email_settings.get("smtp_username")
    
    if not smtp_configured and not RESEND_API_KEY:
        raise HTTPException(status_code=400, detail="Email não configurado. Configure SMTP nas definições ou RESEND_API_KEY no ficheiro .env")
    
    company_name = branding.get("company_name", "PDPV")
    company_subtitle = branding.get("company_subtitle", "Pneus de Pedro V.")
    primary_color = branding.get("primary_color", "#f97316")
    secondary_color = branding.get("secondary_color", "#1f2937")
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: {primary_color}; padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">{company_name}</h1>
            <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0 0;">{company_subtitle}</p>
        </div>
        <div style="padding: 20px; background-color: #f9fafb;">
            <h2 style="color: #1f2937;">Teste de Email Bem Sucedido!</h2>
            <p>Este é um email de teste do sistema {company_name}.</p>
            <p>Se está a receber este email, a configuração está correta.</p>
            <div style="background-color: #d1fae5; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #065f46; margin: 0;">✅ Configuração verificada com sucesso!</p>
            </div>
            <p style="color: #6b7280; font-size: 12px;">Método utilizado: {"SMTP" if smtp_configured else "Resend API"}</p>
        </div>
        <div style="background-color: {secondary_color}; padding: 15px; text-align: center;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                {company_name} - {company_subtitle}
            </p>
        </div>
    </div>
    """
    
    try:
        if smtp_configured:
            # Use SMTP
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            smtp_host = email_settings.get("smtp_host")
            smtp_port = email_settings.get("smtp_port", 587)
            smtp_username = email_settings.get("smtp_username")
            smtp_password = email_settings.get("smtp_password", "")
            smtp_use_ssl = email_settings.get("smtp_use_ssl", False)
            smtp_use_tls = email_settings.get("smtp_use_tls", True)
            email_from = email_settings.get("email_from") or smtp_username
            email_from_name = email_settings.get("email_from_name", company_name)
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{company_name}] Teste de Email"
            msg['From'] = f"{email_from_name} <{email_from}>"
            msg['To'] = request.recipient_email
            
            msg.attach(MIMEText(html_content, 'html'))
            
            def send_smtp():
                if smtp_use_ssl:
                    server = smtplib.SMTP_SSL(smtp_host, smtp_port)
                else:
                    server = smtplib.SMTP(smtp_host, smtp_port)
                    if smtp_use_tls:
                        server.starttls()
                
                if smtp_password:
                    server.login(smtp_username, smtp_password)
                
                server.sendmail(email_from, [request.recipient_email], msg.as_string())
                server.quit()
                return True
            
            await asyncio.to_thread(send_smtp)
            logger.info(f"[SMTP TEST] Test email sent to {request.recipient_email}")
            
            return {
                "status": "success",
                "message": f"Email de teste enviado via SMTP para {request.recipient_email}",
                "method": "SMTP"
            }
        else:
            # Use Resend
            email_from = email_settings.get("email_from", EMAIL_FROM) if email_settings else EMAIL_FROM
            params = {
                "from": email_from,
                "to": [request.recipient_email],
                "subject": f"[{company_name}] Teste de Email",
                "html": html_content
            }
            
            email_result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"[RESEND TEST] Test email sent to {request.recipient_email}, ID: {email_result.get('id')}")
            
            return {
                "status": "success",
                "message": f"Email de teste enviado via Resend para {request.recipient_email}",
                "email_id": email_result.get("id"),
                "method": "Resend"
            }
    except Exception as e:
        logger.error(f"[EMAIL TEST] Failed to send test email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar email: {str(e)}")

@api_router.get("/admin/email-config")
async def get_email_config(current_user: dict = Depends(get_current_user)):
    """Get email configuration status - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração")
    
    email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    email_from = email_settings.get("email_from", EMAIL_FROM) if email_settings else EMAIL_FROM
    
    return {
        "resend_configured": bool(RESEND_API_KEY),
        "email_from": email_from if RESEND_API_KEY else None
    }

# ============== QUOTE OPTIONS ==============
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

class QuoteOptionsUpdate(BaseModel):
    options: List[QuoteOptionCreate]

# ============== PUBLIC QUOTE RESPONSE ==============
class QuoteResponseRequest(BaseModel):
    status: str  # ACCEPTED or REJECTED
    comments: Optional[str] = None
    accepted_option_ids: List[str] = []  # IDs of accepted options

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
    quote_decided_at: Optional[str] = None  # When customer made decision
    quote_decision: Optional[str] = None  # ACCEPTED or REJECTED
    ticket_attachments: List[AttachmentPublicInfo] = []

# ============== QUOTE OPTIONS ENDPOINTS ==============
@api_router.get("/tickets/{ticket_id}/quote-options", response_model=List[QuoteOptionResponse])
async def get_quote_options(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Get all quote options for a ticket"""
    options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
    return options

@api_router.post("/tickets/{ticket_id}/quote-options", response_model=List[QuoteOptionResponse])
async def save_quote_options(ticket_id: str, data: QuoteOptionsUpdate, current_user: dict = Depends(get_current_user)):
    """Save/update quote options for a ticket (replaces all existing options)"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    # Check if quote is locked (already sent to customer)
    if ticket.get("quote_locked_at"):
        raise HTTPException(status_code=409, detail="Orçamento bloqueado - já foi enviado ao cliente. Use 'Criar nova versão' para alterações.")
    
    # Delete existing options
    await db.quote_options.delete_many({"ticket_id": ticket_id})
    
    # Create new options
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
    
    # Update ticket quote_value to total of all options
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "quote_value": total_amount,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Log note
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

@api_router.post("/tickets/{ticket_id}/generate-quote-link")
async def generate_quote_link(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Generate a unique link for client to respond to a quote"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    # Check if ticket has quote options or quote_value
    quote_options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
    if not quote_options and not ticket.get("quote_value"):
        raise HTTPException(status_code=400, detail="O ticket não tem opções de orçamento definidas")
    
    # Generate unique token
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)  # Link valid for 7 days
    
    # Save quote link
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
    
    # Update ticket - LOCK the quote when link is generated
    valid_until = datetime.now(timezone.utc) + timedelta(days=15)
    now = datetime.now(timezone.utc)
    update_fields = {
        "quote_sent": True,
        "quote_link_token": token,
        "quote_valid_until": valid_until.isoformat(),
        "updated_at": now.isoformat()
    }
    # Lock quote if not already locked
    if not ticket.get("quote_locked_at"):
        update_fields["quote_locked_at"] = now.isoformat()
    
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": update_fields}
    )
    
    # Log note
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_user_id": current_user["id"],
        "body": f"Link de orçamento gerado (válido até {expires_at.strftime('%d/%m/%Y')})",
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    # Get frontend URL for the response (no automatic email - user sends manually via message)
    email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    frontend_url = email_settings.get("frontend_url", FRONTEND_URL) if email_settings else FRONTEND_URL
    
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "link": f"/quote/{token}",
        "full_link": f"{frontend_url}/quote/{token}",
        "email_sent": False  # Email não é enviado automaticamente - utilizador envia manualmente
    }

@api_router.post("/tickets/{ticket_id}/quote-new-version")
async def create_new_quote_version(ticket_id: str, current_user: dict = Depends(get_current_user)):
    """Create a new version of the quote - unlocks for editing and generates new link"""
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if current_user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    if current_user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    # Only allow if quote was previously locked
    if not ticket.get("quote_locked_at"):
        raise HTTPException(status_code=400, detail="Orçamento não está bloqueado")
    
    now = datetime.now(timezone.utc)
    
    # Log previous decision if any
    previous_decision = ticket.get("quote_decision")
    previous_total = ticket.get("accepted_total")
    
    # Reset quote lock and decision fields for new version
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
    
    # Reset quote options is_accepted status
    await db.quote_options.update_many(
        {"ticket_id": ticket_id},
        {"$set": {"is_accepted": False, "accepted_at": None}}
    )
    
    # Log note
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

@api_router.get("/public/quote/{token}", response_model=QuoteResponseData)
async def get_public_quote(token: str):
    """Get quote details by public token - NO AUTH REQUIRED"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    # Check if expired
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Link expirado")
    
    ticket = await db.tickets.find_one({"id": quote_link["ticket_id"]}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Get quote options
    quote_options = await db.quote_options.find({"ticket_id": quote_link["ticket_id"]}, {"_id": 0}).to_list(100)
    
    # Get ticket attachments for public viewing
    ticket_attachments_raw = await db.attachments.find(
        {"ticket_id": quote_link["ticket_id"]},
        {"_id": 0, "id": 1, "original_filename": 1}
    ).to_list(100)
    attachment_map = {a["id"]: a["original_filename"] for a in ticket_attachments_raw}
    
    # Calculate accepted total if any
    accepted_options = [o for o in quote_options if o.get("is_accepted")]
    accepted_total = sum(o["amount"] for o in accepted_options) if accepted_options else None
    accepted_count = len(accepted_options) if accepted_options else None
    
    # Build enriched options with attachment details
    enriched_options = []
    for opt in quote_options:
        opt_attachments = [
            AttachmentPublicInfo(id=att_id, original_filename=attachment_map[att_id])
            for att_id in opt.get("attachment_ids", [])
            if att_id in attachment_map
        ]
        enriched_options.append(QuoteOptionPublicResponse(
            id=opt["id"],
            ticket_id=opt["ticket_id"],
            description=opt["description"],
            amount=opt["amount"],
            is_accepted=opt.get("is_accepted", False),
            accepted_at=opt.get("accepted_at"),
            attachments=opt_attachments
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

@api_router.post("/public/quote/{token}/respond")
async def respond_to_quote(token: str, response_data: QuoteResponseRequest):
    """Client responds to a quote - NO AUTH REQUIRED - ONE TIME ONLY"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    # Check if expired
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Link expirado")
    
    # Check if already responded via quote_link
    if quote_link.get("response_status"):
        raise HTTPException(status_code=409, detail="Já respondeu a este orçamento")
    
    # Check if ticket already has a decision (extra safety)
    ticket_id = quote_link["ticket_id"]
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    if ticket.get("quote_decided_at"):
        raise HTTPException(status_code=409, detail="Este orçamento já foi decidido anteriormente")
    
    if response_data.status not in ["ACCEPTED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Estado inválido")
    
    # Check quote validity
    if ticket.get("quote_valid_until"):
        valid_until_dt = datetime.fromisoformat(ticket["quote_valid_until"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > valid_until_dt:
            raise HTTPException(status_code=400, detail="Orçamento expirado. Contacte a oficina.")
    
    now = datetime.now(timezone.utc)
    
    # Get quote options
    quote_options = await db.quote_options.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(100)
    
    # Calculate accepted total from selected options
    accepted_total = 0
    accepted_count = 0
    accepted_descriptions = []
    
    if response_data.status == "ACCEPTED" and quote_options:
        # Mark selected options as accepted
        for opt in quote_options:
            if opt["id"] in response_data.accepted_option_ids:
                await db.quote_options.update_one(
                    {"id": opt["id"]},
                    {"$set": {"is_accepted": True, "accepted_at": now.isoformat()}}
                )
                accepted_total += opt["amount"]
                accepted_count += 1
                accepted_descriptions.append(f"{opt['description']} ({opt['amount']:.2f}€)")
        
        # If no options were selected but status is ACCEPTED, accept all (backwards compat)
        if accepted_count == 0 and not response_data.accepted_option_ids:
            for opt in quote_options:
                await db.quote_options.update_one(
                    {"id": opt["id"]},
                    {"$set": {"is_accepted": True, "accepted_at": now.isoformat()}}
                )
                accepted_total += opt["amount"]
                accepted_count += 1
                accepted_descriptions.append(f"{opt['description']} ({opt['amount']:.2f}€)")
    
    # Update quote link
    await db.quote_links.update_one(
        {"token": token},
        {"$set": {
            "response_status": response_data.status,
            "response_at": now.isoformat(),
            "response_comments": response_data.comments,
            "accepted_option_ids": response_data.accepted_option_ids
        }}
    )
    
    # Update ticket based on response - SET ONE-TIME DECISION FIELDS
    ticket_update = {
        "updated_at": now.isoformat(),
        "quote_response_status": response_data.status,
        "quote_response_at": now.isoformat(),
        "quote_decided_at": now.isoformat(),  # Mark decision timestamp
        "quote_decision": response_data.status  # ACCEPTED or REJECTED
    }
    
    if response_data.status == "ACCEPTED":
        # Change status to ACEITE_LINK if accepted
        ticket_update["status"] = TicketStatus.ACEITE_LINK.value
        if accepted_total > 0:
            ticket_update["accepted_total"] = accepted_total
            ticket_update["accepted_count"] = accepted_count
    else:
        # Change status to REJEITADO_LINK if rejected
        ticket_update["status"] = TicketStatus.REJEITADO_LINK.value
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": ticket_update})
    
    # Log note with details of accepted options
    status_text = "ACEITE" if response_data.status == "ACCEPTED" else "RECUSADO"
    if response_data.status == "ACCEPTED" and accepted_descriptions:
        note_body = f"Cliente respondeu ao orçamento: {status_text}\n"
        note_body += f"Opções aceites ({accepted_count} de {len(quote_options)}):\n"
        for desc in accepted_descriptions:
            note_body += f"  ✓ {desc}\n"
        note_body += f"Total aceite: {accepted_total:.2f}€"
    else:
        note_body = f"Cliente respondeu ao orçamento: {status_text}"
    
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
    
    return {
        "status": "success",
        "message": f"Resposta registada: {status_text}"
    }

@api_router.get("/public/quote/{token}/attachments/{attachment_id}/download")
async def download_attachment_public(token: str, attachment_id: str):
    """Download attachment via public quote token - NO AUTH REQUIRED"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    ticket_id = quote_link["ticket_id"]
    attachment = None
    
    # First, try to find in the main attachments collection (ticket attachments)
    attachment = await db.attachments.find_one({"id": attachment_id, "ticket_id": ticket_id}, {"_id": 0})
    
    # If not found, search in quote_options attachments (embedded)
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
    if not file_path.exists():
        # File doesn't exist on disk - redirect to dynamic PDF generation
        # This handles cases where files were lost between deployments
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/api/public/quote/{token}/pdf", status_code=302)
    
    return FileResponse(
        path=str(file_path),
        filename=attachment["original_filename"],
        media_type=attachment.get("file_type", "application/pdf")
    )

@api_router.get("/public/quote/{token}/pdf")
async def generate_quote_pdf(token: str):
    """Generate PDF on-the-fly for public quote - NO AUTH REQUIRED"""
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.colors import HexColor
    import io
    
    # Validate token
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    # Check expiration
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=410, detail="Link expirado")
    
    # Get ticket and quote options
    ticket = await db.tickets.find_one({"id": quote_link["ticket_id"]}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    quote_options = await db.quote_options.find({"ticket_id": quote_link["ticket_id"]}, {"_id": 0}).to_list(100)
    
    # Get branding
    branding = await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
    company_name = branding.get("company_name", "Pneus D. Pedro V")
    
    # Create PDF in memory
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Brand colors
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
        # Wrap description text
        desc_lines = ticket["description"].split("\n")
        for line in desc_lines[:10]:  # Limit to 10 lines
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
            if y < 100:  # New page if needed
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
        except:
            pass
    
    # Footer
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width/2, 30, f"Gerado automaticamente em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}")
    
    c.save()
    
    # Return PDF
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
            test_vapid = Vapid.from_string(private_key=VAPID_PRIVATE_KEY)
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
    # Load SLA configuration from database
    await load_sla_config_from_db()
    logger.info("[STARTUP] SLA configuration loaded from database")
    
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
