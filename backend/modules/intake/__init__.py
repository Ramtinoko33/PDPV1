"""
Intake Module
Handles incoming requests from various sources before converting to tickets.
"""
from .routes import router
from .models import IntakeRequestCreate, IntakeRequestResponse, IntakeStatus
from . import service

__all__ = [
    "router",
    "IntakeRequestCreate",
    "IntakeRequestResponse", 
    "IntakeStatus",
    "service"
]
