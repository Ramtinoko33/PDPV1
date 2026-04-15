"""
Telegram Alerts Module - Service Layer
Handles: message buffering, image processing, alert CRUD, Telegram bot interaction.
"""
import os
import re
import json
import uuid
import base64
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple

import httpx

from db import db
from .models import AlertStatus

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_ALERTS_BOT_TOKEN", "")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
TELEGRAM_API = "https://api.telegram.org/bot"

BUFFER_TIMEOUT_SECONDS = 10
MAX_MESSAGES_PER_MIN = 10
MAX_PHOTO_SIZE_MB = 3

# In-memory message buffer: {chat_id: {messages: [], photos: [], timer_task: Task, ...}}
_message_buffers = {}
# Rate limiting: {chat_id: [timestamps]}
_rate_limits = {}


# ============== TELEGRAM API HELPERS ==============
async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> bool:
    if not BOT_TOKEN:
        logger.error("[ALERTS_BOT] Bot token not configured")
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage", json=payload)
            if r.status_code != 200:
                logger.error(f"[ALERTS_BOT] sendMessage failed: {r.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[ALERTS_BOT] sendMessage error: {e}")
        return False


async def download_telegram_photo(file_id: str) -> Optional[bytes]:
    if not BOT_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TELEGRAM_API}{BOT_TOKEN}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                return None
            file_path = r.json().get("result", {}).get("file_path")
            if not file_path:
                return None
            r2 = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}")
            if r2.status_code == 200:
                return r2.content
    except Exception as e:
        logger.error(f"[ALERTS_BOT] download photo error: {e}")
    return None


async def get_system_users() -> List[dict]:
    """Get active AGENT users with alerts access to show as assignee options in Telegram bot."""
    users = await db.users.find(
        {"is_active": {"$ne": False}, "role": "AGENT", "has_alerts_access": True},
        {"_id": 0, "id": 1, "name": 1, "role": 1}
    ).to_list(50)
    return users


async def send_assignee_buttons(chat_id: int):
    """Send inline keyboard with system users as assignee choices."""
    users = await get_system_users()
    if not users:
        await send_message(chat_id, "Nenhum rececionista disponível no sistema.")
        return

    buttons = []
    row = []
    for u in users:
        row.append({"text": u["name"], "callback_data": f"assign:{u['id']}:{u['name']}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await send_message(
        chat_id,
        "Escolha o rececionista para este alerta:",
        reply_markup={"inline_keyboard": buttons}
    )


# ============== RATE LIMITING ==============
def check_rate_limit(chat_id: int) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    if chat_id not in _rate_limits:
        _rate_limits[chat_id] = []
    _rate_limits[chat_id] = [t for t in _rate_limits[chat_id] if now - t < 60]
    if len(_rate_limits[chat_id]) >= MAX_MESSAGES_PER_MIN:
        return False
    _rate_limits[chat_id].append(now)
    return True


# ============== IMAGE ANALYSIS ==============
async def analyze_image(image_bytes: bytes) -> dict:
    """Analyze image using GPT-5.2 Vision via Emergent LLM Key."""
    if not EMERGENT_LLM_KEY:
        logger.warning("[ALERTS_VISION] No EMERGENT_LLM_KEY, skipping analysis")
        return {"success": False, "error": "LLM key not configured"}

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"alert-vision-{uuid.uuid4().hex[:8]}",
            system_message="Extrais dados de imagens de oficina mecânica. Responde APENAS com JSON válido."
        ).with_model("openai", "gpt-5.2")

        prompt = """Analisa esta imagem. É uma captura de ecrã do software CEINOR GENES com alertas?

Se SIM, extrai em JSON:
{
  "is_alert": true,
  "license_plate": "XX-XX-XX ou null",
  "client_name": "nome ou null",
  "items": [{"description": "texto do item"}]
}

Se NÃO:
{"is_alert": false}

Regras:
- Devolve APENAS JSON válido, sem markdown, sem texto extra
- license_plate: formato português (AA-00-AA ou 00-AA-00), null se não visível
- client_name: nome do cliente se visível, null se não
- items: lista de objetos com description (texto de cada item/serviço), lista vazia se nenhum
- NÃO inventes dados"""

        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_base64)])),
            timeout=15
        )

        result_text = response.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)

        extracted = json.loads(result_text)

        # Normalize new format: items may be [{description: ...}] -> flatten to strings
        if isinstance(extracted.get("items"), list):
            normalized_items = []
            for item in extracted["items"]:
                if isinstance(item, dict):
                    normalized_items.append(item.get("description", str(item)))
                else:
                    normalized_items.append(str(item))
            extracted["items"] = normalized_items

        # If is_alert is False, mark as extraction failed
        if extracted.get("is_alert") is False:
            extracted["success"] = False
            extracted["error"] = "Image is not a CEINOR GENES alert"
            extracted["raw_response"] = response[:500]
            return extracted

        extracted["success"] = True
        extracted["raw_response"] = response[:500]
        logger.info(f"[ALERTS_VISION] OK: plate={extracted.get('license_plate')}, items={len(extracted.get('items', []))}")
        return extracted

    except asyncio.TimeoutError:
        logger.warning("[ALERTS_VISION] Timeout (15s)")
        return {"success": False, "error": "Timeout"}
    except json.JSONDecodeError as e:
        logger.error(f"[ALERTS_VISION] JSON parse error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[ALERTS_VISION] Error: {e}")
        return {"success": False, "error": str(e)}


# ============== STORAGE ==============
async def store_photo(image_bytes: bytes, original_filename: str, telegram_file_id: str = None) -> dict:
    """Store photo using Object Storage (preferred) or base64 fallback."""
    attachment_id = str(uuid.uuid4())
    file_size = len(image_bytes)
    attachment = {
        "id": attachment_id,
        "filename": f"{attachment_id}.jpg",
        "original_filename": original_filename,
        "file_type": "image/jpeg",
        "file_size": file_size,
        "storage_path": None,
        "telegram_file_id": telegram_file_id,
        "base64_data": None,
    }

    # Try Object Storage
    try:
        from services.storage_service import put_object
        path = f"alerts/{attachment_id}.jpg"
        put_object(path, image_bytes, "image/jpeg")
        attachment["storage_path"] = path
        logger.info(f"[ALERTS_STORAGE] Stored in Object Storage: {path}")
        return attachment
    except Exception as e:
        logger.warning(f"[ALERTS_STORAGE] Object Storage failed: {e}")

    # Fallback: base64 if <5MB
    if file_size < 5 * 1024 * 1024:
        attachment["base64_data"] = base64.b64encode(image_bytes).decode("utf-8")
        logger.info("[ALERTS_STORAGE] Stored as base64")
        return attachment

    # Fallback: telegram_file_id only
    logger.info("[ALERTS_STORAGE] Using telegram_file_id fallback")
    return attachment


# ============== MESSAGE BUFFER ==============
async def _process_buffer(chat_id: int):
    """Process buffered messages after timeout. Creates alert, then asks for assignee."""
    await asyncio.sleep(BUFFER_TIMEOUT_SECONDS)

    buf = _message_buffers.pop(chat_id, None)
    if not buf:
        return

    texts = buf.get("texts", [])
    photos = buf.get("photos", [])
    user_info = buf.get("user_info", {})
    combined_text = "\n".join(texts).strip()

    if not combined_text and not photos:
        return

    # Process last photo only (spec: use LAST one)
    attachment = None
    vision_result = {}
    extraction_failed = False

    if photos:
        last_photo = photos[-1]
        image_bytes = await download_telegram_photo(last_photo["file_id"])
        if image_bytes:
            # Store
            attachment = await store_photo(
                image_bytes,
                f"alerta_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jpg",
                last_photo["file_id"]
            )
            # Analyze
            vision_result = await analyze_image(image_bytes)
            if not vision_result.get("success"):
                extraction_failed = True

    # Create alert in DB (pending assignee)
    now = datetime.now(timezone.utc).isoformat()
    alert_id = str(uuid.uuid4())

    alert_doc = {
        "id": alert_id,
        "source": "telegram_alerts",
        "status": AlertStatus.PENDING.value,
        "license_plate": vision_result.get("license_plate") or None,
        "client_name": vision_result.get("client_name") or None,
        "items": vision_result.get("items", []),
        "assigned_to": None,
        "assigned_to_name": None,
        "created_by": {
            "source": "telegram",
            "chat_id": chat_id,
            "user_id": user_info.get("user_id", 0),
            "username": user_info.get("username"),
            "name": user_info.get("name", "Desconhecido"),
        },
        "telegram_chat_id": chat_id,
        "attachments": [attachment] if attachment else [],
        "extraction_failed": extraction_failed,
        "raw_text": combined_text or None,
        "raw_vision_output": vision_result.get("raw_response"),
        "converted": False,
        "ticket_id": None,
        "ticket_number": None,
        "created_at": now,
        "updated_at": now,
        "converted_at": None,
    }

    await db.alerts.insert_one(alert_doc)
    logger.info(f"[ALERTS] Created alert {alert_id} from chat {chat_id}")

    # Confirm to user and show assignee buttons
    plate_text = f"\nMatrícula: <b>{alert_doc['license_plate']}</b>" if alert_doc.get("license_plate") else ""
    items_text = f"\nItens: {', '.join(alert_doc['items'])}" if alert_doc.get("items") else ""
    warn_text = "\n⚠️ Não consegui ler a imagem, mas o alerta foi criado." if extraction_failed else ""

    await send_message(
        chat_id,
        f"✅ Alerta registado!{plate_text}{items_text}{warn_text}\n\nAgora escolha o rececionista:"
    )
    await send_assignee_buttons(chat_id)

    # Store alert_id in a temporary mapping for callback
    _pending_assignments[chat_id] = alert_id


# Temporary mapping: chat_id -> alert_id waiting for assignee
_pending_assignments = {}


def buffer_message(chat_id: int, user_info: dict, text: str = None, photo: dict = None):
    """Add message to buffer and reset timer."""
    if chat_id not in _message_buffers:
        _message_buffers[chat_id] = {
            "texts": [],
            "photos": [],
            "user_info": user_info,
            "timer_task": None,
        }

    buf = _message_buffers[chat_id]

    if text:
        buf["texts"].append(text)
    if photo:
        buf["photos"].append(photo)

    # Cancel existing timer and restart
    if buf["timer_task"] and not buf["timer_task"].done():
        buf["timer_task"].cancel()

    buf["timer_task"] = asyncio.create_task(_process_buffer(chat_id))


# ============== CALLBACK: ASSIGN ==============
async def handle_assign_callback(chat_id: int, user_id: str, user_name: str) -> bool:
    """Handle assignee selection callback from inline keyboard."""
    alert_id = _pending_assignments.pop(chat_id, None)
    if not alert_id:
        # Maybe old alert — find latest pending unassigned for this chat
        alert = await db.alerts.find_one(
            {"telegram_chat_id": chat_id, "assigned_to": None, "status": AlertStatus.PENDING.value},
            {"_id": 0, "id": 1},
            sort=[("created_at", -1)]
        )
        if alert:
            alert_id = alert["id"]

    if not alert_id:
        await send_message(chat_id, "Nenhum alerta pendente para atribuir.")
        return False

    now = datetime.now(timezone.utc).isoformat()
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"assigned_to": user_id, "assigned_to_name": user_name, "updated_at": now}}
    )

    await send_message(
        chat_id,
        f"✅ Alerta atribuído a <b>{user_name}</b>.\n\nPode enviar nova foto ou texto para criar outro alerta."
    )

    # Create notification for assigned user AND admin
    try:
        from services.notification_service import create_notification
        alert = await db.alerts.find_one({"id": alert_id}, {"_id": 0})
        plate_info = f" ({alert['license_plate']})" if alert and alert.get("license_plate") else ""
        mechanic_name = alert.get("created_by", {}).get("name", "Mecânico") if alert else "Mecânico"
        notif_body = f"Alerta de {mechanic_name}{plate_info} - atribuído a {user_name}"

        # Notify assigned agent
        await create_notification(
            user_id=user_id,
            title="Novo Alerta Telegram",
            body=notif_body,
            notification_type="info",
        )

        # Notify all admins
        admins = await db.users.find(
            {"role": "ADMIN", "is_active": {"$ne": False}},
            {"_id": 0, "id": 1}
        ).to_list(10)
        for admin in admins:
            if admin["id"] != user_id:
                await create_notification(
                    user_id=admin["id"],
                    title="Novo Alerta Telegram",
                    body=notif_body,
                    notification_type="info",
                )
    except Exception as e:
        logger.warning(f"[ALERTS] Notification error: {e}")

    logger.info(f"[ALERTS] Alert {alert_id} assigned to {user_name} ({user_id})")
    return True


# ============== ALERT CRUD ==============
async def get_alerts(
    status: str = None,
    assigned_to: str = None,
    page: int = 1,
    page_size: int = 50,
    user_role: str = None,
    user_id: str = None,
) -> Tuple[List[dict], int]:
    """List alerts with filters. Admins/Supervisors see all, others see only assigned."""
    query = {"source": "telegram_alerts"}
    if status:
        query["status"] = status
    if assigned_to:
        query["assigned_to"] = assigned_to
    elif user_role and user_role not in ("ADMIN", "SUPERVISOR"):
        query["assigned_to"] = user_id

    total = await db.alerts.count_documents(query)
    skip = (page - 1) * page_size
    items = await db.alerts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return items, total


async def get_alert(alert_id: str) -> Optional[dict]:
    return await db.alerts.find_one({"id": alert_id}, {"_id": 0})


async def update_alert(alert_id: str, updates: dict) -> Optional[dict]:
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.alerts.update_one({"id": alert_id}, {"$set": updates})
    if result.matched_count > 0:
        return await get_alert(alert_id)
    return None


async def delete_alert(alert_id: str) -> bool:
    result = await db.alerts.delete_one({"id": alert_id})
    return result.deleted_count > 0


async def dismiss_alert(alert_id: str) -> Optional[dict]:
    """Dismiss an alert (mark as not needed)."""
    alert = await get_alert(alert_id)
    if not alert or alert.get("status") != AlertStatus.PENDING.value:
        return None
    now = datetime.now(timezone.utc).isoformat()
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"status": AlertStatus.DISMISSED.value, "updated_at": now}}
    )
    return await get_alert(alert_id)


async def convert_alert_to_ticket(alert_id: str, converted_by: str, data: dict = None) -> Optional[dict]:
    """Convert alert to a ticket. Mirrors intake conversion logic."""
    alert = await get_alert(alert_id)
    if not alert:
        return None
    if alert.get("converted"):
        return None

    data = data or {}
    now = datetime.now(timezone.utc)
    ticket_id = str(uuid.uuid4())
    ticket_number = f"TK{now.strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"

    customer_name = data.get("customer_name") or alert.get("client_name") or "Cliente (via Alerta)"
    customer_phone = data.get("customer_phone") or ""
    customer_email = data.get("customer_email") or ""
    vehicle_plate = data.get("vehicle_plate") or alert.get("license_plate") or ""
    description = data.get("description") or alert.get("raw_text") or ""
    ticket_type = data.get("ticket_type") or "ORCAMENTO_MECANICA"
    assigned_to = data.get("assigned_to") or alert.get("assigned_to")

    # Append items to description only if not already present
    items_list = alert.get("items", [])
    if items_list:
        items_text = ", ".join(items_list)
        if description and items_text not in description:
            description = f"{description} | Itens: {items_text}"
        elif not description:
            description = f"Itens: {items_text}"

    # Auto-create customer and vehicle
    customer_id = None
    vehicle_id = None
    was_created = False
    try:
        from services.customer_service import find_or_create_customer_vehicle
        customer_id, vehicle_id, was_created = await find_or_create_customer_vehicle(
            license_plate=vehicle_plate,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            source="alert_conversion"
        )
    except Exception as e:
        logger.warning(f"[ALERTS] Customer auto-create failed: {e}")

    # Get assigned user name
    assigned_to_name = None
    if assigned_to:
        user = await db.users.find_one({"id": assigned_to}, {"_id": 0, "name": 1})
        assigned_to_name = user.get("name") if user else None

    # Compute SLA
    sla_due = None
    sla_target_minutes = 0
    sla_policy_key = None
    try:
        from modules.intake.routes import compute_sla_due as _compute_sla
        sla_due, sla_target_minutes, sla_policy_key = _compute_sla(
            ticket_type=ticket_type, created_at=now
        )
    except Exception as e:
        logger.warning(f"[ALERTS] SLA compute failed: {e}")
        sla_due = now + timedelta(hours=24)

    initial_status = "EM_TRATAMENTO" if assigned_to else "ABERTO"

    ticket_doc = {
        "id": ticket_id,
        "ticket_number": ticket_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "channel": "TELEGRAM",
        "type": ticket_type,
        "status": initial_status,
        "priority": "NORMAL",
        "description": description,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "vehicle_plate": vehicle_plate,
        "assigned_to_user_id": assigned_to,
        "assigned_to_name": assigned_to_name,
        "created_by_user_id": converted_by,
        "created_by_name": f"Alerta Telegram: {alert.get('created_by', {}).get('name', 'Desconhecido')}",
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "first_response_done": False,
        "sla_due": sla_due.isoformat() if sla_due else None,
        "sla_started_at": now.isoformat(),
        "sla_paused_at": None,
        "sla_paused_minutes": 0,
        "sla_breached": False,
        "sla_breached_at": None,
        "sla_target_minutes": sla_target_minutes,
        "sla_policy_key": sla_policy_key,
        "quote_sent": False,
        "quote_value": None,
        "source_alert_id": alert_id,
    }

    await db.tickets.insert_one(ticket_doc)

    # Transfer attachments
    for att in alert.get("attachments", []):
        att_doc = {
            "id": att.get("id", str(uuid.uuid4())),
            "ticket_id": ticket_id,
            "filename": att.get("filename", ""),
            "original_filename": att.get("original_filename", "photo.jpg"),
            "file_type": att.get("file_type", "image/jpeg"),
            "file_size": att.get("file_size", 0),
            "storage_path": att.get("storage_path"),
            "uploaded_by_user_id": converted_by,
            "uploaded_at": now.isoformat(),
        }
        await db.attachments.insert_one(att_doc)

    # Add system note
    note_body = "Ticket criado a partir de alerta Telegram"
    if alert.get("license_plate"):
        note_body += f"\nMatrícula: {alert['license_plate']}"
    if items_list:
        note_body += f"\nItens: {', '.join(items_list)}"
    if alert.get("created_by", {}).get("name"):
        note_body += f"\nEnviado por: {alert['created_by']['name']}"

    note_doc = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "created_at": now.isoformat(),
        "created_by_user_id": converted_by,
        "body": note_body,
        "is_system": True,
    }
    await db.notes.insert_one(note_doc)

    # Mark alert as converted
    await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {
            "status": AlertStatus.CONVERTED.value,
            "converted": True,
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "converted_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }}
    )

    logger.info(f"[ALERTS] Converted alert {alert_id} to ticket {ticket_number}")

    # Notify mechanic via Telegram that alert was converted
    mechanic_chat_id = alert.get("telegram_chat_id")
    if mechanic_chat_id:
        plate_text = f" ({vehicle_plate})" if vehicle_plate else ""
        await send_message(
            mechanic_chat_id,
            f"📋 O seu alerta{plate_text} foi convertido no ticket <b>{ticket_number}</b>.\n"
            f"Cliente: {customer_name}"
        )

    return {"ticket_id": ticket_id, "ticket_number": ticket_number, "customer_created": was_created}


async def get_alert_stats() -> dict:
    """Get alert statistics."""
    pipeline = [
        {"$match": {"source": "telegram_alerts"}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    results = await db.alerts.aggregate(pipeline).to_list(10)

    stats = {"pending": 0, "converted": 0, "dismissed": 0, "total": 0}
    for r in results:
        s = (r["_id"] or "pending").lower()
        if s in stats:
            stats[s] = r["count"]
        stats["total"] += r["count"]

    return stats


async def setup_webhook(webhook_url: str) -> dict:
    """Register webhook URL with Telegram Bot API."""
    if not BOT_TOKEN:
        return {"success": False, "error": "Bot token not configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{TELEGRAM_API}{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]}
            )
            data = r.json()
            logger.info(f"[ALERTS_BOT] setWebhook: {data}")
            return {"success": data.get("ok", False), "result": data}
    except Exception as e:
        logger.error(f"[ALERTS_BOT] setWebhook error: {e}")
        return {"success": False, "error": str(e)}
