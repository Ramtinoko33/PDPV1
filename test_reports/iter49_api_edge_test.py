import asyncio
import hashlib
import io
import os
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from openpyxl import Workbook


load_dotenv('/app/backend/.env')
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
PREFIX = 'BUG49QA'


def make_client_info_xlsx(code: str, marker: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(['Alm.', 'Conta', 'Cliente', 'Saldo Conta', 'Saldo Efec.', 'Saldo Desc.', 'Saldo Dev.', 'Carteira', 'Domiciliações', 'Risco', 'Albaranado', 'Forma Pagamento', 'Eventos'])
    ws.append([1, code, f'Cliente {marker}', 123.45, 10, 2, 1, 500, 0, 1000, 0, 'Pagamento a 30 dias', marker])
    ws['ZZ1'] = marker
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def login() -> str:
    r = requests.post(f'{BASE_URL}/api/auth/login', json={'email': 'admin@pdpv.pt', 'password': 'HCNMEnKMLq'}, timeout=30)
    assert r.status_code == 200, f'login failed {r.status_code} {r.text}'
    return r.json()['token']


def upload(token: str, content: bytes, filename: str):
    files = {'file': (filename, content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    return requests.post(f'{BASE_URL}/api/finance/imports/client_info', files=files, headers={'Authorization': f'Bearer {token}'}, timeout=60)


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    marker = uuid.uuid4().hex[:8]
    code = f'{PREFIX}{marker}'
    content = make_client_info_xlsx(code, marker)
    file_hash = hashlib.sha256(content).hexdigest()
    before_counts = {
        'clients': await db.finance_clients.count_documents({}),
        'documents': await db.finance_documents.count_documents({}),
        'credit_evolution': await db.finance_credit_evolution.count_documents({}),
    }

    await db.finance_imports.delete_many({'filename': {'$regex': f'^{PREFIX}'}})
    await db.finance_clients.delete_many({'genes_code': code})
    await db.finance_clients.insert_one({
        'id': f'{PREFIX}-client-{marker}',
        'genes_code': code,
        'name': f'Cliente {marker}',
        'overdue_balance_collectable': 0,
        'oldest_overdue_days': 0,
        'financial_status': 'ok',
        'is_blocked': False,
        'manual_marks': [],
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    })
    silent_id = f'{PREFIX}-silent-{marker}'
    await db.finance_imports.insert_one({
        'id': silent_id,
        'type': 'client_info',
        'source_method': 'manual_upload',
        'filename': f'{PREFIX}-silent-{marker}.xlsx',
        'file_hash': file_hash,
        'uploaded_by': 'bug49qa',
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
        'status': 'imported',
        'totals': {'clients': 0, 'clients_updated': 0, 'clients_found': 0, 'documents': 0, 'documents_created': 0, 'rows_processed': 200},
        'warnings': [],
        'errors': [],
        'original_file_path': f'/tmp/{PREFIX}-silent-{marker}.xlsx',
    })

    token = login()
    first = upload(token, content, f'{PREFIX}-retry-{marker}.xlsx')
    first_json = None
    try:
        first_json = first.json()
    except Exception:
        first_json = first.text
    second = upload(token, content, f'{PREFIX}-third-{marker}.xlsx')
    try:
        second_json = second.json()
    except Exception:
        second_json = second.text

    after_counts = {
        'clients': await db.finance_clients.count_documents({}),
        'documents': await db.finance_documents.count_documents({}),
        'credit_evolution': await db.finance_credit_evolution.count_documents({}),
    }
    imports = await db.finance_imports.find({'file_hash': file_hash}, {'_id': 0, 'id': 1, 'filename': 1, 'status': 1, 'totals': 1}).to_list(10)

    print('BASE_URL', BASE_URL)
    print('silent_id', silent_id)
    print('first_status', first.status_code)
    print('first_body', first_json)
    print('second_status', second.status_code)
    print('second_body', second_json)
    print('same_hash_imports', imports)
    print('before_counts', before_counts)
    print('after_counts', after_counts)

    # cleanup only this script's created records/files
    cursor = db.finance_imports.find({'filename': {'$regex': f'^{PREFIX}'}})
    async for imp in cursor:
        p = imp.get('original_file_path')
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    await db.finance_imports.delete_many({'filename': {'$regex': f'^{PREFIX}'}})
    await db.finance_clients.delete_many({'genes_code': code})


if __name__ == '__main__':
    asyncio.run(main())