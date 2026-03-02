"""
Routes package - API endpoints organized by domain.
"""
from .auth import router as auth_router
from .customers import router as customers_router
from .users import router as users_router
from .vehicles import router as vehicles_router

__all__ = [
    "auth_router",
    "customers_router",
    "users_router",
    "vehicles_router",
]
