"""Notification helpers shared between server.py and route modules.

Extracted to break the circular dependency:
    server.py → routes/tickets.py → server.py (notify_supervisors / create_notification)

Now: routes/tickets.py imports directly from core.notifications.
"""
import uuid
import asyncio
from datetime import datetime, timezone

from db import db
from core.websocket_manager import manager
from services.notification_service import send_web_push_to_user


async def create_notification(
    user_id: str,
    title: str,
    body: str,
    notification_type: str = "info",
    ticket_id: str = None,
    ticket_number: str = None,
):
    """Persist a notification, push it via WebSocket and Web Push."""
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
        "read": False,
    }
    await db.notifications.insert_one(notification_doc)

    # WebSocket push
    await manager.send_to_user(user_id, {
        "type": "notification",
        "data": notification_doc,
    })

    # Web Push (fire-and-forget)
    url = f"/tickets/{ticket_id}" if ticket_id else "/"
    asyncio.create_task(send_web_push_to_user(user_id, title, body, url))

    return notification_doc


async def notify_supervisors(
    title: str,
    body: str,
    notification_type: str = "info",
    ticket_id: str = None,
    ticket_number: str = None,
):
    """Send a notification to every active supervisor and admin."""
    # Local import avoids requiring schemas at module load
    from schemas.user import UserRole

    supervisors = await db.users.find(
        {"role": {"$in": [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]}},
        {"_id": 0, "id": 1},
    ).to_list(100)

    for sup in supervisors:
        await create_notification(
            sup["id"], title, body, notification_type, ticket_id, ticket_number
        )
