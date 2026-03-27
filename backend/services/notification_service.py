"""
Notification Service Module.
Contains functions for web push notifications and in-app notifications.
"""
import logging
import uuid
import asyncio
import json
import os
from datetime import datetime, timezone

from db import db
from schemas.user import UserRole

logger = logging.getLogger(__name__)

# VAPID Config for Web Push
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '').strip().strip('"').strip("'")
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '').strip().strip('"').strip("'")
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@pdpv.pt').strip().strip('"').strip("'")
VAPID_KEYS_VALID = False


def set_vapid_keys_valid(valid: bool):
    """Set VAPID keys validity status."""
    global VAPID_KEYS_VALID
    VAPID_KEYS_VALID = valid


def get_vapid_keys_valid() -> bool:
    """Get VAPID keys validity status."""
    return VAPID_KEYS_VALID


def set_vapid_keys(public_key: str, private_key: str):
    """Set VAPID keys."""
    global VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY
    VAPID_PUBLIC_KEY = public_key
    VAPID_PRIVATE_KEY = private_key


def get_vapid_public_key() -> str:
    """Get VAPID public key."""
    return VAPID_PUBLIC_KEY


async def send_web_push_to_user(user_id: str, title: str, body: str, url: str = None):
    """Send web push notification to all devices of a user"""
    from pywebpush import webpush, WebPushException
    
    # Check if VAPID keys are valid before attempting to send
    if not VAPID_KEYS_VALID:
        return  # Silently skip if keys not valid
    
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return
    
    try:
        subscriptions = await db.push_subscriptions.find(
            {"user_id": user_id}
        ).to_list(100)
        
        if not subscriptions:
            return
        
        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/logo192.png",
            "badge": "/logo192.png",
            "url": url or "/"
        })
        
        for sub in subscriptions:
            try:
                # Validate subscription has required fields
                if not sub.get("endpoint") or not sub.get("keys"):
                    logger.warning(f"Invalid subscription format for user {user_id}, removing")
                    await db.push_subscriptions.delete_one({"_id": sub.get("_id")})
                    continue
                
                # Skip invalid endpoints
                endpoint = sub["endpoint"]
                if "permanently-removed" in endpoint or "invalid" in endpoint or not endpoint.startswith("https://"):
                    logger.warning(f"Invalid endpoint for user {user_id}, removing subscription")
                    await db.push_subscriptions.delete_one({"endpoint": endpoint})
                    continue
                    
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": sub["keys"]
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"}
                )
                logger.info(f"Web push sent to user {user_id}")
            except WebPushException as e:
                # Get response status code safely
                status_code = getattr(e.response, 'status_code', None) if e.response else None
                
                # If subscription is expired/invalid (400, 404, 410), remove it silently
                if status_code in [400, 404, 410]:
                    await db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                    logger.debug(f"Removed invalid/expired subscription for user {user_id} (HTTP {status_code})")
                elif e.response is None or status_code is None:
                    await db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                    logger.debug(f"Removed unreachable subscription for user {user_id}")
                else:
                    if status_code and status_code >= 500:
                        logger.warning(f"Web push server error for user {user_id}: HTTP {status_code}")
                    else:
                        logger.debug(f"Web push failed for user {user_id}: HTTP {status_code}")
            except ValueError as e:
                logger.warning(f"VAPID key format error, web push disabled: {e}")
                return
            except Exception as e:
                error_str = str(e)
                if "permanently-removed" in error_str or "NameResolutionError" in error_str:
                    await db.push_subscriptions.delete_one({"endpoint": sub.get("endpoint", "")})
                    logger.debug(f"Removed invalid subscription for user {user_id}")
                else:
                    logger.warning(f"Web push error for user {user_id}: {type(e).__name__}")
                continue
    except Exception as e:
        logger.error(f"Web push task error for user {user_id}: {e}")


async def create_notification(
    user_id: str, 
    title: str, 
    body: str, 
    notification_type: str = "info", 
    ticket_id: str = None, 
    ticket_number: str = None,
    websocket_manager = None
):
    """Create and send notification to a user."""
    now = datetime.now(timezone.utc)
    notification_id = str(uuid.uuid4())
    
    notification_doc = {
        "id": notification_id,
        "user_id": user_id,
        "title": title,
        "body": body,
        "type": notification_type,
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "read": False
    }
    await db.notifications.insert_one(notification_doc)
    
    # Send via WebSocket if manager is provided
    if websocket_manager:
        await websocket_manager.send_to_user(user_id, {
            "type": "notification",
            "data": notification_doc
        })
    
    # Send via Web Push (in background to not block)
    url = f"/tickets/{ticket_id}" if ticket_id else "/"
    asyncio.create_task(send_web_push_to_user(user_id, title, body, url))
    
    return notification_doc


async def notify_supervisors(
    title: str, 
    body: str, 
    notification_type: str = "info", 
    ticket_id: str = None, 
    ticket_number: str = None,
    websocket_manager = None
):
    """Send notification to all supervisors and admins."""
    supervisors = await db.users.find(
        {"role": {"$in": [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]}},
        {"_id": 0, "id": 1}
    ).to_list(100)
    
    for sup in supervisors:
        await create_notification(
            sup["id"], 
            title, 
            body, 
            notification_type, 
            ticket_id, 
            ticket_number,
            websocket_manager
        )
