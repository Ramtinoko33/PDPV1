"""
CLEANUP MANUAL DE PRODUÇÃO — Consolidar clientes duplicados criados por
uso incorrecto de CodPersona/Conta antes da iter 51.

Este CLI é um wrapper fino sobre `modules.finance.services.merge_service`
que é a MESMA lógica exposta pelos endpoints OWNER-only:

  POST /api/finance/merge-duplicates/dry-run
  POST /api/finance/merge-duplicates/confirm

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

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

sys.path.insert(0, '/app/backend')
from modules.finance.services.merge_service import build_plan, apply_plan  # noqa: E402


MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']


async def main(confirm: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    plan = await build_plan(db)

    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dump_path = f'/tmp/finance_merge_backup_{ts}.json'
    dump_payload = {**plan, 'mode': 'confirm' if confirm else 'dry-run'}
    with open(dump_path, 'w', encoding='utf-8') as f:
        json.dump(dump_payload, f, ensure_ascii=False, indent=2, default=str)

    summary = plan['summary']
    print(
        f'Encontrados {summary["masters"]} master(s) com '
        f'{summary["duplicates"]} duplicado(s).'
    )
    print(f'Backup completo em: {dump_path}')
    print()
    for g in plan['groups'][:20]:
        m = g['master']
        print(f'MASTER {m.get("genes_code")} — {m.get("name")}  (id={m.get("id")})')
        for d in g['duplicates']:
            print(f'  ← DUP {d.get("genes_code")} (id={d.get("id")}) name={d.get("name")!r}')
            if d.get('_updates_for_master'):
                for k, v in d['_updates_for_master'].items():
                    print(f'      MIGRATE→MASTER {k}={v!r}')
            if d.get('_conflicts'):
                for c in d['_conflicts']:
                    print(
                        f'      CONFLICT {c["field"]}: '
                        f'master={c["master_value"]!r} preservado; '
                        f'dup={c["duplicate_value"]!r} ignorado'
                    )
        print()
    if len(plan['groups']) > 20:
        print(f'... e mais {len(plan["groups"])-20} grupo(s).')
    if summary['conflicts_preserved']:
        print(f'⚠️  Total de {summary["conflicts_preserved"]} conflitos preservam valor do master.')
        print('    Ver detalhe completo no backup JSON acima.')
    print()

    if summary['masters'] == 0:
        print('Nada a fazer.')
        return

    if not confirm:
        print('DRY-RUN. Passe --confirm para aplicar.')
        return

    stats = await apply_plan(db, plan, actor='merge_script_cli')
    print(f'✅ Consolidados {stats["merged_count"]} duplicado(s) em {stats["masters_touched"]} master(s).')
    if stats['remap_stats']:
        print('Remapeamentos aplicados:')
        for k, v in sorted(stats['remap_stats'].items()):
            print(f'  {k}: {v} doc(s)')
    print(f'Audit backup preservado em: {dump_path}')


if __name__ == '__main__':
    confirm = '--confirm' in sys.argv
    asyncio.run(main(confirm))
