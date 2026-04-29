"""
User management routes (Admin).
"""
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from db import db
from schemas.user import UserRole, UserCreate, UserUpdate, UserResponse, DashboardConfigUpdate
from core.security import get_current_user, hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[UserResponse])
async def list_users(user: dict = Depends(get_current_user)):
    """List all users (admin/supervisor only)."""
    if user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        # Allow agents with can_create_tickets to list users (for assignment)
        if not user.get("can_create_tickets"):
            raise HTTPException(status_code=403, detail="Acesso negado")
    
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]


@router.post("", response_model=UserResponse)
async def create_user(user_data: UserCreate, current_user: dict = Depends(get_current_user)):
    """Create a new user (admin only)."""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem criar utilizadores")
    
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    user_id = str(uuid.uuid4())
    hashed_password = hash_password(user_data.password)
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "password_hash": hashed_password,
        "name": user_data.name,
        "role": user_data.role.value,
        "created_at": now
    }
    await db.users.insert_one(user_doc)
    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password_hash"})


@router.put("/me/dashboard", response_model=UserResponse)
async def update_my_dashboard_config(data: DashboardConfigUpdate, current_user: dict = Depends(get_current_user)):
    """Update current user's dashboard configuration."""
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {
            "dashboard_default_types": data.dashboard_default_types,
            "dashboard_default_states": data.dashboard_default_states,
            "dashboard_only_mine": data.dashboard_only_mine
        }}
    )
    updated_user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    return UserResponse(**updated_user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    """Update a user (admin only)."""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem editar utilizadores")
    
    update_doc = {}
    if user_data.name:
        update_doc["name"] = user_data.name
    if user_data.role:
        update_doc["role"] = user_data.role.value
    if user_data.password:
        update_doc["password_hash"] = hash_password(user_data.password)
    if user_data.has_alerts_access is not None:
        update_doc["has_alerts_access"] = user_data.has_alerts_access
    if user_data.can_create_tickets is not None:
        update_doc["can_create_tickets"] = user_data.can_create_tickets
    
    if update_doc:
        await db.users.update_one({"id": user_id}, {"$set": update_doc})
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return UserResponse(**user)


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a user (admin only)."""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem eliminar utilizadores")
    
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return {"message": "Utilizador eliminado"}
