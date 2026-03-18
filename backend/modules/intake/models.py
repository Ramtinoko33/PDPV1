"""
Intake Module - Models
Pydantic models for intake requests.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from enum import Enum


class IntakeStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    CONVERTED = "CONVERTED"
    REJECTED = "REJECTED"


class IntakeSourceType(str, Enum):
    MANUAL = "manual"
    BOT_TELEGRAM = "bot_telegram"
    BOT_WHATSAPP = "bot_whatsapp"
    API = "api"
    IMPORT = "import"


class ReviewNote(BaseModel):
    """A single review note with author and timestamp."""
    note: str
    author_id: str
    author_name: str
    created_at: str


class ReviewNoteCreate(BaseModel):
    """Input for creating a review note."""
    note: str


class IntakeRequestCreate(BaseModel):
    source: str  # telegram, whatsapp, email, web_form, telefone, manual
    source_type: IntakeSourceType = IntakeSourceType.MANUAL
    sender_name: str
    sender_contact: str  # Phone number (NOT telegram username)
    sender_email: Optional[str] = None
    telegram_username: Optional[str] = None  # Telegram username stored separately
    raw_text: str
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    attachments: List[str] = []


class IntakeRequestUpdate(BaseModel):
    sender_name: Optional[str] = None
    sender_contact: Optional[str] = None
    raw_text: Optional[str] = None
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    status: Optional[IntakeStatus] = None


class IntakeRequestResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    source: str
    source_type: IntakeSourceType = IntakeSourceType.MANUAL
    sender_name: str
    sender_contact: str  # Phone number
    sender_email: Optional[str] = None
    telegram_username: Optional[str] = None
    raw_text: str
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    attachments: List[str] = []
    status: IntakeStatus
    created_at: str
    # Review fields
    review_notes: List[ReviewNote] = []
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    # Conversion tracking
    converted_ticket_id: Optional[str] = None
    converted_ticket_number: Optional[str] = None
    converted_at: Optional[str] = None
    converted_by: Optional[str] = None


class ConvertToTicketRequest(BaseModel):
    customer_name: Optional[str] = None  # Override sender_name
    customer_phone: Optional[str] = None  # Override sender_contact
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None  # Override license_plate
    ticket_type: str = "INFORMACAO"
    description: Optional[str] = None  # Override raw_text
    assigned_to: Optional[str] = None  # User ID to assign ticket to


class IntakeListResponse(BaseModel):
    """Response for paginated intake list."""
    items: List[IntakeRequestResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
