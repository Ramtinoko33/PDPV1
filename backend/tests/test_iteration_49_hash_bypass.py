"""
Iteration 49 — Duplicate hash bypass + silent-zero cleanup script.

Depois de deploy da iter 48, o utilizador ficou incapaz de reimportar os
ficheiros infocliente_24_07.xlsx e evolucaocredito3em3meses_24_07.xlsx
porque a check de hash aplicacional bloqueava mesmo os imports antigos que
não aplicaram nada em BD.

Este suite valida:
  1. HASH BYPASS — upload cujo hash existe MAS o import anterior tem
     clients_updated == 0 e documents_created == 0 é aceite.
  2. HASH BLOCK  — upload cujo hash existe E o import anterior tem
     clients_updated > 0 continua a ser bloqueado (HTTP 400).
  3. SCRIPT DRY-RUN não altera BD.
  4. SCRIPT --confirm marca imports silenciosos como
     status='rejected_silent_zero' preservando file_hash/original_file_path,
     sem tocar em finance_clients ou finance_documents.
"""
import io
import os
import sys
import uuid
import asyncio
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from openpyxl import Workbook
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')

ADMIN_EMAIL = 'admin@pdpv.pt'
ADMIN_PASSWORD = os.environ.get('TEST_ADMIN_PASSWORD', 'HCNMEnKMLq')
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

TEST_PREFIX = 'TSTHB49'

session = requests.Session()
session.headers.update({'Content-Type': 'application/json'})


def _login():
    r = session.post(f'{BASE_URL}/api/auth/login',
                     json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    session.headers.update({'Authorization': f'Bearer {r.json()["token"]}'})


@pytest.fixture(scope='session', autouse=True)
def _auth():
    _login()


async def _db():
    c = AsyncIOMotorClient(MONGO_URL)
    return c[DB_NAME]


def _make_overdue_xlsx(marker: str, docs: int = 3) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(['Cliente', 'Cód. Cliente', 'Localidade', 'Região', 'Email',
               'Telefone1', 'Telefone2', 'Importe Total Vencido', 'Saldo Cliente'])
    ws.append([f'Cli {marker}', f'HB{marker}', 'Lx', 'Sul', 'x@x.pt',
               None, None, 100.0 * docs, 100.0 * docs])
    ws.append(['', 'Documento', 'Data da fatura', 'Data Vencimento', 'CódSede',
               'Sede', 'Dias Vencidos', 'Importe Vencimiento', 'Vencido Factura'])
    for i in range(docs):
        ws.append(['', f'{marker}/D{i}', datetime(2025, 11, 1), datetime(2025, 12, 1),
                   '01', 'Sede', 30, 100.0, 100.0])
    ws['Z1'] = f'MK-{marker}'
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _upload(content: bytes, import_type: str, filename: str):
    files = {'file': (filename, content,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    return requests.post(
        f'{BASE_URL}/api/finance/imports/{import_type}',
        files=files,
        headers={'Authorization': session.headers['Authorization']},
    )


@pytest.fixture
def cleanup_test_imports():
    """Apaga imports/prefixed antes e depois."""
    async def _wipe():
        db = await _db()
        # Apaga imports e ficheiros
        async for imp in db.finance_imports.find(
            {'filename': {'$regex': f'^{TEST_PREFIX}'}}, {'id': 1, 'original_file_path': 1}
        ):
            p = imp.get('original_file_path')
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
        await db.finance_imports.delete_many({'filename': {'$regex': f'^{TEST_PREFIX}'}})
    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


# ============ HASH BYPASS BEHAVIOUR ============

class TestHashBypass:
    def test_reimport_allowed_when_previous_had_zero_clients(self, cleanup_test_imports):
        """Simular scenario user: import antigo status='imported' mas totals.clients==0.
        Reupload do mesmo ficheiro deve passar em vez de dar HTTP 400."""
        marker = uuid.uuid4().hex[:8]
        content = _make_overdue_xlsx(marker)
        file_hash = hashlib.sha256(content).hexdigest()

        # Cria manualmente um import "silencioso" (status imported, 0 clientes)
        async def _seed():
            db = await _db()
            await db.finance_imports.insert_one({
                'id': str(uuid.uuid4()),
                'type': 'overdue_balances',
                'source_method': 'manual_upload',
                'filename': f'{TEST_PREFIX}-zero-{marker}.xlsx',
                'file_hash': file_hash,
                'uploaded_by': 'test',
                'uploaded_at': datetime.now(timezone.utc).isoformat(),
                'status': 'imported',
                'totals': {'clients': 0, 'clients_updated': 0,
                           'documents': 0, 'documents_created': 0,
                           'rows_processed': 3, 'total_balance': 0,
                           'total_overdue': 0},
                'warnings': ['legacy silent-zero'],
                'errors': [],
            })
        asyncio.run(_seed())

        # Reupload mesmo ficheiro → deve passar
        r = _upload(content, 'overdue_balances', f'{TEST_PREFIX}-retry-{marker}.xlsx')
        assert r.status_code == 200, r.text
        # Novo import deve ter clientes/docs > 0 (parseou correctamente)
        totals = r.json()['totals']
        applied = (
            (totals.get('clients_updated') or 0) > 0
            or (totals.get('clients_created') or 0) > 0
            or (totals.get('clients') or 0) > 0
            or (totals.get('documents_created') or 0) > 0
            or (totals.get('documents') or 0) > 0
        )
        assert applied, totals

    def test_reimport_blocked_when_previous_was_useful(self, cleanup_test_imports):
        """Se o import anterior foi realmente aplicado, duplicado é bloqueado."""
        marker = uuid.uuid4().hex[:8]
        content = _make_overdue_xlsx(marker, docs=2)
        file_hash = hashlib.sha256(content).hexdigest()

        # Seed um import anterior "útil" (status=imported, clients_updated>0)
        async def _seed():
            db = await _db()
            await db.finance_imports.insert_one({
                'id': f'useful-{marker}',
                'type': 'overdue_balances',
                'source_method': 'manual_upload',
                'filename': f'{TEST_PREFIX}-useful-{marker}.xlsx',
                'file_hash': file_hash,
                'uploaded_by': 'test',
                'uploaded_at': datetime.now(timezone.utc).isoformat(),
                'status': 'imported',
                'totals': {'clients': 3, 'clients_updated': 3,
                           'documents': 5, 'documents_created': 5,
                           'rows_processed': 5, 'total_balance': 300,
                           'total_overdue': 300},
                'warnings': [], 'errors': [],
            })
        asyncio.run(_seed())

        # Upload mesmo hash → HTTP 400
        r = _upload(content, 'overdue_balances', f'{TEST_PREFIX}-dup-{marker}.xlsx')
        assert r.status_code == 400, r.text
        assert 'já foi importado' in r.json()['detail']


# ============ CLEANUP SCRIPT ============

class TestCleanupScript:
    SCRIPT = '/app/backend/scripts/mark_silent_zero_imports.py'

    def test_dry_run_leaves_db_unchanged(self, cleanup_test_imports):
        marker = uuid.uuid4().hex[:8]
        # Seed 1 silent-zero import
        async def _seed():
            db = await _db()
            await db.finance_imports.insert_one({
                'id': f'silentz-{marker}',
                'type': 'client_info',
                'source_method': 'manual_upload',
                'filename': f'{TEST_PREFIX}-sz-{marker}.xlsx',
                'file_hash': hashlib.sha256(marker.encode()).hexdigest(),
                'uploaded_by': 'test',
                'uploaded_at': datetime.now(timezone.utc).isoformat(),
                'status': 'imported',
                'totals': {'clients': 0, 'clients_updated': 0,
                           'documents': 0, 'documents_created': 0,
                           'rows_processed': 200},
                'warnings': [], 'errors': [],
                'original_file_path': '/tmp/fake.xlsx',
            })
        asyncio.run(_seed())

        # Corre dry-run
        result = subprocess.run(
            [sys.executable, self.SCRIPT],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert 'DRY-RUN' in result.stdout
        assert f'silentz-{marker}' in result.stdout

        # BD não mudou
        async def _read():
            db = await _db()
            return await db.finance_imports.find_one({'id': f'silentz-{marker}'})
        doc = asyncio.run(_read())
        assert doc['status'] == 'imported', 'dry-run alterou a BD!'

    def test_confirm_marks_silent_zero_as_rejected(self, cleanup_test_imports):
        marker = uuid.uuid4().hex[:8]
        # Seed
        async def _seed():
            db = await _db()
            await db.finance_imports.insert_one({
                'id': f'silentz2-{marker}',
                'type': 'credit_evolution',
                'source_method': 'manual_upload',
                'filename': f'{TEST_PREFIX}-sz2-{marker}.xlsx',
                'file_hash': hashlib.sha256((marker + '_2').encode()).hexdigest(),
                'uploaded_by': 'test',
                'uploaded_at': datetime.now(timezone.utc).isoformat(),
                'status': 'imported',
                'totals': {'clients': 0, 'clients_updated': 0,
                           'documents_created': 0, 'rows_processed': 500},
                'warnings': [], 'errors': [],
                'original_file_path': '/tmp/fake2.xlsx',
            })
            # Semente cliente/documento reais que NÃO devem ser tocados
            await db.finance_clients.insert_one({
                'id': f'guard-cli-{marker}', 'genes_code': f'GUARD{marker}',
                'name': 'guard', 'overdue_balance_collectable': 100,
                'oldest_overdue_days': 0, 'financial_status': 'ok',
                'is_blocked': False, 'manual_marks': [],
                'created_at': '2026-01-01', 'updated_at': '2026-01-01',
            })
        asyncio.run(_seed())

        result = subprocess.run(
            [sys.executable, self.SCRIPT, '--confirm'],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr

        async def _verify():
            db = await _db()
            imp = await db.finance_imports.find_one({'id': f'silentz2-{marker}'})
            cli = await db.finance_clients.find_one({'id': f'guard-cli-{marker}'})
            return imp, cli
        imp, cli = asyncio.run(_verify())

        # Import marcado como rejected_silent_zero
        assert imp['status'] == 'rejected_silent_zero', imp
        assert 'rejected_reason' in imp
        assert imp.get('file_hash')  # preservado
        assert imp.get('original_file_path')  # preservado
        # Cliente NÃO tocado
        assert cli is not None
        assert cli['overdue_balance_collectable'] == 100

        # Cleanup do cliente de guard
        async def _cli_cleanup():
            db = await _db()
            await db.finance_clients.delete_one({'id': f'guard-cli-{marker}'})
        asyncio.run(_cli_cleanup())
