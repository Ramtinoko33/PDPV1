"""
Telegram Module Models
Pydantic models for Telegram integration.
"""
from pydantic import BaseModel
from typing import Optional, List


class TelegramUser(BaseModel):
    """Telegram user information."""
    id: int
    is_bot: bool = False
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None


class TelegramChat(BaseModel):
    """Telegram chat information."""
    id: int
    type: str  # private, group, supergroup, channel
    title: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class TelegramPhoto(BaseModel):
    """Telegram photo size."""
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: Optional[int] = None


class TelegramDocument(BaseModel):
    """Telegram document."""
    file_id: str
    file_unique_id: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None


class TelegramVoice(BaseModel):
    """Telegram voice message."""
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: Optional[str] = None
    file_size: Optional[int] = None


class TelegramAudio(BaseModel):
    """Telegram audio file."""
    file_id: str
    file_unique_id: str
    duration: int
    performer: Optional[str] = None
    title: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None


class TelegramMessage(BaseModel):
    """Telegram message."""
    message_id: int
    date: int
    chat: TelegramChat
    from_user: Optional[TelegramUser] = None
    text: Optional[str] = None
    photo: Optional[List[TelegramPhoto]] = None
    document: Optional[TelegramDocument] = None
    voice: Optional[TelegramVoice] = None
    audio: Optional[TelegramAudio] = None
    caption: Optional[str] = None
    
    class Config:
        populate_by_name = True
        
    def __init__(self, **data):
        # Handle 'from' field which is a reserved keyword in Python
        if 'from' in data:
            data['from_user'] = data.pop('from')
        super().__init__(**data)


class TelegramUpdate(BaseModel):
    """Telegram webhook update."""
    update_id: int
    message: Optional[TelegramMessage] = None


class ExtractedInfo(BaseModel):
    """Information extracted from message using AI."""
    license_plate: Optional[str] = None
    tire_size: Optional[str] = None
    service_type: Optional[str] = None
    urgency: Optional[str] = None
    summary: Optional[str] = None


class WebhookSetupRequest(BaseModel):
    """Request to setup webhook."""
    webhook_url: str
