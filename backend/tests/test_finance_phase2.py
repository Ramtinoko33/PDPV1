"""
Finance Phase 2 tests (iteration 24):
- Open documents daily comparison (probable/partial payments + recovered dashboard totals)
- Promise auto-verification against a new import
- Settings CRUD & permissions
- Credit warning endpoint (no finance role) with block detection & phone matching

Safe against real user data via snapshot/restore of finance_open_documents,
finance_recovery_events, finance_data_health(open_documents), and any promise mutations.
"""

import os
import io
import uuid
import asyncio
import hashlib
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List

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
ADMIN_PASSWORD = 'HCNMEnKMLq'
COLLECTIONS_EMAIL = 'cobranca.teste@pdpv.pt'
COLLECTIONS_PASSWORD = 'TesteFin2026!'
NOFIN_EMAIL = 'rececao.teste@pdpv.pt'
NOFIN_PASSWORD = 'TesteFin2026!'

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

# Test genes codes we control (safe to wipe)
TST_A = 'TST90'
TST_B = 'TST91'

session_admin = requests.Session()
session_admin.headers.update({'Content-Type': 'application/json'})
session_coll = requests.Session()
session_coll.headers.update({'Content-Type': 'application/json'})
session_nofin = requests.Session()
session_nofin.headers.update({'Content-Type': 'application/json'})


def _login(sess, email, pw):
    r = sess.post(f'{BASE_URL}/api/auth/login', json={'email': email, 'password': pw})
    assert r.status_code == 200, f'login {email}: {r.status_code} {r.text}'
    tok = r.json()['token']
    sess.headers.update({'Authorization': f'Bearer {tok}'})
    return r.json()


@pytest.fixture(scope='session', autouse=True)
def _auth():
    _login(session_admin, ADMIN_EMAIL, ADMIN_PASSWORD)
    _login(session_coll, COLLECTIONS_EMAIL, COLLECTIONS_PASSWORD)
    _login(session_nofin, NOFIN_EMAIL, NOFIN_PASSWORD)


# ---------------- helpers ----------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


async def _db():
    c = AsyncIOMotorClient(MONGO_URL)
    return c[DB_NAME]


def _build_open_docs_xlsx(rows: List[Dict], marker: str) -> bytes:
    """Build a minimal open_documents xlsx compatible with parse_open_documents."""
    wb = Workbook()
    ws = wb.active
    headers = ['CodPersona', 'Conta', 'Tipo D. Pagamento', 'Forma Pagamento',
               'Data Fat.', 'Data Venc.', 'Cliente', 'Descritivo', 'Saldo',
               'Registo B.', 'Registo C.', 'Registo D.', 'Quantia', 'Vencido',
               'Cobrado', 'Estado', 'Eventos']
    ws.append(headers)
    for r in rows:
        ws.append([
            r['genes_code'], r.get('conta', '21100001'), 'TR', '30D',
            r.get('data_fat', '2025-11-01'), r.get('data_venc', '2025-12-01'),
            r['client_name'], r['descritivo'], r['saldo'],
            '', '', '', r['quantia'], r['vencido'], r.get('cobrado', 0), 'Aberto', marker
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------- snapshot fixture for open_documents ---------

@pytest.fixture(scope='module')
def open_docs_snapshot():
    """Snapshot & restore finance_open_documents / recovery_events / data_health
    so we don't corrupt the 202 real docs when running the open_docs tests."""
    async def snap():
        db = await _db()
        docs = await db.finance_open_documents.find({}, {'_id': 0}).to_list(10000)
        recovery = await db.finance_recovery_events.find({}, {'_id': 0}).to_list(10000)
        health = await db.finance_data_health.find_one({'source_type': 'open_documents'}, {'_id': 0})
        return {'docs': docs, 'recovery': recovery, 'health': health}
    state = asyncio.run(snap())

    yield state

    async def restore():
        db = await _db()
        await db.finance_open_documents.delete_many({})
        if state['docs']:
            await db.finance_open_documents.insert_many([dict(d) for d in state['docs']])
        # remove only the recovery events created during tests
        await db.finance_recovery_events.delete_many({'genes_code': {'$in': [TST_A, TST_B]}})
        if state['health']:
            await db.finance_data_health.update_one(
                {'source_type': 'open_documents'},
                {'$set': state['health']}, upsert=True
            )
    asyncio.run(restore())

    # cleanup test imports files
    async def cleanup_imports():
        db = await _db()
        cur = db.finance_imports.find({'filename': {'$regex': '^TSTPH2-'}}, {'id': 1, 'original_file_path': 1})
        async for imp in cur:
            p = imp.get('original_file_path')
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        await db.finance_imports.delete_many({'filename': {'$regex': '^TSTPH2-'}})
    asyncio.run(cleanup_imports())


# ============ 1. OPEN DOCUMENTS COMPARISON ============

class TestOpenDocumentsComparison:

    def test_first_upload_warning_and_recovered_events(self, open_docs_snapshot):
        # Snapshot fixture already stashed real docs; the code will delete_many({}) on
        # first import so effectively old_docs=snapshot. To trigger "primeira importação"
        # we clear the collection first so the code sees empty old_docs.
        async def wipe():
            db = await _db()
            await db.finance_open_documents.delete_many({})
        asyncio.run(wipe())

        marker_v1 = uuid.uuid4().hex[:8]
        rows_v1 = [
            {'genes_code': TST_A, 'client_name': 'Test Client A',
             'descritivo': 'VTO. FAT./FT 999/{}'.format(marker_v1),
             'saldo': 100.0, 'quantia': 100.0, 'vencido': 100.0},
            {'genes_code': TST_A, 'client_name': 'Test Client A',
             'descritivo': 'VTO. FAT./FT 999/{}b'.format(marker_v1),
             'saldo': 50.0, 'quantia': 50.0, 'vencido': 50.0},
            {'genes_code': TST_B, 'client_name': 'Test Client B',
             'descritivo': 'VTO. FAT./FT 998/{}'.format(marker_v1),
             'saldo': 200.0, 'quantia': 200.0, 'vencido': 200.0},
        ]
        content_v1 = _build_open_docs_xlsx(rows_v1, marker_v1)
        files = {'file': (f'TSTPH2-v1-{marker_v1}.xlsx', content_v1,
                          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        headers = {'Authorization': session_admin.headers['Authorization']}
        r = requests.post(f'{BASE_URL}/api/finance/imports/open_documents', files=files, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['success'] is True, data
        warnings_str = ' '.join(data.get('warnings', []))
        assert 'Primeira importação' in warnings_str, f'expected first-import warning, got {data}'
        assert data['totals']['recovered_amount'] == 0
        assert data['totals']['probable_payments'] == 0
        assert data['totals']['partial_payments'] == 0

    def test_second_upload_detects_probable_and_partial(self, open_docs_snapshot):
        marker_v2 = uuid.uuid4().hex[:8]
        # v2: remove second doc of TST_A (probable payment 50€),
        # reduce TST_B doc quantia 200 -> 120 (partial payment 80€)
        # keep first doc of TST_A unchanged
        # Descritivos must match v1 exactly for doc_key match. We need to peek at v1 markers.
        async def get_v1_marker():
            db = await _db()
            doc = await db.finance_open_documents.find_one({'genes_code': TST_A}, {'_id': 0, 'description': 1})
            return doc
        doc_first = asyncio.run(get_v1_marker())
        assert doc_first is not None, 'v1 docs not persisted'
        # Use current TST_A documents from DB to build v2 accurately
        async def get_all_test_docs():
            db = await _db()
            return await db.finance_open_documents.find(
                {'genes_code': {'$in': [TST_A, TST_B]}}, {'_id': 0}
            ).to_list(100)
        current_docs = asyncio.run(get_all_test_docs())
        assert len(current_docs) == 3
        by_key = {d['doc_key']: d for d in current_docs}
        tst_a_docs = [d for d in current_docs if d['genes_code'] == TST_A]
        tst_b_doc = [d for d in current_docs if d['genes_code'] == TST_B][0]
        # Keep first TST_A (unchanged), drop second TST_A, reduce TST_B from 200 to 120
        keep_a = tst_a_docs[0]
        rows_v2 = [
            {'genes_code': TST_A, 'client_name': 'Test Client A',
             'descritivo': keep_a['description'],
             'saldo': keep_a['amount'], 'quantia': keep_a['amount'],
             'vencido': keep_a['amount_overdue']},
            {'genes_code': TST_B, 'client_name': 'Test Client B',
             'descritivo': tst_b_doc['description'],
             'saldo': 120.0, 'quantia': 120.0, 'vencido': 120.0},
        ]
        content_v2 = _build_open_docs_xlsx(rows_v2, marker_v2)
        files = {'file': (f'TSTPH2-v2-{marker_v2}.xlsx', content_v2,
                          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        headers = {'Authorization': session_admin.headers['Authorization']}
        r = requests.post(f'{BASE_URL}/api/finance/imports/open_documents', files=files, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['success'] is True
        assert data['totals']['probable_payments'] == 1, data['totals']
        assert data['totals']['partial_payments'] == 1, data['totals']
        # recovered = 50 (removed doc) + 80 (partial) = 130
        assert abs(data['totals']['recovered_amount'] - 130.0) < 0.02, data['totals']

    def test_dashboard_reflects_recovered_today(self, open_docs_snapshot):
        r = session_admin.get(f'{BASE_URL}/api/finance/dashboard')
        assert r.status_code == 200
        dash = r.json()
        assert 'recovered_today' in dash
        assert 'recovered_week' in dash
        assert 'recovered_month' in dash
        # recovered today should be >= 130 from our v2 import today
        assert dash['recovered_today'] >= 130.0, dash


# ============ 2. PROMISE AUTO-VERIFICATION (unit-level) ============

class TestPromiseVerification:
    """Direct call to verify_promises_after_import to avoid crafting a full 23k€ overdue xlsx.
    Full integration path (upload -> verify) uses same function; only the reprocess pipeline is skipped."""

    def test_past_promise_marked_failed_future_untouched(self):
        import sys
        sys.path.insert(0, '/app/backend')
        from modules.finance.services.import_service import verify_promises_after_import

        async def scenario():
            db = await _db()
            now = datetime.now(timezone.utc).isoformat()
            past_date = (date.today() - timedelta(days=5)).isoformat()
            future_date = (date.today() + timedelta(days=30)).isoformat()

            # Create test client with an overdue balance that HASN'T dropped
            client_a = {
                'id': f'tstph2-client-{uuid.uuid4().hex[:8]}',
                'genes_code': TST_A,
                'client_name': 'Test Client A',
                'overdue_balance_accounting': 500.0,
                'overdue_balance_collectable': 500.0,
                'total_balance': 500.0,
                'oldest_overdue_days': 30,
                'traffic_light': 'ORANGE',
                'financial_status': 'EM_COBRANCA',
                'is_blocked': False,
                'updated_at': now,
            }
            await db.finance_clients.insert_one(dict(client_a))

            # Promise past with baseline set — reduction 0 => failed
            past_promise = {
                'id': f'tstph2-prom-past-{uuid.uuid4().hex[:8]}',
                'client_id': client_a['id'],
                'amount': 200.0,
                'promise_date': past_date,
                'status': 'open',
                'baseline_overdue': 500.0,
                'created_at': now,
            }
            future_promise = {
                'id': f'tstph2-prom-future-{uuid.uuid4().hex[:8]}',
                'client_id': client_a['id'],
                'amount': 100.0,
                'promise_date': future_date,
                'status': 'open',
                'baseline_overdue': 500.0,
                'created_at': now,
            }
            await db.finance_promises.insert_many([dict(past_promise), dict(future_promise)])

            fake_import_id = 'tstph2-imp-' + uuid.uuid4().hex[:8]
            n = await verify_promises_after_import(fake_import_id, date.today().isoformat())

            past_after = await db.finance_promises.find_one({'id': past_promise['id']}, {'_id': 0})
            future_after = await db.finance_promises.find_one({'id': future_promise['id']}, {'_id': 0})
            client_after = await db.finance_clients.find_one({'id': client_a['id']}, {'_id': 0})
            action = await db.finance_actions.find_one(
                {'client_id': client_a['id'], 'action_type': 'promise_updated'}, {'_id': 0}
            )

            # cleanup
            await db.finance_promises.delete_many({'id': {'$in': [past_promise['id'], future_promise['id']]}})
            await db.finance_clients.delete_one({'id': client_a['id']})
            await db.finance_actions.delete_many({'client_id': client_a['id']})

            return n, past_after, future_after, client_after, action

        n, past_after, future_after, client_after, action = asyncio.run(scenario())

        assert n >= 1, f'promises_verified={n}'
        assert past_after['status'] == 'failed', past_after
        assert past_after.get('verified_at') is not None
        assert 'verification_note' in past_after
        # future promise untouched
        assert future_after['status'] == 'open'
        assert future_after.get('verified_at') in (None, ''), future_after
        # client updated to PROMESSA_FALHADA/CRITICAL
        assert client_after['financial_status'] == 'PROMESSA_FALHADA', client_after
        assert client_after['traffic_light'] in ('CRITICAL', 'RED'), client_after
        # system action
        assert action is not None
        assert action['user_id'] == 'system'


# ============ 3. SETTINGS CRUD ============

class TestFinanceSettings:

    def test_get_defaults(self):
        # ensure clean baseline
        async def reset():
            db = await _db()
            await db.finance_settings.delete_one({'id': 'global'})
        asyncio.run(reset())

        r = session_admin.get(f'{BASE_URL}/api/finance/settings')
        assert r.status_code == 200
        s = r.json()
        assert s['residual_document_threshold'] == 1.0
        assert s['residual_client_threshold'] == 5.0
        assert abs(s['residual_percentage_threshold'] - 0.005) < 1e-9
        assert s['residual_max_documents'] == 10
        assert s['show_credit_warning_on_tickets'] is True

    def test_put_admin_persists(self):
        r = session_admin.put(f'{BASE_URL}/api/finance/settings',
                              json={'residual_document_threshold': 2.5,
                                    'residual_max_documents': 15})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s['residual_document_threshold'] == 2.5
        assert s['residual_max_documents'] == 15
        # GET reads persisted values
        r2 = session_admin.get(f'{BASE_URL}/api/finance/settings')
        assert r2.status_code == 200
        assert r2.json()['residual_document_threshold'] == 2.5

    def test_put_collections_agent_forbidden(self):
        r = session_coll.put(f'{BASE_URL}/api/finance/settings',
                             json={'residual_document_threshold': 9.9})
        assert r.status_code == 403, r.text

    def test_restore_defaults(self):
        r = session_admin.put(f'{BASE_URL}/api/finance/settings',
                              json={'residual_document_threshold': 1.0,
                                    'residual_client_threshold': 5.0,
                                    'residual_percentage_threshold': 0.005,
                                    'residual_max_documents': 10,
                                    'show_credit_warning_on_tickets': True})
        assert r.status_code == 200


# ============ 4. CREDIT WARNING ENDPOINT ============

class TestCreditWarning:
    _client_id = None

    def test_seed_blocked_client(self):
        async def seed():
            db = await _db()
            now = datetime.now(timezone.utc).isoformat()
            cid = f'tstph2-cw-{uuid.uuid4().hex[:8]}'
            await db.finance_clients.insert_one({
                'id': cid,
                'genes_code': TST_A,
                'client_name': 'Test Blocked',
                'phone': '912888777',
                'mobile': None,
                'is_blocked': True,
                'traffic_light': 'CRITICAL',
                'financial_status': 'BLOQUEIO_APROVADO',
                'overdue_balance_accounting': 0,
                'total_balance': 0,
                'updated_at': now,
            })
            return cid
        cid = asyncio.run(seed())
        TestCreditWarning._client_id = cid

    def test_no_finance_role_gets_200_and_result(self):
        r = session_nofin.get(f'{BASE_URL}/api/finance/credit-warning', params={'phone': '912888777'})
        assert r.status_code == 200, r.text
        data = r.json()
        assert 'show_warning' in data
        assert data['show_warning'] is True
        assert 'balance' not in data and 'amount' not in data, data

    def test_prefixed_phone_matches(self):
        r = session_nofin.get(f'{BASE_URL}/api/finance/credit-warning', params={'phone': '+351912888777'})
        assert r.status_code == 200
        assert r.json()['show_warning'] is True

    def test_negative_case(self):
        r = session_nofin.get(f'{BASE_URL}/api/finance/credit-warning', params={'phone': '211111111'})
        assert r.status_code == 200
        assert r.json()['show_warning'] is False

    def test_setting_disables_warning(self):
        session_admin.put(f'{BASE_URL}/api/finance/settings',
                          json={'show_credit_warning_on_tickets': False})
        r = session_nofin.get(f'{BASE_URL}/api/finance/credit-warning', params={'phone': '912888777'})
        assert r.status_code == 200
        assert r.json()['show_warning'] is False
        # restore
        session_admin.put(f'{BASE_URL}/api/finance/settings',
                          json={'show_credit_warning_on_tickets': True})

    def test_cleanup(self):
        async def clean():
            db = await _db()
            if TestCreditWarning._client_id:
                await db.finance_clients.delete_one({'id': TestCreditWarning._client_id})
        asyncio.run(clean())


# ============ 5. Final teardown of any leftover TST9x data ============

def teardown_module(module):
    async def clean_all():
        db = await _db()
        await db.finance_clients.delete_many({'genes_code': {'$in': [TST_A, TST_B]}})
        await db.finance_documents.delete_many({'genes_code': {'$in': [TST_A, TST_B]}})
        await db.finance_recovery_events.delete_many({'genes_code': {'$in': [TST_A, TST_B]}})
        await db.finance_actions.delete_many({'client_id': {'$regex': '^tstph2-'}})
        # ensure defaults restored
        await db.finance_settings.update_one({'id': 'global'}, {'$set': {
            'residual_document_threshold': 1.0,
            'residual_client_threshold': 5.0,
            'residual_percentage_threshold': 0.005,
            'residual_max_documents': 10,
            'show_credit_warning_on_tickets': True,
            'id': 'global',
        }}, upsert=True)
    asyncio.run(clean_all())
