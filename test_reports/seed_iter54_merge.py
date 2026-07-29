"""Seed a master + duplicate pair for iter54 UI merge test."""
import asyncio, os, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient

SUFFIX = '95401'
DUP = f'DUP{SUFFIX}'
MASTER_ID = 'iter54-master-' + str(uuid.uuid4())[:8]
DUP_ID = 'iter54-dup-' + str(uuid.uuid4())[:8]

async def main(action):
    c = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = c[os.environ['DB_NAME']]
    if action == 'clean':
        r1 = await db.finance_clients.delete_many({'genes_code': {'$in': [SUFFIX, DUP]}})
        r2 = await db.finance_open_documents.delete_many({'genes_code': {'$in': [SUFFIX, DUP]}})
        r3 = await db.finance_merge_reports.delete_many({})
        print(f'cleaned clients={r1.deleted_count} open_docs={r2.deleted_count} reports={r3.deleted_count}')
        return
    # seed
    await db.finance_clients.delete_many({'genes_code': {'$in': [SUFFIX, DUP]}})
    await db.finance_open_documents.delete_many({'genes_code': {'$in': [SUFFIX, DUP]}})
    now = datetime.now(timezone.utc).isoformat()
    base = {
        'name': f'ITER54 TEST {SUFFIX}',
        'overdue_balance_collectable': 0,
        'oldest_overdue_days': 0,
        'financial_status': 'OK',
        'is_blocked': False,
        'manual_marks': [],
        'created_at': now,
        'updated_at': now,
    }
    await db.finance_clients.insert_one({**base, 'id': MASTER_ID, 'genes_code': SUFFIX, 'finance_email': f'm_{SUFFIX}@pdpv.pt'})
    await db.finance_clients.insert_one({**base, 'id': DUP_ID, 'genes_code': DUP, 'account': f'21111{SUFFIX.zfill(5)}', 'genes_account': f'21111{SUFFIX.zfill(5)}', 'carteira': 999.0, 'finance_email': f'd_{SUFFIX}@pdpv.pt'})
    await db.finance_open_documents.insert_one({
        'id': f'FOD-{SUFFIX}-1', 'genes_code': DUP, 'client_name': base['name'],
        'document_number': f'{SUFFIX}/1', 'document_type': 'FT',
        'doc_key': f'{DUP}_{SUFFIX}/1', 'amount': 999.0,
        'invoice_date': '2026-01-10', 'due_date': '2026-02-10',
        'import_id': 'iter54', 'as_of_date': '2026-02-15', 'updated_at': now,
    })
    print(f'SEEDED master_id={MASTER_ID} dup_id={DUP_ID}')

async def verify():
    c = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = c[os.environ['DB_NAME']]
    dup = await db.finance_clients.find_one({'genes_code': DUP}, {'_id': 0})
    master_docs = await db.finance_open_documents.find({'genes_code': SUFFIX}, {'_id': 0}).to_list(10)
    dup_docs = await db.finance_open_documents.find({'genes_code': DUP}, {'_id': 0}).to_list(10)
    print(f'VERIFY dup.is_merged_duplicate={dup and dup.get("is_merged_duplicate")}')
    print(f'VERIFY dup.merged_into={dup and dup.get("merged_into")}')
    print(f'VERIFY master_docs count={len(master_docs)} first_doc_key={master_docs[0]["doc_key"] if master_docs else None}')
    print(f'VERIFY dup_docs count={len(dup_docs)}')

import sys
action = sys.argv[1] if len(sys.argv) > 1 else 'seed'
if action == 'verify':
    asyncio.run(verify())
else:
    asyncio.run(main(action))
