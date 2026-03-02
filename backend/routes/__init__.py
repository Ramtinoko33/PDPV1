"""
Routes package - API endpoints organized by domain.
"""
from .auth import router as auth_router

__all__ = [
    "auth_router",
]
