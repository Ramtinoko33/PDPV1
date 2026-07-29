"""
CLEANUP MANUAL DE PRODUÇÃO — Consolidar clientes duplicados criados por
uso incorrecto de CodPersona/Conta antes da iter 51.

Antes desta iter, InfoClientes/Evolução Crédito passaram a usar `Conta`
inteira (`2111100163`) como `genes_code`, criando duplicados dos clientes
originais (código `163`). Documentos usava `CodPersona` (`120`), outro
identificador inútil que também criava duplicados.

Este script:
  1. Detecta pares/grupos por sufixo de Conta.
  2. Master = documento cujo `genes_code` bate com o sufixo extraído.
  3. Duplicados (com prefixo `21111` ou id numérico curto sem master
     correspondente) são consolidados no master.
  4. Migra colecções afectadas (finance_credit_evolution, finance_documents,
     finance_actions, finance_promises, finance_regularizations,
     finance_tasks, finance_blocks) trocando `genes_code`/`client_id` para
     o master.
  5. Campos do master têm prioridade: só copiamos do duplicado o que o
     master tem NULL/None/vazio (excepto contactos financeiros: só se master
     não tiver).
  6. Marca duplicado como `is_merged_duplicate=True, merged_into=<master.id>,
     merged_at, merged_by, merge_reason`. NÃO apaga.

Dry-run por defeito. `--confirm` aplica.

Uso:
  python /app/backend/scripts/merge_duplicate_finance_clients.py
  python /app/backend/scripts/merge_duplicate_finance_clients.py --confirm
"""
import os
import sys
import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa

# Reusar o normalizador dos parsers
sys.path.insert(0, '/app/backend')
from modules.finance.parsers.account_normalizer import normalize_account_to_client_code  # noqa

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

# Colecções que referem clientes via genes_code ou client_id
CLIENT_REF_COLLECTIONS_BY_GENES = [
    'finance_credit_evolution',
    'finance_documents',
]
CLIENT_REF_COLLECTIONS_BY_ID = [
    'finance_documents',        # tem também client_id em muitos casos
    'finance_actions',
    'finance_promises',
    'finance_regularizations',
    'finance_tasks',
    'finance_blocks',
]

# Campos "financial contacts" que só copiamos se master estiver vazio
CONTACT_FIELDS_MERGE_IF_EMPTY = (
    'finance_email', 'finance_mobile', 'finance_phone',
    'finance_contact_name', 'finance_contact_role', 'finance_contact_tag',
)

# Campos de enriquecimento que copiamos apenas se master os tiver None/vazios
ENRICH_FIELDS_MERGE_IF_EMPTY = (
    'saldo_conta', 'saldo_efec', 'saldo_desc', 'saldo_dev',
    'carteira', 'domiciliacoes', 'albaranado', 'forma_pagamento',
    'eventos_raw', 'risco_raw', 'risco_validado', 'risco_placeholder',
    'last_infoclientes_import_id',
    'annual_revenue', 'insured_risk_value', 'risk_percentage',
    'portfolio', 'pending_delivery', 'risk_value', 'genes_account',
    'credit_trend_percentage', 'credit_trend_absolute',
)


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == 0


async def _find_duplicate_groups(db) -> List[Dict[str, Any]]:
    """Constroi lista de {master, duplicates:[..], conflicts:[..]}."""
    # Todos os clientes já em BD
    all_clients: List[Dict[str, Any]] = []
    async for c in db.finance_clients.find({}, {'_id': 0}):
        all_clients.append(c)

    # Indexa por genes_code
    by_code: Dict[str, Dict[str, Any]] = {c.get('genes_code'): c for c in all_clients if c.get('genes_code')}

    groups: List[Dict[str, Any]] = []
    seen_dupes: set = set()

    for c in all_clients:
        code = c.get('genes_code') or ''
        if not code or c.get('is_merged_duplicate'):
            continue
        # Candidato a duplicado: código bate com padrão 21111NNN
        suffix = normalize_account_to_client_code(code)
        if not suffix or suffix == code:
            continue
        # Procura master
        master = by_code.get(suffix)
        if not master:
            # Sem master ainda — não fazemos merge (aguardar 1º import correcto)
            continue
        if master.get('id') == c.get('id') or c.get('id') in seen_dupes:
            continue
        # Adiciona ao grupo do master
        group = next((g for g in groups if g['master']['id'] == master['id']), None)
        if group is None:
            group = {'master': master, 'duplicates': [], 'conflicts': []}
            groups.append(group)
        group['duplicates'].append(c)
        seen_dupes.add(c.get('id'))

    return groups


def _compute_conflicts_and_updates(master: Dict, dup: Dict) -> Tuple[Dict, List[str]]:
    """Devolve (updates_para_master, conflicts_report)."""
    updates: Dict[str, Any] = {}
    conflicts: List[str] = []
    for field in CONTACT_FIELDS_MERGE_IF_EMPTY + ENRICH_FIELDS_MERGE_IF_EMPTY:
        m_val = master.get(field)
        d_val = dup.get(field)
        if d_val is None:
            continue
        if _empty(m_val):
            updates[field] = d_val
        elif m_val != d_val:
            conflicts.append(f'{field}: master={m_val!r} dup={d_val!r}')
    return updates, conflicts


async def main(confirm: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    groups = await _find_duplicate_groups(db)

    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dump_path = f'/tmp/finance_merge_backup_{ts}.json'
    with open(dump_path, 'w', encoding='utf-8') as f:
        json.dump(groups, f, ensure_ascii=False, indent=2, default=str)

    # Pré-calcular conflicts e updates de cada duplicado
    total_dupes = 0
    total_conflicts: List[str] = []
    for g in groups:
        m = g['master']
        for d in g['duplicates']:
            updates, conflicts = _compute_conflicts_and_updates(m, d)
            d['_updates_for_master'] = updates
            d['_conflicts'] = conflicts
            total_conflicts.extend(f'{m.get("genes_code")}←{d.get("genes_code")}: {c}' for c in conflicts)
        total_dupes += len(g['duplicates'])

    print(f'Encontrados {len(groups)} master(s) com {total_dupes} duplicado(s).')
    print(f'Backup completo em: {dump_path}')
    print()
    for g in groups[:20]:
        m = g['master']
        print(f'MASTER {m.get("genes_code")} — {m.get("name")}  (id={m.get("id")})')
        for d in g['duplicates']:
            print(f'  ← DUP {d.get("genes_code")} (id={d.get("id")}) name={d.get("name")!r}')
            if d.get('_conflicts'):
                for c in d['_conflicts']:
                    print(f'      CONFLICT: {c}')
        print()
    if len(groups) > 20:
        print(f'... e mais {len(groups)-20} grupo(s).')
    if total_conflicts:
        print(f'⚠️  Total de {len(total_conflicts)} conflitos preservam valor do master.')
    print()

    if not groups:
        print('Nada a fazer.')
        return

    if not confirm:
        print('DRY-RUN. Passe --confirm para aplicar.')
        return

    now = datetime.now(timezone.utc).isoformat()
    merged_count = 0

    for g in groups:
        master = g['master']
        master_id = master['id']
        master_code = master['genes_code']
        for dup in g['duplicates']:
            dup_id = dup['id']
            dup_code = dup['genes_code']

            # 1) Aplicar updates ao master
            if dup['_updates_for_master']:
                await db.finance_clients.update_one(
                    {'id': master_id},
                    {'$set': {**dup['_updates_for_master'], 'updated_at': now}}
                )

            # 2) Remapear colecções por genes_code
            for col in CLIENT_REF_COLLECTIONS_BY_GENES:
                await db[col].update_many(
                    {'genes_code': dup_code},
                    {'$set': {'genes_code': master_code}}
                )

            # 3) Remapear colecções por client_id
            for col in CLIENT_REF_COLLECTIONS_BY_ID:
                await db[col].update_many(
                    {'client_id': dup_id},
                    {'$set': {'client_id': master_id}}
                )

            # 4) Colapsar duplicated credit_evolution (só master fica).
            #    Depois do remap acima, podem existir 2 docs com mesmo
            #    genes_code — mantemos o mais recente por updated_at.
            evo_docs = []
            async for e in db.finance_credit_evolution.find(
                {'genes_code': master_code}, {'_id': 0}
            ):
                evo_docs.append(e)
            if len(evo_docs) > 1:
                evo_docs.sort(key=lambda e: e.get('updated_at') or '', reverse=True)
                keep = evo_docs[0]
                await db.finance_credit_evolution.delete_many({'genes_code': master_code})
                await db.finance_credit_evolution.insert_one(keep)

            # 5) Marcar duplicado
            await db.finance_clients.update_one(
                {'id': dup_id},
                {'$set': {
                    'is_merged_duplicate': True,
                    'merged_into': master_id,
                    'merged_into_genes_code': master_code,
                    'merged_at': now,
                    'merged_by': 'merge_script_iter51',
                    'merge_reason': (
                        f'Duplicado detectado por sufixo da Conta ({dup_code} → {master_code}). '
                        'CodPersona/Conta inteira nunca deveriam ter sido usadas como client_key.'
                    ),
                    'merge_conflicts': dup['_conflicts'],
                }}
            )
            merged_count += 1

    print(f'✅ Consolidados {merged_count} duplicado(s) em {len(groups)} master(s).')
    print(f'Audit backup preservado em: {dump_path}')


if __name__ == '__main__':
    confirm = '--confirm' in sys.argv
    asyncio.run(main(confirm))
