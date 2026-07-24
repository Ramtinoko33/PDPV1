"""
CLEANUP MANUAL DE PRODUÇÃO — Marcar importações Saldos Vencidos corruptas
como "rejected" para desbloquear o painel sem tocar em dados de negócio.

Contexto: no dia 23/07/2026, uma importação de "Saldos Vencidos" foi
uploaded com 1492 clientes / 0 documentos (parser não reconheceu a
estrutura) e ficou em pending_approval. Como o código de produção
(no momento em que este script foi escrito) AINDA NÃO tem o safety
guard, aprovar essa entrada apagava todos os saldos vencidos em base.

Este script:
  1. Faz SEMPRE um dump JSON dos registos actualmente em risco para
     `/tmp/finance_cleanup_backup_<timestamp>.json` (audit trail), antes
     de qualquer alteração à BD.
  2. Lista as importações do tipo overdue_balances em estado
     pending_approval E com totals.documents == 0. Mostra também
     os campos-chave para revisão humana.
  3. Se `--confirm` for passado, marca-as como "rejected" preservando:
        - o file_path original (o ficheiro em disco não é apagado)
        - todos os totais originais
        - o histórico (uploaded_at, uploaded_by, etc.)
     Apenas adiciona status=rejected, rejected_at e o campo errors com
     a razão do cleanup.
  4. Não altera nem apaga NENHUM registo em finance_documents,
     finance_clients ou qualquer outra colecção de negócio. Só toca
     em finance_imports.

⚠️  RECOMENDAÇÃO ANTES DE CORRER --confirm:
    • Fazer snapshot da BD via `mongodump` (ou o mecanismo da tua stack).
    • Verificar o dump JSON gerado no passo 1.
    • Correr primeiro em dry-run e conferir a lista impressa.

Uso:
  python /app/backend/scripts/cleanup_corrupt_overdue_pending.py           # dry-run + dump
  python /app/backend/scripts/cleanup_corrupt_overdue_pending.py --confirm # aplica

Ambiente:
  Lê MONGO_URL e DB_NAME de /app/backend/.env (via dotenv). Correr no
  mesmo shell/servidor onde a produção tem esses valores.
"""
import os
import sys
import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']


async def main(confirm: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    query = {
        'type': 'overdue_balances',
        'status': 'pending_approval',
        'totals.documents': 0,
    }

    # Snapshot COMPLETO dos registos afetados (audit trail)
    full_docs = []
    async for imp in db.finance_imports.find(query, {'_id': 0}):
        full_docs.append(imp)

    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dump_path = f'/tmp/finance_cleanup_backup_{ts}.json'
    with open(dump_path, 'w', encoding='utf-8') as f:
        json.dump(full_docs, f, ensure_ascii=False, indent=2, default=str)

    print(f'Encontradas {len(full_docs)} importação(ões) corrupta(s).')
    print(f'Backup completo escrito em: {dump_path}')
    print()
    for imp in full_docs:
        totals = imp.get('totals') or {}
        print(f'  - id={imp.get("id")}')
        print(f'    ficheiro       = {imp.get("filename")}')
        print(f'    uploaded_at    = {imp.get("uploaded_at")}')
        print(f'    uploaded_by    = {imp.get("uploaded_by")}')
        print(f'    clientes       = {totals.get("clients")}')
        print(f'    documentos     = {totals.get("documents")}')
        print(f'    total_vencido  = {totals.get("total_overdue")}')
        print(f'    original_file  = {imp.get("original_file_path")}')
        print()

    if not full_docs:
        print('Nada a fazer.')
        return

    if not confirm:
        print('DRY-RUN. Nenhuma alteração feita à BD.')
        print('Reveja a listagem acima e o ficheiro de backup, e depois')
        print('corra novamente com  --confirm  para aplicar.')
        return

    ids = [imp['id'] for imp in full_docs]
    now = datetime.now(timezone.utc).isoformat()
    result = await db.finance_imports.update_many(
        {'id': {'$in': ids}},
        {'$set': {
            'status': 'rejected',
            'errors': [
                'Rejeitado manualmente pelo cleanup script — parser produziu '
                '0 documentos com clientes > 0. Provável ficheiro corrupto ou '
                'com tipo errado. Nunca chegou a aplicar dados.'
            ],
            'rejected_at': now,
            'rejected_by': 'cleanup_script',
        }}
    )
    # Nada mais é tocado — finance_documents, finance_clients, etc. ficam intactos.
    print(f'Atualizadas {result.modified_count} importação(ões) para "rejected".')
    print(f'Audit backup preservado em: {dump_path}')


if __name__ == '__main__':
    confirm = '--confirm' in sys.argv
    asyncio.run(main(confirm))
