"""
Authentication routes module.
Contains endpoints for register, login, refresh, logout, and /me.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
import jwt

from db import db
from schemas.user import UserCreate, UserLogin, UserResponse
from core.security import (
    SECRET_KEY,
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from services.auth_service import (
    check_login_rate_limit,
    record_login_failure,
    clear_login_attempts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=dict)
async def register(user_data: UserCreate):
    """Register a new user."""
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
        "token_version": 0,
        "refresh_version": 0,
        "created_at": now
    }
    await db.users.insert_one(user_doc)
    
    access_token = create_access_token({"sub": user_id, "role": user_data.role.value}, 0)
    refresh_token = create_refresh_token({"sub": user_id}, 0, 0)
    return {
        "token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user_id,
            "email": user_data.email,
            "name": user_data.name,
            "role": user_data.role.value,
            "created_at": now
        }
    }


@router.post("/login", response_model=dict)
async def login(credentials: UserLogin, request: Request):
    """Login with email and password. Includes rate limiting and lockout."""
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Check rate limit
    allowed, message = await check_login_rate_limit(credentials.email, client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)
    
    # Validate credentials
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        # Record failure (don't reveal if user exists)
        await record_login_failure(credentials.email, client_ip)
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    # Success - clear attempts
    await clear_login_attempts(credentials.email, client_ip)
    
    # Get token versions (default 0 for existing users)
    token_version = user.get("token_version", 0)
    refresh_version = user.get("refresh_version", 0)
    
    # Create tokens
    access_token = create_access_token({"sub": user["id"], "role": user["role"]}, token_version)
    refresh_token = create_refresh_token({"sub": user["id"]}, token_version, refresh_version)
    
    logger.info(f"[AUTH] Successful login: {user['email']} from {client_ip}")
    
    return {
        "token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "created_at": user["created_at"]
        }
    }


@router.post("/refresh")
async def refresh_token_endpoint(request: Request):
    """Exchange refresh token for new access token with rotation."""
    body = await request.json()
    refresh_token_str = body.get("refresh_token")
    
    if not refresh_token_str:
        raise HTTPException(status_code=400, detail="Refresh token não fornecido")
    
    try:
        payload = jwt.decode(refresh_token_str, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Validate token type
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token inválido")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido")
        
        # Get user from DB
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Utilizador não encontrado")
        
        # Validate token_version (logout invalidation)
        token_version = payload.get("tv", 0)
        user_token_version = user.get("token_version", 0)
        if token_version != user_token_version:
            raise HTTPException(status_code=401, detail="Sessão inválida. Faça login novamente.")
        
        # Validate refresh_version (rotation check)
        refresh_version = payload.get("rv", 0)
        user_refresh_version = user.get("refresh_version", 0)
        if refresh_version != user_refresh_version:
            # Possible token reuse attack - invalidate all sessions
            logger.warning(f"[SECURITY] Refresh token reuse detected for user {user['email']}. Invalidating all sessions.")
            await db.users.update_one(
                {"id": user_id},
                {"$inc": {"token_version": 1, "refresh_version": 1}}
            )
            raise HTTPException(status_code=401, detail="Token já utilizado. Por segurança, faça login novamente.")
        
        # Rotate: increment refresh_version
        new_refresh_version = user_refresh_version + 1
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"refresh_version": new_refresh_version}}
        )
        
        # Issue new tokens with updated versions
        new_access_token = create_access_token({"sub": user["id"], "role": user["role"]}, user_token_version)
        new_refresh_token = create_refresh_token({"sub": user["id"]}, user_token_version, new_refresh_version)
        
        logger.info(f"[AUTH] Token refreshed for: {user['email']} (rv: {user_refresh_version} -> {new_refresh_version})")
        
        return {
            "token": new_access_token,
            "refresh_token": new_refresh_token
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expirado. Faça login novamente.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout - invalidates all tokens by incrementing token_version and refresh_version."""
    user_id = current_user["id"]
    
    await db.users.update_one(
        {"id": user_id},
        {"$inc": {"token_version": 1, "refresh_version": 1}}
    )
    
    logger.info(f"[AUTH] Logout: {current_user['email']} - all tokens invalidated")
    
    return {"status": "ok", "message": "Sessão terminada. Todos os dispositivos foram desconectados."}


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    return UserResponse(**user)
