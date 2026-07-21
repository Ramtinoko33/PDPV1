"""
Motor de sugestões diárias para o CRM Finance.

Determinístico (rule engine), sem IA livre. Recolhe candidatos de várias fontes,
atribui prioridade + motivo, aplica guardrails (dados desatualizados, cliente
apenas residual, promessa ativa, etc.) e devolve uma lista equilibrada segundo
o modo (30/45/60 min).

O objectivo é dar à cobradora uma lista pronta a executar quando entra no
sistema. A IA pode depois usar o outcome / feedback para melhorar sugestões
futuras — mas as regras aqui são estáveis e explicáveis.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import db
from modules.finance.models import (
    TaskType, TaskStatus, TaskSource, TaskMode,
    FinancialStatus, DocumentClassification, PromiseStatus,
)

logger = logging.getLogger(__name__)


# Distribuição alvo de tarefas por modo — chaves são "categorias" internas.
DISTRIBUTION: Dict[str, Dict[str, int]] = {
    "30": {
        "promises":        3,
        "critical":        5,
        "old_low_value":   3,
        "no_contact":      2,
        "regularizations": 2,
        "block_suggest":   0,
    },
    "45": {
        "promises":        5,
        "critical":        6,
        "old_low_value":   5,
        "no_contact":      3,
        "regularizations": 3,
        "block_suggest":   2,
    },
    "60": {
        "promises":        6,
        "critical":        8,
        "old_low_value":   6,
        "no_contact":      4,
        "regularizations": 3,
        "block_suggest":   3,
    },
}


# Mapeamento entre TaskType e ação recomendada (texto sugerido para a cobradora).
SUGGESTED_ACTIONS: Dict[TaskType, str] = {
    TaskType.FOLLOW_FAILED_PROMISE:       "Contactar o cliente sobre promessa não cumprida.",
    TaskType.FOLLOW_PROMISE_DUE_TODAY:    "Lembrar o cliente do compromisso de pagamento acordado para hoje.",
    TaskType.SEND_ACCOUNT_STATEMENT:      "Enviar conta corrente atualizada.",
    TaskType.REQUEST_PAYMENT:             "Pedir regularização das faturas em aberto.",
    TaskType.REQUEST_PROOF:                "Solicitar comprovativo de pagamento referido pelo cliente.",
    TaskType.CALL_HIGH_VALUE_CLIENT:      "Telefonar para tratar da situação (valor elevado).",
    TaskType.REVIEW_OLD_DEBT:             "Rever dívida antiga (>90 dias) e definir próxima ação.",
    TaskType.REVIEW_LOW_VALUE_OLD_DEBT:   "Rever micro-saldos/valores baixos antigos e decidir regularização.",
    TaskType.UPDATE_FINANCE_CONTACT:      "Confirmar/actualizar o email financeiro do cliente.",
    TaskType.REVIEW_RESIDUAL:              "Rever saldo residual e decidir regularização técnica.",
    TaskType.SUGGEST_BLOCK:               "Sugerir bloqueio ao FINANCE_REVIEWER.",
    TaskType.REVIEW_DISPUTE:              "Rever cliente em disputa — acompanhar internamente.",
    TaskType.CREATE_PAYMENT_PLAN:         "Propor plano de pagamento faseado.",
    TaskType.SET_NEXT_ACTION:              "Definir próxima acção com o cliente.",
    TaskType.UPLOAD_GENES_MAP:            "Carregar o mapa GENES atualizado antes de cobrar.",
}


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bucket_of(days: int) -> str:
    if days <= 15: return "d0_15"
    if days <= 30: return "d16_30"
    if days <= 60: return "d31_60"
    if days <= 90: return "d61_90"
    if days <= 120: return "d90p"
    return "d120p"


async def _data_health_ok() -> Tuple[bool, Optional[str]]:
    """Verifica se os mapas críticos estão actualizados. Reflecte /finance/data-health."""
    async for h in db.finance_data_health.find({"blocking_collections": True}, {"_id": 0, "type": 1, "as_of_date": 1}):
        return False, f"Dados desatualizados: {h.get('type')} de {h.get('as_of_date') or '—'}. Carregue o mapa GENES antes de cobrar."
    return True, None


async def _get_promise_maps() -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    """Devolve {client_id: promise} para promessas OPEN activas e FALHADAS."""
    open_by_client: Dict[str, Dict] = {}
    failed_by_client: Dict[str, Dict] = {}
    today = _today_iso()

    async for p in db.finance_promises.find({"status": PromiseStatus.OPEN.value}, {"_id": 0}):
        cid = p.get("client_id")
        if cid:
            open_by_client[cid] = p

    async for p in db.finance_promises.find({"status": PromiseStatus.FAILED.value}, {"_id": 0}).sort("promise_date", -1):
        cid = p.get("client_id")
        if cid and cid not in failed_by_client:
            failed_by_client[cid] = p

    return open_by_client, failed_by_client


def _priority_for_critical(client: Dict[str, Any]) -> float:
    """Score para clientes críticos: combina traffic_light + valor + dias."""
    score = 0.0
    tl = client.get("traffic_light", "GREEN")
    score += {"CRITICAL": 100, "RED": 75, "ORANGE": 50, "YELLOW": 25}.get(tl, 0)
    score += min((client.get("overdue_balance_collectable", 0) or 0) / 1000, 30)
    score += min((client.get("oldest_overdue_days", 0) or 0) / 10, 20)
    return round(score, 2)


async def _candidates_promises(
    open_map: Dict[str, Dict], failed_map: Dict[str, Dict],
) -> List[Dict[str, Any]]:
    """Follow-ups a promessas falhadas + due-today."""
    cands: List[Dict[str, Any]] = []
    today = _today_iso()

    # Falhadas
    for cid, p in failed_map.items():
        client = await db.finance_clients.find_one({"id": cid}, {"_id": 0})
        if not client:
            continue
        cands.append({
            "client": client,
            "task_type": TaskType.FOLLOW_FAILED_PROMISE,
            "priority_score": 90.0 + min(client.get("overdue_balance_collectable", 0) / 500, 30),
            "priority_reason": f"Promessa falhada (valor: {p.get('amount', 0):.2f} €).",
        })

    # Due today
    for cid, p in open_map.items():
        if p.get("promise_date") == today:
            client = await db.finance_clients.find_one({"id": cid}, {"_id": 0})
            if client:
                cands.append({
                    "client": client,
                    "task_type": TaskType.FOLLOW_PROMISE_DUE_TODAY,
                    "priority_score": 85.0,
                    "priority_reason": "Promessa acordada vence hoje — lembrar o cliente.",
                })
    return cands


async def _candidates_critical(open_map: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Clientes críticos (traffic_light CRITICAL/RED, sem promessa ativa, valor relevante)."""
    cands: List[Dict[str, Any]] = []
    query = {
        "overdue_balance_collectable": {"$gt": 20},
        "is_residual_only": {"$ne": True},
        "financial_status": {"$nin": [
            FinancialStatus.EM_DISPUTA.value,
            FinancialStatus.BLOQUEADO.value,
            FinancialStatus.REGULARIZACAO_TECNICA.value,
            FinancialStatus.OK.value,
        ]},
        "traffic_light": {"$in": ["CRITICAL", "RED", "ORANGE"]},
    }
    async for c in db.finance_clients.find(query, {"_id": 0}).sort("overdue_balance_collectable", -1).limit(200):
        if c["id"] in open_map:
            continue  # promessa activa — não gerar cobrança
        overdue = c.get("overdue_balance_collectable", 0) or 0
        days = c.get("oldest_overdue_days", 0) or 0
        # Sugerir tipo apropriado
        if overdue >= 500:
            task_type = TaskType.CALL_HIGH_VALUE_CLIENT
        elif days >= 60:
            task_type = TaskType.REQUEST_PAYMENT
        else:
            task_type = TaskType.SEND_ACCOUNT_STATEMENT
        cands.append({
            "client": c,
            "task_type": task_type,
            "priority_score": _priority_for_critical(c),
            "priority_reason": f"Cliente crítico (semáforo {c.get('traffic_light')}, {overdue:.2f} €, {days} dias).",
        })
    return cands


async def _candidates_old_low_value(open_map: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Micro-saldos antigos e dívidas antigas de baixo valor a rever."""
    cands: List[Dict[str, Any]] = []
    # Clientes com residual/micro-old + total residual pequeno
    async for c in db.finance_clients.find({
        "residual_balance": {"$gt": 0, "$lte": 50},
        "is_residual_only": True,
    }, {"_id": 0}).sort("oldest_overdue_days", -1).limit(100):
        cands.append({
            "client": c,
            "task_type": TaskType.REVIEW_LOW_VALUE_OLD_DEBT,
            "priority_score": 30 + min(c.get("oldest_overdue_days", 0) / 20, 20),
            "priority_reason": f"Micro-saldo antigo ({c.get('residual_balance', 0):.2f} €, {c.get('oldest_overdue_days', 0)} dias) — validar regularização.",
        })

    # Dívidas antigas normais (>90 dias, valor médio)
    async for c in db.finance_clients.find({
        "overdue_balance_collectable": {"$gt": 20, "$lte": 200},
        "oldest_overdue_days": {"$gte": 90},
        "is_residual_only": {"$ne": True},
        "financial_status": {"$nin": [
            FinancialStatus.EM_DISPUTA.value,
            FinancialStatus.BLOQUEADO.value,
            FinancialStatus.PROMESSA_ATIVA.value,
        ]},
    }, {"_id": 0}).limit(100):
        if c["id"] in open_map:
            continue
        cands.append({
            "client": c,
            "task_type": TaskType.REVIEW_OLD_DEBT,
            "priority_score": 40 + min(c.get("oldest_overdue_days", 0) / 20, 25),
            "priority_reason": f"Dívida antiga esquecida ({c.get('overdue_balance_collectable', 0):.2f} €, {c.get('oldest_overdue_days', 0)} dias).",
        })
    return cands


async def _candidates_no_contact(open_map: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Clientes sem contacto nos últimos 30 dias que ainda têm valores a cobrar."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cands: List[Dict[str, Any]] = []
    async for c in db.finance_clients.find({
        "overdue_balance_collectable": {"$gt": 20},
        "is_residual_only": {"$ne": True},
        "financial_status": {"$nin": [
            FinancialStatus.EM_DISPUTA.value,
            FinancialStatus.BLOQUEADO.value,
        ]},
        "$or": [
            {"last_action_at": {"$exists": False}},
            {"last_action_at": None},
            {"last_action_at": ""},
            {"last_action_at": {"$lt": cutoff}},
        ],
    }, {"_id": 0}).sort("overdue_balance_collectable", -1).limit(80):
        if c["id"] in open_map:
            continue

        # Sub-tipo: sem finance_email → UPDATE_FINANCE_CONTACT; senão SEND_ACCOUNT_STATEMENT
        has_email = bool((c.get("finance_email") or "").strip())
        cands.append({
            "client": c,
            "task_type": TaskType.UPDATE_FINANCE_CONTACT if not has_email else TaskType.SEND_ACCOUNT_STATEMENT,
            "priority_score": 35 + min(c.get("overdue_balance_collectable", 0) / 1000, 20),
            "priority_reason": (
                "Cliente sem email financeiro registado — atualizar contacto antes de cobrar."
                if not has_email
                else "Sem contacto há mais de 30 dias — retomar cobrança."
            ),
        })
    return cands


async def _candidates_regularizations(open_map: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Documentos residuais/micro-old a validar contabilisticamente."""
    seen_clients: set = set()
    cands: List[Dict[str, Any]] = []
    async for doc in db.finance_documents.find({
        "$or": [
            {"effective_classification": {"$in": [
                DocumentClassification.RESIDUAL.value,
                DocumentClassification.MICRO_OLD.value,
            ]}},
            {"effective_classification": {"$exists": False}, "classification": {"$in": [
                DocumentClassification.RESIDUAL.value,
                DocumentClassification.MICRO_OLD.value,
            ]}},
        ],
        "manually_marked_collectable": {"$ne": True},
        "manual_action": {"$nin": ["mark_resolved_operationally", "mark_collectable"]},
    }, {"_id": 0}).sort("days_overdue", -1).limit(50):
        cid = doc.get("client_id")
        if not cid or cid in seen_clients:
            continue
        seen_clients.add(cid)
        client = await db.finance_clients.find_one({"id": cid}, {"_id": 0})
        if not client:
            continue
        cands.append({
            "client": client,
            "task_type": TaskType.REVIEW_RESIDUAL,
            "priority_score": 25 + min(doc.get("days_overdue", 0) / 30, 15),
            "priority_reason": f"Doc residual/micro-old ({doc.get('amount_open', 0):.2f} €, {doc.get('days_overdue', 0)} dias) — sugerir regularização técnica.",
        })
    return cands


async def _candidates_block_suggest(open_map: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Clientes elegíveis a sugerir bloqueio (>120 dias, valor relevante)."""
    cands: List[Dict[str, Any]] = []
    async for c in db.finance_clients.find({
        "overdue_balance_collectable": {"$gt": 100},
        "oldest_overdue_days": {"$gte": 120},
        "is_blocked": {"$ne": True},
        "financial_status": {"$nin": [
            FinancialStatus.EM_DISPUTA.value,
            FinancialStatus.BLOQUEIO_SUGERIDO.value,
        ]},
    }, {"_id": 0}).sort("overdue_balance_collectable", -1).limit(30):
        if c["id"] in open_map:
            continue
        cands.append({
            "client": c,
            "task_type": TaskType.SUGGEST_BLOCK,
            "priority_score": 70 + min(c.get("overdue_balance_collectable", 0) / 1000, 20),
            "priority_reason": f"Cliente >120 dias com {c.get('overdue_balance_collectable', 0):.2f} € vencidos — considerar sugerir bloqueio.",
        })
    return cands


def _build_task_doc(cand: Dict[str, Any], generation_id: str, assigned_to: Optional[str]) -> Dict[str, Any]:
    """Constrói o dict de finance_tasks a partir de um candidato."""
    c = cand["client"]
    task_type: TaskType = cand["task_type"]
    days = c.get("oldest_overdue_days", 0) or 0
    return {
        "id": str(uuid.uuid4()),
        "client_id": c["id"],
        "client_key": c.get("genes_code"),
        "client_name": c.get("name"),
        "genes_code": c.get("genes_code"),
        "task_type": task_type.value,
        "priority_score": round(cand.get("priority_score", 0), 2),
        "priority_reason": cand.get("priority_reason", ""),
        "suggested_action": SUGGESTED_ACTIONS.get(task_type, ""),
        "bucket": _bucket_of(days),
        "customer_segment": c.get("customer_segment"),
        "amount_collectable": round(c.get("overdue_balance_collectable", 0) or 0, 2),
        "days_overdue": days,
        "status": TaskStatus.OPEN.value,
        "assigned_to": assigned_to,
        "created_at": _now_iso(),
        "due_date": _today_iso(),
        "completed_at": None,
        "outcome": None,
        "feedback_action": None,
        "feedback_reason": None,
        "feedback_note": None,
        "next_action_date": None,
        "converted_to_task_id": None,
        "source": TaskSource.RULE_ENGINE.value,
        "import_id": None,
        "generation_id": generation_id,
    }


async def _archive_open_today(assigned_to: Optional[str]) -> int:
    """Marca as tarefas OPEN de hoje (do mesmo assigned_to, se dado) como EXPIRED."""
    today = _today_iso()
    q: Dict[str, Any] = {"status": TaskStatus.OPEN.value, "due_date": today}
    if assigned_to:
        q["assigned_to"] = assigned_to
    r = await db.finance_tasks.update_many(q, {"$set": {
        "status": TaskStatus.EXPIRED.value,
        "completed_at": _now_iso(),
        "outcome": "auto-archived by force_regenerate",
    }})
    return r.modified_count


async def _has_tasks_today(assigned_to: Optional[str]) -> int:
    q: Dict[str, Any] = {"due_date": _today_iso(), "status": {"$in": [TaskStatus.OPEN.value, TaskStatus.IN_REVIEW.value]}}
    if assigned_to:
        q["assigned_to"] = assigned_to
    return await db.finance_tasks.count_documents(q)


async def generate_daily_tasks(
    mode: TaskMode,
    assigned_to: Optional[str] = None,
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    """
    Gera a lista de tarefas para o dia com base no modo (30/45/60 min).

    Retorna dict:
        {generation_id, mode, tasks_created, tasks_archived, blocked_reason, tasks: [...]}
    """
    generation_id = str(uuid.uuid4())
    now = _now_iso()

    # 1) Guardrail: dados desatualizados?
    ok, reason = await _data_health_ok()
    if not ok:
        upload_task = {
            "id": str(uuid.uuid4()),
            "client_id": None,
            "client_key": None,
            "client_name": None,
            "genes_code": None,
            "task_type": TaskType.UPLOAD_GENES_MAP.value,
            "priority_score": 999.0,
            "priority_reason": reason or "Dados financeiros desatualizados",
            "suggested_action": SUGGESTED_ACTIONS[TaskType.UPLOAD_GENES_MAP],
            "bucket": None,
            "customer_segment": None,
            "amount_collectable": 0.0,
            "days_overdue": 0,
            "status": TaskStatus.OPEN.value,
            "assigned_to": assigned_to,
            "created_at": now,
            "due_date": _today_iso(),
            "completed_at": None, "outcome": None,
            "feedback_action": None, "feedback_reason": None, "feedback_note": None,
            "next_action_date": None, "converted_to_task_id": None,
            "source": TaskSource.RULE_ENGINE.value,
            "import_id": None,
            "generation_id": generation_id,
        }
        # arquivar existentes se force
        archived = 0
        if force_regenerate:
            archived = await _archive_open_today(assigned_to)
        await db.finance_tasks.insert_one(upload_task)
        return {
            "generation_id": generation_id,
            "mode": mode.value,
            "tasks_created": 1,
            "tasks_archived": archived,
            "blocked_reason": reason,
            "tasks": [upload_task],
        }

    # 2) Se já existem tarefas hoje e não força, não cria duplicados
    archived = 0
    if force_regenerate:
        archived = await _archive_open_today(assigned_to)
    else:
        existing = await _has_tasks_today(assigned_to)
        if existing > 0:
            tasks = []
            q: Dict[str, Any] = {"due_date": _today_iso()}
            if assigned_to:
                q["assigned_to"] = assigned_to
            async for t in db.finance_tasks.find(q, {"_id": 0}).sort("priority_score", -1):
                tasks.append(t)
            return {
                "generation_id": generation_id,
                "mode": mode.value,
                "tasks_created": 0,
                "tasks_archived": 0,
                "blocked_reason": None,
                "tasks": tasks,
            }

    # 3) Recolher candidatos por categoria
    open_map, failed_map = await _get_promise_maps()

    categories: Dict[str, List[Dict[str, Any]]] = {
        "promises":         await _candidates_promises(open_map, failed_map),
        "critical":         await _candidates_critical(open_map),
        "old_low_value":    await _candidates_old_low_value(open_map),
        "no_contact":       await _candidates_no_contact(open_map),
        "regularizations":  await _candidates_regularizations(open_map),
        "block_suggest":    await _candidates_block_suggest(open_map),
    }

    # ordenar candidatos por score dentro de cada categoria
    for k in categories:
        categories[k].sort(key=lambda x: x.get("priority_score", 0), reverse=True)

    # 4) Selecionar segundo distribuição alvo, evitar duplicados por client_id
    quota = DISTRIBUTION.get(mode.value, DISTRIBUTION["30"])
    picked: List[Dict[str, Any]] = []
    seen_client_type: set = set()  # (client_id, task_type)

    for category_key, target in quota.items():
        for cand in categories.get(category_key, []):
            cid = cand["client"]["id"]
            ttype = cand["task_type"].value
            if (cid, ttype) in seen_client_type:
                continue
            seen_client_type.add((cid, ttype))
            picked.append(cand)
            if len([x for x in picked if categories.get(category_key) and x in categories[category_key]]) >= target:
                break

    # Fallback simplificado: garantir que apenas o "target" por categoria é criado
    # (a lógica acima pode contar mal quando um cand aparece em >1 categoria; recontar
    # limitando por categoria em separado)
    final_tasks: List[Dict[str, Any]] = []
    seen_pairs: set = set()
    for category_key, target in quota.items():
        count = 0
        for cand in categories.get(category_key, []):
            if count >= target:
                break
            cid = cand["client"]["id"]
            key = (cid, cand["task_type"].value)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            final_tasks.append(_build_task_doc(cand, generation_id, assigned_to))
            count += 1

    # Persistir
    if final_tasks:
        await db.finance_tasks.insert_many([dict(t) for t in final_tasks])

    # Ordenar por prioridade descendente
    final_tasks.sort(key=lambda t: t.get("priority_score", 0), reverse=True)

    logger.info(
        f"[FINANCE-TASKS] generation_id={generation_id} mode={mode.value} "
        f"created={len(final_tasks)} archived={archived} assigned_to={assigned_to}"
    )

    return {
        "generation_id": generation_id,
        "mode": mode.value,
        "tasks_created": len(final_tasks),
        "tasks_archived": archived,
        "blocked_reason": None,
        "tasks": final_tasks,
    }
