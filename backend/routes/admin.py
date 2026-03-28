"""
Admin routes module.
Contains endpoints for admin settings, ticket types, statuses, SLA config, email config, branding, reports.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from db import db
from schemas.user import UserRole
from core.security import get_current_user
from services.ticket_service import REJECTION_REASON_CODES

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== SCHEMAS ==============
class TicketTypeCreate(BaseModel):
    code: str
    label: str
    color: str = "#f97316"

class TicketTypeUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None

class TicketTypeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    label: str
    color: str
    created_at: str

class TicketStatusCreate(BaseModel):
    code: str
    label: str
    color: str = "#3b82f6"
    is_final: bool = False

class TicketStatusUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    is_final: Optional[bool] = None

class TicketStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    label: str
    color: str
    is_final: bool = False
    created_at: str

class BusinessHoursConfig(BaseModel):
    start: str = "08:30"
    end: str = "18:30"
    closed: bool = False

class SlaConfigUpdate(BaseModel):
    monday: Optional[BusinessHoursConfig] = None
    tuesday: Optional[BusinessHoursConfig] = None
    wednesday: Optional[BusinessHoursConfig] = None
    thursday: Optional[BusinessHoursConfig] = None
    friday: Optional[BusinessHoursConfig] = None
    saturday: Optional[BusinessHoursConfig] = None
    sunday: Optional[BusinessHoursConfig] = None
    sla_orcamento_mecanica: Optional[int] = None
    sla_orcamento_pneus: Optional[int] = None
    sla_informacao: Optional[int] = None
    sla_reclamacao: Optional[int] = None
    sla_marcacao: Optional[int] = None
    sla_interno: Optional[int] = None
    sla_default: Optional[int] = None
    first_response_hours: Optional[int] = None
    quote_response_hours: Optional[int] = None
    enabled: Optional[bool] = None
    use_business_hours: Optional[bool] = None
    pause_on_aguarda_cliente: Optional[bool] = None

class SlaConfigResponse(BaseModel):
    monday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    tuesday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    wednesday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    thursday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    friday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="18:30", closed=False)
    saturday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="13:00", closed=False)
    sunday: BusinessHoursConfig = BusinessHoursConfig(start="08:30", end="13:00", closed=True)
    sla_orcamento_mecanica: int = 8
    sla_orcamento_pneus: int = 8
    sla_informacao: int = 2
    sla_reclamacao: int = 2
    sla_marcacao: int = 3
    sla_interno: int = 8
    sla_default: int = 2
    first_response_hours: int = 2
    quote_response_hours: int = 24
    enabled: bool = True
    use_business_hours: bool = True
    pause_on_aguarda_cliente: bool = True

class EmailConfigUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_use_tls: Optional[bool] = None
    email_from: Optional[str] = None
    email_from_name: Optional[str] = None
    frontend_url: Optional[str] = None

class EmailConfigResponse(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_use_ssl: bool = True
    smtp_use_tls: bool = False
    email_from: Optional[str] = None
    email_from_name: str = "PDPV Tickets"
    frontend_url: Optional[str] = None

class BrandingConfigUpdate(BaseModel):
    company_name: Optional[str] = None
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    quote_header_text: Optional[str] = None
    quote_footer_text: Optional[str] = None
    email_signature: Optional[str] = None

class BrandingConfigResponse(BaseModel):
    company_name: str = "PDPV Tickets"
    primary_color: str = "#f97316"
    logo_url: Optional[str] = None
    quote_header_text: str = "Proposta de Orçamento"
    quote_footer_text: str = "Obrigado pela sua preferência."
    email_signature: str = "Atenciosamente,\nA equipa PDPV"

class ReportFilters(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    assigned_to: Optional[str] = None
    channel: Optional[str] = None

class TicketMetrics(BaseModel):
    total_tickets: int = 0
    tickets_by_status: Dict[str, int] = {}
    tickets_by_type: Dict[str, int] = {}
    tickets_by_channel: Dict[str, int] = {}
    avg_resolution_time_hours: Optional[float] = None
    sla_compliance_rate: float = 0.0
    tickets_overdue: int = 0
    quotes_sent: int = 0
    quotes_accepted: int = 0
    quotes_rejected: int = 0
    total_quote_value: float = 0.0

class AgentPerformance(BaseModel):
    user_id: str
    user_name: str
    tickets_assigned: int = 0
    tickets_closed: int = 0
    avg_response_time_hours: Optional[float] = None
    sla_compliance_rate: float = 0.0

class ReportResponse(BaseModel):
    period: Dict[str, Optional[str]]
    metrics: TicketMetrics
    agent_performance: List[AgentPerformance] = []
    daily_ticket_counts: List[Dict[str, Any]] = []

class TireSizeCount(BaseModel):
    size: str
    count: int
    percentage: float

class BrandCount(BaseModel):
    brand: str
    count: int
    percentage: float

class TireAnalysisResponse(BaseModel):
    total_tickets: int
    tire_sizes: List[TireSizeCount]
    brands: List[BrandCount]
    period: Dict[str, Optional[str]]

class RejectionReasonStat(BaseModel):
    code: str
    label: str
    count: int
    percentage: float

class RejectionByTicketType(BaseModel):
    type: str
    count: int
    percentage: float

class RejectionReasonsResponse(BaseModel):
    total_rejected: int
    with_reason: int = 0
    without_reason: int = 0
    by_reason: List[RejectionReasonStat] = []
    by_ticket_type: List[RejectionByTicketType] = []
    period: Dict[str, Optional[str]] = {}

class TireSizeStat(BaseModel):
    size: str
    count: int
    percentage: float

class TireBrandStat(BaseModel):
    brand: str
    count: int

class TireKeywordStat(BaseModel):
    keyword: str
    count: int

class TireAnalysisResponse(BaseModel):
    total_tickets_analyzed: int
    tickets_with_sizes: int
    tire_sizes: List[TireSizeStat] = []
    brands: List[TireBrandStat] = []
    keywords: List[TireKeywordStat] = []


# ============== HELPERS ==============
def build_sla_config_response(config: dict) -> SlaConfigResponse:
    def get_day_config(config: dict, day: str, default_start: str, default_end: str, default_closed: bool) -> BusinessHoursConfig:
        day_data = config.get(day, {})
        if isinstance(day_data, dict):
            return BusinessHoursConfig(
                start=day_data.get("start", default_start),
                end=day_data.get("end", default_end),
                closed=day_data.get("closed", default_closed)
            )
        return BusinessHoursConfig(start=default_start, end=default_end, closed=default_closed)
    
    return SlaConfigResponse(
        monday=get_day_config(config, "monday", "08:30", "18:30", False),
        tuesday=get_day_config(config, "tuesday", "08:30", "18:30", False),
        wednesday=get_day_config(config, "wednesday", "08:30", "18:30", False),
        thursday=get_day_config(config, "thursday", "08:30", "18:30", False),
        friday=get_day_config(config, "friday", "08:30", "18:30", False),
        saturday=get_day_config(config, "saturday", "08:30", "13:00", False),
        sunday=get_day_config(config, "sunday", "08:30", "13:00", True),
        sla_orcamento_mecanica=config.get("sla_orcamento_mecanica", 8),
        sla_orcamento_pneus=config.get("sla_orcamento_pneus", 8),
        sla_informacao=config.get("sla_informacao", 2),
        sla_reclamacao=config.get("sla_reclamacao", 2),
        sla_marcacao=config.get("sla_marcacao", 3),
        sla_interno=config.get("sla_interno", 8),
        sla_default=config.get("sla_default", 2),
        first_response_hours=config.get("first_response_hours", 2),
        quote_response_hours=config.get("quote_response_hours", 24),
        enabled=config.get("enabled", True),
        use_business_hours=config.get("use_business_hours", True),
        pause_on_aguarda_cliente=config.get("pause_on_aguarda_cliente", True)
    )


# ============== TICKET TYPES ==============
@router.get("/ticket-types", response_model=List[TicketTypeResponse])
async def list_ticket_types(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver tipos")
    
    types = await db.ticket_types.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)
    
    if not types:
        default_types = [
            {"id": str(uuid.uuid4()), "code": "ORCAMENTO_PNEUS", "label": "Orçamento Pneus", "color": "#f97316", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ORCAMENTO_MECANICA", "label": "Orçamento Mecânica", "color": "#3b82f6", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "MARCACAO", "label": "Marcação", "color": "#10b981", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "INFORMACAO", "label": "Informação", "color": "#8b5cf6", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "INTERNO", "label": "Interno", "color": "#6b7280", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "RECLAMACAO", "label": "Reclamação", "color": "#ef4444", "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        await db.ticket_types.insert_many(default_types)
        types = default_types
    
    return [TicketTypeResponse(**t) for t in types]


@router.post("/ticket-types", response_model=TicketTypeResponse)
async def create_ticket_type(type_data: TicketTypeCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar tipos")
    
    existing = await db.ticket_types.find_one({"code": type_data.code})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um tipo com este código")
    
    type_doc = {
        "id": str(uuid.uuid4()),
        "code": type_data.code.upper().replace(" ", "_"),
        "label": type_data.label,
        "color": type_data.color,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.ticket_types.insert_one(type_doc)
    return TicketTypeResponse(**type_doc)


@router.put("/ticket-types/{type_id}", response_model=TicketTypeResponse)
async def update_ticket_type(type_id: str, type_data: TicketTypeUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar tipos")
    
    type_doc = await db.ticket_types.find_one({"id": type_id}, {"_id": 0})
    if not type_doc:
        raise HTTPException(status_code=404, detail="Tipo não encontrado")
    
    update_doc = {}
    if type_data.label:
        update_doc["label"] = type_data.label
    if type_data.color:
        update_doc["color"] = type_data.color
    
    if update_doc:
        await db.ticket_types.update_one({"id": type_id}, {"$set": update_doc})
    
    updated = await db.ticket_types.find_one({"id": type_id}, {"_id": 0})
    return TicketTypeResponse(**updated)


@router.delete("/ticket-types/{type_id}")
async def delete_ticket_type(type_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar tipos")
    
    type_doc = await db.ticket_types.find_one({"id": type_id}, {"_id": 0})
    if not type_doc:
        raise HTTPException(status_code=404, detail="Tipo não encontrado")
    
    tickets_using = await db.tickets.count_documents({"type": type_doc["code"]})
    if tickets_using > 0:
        raise HTTPException(status_code=400, detail=f"Não é possível eliminar. {tickets_using} ticket(s) usam este tipo.")
    
    await db.ticket_types.delete_one({"id": type_id})
    return {"message": "Tipo eliminado"}


# ============== TICKET STATUSES ==============
@router.get("/ticket-statuses", response_model=List[TicketStatusResponse])
async def list_ticket_statuses_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver estados")
    
    statuses = await db.ticket_statuses.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)
    
    if not statuses:
        default_statuses = [
            {"id": str(uuid.uuid4()), "code": "ABERTO", "label": "Aberto", "color": "#3b82f6", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "EM_TRATAMENTO", "label": "Em Tratamento", "color": "#f59e0b", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGUARDA_CLIENTE", "label": "Aguarda Cliente", "color": "#8b5cf6", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "AGENDADO", "label": "Agendado", "color": "#10b981", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "FECHADO", "label": "Fechado", "color": "#6b7280", "is_final": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "ACEITE_LINK", "label": "Aceite (Link)", "color": "#22c55e", "is_final": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "code": "REJEITADO_LINK", "label": "Rejeitado (Link)", "color": "#ef4444", "is_final": True, "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        await db.ticket_statuses.insert_many(default_statuses)
        statuses = default_statuses
    
    return [TicketStatusResponse(**s) for s in statuses]


@router.post("/ticket-statuses", response_model=TicketStatusResponse)
async def create_ticket_status(status_data: TicketStatusCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar estados")
    
    existing = await db.ticket_statuses.find_one({"code": status_data.code})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um estado com este código")
    
    status_doc = {
        "id": str(uuid.uuid4()),
        "code": status_data.code.upper().replace(" ", "_"),
        "label": status_data.label,
        "color": status_data.color,
        "is_final": status_data.is_final,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.ticket_statuses.insert_one(status_doc)
    return TicketStatusResponse(**status_doc)


@router.put("/ticket-statuses/{status_id}", response_model=TicketStatusResponse)
async def update_ticket_status(status_id: str, status_data: TicketStatusUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar estados")
    
    status_doc = await db.ticket_statuses.find_one({"id": status_id}, {"_id": 0})
    if not status_doc:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    update_doc = {}
    if status_data.label is not None:
        update_doc["label"] = status_data.label
    if status_data.color is not None:
        update_doc["color"] = status_data.color
    if status_data.is_final is not None:
        update_doc["is_final"] = status_data.is_final
    
    if update_doc:
        await db.ticket_statuses.update_one({"id": status_id}, {"$set": update_doc})
    
    updated = await db.ticket_statuses.find_one({"id": status_id}, {"_id": 0})
    return TicketStatusResponse(**updated)


@router.delete("/ticket-statuses/{status_id}")
async def delete_ticket_status(status_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar estados")
    
    status_doc = await db.ticket_statuses.find_one({"id": status_id}, {"_id": 0})
    if not status_doc:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    tickets_using = await db.tickets.count_documents({"status": status_doc["code"]})
    if tickets_using > 0:
        raise HTTPException(status_code=400, detail=f"Não é possível eliminar. {tickets_using} ticket(s) usam este estado.")
    
    await db.ticket_statuses.delete_one({"id": status_id})
    return {"message": "Estado eliminado"}


# ============== SLA CONFIG ==============
@router.get("/sla-config", response_model=SlaConfigResponse)
async def get_sla_config(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração SLA")
    
    config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
    if not config:
        return SlaConfigResponse()
    
    return build_sla_config_response(config)


@router.put("/sla-config", response_model=SlaConfigResponse)
async def update_sla_config(config_data: SlaConfigUpdate, current_user: dict = Depends(get_current_user)):
    from server import load_sla_config_from_db
    
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configuração SLA")
    
    existing = await db.settings.find_one({"type": "sla_config"})
    
    update_doc = {"type": "sla_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        day_config = getattr(config_data, day, None)
        if day_config is not None:
            update_doc[day] = day_config.model_dump()
    
    if config_data.sla_orcamento_mecanica is not None:
        update_doc["sla_orcamento_mecanica"] = config_data.sla_orcamento_mecanica
    if config_data.sla_orcamento_pneus is not None:
        update_doc["sla_orcamento_pneus"] = config_data.sla_orcamento_pneus
    if config_data.sla_informacao is not None:
        update_doc["sla_informacao"] = config_data.sla_informacao
    if config_data.sla_reclamacao is not None:
        update_doc["sla_reclamacao"] = config_data.sla_reclamacao
    if config_data.sla_marcacao is not None:
        update_doc["sla_marcacao"] = config_data.sla_marcacao
    if config_data.sla_interno is not None:
        update_doc["sla_interno"] = config_data.sla_interno
    if config_data.sla_default is not None:
        update_doc["sla_default"] = config_data.sla_default
    if config_data.first_response_hours is not None:
        update_doc["first_response_hours"] = config_data.first_response_hours
    if config_data.quote_response_hours is not None:
        update_doc["quote_response_hours"] = config_data.quote_response_hours
    if config_data.enabled is not None:
        update_doc["enabled"] = config_data.enabled
    if config_data.use_business_hours is not None:
        update_doc["use_business_hours"] = config_data.use_business_hours
    if config_data.pause_on_aguarda_cliente is not None:
        update_doc["pause_on_aguarda_cliente"] = config_data.pause_on_aguarda_cliente
    
    if existing:
        await db.settings.update_one({"type": "sla_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    await load_sla_config_from_db()
    
    config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
    return build_sla_config_response(config)


# ============== EMAIL CONFIG ==============
@router.get("/email-config", response_model=EmailConfigResponse)
async def get_email_config(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver configuração de email")
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    if not config:
        return EmailConfigResponse()
    
    return EmailConfigResponse(
        smtp_host=config.get("smtp_host"),
        smtp_port=config.get("smtp_port"),
        smtp_username=config.get("smtp_username"),
        smtp_use_ssl=config.get("smtp_use_ssl", True),
        smtp_use_tls=config.get("smtp_use_tls", False),
        email_from=config.get("email_from"),
        email_from_name=config.get("email_from_name", "PDPV Tickets"),
        frontend_url=config.get("frontend_url")
    )


@router.put("/email-config", response_model=EmailConfigResponse)
async def update_email_config(config_data: EmailConfigUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar configuração de email")
    
    existing = await db.settings.find_one({"type": "email_config"})
    
    update_doc = {"type": "email_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    if config_data.smtp_host is not None:
        update_doc["smtp_host"] = config_data.smtp_host
    if config_data.smtp_port is not None:
        update_doc["smtp_port"] = config_data.smtp_port
    if config_data.smtp_username is not None:
        update_doc["smtp_username"] = config_data.smtp_username
    if config_data.smtp_password is not None:
        update_doc["smtp_password"] = config_data.smtp_password
    if config_data.smtp_use_ssl is not None:
        update_doc["smtp_use_ssl"] = config_data.smtp_use_ssl
    if config_data.smtp_use_tls is not None:
        update_doc["smtp_use_tls"] = config_data.smtp_use_tls
    if config_data.email_from is not None:
        update_doc["email_from"] = config_data.email_from
    if config_data.email_from_name is not None:
        update_doc["email_from_name"] = config_data.email_from_name
    if config_data.frontend_url is not None:
        update_doc["frontend_url"] = config_data.frontend_url
    
    if existing:
        await db.settings.update_one({"type": "email_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    return EmailConfigResponse(
        smtp_host=config.get("smtp_host"),
        smtp_port=config.get("smtp_port"),
        smtp_username=config.get("smtp_username"),
        smtp_use_ssl=config.get("smtp_use_ssl", True),
        smtp_use_tls=config.get("smtp_use_tls", False),
        email_from=config.get("email_from"),
        email_from_name=config.get("email_from_name", "PDPV Tickets"),
        frontend_url=config.get("frontend_url")
    )


class TestEmailRequest(BaseModel):
    recipient_email: str


@router.post("/test-email")
async def send_test_email(request: TestEmailRequest, current_user: dict = Depends(get_current_user)):
    """Send a test email to verify SMTP configuration - ADMIN only"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem enviar emails de teste")
    
    config = await db.settings.find_one({"type": "email_config"}, {"_id": 0})
    if not config:
        raise HTTPException(status_code=400, detail="Configuração de email não encontrada")
    
    smtp_host = config.get("smtp_host")
    smtp_port = config.get("smtp_port", 587)
    smtp_username = config.get("smtp_username")
    smtp_password = config.get("smtp_password")
    smtp_use_tls = config.get("smtp_use_tls", True)
    smtp_use_ssl = config.get("smtp_use_ssl", False)
    email_from = config.get("email_from", smtp_username)
    email_from_name = config.get("email_from_name", "PDPV Tickets")
    
    if not smtp_host or not smtp_username or not smtp_password:
        raise HTTPException(status_code=400, detail="Configuração SMTP incompleta")
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"{email_from_name} <{email_from}>"
        msg['To'] = request.recipient_email
        msg['Subject'] = "Teste de Configuração SMTP - PDPV Tickets"
        
        body = """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #f97316;">Teste de Email</h2>
            <p>Este é um email de teste do sistema PDPV Tickets.</p>
            <p>Se recebeu este email, a configuração SMTP está correcta!</p>
            <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #6b7280; font-size: 12px;">
                Email enviado automaticamente pelo sistema PDPV Tickets
            </p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))
        
        # Connect and send
        if smtp_use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            if smtp_use_tls:
                server.starttls()
        
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
        return {"message": f"Email de teste enviado para {request.recipient_email}"}
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="Erro de autenticação SMTP. Verifique username e password.")
    except smtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail=f"Não foi possível conectar ao servidor {smtp_host}:{smtp_port}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar email: {str(e)}")


# ============== BRANDING CONFIG ==============
@router.get("/branding", response_model=BrandingConfigResponse)
async def get_branding(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver branding")
    
    config = await db.settings.find_one({"type": "branding_config"}, {"_id": 0})
    if not config:
        return BrandingConfigResponse()
    
    return BrandingConfigResponse(
        company_name=config.get("company_name", "PDPV Tickets"),
        primary_color=config.get("primary_color", "#f97316"),
        logo_url=config.get("logo_url"),
        quote_header_text=config.get("quote_header_text", "Proposta de Orçamento"),
        quote_footer_text=config.get("quote_footer_text", "Obrigado pela sua preferência."),
        email_signature=config.get("email_signature", "Atenciosamente,\nA equipa PDPV")
    )


@router.put("/branding", response_model=BrandingConfigResponse)
async def update_branding(config_data: BrandingConfigUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar branding")
    
    existing = await db.settings.find_one({"type": "branding_config"})
    
    update_doc = {"type": "branding_config", "updated_at": datetime.now(timezone.utc).isoformat()}
    
    if config_data.company_name is not None:
        update_doc["company_name"] = config_data.company_name
    if config_data.primary_color is not None:
        update_doc["primary_color"] = config_data.primary_color
    if config_data.logo_url is not None:
        update_doc["logo_url"] = config_data.logo_url
    if config_data.quote_header_text is not None:
        update_doc["quote_header_text"] = config_data.quote_header_text
    if config_data.quote_footer_text is not None:
        update_doc["quote_footer_text"] = config_data.quote_footer_text
    if config_data.email_signature is not None:
        update_doc["email_signature"] = config_data.email_signature
    
    if existing:
        await db.settings.update_one({"type": "branding_config"}, {"$set": update_doc})
    else:
        await db.settings.insert_one(update_doc)
    
    config = await db.settings.find_one({"type": "branding_config"}, {"_id": 0})
    return BrandingConfigResponse(
        company_name=config.get("company_name", "PDPV Tickets"),
        primary_color=config.get("primary_color", "#f97316"),
        logo_url=config.get("logo_url"),
        quote_header_text=config.get("quote_header_text", "Proposta de Orçamento"),
        quote_footer_text=config.get("quote_footer_text", "Obrigado pela sua preferência."),
        email_signature=config.get("email_signature", "Atenciosamente,\nA equipa PDPV")
    )


# ============== REPORTS ==============
@router.post("/reports", response_model=ReportResponse)
async def generate_report(filters: ReportFilters, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver relatórios")
    
    query = {"archived_at": None}
    
    if filters.start_date:
        query["created_at"] = {"$gte": filters.start_date}
    if filters.end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = filters.end_date
        else:
            query["created_at"] = {"$lte": filters.end_date}
    if filters.status:
        query["status"] = filters.status
    if filters.type:
        query["type"] = filters.type
    if filters.assigned_to:
        query["assigned_to_user_id"] = filters.assigned_to
    if filters.channel:
        query["channel"] = filters.channel
    
    tickets = await db.tickets.find(query, {"_id": 0}).to_list(10000)
    
    metrics = TicketMetrics()
    metrics.total_tickets = len(tickets)
    
    status_counts = {}
    type_counts = {}
    channel_counts = {}
    overdue_count = 0
    quotes_sent = 0
    quotes_accepted = 0
    quotes_rejected = 0
    total_quote_value = 0.0
    sla_compliant = 0
    
    for t in tickets:
        status = t.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        
        ticket_type = t.get("type", "UNKNOWN")
        type_counts[ticket_type] = type_counts.get(ticket_type, 0) + 1
        
        channel = t.get("channel", "UNKNOWN")
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        
        if t.get("first_response_done"):
            sla_compliant += 1
        elif t.get("sla_due"):
            try:
                sla_due = datetime.fromisoformat(t["sla_due"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > sla_due:
                    overdue_count += 1
            except ValueError:
                pass
        
        if t.get("quote_sent"):
            quotes_sent += 1
            if t.get("quote_value"):
                total_quote_value += t["quote_value"]
        if t.get("quote_response_status") == "ACCEPTED":
            quotes_accepted += 1
        elif t.get("quote_response_status") == "REJECTED":
            quotes_rejected += 1
    
    metrics.tickets_by_status = status_counts
    metrics.tickets_by_type = type_counts
    metrics.tickets_by_channel = channel_counts
    metrics.tickets_overdue = overdue_count
    metrics.quotes_sent = quotes_sent
    metrics.quotes_accepted = quotes_accepted
    metrics.quotes_rejected = quotes_rejected
    metrics.total_quote_value = total_quote_value
    
    if metrics.total_tickets > 0:
        metrics.sla_compliance_rate = round((sla_compliant / metrics.total_tickets) * 100, 1)
    
    agent_performance = []
    agents = await db.users.find(
        {"role": {"$in": [UserRole.AGENT.value, UserRole.SUPERVISOR.value]}},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    
    for agent in agents:
        agent_tickets = [t for t in tickets if t.get("assigned_to_user_id") == agent["id"]]
        closed_tickets = [t for t in agent_tickets if t.get("status") == "FECHADO"]
        compliant = sum(1 for t in agent_tickets if t.get("first_response_done"))
        
        perf = AgentPerformance(
            user_id=agent["id"],
            user_name=agent["name"],
            tickets_assigned=len(agent_tickets),
            tickets_closed=len(closed_tickets),
            sla_compliance_rate=round((compliant / len(agent_tickets) * 100), 1) if agent_tickets else 0
        )
        agent_performance.append(perf)
    
    daily_counts = []
    if not filters.start_date:
        start = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        start = datetime.fromisoformat(filters.start_date.replace("Z", "+00:00"))
    
    end = datetime.now(timezone.utc) if not filters.end_date else datetime.fromisoformat(filters.end_date.replace("Z", "+00:00"))
    
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        day_count = sum(1 for t in tickets if t.get("created_at", "").startswith(date_str))
        daily_counts.append({"date": date_str, "count": day_count})
        current += timedelta(days=1)
    
    return ReportResponse(
        period={"start": filters.start_date, "end": filters.end_date},
        metrics=metrics,
        agent_performance=agent_performance,
        daily_ticket_counts=daily_counts[-30:]
    )


@router.get("/reports/rejection-reasons", response_model=RejectionReasonsResponse)
async def get_rejection_reasons_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver relatórios")
    
    # Get ALL rejected tickets (with or without reason)
    query = {"quote_response_status": "REJECTED"}
    
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    if ticket_type:
        query["type"] = ticket_type
    if assigned_to:
        query["assigned_to_user_id"] = assigned_to
    
    tickets = await db.tickets.find(query, {
        "_id": 0, "rejection_reason_code": 1, "rejection_reason_label": 1, "type": 1
    }).to_list(10000)
    
    total = len(tickets)
    with_reason = 0
    without_reason = 0
    reason_counts = {}
    type_counts = {}
    
    for t in tickets:
        code = t.get("rejection_reason_code")
        if code:
            with_reason += 1
            label = t.get("rejection_reason_label") or REJECTION_REASON_CODES.get(code, "Sem motivo registado")
            if code not in reason_counts:
                reason_counts[code] = {"label": label, "count": 0}
            reason_counts[code]["count"] += 1
        else:
            without_reason += 1
        
        ticket_type_val = t.get("type", "UNKNOWN")
        type_counts[ticket_type_val] = type_counts.get(ticket_type_val, 0) + 1
    
    by_reason = []
    for code, data in sorted(reason_counts.items(), key=lambda x: x[1]["count"], reverse=True):
        by_reason.append(RejectionReasonStat(
            code=code,
            label=data["label"],
            count=data["count"],
            percentage=round((data["count"] / total * 100), 1) if total > 0 else 0
        ))
    
    by_ticket_type = []
    for ttype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        by_ticket_type.append(RejectionByTicketType(
            type=ttype,
            count=count,
            percentage=round((count / total * 100), 1) if total > 0 else 0
        ))
    
    return RejectionReasonsResponse(
        total_rejected=total,
        with_reason=with_reason,
        without_reason=without_reason,
        by_reason=by_reason,
        by_ticket_type=by_ticket_type,
        period={"start": start_date, "end": end_date}
    )


# ============== TIRE ANALYSIS ==============
import re

TIRE_SIZE_PATTERN = re.compile(r'\b(\d{3})\s*[/\\]\s*(\d{2,3})\s*[RrZz]?\s*(\d{2})\b')
TIRE_BRANDS = [
    "michelin", "continental", "bridgestone", "goodyear", "pirelli", "dunlop",
    "hankook", "yokohama", "firestone", "toyo", "kumho", "nexen", "falken",
    "cooper", "bf goodrich", "bfgoodrich", "uniroyal", "barum", "semperit",
    "nokian", "vredestein", "lassa", "nankang", "maxxis", "general tire",
    "general", "kleber", "sava", "debica", "matador", "viking", "gt radial",
    "triangle", "landsail", "roadstone", "imperial", "tracmax", "minerva",
    "westlake", "zeetex", "sailun", "rovelo", "aplus", "windforce", "boto",
    "davanti", "gripmax", "hifly"
]
SERVICE_KEYWORDS = {
    "montagem": ["montagem", "montar", "monte"],
    "equilibragem": ["equilibragem", "equilibrar", "balanceamento"],
    "alinhamento": ["alinhamento", "alinhar", "alinhamento direcção"],
    "substituição": ["substituição", "substituir", "troca", "trocar"],
    "reparação": ["reparação", "reparar", "arranjo", "arranjar"],
    "inspeção": ["inspeção", "inspecção", "ipo", "revisão"],
    "óleo": ["óleo", "oleo", "vidro óleo"],
    "travões": ["travões", "travoes", "pastilhas", "discos"],
    "amortecedores": ["amortecedores", "amortecedor", "suspensão"],
    "pneus usados": ["usados", "usado", "recauchutado", "recauchutagem"],
    "pneus novos": ["novos", "novo"],
    "jantes": ["jante", "jantes"],
    "válvulas": ["válvula", "valvula", "válvulas", "valvulas"],
    "furos": ["furo", "furos", "furado"]
}

@router.get("/reports/tire-analysis", response_model=TireAnalysisResponse)
async def get_tire_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para ver relatórios")
    
    query = {"archived_at": None}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    tickets = await db.tickets.find(query, {"_id": 0, "description": 1, "subject": 1}).to_list(10000)
    
    total_analyzed = len(tickets)
    tickets_with_sizes = 0
    size_counts = {}
    brand_counts = {}
    keyword_counts = {}
    
    for t in tickets:
        text = f"{t.get('subject', '')} {t.get('description', '')}".strip()
        if not text:
            continue
        text_lower = text.lower()
        
        # Extract tire sizes
        sizes = TIRE_SIZE_PATTERN.findall(text)
        if sizes:
            tickets_with_sizes += 1
            for width, aspect, rim in sizes:
                size_str = f"{width}/{aspect}R{rim}"
                size_counts[size_str] = size_counts.get(size_str, 0) + 1
        
        # Extract brands
        for brand in TIRE_BRANDS:
            if brand in text_lower:
                display_brand = brand.title()
                if display_brand == "Bf Goodrich":
                    display_brand = "BF Goodrich"
                elif display_brand == "Gt Radial":
                    display_brand = "GT Radial"
                brand_counts[display_brand] = brand_counts.get(display_brand, 0) + 1
        
        # Extract service keywords
        for service, variants in SERVICE_KEYWORDS.items():
            for variant in variants:
                if variant in text_lower:
                    keyword_counts[service] = keyword_counts.get(service, 0) + 1
                    break
    
    total_sizes = sum(size_counts.values()) or 1
    tire_sizes = sorted(
        [TireSizeStat(size=s, count=c, percentage=round(c / total_sizes * 100, 1))
         for s, c in size_counts.items()],
        key=lambda x: x.count, reverse=True
    )
    brands = sorted(
        [TireBrandStat(brand=b, count=c) for b, c in brand_counts.items()],
        key=lambda x: x.count, reverse=True
    )
    keywords = sorted(
        [TireKeywordStat(keyword=k, count=c) for k, c in keyword_counts.items()],
        key=lambda x: x.count, reverse=True
    )
    
    return TireAnalysisResponse(
        total_tickets_analyzed=total_analyzed,
        tickets_with_sizes=tickets_with_sizes,
        tire_sizes=tire_sizes,
        brands=brands,
        keywords=keywords
    )


# ============== HOLIDAYS ==============
class HolidayCreate(BaseModel):
    date: str  # YYYY-MM-DD format
    name: str
    is_recurring_annual: bool = False
    scope: str = "nacional"  # nacional, local
    active: bool = True

class HolidayUpdate(BaseModel):
    date: Optional[str] = None
    name: Optional[str] = None
    is_recurring_annual: Optional[bool] = None
    scope: Optional[str] = None
    active: Optional[bool] = None

class HolidayResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    date: str
    name: str
    is_recurring_annual: bool
    scope: str
    active: bool
    created_at: str


@router.get("/holidays", response_model=List[HolidayResponse])
async def list_holidays(
    active_only: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """List all holidays - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver feriados")
    
    query = {}
    if active_only:
        query["active"] = True
    
    holidays = await db.holidays.find(query, {"_id": 0}).sort("date", 1).to_list(1000)
    return [HolidayResponse(**h) for h in holidays]


@router.post("/holidays", response_model=HolidayResponse)
async def create_holiday(holiday_data: HolidayCreate, current_user: dict = Depends(get_current_user)):
    """Create a new holiday - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar feriados")
    
    # Validate date format
    try:
        datetime.strptime(holiday_data.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD")
    
    # Check for duplicate date
    existing = await db.holidays.find_one({"date": holiday_data.date})
    if existing:
        raise HTTPException(status_code=400, detail=f"Já existe um feriado na data {holiday_data.date}")
    
    holiday_doc = {
        "id": str(uuid.uuid4()),
        "date": holiday_data.date,
        "name": holiday_data.name,
        "is_recurring_annual": holiday_data.is_recurring_annual,
        "scope": holiday_data.scope,
        "active": holiday_data.active,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.holidays.insert_one(holiday_doc)
    
    # Reload holidays in SLA service
    from services.sla_service import load_holidays_from_db
    await load_holidays_from_db(db)
    
    return HolidayResponse(**holiday_doc)


@router.put("/holidays/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(holiday_id: str, holiday_data: HolidayUpdate, current_user: dict = Depends(get_current_user)):
    """Update a holiday - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar feriados")
    
    holiday = await db.holidays.find_one({"id": holiday_id}, {"_id": 0})
    if not holiday:
        raise HTTPException(status_code=404, detail="Feriado não encontrado")
    
    update_doc = {}
    
    if holiday_data.date is not None:
        # Validate date format
        try:
            datetime.strptime(holiday_data.date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD")
        
        # Check for duplicate date (excluding current)
        existing = await db.holidays.find_one({"date": holiday_data.date, "id": {"$ne": holiday_id}})
        if existing:
            raise HTTPException(status_code=400, detail=f"Já existe um feriado na data {holiday_data.date}")
        update_doc["date"] = holiday_data.date
    
    if holiday_data.name is not None:
        update_doc["name"] = holiday_data.name
    if holiday_data.is_recurring_annual is not None:
        update_doc["is_recurring_annual"] = holiday_data.is_recurring_annual
    if holiday_data.scope is not None:
        update_doc["scope"] = holiday_data.scope
    if holiday_data.active is not None:
        update_doc["active"] = holiday_data.active
    
    if update_doc:
        await db.holidays.update_one({"id": holiday_id}, {"$set": update_doc})
    
    # Reload holidays in SLA service
    from services.sla_service import load_holidays_from_db
    await load_holidays_from_db(db)
    
    updated = await db.holidays.find_one({"id": holiday_id}, {"_id": 0})
    return HolidayResponse(**updated)


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(holiday_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a holiday - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar feriados")
    
    holiday = await db.holidays.find_one({"id": holiday_id}, {"_id": 0})
    if not holiday:
        raise HTTPException(status_code=404, detail="Feriado não encontrado")
    
    await db.holidays.delete_one({"id": holiday_id})
    
    # Reload holidays in SLA service
    from services.sla_service import load_holidays_from_db
    await load_holidays_from_db(db)
    
    return {"message": "Feriado eliminado"}


@router.post("/holidays/{holiday_id}/toggle")
async def toggle_holiday(holiday_id: str, current_user: dict = Depends(get_current_user)):
    """Toggle holiday active status - ADMIN only"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar feriados")
    
    holiday = await db.holidays.find_one({"id": holiday_id}, {"_id": 0})
    if not holiday:
        raise HTTPException(status_code=404, detail="Feriado não encontrado")
    
    new_status = not holiday.get("active", True)
    await db.holidays.update_one({"id": holiday_id}, {"$set": {"active": new_status}})
    
    # Reload holidays in SLA service
    from services.sla_service import load_holidays_from_db
    await load_holidays_from_db(db)
    
    return {"message": f"Feriado {'activado' if new_status else 'desactivado'}", "active": new_status}
