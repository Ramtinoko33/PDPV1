"""
CRM Finance Module
Gestão operacional de cobranças baseada em dados importados do GENES/ERP

Este módulo é independente do sistema de tickets e clientes existente.
- GENES/ERP = fonte da verdade contabilística
- CRM Finance = fonte da verdade operacional de cobranças
"""
from .routes import router
from .models import FinanceRole, FinancialStatus, TrafficLight
from .permissions import (
    has_finance_access,
    is_finance_owner,
    is_finance_reviewer,
    is_collections_agent,
    require_finance_access,
    require_finance_reviewer,
    require_finance_owner,
    require_collections_agent,
)

__all__ = [
    "router",
    "FinanceRole",
    "FinancialStatus", 
    "TrafficLight",
    "has_finance_access",
    "is_finance_owner",
    "is_finance_reviewer",
    "is_collections_agent",
    "require_finance_access",
    "require_finance_reviewer",
    "require_finance_owner",
    "require_collections_agent",
]
