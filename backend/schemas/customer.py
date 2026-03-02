"""
Customer and Vehicle related Pydantic schemas.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional


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
