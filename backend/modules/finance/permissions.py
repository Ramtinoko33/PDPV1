"""
CRM Finance Module - Permission Guards
Decorators e funções para verificar permissões do módulo financeiro
"""
import logging
from functools import wraps
from fastapi import HTTPException, Depends
from typing import List, Optional, Callable

from core.security import get_current_user
from .models import FinanceRole

logger = logging.getLogger(__name__)


def get_finance_role(user: dict) -> Optional[FinanceRole]:
    """Extrai o finance_role do utilizador"""
    role_str = user.get("finance_role")
    if not role_str:
        return None
    try:
        return FinanceRole(role_str)
    except ValueError:
        return None


def has_finance_access(user: dict) -> bool:
    """Verifica se o utilizador tem acesso ao módulo financeiro"""
    return get_finance_role(user) is not None


def is_finance_owner(user: dict) -> bool:
    """Verifica se é OWNER"""
    return get_finance_role(user) == FinanceRole.OWNER


def is_finance_reviewer(user: dict) -> bool:
    """Verifica se é FINANCE_REVIEWER ou superior"""
    role = get_finance_role(user)
    return role in [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER]


def is_collections_agent(user: dict) -> bool:
    """Verifica se é COLLECTIONS_AGENT ou superior"""
    role = get_finance_role(user)
    return role in [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT]


def can_approve_imports(user: dict) -> bool:
    """Pode aprovar importações críticas"""
    return is_finance_reviewer(user)


def can_manage_blocks(user: dict) -> bool:
    """Pode bloquear/desbloquear clientes"""
    return is_finance_reviewer(user)


def can_approve_block_requests(user: dict) -> bool:
    """Pode aprovar/rejeitar pedidos de bloqueio"""
    return is_finance_reviewer(user)


def can_suggest_block(user: dict) -> bool:
    """Pode sugerir bloqueio"""
    return is_collections_agent(user)


def can_register_actions(user: dict) -> bool:
    """Pode registar contactos e ações"""
    return is_collections_agent(user)


def can_create_promises(user: dict) -> bool:
    """Pode criar promessas de pagamento"""
    return is_collections_agent(user)


def can_view_audit(user: dict) -> bool:
    """Pode ver auditoria"""
    return is_finance_reviewer(user)


def can_edit_settings(user: dict) -> bool:
    """Pode editar configurações"""
    return is_finance_owner(user)


# ============== FASTAPI DEPENDENCIES ==============

async def require_finance_access(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency que requer acesso ao módulo financeiro.
    Uso: current_user: dict = Depends(require_finance_access)
    """
    if not has_finance_access(current_user):
        logger.warning(f"User {current_user.get('id')} attempted finance access without permission")
        raise HTTPException(
            status_code=403,
            detail="Não tem permissão para aceder ao módulo financeiro"
        )
    return current_user


async def require_finance_reviewer(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency que requer FINANCE_REVIEWER ou OWNER.
    """
    if not is_finance_reviewer(current_user):
        raise HTTPException(
            status_code=403,
            detail="Esta ação requer permissão de FINANCE_REVIEWER ou superior"
        )
    return current_user


async def require_finance_owner(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency que requer OWNER.
    """
    if not is_finance_owner(current_user):
        raise HTTPException(
            status_code=403,
            detail="Esta ação requer permissão de OWNER"
        )
    return current_user


async def require_collections_agent(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency que requer COLLECTIONS_AGENT ou superior.
    """
    if not is_collections_agent(current_user):
        raise HTTPException(
            status_code=403,
            detail="Esta ação requer permissão de COLLECTIONS_AGENT ou superior"
        )
    return current_user


# ============== PERMISSION MATRIX ==============

PERMISSION_MATRIX = {
    # Ação: [Roles permitidos]
    "view_dashboard": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_collections": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_clients": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_client_detail": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_regularizations": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_imports": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_promises": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "view_block_requests": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    "view_audit": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    "view_settings": [FinanceRole.OWNER],
    
    "upload_import": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "approve_import": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    
    "register_action": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "create_promise": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "update_promise": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    
    "mark_dispute": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "mark_payment_plan": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    
    "suggest_block": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER, FinanceRole.COLLECTIONS_AGENT],
    "approve_block": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    "reject_block": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    "block_client": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    "unblock_client": [FinanceRole.OWNER, FinanceRole.FINANCE_REVIEWER],
    
    "edit_settings": [FinanceRole.OWNER],
}


def check_permission(user: dict, action: str) -> bool:
    """
    Verifica se o utilizador tem permissão para uma ação específica.
    """
    role = get_finance_role(user)
    if role is None:
        return False
    
    allowed_roles = PERMISSION_MATRIX.get(action, [])
    return role in allowed_roles
