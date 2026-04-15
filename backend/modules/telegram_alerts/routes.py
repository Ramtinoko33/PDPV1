"""
Telegram Alerts Module - API Routes
Endpoints for webhook, alert CRUD, conversion, and stats.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from db import db
from core.security import get_current_user
from .models import AlertUpdate, AlertConvertRequest
from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram-alerts", tags=["Telegram Alerts"])


# ============== WEBHOOK ==============
@router.post("/webhook")
async def telegram_alerts_webhook(request: Request):
    """Receive Telegram bot updates (messages + callbacks)."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    # Handle callback query (assignee selection)
    callback = payload.get("callback_query")
    if callback:
        data = callback.get("data", "")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        if data.startswith("assign:") and chat_id:
            parts = data.split(":", 2)
            if len(parts) == 3:
                user_id = parts[1]
                user_name = parts[2]
                await service.handle_assign_callback(chat_id, user_id, user_name)
                # Answer callback to remove loading indicator
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.post(
                            f"{service.TELEGRAM_API}{service.BOT_TOKEN}/answerCallbackQuery",
                            json={"callback_query_id": callback["id"], "text": f"Atribuído a {user_name}"}
                        )
                except Exception:
                    pass
        return {"ok": True}

    # Handle message
    message = payload.get("message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id", 0)
    username = message.get("from", {}).get("username")
    first_name = message.get("from", {}).get("first_name", "")
    last_name = message.get("from", {}).get("last_name", "")
    text = message.get("text", "").strip()

    if not chat_id:
        return {"ok": True}

    # Rate limit
    if not service.check_rate_limit(chat_id):
        await service.send_message(chat_id, "⚠️ Muitas mensagens. Aguarde um momento.")
        return {"ok": True}

    # Handle /start command
    if text == "/start":
        await service.send_message(
            chat_id,
            "👋 Bem-vindo ao <b>PDPV Alertas</b>!\n\n"
            "Envie uma <b>foto</b> ou <b>texto</b> para criar um alerta.\n"
            "Depois escolha o rececionista."
        )
        return {"ok": True}

    # Collect user info
    user_info = {
        "user_id": user_id,
        "username": username,
        "name": f"{first_name} {last_name}".strip() or "Desconhecido",
    }

    # Photo message
    photo = message.get("photo")
    if photo:
        # Telegram sends multiple sizes, take the largest
        best = max(photo, key=lambda p: p.get("file_size", 0))
        file_size = best.get("file_size", 0)
        if file_size > MAX_PHOTO_SIZE_MB * 1024 * 1024:
            await service.send_message(chat_id, f"⚠️ Foto demasiado grande (max {MAX_PHOTO_SIZE_MB}MB)")
            return {"ok": True}

        caption = message.get("caption", "")
        service.buffer_message(
            chat_id,
            user_info,
            text=caption if caption else None,
            photo={"file_id": best["file_id"], "file_size": file_size}
        )
        return {"ok": True}

    # Ignore video
    if message.get("video") or message.get("video_note"):
        await service.send_message(chat_id, "⚠️ Vídeos não são suportados. Envie uma foto ou texto.")
        return {"ok": True}

    # Text message
    if text:
        service.buffer_message(chat_id, user_info, text=text)
        return {"ok": True}

    # Document (treat as photo if image)
    doc = message.get("document")
    if doc and doc.get("mime_type", "").startswith("image/"):
        file_size = doc.get("file_size", 0)
        if file_size <= MAX_PHOTO_SIZE_MB * 1024 * 1024:
            service.buffer_message(
                chat_id,
                user_info,
                photo={"file_id": doc["file_id"], "file_size": file_size}
            )
        else:
            await service.send_message(chat_id, f"⚠️ Ficheiro demasiado grande (max {MAX_PHOTO_SIZE_MB}MB)")
        return {"ok": True}

    return {"ok": True}


MAX_PHOTO_SIZE_MB = 3


# ============== WEBHOOK SETUP ==============
@router.post("/setup-webhook")
async def setup_alerts_webhook(request: Request, current_user: dict = Depends(get_current_user)):
    """Setup Telegram webhook for alerts bot. Admin only."""
    if current_user["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Allow custom URL in body
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    custom_url = body.get("webhook_url") if body else None

    if custom_url:
        webhook_url = custom_url
    else:
        # Determine webhook URL from frontend URL settings
        email_settings = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
        frontend_url = email_settings.get("frontend_url", "") if email_settings else ""

        if not frontend_url:
            import os
            frontend_url = os.environ.get("FRONTEND_URL", "") or os.environ.get("APP_URL", "")

        if not frontend_url:
            raise HTTPException(status_code=400, detail="URL do frontend não configurado. Configure nas definições de email.")

        webhook_url = f"{frontend_url}/api/telegram-alerts/webhook"

    result = await service.setup_webhook(webhook_url)

    if result.get("success"):
        return {"status": "success", "webhook_url": webhook_url, "result": result.get("result")}
    raise HTTPException(status_code=500, detail=result.get("error", "Falha ao configurar webhook"))


# ============== ACCESS CHECK ==============
def _check_alerts_access(user: dict):
    """Check if user has access to alerts module."""
    if user["role"] in ("ADMIN", "SUPERVISOR"):
        return True
    if user.get("has_alerts_access"):
        return True
    raise HTTPException(status_code=403, detail="Sem acesso aos alertas")


# ============== ALERT CRUD ==============
@router.get("/alerts")
async def list_alerts(
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    current_user: dict = Depends(get_current_user),
):
    _check_alerts_access(current_user)
    items, total = await service.get_alerts(
        status=status,
        assigned_to=assigned_to,
        page=page,
        page_size=page_size,
        user_role=current_user["role"],
        user_id=current_user["id"],
    )
    return {"alerts": items, "total": total, "page": page, "page_size": page_size}


@router.get("/alerts/stats")
async def alert_stats(current_user: dict = Depends(get_current_user)):
    _check_alerts_access(current_user)
    return await service.get_alert_stats()


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    _check_alerts_access(current_user)
    alert = await service.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return alert


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, data: AlertUpdate, current_user: dict = Depends(get_current_user)):
    _check_alerts_access(current_user)
    updates = {k: v for k, v in data.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    result = await service.update_alert(alert_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return result


@router.post("/alerts/{alert_id}/convert")
async def convert_alert(alert_id: str, data: AlertConvertRequest, current_user: dict = Depends(get_current_user)):
    _check_alerts_access(current_user)
    convert_data = {k: v for k, v in data.dict(exclude_unset=True).items() if v is not None}
    result = await service.convert_alert_to_ticket(
        alert_id=alert_id,
        converted_by=current_user["id"],
        data=convert_data,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Não foi possível converter. Alerta não encontrado ou já convertido.")
    return result


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Sem permissão")
    success = await service.delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return {"status": "success"}


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    _check_alerts_access(current_user)
    result = await service.dismiss_alert(alert_id)
    if not result:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return result


@router.get("/alerts-count")
async def pending_alerts_count(current_user: dict = Depends(get_current_user)):
    """Get pending alerts count for sidebar badge."""
    has_access = current_user["role"] in ("ADMIN", "SUPERVISOR") or current_user.get("has_alerts_access")
    if not has_access:
        return {"count": 0}
    count = await db.alerts.count_documents({"source": "telegram_alerts", "status": "pending"})
    return {"count": count}


@router.get("/alerts/{alert_id}/photo/{attachment_id}")
async def get_alert_photo(alert_id: str, attachment_id: str, current_user: dict = Depends(get_current_user)):
    """Get alert photo (base64 or redirect to storage)."""
    _check_alerts_access(current_user)
    alert = await service.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")

    for att in alert.get("attachments", []):
        if att.get("id") == attachment_id:
            if att.get("storage_path"):
                try:
                    from services.storage_service import get_object
                    data, content_type = get_object(att["storage_path"])
                    import base64
                    return {"base64": base64.b64encode(data).decode("utf-8"), "file_type": content_type}
                except Exception:
                    pass
            if att.get("base64_data"):
                return {"base64": att["base64_data"], "file_type": att.get("file_type", "image/jpeg")}
            if att.get("telegram_file_id"):
                image_bytes = await service.download_telegram_photo(att["telegram_file_id"])
                if image_bytes:
                    import base64
                    return {"base64": base64.b64encode(image_bytes).decode("utf-8"), "file_type": "image/jpeg"}

    raise HTTPException(status_code=404, detail="Foto não encontrada")
