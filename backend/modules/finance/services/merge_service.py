"""
Serviço de consolidação de clientes Finance duplicados (soft-merge).

Extraído de `scripts/merge_duplicate_finance_clients.py` para poder ser
chamado quer via CLI quer via endpoints OWNER-only:
  POST /api/finance/merge-duplicates/dry-run
  POST /api/finance/merge-duplicates/confirm

Regras P0 (spec do utilizador):
  1. Master é o cliente cujo `genes_code` bate com o sufixo do padrão
     `21111\\d+`. Se o master estiver preenchido num campo sensível,
     NUNCA é sobrescrito — o valor do duplicado fica registado como
     `merge_conflicts`.
  2. Campos migram do duplicado para o master apenas se o campo estiver
     vazio/nulo no master.
  3. Colecções remapeadas por `genes_code`:  finance_credit_evolution,
     finance_documents, finance_open_documents (com rebuild de doc_key).
  4. Colecções remapeadas por `client_id`:   finance_documents,
     finance_actions, finance_promises, finance_regularizations,
     finance_tasks, finance_block_requests.
  5. Duplicado NUNCA é apagado — recebe `is_merged_duplicate=True`,
     `merged_into`, `merged_into_genes_code`, `merged_at`, `merged_by`,
     `merged_reason`, `merge_conflicts`.
  6. Todos os relatórios são estruturados (JSON amigável para audit).
"""
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# Reusar o normalizador dos parsers
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
from modules.finance.parsers.account_normalizer import normalize_account_to_client_code  # noqa: E402


# Colecções que referem clientes via genes_code
CLIENT_REF_COLLECTIONS_BY_GENES = [
    'finance_credit_evolution',
    'finance_documents',
    'finance_open_documents',
]
# Colecções que referem clientes via client_id
CLIENT_REF_COLLECTIONS_BY_ID = [
    'finance_documents',
    'finance_actions',
    'finance_promises',
    'finance_regularizations',
    'finance_tasks',
    'finance_block_requests',
]

# Contactos financeiros: só migram se master vazio
CONTACT_FIELDS_MERGE_IF_EMPTY = (
    'finance_email', 'finance_mobile', 'finance_phone',
    'finance_contact_name', 'finance_contact_role', 'finance_contact_tag',
)

# Enriquecimento (spec do utilizador): só migram se master vazio
ENRICH_FIELDS_MERGE_IF_EMPTY = (
    'saldo_conta', 'saldo_efec', 'saldo_desc', 'saldo_dev',
    'carteira', 'domiciliacoes', 'albaranado', 'forma_pagamento',
    'eventos_raw', 'risco_raw', 'risco_validado', 'risco_placeholder',
    'customer_segment',
    'last_infoclientes_import_id',
    'annual_revenue', 'insured_risk_value', 'risk_percentage',
    'portfolio', 'pending_delivery', 'risk_value', 'genes_account',
    'credit_trend_percentage', 'credit_trend_absolute',
)


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == 0


def _compute_conflicts_and_updates(
    master: Dict, dup: Dict
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Regras: master vazio+dup preenchido → migra; master preenchido+dup
    diferente → preserva master + conflict; caso contrário → nada."""
    updates: Dict[str, Any] = {}
    conflicts: List[Dict[str, Any]] = []
    for field in CONTACT_FIELDS_MERGE_IF_EMPTY + ENRICH_FIELDS_MERGE_IF_EMPTY:
        m_val = master.get(field)
        d_val = dup.get(field)
        if _empty(d_val):
            continue
        if _empty(m_val):
            updates[field] = d_val
        elif m_val != d_val:
            conflicts.append({
                'field': field,
                'master_value': m_val,
                'duplicate_value': d_val,
                'action': 'preserved_master',
                'reason': 'master preenchido; duplicado ignorado',
            })
    return updates, conflicts


async def _find_duplicate_groups(db) -> List[Dict[str, Any]]:
    """Devolve [{master, duplicates:[{...,_updates_for_master,_conflicts}]}]."""
    all_clients: List[Dict[str, Any]] = []
    async for c in db.finance_clients.find({}, {'_id': 0}):
        all_clients.append(c)

    by_code: Dict[str, Dict[str, Any]] = {
        c.get('genes_code'): c for c in all_clients if c.get('genes_code')
    }

    groups: List[Dict[str, Any]] = []
    seen_dupes: set = set()

    for c in all_clients:
        code = c.get('genes_code') or ''
        if not code or c.get('is_merged_duplicate'):
            continue
        # sufixo do padrão 21111...
        suffix = normalize_account_to_client_code(code)
        if not suffix:
            for account_field in ('account', 'genes_account', 'conta'):
                acc = c.get(account_field)
                if acc:
                    suffix = normalize_account_to_client_code(acc)
                    if suffix:
                        break
        if not suffix or suffix == code:
            continue
        master = by_code.get(suffix)
        if not master:
            continue
        if master.get('id') == c.get('id') or c.get('id') in seen_dupes:
            continue
        group = next((g for g in groups if g['master']['id'] == master['id']), None)
        if group is None:
            group = {'master': master, 'duplicates': []}
            groups.append(group)
        group['duplicates'].append(c)
        seen_dupes.add(c.get('id'))

    return groups


async def build_plan(db) -> Dict[str, Any]:
    """Constrói o plano de merge (dry-run) sem tocar em nada.

    Devolve dict com:
      generated_at, summary {masters,duplicates,conflicts_preserved},
      groups: [{master, duplicates:[{...,_updates_for_master,_conflicts}]}],
      conflicts: [{master_id, master_genes_code, duplicate_id,
                   duplicate_genes_code, field, master_value,
                   duplicate_value, action, reason}]
    """
    groups = await _find_duplicate_groups(db)
    total_dupes = 0
    total_conflicts: List[Dict[str, Any]] = []
    for g in groups:
        m = g['master']
        for d in g['duplicates']:
            updates, conflicts = _compute_conflicts_and_updates(m, d)
            d['_updates_for_master'] = updates
            d['_conflicts'] = conflicts
            for c in conflicts:
                total_conflicts.append({
                    'master_id': m.get('id'),
                    'master_genes_code': m.get('genes_code'),
                    'duplicate_id': d.get('id'),
                    'duplicate_genes_code': d.get('genes_code'),
                    **c,
                })
        total_dupes += len(g['duplicates'])

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'masters': len(groups),
            'duplicates': total_dupes,
            'conflicts_preserved': len(total_conflicts),
        },
        'conflicts': total_conflicts,
        'groups': groups,
    }


async def apply_plan(db, plan: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """Aplica um plano previamente construído. NÃO recomputa nada — usa
    exactamente o que está em `plan['groups']` (assinatura do dry-run
    validado pelo utilizador).

    Devolve: {merged_count, masters_touched, remap_stats}
    """
    now = datetime.now(timezone.utc).isoformat()
    merged_count = 0
    remap_stats: Dict[str, int] = {}

    groups = plan.get('groups') or []
    for g in groups:
        master = g['master']
        master_id = master['id']
        master_code = master['genes_code']
        for dup in g['duplicates']:
            dup_id = dup['id']
            dup_code = dup['genes_code']

            # 1) Aplicar updates ao master (só campos vazios no master)
            updates = dup.get('_updates_for_master') or {}
            if updates:
                await db.finance_clients.update_one(
                    {'id': master_id},
                    {'$set': {**updates, 'updated_at': now}},
                )

            # 2) Remapear colecções por genes_code
            for col in CLIENT_REF_COLLECTIONS_BY_GENES:
                r = await db[col].update_many(
                    {'genes_code': dup_code},
                    {'$set': {'genes_code': master_code}},
                )
                key = f'{col}:genes_code'
                remap_stats[key] = remap_stats.get(key, 0) + r.modified_count

            # 2b) Rebuild doc_key em finance_open_documents
            async for od in db.finance_open_documents.find(
                {'genes_code': master_code},
                {'_id': 0, 'id': 1, 'doc_key': 1, 'document_number': 1},
            ):
                new_key = f'{master_code}_{od.get("document_number")}'
                if od.get('doc_key') != new_key:
                    filter_ = (
                        {'id': od['id']} if od.get('id')
                        else {'doc_key': od.get('doc_key')}
                    )
                    await db.finance_open_documents.update_one(
                        filter_, {'$set': {'doc_key': new_key}}
                    )
                    key = 'finance_open_documents:doc_key'
                    remap_stats[key] = remap_stats.get(key, 0) + 1

            # 3) Remapear colecções por client_id
            for col in CLIENT_REF_COLLECTIONS_BY_ID:
                r = await db[col].update_many(
                    {'client_id': dup_id},
                    {'$set': {'client_id': master_id}},
                )
                key = f'{col}:client_id'
                remap_stats[key] = remap_stats.get(key, 0) + r.modified_count

            # 4) Colapsar duplicated credit_evolution
            evo_docs = []
            async for e in db.finance_credit_evolution.find(
                {'genes_code': master_code}, {'_id': 0}
            ):
                evo_docs.append(e)
            if len(evo_docs) > 1:
                evo_docs.sort(key=lambda e: e.get('updated_at') or '', reverse=True)
                keep = evo_docs[0]
                await db.finance_credit_evolution.delete_many(
                    {'genes_code': master_code}
                )
                await db.finance_credit_evolution.insert_one(keep)

            # 5) Marcar duplicado (SOFT — nunca apaga)
            reason = (
                f'Duplicado detectado por sufixo da Conta '
                f'({dup_code} → {master_code}). CodPersona/Conta inteira '
                'nunca deveriam ter sido usadas como client_key.'
            )
            await db.finance_clients.update_one(
                {'id': dup_id},
                {'$set': {
                    'is_merged_duplicate': True,
                    'merged_into': master_id,
                    'merged_into_genes_code': master_code,
                    'merged_at': now,
                    'merged_by': actor,
                    'merged_reason': reason,
                    # alias legado
                    'merge_reason': reason,
                    'merge_conflicts': dup.get('_conflicts') or [],
                }},
            )
            merged_count += 1

    return {
        'merged_count': merged_count,
        'masters_touched': len(groups),
        'remap_stats': remap_stats,
    }
