"""Assistências module — API routes + Telegram webhook."""
import logging
import os
import base64
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from fastapi.responses import Response
from pydantic import BaseModel

from db import db
from core.security import get_current_user
from . import service, bot_api

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistencias", tags=["assistencias"])


# ============== Permissions ==============
def _require_office_or_admin(user: dict):
    if user.get("role") not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Apenas escritório/admin")


def _require_admin(user: dict):
    if user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Apenas administradores")


def _check_access(user: dict):
    if user.get("role") in ("ADMIN", "SUPERVISOR"):
        return
    if user.get("has_assistencias_access"):
        return
    raise HTTPException(status_code=403, detail="Sem permissão para o módulo Assistências")


# ============== Telegram webhook ==============
@router.post("/webhook")
async def telegram_webhook(request: Request):
    """DEPRECATED — Assistências bot consolidated into @pdpv_interno_bot.
    Returns 200 OK to prevent Telegram from retrying; any lingering webhook
    delivery is silently absorbed. Users hitting the standalone bot will get
    no response — direct them to @pdpv_interno_bot.
    """
    return {"status": "deprecated", "message": "Bot consolidated into @pdpv_interno_bot"}


@router.post("/webhook/legacy")
async def telegram_webhook_legacy(request: Request):
    """Receive Telegram updates for the Assistências bot (LEGACY, unrouted)."""
    # Optional secret check
    expected_secret = os.environ.get("TELEGRAM_ASSISTENCIAS_WEBHOOK_SECRET")
    if expected_secret:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if got != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    payload = await request.json()

    cb = payload.get("callback_query")
    if cb:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        data = cb.get("data", "")
        cb_id = cb.get("id")
        if chat_id and data:
            await service.handle_callback(chat_id, data, cb_id)
        return {"ok": True}

    msg = payload.get("message")
    if not msg:
        return {"ok": True}

    chat_id = msg.get("chat", {}).get("id")
    from_user = msg.get("from", {}) or {}
    tg_user = {
        "id": from_user.get("id"),
        "username": from_user.get("username"),
        "name": f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()
                or "Desconhecido",
    }
    text = (msg.get("text") or "").strip()

    if text.lower() in ("/start", "/help"):
        await bot_api.send_message(
            chat_id,
            "🚐 <b>PDPV Assistências Bot</b>\n\n"
            "Comandos:\n"
            "/nova_assistencia — registar nova assistência\n"
            "/cancelar — cancelar sessão"
        )
        return {"ok": True}

    if text.lower() in ("/nova_assistencia", "/nova", "/new"):
        await service.start_new_assistance(chat_id, tg_user)
        return {"ok": True}

    if text.lower() in ("/cancelar", "/cancel", "/reset"):
        await service.cancel_session(chat_id)
        return {"ok": True}

    location = msg.get("location")
    if location:
        await service.handle_location(chat_id, tg_user, location)
        return {"ok": True}

    voice = msg.get("voice") or msg.get("audio")
    if voice:
        await service.handle_voice(chat_id, tg_user, voice)
        return {"ok": True}

    photo = msg.get("photo")
    if photo:
        best = max(photo, key=lambda p: p.get("file_size", 0))
        await service.handle_photo(chat_id, tg_user, {"file_id": best["file_id"]})
        return {"ok": True}

    doc = msg.get("document")
    if doc and (doc.get("mime_type") or "").startswith("image/"):
        await service.handle_photo(chat_id, tg_user, {"file_id": doc["file_id"]})
        return {"ok": True}

    if text:
        await service.handle_text(chat_id, tg_user, text)
        return {"ok": True}

    return {"ok": True}


# ============== Bot configuration (admin) ==============
@router.get("/bot/status")
async def bot_status(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    if not bot_api.is_configured():
        return {"configured": False, "reason": "TELEGRAM_ASSISTENCIAS_BOT_TOKEN missing"}
    info = await bot_api.get_me() or {}
    return {"configured": True, "telegram_getMe": info.get("result") or info}


class WebhookIn(BaseModel):
    url: str


@router.post("/bot/webhook/configure")
async def configure_webhook(body: WebhookIn, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    if not bot_api.is_configured():
        raise HTTPException(status_code=503, detail="Bot not configured")
    res = await bot_api.set_webhook(body.url)
    if not res or not res.get("ok"):
        raise HTTPException(status_code=502, detail="Telegram setWebhook failed")
    return res


# ============== Authorized bot users (admin) ==============
@router.get("/bot/users")
async def list_bot_users(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return await service.list_bot_users()


class BotUserIn(BaseModel):
    telegram_user_id: int
    user_id: str


@router.post("/bot/users")
async def add_bot_user(body: BotUserIn, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        rec = await service.add_bot_user(body.telegram_user_id, body.user_id, current_user)
        return rec
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/bot/users/{telegram_user_id}")
async def remove_bot_user(telegram_user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    ok = await service.remove_bot_user(telegram_user_id)
    return {"deleted": ok}


# ============== List / detail / stats ==============
@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    _check_access(current_user)
    return await service.get_stats()


@router.get("/pending-count")
async def pending_count(current_user: dict = Depends(get_current_user)):
    """Count of records still requiring office attention (everything except FATURADA_CONCLUIDA and NAO_FATURAVEL)."""
    _check_access(current_user)
    q = {"status": {"$nin": ["FATURADA_CONCLUIDA", "NAO_FATURAVEL"]}}
    if current_user.get("role") not in ("ADMIN", "SUPERVISOR"):
        q["employee_id"] = current_user.get("id")
    from db import db as _db
    n = await _db.assistencias.count_documents(q)
    return {"count": n}


@router.get("/stats/advanced")
async def get_stats_advanced(
    start: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    return await service.get_stats_advanced(start, end)


@router.get("/export/csv")
async def export_csv(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    csv_bytes = await service.export_csv(status, employee_id, start, end)
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="assistencias.csv"'},
    )


@router.get("/records")
async def list_records(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    plate: Optional[str] = Query(None),
    invoice_number: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    _check_access(current_user)
    # Non-admin/sup employees only see their own records
    if current_user.get("role") not in ("ADMIN", "SUPERVISOR"):
        employee_id = current_user.get("id")
    items, total = await service.list_records(
        status, employee_id, plate, invoice_number, search, page, page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/records/{record_id}")
async def get_record(record_id: str, current_user: dict = Depends(get_current_user)):
    _check_access(current_user)
    rec = await service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    if (current_user.get("role") not in ("ADMIN", "SUPERVISOR")
            and rec.get("employee_id") != current_user.get("id")):
        raise HTTPException(status_code=403, detail="Sem permissão")
    return rec


class UpdateRecordIn(BaseModel):
    registration_plate: Optional[str] = None
    text_notes: Optional[str] = None
    approximate_address: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_total: Optional[float] = None
    invoice_date: Optional[str] = None
    invoice_customer: Optional[str] = None
    invoice_nif: Optional[str] = None


@router.put("/records/{record_id}")
async def update_record(
    record_id: str,
    body: UpdateRecordIn,
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    updates = {k: v for k, v in body.dict().items() if v is not None}
    rec = await service.update_record(record_id, updates, current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    return rec


@router.delete("/records/{record_id}")
async def delete_record(record_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    ok = await service.delete_record(record_id, current_user)
    if not ok:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    return {"deleted": True}


class StatusIn(BaseModel):
    status: str


@router.post("/records/{record_id}/status")
async def change_status(
    record_id: str, body: StatusIn,
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    rec = await service.update_status(record_id, body.status, current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    if isinstance(rec, dict) and rec.get("error"):
        raise HTTPException(status_code=400, detail=rec["error"])
    return rec


# ============== Invoice upload + AI extraction ==============
@router.post("/records/{record_id}/invoice")
async def upload_invoice(
    record_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Apenas PDF é aceite")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Ficheiro vazio")
    if len(pdf_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF maior que 15MB")
    rec = await service.attach_invoice_and_extract(record_id, pdf_bytes, current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    return rec


class ConfirmInvoiceIn(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    invoice_total: Optional[float] = None
    invoice_customer: Optional[str] = None
    invoice_nif: Optional[str] = None


@router.post("/records/{record_id}/invoice/confirm")
async def confirm_invoice(
    record_id: str, body: ConfirmInvoiceIn,
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    rec = await service.confirm_invoice(record_id, body.dict(), current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    return rec


@router.post("/records/{record_id}/invoice/send")
async def send_invoice(record_id: str, current_user: dict = Depends(get_current_user)):
    _require_office_or_admin(current_user)
    rec = await service.send_invoice_to_employee(record_id, current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    if isinstance(rec, dict) and rec.get("error"):
        raise HTTPException(status_code=400, detail=rec["error"])
    return rec


@router.post("/records/{record_id}/delivery/confirm")
async def confirm_delivery(record_id: str, current_user: dict = Depends(get_current_user)):
    _require_office_or_admin(current_user)
    rec = await service.confirm_delivery(record_id, current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    return rec


class NonBillableIn(BaseModel):
    reason: str
    internal_note: str = ""


@router.post("/records/{record_id}/non-billable")
async def mark_non_billable(
    record_id: str, body: NonBillableIn,
    current_user: dict = Depends(get_current_user),
):
    _require_office_or_admin(current_user)
    rec = await service.mark_non_billable(record_id, body.reason, body.internal_note, current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Assistência não encontrada")
    if isinstance(rec, dict) and rec.get("error"):
        raise HTTPException(status_code=400, detail=rec["error"])
    return rec


# ============== Photo / PDF retrieval (returns base64 for inline preview) ==============
@router.get("/records/{record_id}/photo/{kind}")
async def get_photo(
    record_id: str, kind: str,
    index: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    _check_access(current_user)
    rec = await service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Não encontrada")
    photo = None
    if kind == "plate":
        photo = rec.get("plate_photo")
    elif kind == "worksheet":
        photo = rec.get("worksheet_photo")
    elif kind == "additional":
        photos = rec.get("additional_photos") or []
        if 0 <= index < len(photos):
            photo = photos[index]
    if not photo:
        raise HTTPException(status_code=404, detail="Foto não disponível")
    data = await service.get_file_bytes(photo)
    if not data:
        raise HTTPException(status_code=404, detail="Falha a obter foto")
    return {
        "base64": base64.b64encode(data).decode("utf-8"),
        "file_type": photo.get("content_type") or "image/jpeg",
    }


@router.get("/records/{record_id}/invoice/pdf")
async def get_invoice_pdf(record_id: str, current_user: dict = Depends(get_current_user)):
    _check_access(current_user)
    rec = await service.get_record(record_id)
    if not rec or not rec.get("invoice_pdf"):
        raise HTTPException(status_code=404, detail="Fatura não disponível")
    data = await service.get_file_bytes(rec["invoice_pdf"])
    if not data:
        raise HTTPException(status_code=404, detail="Falha a obter PDF")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="fatura_{record_id[:8]}.pdf"'},
    )


@router.get("/records/{record_id}/audio")
async def get_audio(record_id: str, current_user: dict = Depends(get_current_user)):
    _check_access(current_user)
    rec = await service.get_record(record_id)
    if not rec or not rec.get("audio_file"):
        raise HTTPException(status_code=404, detail="Sem áudio")
    data = await service.get_file_bytes(rec["audio_file"])
    if not data:
        raise HTTPException(status_code=404, detail="Falha")
    return {
        "base64": base64.b64encode(data).decode("utf-8"),
        "file_type": rec["audio_file"].get("content_type") or "audio/ogg",
    }
