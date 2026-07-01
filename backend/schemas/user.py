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


class FinanceRole(str, Enum):
    """Roles específicos do módulo CRM Finance"""
    OWNER = "OWNER"
    FINANCE_REVIEWER = "FINANCE_REVIEWER"
    COLLECTIONS_AGENT = "COLLECTIONS_AGENT"


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
    finance_role: Optional[FinanceRole] = None  # CRM Finance module role
    created_at: str
    dashboard_default_types: List[str] = []
    dashboard_default_states: List[str] = []
    dashboard_only_mine: bool = False


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    finance_role: Optional[FinanceRole] = None  # CRM Finance module role
    password: Optional[str] = None


class DashboardConfigUpdate(BaseModel):
    dashboard_default_types: List[str] = []
    dashboard_default_states: List[str] = []
    dashboard_only_mine: bool = False
