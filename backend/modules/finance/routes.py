"""
CRM Finance Module - API Routes
Endpoints para gestão operacional de cobranças
"""
import os
import re
import uuid
import logging
import hashlib
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import db
from core.security import get_current_user
from .models import (
    # Enums
    FinanceRole, FinancialStatus, TrafficLight,
    ImportType, ImportStatus, ImportSourceMethod,
    DocumentClassification, DocumentActionType, ActionType, DelayReason,
    PromiseStatus, BlockRequestStatus, DataHealthStatus,
    # Request/Response
    FinanceClientResponse, FinanceClientListResponse,
    FinanceDocumentResponse,
    FinanceImportResponse, FinanceImportListResponse, ImportTotals,
    FinanceActionCreate, FinanceActionResponse,
    FinancePromiseCreate, FinancePromiseUpdate, FinancePromiseResponse,
    BlockRequestCreate, BlockRequestReview, BlockRequestResponse,
    DataHealthResponse, DataHealthListResponse,
    DashboardResponse, AgingBucket, TopDebtor,
    CollectionsTodayResponse, CollectionItem,
    RegularizationsResponse, RegularizationItem,
    DocumentActionCreate,
    FinanceSettingsUpdate,
    EmailTemplateCreate, EmailTemplateUpdate, EmailTemplateResponse, EmailTemplateListResponse,
)
from .permissions import (
    require_finance_access,
    require_finance_reviewer,
    require_finance_owner,
    require_collections_agent,
    can_approve_imports,
    get_finance_role,
    can_manage_blocks,
    check_permission,
)
from .services.import_service import (
    process_overdue_balances_import,
    process_client_info_import,
    process_credit_evolution_import,
    process_open_documents_import,
    get_finance_settings,
    recompute_documents_and_clients,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/finance", tags=["finance"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "finance_imports"


# ============== DATA HEALTH ==============

@router.get("/data-health", response_model=DataHealthListResponse)
async def get_data_health(current_user: dict = Depends(require_finance_access)):
    """
    Retorna o estado de saúde dos dados (última importação, avisos, bloqueios).
    """
    health_items = []
    any_blocking = False
    
    # Definir tipos e frequências
    source_configs = [
        (ImportType.OVERDUE_BALANCES, "daily", True),
        (ImportType.OPEN_DOCUMENTS, "daily", False),
        (ImportType.CLIENT_INFO, "weekly", False),
        (ImportType.CREDIT_EVOLUTION, "quarterly", False),
    ]
    
    for import_type, frequency, is_critical in source_configs:
        # Buscar última importação bem sucedida
        last_import = await db.finance_imports.find_one(
            {"type": import_type.value, "status": {"$in": ["imported", "accepted", "accepted_with_warnings"]}},
            {"_id": 0},
            sort=[("uploaded_at", -1)]
        )
        
        # Calcular estado
        status = DataHealthStatus.OK
        is_blocking = False
        message = None
        
        if not last_import:
            status = DataHealthStatus.BLOCKING if is_critical else DataHealthStatus.WARNING
            is_blocking = is_critical
            message = "Nenhuma importação realizada"
        else:
            # Verificar se está desatualizado
            last_date_str = last_import.get("as_of_date") or last_import.get("uploaded_at", "")[:10]
            if last_date_str:
                try:
                    last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00")).date() if "T" in last_date_str else date.fromisoformat(last_date_str)
                    today = date.today()
                    days_old = (today - last_date).days
                    
                    if frequency == "daily" and days_old >= 1:
                        status = DataHealthStatus.BLOCKING if is_critical else DataHealthStatus.WARNING
                        is_blocking = is_critical
                        message = f"Dados com {days_old} dia(s) de atraso"
                    elif frequency == "weekly" and days_old >= 7:
                        status = DataHealthStatus.WARNING
                        message = f"Dados com {days_old} dia(s) de atraso"
                    elif frequency == "quarterly" and days_old >= 92:
                        status = DataHealthStatus.WARNING
                        message = f"Dados com {days_old} dia(s) de atraso"
                except:
                    pass
        
        if is_blocking:
            any_blocking = True
        
        health_items.append(DataHealthResponse(
            source_type=import_type,
            required_frequency=frequency,
            last_import_id=last_import.get("id") if last_import else None,
            last_import_at=last_import.get("uploaded_at") if last_import else None,
            last_as_of_date=last_import.get("as_of_date") if last_import else None,
            status=status,
            is_blocking_operations=is_blocking,
            message=message
        ))
    
    return DataHealthListResponse(items=health_items, any_blocking=any_blocking)


# ============== DASHBOARD ==============

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(current_user: dict = Depends(require_finance_access)):
    """
    Dashboard financeiro com métricas principais.
    """
    # Agregar totais dos clientes (inclui residuais — contam na dívida contabilística)
    pipeline = [
        {"$group": {
            "_id": None,
            "total_balance": {"$sum": "$total_balance"},
            "total_overdue_accounting": {"$sum": "$overdue_balance_accounting"},
            "total_overdue_collectable": {"$sum": "$overdue_balance_collectable"},
            "total_residual": {"$sum": "$residual_balance"},
            "clients_with_overdue": {"$sum": {"$cond": [{"$gt": ["$overdue_balance_collectable", 0]}, 1, 0]}},
            "clients_blocked": {"$sum": {"$cond": ["$is_blocked", 1, 0]}},
        }}
    ]
    
    agg_result = await db.finance_clients.aggregate(pipeline).to_list(1)
    totals = agg_result[0] if agg_result else {}
    
    # Contar promessas
    promises_active = await db.finance_promises.count_documents({"status": PromiseStatus.OPEN.value})
    promises_failed = await db.finance_promises.count_documents({"status": PromiseStatus.FAILED.value})
    
    # Calcular aging buckets
    aging_pipeline = [
        {"$match": {"overdue_balance_collectable": {"$gt": 0}}},
        {"$project": {
            "bucket": {
                "$switch": {
                    "branches": [
                        {"case": {"$lte": ["$oldest_overdue_days", 30]}, "then": "0-30"},
                        {"case": {"$lte": ["$oldest_overdue_days", 60]}, "then": "31-60"},
                        {"case": {"$lte": ["$oldest_overdue_days", 90]}, "then": "61-90"},
                    ],
                    "default": "+90"
                }
            },
            "overdue_balance_collectable": 1
        }},
        {"$group": {
            "_id": "$bucket",
            "client_count": {"$sum": 1},
            "total_amount": {"$sum": "$overdue_balance_collectable"}
        }}
    ]
    
    aging_result = await db.finance_clients.aggregate(aging_pipeline).to_list(10)
    aging_map = {r["_id"]: r for r in aging_result}
    
    aging_buckets = []
    for label in ["0-30", "31-60", "61-90", "+90"]:
        data = aging_map.get(label, {})
        aging_buckets.append(AgingBucket(
            range_label=label,
            client_count=data.get("client_count", 0),
            total_amount=data.get("total_amount", 0.0)
        ))
    
    # Top 10 devedores
    top_debtors_cursor = db.finance_clients.find(
        {"overdue_balance_collectable": {"$gt": 0}},
        {"_id": 0}
    ).sort("overdue_balance_collectable", -1).limit(10)
    
    top_debtors = []
    async for client in top_debtors_cursor:
        top_debtors.append(TopDebtor(
            client_id=client["id"],
            client_name=client["name"],
            genes_code=client["genes_code"],
            overdue_amount=client["overdue_balance_collectable"],
            oldest_days=client.get("oldest_overdue_days", 0),
            traffic_light=TrafficLight(client.get("traffic_light", "GREEN"))
        ))
    
    # Última importação
    last_import = await db.finance_imports.find_one(
        {"type": ImportType.OVERDUE_BALANCES.value, "status": "imported"},
        {"_id": 0, "uploaded_at": 1},
        sort=[("uploaded_at", -1)]
    )
    
    # Verificar se dados estão atualizados
    data_health = await get_data_health(current_user)
    
    # Valor recuperado (eventos da comparação diária)
    today_str = date.today().isoformat()
    week_start = (date.today() - timedelta(days=6)).isoformat()
    month_start = date.today().replace(day=1).isoformat()
    min_date = min(week_start, month_start)
    recovered_today = recovered_week = recovered_month = 0.0
    async for ev in db.finance_recovery_events.find({"date": {"$gte": min_date}}, {"_id": 0, "date": 1, "amount": 1}):
        amt = ev.get("amount", 0) or 0
        if ev["date"] >= month_start:
            recovered_month += amt
        if ev["date"] >= week_start:
            recovered_week += amt
        if ev["date"] == today_str:
            recovered_today += amt
    
    return DashboardResponse(
        total_balance=totals.get("total_balance", 0.0),
        total_overdue_accounting=totals.get("total_overdue_accounting", 0.0),
        total_overdue_collectable=totals.get("total_overdue_collectable", 0.0),
        total_residual=totals.get("total_residual", 0.0),
        clients_with_overdue=totals.get("clients_with_overdue", 0),
        clients_blocked=totals.get("clients_blocked", 0),
        promises_active=promises_active,
        promises_failed=promises_failed,
        aging_buckets=aging_buckets,
        top_debtors=top_debtors,
        last_import_at=last_import.get("uploaded_at") if last_import else None,
        data_is_current=not data_health.any_blocking,
        recovered_today=round(recovered_today, 2),
        recovered_week=round(recovered_week, 2),
        recovered_month=round(recovered_month, 2)
    )


# ============== COLLECTIONS TODAY ==============

@router.get("/overdue-evolution")
async def get_overdue_evolution(
    days: int = 30,
    current_user: dict = Depends(require_finance_access),
):
    """Time series of daily overdue-collectable evolution + recovered vs newly-overdue split.

    For each of the last N days that had at least one import, returns:
      - date (YYYY-MM-DD)
      - total_overdue_collectable (aggregated from finance_client_daily_metrics)
      - total_balance
      - recovered_amount (sum of finance_recovery_events for that date)
      - net_change (today_overdue - previous_day_overdue). Positive → dívida está a crescer;
        negativo → dívida está a diminuir.
      - newly_overdue (implicito): net_change + recovered_amount. Faturas que passaram a
        vencidas no dia. Se `newly_overdue > recovered`, a operação está a perder terreno.
    """
    days = max(1, min(days, 365))
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()

    # Aggregate daily overdue from snapshots
    snap_pipeline = [
        {"$match": {"date": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$date",
            "total_overdue_collectable": {"$sum": "$overdue_balance_collectable"},
            "total_overdue_accounting": {"$sum": "$overdue_balance_accounting"},
            "total_balance": {"$sum": "$total_balance"},
            "total_residual": {"$sum": "$residual_balance"},
            "clients": {"$sum": 1},
            "clients_with_overdue": {
                "$sum": {"$cond": [{"$gt": ["$overdue_balance_collectable", 0]}, 1, 0]}
            },
        }},
        {"$sort": {"_id": 1}},
    ]
    snaps = await db.finance_client_daily_metrics.aggregate(snap_pipeline).to_list(365)

    # Aggregate recovered per date
    rec_pipeline = [
        {"$match": {"date": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$date",
            "recovered_amount": {"$sum": "$amount"},
            "events": {"$sum": 1},
        }},
    ]
    recs = await db.finance_recovery_events.aggregate(rec_pipeline).to_list(365)
    rec_by_date = {r["_id"]: r for r in recs}

    # Build time series
    series = []
    prev_overdue = None
    for s in snaps:
        d = s["_id"]
        overdue = round(s.get("total_overdue_collectable", 0.0), 2)
        recovered = round((rec_by_date.get(d) or {}).get("recovered_amount", 0.0), 2)
        net_change = round(overdue - prev_overdue, 2) if prev_overdue is not None else 0.0
        # newly_overdue = net_change + recovered  → faturas que se tornaram vencidas
        # (só significativo quando há histórico do dia anterior)
        newly_overdue = round(net_change + recovered, 2) if prev_overdue is not None else 0.0
        series.append({
            "date": d,
            "total_overdue_collectable": overdue,
            "total_overdue_accounting": round(s.get("total_overdue_accounting", 0.0), 2),
            "total_balance": round(s.get("total_balance", 0.0), 2),
            "total_residual": round(s.get("total_residual", 0.0), 2),
            "clients_with_overdue": s.get("clients_with_overdue", 0),
            "recovered_amount": recovered,
            "recovered_events": (rec_by_date.get(d) or {}).get("events", 0),
            "net_change": net_change,
            "newly_overdue": newly_overdue,
        })
        prev_overdue = overdue

    # Summary: how much did overdue change across the whole window?
    summary = {
        "days_covered": len(series),
        "first_date": series[0]["date"] if series else None,
        "last_date": series[-1]["date"] if series else None,
        "overdue_at_start": series[0]["total_overdue_collectable"] if series else 0,
        "overdue_at_end": series[-1]["total_overdue_collectable"] if series else 0,
        "total_delta": round(
            series[-1]["total_overdue_collectable"] - series[0]["total_overdue_collectable"], 2
        ) if len(series) >= 2 else 0,
        "total_recovered": round(sum(p["recovered_amount"] for p in series), 2),
        "total_newly_overdue": round(sum(p["newly_overdue"] for p in series), 2),
    }
    return {"series": series, "summary": summary}


@router.get("/collections/today", response_model=CollectionsTodayResponse)
async def get_collections_today(
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    min_overdue: Optional[float] = Query(None, ge=0),
    max_overdue: Optional[float] = Query(None, ge=0),
    min_days: Optional[int] = Query(None, ge=0),
    max_days: Optional[int] = Query(None, ge=0),
    only_low_values: bool = Query(False, description="Apenas vencidos <= 5€"),
    only_old_docs: bool = Query(False, description="Apenas > 365 dias vencidos"),
    financial_status: Optional[FinancialStatus] = None,
    sort_by: str = Query(
        "priority",
        pattern="^(priority|overdue_asc|overdue_desc|total_asc|total_desc|days_asc|days_desc|last_action|financial_status|doc_count)$"
    ),
    current_user: dict = Depends(require_finance_access)
):
    """
    Lista de cobranças do dia - clientes prioritários para contactar.
    Suporta filtros por valor vencido, dias, estado financeiro e ordenação.
    """
    # Verificar se dados estão atualizados
    data_health = await get_data_health(current_user)
    
    if data_health.any_blocking:
        return CollectionsTodayResponse(
            items=[],
            total_items=0,
            total_value=0.0,
            is_blocked=True,
            block_message="Dados financeiros desatualizados. Para evitar cobranças incorretas, carregue o ficheiro atualizado."
        )
    
    # Buscar clientes para cobrança (excluir residuais, bloqueados sem ação pendente)
    query: dict = {
        "overdue_balance_collectable": {"$gt": 0},
        "is_residual_only": {"$ne": True},
        "financial_status": {"$nin": [
            FinancialStatus.REGULARIZACAO_TECNICA.value,
            FinancialStatus.OK.value
        ]}
    }

    if financial_status:
        query["financial_status"] = financial_status.value

    if min_overdue is not None or max_overdue is not None:
        overdue_q = query.get("overdue_balance_collectable", {"$gt": 0})
        if min_overdue is not None:
            overdue_q["$gte"] = min_overdue
        if max_overdue is not None:
            overdue_q["$lte"] = max_overdue
        query["overdue_balance_collectable"] = overdue_q

    if only_low_values:
        overdue_q = query.get("overdue_balance_collectable", {"$gt": 0})
        overdue_q["$lte"] = 5.0
        query["overdue_balance_collectable"] = overdue_q

    if min_days is not None or max_days is not None or only_old_docs:
        days_q: dict = {}
        if min_days is not None:
            days_q["$gte"] = min_days
        if max_days is not None:
            days_q["$lte"] = max_days
        if only_old_docs:
            days_q["$gt"] = max(days_q.get("$gt", 0), 365)
        query["oldest_overdue_days"] = days_q

    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"genes_code": {"$regex": search, "$options": "i"}},
        ]

    # Buscar clientes com promessas ativas/falhadas
    active_promises = await db.finance_promises.distinct("client_id", {"status": PromiseStatus.OPEN.value})
    failed_promises = await db.finance_promises.distinct("client_id", {"status": PromiseStatus.FAILED.value})
    active_promises_set = set(active_promises)
    failed_promises_set = set(failed_promises)

    # Ordenação Mongo (rápido)
    mongo_sort: List[tuple] = []
    if sort_by == "overdue_asc":
        mongo_sort = [("overdue_balance_collectable", 1)]
    elif sort_by == "overdue_desc":
        mongo_sort = [("overdue_balance_collectable", -1)]
    elif sort_by == "total_asc":
        mongo_sort = [("total_balance", 1)]
    elif sort_by == "total_desc":
        mongo_sort = [("total_balance", -1)]
    elif sort_by == "days_asc":
        mongo_sort = [("oldest_overdue_days", 1)]
    elif sort_by == "days_desc":
        mongo_sort = [("oldest_overdue_days", -1)]
    elif sort_by == "last_action":
        mongo_sort = [("last_action_at", 1)]
    elif sort_by == "financial_status":
        mongo_sort = [("financial_status", 1)]
    else:
        # priority | doc_count -> ordenação em Python
        mongo_sort = [("traffic_light", -1), ("overdue_balance_collectable", -1)]

    clients_cursor = db.finance_clients.find(query, {"_id": 0}).sort(mongo_sort).limit(limit)
    
    items = []
    total_value = 0.0

    # doc_count precisa de $lookup — fazer em Python (limitado por `limit`)
    doc_counts: dict[str, int] = {}
    if sort_by == "doc_count":
        pass  # calculado abaixo por cliente
    
    async for client in clients_cursor:
        client_id = client["id"]
        
        # Calcular score de prioridade
        priority_score = 0.0
        if client.get("traffic_light") == TrafficLight.CRITICAL.value:
            priority_score += 100
        elif client.get("traffic_light") == TrafficLight.RED.value:
            priority_score += 75
        elif client.get("traffic_light") == TrafficLight.ORANGE.value:
            priority_score += 50
        
        if client_id in failed_promises_set:
            priority_score += 30
        
        priority_score += min(client.get("oldest_overdue_days", 0) / 10, 20)
        priority_score += min(client.get("overdue_balance_collectable", 0) / 1000, 30)

        if sort_by == "doc_count":
            doc_counts[client_id] = await db.finance_documents.count_documents({
                "client_id": client_id,
                "effective_classification": DocumentClassification.COLLECTABLE.value,
                "amount_open": {"$gt": 0},
            })
        
        items.append(CollectionItem(
            client_id=client_id,
            client_name=client["name"],
            genes_code=client["genes_code"],
            total_balance=client.get("total_balance", 0.0),
            overdue_collectable=client.get("overdue_balance_collectable", 0.0),
            residual_balance=client.get("residual_balance", 0.0),
            oldest_overdue_days=client.get("oldest_overdue_days", 0),
            financial_status=FinancialStatus(client.get("financial_status", "EM_COBRANCA")),
            traffic_light=TrafficLight(client.get("traffic_light", "GREEN")),
            last_action_at=client.get("last_action_at"),
            next_action_date=client.get("next_action_date"),
            has_active_promise=client_id in active_promises_set,
            has_failed_promise=client_id in failed_promises_set,
            priority_score=priority_score
        ))
        
        total_value += client.get("overdue_balance_collectable", 0.0)
    
    # Ordenar por prioridade (default) ou doc_count
    if sort_by == "priority":
        items.sort(key=lambda x: x.priority_score, reverse=True)
    elif sort_by == "doc_count":
        items.sort(key=lambda x: doc_counts.get(x.client_id, 0), reverse=True)
    
    return CollectionsTodayResponse(
        items=items,
        total_items=len(items),
        total_value=total_value,
        is_blocked=False,
        block_message=None
    )


# ============== CLIENTS ==============

@router.get("/clients", response_model=FinanceClientListResponse)
async def list_clients(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    status: Optional[FinancialStatus] = None,
    traffic_light: Optional[TrafficLight] = None,
    has_overdue: Optional[bool] = None,
    is_blocked: Optional[bool] = None,
    current_user: dict = Depends(require_finance_access)
):
    """
    Lista clientes financeiros com filtros.
    """
    query = {}
    
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"genes_code": {"$regex": search, "$options": "i"}},
        ]
    
    if status:
        query["financial_status"] = status.value
    
    if traffic_light:
        query["traffic_light"] = traffic_light.value
    
    if has_overdue is True:
        query["overdue_balance_collectable"] = {"$gt": 0}
    elif has_overdue is False:
        query["overdue_balance_collectable"] = {"$lte": 0}
    
    if is_blocked is not None:
        query["is_blocked"] = is_blocked
    
    # Contar total
    total = await db.finance_clients.count_documents(query)
    
    # Buscar página
    skip = (page - 1) * page_size
    clients_cursor = db.finance_clients.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(page_size)
    
    clients = []
    async for client in clients_cursor:
        clients.append(FinanceClientResponse(**client))
    
    return FinanceClientListResponse(
        clients=clients,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/clients/{client_id}", response_model=FinanceClientResponse)
async def get_client(client_id: str, current_user: dict = Depends(require_finance_access)):
    """
    Detalhes de um cliente financeiro.
    """
    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Anexar evolução trimestral de crédito, se existir
    evo = await db.finance_credit_evolution.find_one({"genes_code": client.get("genes_code")}, {"_id": 0})
    if evo:
        client["credit_evolution"] = evo.get("evolution")
        client["credit_trend_percentage"] = evo.get("trend_percentage")
        client["credit_trend_absolute"] = evo.get("trend_absolute")
    
    return FinanceClientResponse(**client)


@router.get("/clients/{client_id}/documents")
async def get_client_documents(
    client_id: str,
    classification: Optional[DocumentClassification] = None,
    current_user: dict = Depends(require_finance_access)
):
    """
    Documentos de um cliente.
    """
    query = {"client_id": client_id}
    if classification:
        query["classification"] = classification.value
    
    docs_cursor = db.finance_documents.find(query, {"_id": 0}).sort("due_date", 1)
    docs = await docs_cursor.to_list(500)
    
    return {"documents": [FinanceDocumentResponse(**d) for d in docs]}


@router.get("/clients/{client_id}/history")
async def get_client_history(
    client_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_finance_access)
):
    """
    Histórico de ações/contactos de um cliente.
    """
    actions_cursor = db.finance_actions.find(
        {"client_id": client_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    
    actions = await actions_cursor.to_list(limit)
    
    return {"actions": [FinanceActionResponse(**a) for a in actions]}


# ============== ACTIONS ==============

@router.post("/clients/{client_id}/actions", response_model=FinanceActionResponse)
async def create_action(
    client_id: str,
    action: FinanceActionCreate,
    current_user: dict = Depends(require_collections_agent)
):
    """
    Registar contacto/ação num cliente.
    """
    # Verificar cliente existe
    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0, "id": 1})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    action_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "action_type": action.action_type.value,
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "notes": action.notes,
        "delay_reason": action.delay_reason.value if action.delay_reason else None,
        "next_action_date": action.next_action_date,
        "created_at": now
    }
    
    await db.finance_actions.insert_one(action_doc)
    
    # Atualizar cliente
    update_data = {
        "last_action_at": now,
        "updated_at": now
    }
    if action.next_action_date:
        update_data["next_action_date"] = action.next_action_date
    
    await db.finance_clients.update_one(
        {"id": client_id},
        {"$set": update_data}
    )
    
    logger.info(f"Finance action created: {action.action_type.value} for client {client_id} by user {current_user['id']}")
    
    return FinanceActionResponse(**action_doc)


# ============== PROMISES ==============

@router.get("/promises")
async def list_promises(
    status: Optional[PromiseStatus] = None,
    client_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_finance_access)
):
    """
    Listar promessas de pagamento.
    """
    query = {}
    if status:
        query["status"] = status.value
    if client_id:
        query["client_id"] = client_id
    
    promises_cursor = db.finance_promises.find(query, {"_id": 0}).sort("promise_date", 1).limit(limit)
    promises = await promises_cursor.to_list(limit)
    
    # Enriquecer com nome do cliente
    client_ids = list({p["client_id"] for p in promises})
    clients_map = {}
    if client_ids:
        async for c in db.finance_clients.find({"id": {"$in": client_ids}}, {"_id": 0, "id": 1, "name": 1, "genes_code": 1}):
            clients_map[c["id"]] = c
    
    for p in promises:
        client = clients_map.get(p["client_id"], {})
        p["client_name"] = client.get("name")
        p["genes_code"] = client.get("genes_code")
    
    return {"promises": [FinancePromiseResponse(**p) for p in promises]}


@router.post("/clients/{client_id}/promises", response_model=FinancePromiseResponse)
async def create_promise(
    client_id: str,
    promise: FinancePromiseCreate,
    current_user: dict = Depends(require_collections_agent)
):
    """
    Criar promessa de pagamento.
    """
    # Verificar cliente existe
    client = await db.finance_clients.find_one(
        {"id": client_id}, {"_id": 0, "id": 1, "name": 1, "overdue_balance_accounting": 1}
    )
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    promise_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "baseline_overdue": client.get("overdue_balance_accounting", 0),
        "amount": promise.amount,
        "promise_date": promise.promise_date,
        "status": PromiseStatus.OPEN.value,
        "notes": promise.notes,
        "linked_document_ids": promise.linked_document_ids,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
        "created_at": now,
        "verified_at": None,
        "verified_import_id": None
    }
    
    await db.finance_promises.insert_one(promise_doc)
    
    # Atualizar estado do cliente para PROMESSA_ATIVA
    await db.finance_clients.update_one(
        {"id": client_id},
        {"$set": {
            "financial_status": FinancialStatus.PROMESSA_ATIVA.value,
            "updated_at": now
        }}
    )
    
    # Registar ação
    action_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "action_type": ActionType.PROMISE_CREATED.value,
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "notes": f"Promessa de {promise.amount}€ para {promise.promise_date}",
        "created_at": now
    }
    await db.finance_actions.insert_one(action_doc)
    
    logger.info(f"Promise created for client {client_id}: {promise.amount}€ by user {current_user['id']}")
    
    return FinancePromiseResponse(**promise_doc)


@router.patch("/promises/{promise_id}", response_model=FinancePromiseResponse)
async def update_promise(
    promise_id: str,
    update: FinancePromiseUpdate,
    current_user: dict = Depends(require_collections_agent)
):
    """
    Atualizar promessa de pagamento.
    """
    promise = await db.finance_promises.find_one({"id": promise_id}, {"_id": 0})
    if not promise:
        raise HTTPException(status_code=404, detail="Promessa não encontrada")
    
    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}
    
    if update.status:
        update_data["status"] = update.status.value
    if update.notes is not None:
        update_data["notes"] = update.notes
    
    await db.finance_promises.update_one({"id": promise_id}, {"$set": update_data})
    
    # Se promessa falhou, atualizar estado do cliente
    if update.status == PromiseStatus.FAILED:
        await db.finance_clients.update_one(
            {"id": promise["client_id"]},
            {"$set": {
                "financial_status": FinancialStatus.PROMESSA_FALHADA.value,
                "updated_at": now
            }}
        )
    
    updated = await db.finance_promises.find_one({"id": promise_id}, {"_id": 0})
    return FinancePromiseResponse(**updated)


# ============== BLOCKS ==============

@router.get("/block-requests")
async def list_block_requests(
    status: Optional[BlockRequestStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_finance_reviewer)
):
    """
    Listar pedidos de bloqueio.
    """
    query = {}
    if status:
        query["status"] = status.value
    
    requests_cursor = db.finance_block_requests.find(query, {"_id": 0}).sort("suggested_at", -1).limit(limit)
    requests = await requests_cursor.to_list(limit)
    
    return {"requests": [BlockRequestResponse(**r) for r in requests]}


@router.post("/clients/{client_id}/suggest-block", response_model=BlockRequestResponse)
async def suggest_block(
    client_id: str,
    request: BlockRequestCreate,
    current_user: dict = Depends(require_collections_agent)
):
    """
    Sugerir bloqueio de um cliente.
    """
    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    if client.get("is_blocked"):
        raise HTTPException(status_code=400, detail="Cliente já está bloqueado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    block_request = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "client_name": client["name"],
        "suggested_by": current_user["id"],
        "suggested_by_name": current_user.get("name", ""),
        "suggested_at": now,
        "reason": request.reason,
        "status": BlockRequestStatus.PENDING.value,
        "reviewed_by": None,
        "reviewed_by_name": None,
        "reviewed_at": None,
        "review_notes": None
    }
    
    await db.finance_block_requests.insert_one(block_request)
    
    # Atualizar estado do cliente
    await db.finance_clients.update_one(
        {"id": client_id},
        {"$set": {
            "financial_status": FinancialStatus.BLOQUEIO_SUGERIDO.value,
            "updated_at": now
        }}
    )
    
    # Registar ação
    action_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "action_type": ActionType.BLOCK_SUGGESTED.value,
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "notes": f"Bloqueio sugerido: {request.reason}",
        "created_at": now
    }
    await db.finance_actions.insert_one(action_doc)
    
    logger.info(f"Block suggested for client {client_id} by user {current_user['id']}")
    
    return BlockRequestResponse(**block_request)


@router.post("/block-requests/{request_id}/review", response_model=BlockRequestResponse)
async def review_block_request(
    request_id: str,
    review: BlockRequestReview,
    current_user: dict = Depends(require_finance_reviewer)
):
    """
    Aprovar ou rejeitar pedido de bloqueio.
    """
    block_request = await db.finance_block_requests.find_one({"id": request_id}, {"_id": 0})
    if not block_request:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if block_request["status"] != BlockRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Pedido já foi processado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    new_status = BlockRequestStatus.APPROVED if review.approved else BlockRequestStatus.REJECTED
    
    await db.finance_block_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": new_status.value,
            "reviewed_by": current_user["id"],
            "reviewed_by_name": current_user.get("name", ""),
            "reviewed_at": now,
            "review_notes": review.review_notes
        }}
    )
    
    client_id = block_request["client_id"]
    
    if review.approved:
        # Bloquear cliente
        await db.finance_clients.update_one(
            {"id": client_id},
            {"$set": {
                "is_blocked": True,
                "block_reason": block_request["reason"],
                "financial_status": FinancialStatus.BLOQUEADO.value,
                "updated_at": now
            }}
        )
        action_type = ActionType.BLOCK_APPROVED
    else:
        # Reverter estado
        await db.finance_clients.update_one(
            {"id": client_id},
            {"$set": {
                "financial_status": FinancialStatus.EM_COBRANCA.value,
                "updated_at": now
            }}
        )
        action_type = ActionType.BLOCK_REJECTED
    
    # Registar ação
    action_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "action_type": action_type.value,
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "notes": review.review_notes or ("Bloqueio aprovado" if review.approved else "Bloqueio rejeitado"),
        "created_at": now
    }
    await db.finance_actions.insert_one(action_doc)
    
    logger.info(f"Block request {request_id} {'approved' if review.approved else 'rejected'} by user {current_user['id']}")
    
    updated = await db.finance_block_requests.find_one({"id": request_id}, {"_id": 0})
    return BlockRequestResponse(**updated)


@router.post("/clients/{client_id}/unblock")
async def unblock_client(
    client_id: str,
    reason: str = Query(..., min_length=1),
    current_user: dict = Depends(require_finance_reviewer)
):
    """
    Desbloquear cliente.
    """
    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    if not client.get("is_blocked"):
        raise HTTPException(status_code=400, detail="Cliente não está bloqueado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Determinar novo estado baseado em dívida
    new_status = FinancialStatus.OK.value
    if client.get("overdue_balance_collectable", 0) > 0:
        new_status = FinancialStatus.EM_COBRANCA.value
    
    await db.finance_clients.update_one(
        {"id": client_id},
        {"$set": {
            "is_blocked": False,
            "block_reason": None,
            "financial_status": new_status,
            "updated_at": now
        }}
    )
    
    # Registar ação
    action_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "action_type": ActionType.UNBLOCKED.value,
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "notes": f"Desbloqueado: {reason}",
        "created_at": now
    }
    await db.finance_actions.insert_one(action_doc)
    
    logger.info(f"Client {client_id} unblocked by user {current_user['id']}")
    
    return {"success": True, "message": "Cliente desbloqueado"}


# ============== REGULARIZATIONS ==============

# Mapeamento sugestões -> label PT
_SUGGESTION_LABELS = {
    "validate_old_invoice": "Validar recibo/fatura antiga antes de cobrar.",
    "request_regularization": "Pedir regularização à contabilidade.",
    "review": "Rever internamente.",
    "ignore": "Ignorar operacionalmente.",
}


def _build_suggestion(classification: str, days_overdue: int, amount_open: float) -> tuple[str, str]:
    """Devolve (código, label) da sugestão para o documento."""
    if classification == DocumentClassification.MICRO_OLD.value:
        code = "validate_old_invoice"
    elif classification == DocumentClassification.RESIDUAL_ACCUMULATED.value:
        code = "request_regularization"
    elif classification == DocumentClassification.RESIDUAL.value:
        if amount_open < 0.10:
            code = "ignore"
        elif days_overdue > 365:
            code = "validate_old_invoice"
        else:
            code = "review"
    else:
        code = "review"
    return code, _SUGGESTION_LABELS[code]


@router.get("/regularizations", response_model=RegularizationsResponse)
async def get_regularizations(
    only_micro_old: bool = Query(False, description="Apenas micro-saldos antigos (>365 dias)"),
    only_residual: bool = Query(False, description="Apenas residuais (<=1€)"),
    only_low_values: bool = Query(False, description="Apenas valores <=1€"),
    min_days: Optional[int] = Query(None, ge=0),
    max_days: Optional[int] = Query(None, ge=0),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
    search: Optional[str] = None,
    sort_by: str = Query("days_overdue", pattern="^(days_overdue|amount_open|client_residual_balance|client_name)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(500, ge=1, le=2000),
    current_user: dict = Depends(require_finance_access)
):
    """
    Lista de documentos elegíveis para regularização (residuais, micro-saldos antigos,
    residuais acumulados). Devolve por documento, com sugestão específica e agregado
    do cliente. Suporta filtros e ordenação.
    """
    # Documentos elegíveis (usar effective_classification quando disponível)
    eligible_classifications = [
        DocumentClassification.RESIDUAL.value,
        DocumentClassification.MICRO_OLD.value,
        DocumentClassification.RESIDUAL_ACCUMULATED.value,
    ]

    query: dict = {
        "$and": [
            {"amount_open": {"$gt": 0}},
            {"$or": [
                {"effective_classification": {"$in": eligible_classifications}},
                {
                    "effective_classification": {"$exists": False},
                    "classification": {"$in": eligible_classifications},
                },
            ]},
            {"manually_marked_collectable": {"$ne": True}},
            {"manual_action": {"$nin": ["mark_resolved_operationally", "mark_collectable"]}},
        ]
    }

    if only_micro_old:
        query["classification"] = DocumentClassification.MICRO_OLD.value
    elif only_residual:
        query["classification"] = DocumentClassification.RESIDUAL.value

    if only_low_values:
        query["amount_open"] = {"$gt": 0, "$lte": 1}
    if min_amount is not None or max_amount is not None:
        amount_q: dict = query.get("amount_open", {"$gt": 0})
        if min_amount is not None:
            amount_q["$gte"] = min_amount
        if max_amount is not None:
            amount_q["$lte"] = max_amount
        query["amount_open"] = amount_q
    if min_days is not None or max_days is not None:
        days_q: dict = {}
        if min_days is not None:
            days_q["$gte"] = min_days
        if max_days is not None:
            days_q["$lte"] = max_days
        query["days_overdue"] = days_q

    # Cache de agregados de cliente (residual balance + doc count)
    client_cache: dict[str, dict] = {}

    # Precisamos de sort por campo derivado (client_residual_balance / client_name) —
    # nesse caso ordenamos em Python; caso contrário ordenamos em Mongo.
    mongo_sort_field = None
    if sort_by == "days_overdue":
        mongo_sort_field = "days_overdue"
    elif sort_by == "amount_open":
        mongo_sort_field = "amount_open"

    cursor = db.finance_documents.find(query, {"_id": 0})
    if mongo_sort_field:
        cursor = cursor.sort(mongo_sort_field, -1 if sort_dir == "desc" else 1)
    cursor = cursor.limit(limit)

    items: List[RegularizationItem] = []
    total_residual = 0.0
    seen_clients: set[str] = set()

    async for doc in cursor:
        client_id = doc.get("client_id")
        if not client_id:
            continue

        if client_id not in client_cache:
            client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0}) or {}
            residual_doc_count = await db.finance_documents.count_documents({
                "client_id": client_id,
                "manually_marked_collectable": {"$ne": True},
                "manual_action": {"$nin": ["mark_resolved_operationally", "mark_collectable"]},
                "$or": [
                    {"effective_classification": {"$in": eligible_classifications}},
                    {
                        "effective_classification": {"$exists": False},
                        "classification": {"$in": eligible_classifications},
                    },
                ],
            })
            client_cache[client_id] = {
                "client_name": client.get("name", "—"),
                "genes_code": client.get("genes_code", "—"),
                "residual_balance": client.get("residual_balance", 0.0),
                "residual_doc_count": residual_doc_count,
            }

        c = client_cache[client_id]

        if search:
            s = search.lower()
            if s not in c["client_name"].lower() and s not in str(c["genes_code"]).lower() and s not in doc.get("document_number", "").lower():
                continue

        # Filtrar clientes que só devem entrar em regularizações se residual total <= 5€
        # (regra: clientes com residual < 5€ vão para regularizações; acima disso podem
        # continuar em cobrança residual acumulada — mas ainda listamos aqui como aviso)
        classification = doc.get("classification", DocumentClassification.RESIDUAL.value)
        code, label = _build_suggestion(classification, doc.get("days_overdue", 0), doc.get("amount_open", 0))

        items.append(RegularizationItem(
            document_id=doc["id"],
            document_type=doc.get("document_type", "FT"),
            document_number=doc.get("document_number", "—"),
            invoice_date=doc.get("invoice_date"),
            due_date=doc.get("due_date"),
            amount_open=round(doc.get("amount_open", 0), 2),
            days_overdue=doc.get("days_overdue", 0),
            classification=DocumentClassification(classification),
            manual_action=doc.get("manual_action"),
            client_id=client_id,
            client_name=c["client_name"],
            genes_code=c["genes_code"],
            client_residual_balance=round(c["residual_balance"], 2),
            client_residual_document_count=c["residual_doc_count"],
            suggestion_code=code,
            suggestion_label=label,
        ))
        total_residual += doc.get("amount_open", 0)
        seen_clients.add(client_id)

    # Ordenação em Python quando o campo é derivado
    if sort_by in ("client_residual_balance", "client_name"):
        rev = sort_dir == "desc"
        keyfn = (
            (lambda i: i.client_residual_balance) if sort_by == "client_residual_balance"
            else (lambda i: i.client_name.lower())
        )
        items.sort(key=keyfn, reverse=rev)

    return RegularizationsResponse(
        items=items,
        total_residual=round(total_residual, 2),
        total_documents=len(items),
        total_clients=len(seen_clients),
    )


# --- Acção manual sobre documento ---
@router.post("/documents/{document_id:path}/action", response_model=FinanceDocumentResponse)
async def apply_document_action(
    document_id: str,
    payload: DocumentActionCreate,
    current_user: dict = Depends(require_collections_agent),
):
    """
    Aplica uma acção manual num documento (residual/micro-old/regularização).
    Recalcula automaticamente os agregados do cliente afectado.
    """
    doc = await db.finance_documents.find_one({"id": document_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    action = payload.action

    update: dict = {"updated_at": now}

    if action == DocumentActionType.MARK_COLLECTABLE:
        update["manually_marked_collectable"] = True
        update["manual_action"] = "mark_collectable"
        update["effective_classification"] = DocumentClassification.COLLECTABLE.value
    elif action == DocumentActionType.MARK_DISPUTE:
        update["manually_marked_collectable"] = False
        update["manual_action"] = "mark_dispute"
        update["effective_classification"] = DocumentClassification.DISPUTE.value
    elif action == DocumentActionType.MARK_RESOLVED_OPERATIONALLY:
        update["manually_marked_collectable"] = False
        update["manual_action"] = "mark_resolved_operationally"
        update["effective_classification"] = DocumentClassification.RESOLVED_OPERATIONALLY.value
    elif action == DocumentActionType.REGULARIZE_INTERNALLY:
        update["manually_marked_collectable"] = False
        update["manual_action"] = "regularize_internally"
        # mantém effective_classification actual (residual/micro-old) — apenas marca pedido
    elif action == DocumentActionType.KEEP_IN_COLLECTIONS:
        update["manually_marked_collectable"] = True
        update["manual_action"] = "keep_in_collections"
        update["effective_classification"] = DocumentClassification.COLLECTABLE.value
    elif action == DocumentActionType.RESET:
        update["manually_marked_collectable"] = False
        update["manual_action"] = None
        update["manual_action_reason"] = None
        update["manual_action_by"] = None
        update["manual_action_at"] = None
        # effective_classification volta a acompanhar `classification`
        update["effective_classification"] = doc.get("classification", DocumentClassification.RESIDUAL.value)

    if action != DocumentActionType.RESET:
        update["manual_action_reason"] = payload.reason
        update["manual_action_by"] = current_user["id"]
        update["manual_action_at"] = now

    await db.finance_documents.update_one({"id": document_id}, {"$set": update})

    # Log de acção do cliente
    if doc.get("client_id"):
        await db.finance_actions.insert_one({
            "id": str(uuid.uuid4()),
            "client_id": doc["client_id"],
            "action_type": ActionType.INTERNAL_REGULARIZATION.value,
            "user_id": current_user["id"],
            "user_name": current_user.get("name", ""),
            "notes": f"[{action.value}] doc {doc.get('document_type')} {doc.get('document_number')} · {payload.reason or ''}".strip(),
            "delay_reason": DelayReason.SALDO_RESIDUAL.value,
            "next_action_date": None,
            "created_at": now,
        })

    # Recomputar agregados (automático)
    try:
        await recompute_documents_and_clients(triggered_by=f"doc_action:{action.value}")
    except Exception as e:
        logger.exception(f"Recompute failed after doc action: {e}")

    updated_doc = await db.finance_documents.find_one({"id": document_id}, {"_id": 0})
    return FinanceDocumentResponse(**updated_doc)


# --- Recomputação manual ---
@router.post("/recompute")
async def trigger_recompute(
    dry_run: bool = Query(False),
    current_user: dict = Depends(require_finance_owner),
):
    """
    Aciona a recomputação global de classificações e agregados (apenas OWNER).
    Útil após alterar thresholds ou corrigir dados manualmente.
    """
    summary = await recompute_documents_and_clients(
        triggered_by=f"manual:{current_user['id']}",
        dry_run=dry_run,
    )
    return summary


# ============== IMPORTS ==============

@router.get("/imports", response_model=FinanceImportListResponse)
async def list_imports(
    type: Optional[ImportType] = None,
    status: Optional[ImportStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_finance_access)
):
    """
    Listar importações (paginado, mais recentes primeiro).
    """
    query = {}
    if type:
        query["type"] = type.value
    if status:
        query["status"] = status.value
    
    total = await db.finance_imports.count_documents(query)

    imports_cursor = (
        db.finance_imports.find(query, {"_id": 0})
        .sort("uploaded_at", -1)
        .skip(offset)
        .limit(limit)
    )
    imports = await imports_cursor.to_list(limit)
    
    # Enriquecer com nome do utilizador
    user_ids = list({i["uploaded_by"] for i in imports if i.get("uploaded_by")})
    users_map = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}):
            users_map[u["id"]] = u.get("name")
    
    for i in imports:
        i["uploaded_by_name"] = users_map.get(i.get("uploaded_by"))
    
    return FinanceImportListResponse(
        imports=[FinanceImportResponse(**i) for i in imports],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(imports)) < total,
    )


# ============== CLEANUP DE FICHEIROS DE IMPORTAÇÃO ==============
# NOTA: estas rotas TÊM de estar declaradas ANTES da rota genérica
# `POST /imports/{import_type}` para evitar que "cleanup" seja tratado como enum.

@router.get("/imports/cleanup/preview")
async def preview_imports_cleanup(
    older_than_days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_finance_reviewer),
):
    """
    Pré-visualização de ficheiros elegíveis para limpeza.
    Considera imports com status FAILED/REJECTED anteriores a `older_than_days`.
    Mantém sempre o registo de auditoria em `finance_imports` — apenas apaga
    o ficheiro binário original em disco.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    query = {
        "status": {"$in": [ImportStatus.FAILED.value, ImportStatus.REJECTED.value]},
        "uploaded_at": {"$lt": cutoff},
        "original_file_path": {"$exists": True, "$nin": [None, ""]},
    }

    items = []
    total_bytes = 0
    async for imp in db.finance_imports.find(query, {"_id": 0}):
        fp = imp.get("original_file_path")
        exists = False
        size = 0
        if fp:
            p = Path(fp)
            exists = p.exists()
            if exists:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
        total_bytes += size
        items.append({
            "id": imp["id"],
            "filename": imp.get("filename"),
            "status": imp["status"],
            "uploaded_at": imp["uploaded_at"],
            "file_exists_on_disk": exists,
            "file_size_bytes": size,
        })

    return {
        "cutoff_days": older_than_days,
        "cutoff_at": cutoff,
        "total_candidates": len(items),
        "total_bytes": total_bytes,
        "items": items,
    }


@router.post("/imports/cleanup")
async def cleanup_import_files(
    older_than_days: int = Query(30, ge=1, le=365),
    dry_run: bool = Query(False),
    current_user: dict = Depends(require_finance_owner),
):
    """
    Apaga ficheiros binários de imports FAILED/REJECTED mais antigos que N dias.
    NUNCA apaga o registo em `finance_imports` — auditoria preservada.
    Actualiza `original_file_path` para `null` e adiciona `file_cleaned_at`.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    query = {
        "status": {"$in": [ImportStatus.FAILED.value, ImportStatus.REJECTED.value]},
        "uploaded_at": {"$lt": cutoff},
        "original_file_path": {"$exists": True, "$nin": [None, ""]},
    }

    files_deleted = 0
    bytes_freed = 0
    errors: List[str] = []

    async for imp in db.finance_imports.find(query, {"_id": 0}):
        fp = imp.get("original_file_path")
        if not fp:
            continue
        p = Path(fp)
        size = 0
        if p.exists():
            try:
                size = p.stat().st_size
            except OSError:
                size = 0

            if not dry_run:
                try:
                    p.unlink()
                except OSError as e:
                    errors.append(f"{imp['id']}: {e}")
                    continue

        if not dry_run:
            await db.finance_imports.update_one(
                {"id": imp["id"]},
                {"$set": {
                    "original_file_path": None,
                    "file_cleaned_at": now,
                    "file_cleaned_by": current_user["id"],
                }}
            )

        files_deleted += 1
        bytes_freed += size

    logger.info(
        f"Finance imports cleanup by {current_user['id']}: "
        f"dry_run={dry_run} deleted={files_deleted} bytes_freed={bytes_freed}"
    )

    return {
        "dry_run": dry_run,
        "cutoff_days": older_than_days,
        "files_deleted": files_deleted,
        "bytes_freed": bytes_freed,
        "errors": errors,
    }


@router.post("/imports/{import_type}")
async def upload_import(
    import_type: ImportType,
    file: UploadFile = File(...),
    as_of_date: Optional[str] = Form(None),
    current_user: dict = Depends(require_finance_access)
):
    """
    Upload de ficheiro para importação.
    Valida e processa o ficheiro.
    """
    # Validar extensão
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Formato de ficheiro inválido. Use .xlsx ou .xls")
    
    # Ler conteúdo
    content = await file.read()
    
    # Calcular hash
    file_hash = hashlib.sha256(content).hexdigest()
    
    # Verificar duplicado
    existing = await db.finance_imports.find_one({"file_hash": file_hash}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=400, detail="Este ficheiro já foi importado anteriormente")
    
    now = datetime.now(timezone.utc).isoformat()
    import_id = str(uuid.uuid4())
    
    # Guardar ficheiro original (necessário para reprocessar após aprovação)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_file_path = UPLOAD_DIR / f"{import_id}.xlsx"
    original_file_path.write_bytes(content)
    
    # Criar registo de importação
    import_doc = {
        "id": import_id,
        "type": import_type.value,
        "source_method": ImportSourceMethod.MANUAL_UPLOAD.value,
        "filename": file.filename,
        "file_hash": file_hash,
        "as_of_date": as_of_date,
        "uploaded_by": current_user["id"],
        "uploaded_at": now,
        "status": ImportStatus.RECEIVED.value,
        "original_file_path": str(original_file_path),
        "totals": {
            "clients": 0,
            "documents": 0,
            "total_balance": 0,
            "total_overdue": 0,
            "total_collectable": 0,
            "total_residual": 0
        },
        "warnings": [],
        "errors": [],
        "approved_by": None,
        "approved_at": None
    }
    
    await db.finance_imports.insert_one(import_doc)
    
    logger.info(f"Import {import_type.value} received: {file.filename} by user {current_user['id']}")
    
    try:
        if import_type == ImportType.OVERDUE_BALANCES:
            result = await process_overdue_balances_import(
                import_id=import_id,
                file_content=content,
                uploaded_by=current_user["id"],
                as_of_date=as_of_date
            )
        elif import_type == ImportType.CLIENT_INFO:
            result = await process_client_info_import(
                import_id=import_id,
                file_content=content,
                uploaded_by=current_user["id"]
            )
        elif import_type == ImportType.CREDIT_EVOLUTION:
            result = await process_credit_evolution_import(
                import_id=import_id,
                file_content=content,
                uploaded_by=current_user["id"]
            )
        else:
            result = await process_open_documents_import(
                import_id=import_id,
                file_content=content,
                uploaded_by=current_user["id"],
                as_of_date=as_of_date
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing import: {e}")
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {
                "status": ImportStatus.FAILED.value,
                "errors": [str(e)]
            }}
        )
        raise HTTPException(status_code=500, detail=f"Erro ao processar ficheiro: {str(e)}")


@router.post("/imports/{import_id}/approve")
async def approve_import(
    import_id: str,
    current_user: dict = Depends(require_finance_reviewer)
):
    """
    Aprovar importação pendente — reprocessa o ficheiro original e aplica os dados.
    """
    import_doc = await db.finance_imports.find_one({"id": import_id}, {"_id": 0})
    if not import_doc:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    
    if import_doc["status"] != ImportStatus.PENDING_APPROVAL.value:
        raise HTTPException(status_code=400, detail="Esta importação não está pendente de aprovação")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Reprocessar o ficheiro original (dados só são aplicados agora)
    file_path = import_doc.get("original_file_path")
    if import_doc["type"] == ImportType.OVERDUE_BALANCES.value:
        if not file_path or not Path(file_path).exists():
            raise HTTPException(status_code=400, detail="Ficheiro original não disponível para reprocessamento")
        content = Path(file_path).read_bytes()
        result = await process_overdue_balances_import(
            import_id=import_id,
            file_content=content,
            uploaded_by=import_doc["uploaded_by"],
            as_of_date=import_doc.get("as_of_date"),
            force_approved=True
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Erro ao aplicar importação: {result.get('errors')}")
    else:
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {"status": ImportStatus.IMPORTED.value}}
        )
    
    await db.finance_imports.update_one(
        {"id": import_id},
        {"$set": {
            "approved_by": current_user["id"],
            "approved_at": now
        }}
    )
    
    logger.info(f"Import {import_id} approved by user {current_user['id']}")
    
    return {"success": True, "message": "Importação aprovada e dados aplicados"}


# ============== CONFIGURAÇÕES ==============

@router.get("/settings")
async def get_settings(current_user: dict = Depends(require_finance_access)):
    """Configurações do módulo Finance (thresholds residuais, avisos)."""
    return await get_finance_settings()


@router.put("/settings")
async def update_settings(
    payload: FinanceSettingsUpdate,
    current_user: dict = Depends(require_finance_owner)
):
    """Atualizar configurações (apenas OWNER). Aciona recomputação automática."""
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    
    await db.finance_settings.update_one(
        {"id": "global"},
        {"$set": {**update, "id": "global"}},
        upsert=True
    )
    
    logger.info(f"Finance settings updated by {current_user['id']}: {list(update.keys())}")

    # Auto-recompute quando thresholds relevantes forem alterados
    threshold_keys = {
        "residual_document_threshold",
        "residual_client_threshold",
        "residual_max_documents",
        "micro_old_days_threshold",
    }
    if threshold_keys & set(update.keys()):
        try:
            summary = await recompute_documents_and_clients(
                triggered_by=f"settings_update:{current_user['id']}"
            )
            logger.info(f"Auto-recompute after settings: {summary}")
        except Exception as e:
            logger.exception(f"Auto-recompute failed after settings update: {e}")

    settings = await get_finance_settings()
    return settings


# ============== AVISO DE CRÉDITO (TICKETS) ==============

@router.get("/credit-warning")
async def credit_warning(
    phone: str = Query(""),
    current_user: dict = Depends(get_current_user)
):
    """
    Verifica se deve mostrar o aviso genérico de validação financeira num ticket.
    Acessível a qualquer utilizador autenticado — NUNCA devolve valores financeiros.
    """
    settings = await get_finance_settings()
    if not settings.get("show_credit_warning_on_tickets", True):
        return {"show_warning": False}
    
    digits = re.sub(r"\D", "", phone or "")[-9:]
    if len(digits) < 9:
        return {"show_warning": False}
    
    async for c in db.finance_clients.find(
        {"$or": [{"is_blocked": True}, {"traffic_light": "CRITICAL"}]},
        {"_id": 0, "phone": 1, "mobile": 1}
    ):
        for p in [c.get("phone"), c.get("mobile")]:
            if p and re.sub(r"\D", "", str(p))[-9:] == digits:
                return {"show_warning": True}
    
    return {"show_warning": False}


# ============== EMAIL TEMPLATES (BD-backed) ==============
# Templates para comunicação manual — usados pelo QuickCommunicationPanel.
# CRUD é OWNER-only; listagem é acessível a qualquer finance_role.

DEFAULT_EMAIL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "key": "lembrete_amigavel",
        "label": "Lembrete amigável",
        "bucket_hint": "d0_15",
        "subject": "Lembrete de faturação em aberto",
        "body": (
            "Bom dia,\n\n"
            "Vimos por este meio lembrar que existem faturas em aberto. "
            "Junto envio a conta corrente atualizada.\n\n"
            "Se já efetuou o pagamento, ignore esta mensagem. Caso contrário, "
            "agradecemos a regularização assim que possível.\n\n"
            "Obrigado,\nPDPV Automóvel"
        ),
        "whatsapp_body": (
            "Olá, esta é uma mensagem da PDPV Automóvel a lembrar que existem faturas em aberto. "
            "Se já efetuou o pagamento, ignore esta mensagem. Obrigado."
        ),
    },
    {
        "key": "pedido_pagamento",
        "label": "Pedido de pagamento",
        "bucket_hint": "d16_30",
        "subject": "Pedido de regularização de faturas em aberto",
        "body": (
            "Bom dia,\n\n"
            "Registamos valores em atraso na vossa conta corrente. "
            "Pedimos a vossa colaboração para regularizar até ao final da semana ou "
            "nos dar retorno com data prevista de pagamento.\n\n"
            "Obrigado,\nPDPV Automóvel"
        ),
        "whatsapp_body": (
            "Olá, temos faturas em aberto que agradecíamos que fossem regularizadas até ao final da semana. Obrigado."
        ),
    },
    {
        "key": "pedido_comprovativo",
        "label": "Pedido de comprovativo",
        "bucket_hint": "generic",
        "subject": "Pedido de comprovativo de pagamento",
        "body": (
            "Bom dia,\n\n"
            "Referiu que efetuou o pagamento das faturas em aberto. "
            "Agradecíamos o envio do comprovativo para conciliação interna.\n\n"
            "Obrigado,\nPDPV Automóvel"
        ),
        "whatsapp_body": (
            "Olá, referiu que efetuou o pagamento. Pode enviar o comprovativo para conciliação? Obrigado."
        ),
    },
    {
        "key": "lembrete_promessa",
        "label": "Lembrete de promessa",
        "bucket_hint": "promise",
        "subject": "Lembrete — compromisso de pagamento acordado",
        "body": (
            "Bom dia,\n\n"
            "Lembramos o compromisso de pagamento acordado. Ficamos a aguardar "
            "o vosso comprovativo ou contacto.\n\n"
            "Obrigado,\nPDPV Automóvel"
        ),
        "whatsapp_body": (
            "Olá, a lembrar o compromisso de pagamento acordado. Ficamos a aguardar o vosso retorno. Obrigado."
        ),
    },
    {
        "key": "promessa_falhada",
        "label": "Promessa falhada",
        "bucket_hint": "d61_90",
        "subject": "Compromisso de pagamento não cumprido",
        "body": (
            "Bom dia,\n\n"
            "Verificamos que o pagamento acordado não foi ainda efetuado. "
            "Pedimos que nos contacte com urgência para revisão do plano de pagamento.\n\n"
            "PDPV Automóvel"
        ),
        "whatsapp_body": (
            "Olá, o pagamento acordado não foi ainda efetuado. Pedimos que nos contacte com urgência. Obrigado."
        ),
    },
    {
        "key": "plano_pagamento",
        "label": "Plano de pagamento",
        "bucket_hint": "d61_90",
        "subject": "Proposta de plano de pagamento",
        "body": (
            "Bom dia,\n\n"
            "Face aos valores em atraso, propomos um plano de pagamento faseado. "
            "Ficamos a aguardar a vossa resposta para acordarmos os detalhes.\n\n"
            "PDPV Automóvel"
        ),
        "whatsapp_body": (
            "Olá, gostaríamos de acordar um plano de pagamento faseado para os valores em atraso. Podemos falar? Obrigado."
        ),
    },
    {
        "key": "confirmar_email_contabilidade",
        "label": "Confirmar email financeiro",
        "bucket_hint": "generic",
        "subject": "Confirmação do email para envio de faturação",
        "body": (
            "Bom dia,\n\n"
            "Para garantir o correto envio de faturação e conta corrente, agradecíamos "
            "a confirmação do email financeiro/contabilidade a utilizar.\n\n"
            "Obrigado,\nPDPV Automóvel"
        ),
    },
    {
        "key": "aviso_bloqueio",
        "label": "Aviso pré-bloqueio",
        "bucket_hint": "d90p",
        "subject": "Aviso — validação financeira necessária",
        "body": (
            "Bom dia,\n\n"
            "Face aos valores em atraso, informamos que novos serviços poderão exigir "
            "validação financeira prévia. Ficamos ao dispor para regularizar a situação.\n\n"
            "PDPV Automóvel"
        ),
    },
]


async def _seed_default_email_templates_if_empty() -> None:
    """Popula templates default se a coleção estiver vazia. Chamada no startup."""
    count = await db.finance_email_templates.count_documents({})
    if count > 0:
        return
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for t in DEFAULT_EMAIL_TEMPLATES:
        docs.append({
            "id": str(uuid.uuid4()),
            "key": t["key"],
            "label": t["label"],
            "bucket_hint": t.get("bucket_hint"),
            "subject": t["subject"],
            "body": t["body"],
            "whatsapp_body": t.get("whatsapp_body"),
            "is_active": True,
            "created_by": None,
            "created_at": now,
            "updated_at": now,
        })
    if docs:
        await db.finance_email_templates.insert_many(docs)
        logger.info(f"Seeded {len(docs)} default finance email templates")


@router.get("/email-templates", response_model=EmailTemplateListResponse)
async def list_email_templates(
    active_only: bool = Query(True),
    bucket_hint: Optional[str] = None,
    current_user: dict = Depends(require_finance_access),
):
    """Lista templates de email/whatsapp para comunicação manual."""
    query: dict = {}
    if active_only:
        query["is_active"] = True
    if bucket_hint:
        query["bucket_hint"] = bucket_hint
    templates = []
    async for t in db.finance_email_templates.find(query, {"_id": 0}).sort([("bucket_hint", 1), ("label", 1)]):
        templates.append(EmailTemplateResponse(**t))
    return EmailTemplateListResponse(templates=templates, total=len(templates))


@router.post("/email-templates", response_model=EmailTemplateResponse)
async def create_email_template(
    payload: EmailTemplateCreate,
    current_user: dict = Depends(require_finance_owner),
):
    """Criar novo template (apenas OWNER)."""
    existing = await db.finance_email_templates.find_one({"key": payload.key}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=400, detail=f"Já existe template com key '{payload.key}'")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "created_by": current_user["id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.finance_email_templates.insert_one(doc)
    doc.pop("_id", None)
    return EmailTemplateResponse(**doc)


@router.put("/email-templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    payload: EmailTemplateUpdate,
    current_user: dict = Depends(require_finance_owner),
):
    """Atualizar template (apenas OWNER)."""
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.finance_email_templates.update_one({"id": template_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    doc = await db.finance_email_templates.find_one({"id": template_id}, {"_id": 0})
    return EmailTemplateResponse(**doc)


@router.delete("/email-templates/{template_id}")
async def delete_email_template(
    template_id: str,
    current_user: dict = Depends(require_finance_owner),
):
    """Apagar template (apenas OWNER). Recomenda-se desativar via `is_active=false`."""
    r = await db.finance_email_templates.delete_one({"id": template_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return {"success": True}


# ============== ENVIO REAL DE EMAIL (Resend) ==============
class SendEmailPayload(BaseModel):
    to: str = Field(..., min_length=3, max_length=200)
    subject: str = Field(..., min_length=1, max_length=250)
    body: str = Field(..., min_length=1, max_length=8000)
    template_key: Optional[str] = None
    linked_document_numbers: Optional[List[str]] = None


@router.post("/clients/{client_id}/send-email")
async def send_client_email(
    client_id: str,
    payload: SendEmailPayload,
    current_user: dict = Depends(require_collections_agent),
):
    """
    Envia um email via Resend em nome da PDPV.
    Se Resend não estiver configurado ou domínio não estiver verificado, guarda
    a acção como PENDING no histórico com um marcador `[SEND_FAILED]` — não bloqueia
    a operação da cobradora.

    Regras:
      - Cliente tem de existir.
      - Cliente com apenas saldo residual só pode receber email se current_user é
        FINANCE_REVIEWER ou OWNER (evita spam por engano à cobradora).
      - Todas as tentativas ficam gravadas em finance_actions.
    """
    import os
    import resend as _resend
    import asyncio as _asyncio

    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Guardrail: cliente apenas residual só pode receber email com aprovação
    if client.get("is_residual_only") and get_finance_role(current_user) == FinanceRole.COLLECTIONS_AGENT:
        raise HTTPException(
            status_code=403,
            detail="Cliente apenas com saldo residual — envio requer FINANCE_REVIEWER ou OWNER",
        )

    resend_key = os.environ.get("RESEND_API_KEY", "")
    email_from = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")

    now = datetime.now(timezone.utc).isoformat()
    action_id = str(uuid.uuid4())
    sent = False
    error_msg = None
    provider_id = None

    if resend_key:
        try:
            _resend.api_key = resend_key
            # Converter corpo texto em HTML simples (preservar linhas)
            html_body = payload.body.replace("\n", "<br/>")
            result = await _asyncio.to_thread(
                _resend.Emails.send,
                {
                    "from": email_from,
                    "to": [payload.to],
                    "subject": payload.subject,
                    "html": html_body,
                    "text": payload.body,
                },
            )
            provider_id = result.get("id") if isinstance(result, dict) else None
            sent = True
            logger.info(f"[FINANCE-RESEND] Sent to {payload.to}, id={provider_id}, template={payload.template_key}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[FINANCE-RESEND] Send failed to {payload.to}: {e}")
    else:
        error_msg = "RESEND_API_KEY não configurada"

    # Gravar sempre no histórico
    note_parts = [
        f"[Email {'ENVIADO' if sent else 'FALHOU'} → {payload.to}]",
        f"template={payload.template_key or '—'}",
        f"subject=\"{payload.subject}\"",
    ]
    if provider_id:
        note_parts.append(f"resend_id={provider_id}")
    if error_msg:
        note_parts.append(f"error={error_msg[:200]}")
    note = " ".join(note_parts) + "\n\n" + payload.body

    await db.finance_actions.insert_one({
        "id": action_id,
        "client_id": client_id,
        "action_type": ActionType.EMAIL.value,
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "notes": note[:4000],
        "delay_reason": None,
        "next_action_date": None,
        "created_at": now,
        "email_meta": {
            "to": payload.to,
            "subject": payload.subject,
            "template_key": payload.template_key,
            "linked_document_numbers": payload.linked_document_numbers or [],
            "sent": sent,
            "provider": "resend" if sent else None,
            "provider_id": provider_id,
            "error": error_msg,
        },
    })

    return {
        "sent": sent,
        "provider_id": provider_id,
        "error": error_msg,
        "action_id": action_id,
    }



# ============== RÉGUA DE COBRANÇA (dunning ladder) ==============
# Régua curta e determinística para orientar a cobradora — não é call-center automatizado.
# Bucket derivado de oldest_overdue_days + estado financeiro.

DUNNING_BUCKETS: List[Dict[str, Any]] = [
    {
        "key": "d0_15",
        "label": "D+0 a D+15 — Lembrete amigável",
        "min_days": 0, "max_days": 15,
        "tone": "friendly",
        "suggested_template_keys": ["lembrete_amigavel"],
        "suggested_actions": ["send_account_statement", "friendly_reminder"],
        "color": "green",
    },
    {
        "key": "d16_30",
        "label": "D+16 a D+30 — Contacto direto",
        "min_days": 16, "max_days": 30,
        "tone": "neutral",
        "suggested_template_keys": ["pedido_pagamento", "lembrete_amigavel"],
        "suggested_actions": ["send_account_statement", "call_direct", "request_confirmation"],
        "color": "yellow",
    },
    {
        "key": "d31_60",
        "label": "D+31 a D+60 — Pedido formal",
        "min_days": 31, "max_days": 60,
        "tone": "firm",
        "suggested_template_keys": ["pedido_pagamento", "pedido_comprovativo"],
        "suggested_actions": ["request_payment", "request_promise", "escalate_to_reviewer"],
        "color": "orange",
    },
    {
        "key": "d61_90",
        "label": "D+61 a D+90 — Promessa formal / Plano",
        "min_days": 61, "max_days": 90,
        "tone": "firm",
        "suggested_template_keys": ["promessa_falhada", "plano_pagamento"],
        "suggested_actions": ["formal_promise", "propose_payment_plan"],
        "color": "red",
    },
    {
        "key": "d90p",
        "label": "D+90+ — Sugerir bloqueio",
        "min_days": 91, "max_days": 120,
        "tone": "escalation",
        "suggested_template_keys": ["aviso_bloqueio", "plano_pagamento"],
        "suggested_actions": ["suggest_block", "review_dispute", "senior_review"],
        "color": "red",
    },
    {
        "key": "d120p",
        "label": "D+120+ — Decisão de gestão",
        "min_days": 121, "max_days": 100000,
        "tone": "escalation",
        "suggested_template_keys": ["aviso_bloqueio"],
        "suggested_actions": ["management_decision", "external_collection", "regularize_technical"],
        "color": "black",
    },
]


def _resolve_bucket(days: int, financial_status: Optional[str]) -> Dict[str, Any]:
    """Devolve o bucket da régua para um cliente."""
    # Estados especiais têm bucket próprio
    if financial_status == FinancialStatus.PROMESSA_ATIVA.value:
        return {
            "key": "promise",
            "label": "Com promessa ativa",
            "min_days": days, "max_days": days,
            "tone": "waiting",
            "suggested_template_keys": ["lembrete_promessa"],
            "suggested_actions": ["wait_promise", "monitor_progress"],
            "color": "blue",
        }
    if financial_status == FinancialStatus.EM_DISPUTA.value:
        return {
            "key": "dispute",
            "label": "Em disputa",
            "min_days": days, "max_days": days,
            "tone": "hold",
            "suggested_template_keys": ["pedido_comprovativo"],
            "suggested_actions": ["review_dispute", "wait_resolution"],
            "color": "purple",
        }
    if financial_status == FinancialStatus.BLOQUEADO.value:
        return {
            "key": "blocked",
            "label": "Cliente bloqueado",
            "min_days": days, "max_days": days,
            "tone": "hold",
            "suggested_template_keys": [],
            "suggested_actions": ["management_decision"],
            "color": "black",
        }

    for b in DUNNING_BUCKETS:
        if b["min_days"] <= days <= b["max_days"]:
            return b
    return DUNNING_BUCKETS[-1]


@router.get("/dunning-ladder")
async def get_dunning_ladder(current_user: dict = Depends(require_finance_access)):
    """Devolve a régua de cobrança estática (buckets + templates sugeridos)."""
    return {"buckets": DUNNING_BUCKETS}


@router.get("/clients/{client_id}/dunning-bucket")
async def get_client_dunning_bucket(
    client_id: str,
    current_user: dict = Depends(require_finance_access),
):
    """Devolve o bucket actual do cliente + templates sugeridos."""
    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    days = int(client.get("oldest_overdue_days", 0) or 0)
    status = client.get("financial_status")
    bucket = _resolve_bucket(days, status)

    # Enriquecer com templates completos
    templates: List[Dict[str, Any]] = []
    for key in bucket.get("suggested_template_keys", []):
        t = await db.finance_email_templates.find_one({"key": key, "is_active": True}, {"_id": 0})
        if t:
            templates.append(t)

    return {
        "client_id": client_id,
        "oldest_overdue_days": days,
        "financial_status": status,
        "bucket": bucket,
        "suggested_templates": templates,
    }

