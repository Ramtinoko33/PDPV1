"""
User-related Pydantic schemas.
"""
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import List, Optional
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    AGENT = "AGENT"
    INTERNAL_CREATOR = "INTERNAL_CREATOR"


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole = UserRole.AGENT


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: UserRole
    created_at: str
    dashboard_default_types: List[str] = []
    dashboard_default_states: List[str] = []
    dashboard_only_mine: bool = False
    has_alerts_access: bool = False
    can_create_tickets: bool = False


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None
    has_alerts_access: Optional[bool] = None
    can_create_tickets: Optional[bool] = None


class DashboardConfigUpdate(BaseModel):
    dashboard_default_types: List[str] = []
    dashboard_default_states: List[str] = []
    dashboard_only_mine: bool = False
