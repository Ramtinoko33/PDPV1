"""
WhatsApp Business Cloud API - Models
"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class WhatsAppMessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    LOCATION = "location"
    CONTACTS = "contacts"
    STICKER = "sticker"
    INTERACTIVE = "interactive"
    BUTTON = "button"
    UNKNOWN = "unknown"


class TicketMessageDirection(str, Enum):
    INBOUND = "inbound"    # From customer
    OUTBOUND = "outbound"  # To customer


class TicketMessageCreate(BaseModel):
    """Model for creating a ticket message"""
    ticket_id: str
    body: str
    direction: TicketMessageDirection = TicketMessageDirection.INBOUND
    message_type: str = "text"
    external_message_id: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_name: Optional[str] = None


class TicketMessageResponse(BaseModel):
    """Response model for ticket message"""
    id: str
    ticket_id: str
    body: str
    direction: str
    message_type: str
    external_message_id: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_name: Optional[str] = None
    created_at: str
    created_by_user_id: Optional[str] = None


# WhatsApp Cloud API Webhook Models
class WhatsAppTextContent(BaseModel):
    body: str


class WhatsAppMediaContent(BaseModel):
    id: str
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    caption: Optional[str] = None
    filename: Optional[str] = None


class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message from webhook"""
    from_: str  # Phone number
    id: str     # Message ID
    timestamp: str
    type: str
    text: Optional[WhatsAppTextContent] = None
    image: Optional[WhatsAppMediaContent] = None
    document: Optional[WhatsAppMediaContent] = None
    audio: Optional[WhatsAppMediaContent] = None
    video: Optional[WhatsAppMediaContent] = None
    
    class Config:
        populate_by_name = True
        fields = {'from_': 'from'}


class WhatsAppContact(BaseModel):
    """WhatsApp contact info"""
    profile: Optional[dict] = None
    wa_id: str


class WhatsAppMetadata(BaseModel):
    display_phone_number: str
    phone_number_id: str


class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: WhatsAppMetadata
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[dict]] = None
    statuses: Optional[List[dict]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    """Full webhook payload from WhatsApp Cloud API"""
    object: str
    entry: List[WhatsAppEntry]
