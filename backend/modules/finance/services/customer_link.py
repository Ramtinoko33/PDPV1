"""
Ligação entre finance_clients e customers (módulo principal).

Fornece:
- CUSTOMER_TYPE_TO_SEGMENT: mapeamento das strings livres do GENES para o enum
  CustomerSegment usado pelo Finance.
- match_customer_by_name(): heurística simples de matching por nome normalizado.
- backfill_finance_client(): actualiza um finance_client com dados vindos do
  customer ligado (segment + contactos), sem sobrescrever valores manuais
  já definidos.
- backfill_all_finance_clients(): job idempotente para correr no startup.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import db
from modules.finance.models import CustomerSegment

logger = logging.getLogger(__name__)


# Mapeamento dos customer_type reais no GENES → segmento operacional.
# Chaves em UPPERCASE, comparação case-insensitive + normalizada.
CUSTOMER_TYPE_TO_SEGMENT: Dict[str, CustomerSegment] = {
    "PARTICULAR": CustomerSegment.PARTICULAR,
    "FUNCIONARIOS": CustomerSegment.PARTICULAR,
    "FUNCIONÁRIOS": CustomerSegment.PARTICULAR,

    "EMPRESA": CustomerSegment.EMPRESA,
    "EMPRESA AGRICULA": CustomerSegment.EMPRESA,
    "EMPRESA AGRÍCOLA": CustomerSegment.EMPRESA,
    "INDUSTRIA": CustomerSegment.EMPRESA,
    "INDÚSTRIA": CustomerSegment.EMPRESA,
    "AGRICULTOR": CustomerSegment.EMPRESA,
    "VINICULTOR": CustomerSegment.EMPRESA,
    "COOPERATIVA AGRICOLA": CustomerSegment.EMPRESA,
    "COOPERATIVA AGRÍCOLA": CustomerSegment.EMPRESA,
    "OFICINA REPARADORA AUTO": CustomerSegment.EMPRESA,
    "CONCESS. AUTOMOVEIS": CustomerSegment.EMPRESA,
    "CONCESS. AUTOMÓVEIS": CustomerSegment.EMPRESA,
    "CONCESS. MAQ. AGRICOLAS": CustomerSegment.EMPRESA,
    "CONCESS. MAQ. AGRÍCOLAS": CustomerSegment.EMPRESA,
    "ALUGADOR MAQUINAS": CustomerSegment.EMPRESA,
    "ALUGADOR MÁQUINAS": CustomerSegment.EMPRESA,

    "FROTISTA LIGEIRO": CustomerSegment.FROTA,
    "FROTISTA PESADOS": CustomerSegment.FROTA,
    "FROTA": CustomerSegment.FROTA,

    "SEGURADORA": CustomerSegment.SEGURADORA,
    "LEASING": CustomerSegment.LEASING,
    "CONTA CORRENTE": CustomerSegment.CONTA_CORRENTE,
    "CONTA_CORRENTE": CustomerSegment.CONTA_CORRENTE,

    "ENTIDADE DO ESTADO": CustomerSegment.OUTRO,
}


def resolve_segment(customer_type: Optional[str]) -> CustomerSegment:
    """Devolve o segmento correspondente ao customer_type do GENES."""
    if not customer_type:
        return CustomerSegment.UNKNOWN
    key = customer_type.strip().upper()
    return CUSTOMER_TYPE_TO_SEGMENT.get(key, CustomerSegment.UNKNOWN)


def _normalize_name(s: str) -> str:
    """Normaliza um nome para matching heurístico (upper, sem pontuação/acentos, single-space)."""
    if not s:
        return ""
    s = s.upper()
    # remover acentos comuns em PT
    accents = str.maketrans("ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ", "AAAAAEEEEIIIIOOOOOUUUUC")
    s = s.translate(accents)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def _pick_customer_first_email(customer: Dict[str, Any]) -> Optional[str]:
    emails = customer.get("emails") or []
    if isinstance(emails, list) and emails:
        # primeiro non-empty
        for e in emails:
            if e and isinstance(e, str) and "@" in e:
                return e.strip()
    # fallback legacy
    e = customer.get("email")
    return e if e and "@" in e else None


async def _pick_customer_first_phone(customer: Dict[str, Any]) -> Optional[str]:
    phones = customer.get("phones") or []
    if isinstance(phones, list) and phones:
        for p in phones:
            if p and isinstance(p, str):
                return p.strip()
    return customer.get("phone") or customer.get("mobile")


async def match_customer_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Tenta encontrar um customer pelo nome (exact normalized match).
    Devolve o customer se houver correspondência única, senão None.
    Usa o campo indexado `name_normalized` quando existe (fallback: full-scan).
    """
    if not name:
        return None
    normalized = _normalize_name(name)
    if not normalized or len(normalized) < 3:
        return None

    # 1) Fast path — usa índice em name_normalized
    fast = []
    async for c in db.customers.find(
        {"name_normalized": normalized},
        {"_id": 0, "id": 1, "name": 1, "customer_type": 1, "emails": 1, "phones": 1, "email": 1, "phone": 1, "mobile": 1},
    ):
        fast.append(c)
        if len(fast) > 1:
            return None
    if fast:
        return fast[0]

    # 2) Fallback lento — se o backfill ainda não correu ou há customers sem name_normalized
    candidates: List[Dict[str, Any]] = []
    async for c in db.customers.find(
        {"name_normalized": {"$exists": False}},
        {"_id": 0, "id": 1, "name": 1, "customer_type": 1, "emails": 1, "phones": 1, "email": 1, "phone": 1, "mobile": 1},
    ):
        if _normalize_name(c.get("name", "")) == normalized:
            candidates.append(c)
            if len(candidates) > 1:
                return None
    return candidates[0] if candidates else None


async def ensure_customers_name_normalized_index() -> Dict[str, Any]:
    """
    Idempotente:
      - Cria índice em `customers.name_normalized` (não-único, pode haver homónimos).
      - Preenche `name_normalized` em documentos que ainda não têm.
    Retorna sumário {index_created, backfilled}.
    """
    created = False
    try:
        existing = await db.customers.index_information()
        if "name_normalized_1" not in existing:
            await db.customers.create_index("name_normalized")
            created = True
    except Exception as e:
        logger.warning(f"[FINANCE] Failed creating name_normalized index: {e}")

    backfilled = 0
    async for c in db.customers.find(
        {"name_normalized": {"$exists": False}}, {"_id": 0, "id": 1, "name": 1}
    ):
        n = _normalize_name(c.get("name", ""))
        if n:
            await db.customers.update_one({"id": c["id"]}, {"$set": {"name_normalized": n}})
            backfilled += 1

    logger.info(f"[FINANCE] ensure_customers_name_normalized_index: created={created} backfilled={backfilled}")
    return {"index_created": created, "backfilled": backfilled}


async def backfill_finance_client(
    finance_client_id: str,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Actualiza um finance_client com:
      - `linked_customer_id` (se não estiver ligado, tenta match por nome)
      - `customer_segment` (deriva de customer_type se estiver UNKNOWN OU force=True)
      - `finance_email`/`finance_phone`/`finance_mobile` (só se estiverem vazios; nunca sobrescreve edição manual)

    NÃO tocar em campos financeiros (balances, classificações, etc.).
    """
    fc = await db.finance_clients.find_one({"id": finance_client_id}, {"_id": 0})
    if not fc:
        return {"ok": False, "reason": "finance_client not found"}

    linked_id = fc.get("linked_customer_id")
    customer = None
    if linked_id:
        customer = await db.customers.find_one({"id": linked_id}, {"_id": 0})
    if not customer:
        customer = await match_customer_by_name(fc.get("name", ""))

    update: Dict[str, Any] = {}
    if customer:
        if not linked_id:
            update["linked_customer_id"] = customer["id"]

        # Segment
        current_segment = fc.get("customer_segment") or CustomerSegment.UNKNOWN.value
        if force or current_segment == CustomerSegment.UNKNOWN.value:
            new_seg = resolve_segment(customer.get("customer_type"))
            if new_seg.value != current_segment:
                update["customer_segment"] = new_seg.value

        # Contactos — só se vazios (nunca sobrescrever manual)
        if not fc.get("finance_email"):
            email = await _pick_customer_first_email(customer)
            if email:
                update["finance_email"] = email
        if not fc.get("finance_phone"):
            phone = await _pick_customer_first_phone(customer)
            if phone:
                update["finance_phone"] = phone
        if not fc.get("finance_mobile"):
            mobile = customer.get("mobile")
            if mobile:
                update["finance_mobile"] = mobile
    else:
        # Sem link possível — garantir apenas que o segmento existe (UNKNOWN se ausente)
        if "customer_segment" not in fc:
            update["customer_segment"] = CustomerSegment.UNKNOWN.value

    if update:
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.finance_clients.update_one({"id": finance_client_id}, {"$set": update})

    return {"ok": True, "linked": bool(customer), "fields_updated": list(update.keys())}


async def backfill_all_finance_clients(force: bool = False) -> Dict[str, Any]:
    """Corre backfill em todos os finance_clients. Idempotente por default."""
    total = 0
    updated = 0
    linked = 0
    async for fc in db.finance_clients.find({}, {"_id": 0, "id": 1}):
        total += 1
        r = await backfill_finance_client(fc["id"], force=force)
        if r.get("fields_updated"):
            updated += 1
        if r.get("linked"):
            linked += 1
    summary = {"total": total, "updated": updated, "linked": linked}
    logger.info(f"[FINANCE] backfill_all_finance_clients: {summary}")
    return summary
