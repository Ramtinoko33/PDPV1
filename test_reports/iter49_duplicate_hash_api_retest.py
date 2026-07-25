"""
Independent focused retest for Iteration 49 duplicate finance import hash bug.

Verifies through the live backend API + MongoDB:
1) silent-zero historical import with same file_hash does NOT block re-upload
2) useful historical import with same file_hash DOES block re-upload
3) simultaneous silent-zero + useful import with same file_hash DOES block re-upload
4) cleanup script dry-run and --confirm behavior, preserving import fields and not
   touching guard finance_clients/finance_documents rows
"""
import asyncio
import hashlib
import io
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from openpyxl import Workbook


load_dotenv('/app/backend/.env')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    for line in Path('/app/frontend/.env').read_text().splitlines():
        if line.startswith('REACT_APP_BACKEND_URL='):
            BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
            break

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
PREFIX = 'QA49R'
SCRIPT = '/app/backend/scripts/mark_silent_zero_imports.py'


def make_overdue_xlsx(marker: str, docs: int = 2) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(['Cliente', 'Cód. Cliente', 'Localidade', 'Região', 'Email',
               'Telefone1', 'Telefone2', 'Importe Total Vencido', 'Saldo Cliente'])
    ws.append([f'Cliente {marker}', f'{PREFIX}{marker}', 'Lisboa', 'Sul', 'qa@example.test',
               None, None, 100.0 * docs, 100.0 * docs])
    ws.append(['', 'Documento', 'Data da fatura', 'Data Vencimento', 'CódSede',
               'Sede', 'Dias Vencidos', 'Importe Vencimiento', 'Vencido Factura'])
    for i in range(docs):
        ws.append(['', f'{marker}/D{i}', datetime(2025, 11, 1), datetime(2025, 12, 1),
                   '01', 'Sede', 30, 100.0, 100.0])
    ws['Z1'] = f'{PREFIX}-{marker}'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


async def cleanup():
    database = await db()
    async for imp in database.finance_imports.find(
        {'filename': {'$regex': f'^{PREFIX}'}}, {'_id': 0, 'original_file_path': 1}
    ):
        p = imp.get('original_file_path')
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    await database.finance_imports.delete_many({'filename': {'$regex': f'^{PREFIX}'}})
    await database.finance_clients.delete_many({'genes_code': {'$regex': f'^{PREFIX}'}})
    await database.finance_documents.delete_many({'genes_code': {'$regex': f'^{PREFIX}'}})
    await database.finance_client_daily_metrics.delete_many({'import_id': {'$regex': f'^{PREFIX}'}})


def login() -> str:
    response = requests.post(
        f'{BASE_URL}/api/auth/login',
        json={'email': 'admin@pdpv.pt', 'password': 'HCNMEnKMLq'},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    return response.json()['token']


def upload(token: str, content: bytes, filename: str) -> requests.Response:
    return requests.post(
        f'{BASE_URL}/api/finance/imports/overdue_balances',
        files={'file': (filename, content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
        headers={'Authorization': f'Bearer {token}'},
        timeout=60,
    )


def assert_applied_totals(totals: dict):
    applied = any((totals.get(k) or 0) > 0 for k in (
        'clients_updated', 'clients_created', 'clients_found', 'clients',
        'documents_created', 'documents'
    ))
    assert applied, totals


async def seed_import(marker: str, file_hash: str, *, useful: bool, suffix: str):
    database = await db()
    await database.finance_imports.insert_one({
        'id': f'{PREFIX}-{suffix}-{marker}',
        'type': 'overdue_balances',
        'source_method': 'manual_upload',
        'filename': f'{PREFIX}-{suffix}-{marker}.xlsx',
        'file_hash': file_hash,
        'uploaded_by': 'qa-retest',
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
        'status': 'imported',
        'totals': {
            'clients': 3 if useful else 0,
            'clients_updated': 3 if useful else 0,
            'clients_found': 3 if useful else 0,
            'documents': 5 if useful else 0,
            'documents_created': 5 if useful else 0,
            'rows_processed': 20,
            'total_balance': 300 if useful else 0,
            'total_overdue': 300 if useful else 0,
        },
        'warnings': [],
        'errors': [],
        'original_file_path': f'/tmp/{PREFIX}-{suffix}-{marker}.xlsx',
    })


async def test_cleanup_script():
    database = await db()
    marker = uuid.uuid4().hex[:8]
    file_hash = hashlib.sha256(f'cleanup-{marker}'.encode()).hexdigest()
    original_path = f'/tmp/{PREFIX}-cleanup-{marker}.xlsx'
    totals = {'clients': 0, 'clients_updated': 0, 'documents': 0,
              'documents_created': 0, 'rows_processed': 200}
    await database.finance_imports.insert_one({
        'id': f'{PREFIX}-cleanup-{marker}',
        'type': 'client_info',
        'source_method': 'manual_upload',
        'filename': f'{PREFIX}-cleanup-{marker}.xlsx',
        'file_hash': file_hash,
        'uploaded_by': 'qa-retest',
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
        'status': 'imported',
        'totals': totals.copy(),
        'warnings': [],
        'errors': [],
        'original_file_path': original_path,
    })
    await database.finance_clients.insert_one({
        'id': f'{PREFIX}-guard-client-{marker}',
        'genes_code': f'{PREFIX}GUARD{marker}',
        'name': 'guard client',
        'overdue_balance_collectable': 123,
        'financial_status': 'ok',
        'is_blocked': False,
        'created_at': '2026-01-01',
        'updated_at': '2026-01-01',
    })
    await database.finance_documents.insert_one({
        'id': f'{PREFIX}-guard-doc-{marker}',
        'client_id': f'{PREFIX}-guard-client-{marker}',
        'genes_code': f'{PREFIX}GUARD{marker}',
        'document_number': 'GUARD/1',
        'amount_open': 123,
        'classification': 'collectable',
        'effective_classification': 'collectable',
        'created_at': '2026-01-01',
        'updated_at': '2026-01-01',
    })

    dry = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, timeout=30)
    assert dry.returncode == 0, dry.stderr
    assert 'DRY-RUN' in dry.stdout, dry.stdout
    dry_doc = await database.finance_imports.find_one({'id': f'{PREFIX}-cleanup-{marker}'}, {'_id': 0})
    assert dry_doc['status'] == 'imported', dry_doc

    confirmed = subprocess.run([sys.executable, SCRIPT, '--confirm'], capture_output=True, text=True, timeout=30)
    assert confirmed.returncode == 0, confirmed.stderr
    imp = await database.finance_imports.find_one({'id': f'{PREFIX}-cleanup-{marker}'}, {'_id': 0})
    cli = await database.finance_clients.find_one({'id': f'{PREFIX}-guard-client-{marker}'}, {'_id': 0})
    doc = await database.finance_documents.find_one({'id': f'{PREFIX}-guard-doc-{marker}'}, {'_id': 0})
    assert imp['status'] == 'rejected_silent_zero', imp
    assert imp['file_hash'] == file_hash, imp
    assert imp['original_file_path'] == original_path, imp
    assert imp['totals'] == totals, imp
    assert cli['overdue_balance_collectable'] == 123, cli
    assert doc['amount_open'] == 123, doc
    return {'dry_run_seen': 'DRY-RUN' in dry.stdout, 'confirm_status': imp['status']}


async def main():
    await cleanup()
    token = login()
    evidence = {}
    try:
        # HASH BYPASS: previous same-hash imported doc had zero applied counters.
        marker = uuid.uuid4().hex[:8]
        content = make_overdue_xlsx(marker, docs=2)
        file_hash = hashlib.sha256(content).hexdigest()
        await seed_import(marker, file_hash, useful=False, suffix='silent')
        response = upload(token, content, f'{PREFIX}-retry-{marker}.xlsx')
        evidence['hash_bypass'] = {'status_code': response.status_code, 'body': response.text[:500]}
        assert response.status_code == 200, response.text
        assert_applied_totals(response.json().get('totals') or {})

        # Exact user-flow edge: once the reimport was useful, the same file must block.
        response = upload(token, content, f'{PREFIX}-retry-second-{marker}.xlsx')
        evidence['hash_sequential_second_reimport'] = {'status_code': response.status_code, 'body': response.text[:500]}
        assert response.status_code == 400, response.text
        assert 'já foi importado' in response.json().get('detail', ''), response.text

        # HASH BLOCK: previous same-hash imported doc was useful.
        marker = uuid.uuid4().hex[:8]
        content = make_overdue_xlsx(marker, docs=2)
        file_hash = hashlib.sha256(content).hexdigest()
        await seed_import(marker, file_hash, useful=True, suffix='useful')
        response = upload(token, content, f'{PREFIX}-dup-{marker}.xlsx')
        evidence['hash_block'] = {'status_code': response.status_code, 'body': response.text[:500]}
        assert response.status_code == 400, response.text
        assert 'já foi importado' in response.json().get('detail', ''), response.text

        # EDGE CASE: silent-zero and useful docs coexist for same hash; useful must win and block.
        marker = uuid.uuid4().hex[:8]
        content = make_overdue_xlsx(marker, docs=2)
        file_hash = hashlib.sha256(content).hexdigest()
        await seed_import(marker, file_hash, useful=False, suffix='silent-edge')
        await seed_import(marker, file_hash, useful=True, suffix='useful-edge')
        response = upload(token, content, f'{PREFIX}-edge-{marker}.xlsx')
        evidence['hash_edge_silent_plus_useful'] = {'status_code': response.status_code, 'body': response.text[:500]}
        assert response.status_code == 400, response.text
        assert 'já foi importado' in response.json().get('detail', ''), response.text

        evidence['cleanup_script'] = await test_cleanup_script()
        evidence['verdict'] = 'passed'
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    finally:
        await cleanup()


if __name__ == '__main__':
    asyncio.run(main())