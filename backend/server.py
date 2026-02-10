from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Set
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
import jwt
from enum import Enum
import shutil
import asyncio
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
SECRET_KEY = os.environ.get('JWT_SECRET', 'pdpv-tickets-secret-key-2024')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# File storage
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

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

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ============== ENUMS ==============
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    AGENT = "AGENT"
    FINANCEIRO = "FINANCEIRO"
    INTERNAL_CREATOR = "INTERNAL_CREATOR"

class TicketChannel(str, Enum):
    TELEFONE = "TELEFONE"
    BALCAO = "BALCAO"
    FORMULARIO = "FORMULARIO"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    TELEGRAM = "TELEGRAM"

class TicketType(str, Enum):
    ORCAMENTO_PNEUS = "ORCAMENTO_PNEUS"
    ORCAMENTO_MECANICA = "ORCAMENTO_MECANICA"
    MARCACAO = "MARCACAO"
    INFORMACAO = "INFORMACAO"
    FINANCEIRO = "FINANCEIRO"
    INTERNO = "INTERNO"
    RECLAMACAO = "RECLAMACAO"

class TicketStatus(str, Enum):
    NOVO = "NOVO"
    TRIAGEM = "TRIAGEM"
    EM_ORCAMENTO = "EM_ORCAMENTO"
    AGUARDA_CLIENTE = "AGUARDA_CLIENTE"
    AGUARDA_PECA = "AGUARDA_PECA"
    AGENDADO = "AGENDADO"
    FINANCEIRO = "FINANCEIRO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"

class TicketPriority(str, Enum):
    NORMAL = "NORMAL"
    URGENTE = "URGENTE"

class MessageDirection(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"

class MessageChannel(str, Enum):
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"

class AlertType(str, Enum):
    SLA_FIRST_RESPONSE = "SLA_FIRST_RESPONSE"
    SLA_QUOTE = "SLA_QUOTE"
    FOLLOWUP = "FOLLOWUP"

# ============== MODELS ==============
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole = UserRole.AGENT

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: UserRole
    created_at: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None

class TicketCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None
    type: TicketType = TicketType.INFORMACAO
    channel: TicketChannel = TicketChannel.TELEFONE
    priority: TicketPriority = TicketPriority.NORMAL
    description: str = ""

class TicketUpdate(BaseModel):
    status: Optional[TicketStatus] = None
    assigned_to_user_id: Optional[str] = None
    priority: Optional[TicketPriority] = None
    quote_sent: Optional[bool] = None
    quote_value: Optional[float] = None
    description: Optional[str] = None

class TicketResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_number: str
    created_at: str
    updated_at: str
    channel: TicketChannel
    type: TicketType
    status: TicketStatus
    priority: TicketPriority
    description: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    last_public_message_at: Optional[str] = None
    first_response_done: bool = False
    sla_first_response_due: Optional[str] = None
    sla_quote_due: Optional[str] = None
    quote_sent: bool = False
    quote_value: Optional[float] = None
    is_overdue: bool = False

class MessageCreate(BaseModel):
    body: str
    channel: MessageChannel = MessageChannel.EMAIL

class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    created_at: str
    direction: MessageDirection
    channel: MessageChannel
    body: str
    from_text: Optional[str] = None
    to_text: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None

class NoteCreate(BaseModel):
    body: str

class NoteResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    created_at: str
    created_by_user_id: str
    created_by_name: Optional[str] = None
    body: str

class AlertResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    created_at: str
    alert_type: AlertType
    body: str
    is_resolved: bool = False

class AttachmentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    uploaded_at: str
    uploaded_by_user_id: Optional[str] = None
    uploaded_by_name: Optional[str] = None

class WhatsAppWebhook(BaseModel):
    phone: str
    name: str
    message_text: str
    timestamp: Optional[str] = None
    attachments_urls: List[str] = []

class TelegramWebhook(BaseModel):
    sender_name: str
    sender_id: str
    transcript_text: str
    timestamp: Optional[str] = None

class DashboardStats(BaseModel):
    novos: int = 0
    atrasados_sla: int = 0
    aguarda_cliente: int = 0
    em_orcamento: int = 0
    financeiro: int = 0
    total: int = 0

# ============== HELPERS ==============
def generate_ticket_number():
    now = datetime.now(timezone.utc)
    return f"TK{now.strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"

def compute_sla_first_response(ticket_type: TicketType) -> datetime:
    now = datetime.now(timezone.utc)
    if ticket_type == TicketType.FINANCEIRO:
        return now + timedelta(hours=4)
    return now + timedelta(hours=2)

def compute_sla_quote(ticket_type: TicketType) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    if ticket_type == TicketType.ORCAMENTO_PNEUS:
        return now + timedelta(hours=24)
    elif ticket_type == TicketType.ORCAMENTO_MECANICA:
        return now + timedelta(hours=48)
    return None

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token não fornecido")
    try:
        token = authorization
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="Utilizador não encontrado")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

def check_ticket_overdue(ticket: dict) -> bool:
    now = datetime.now(timezone.utc)
    if ticket.get("sla_first_response_due") and not ticket.get("first_response_done"):
        sla_due = datetime.fromisoformat(ticket["sla_first_response_due"].replace("Z", "+00:00"))
        if now > sla_due:
            return True
    if ticket.get("sla_quote_due") and not ticket.get("quote_sent"):
        sla_due = datetime.fromisoformat(ticket["sla_quote_due"].replace("Z", "+00:00"))
        if now > sla_due:
            return True
    return False

# ============== AUTH ROUTES ==============
@api_router.post("/auth/register", response_model=dict)
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    user_id = str(uuid.uuid4())
    hashed_password = pwd_context.hash(user_data.password)
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "password_hash": hashed_password,
        "name": user_data.name,
        "role": user_data.role.value,
        "created_at": now
    }
    await db.users.insert_one(user_doc)
    
    token = create_access_token({"sub": user_id, "role": user_data.role.value})
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": user_data.email,
            "name": user_data.name,
            "role": user_data.role.value,
            "created_at": now
        }
    }

@api_router.post("/auth/login", response_model=dict)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not pwd_context.verify(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    token = create_access_token({"sub": user["id"], "role": user["role"]})
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "created_at": user["created_at"]
        }
    }

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)

# ============== USER MANAGEMENT (ADMIN) ==============
@api_router.get("/users", response_model=List[UserResponse])
async def list_users(user: dict = Depends(get_current_user)):
    if user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]

@api_router.post("/users", response_model=UserResponse)
async def create_user(user_data: UserCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem criar utilizadores")
    
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    user_id = str(uuid.uuid4())
    hashed_password = pwd_context.hash(user_data.password)
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "password_hash": hashed_password,
        "name": user_data.name,
        "role": user_data.role.value,
        "created_at": now
    }
    await db.users.insert_one(user_doc)
    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password_hash"})

@api_router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    current_user = current_user
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem editar utilizadores")
    
    update_doc = {}
    if user_data.name:
        update_doc["name"] = user_data.name
    if user_data.role:
        update_doc["role"] = user_data.role.value
    if user_data.password:
        update_doc["password_hash"] = pwd_context.hash(user_data.password)
    
    if update_doc:
        await db.users.update_one({"id": user_id}, {"$set": update_doc})
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return UserResponse(**user)

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    current_user = current_user
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem eliminar utilizadores")
    
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return {"message": "Utilizador eliminado"}

# ============== TICKET ROUTES ==============
@api_router.post("/tickets", response_model=TicketResponse)
async def create_ticket(ticket_data: TicketCreate, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    # INTERNAL_CREATOR can only create INTERNO tickets
    if user["role"] == UserRole.INTERNAL_CREATOR.value and ticket_data.type != TicketType.INTERNO:
        raise HTTPException(status_code=403, detail="Apenas pode criar tickets internos")
    
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    ticket_number = generate_ticket_number()
    
    sla_first = compute_sla_first_response(ticket_data.type)
    sla_quote = compute_sla_quote(ticket_data.type)
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": ticket_data.channel.value,
        "type": ticket_data.type.value,
        "status": TicketStatus.NOVO.value,
        "priority": ticket_data.priority.value,
        "description": ticket_data.description,
        "customer_name": ticket_data.customer_name,
        "customer_phone": ticket_data.customer_phone,
        "customer_email": ticket_data.customer_email,
        "vehicle_plate": ticket_data.vehicle_plate,
        "assigned_to_user_id": None,
        "last_public_message_at": None,
        "first_response_done": False,
        "sla_first_response_due": sla_first.isoformat(),
        "sla_quote_due": sla_quote.isoformat() if sla_quote else None,
        "quote_sent": False,
        "quote_value": None,
        "created_by_user_id": user["id"]
    }
    await db.tickets.insert_one(ticket_doc)
    
    # Notify supervisors about new ticket
    asyncio.create_task(notify_supervisors(
        title="Novo Ticket",
        body=f"Ticket {ticket_number} criado - {ticket_data.customer_name}",
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
    
    query = {}
    
    # Role-based filtering
    if user["role"] == UserRole.AGENT.value:
        query["assigned_to_user_id"] = user["id"]
    elif user["role"] == UserRole.FINANCEIRO.value:
        query["type"] = TicketType.FINANCEIRO.value
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
            {"ticket_number": {"$regex": search, "$options": "i"}}
        ]
    
    tickets = await db.tickets.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Get assigned user names
    user_ids = list(set([t.get("assigned_to_user_id") for t in tickets if t.get("assigned_to_user_id")]))
    users_map = {}
    if user_ids:
        users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        users_map = {u["id"]: u["name"] for u in users}
    
    result = []
    now = datetime.now(timezone.utc)
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

@api_router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
        raise HTTPException(status_code=403, detail="Sem permissão para ver este ticket")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão para ver tickets")
    
    # Get assigned user name
    if ticket.get("assigned_to_user_id"):
        assigned_user = await db.users.find_one({"id": ticket["assigned_to_user_id"]}, {"_id": 0, "name": 1})
        ticket["assigned_to_name"] = assigned_user["name"] if assigned_user else None
    
    ticket["is_overdue"] = check_ticket_overdue(ticket)
    return TicketResponse(**ticket)

@api_router.put("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: str, ticket_data: TicketUpdate, current_user: dict = Depends(get_current_user)):
    user = current_user
    
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value:
        if ticket.get("assigned_to_user_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Sem permissão para editar este ticket")
        # Agents cannot change assignment
        if ticket_data.assigned_to_user_id is not None:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar atribuição")
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
        raise HTTPException(status_code=403, detail="Sem permissão para editar este ticket")
    if user["role"] == UserRole.INTERNAL_CREATOR.value:
        raise HTTPException(status_code=403, detail="Sem permissão para editar tickets")
    
    update_doc = {"updated_at": datetime.now(timezone.utc).isoformat()}
    old_status = ticket.get("status")
    old_assigned = ticket.get("assigned_to_user_id")
    
    if ticket_data.status is not None:
        update_doc["status"] = ticket_data.status.value
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
    
    await db.tickets.update_one({"id": ticket_id}, {"$set": update_doc})
    
    # Log status/assignment changes
    if ticket_data.status and ticket_data.status.value != old_status:
        note_doc = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by_user_id": user["id"],
            "body": f"Estado alterado de {old_status} para {ticket_data.status.value}",
            "is_system": True
        }
        await db.notes.insert_one(note_doc)
    
    if ticket_data.assigned_to_user_id is not None and ticket_data.assigned_to_user_id != old_assigned:
        assigned_name = "Ninguém"
        if ticket_data.assigned_to_user_id:
            assigned_user = await db.users.find_one({"id": ticket_data.assigned_to_user_id}, {"_id": 0, "name": 1})
            assigned_name = assigned_user["name"] if assigned_user else ticket_data.assigned_to_user_id
            
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
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
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
        "created_by_user_id": user["id"]
    }
    await db.messages.insert_one(message_doc)
    
    # Update ticket
    update_doc = {
        "updated_at": now.isoformat(),
        "last_public_message_at": now.isoformat(),
        "first_response_done": True
    }
    await db.tickets.update_one({"id": ticket_id}, {"$set": update_doc})
    
    # Mock email sending (in production, integrate with email service)
    logger.info(f"[MOCK EMAIL] Sending to {message_doc['to_text']}: {message_data.body[:100]}")
    
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
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
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
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
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
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
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
    if user["role"] == UserRole.FINANCEIRO.value and ticket.get("type") != TicketType.FINANCEIRO.value:
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
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado no servidor")
    
    return FileResponse(
        path=str(file_path),
        filename=attachment["original_filename"],
        media_type=attachment["file_type"]
    )

# ============== DASHBOARD ==============
@api_router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    user = current_user
    
    base_query = {}
    
    # Role-based filtering
    if user["role"] == UserRole.AGENT.value:
        base_query["assigned_to_user_id"] = user["id"]
    elif user["role"] == UserRole.FINANCEIRO.value:
        base_query["type"] = TicketType.FINANCEIRO.value
    elif user["role"] == UserRole.INTERNAL_CREATOR.value:
        return DashboardStats()
    
    # Count stats
    novos = await db.tickets.count_documents({**base_query, "status": TicketStatus.NOVO.value})
    aguarda_cliente = await db.tickets.count_documents({**base_query, "status": TicketStatus.AGUARDA_CLIENTE.value})
    em_orcamento = await db.tickets.count_documents({**base_query, "status": TicketStatus.EM_ORCAMENTO.value})
    financeiro = await db.tickets.count_documents({**base_query, "type": TicketType.FINANCEIRO.value})
    
    # Count overdue
    now = datetime.now(timezone.utc)
    all_tickets = await db.tickets.find({
        **base_query,
        "status": {"$nin": [TicketStatus.CONCLUIDO.value, TicketStatus.CANCELADO.value]}
    }, {"_id": 0}).to_list(10000)
    
    atrasados = sum(1 for t in all_tickets if check_ticket_overdue(t))
    
    total = await db.tickets.count_documents(base_query)
    
    return DashboardStats(
        novos=novos,
        atrasados_sla=atrasados,
        aguarda_cliente=aguarda_cliente,
        em_orcamento=em_orcamento,
        financeiro=financeiro,
        total=total
    )

# ============== WEBHOOKS ==============
@api_router.post("/webhook/whatsapp/inbound")
async def whatsapp_webhook(data: WhatsAppWebhook):
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=48)
    
    # Find existing open ticket for this phone
    existing_ticket = await db.tickets.find_one({
        "customer_phone": data.phone,
        "status": {"$nin": [TicketStatus.CONCLUIDO.value, TicketStatus.CANCELADO.value]},
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
        sla_first = compute_sla_first_response(TicketType.INFORMACAO)
        
        ticket_doc = {
            "id": ticket_id,
            "ticket_number": ticket_number,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "channel": TicketChannel.WHATSAPP.value,
            "type": TicketType.INFORMACAO.value,
            "status": TicketStatus.NOVO.value,
            "priority": TicketPriority.NORMAL.value,
            "description": data.message_text,
            "customer_name": data.name,
            "customer_phone": data.phone,
            "customer_email": None,
            "vehicle_plate": None,
            "assigned_to_user_id": None,
            "last_public_message_at": now.isoformat(),
            "first_response_done": False,
            "sla_first_response_due": sla_first.isoformat(),
            "sla_quote_due": None,
            "quote_sent": False,
            "quote_value": None,
            "created_by_user_id": None
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
    sla_first = compute_sla_first_response(TicketType.INTERNO)
    
    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": TicketChannel.TELEGRAM.value,
        "type": TicketType.INTERNO.value,
        "status": TicketStatus.NOVO.value,
        "priority": TicketPriority.NORMAL.value,
        "description": data.transcript_text,
        "customer_name": data.sender_name,
        "customer_phone": data.sender_id,
        "customer_email": None,
        "vehicle_plate": None,
        "assigned_to_user_id": None,
        "last_public_message_at": None,
        "first_response_done": False,
        "sla_first_response_due": sla_first.isoformat(),
        "sla_quote_due": None,
        "quote_sent": False,
        "quote_value": None,
        "created_by_user_id": None
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
    
    # Create financeiro
    fin_doc = {
        "id": str(uuid.uuid4()),
        "email": "financeiro@pdpv.pt",
        "password_hash": pwd_context.hash("fin123"),
        "name": "Ana Costa",
        "role": UserRole.FINANCEIRO.value,
        "created_at": now
    }
    await db.users.insert_one(fin_doc)
    
    return {"message": "Dados de seed criados com sucesso"}

# Include the router
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

# ============== WEBSOCKET ==============
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
    
    return notification_doc

async def notify_supervisors(title: str, body: str, notification_type: str = "info", ticket_id: str = None, ticket_number: str = None):
    # Get all supervisors and admins
    supervisors = await db.users.find(
        {"role": {"$in": [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]}},
        {"_id": 0, "id": 1}
    ).to_list(100)
    
    for sup in supervisors:
        await create_notification(sup["id"], title, body, notification_type, ticket_id, ticket_number)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
