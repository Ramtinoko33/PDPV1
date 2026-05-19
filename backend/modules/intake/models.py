"""
Intake Module - Models
Pydantic models for intake requests.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any, Dict
from enum import Enum


class IntakeStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    CONVERTED = "CONVERTED"
    REJECTED = "REJECTED"


class IntakeSourceType(str, Enum):
    MANUAL = "manual"
    BOT_TELEGRAM = "bot_telegram"
    # Discriminator for the new PDPV internal Telegram bot (open-flow pre-ticket with AI)
    TELEGRAM_INTERNAL_BOT = "telegram_internal_bot"
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
    attachments: List[Any] = []


class IntakeRequestUpdate(BaseModel):
    sender_name: Optional[str] = None
    sender_contact: Optional[str] = None
    raw_text: Optional[str] = None
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    status: Optional[IntakeStatus] = None
    # Allow editing AI-extracted fields and validation metadata
    ai_extracted: Optional[Dict[str, Any]] = None
    validated_by: Optional[str] = None


class IntakeRequestResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    source: str
    source_type: IntakeSourceType = IntakeSourceType.MANUAL
    # New discriminators for distinguishing between bots/origins
    source_bot: Optional[str] = None          # e.g., "PDPV_INTERNAL_BOT", "PDPV_OFICINA_BOT"
    origin_channel: Optional[str] = None      # e.g., "TELEGRAM_INTERNAL_BOT", "WEB_FORM"
    reference: Optional[str] = None           # short human-friendly reference (e.g., PT20260219ABCDE)
    sender_name: Optional[str] = ""           # Customer/driver name (may be empty when AI cannot identify it)
    sender_contact: Optional[str] = ""        # Customer phone (may be empty)
    sender_email: Optional[str] = None
    telegram_username: Optional[str] = None
    raw_text: str = ""
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    # attachments may be a list of legacy strings (URLs) OR new structured objects
    attachments: List[Any] = []
    status: IntakeStatus
    created_at: str
    updated_at: Optional[str] = None
    # Review fields
    review_notes: List[ReviewNote] = []
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    # Conversion tracking
    converted_ticket_id: Optional[str] = None
    converted_ticket_number: Optional[str] = None
    converted_at: Optional[str] = None
    converted_by: Optional[str] = None
    # Analysis tracking (legacy single-image vision pipeline)
    analysis_status: Optional[str] = None
    analysis_error: Optional[str] = None
    raw_vision_output: Optional[str] = None
    # Extra vehicle data
    vehicle_brand: Optional[str] = None
    vehicle_model: Optional[str] = None
    # ====== Open-flow AI extraction (new internal bot) ======
    # Internal employee that created the pre-ticket (Telegram operator, etc.)
    created_by_name: Optional[str] = None
    telegram_user_id: Optional[int] = None
    telegram_chat_id: Optional[int] = None
    # Accumulated raw inputs (may be missing on legacy/single-message records)
    texts: List[str] = []
    audio_transcripts: List[str] = []
    image_hints: List[str] = []
    # Structured fields extracted by GPT-4o
    ai_extracted: Optional[Dict[str, Any]] = None
    validated_by: Optional[str] = None


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
