"""
Core security module.
Contains JWT token creation/validation, password hashing, and authentication dependencies.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import Header, HTTPException
from passlib.context import CryptContext
import jwt

from db import db

logger = logging.getLogger(__name__)

# JWT Config - SECURITY: prefer env var, fallback to auto-generated persistent secret.
# In production we MUST NOT crash if JWT_SECRET is missing — the deployment probe
# would receive Connection Refused and the pod would never become Ready.
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    # Try persistent file fallback (survives container restarts in the same volume)
    import secrets
    from pathlib import Path
    _fallback_path = Path("/app/backend/.jwt_secret")
    try:
        if _fallback_path.exists():
            JWT_SECRET = _fallback_path.read_text().strip()
        if not JWT_SECRET:
            JWT_SECRET = secrets.token_urlsafe(64)
            try:
                _fallback_path.write_text(JWT_SECRET)
            except Exception:
                pass
        logger.warning(
            "[SECURITY] JWT_SECRET env var not set — using auto-generated fallback. "
            "Set JWT_SECRET in production for stronger guarantees across pod restarts."
        )
    except Exception:
        JWT_SECRET = secrets.token_urlsafe(64)
        logger.warning("[SECURITY] JWT_SECRET fallback file unavailable — using in-memory secret.")

SECRET_KEY = JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 2  # Short-lived access token
REFRESH_TOKEN_EXPIRE_DAYS = 14  # Long-lived refresh token

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: dict, token_version: int = 0) -> str:
    """Create a short-lived JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({
        "exp": expire,
        "iat": int(now.timestamp()),
        "tv": token_version,
        "type": "access"
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, token_version: int = 0, refresh_version: int = 0) -> str:
    """Create a long-lived JWT refresh token with rotation support."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": int(now.timestamp()),
        "tv": token_version,
        "rv": refresh_version,
        "type": "refresh"
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(authorization: str = Header(None)) -> dict:
    """
    FastAPI dependency to extract and validate the current user from JWT token.
    Validates token type, expiration, and version against the database.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Token não fornecido")
    try:
        token = authorization
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check token type
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token inválido")
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="Utilizador não encontrado")
        
        # Validate token_version
        token_version = payload.get("tv", 0)
        user_token_version = user.get("token_version", 0)
        if token_version != user_token_version:
            raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
        
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)
