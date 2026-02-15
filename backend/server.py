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
from pywebpush import webpush, WebPushException
import resend

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Resend config
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'onboarding@resend.dev')
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# JWT Config
SECRET_KEY = os.environ.get('JWT_SECRET', 'pdpv-tickets-secret-key-2024')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# File storage
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# VAPID Config for Web Push
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '').replace('\\n', '\n')
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@pdpv.pt')

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

# ============== ENUMS ==============
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    AGENT = "AGENT"
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
    INTERNO = "INTERNO"
    RECLAMACAO = "RECLAMACAO"

class TicketStatus(str, Enum):
    ABERTO = "ABERTO"
    EM_TRATAMENTO = "EM_TRATAMENTO"
    AGUARDA_CLIENTE = "AGUARDA_CLIENTE"
    FECHADO = "FECHADO"

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
    assigned_to_user_id: Optional[str] = None

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
    sla_due: Optional[str] = None
    quote_sent: bool = False
    quote_value: Optional[float] = None
    quote_response_status: Optional[str] = None
    quote_response_at: Optional[str] = None
    is_overdue: bool = False
    archived_at: Optional[str] = None
    archived_by: Optional[str] = None

class TicketStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: str
    old_status: Optional[str] = None
    new_status: str
    changed_by_user_id: str
    changed_by_name: Optional[str] = None
    changed_at: str

class MessageCreate(BaseModel):
    body: str
    channel: MessageChannel = MessageChannel.EMAIL
    is_quote_response: bool = False  # If true, changes ticket status to AGUARDA_CLIENTE
    attachment_ids: List[str] = []  # List of attachment IDs to link to this message

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
    attachment_ids: List[str] = []

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

# ============== CUSTOMER & VEHICLE MODELS ==============
class VehicleCreate(BaseModel):
    plate: str
    model: Optional[str] = None
    observations: Optional[str] = None

class VehicleResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    customer_id: str
    plate: str
    model: Optional[str] = None
    observations: Optional[str] = None

class CustomerCreate(BaseModel):
    code: Optional[str] = None
    name: str
    nif: Optional[str] = None
    customer_type: Optional[str] = None
    address: Optional[str] = None
    phones: List[str] = []
    fax: Optional[str] = None
    emails: List[str] = []
    vehicles: List[VehicleCreate] = []

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    nif: Optional[str] = None
    customer_type: Optional[str] = None
    address: Optional[str] = None
    phones: Optional[List[str]] = None
    fax: Optional[str] = None
    emails: Optional[List[str]] = None

class CustomerResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: Optional[str] = None
    name: str
    nif: Optional[str] = None
    customer_type: Optional[str] = None
    address: Optional[str] = None
    phones: List[str] = []
    fax: Optional[str] = None
    emails: List[str] = []
    created_at: str
    updated_at: str
    vehicles: List[VehicleResponse] = []
    ticket_count: int = 0

class CustomerSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    phones: List[str] = []
    emails: List[str] = []
    vehicle_plate: Optional[str] = None
    vehicle_model: Optional[str] = None

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
    em_tratamento: int = 0
    total: int = 0

# ============== HELPERS ==============
def generate_ticket_number():
    now = datetime.now(timezone.utc)
    return f"TK{now.strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"

def compute_sla_due() -> datetime:
    """Returns SLA due date - 2 hours from now by default"""
    now = datetime.now(timezone.utc)
    return now + timedelta(hours=2)

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
    """Check if ticket is overdue based on SLA due date and first response status"""
    now = datetime.now(timezone.utc)
    # Only check SLA if ticket is not closed and hasn't received first response
    if ticket.get("status") == TicketStatus.FECHADO.value:
        return False
    if ticket.get("sla_due") and not ticket.get("first_response_done"):
        sla_due = datetime.fromisoformat(ticket["sla_due"].replace("Z", "+00:00"))
        if now > sla_due:
            return True
    return False

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

# ============== CUSTOMER MANAGEMENT ==============
@api_router.get("/customers", response_model=List[CustomerResponse])
async def list_customers(
    current_user: dict = Depends(get_current_user),
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"nif": {"$regex": search, "$options": "i"}},
            {"phones": {"$regex": search, "$options": "i"}},
            {"emails": {"$regex": search, "$options": "i"}}
        ]
    
    customers = await db.customers.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    
    if not customers:
        return []
    
    # Batch fetch all vehicles for these customers (avoid N+1)
    customer_ids = [c["id"] for c in customers]
    all_vehicles = await db.vehicles.find(
        {"customer_id": {"$in": customer_ids}}, 
        {"_id": 0}
    ).to_list(1000)
    
    # Group vehicles by customer_id
    vehicles_by_customer = {}
    for v in all_vehicles:
        cid = v["customer_id"]
        if cid not in vehicles_by_customer:
            vehicles_by_customer[cid] = []
        vehicles_by_customer[cid].append(v)
    
    # Build result with vehicles (ticket_count set to 0 for performance - can be loaded on detail view)
    result = []
    for c in customers:
        c["vehicles"] = vehicles_by_customer.get(c["id"], [])
        c["ticket_count"] = 0  # Skip ticket count query for list performance
        result.append(CustomerResponse(**c))
    
    return result

@api_router.get("/customers/search")
async def search_customers(
    current_user: dict = Depends(get_current_user),
    q: str = ""
):
    """Search customers by phone, plate or name for auto-complete - returns full customer data"""
    if len(q) < 2:
        return []
    
    customer_ids_found = set()
    customers_data = {}  # id -> customer data
    
    # Search by phone
    customers_by_phone = await db.customers.find(
        {"phones": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).limit(10).to_list(10)
    
    for c in customers_by_phone:
        if c["id"] not in customer_ids_found:
            customer_ids_found.add(c["id"])
            customers_data[c["id"]] = c
    
    # Search by plate - get customer_ids from vehicles
    vehicles_by_plate = await db.vehicles.find(
        {"plate": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).limit(10).to_list(10)
    
    plate_customer_ids = [v["customer_id"] for v in vehicles_by_plate if v["customer_id"] not in customer_ids_found]
    if plate_customer_ids:
        customers_from_plates = await db.customers.find(
            {"id": {"$in": plate_customer_ids}},
            {"_id": 0}
        ).to_list(10)
        for c in customers_from_plates:
            if c["id"] not in customer_ids_found:
                customer_ids_found.add(c["id"])
                customers_data[c["id"]] = c
    
    # Search by name
    customers_by_name = await db.customers.find(
        {"name": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).limit(10).to_list(10)
    
    for c in customers_by_name:
        if c["id"] not in customer_ids_found:
            customer_ids_found.add(c["id"])
            customers_data[c["id"]] = c
    
    # Batch fetch all vehicles for found customers (single query instead of N queries)
    if customer_ids_found:
        all_vehicles = await db.vehicles.find(
            {"customer_id": {"$in": list(customer_ids_found)}},
            {"_id": 0}
        ).to_list(500)
        
        vehicles_by_customer = {}
        for v in all_vehicles:
            cid = v["customer_id"]
            if cid not in vehicles_by_customer:
                vehicles_by_customer[cid] = []
            vehicles_by_customer[cid].append({"plate": v["plate"], "model": v.get("model")})
    else:
        vehicles_by_customer = {}
    
    # Build results
    results = []
    for cid, c in customers_data.items():
        results.append({
            "id": c["id"],
            "name": c["name"],
            "phones": c.get("phones", []),
            "emails": c.get("emails", []),
            "vehicles": vehicles_by_customer.get(cid, [])
        })
    
    return results[:15]

@api_router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    vehicles = await db.vehicles.find({"customer_id": customer_id}, {"_id": 0}).to_list(100)
    customer["vehicles"] = vehicles
    
    ticket_count = await db.tickets.count_documents({
        "$or": [
            {"customer_phone": {"$in": customer.get("phones", [])}},
            {"customer_email": {"$in": customer.get("emails", [])}}
        ]
    })
    customer["ticket_count"] = ticket_count
    
    return CustomerResponse(**customer)

@api_router.get("/customers/{customer_id}/history")
async def get_customer_history(customer_id: str, current_user: dict = Depends(get_current_user)):
    """Get all tickets and vehicles for a customer"""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Get vehicles
    vehicles = await db.vehicles.find({"customer_id": customer_id}, {"_id": 0}).to_list(100)
    vehicle_plates = [v["plate"] for v in vehicles]
    
    # Get tickets by phone, email, or plate
    query = {"$or": []}
    if customer.get("phones"):
        query["$or"].append({"customer_phone": {"$in": customer["phones"]}})
    if customer.get("emails"):
        query["$or"].append({"customer_email": {"$in": customer["emails"]}})
    if vehicle_plates:
        query["$or"].append({"vehicle_plate": {"$in": vehicle_plates}})
    
    if not query["$or"]:
        tickets = []
    else:
        tickets = await db.tickets.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    return {
        "customer": customer,
        "vehicles": vehicles,
        "tickets": tickets,
        "total_tickets": len(tickets)
    }

@api_router.post("/customers", response_model=CustomerResponse)
async def create_customer(customer_data: CustomerCreate, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    customer_id = str(uuid.uuid4())
    
    customer_doc = {
        "id": customer_id,
        "code": customer_data.code,
        "name": customer_data.name,
        "nif": customer_data.nif,
        "customer_type": customer_data.customer_type,
        "address": customer_data.address,
        "phones": customer_data.phones,
        "fax": customer_data.fax,
        "emails": customer_data.emails,
        "created_at": now,
        "updated_at": now
    }
    await db.customers.insert_one(customer_doc)
    
    # Create vehicles
    vehicles = []
    for v in customer_data.vehicles:
        vehicle_id = str(uuid.uuid4())
        vehicle_doc = {
            "id": vehicle_id,
            "customer_id": customer_id,
            "plate": v.plate.upper().strip(),
            "model": v.model,
            "observations": v.observations
        }
        await db.vehicles.insert_one(vehicle_doc)
        vehicles.append(vehicle_doc)
    
    customer_doc["vehicles"] = vehicles
    customer_doc["ticket_count"] = 0
    return CustomerResponse(**customer_doc)

@api_router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: str, customer_data: CustomerUpdate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    update_doc = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if customer_data.name is not None:
        update_doc["name"] = customer_data.name
    if customer_data.nif is not None:
        update_doc["nif"] = customer_data.nif
    if customer_data.customer_type is not None:
        update_doc["customer_type"] = customer_data.customer_type
    if customer_data.address is not None:
        update_doc["address"] = customer_data.address
    if customer_data.phones is not None:
        update_doc["phones"] = customer_data.phones
    if customer_data.fax is not None:
        update_doc["fax"] = customer_data.fax
    if customer_data.emails is not None:
        update_doc["emails"] = customer_data.emails
    
    await db.customers.update_one({"id": customer_id}, {"$set": update_doc})
    
    updated = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    vehicles = await db.vehicles.find({"customer_id": customer_id}, {"_id": 0}).to_list(100)
    updated["vehicles"] = vehicles
    updated["ticket_count"] = 0
    return CustomerResponse(**updated)

@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem eliminar clientes")
    
    result = await db.customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Delete associated vehicles
    await db.vehicles.delete_many({"customer_id": customer_id})
    
    return {"message": "Cliente eliminado"}

# ============== VEHICLE MANAGEMENT ==============
@api_router.post("/customers/{customer_id}/vehicles", response_model=VehicleResponse)
async def add_vehicle(customer_id: str, vehicle_data: VehicleCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    vehicle_id = str(uuid.uuid4())
    vehicle_doc = {
        "id": vehicle_id,
        "customer_id": customer_id,
        "plate": vehicle_data.plate.upper().strip(),
        "model": vehicle_data.model,
        "observations": vehicle_data.observations
    }
    await db.vehicles.insert_one(vehicle_doc)
    return VehicleResponse(**vehicle_doc)

@api_router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.vehicles.delete_one({"id": vehicle_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Veículo não encontrado")
    return {"message": "Veículo eliminado"}

# ============== IMPORT CUSTOMERS ==============
@api_router.post("/customers/import")
async def import_customers(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Import customers from Excel file"""
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para importar")
    
    import pandas as pd
    import io
    
    content = await file.read()
    xlsx = pd.ExcelFile(io.BytesIO(content))
    
    imported_customers = 0
    imported_vehicles = 0
    errors = []
    
    # Process customers sheet
    customers_df = None
    vehicles_df = None
    
    for sheet in xlsx.sheet_names:
        if 'cliente' in sheet.lower():
            customers_df = pd.read_excel(xlsx, sheet_name=sheet)
        elif 'viatura' in sheet.lower():
            vehicles_df = pd.read_excel(xlsx, sheet_name=sheet)
    
    if customers_df is None:
        raise HTTPException(status_code=400, detail="Folha de clientes não encontrada")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Group customers by code to merge contacts
    customer_map = {}  # code -> customer data
    
    for _, row in customers_df.iterrows():
        try:
            code = str(row.get('Código', '')).strip()
            if not code or code == 'nan':
                continue
            
            name = str(row.get('Nome', '')).strip()
            if not name or name == 'nan':
                continue
            
            if code not in customer_map:
                customer_map[code] = {
                    "code": code,
                    "name": name,
                    "nif": str(row.get('Nif', '')).strip() if pd.notna(row.get('Nif')) else None,
                    "customer_type": str(row.get('tipo de cliente', '')).strip() if pd.notna(row.get('tipo de cliente')) else None,
                    "address": str(row.get('Morada', '')).strip() if pd.notna(row.get('Morada')) else None,
                    "phones": set(),
                    "fax": str(row.get('Fax', '')).strip() if pd.notna(row.get('Fax')) else None,
                    "emails": set()
                }
            
            # Add phones
            for phone_col in ['Telefone1', 'Telefone2']:
                phone = row.get(phone_col)
                if pd.notna(phone):
                    phone_str = str(int(phone) if isinstance(phone, float) else phone).strip()
                    if phone_str and phone_str != 'nan':
                        customer_map[code]["phones"].add(phone_str)
            
            # Add email
            email = row.get('Email')
            if pd.notna(email):
                email_str = str(email).strip()
                if email_str and email_str != 'nan' and '@' in email_str:
                    customer_map[code]["emails"].add(email_str)
        except Exception as e:
            errors.append(f"Erro na linha cliente: {str(e)}")
    
    # Insert customers
    customer_id_map = {}  # name -> id
    for code, cdata in customer_map.items():
        try:
            # Check if exists by code
            existing = await db.customers.find_one({"code": code})
            if existing:
                customer_id_map[cdata["name"]] = existing["id"]
                # Update phones/emails
                await db.customers.update_one(
                    {"id": existing["id"]},
                    {"$addToSet": {
                        "phones": {"$each": list(cdata["phones"])},
                        "emails": {"$each": list(cdata["emails"])}
                    }}
                )
                continue
            
            customer_id = str(uuid.uuid4())
            customer_doc = {
                "id": customer_id,
                "code": code,
                "name": cdata["name"],
                "nif": cdata["nif"],
                "customer_type": cdata["customer_type"],
                "address": cdata["address"],
                "phones": list(cdata["phones"]),
                "fax": cdata["fax"],
                "emails": list(cdata["emails"]),
                "created_at": now,
                "updated_at": now
            }
            await db.customers.insert_one(customer_doc)
            customer_id_map[cdata["name"]] = customer_id
            imported_customers += 1
        except Exception as e:
            errors.append(f"Erro ao criar cliente {cdata['name']}: {str(e)}")
    
    # Process vehicles
    if vehicles_df is not None:
        for _, row in vehicles_df.iterrows():
            try:
                plate = str(row.get('Matrícula', '')).strip().upper()
                if not plate or plate == 'NAN':
                    continue
                
                client_name = str(row.get('Cliente', '')).strip()
                model = str(row.get('Modelo', '')).strip() if pd.notna(row.get('Modelo')) else None
                obs = str(row.get('Observações', '')).strip() if pd.notna(row.get('Observações')) else None
                
                # Find customer by name
                customer_id = customer_id_map.get(client_name)
                if not customer_id:
                    # Try to find in DB
                    customer = await db.customers.find_one({"name": client_name}, {"_id": 0, "id": 1})
                    if customer:
                        customer_id = customer["id"]
                    else:
                        continue
                
                # Check if vehicle exists
                existing = await db.vehicles.find_one({"plate": plate})
                if existing:
                    continue
                
                vehicle_doc = {
                    "id": str(uuid.uuid4()),
                    "customer_id": customer_id,
                    "plate": plate,
                    "model": model,
                    "observations": obs
                }
                await db.vehicles.insert_one(vehicle_doc)
                imported_vehicles += 1
            except Exception as e:
                errors.append(f"Erro ao criar veículo: {str(e)}")
    
    return {
        "message": "Importação concluída",
        "imported_customers": imported_customers,
        "imported_vehicles": imported_vehicles,
        "errors": errors[:10]  # Return first 10 errors
    }

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
    
    sla_due = compute_sla_due()
    
    # Set status to EM_TRATAMENTO if assigned to someone, otherwise ABERTO
    initial_status = TicketStatus.EM_TRATAMENTO.value if ticket_data.assigned_to_user_id else TicketStatus.ABERTO.value
    
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
        "last_public_message_at": None,
        "first_response_done": False,
        "sla_due": sla_due.isoformat(),
        "quote_sent": False,
        "quote_value": None,
        "created_by_user_id": user["id"],
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
        query["assigned_to_user_id"] = user["id"]
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
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value and ticket.get("assigned_to_user_id") != user["id"]:
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
    
    # Check if ticket is archived
    if ticket.get("archived_at"):
        raise HTTPException(status_code=400, detail="Não é possível editar um ticket arquivado")
    
    # Check permissions
    if user["role"] == UserRole.AGENT.value:
        if ticket.get("assigned_to_user_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Sem permissão para editar este ticket")
        # Agents cannot change assignment
        if ticket_data.assigned_to_user_id is not None:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar atribuição")
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
    
    # Log status change to history
    if ticket_data.status and ticket_data.status.value != old_status:
        await log_status_change(ticket_id, old_status, ticket_data.status.value, user["id"])
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
            
            # Build HTML content
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #f97316; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">PDPV Tickets</h1>
                </div>
                <div style="padding: 20px; background-color: #f9fafb;">
                    <p>Olá <strong>{ticket['customer_name']}</strong>,</p>
                    <p>Recebeu uma nova resposta ao seu pedido:</p>
                    <div style="background-color: white; padding: 15px; border-left: 4px solid #f97316; margin: 20px 0;">
                        {message_data.body.replace(chr(10), '<br>')}
                    </div>
                    <p style="color: #6b7280; font-size: 14px;">
                        Referência do ticket: <strong>{ticket['ticket_number']}</strong>
                    </p>
                    {f'<p style="color: #6b7280; font-size: 14px;">Este email inclui {len(message_data.attachment_ids)} anexo(s).</p>' if message_data.attachment_ids else ''}
                </div>
                <div style="background-color: #1f2937; padding: 15px; text-align: center;">
                    <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                        PDPV - Pneus de Pedro V. | Este é um email automático, por favor não responda.
                    </p>
                </div>
            </div>
            """
            
            params = {
                "from": EMAIL_FROM,
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
    
    # Base query: exclude archived tickets
    base_query = {"archived_at": None}
    
    # Role-based filtering
    if user["role"] == UserRole.AGENT.value:
        base_query["assigned_to_user_id"] = user["id"]
    elif user["role"] == UserRole.INTERNAL_CREATOR.value:
        return DashboardStats()
    
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
        sla_due = compute_sla_due()
        
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
    sla_due = compute_sla_due()
    
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

async def send_web_push_to_user(user_id: str, title: str, body: str, url: str = None):
    """Send web push notification to all devices of a user"""
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not configured, skipping web push")
        return
    
    subscriptions = await db.push_subscriptions.find(
        {"user_id": user_id},
        {"_id": 0}
    ).to_list(100)
    
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": "/logo192.png",
        "badge": "/logo192.png",
        "url": url or "/"
    })
    
    for sub in subscriptions:
        try:
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
            logger.error(f"Web push failed for user {user_id}: {e}")
            # If subscription is expired/invalid, remove it
            if e.response and e.response.status_code in [404, 410]:
                await db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                logger.info(f"Removed invalid subscription for user {user_id}")

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

class TicketStatusUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    is_final: Optional[bool] = None

class TicketStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    label: str
    color: str
    is_final: bool
    order: int = 0
    created_at: str

@api_router.get("/admin/ticket-statuses", response_model=List[TicketStatusResponse])
async def list_ticket_statuses(current_user: dict = Depends(get_current_user)):
    """List all ticket statuses - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver estados")
    
    statuses = await db.ticket_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    
    # If no statuses in DB, return defaults
    if not statuses:
        default_statuses = [
            {"id": str(uuid.uuid4()), "code": "ABERTO", "label": "Aberto", "color": "#22c55e", "is_final": False, "order": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "EM_TRATAMENTO", "label": "Em Tratamento", "color": "#3b82f6", "is_final": False, "order": 1, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGUARDA_CLIENTE", "label": "Aguarda Cliente", "color": "#f59e0b", "is_final": False, "order": 2, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "FECHADO", "label": "Fechado", "color": "#6b7280", "is_final": True, "order": 3, "created_at": datetime.now(timezone.utc).isoformat()}
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
class SlaConfigUpdate(BaseModel):
    first_response_hours: Optional[int] = None
    quote_response_hours: Optional[int] = None
    enabled: Optional[bool] = None

class SlaConfigResponse(BaseModel):
    first_response_hours: int = 2
    quote_response_hours: int = 24
    enabled: bool = True

@api_router.get("/admin/sla-config", response_model=SlaConfigResponse)
async def get_sla_config(current_user: dict = Depends(get_current_user)):
    """Get SLA configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração SLA")
    
    config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
    if not config:
        return SlaConfigResponse()
    
    return SlaConfigResponse(
        first_response_hours=config.get("first_response_hours", 2),
        quote_response_hours=config.get("quote_response_hours", 24),
        enabled=config.get("enabled", True)
    )

@api_router.put("/admin/sla-config", response_model=SlaConfigResponse)
async def update_sla_config(config_data: SlaConfigUpdate, current_user: dict = Depends(get_current_user)):
    """Update SLA configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configuração SLA")
    
    existing = await db.settings.find_one({"type": "sla_config"})
    
    update_doc = {"type": "sla_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    if config_data.first_response_hours is not None:
        update_doc["first_response_hours"] = config_data.first_response_hours
    if config_data.quote_response_hours is not None:
        update_doc["quote_response_hours"] = config_data.quote_response_hours
    if config_data.enabled is not None:
        update_doc["enabled"] = config_data.enabled
    
    if existing:
        await db.settings.update_one({"type": "sla_config"}, {"$set": update_doc})
    else:
        update_doc["first_response_hours"] = config_data.first_response_hours or 2
        update_doc["quote_response_hours"] = config_data.quote_response_hours or 24
        update_doc["enabled"] = config_data.enabled if config_data.enabled is not None else True
        await db.settings.insert_one(update_doc)
    
    config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
    return SlaConfigResponse(
        first_response_hours=config.get("first_response_hours", 2),
        quote_response_hours=config.get("quote_response_hours", 24),
        enabled=config.get("enabled", True)
    )

# ============== ADMIN SETTINGS - EMAIL CONFIG ==============
class EmailConfigUpdate(BaseModel):
    resend_api_key: Optional[str] = None
    email_from: Optional[str] = None
    frontend_url: Optional[str] = None

class EmailConfigResponse(BaseModel):
    resend_configured: bool = False
    email_from: Optional[str] = None
    frontend_url: Optional[str] = None

@api_router.get("/admin/email-settings", response_model=EmailConfigResponse)
async def get_email_settings(current_user: dict = Depends(get_current_user)):
    """Get email settings - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configurações de email")
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    
    return EmailConfigResponse(
        resend_configured=bool(RESEND_API_KEY or (config and config.get("resend_api_key"))),
        email_from=EMAIL_FROM if RESEND_API_KEY else (config.get("email_from") if config else None),
        frontend_url=config.get("frontend_url", "https://pdpv-workshop.preview.emergentagent.com") if config else "https://pdpv-workshop.preview.emergentagent.com"
    )

@api_router.put("/admin/email-settings", response_model=EmailConfigResponse)
async def update_email_settings(config_data: EmailConfigUpdate, current_user: dict = Depends(get_current_user)):
    """Update email settings - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configurações de email")
    
    existing = await db.settings.find_one({"type": "email_config"})
    
    update_doc = {"type": "email_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    if config_data.resend_api_key is not None:
        update_doc["resend_api_key"] = config_data.resend_api_key
    if config_data.email_from is not None:
        update_doc["email_from"] = config_data.email_from
    if config_data.frontend_url is not None:
        update_doc["frontend_url"] = config_data.frontend_url
    
    if existing:
        await db.settings.update_one({"type": "email_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    return EmailConfigResponse(
        resend_configured=bool(RESEND_API_KEY or config.get("resend_api_key")),
        email_from=EMAIL_FROM if RESEND_API_KEY else config.get("email_from"),
        frontend_url=config.get("frontend_url", "https://pdpv-workshop.preview.emergentagent.com")
    )

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
    daily_ticket_counts: List[Dict[str, any]] = []

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
            except:
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

# ============== EMAIL TEST ==============
class TestEmailRequest(BaseModel):
    recipient_email: EmailStr

@api_router.post("/admin/test-email")
async def test_email(request: TestEmailRequest, current_user: dict = Depends(get_current_user)):
    """Send a test email to verify Resend configuration - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem testar email")
    
    if not RESEND_API_KEY:
        raise HTTPException(status_code=400, detail="RESEND_API_KEY não configurada. Configure no ficheiro .env")
    
    try:
        html_content = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #f97316; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">PDPV Tickets</h1>
            </div>
            <div style="padding: 20px; background-color: #f9fafb;">
                <h2 style="color: #1f2937;">Teste de Email Bem Sucedido!</h2>
                <p>Este é um email de teste do sistema PDPV Tickets.</p>
                <p>Se está a receber este email, a configuração do Resend está correta.</p>
                <div style="background-color: #d1fae5; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="color: #065f46; margin: 0;">✅ Configuração verificada com sucesso!</p>
                </div>
            </div>
            <div style="background-color: #1f2937; padding: 15px; text-align: center;">
                <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                    PDPV - Pneus de Pedro V.
                </p>
            </div>
        </div>
        """
        
        params = {
            "from": EMAIL_FROM,
            "to": [request.recipient_email],
            "subject": "[PDPV Tickets] Teste de Email",
            "html": html_content
        }
        
        email_result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"[RESEND TEST] Test email sent to {request.recipient_email}, ID: {email_result.get('id')}")
        
        return {
            "status": "success",
            "message": f"Email de teste enviado para {request.recipient_email}",
            "email_id": email_result.get("id")
        }
    except Exception as e:
        logger.error(f"[RESEND TEST] Failed to send test email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar email: {str(e)}")

@api_router.get("/admin/email-config")
async def get_email_config(current_user: dict = Depends(get_current_user)):
    """Get email configuration status - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração")
    
    return {
        "resend_configured": bool(RESEND_API_KEY),
        "email_from": EMAIL_FROM if RESEND_API_KEY else None
    }

# ============== PUBLIC QUOTE RESPONSE ==============
class QuoteResponseRequest(BaseModel):
    status: str  # ACCEPTED or REJECTED
    comments: Optional[str] = None

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
    
    if not ticket.get("quote_value"):
        raise HTTPException(status_code=400, detail="O ticket não tem valor de orçamento definido")
    
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
    
    # Update ticket
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "quote_sent": True,
            "quote_link_token": token,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
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
    
    # Send email with quote link automatically
    customer_email = ticket.get("customer_email")
    if customer_email and RESEND_API_KEY:
        try:
            # Get frontend URL from settings or use default
            email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
            frontend_url = email_settings.get("frontend_url", "https://pdpv-workshop.preview.emergentagent.com") if email_settings else "https://pdpv-workshop.preview.emergentagent.com"
            quote_link_url = f"{frontend_url}/quote/{token}"
            
            quote_value_formatted = f"{ticket['quote_value']:.2f}".replace('.', ',')
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #f97316; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">PDPV Tickets</h1>
                </div>
                <div style="padding: 20px; background-color: #f9fafb;">
                    <p>Olá <strong>{ticket['customer_name']}</strong>,</p>
                    <p>Preparámos um orçamento para si referente ao seu pedido.</p>
                    
                    <div style="background-color: #fff7ed; border: 2px solid #f97316; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                        <p style="color: #9a3412; font-size: 14px; margin: 0 0 10px 0;">VALOR DO ORÇAMENTO</p>
                        <p style="color: #f97316; font-size: 32px; font-weight: bold; margin: 0;">{quote_value_formatted} €</p>
                    </div>
                    
                    {f'<p><strong>Veículo:</strong> {ticket["vehicle_plate"]}</p>' if ticket.get('vehicle_plate') else ''}
                    {f'<p><strong>Descrição:</strong> {ticket["description"]}</p>' if ticket.get('description') else ''}
                    
                    <p style="margin-top: 20px;">Clique no botão abaixo para aceitar ou recusar este orçamento:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{quote_link_url}" style="background-color: #f97316; color: white; padding: 15px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Ver Orçamento
                        </a>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 12px; margin-top: 20px;">
                        Este link é válido até {expires_at.strftime('%d/%m/%Y')}.<br>
                        Referência do ticket: <strong>{ticket['ticket_number']}</strong>
                    </p>
                </div>
                <div style="background-color: #1f2937; padding: 15px; text-align: center;">
                    <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                        PDPV - Pneus de Pedro V. | Este é um email automático.
                    </p>
                </div>
            </div>
            """
            
            params = {
                "from": EMAIL_FROM,
                "to": [customer_email],
                "subject": f"[Ticket #{ticket['ticket_number']}] Orçamento - {quote_value_formatted}€",
                "html": html_content
            }
            
            email_result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"[RESEND] Quote link email sent to {customer_email}, ID: {email_result.get('id')}")
            
            # Log that email was sent
            email_note_doc = {
                "id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by_user_id": current_user["id"],
                "body": f"Email com link de orçamento enviado para {customer_email}",
                "is_system": True
            }
            await db.notes.insert_one(email_note_doc)
        except Exception as e:
            logger.error(f"[RESEND] Failed to send quote link email: {str(e)}")
    
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "link": f"/quote/{token}",
        "email_sent": bool(customer_email and RESEND_API_KEY)
    }

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
    
    return QuoteResponseData(
        ticket_number=ticket["ticket_number"],
        customer_name=ticket["customer_name"],
        vehicle_plate=ticket.get("vehicle_plate"),
        quote_value=ticket.get("quote_value", 0),
        description=ticket.get("description"),
        quote_sent_at=quote_link["created_at"],
        response_status=quote_link.get("response_status"),
        response_at=quote_link.get("response_at")
    )

@api_router.post("/public/quote/{token}/respond")
async def respond_to_quote(token: str, response_data: QuoteResponseRequest):
    """Client responds to a quote - NO AUTH REQUIRED"""
    quote_link = await db.quote_links.find_one({"token": token}, {"_id": 0})
    if not quote_link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    # Check if expired
    expires_at = datetime.fromisoformat(quote_link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Link expirado")
    
    # Check if already responded
    if quote_link.get("response_status"):
        raise HTTPException(status_code=400, detail="Já respondeu a este orçamento")
    
    if response_data.status not in ["ACCEPTED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Estado inválido")
    
    now = datetime.now(timezone.utc)
    
    # Update quote link
    await db.quote_links.update_one(
        {"token": token},
        {"$set": {
            "response_status": response_data.status,
            "response_at": now.isoformat(),
            "response_comments": response_data.comments
        }}
    )
    
    ticket = await db.tickets.find_one({"id": quote_link["ticket_id"]}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # Update ticket based on response
    ticket_update = {
        "updated_at": now.isoformat(),
        "quote_response_status": response_data.status,
        "quote_response_at": now.isoformat()
    }
    
    if response_data.status == "ACCEPTED":
        # Change status to EM_TRATAMENTO if accepted
        ticket_update["status"] = TicketStatus.EM_TRATAMENTO.value
    else:
        # Change status to FECHADO if rejected
        ticket_update["status"] = TicketStatus.FECHADO.value
    
    await db.tickets.update_one({"id": quote_link["ticket_id"]}, {"$set": ticket_update})
    
    # Log note
    status_text = "ACEITE" if response_data.status == "ACCEPTED" else "RECUSADO"
    note_body = f"Cliente respondeu ao orçamento: {status_text}"
    if response_data.comments:
        note_body += f"\nComentários: {response_data.comments}"
    
    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": quote_link["ticket_id"],
        "created_at": now.isoformat(),
        "created_by_user_id": "CLIENTE",
        "body": note_body,
        "is_system": True
    }
    await db.notes.insert_one(note_doc)
    
    # Notify assigned user and supervisors
    if ticket.get("assigned_to_user_id"):
        asyncio.create_task(create_notification(
            user_id=ticket["assigned_to_user_id"],
            title=f"Orçamento {status_text}",
            body=f"O cliente {ticket['customer_name']} {status_text.lower()} o orçamento do ticket {ticket['ticket_number']}",
            notification_type="success" if response_data.status == "ACCEPTED" else "warning",
            ticket_id=ticket["id"],
            ticket_number=ticket["ticket_number"]
        ))
    
    asyncio.create_task(notify_supervisors(
        title=f"Orçamento {status_text}",
        body=f"O cliente {ticket['customer_name']} {status_text.lower()} o orçamento do ticket {ticket['ticket_number']}",
        notification_type="success" if response_data.status == "ACCEPTED" else "warning",
        ticket_id=ticket["id"],
        ticket_number=ticket["ticket_number"]
    ))
    
    return {
        "status": "success",
        "message": f"Resposta registada: {status_text}"
    }

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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup"""
    # Start SLA check background task
    asyncio.create_task(run_sla_check())
    logger.info("[STARTUP] SLA background check started (runs every 15 minutes)")
