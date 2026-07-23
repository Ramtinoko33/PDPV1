"""
CLEANUP MANUAL DE PRODUÇÃO — Apagar importações corruptas de hoje.

Contexto: no dia 23/07/2026, uma importação de "Saldos Vencidos" foi
uploaded com 1492 clientes / 0 documentos (parser não reconheceu a
estrutura) e ficou em pending_approval. Como o código de produção
AINDA NÃO tem o safety guard, aprovar essa entrada apagava todos os
saldos vencidos em base.

Este script faz DOIS passos:
  1. Lista as importações do tipo overdue_balances em estado
     pending_approval E com totals.documents == 0.
  2. Marca-as como "rejected" (deixando o file_path intacto para
     auditoria) e regista o motivo.

⚠️  Correr APENAS após revisão da lista impressa no passo 1.
    Passa --confirm para efetivamente atualizar a BD.

Uso:
  python /app/backend/scripts/cleanup_corrupt_overdue_pending.py           # dry-run
  python /app/backend/scripts/cleanup_corrupt_overdue_pending.py --confirm # aplica
"""
import os
import sys
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

    cursor = db.finance_imports.find(query, {
        '_id': 0, 'id': 1, 'filename': 1, 'uploaded_at': 1,
        'totals': 1, 'original_file_path': 1
    })

    found = []
    async for imp in cursor:
        found.append(imp)

    print(f'Encontradas {len(found)} importação(ões) corrupta(s):')
    for imp in found:
        print(f'  - id={imp.get("id")}, ficheiro={imp.get("filename")}, '
              f'clientes={imp.get("totals", {}).get("clients")}, '
              f'documentos={imp.get("totals", {}).get("documents")}, '
              f'uploaded_at={imp.get("uploaded_at")}')

    if not found:
        print('Nada a fazer.')
        return

    if not confirm:
        print('\nDRY-RUN: passe --confirm para atualizar a base de dados.')
        return

    ids = [imp['id'] for imp in found]
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
        }}
    )
    print(f'\nAtualizadas {result.modified_count} importação(ões) para "rejected".')


if __name__ == '__main__':
    confirm = '--confirm' in sys.argv
    asyncio.run(main(confirm))
