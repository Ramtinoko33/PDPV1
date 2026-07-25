"""
CLEANUP MANUAL DE PRODUÇÃO — Marcar como rejected imports antigos silenciosos.

Contexto: até à iter 48 (Feb 2026), os parsers de InfoClientes e Evolução
Crédito reconheciam apenas 'CodCliente'/'CODCLIENTE' como coluna do código
do cliente. Os ficheiros reais GENES usam 'Conta'. Resultado: o parser
processava as linhas mas ignorava-as → import "Importado" com 0 clientes
aplicados, sem qualquer aviso.

Este script:
  1. Dump JSON audit em /tmp/finance_silent_zero_backup_<ts>.json
     com o estado completo dos imports afectados ANTES de qualquer alteração.
  2. Lista imports "silenciosos" com estes critérios:
        - status IN {imported, accepted_with_warnings}
        - rows_processed > 10 (ou totals.rows_processed > 10 se existir)
        - clients_updated == 0 AND clients_found == 0 (ou totals.clients==0)
        - documents_created == 0 AND (totals.documents==0)
     Para tipos que não têm rows_processed (imports muito antigos), usa
     fallback: totals.clients == 0 AND totals.documents == 0 e o import
     tem file_hash + original_file_path (garantia que passou pelo parser).
  3. Com --confirm marca-os como status='rejected_silent_zero' preservando:
        - file_hash, original_file_path, uploaded_at/by, filename
        - totals, warnings existentes
     e regista rejected_at + rejected_by + reason.
  4. NUNCA toca em finance_clients, finance_documents ou finance_credit_evolution.

Uso:
  python /app/backend/scripts/mark_silent_zero_imports.py           # dry-run
  python /app/backend/scripts/mark_silent_zero_imports.py --confirm # aplica

Depois deste cleanup, os utilizadores podem reimportar os ficheiros originais
sem colisão de hash. Após a iter 49 do backend, o hash-check já não bloqueia
imports antigos com clients_updated==0, portanto este script é opcional para
higienizar o histórico visual — o reimport funciona mesmo sem o correr.
"""
import os
import sys
import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

USEFUL_STATUSES = {'imported', 'accepted_with_warnings'}
TYPES_IN_SCOPE = {
    'client_info',
    'credit_evolution',
    'overdue_balances',
    'open_documents',
}


def _is_silent_zero(imp: Dict[str, Any]) -> bool:
    """Regra de detecção."""
    if imp.get('status') not in USEFUL_STATUSES:
        return False
    if imp.get('type') not in TYPES_IN_SCOPE:
        return False
    totals = imp.get('totals') or {}
    # Se tivermos os counters novos (iter 48), usa-os
    clients_updated = totals.get('clients_updated')
    clients_found = totals.get('clients_found')
    documents_created = totals.get('documents_created')
    rows_processed = totals.get('rows_processed')
    # Fallbacks para imports antigos sem os counters
    legacy_clients = totals.get('clients') or 0
    legacy_documents = totals.get('documents') or 0

    # Regra principal (iter 48+)
    if rows_processed is not None:
        if rows_processed <= 10:
            return False
        no_clients = (clients_updated or 0) == 0 and (clients_found or 0) == 0
        no_docs = (documents_created or 0) == 0
        return no_clients and no_docs and legacy_clients == 0

    # Regra fallback para imports antigos (pre-iter 48)
    # → 0 clientes E 0 documentos E ficheiro original presente
    if legacy_clients == 0 and legacy_documents == 0 and imp.get('original_file_path'):
        return True
    return False


async def main(confirm: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Query lato — só filtramos status + tipo. A regra de silent-zero é
    # aplicada em Python para permitir a lógica composta acima.
    cursor = db.finance_imports.find(
        {'status': {'$in': list(USEFUL_STATUSES)},
         'type': {'$in': list(TYPES_IN_SCOPE)}},
        {'_id': 0}
    )
    candidates: List[Dict[str, Any]] = []
    async for imp in cursor:
        if _is_silent_zero(imp):
            candidates.append(imp)

    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dump_path = f'/tmp/finance_silent_zero_backup_{ts}.json'
    with open(dump_path, 'w', encoding='utf-8') as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2, default=str)

    print(f'Encontrados {len(candidates)} import(s) silenciosos.')
    print(f'Backup audit escrito em: {dump_path}')
    print()
    for imp in candidates:
        totals = imp.get('totals') or {}
        print(f'  id={imp.get("id")}')
        print(f'    tipo         = {imp.get("type")}')
        print(f'    ficheiro     = {imp.get("filename")}')
        print(f'    uploaded_at  = {imp.get("uploaded_at")}')
        print(f'    status_atual = {imp.get("status")}')
        print(f'    -> novo      = rejected_silent_zero')
        print(f'    totals       = clients={totals.get("clients")}, '
              f'clients_updated={totals.get("clients_updated")}, '
              f'documents={totals.get("documents")}, '
              f'rows_processed={totals.get("rows_processed")}')
        print()

    if not candidates:
        print('Nada a fazer.')
        return

    if not confirm:
        print('DRY-RUN. Passe --confirm para aplicar.')
        return

    ids = [c['id'] for c in candidates]
    now = datetime.now(timezone.utc).isoformat()
    result = await db.finance_imports.update_many(
        {'id': {'$in': ids}},
        {'$set': {
            'status': 'rejected_silent_zero',
            'rejected_at': now,
            'rejected_by': 'cleanup_script_iter49',
            'rejected_reason': (
                'Import silencioso: parser não encontrou nenhum cliente '
                '(bug corrigido na iter 48). Nunca aplicou dados. '
                'Marcado retroactivamente para permitir reimport.'
            ),
        },
         '$push': {
             'warnings': 'Marcado como silent-zero pelo cleanup_script_iter49.'
         }}
    )
    print(f'Actualizados {result.modified_count} import(s) para "rejected_silent_zero".')
    print(f'Audit backup preservado em: {dump_path}')
    print()
    print('Nenhum registo em finance_clients, finance_documents ou '
          'finance_credit_evolution foi modificado.')


if __name__ == '__main__':
    confirm = '--confirm' in sys.argv
    asyncio.run(main(confirm))
