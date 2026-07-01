"""
CRM Finance Module - API Routes
Endpoints para gestão operacional de cobranças
"""
import os
import uuid
import logging
import hashlib
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import JSONResponse

from db import db
from core.security import get_current_user
from .models import (
    # Enums
    FinanceRole, FinancialStatus, TrafficLight,
    ImportType, ImportStatus, ImportSourceMethod,
    DocumentClassification, ActionType, DelayReason,
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
)
from .permissions import (
    require_finance_access,
    require_finance_reviewer,
    require_finance_owner,
    require_collections_agent,
    can_approve_imports,
    can_manage_blocks,
    check_permission,
)
from .services.import_service import (
    process_overdue_balances_import,
    process_client_info_import,
    process_credit_evolution_import,
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
        data_is_current=not data_health.any_blocking
    )


# ============== COLLECTIONS TODAY ==============

@router.get("/collections/today", response_model=CollectionsTodayResponse)
async def get_collections_today(
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_finance_access)
):
    """
    Lista de cobranças do dia - clientes prioritários para contactar.
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
    query = {
        "overdue_balance_collectable": {"$gt": 0},
        "is_residual_only": {"$ne": True},
        "financial_status": {"$nin": [
            FinancialStatus.REGULARIZACAO_TECNICA.value,
            FinancialStatus.OK.value
        ]}
    }
    
    # Buscar clientes com promessas ativas/falhadas
    active_promises = await db.finance_promises.distinct("client_id", {"status": PromiseStatus.OPEN.value})
    failed_promises = await db.finance_promises.distinct("client_id", {"status": PromiseStatus.FAILED.value})
    active_promises_set = set(active_promises)
    failed_promises_set = set(failed_promises)
    
    # Buscar clientes
    clients_cursor = db.finance_clients.find(query, {"_id": 0}).sort([
        ("traffic_light", -1),  # Críticos primeiro
        ("overdue_balance_collectable", -1)
    ]).limit(limit)
    
    items = []
    total_value = 0.0
    
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
    
    # Ordenar por prioridade
    items.sort(key=lambda x: x.priority_score, reverse=True)
    
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
    client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0, "id": 1, "name": 1})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    promise_doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
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

@router.get("/regularizations", response_model=RegularizationsResponse)
async def get_regularizations(
    current_user: dict = Depends(require_finance_access)
):
    """
    Lista clientes apenas com saldos residuais para regularização.
    """
    # Buscar clientes com saldo residual > 0 mas sem dívida cobrável
    query = {
        "residual_balance": {"$gt": 0},
        "$or": [
            {"overdue_balance_collectable": {"$lte": 0}},
            {"is_residual_only": True}
        ]
    }
    
    clients_cursor = db.finance_clients.find(query, {"_id": 0}).sort("residual_balance", -1)
    
    items = []
    total_residual = 0.0
    
    async for client in clients_cursor:
        # Contar documentos residuais
        residual_count = await db.finance_documents.count_documents({
            "client_id": client["id"],
            "classification": {"$in": [
                DocumentClassification.RESIDUAL.value,
                DocumentClassification.RESIDUAL_ACCUMULATED.value
            ]}
        })
        
        residual_balance = client.get("residual_balance", 0.0)
        total_residual += residual_balance
        
        # Determinar sugestão
        if residual_count > 10 or residual_balance > 5:
            suggestion = "review"
        elif residual_balance < 1:
            suggestion = "ignore"
        else:
            suggestion = "request_regularization"
        
        items.append(RegularizationItem(
            client_id=client["id"],
            client_name=client["name"],
            genes_code=client["genes_code"],
            residual_balance=residual_balance,
            residual_document_count=residual_count,
            suggestion=suggestion
        ))
    
    return RegularizationsResponse(
        items=items,
        total_residual=total_residual,
        total_clients=len(items)
    )


# ============== IMPORTS ==============

@router.get("/imports", response_model=FinanceImportListResponse)
async def list_imports(
    type: Optional[ImportType] = None,
    status: Optional[ImportStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_finance_access)
):
    """
    Listar importações.
    """
    query = {}
    if type:
        query["type"] = type.value
    if status:
        query["status"] = status.value
    
    imports_cursor = db.finance_imports.find(query, {"_id": 0}).sort("uploaded_at", -1).limit(limit)
    imports = await imports_cursor.to_list(limit)
    
    total = await db.finance_imports.count_documents(query)
    
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
        total=total
    )


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
            # OPEN_DOCUMENTS - ainda não implementado (Fase 2)
            result = {
                "success": True,
                "import_id": import_id,
                "status": ImportStatus.RECEIVED.value,
                "message": f"Ficheiro {import_type.value} recebido. Parser será implementado em fase futura."
            }
        
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
