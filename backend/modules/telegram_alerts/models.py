"""
Telegram Alerts Module - Data Models
"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class AlertStatus(str, Enum):
    PENDING = "pending"
    CONVERTED = "converted"
    DISMISSED = "dismissed"


class AlertAttachment(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int = 0
    storage_path: Optional[str] = None
    telegram_file_id: Optional[str] = None
    base64_data: Optional[str] = None


class AlertCreatedBy(BaseModel):
    source: str = "telegram"
    chat_id: int
    user_id: int
    username: Optional[str] = None
    name: str


class AlertResponse(BaseModel):
    id: str
    source: str = "telegram_alerts"
    status: str = "pending"
    license_plate: Optional[str] = None
    client_name: Optional[str] = None
    items: List[str] = []
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by: dict = {}
    telegram_chat_id: int = 0
    attachments: List[dict] = []
    extraction_failed: bool = False
    raw_text: Optional[str] = None
    raw_vision_output: Optional[str] = None
    converted: bool = False
    ticket_id: Optional[str] = None
    ticket_number: Optional[str] = None
    created_at: str = ""
    updated_at: Optional[str] = None
    converted_at: Optional[str] = None


class AlertUpdate(BaseModel):
    license_plate: Optional[str] = None
    client_name: Optional[str] = None
    items: Optional[List[str]] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None


class AlertConvertRequest(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    vehicle_plate: Optional[str] = None
    ticket_type: str = "ORCAMENTO_MECANICA"
    description: Optional[str] = None
    assigned_to: Optional[str] = None
