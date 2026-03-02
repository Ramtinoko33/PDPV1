"""
Schemas package - Pydantic models for request/response validation.
"""
from .user import (
    UserRole,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    DashboardConfigUpdate,
)

from .ticket import (
    TicketChannel,
    TicketType,
    TicketStatus,
    TicketPriority,
    MessageDirection,
    MessageChannel,
    AlertType,
    TicketCreate,
    TicketUpdate,
    TicketResponse,
    TicketStatusHistoryResponse,
    MessageCreate,
    MessageResponse,
    NoteCreate,
    NoteResponse,
    AlertResponse,
    ReminderCreate,
    ReminderResponse,
    AttachmentResponse,
    DashboardStats,
)

from .customer import (
    VehicleCreate,
    VehicleResponse,
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerSearchResult,
    WhatsAppWebhook,
    TelegramWebhook,
)

__all__ = [
    # User
    "UserRole",
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "DashboardConfigUpdate",
    # Ticket
    "TicketChannel",
    "TicketType",
    "TicketStatus",
    "TicketPriority",
    "MessageDirection",
    "MessageChannel",
    "AlertType",
    "TicketCreate",
    "TicketUpdate",
    "TicketResponse",
    "TicketStatusHistoryResponse",
    "MessageCreate",
    "MessageResponse",
    "NoteCreate",
    "NoteResponse",
    "AlertResponse",
    "ReminderCreate",
    "ReminderResponse",
    "AttachmentResponse",
    "DashboardStats",
    # Customer
    "VehicleCreate",
    "VehicleResponse",
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    "CustomerSearchResult",
    "WhatsAppWebhook",
    "TelegramWebhook",
]
