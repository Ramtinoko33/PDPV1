"""
Ticket-related Pydantic schemas.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from enum import Enum


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
    ACEITE_LINK = "ACEITE_LINK"
    REJEITADO_LINK = "REJEITADO_LINK"
    AGENDADO = "AGENDADO"


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
    status: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    priority: Optional[TicketPriority] = None
    quote_sent: Optional[bool] = None
    quote_value: Optional[float] = None
    description: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None
    type: Optional[TicketType] = None


class TicketResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_number: str
    created_at: str
    updated_at: str
    channel: TicketChannel
    type: TicketType
    status: str
    priority: TicketPriority
    description: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None  # NEW: Name of who created the ticket
    customer_id: Optional[str] = None      # Link to customer
    vehicle_id: Optional[str] = None       # Link to vehicle
    last_public_message_at: Optional[str] = None
    first_response_done: bool = False
    sla_due: Optional[str] = None
    # New SLA fields
    sla_started_at: Optional[str] = None       # When SLA clock started (business hours)
    sla_paused_at: Optional[str] = None        # When SLA was paused (e.g., AGUARDA_CLIENTE)
    sla_paused_minutes: int = 0                # Total accumulated paused minutes
    sla_breached: bool = False                 # True if SLA was breached
    sla_breached_at: Optional[str] = None      # When breach occurred
    sla_target_minutes: Optional[int] = None   # Target minutes based on ticket type
    sla_policy_key: Optional[str] = None       # Policy identifier (e.g., SLA_ORCAMENTO_480min)
    # End new SLA fields
    quote_sent: bool = False
    quote_value: Optional[float] = None
    quote_response_status: Optional[str] = None
    quote_response_at: Optional[str] = None
    accepted_total: Optional[float] = None
    accepted_count: Optional[int] = None
    quote_valid_until: Optional[str] = None
    quote_locked_at: Optional[str] = None
    quote_decided_at: Optional[str] = None
    quote_decision: Optional[str] = None
    reply_link_token: Optional[str] = None
    is_overdue: bool = False
    archived_at: Optional[str] = None
    archived_by: Optional[str] = None
    creator_can_edit: bool = False
    # Rejection reason fields
    rejection_reason_code: Optional[str] = None
    rejection_reason_label: Optional[str] = None
    rejection_reason_note: Optional[str] = None
    rejected_at: Optional[str] = None
    rejected_via: Optional[str] = None
    # Intake traceability
    intake_request_id: Optional[str] = None
    intake_source: Optional[str] = None
    intake_source_type: Optional[str] = None
    telegram_username: Optional[str] = None


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
    is_quote_response: bool = False
    attachment_ids: List[str] = []


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
    from_customer: bool = False


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


class ReminderCreate(BaseModel):
    description: str
    due_at: str
    assigned_to_user_id: Optional[str] = None
    ticket_id: Optional[str] = None


class ReminderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ticket_id: Optional[str] = None
    ticket_number: Optional[str] = None
    description: str
    due_at: str
    assigned_to_user_id: str
    assigned_to_name: Optional[str] = None
    is_done: bool = False
    is_overdue: bool = False
    created_by_user_id: str
    created_by_name: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


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


class DashboardStats(BaseModel):
    novos: int = 0
    atrasados_sla: int = 0
    aguarda_cliente: int = 0
    em_tratamento: int = 0
    total: int = 0
