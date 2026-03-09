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


class IntakeRequestCreate(BaseModel):
    source: str  # telegram, whatsapp, email, web_form
    sender_name: str
    sender_contact: str
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
    sender_name: str
    sender_contact: str
    raw_text: str
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    attachments: List[str] = []
    status: IntakeStatus
    created_at: str
    converted_ticket_id: Optional[str] = None
    converted_at: Optional[str] = None


class ConvertToTicketRequest(BaseModel):
    customer_name: Optional[str] = None  # Override sender_name
    customer_phone: Optional[str] = None  # Override sender_contact
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None  # Override license_plate
    ticket_type: str = "INFORMACAO"
    description: Optional[str] = None  # Override raw_text
