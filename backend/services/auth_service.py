"""
Authentication service module.
Contains rate limiting and login attempt tracking logic.
"""
import logging
from datetime import datetime, timezone, timedelta

from db import db

logger = logging.getLogger(__name__)


async def check_login_rate_limit(email: str, client_ip: str) -> tuple[bool, str]:
    """
    Check if login attempt is allowed.
    Returns (allowed: bool, message: str)
    """
    key = f"{email.lower().strip()}|{client_ip}"
    now = datetime.now(timezone.utc)
    
    attempt = await db.auth_login_attempts.find_one({"key": key}, {"_id": 0})
    
    if attempt:
        # Check if currently locked
        if attempt.get("locked_until"):
            locked_until = datetime.fromisoformat(attempt["locked_until"].replace("Z", "+00:00"))
            if now < locked_until:
                remaining = int((locked_until - now).total_seconds() / 60) + 1
                return False, f"Demasiadas tentativas. Tente novamente em {remaining} minutos."
        
        # Check if window has passed (15 min) - reset if so
        first_attempt = datetime.fromisoformat(attempt["first_attempt_at"].replace("Z", "+00:00"))
        if (now - first_attempt).total_seconds() > 15 * 60:
            # Reset the attempt counter
            await db.auth_login_attempts.update_one(
                {"key": key},
                {"$set": {
                    "attempts": 0,
                    "first_attempt_at": now.isoformat(),
                    "locked_until": None,
                    "updated_at": now.isoformat()
                }}
            )
    
    return True, ""


async def record_login_failure(email: str, client_ip: str) -> None:
    """Record a failed login attempt and lock if threshold exceeded."""
    key = f"{email.lower().strip()}|{client_ip}"
    now = datetime.now(timezone.utc)
    
    attempt = await db.auth_login_attempts.find_one({"key": key}, {"_id": 0})
    
    if not attempt:
        # First attempt
        await db.auth_login_attempts.insert_one({
            "key": key,
            "attempts": 1,
            "first_attempt_at": now.isoformat(),
            "locked_until": None,
            "updated_at": now.isoformat()
        })
    else:
        new_attempts = attempt.get("attempts", 0) + 1
        update_doc = {
            "attempts": new_attempts,
            "updated_at": now.isoformat()
        }
        
        # Lock if 5+ failed attempts
        if new_attempts >= 5:
            update_doc["locked_until"] = (now + timedelta(minutes=15)).isoformat()
            logger.warning(f"[SECURITY] Login locked for key: {key[:20]}... after {new_attempts} attempts")
        
        await db.auth_login_attempts.update_one(
            {"key": key},
            {"$set": update_doc}
        )


async def clear_login_attempts(email: str, client_ip: str) -> None:
    """Clear login attempts on successful login."""
    key = f"{email.lower().strip()}|{client_ip}"
    await db.auth_login_attempts.delete_one({"key": key})
