"""Renting module — API routes + Telegram webhook."""
import os
import base64
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from db import db
from core.security import get_current_user
from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/renting", tags=["renting"])


# ============== PERMISSION HELPER ==============
def _check_renting_access(user: dict):
    if user.get("role") in ("ADMIN", "SUPERVISOR"):
        return
    if not user.get("has_renting_access"):
        raise HTTPException(status_code=403, detail="Sem permissão para o módulo Renting")


# ============== TELEGRAM WEBHOOK ==============
@router.post("/webhook")
async def telegram_webhook(payload: dict):
    """Handle incoming Telegram updates for the Renting bot."""
    # Callback queries
    cb = payload.get("callback_query")
    if cb:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        data = cb.get("data", "")
        callback_id = cb.get("id")
        if chat_id and data:
            await service.handle_callback(chat_id, data)
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"{service.TELEGRAM_API}{service.BOT_TOKEN}/answerCallbackQuery",
                        json={"callback_query_id": callback_id, "text": "OK"}
                    )
            except Exception:
                pass
        return {"ok": True}

    msg = payload.get("message")
    if not msg:
        return {"ok": True}

    chat_id = msg.get("chat", {}).get("id")
    from_user = msg.get("from", {}) or {}
    user_info = {
        "user_id": from_user.get("id"),
        "username": from_user.get("username"),
        "name": f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or "Desconhecido",
        "chat_id": chat_id,
    }
    text = (msg.get("text") or "").strip()

    if text.lower() in ("/start", "/help"):
        await service.send_message(
            chat_id,
            "🚗 <b>Renting Bot</b>\n\n"
            "Comandos:\n"
            "/novo_renting — começar novo registo\n"
            "/cancelar — cancelar sessão atual"
        )
        return {"ok": True}

    if text.lower() == "/novo_renting":
        await service.start_new_session(chat_id, user_info)
        return {"ok": True}

    if text.lower() in ("/cancelar", "/cancel", "/reset"):
        await service.cancel_session(chat_id)
        return {"ok": True}

    voice = msg.get("voice") or msg.get("audio")
    if voice:
        await service.handle_voice(chat_id, user_info, voice)
        return {"ok": True}

    photo = msg.get("photo")
    if photo:
        best = max(photo, key=lambda p: p.get("file_size", 0))
        await service.handle_photo(chat_id, user_info, {"file_id": best["file_id"], "file_size": best.get("file_size", 0)})
        return {"ok": True}

    doc = msg.get("document")
    if doc and doc.get("mime_type", "").startswith("image/"):
        await service.handle_photo(chat_id, user_info, {"file_id": doc["file_id"], "file_size": doc.get("file_size", 0)})
        return {"ok": True}

    if text:
        await service.handle_text(chat_id, user_info, text)
        return {"ok": True}

    return {"ok": True}


@router.post("/setup-webhook")
async def setup_webhook(webhook_url: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Apenas administradores")
    return await service.setup_webhook(webhook_url)


# ============== ADMIN API ==============
@router.get("/records")
async def list_records(
    status: Optional[str] = Query(None),
    renting_company: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    subtype: Optional[str] = Query(None, regex="^(tires|adblue|puncture|other)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    _check_renting_access(current_user)
    items, total = await service.list_records(status, renting_company, search, subtype, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    _check_renting_access(current_user)
    return await service.get_stats()


@router.get("/records/{record_id}")
async def get_record(record_id: str, current_user: dict = Depends(get_current_user)):
    _check_renting_access(current_user)
    rec = await service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    return rec


class RentingUpdate(BaseModel):
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    renting_company: Optional[str] = None
    license_plate: Optional[str] = None
    km: Optional[int] = None
    service_type: Optional[str] = None
    service_type_label: Optional[str] = None
    wheels: Optional[list] = None
    observations: Optional[dict] = None
    subtype: Optional[str] = None
    adblue_liters: Optional[float] = None
    description: Optional[str] = None
    puncture_wheel: Optional[str] = None
    puncture_wheel_label: Optional[str] = None
    # Reception desk fields
    proposed_tires: Optional[str] = None
    authorization_number: Optional[str] = None
    status: Optional[str] = None


@router.put("/records/{record_id}")
async def update_record(record_id: str, body: RentingUpdate, current_user: dict = Depends(get_current_user)):
    _check_renting_access(current_user)
    updates = body.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Sem campos para atualizar")
    if "status" in updates and updates["status"] not in ("draft", "in_progress", "completed"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    rec = await service.update_record(record_id, updates, actor=current_user)
    if not rec:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    return rec


@router.delete("/records/{record_id}")
async def delete_record(record_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Apenas administradores")
    ok = await service.delete_record(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    return {"deleted": True}


@router.get("/records/{record_id}/pdf")
async def get_record_pdf(record_id: str, current_user: dict = Depends(get_current_user)):
    """Generate a technical PDF for a Renting record (for sending to the renting company)."""
    _check_renting_access(current_user)
    rec = await service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    try:
        branding = await db.settings.find_one({"type": "branding_config"}, {"_id": 0}) or {}
        company_name = branding.get("company_name", "Pneus D. Pedro V")
        from .pdf import build_renting_pdf
        pdf_bytes = await build_renting_pdf(rec, company_name=company_name)
    except Exception as e:
        logger.error(f"[RENTING_PDF] generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar PDF")
    plate = (rec.get("license_plate") or "renting").replace("-", "").replace(" ", "")
    filename = f"renting_{plate}_{(rec.get('id') or '')[:8]}.pdf"
    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ============== PHOTO PROXY ==============
@router.get("/records/{record_id}/photo/{photo_kind}")
async def get_record_photo(
    record_id: str,
    photo_kind: str,
    wheel_index: Optional[int] = Query(None),
    sub: Optional[str] = Query(None, regex="^(full|dot|tread)$"),
    current_user: dict = Depends(get_current_user),
):
    """Serve a photo by kind: 'plate' | 'km' | 'wheel' (requires wheel_index + sub)."""
    _check_renting_access(current_user)
    rec = await service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    photo = None
    if photo_kind == "plate":
        photo = rec.get("license_plate_photo")
    elif photo_kind == "km":
        photo = rec.get("km_photo")
    elif photo_kind == "wheel":
        if wheel_index is None or sub is None:
            raise HTTPException(status_code=400, detail="wheel_index e sub são obrigatórios")
        wheels = rec.get("wheels", [])
        if wheel_index < 0 or wheel_index >= len(wheels):
            raise HTTPException(status_code=404, detail="Roda não encontrada")
        photo = wheels[wheel_index].get(f"photo_{sub}")
    if not photo:
        raise HTTPException(status_code=404, detail="Foto não encontrada")

    if photo.get("storage_path"):
        try:
            from services.storage_service import get_object
            data, content_type = get_object(photo["storage_path"])
            return {"base64": base64.b64encode(data).decode("utf-8"), "file_type": content_type or "image/jpeg"}
        except Exception:
            pass
    if photo.get("base64_data"):
        return {"base64": photo["base64_data"], "file_type": photo.get("file_type", "image/jpeg")}
    if photo.get("telegram_file_id"):
        b = await service.download_telegram_photo(photo["telegram_file_id"])
        if b:
            return {"base64": base64.b64encode(b).decode("utf-8"), "file_type": "image/jpeg"}
    raise HTTPException(status_code=404, detail="Foto indisponível")


@router.get("/records/{record_id}/observations-audio")
async def get_observations_audio(record_id: str, current_user: dict = Depends(get_current_user)):
    _check_renting_access(current_user)
    rec = await service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    obs = rec.get("observations") or {}
    audio = obs.get("audio") if obs.get("type") == "audio" else None
    if not audio:
        raise HTTPException(status_code=404, detail="Áudio não encontrado")
    if audio.get("storage_path"):
        try:
            from services.storage_service import get_object
            data, content_type = get_object(audio["storage_path"])
            return {"base64": base64.b64encode(data).decode("utf-8"), "file_type": content_type or "audio/ogg"}
        except Exception:
            pass
    if audio.get("base64_data"):
        return {"base64": audio["base64_data"], "file_type": audio.get("file_type", "audio/ogg")}
    if audio.get("telegram_file_id"):
        b, ext = await service.download_telegram_file(audio["telegram_file_id"])
        if b:
            return {"base64": base64.b64encode(b).decode("utf-8"), "file_type": f"audio/{ext or 'ogg'}"}
    raise HTTPException(status_code=404, detail="Áudio indisponível")
