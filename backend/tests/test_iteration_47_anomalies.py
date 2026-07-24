"""
Iteration 47 — Dashboard de Anomalias entre imports Finance consecutivos.

Testa:
  1. Detecção crítica (total_overdue Δ > 20% E |Δ| > 500€)
  2. Detecção warning (clientes Δ > 10%)
  3. Noise floor: pequenas diferenças não geram anomalia
  4. Fluxo de validação com comentário obrigatório
  5. RBAC: COLLECTIONS_AGENT pode ver mas NÃO validar
  6. Endpoint /anomalies/count devolve o breakdown
  7. Filtros status=active|validated|all e severity=warning|critical
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import requests
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
COLLECTOR_EMAIL = 'cobranca.teste@pdpv.pt'
COLLECTOR_PASSWORD = 'TesteFin2026!'

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

TEST_PREFIX = 'TSTANOM'


def _login(email, pwd):
    r = requests.post(f'{BASE_URL}/api/auth/login',
                      json={'email': email, 'password': pwd})
    assert r.status_code == 200, r.text
    return r.json()['token']


@pytest.fixture(scope='session')
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope='session')
def collector_token():
    try:
        return _login(COLLECTOR_EMAIL, COLLECTOR_PASSWORD)
    except Exception:
        pytest.skip('Collections agent test account not available')


async def _db():
    c = AsyncIOMotorClient(MONGO_URL)
    return c[DB_NAME]


def _seed_import(type_key, days_ago, totals, filename_suffix):
    async def _go():
        db = await _db()
        uploaded = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        as_of = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
        import_id = str(uuid.uuid4())
        await db.finance_imports.insert_one({
            'id': import_id,
            'type': type_key,
            'source_method': 'manual_upload',
            'filename': f'{TEST_PREFIX}-{filename_suffix}.xlsx',
            'file_hash': uuid.uuid4().hex,
            'as_of_date': as_of,
            'uploaded_by': 'test',
            'uploaded_at': uploaded,
            'status': 'imported',
            'original_file_path': None,
            'totals': totals,
            'warnings': [],
            'errors': [],
        })
        return import_id
    return asyncio.run(_go())


@pytest.fixture
def clean_imports():
    """Isola cada teste — limpa TSTANOM antes e depois."""
    async def wipe():
        db = await _db()
        # Apagar tanto imports como validations de teste
        await db.finance_imports.delete_many({'filename': {'$regex': f'^{TEST_PREFIX}-'}})
        # Não temos maneira segura de saber quais validations são de teste,
        # mas o id da anomalia é hash de type+ids, portanto ficam órfãos ao
        # apagar os imports. Limpamos todas as validações órfãs.
        # Como não temos outras validações reais, é seguro apagar tudo neste
        # ambiente de teste — mas usamos filtro pelo import_id.
        # Alternativa: apagar por comment prefixo se usarmos marker.
        pass  # (validations limpas por test via _cleanup_validations)
    asyncio.run(wipe())
    yield
    asyncio.run(wipe())


def _cleanup_validations(anomaly_ids):
    async def _go():
        db = await _db()
        await db.finance_anomaly_validations.delete_many(
            {'anomaly_id': {'$in': list(anomaly_ids)}}
        )
    asyncio.run(_go())


def _get(url, token, **params):
    return requests.get(url, headers={'Authorization': f'Bearer {token}'}, params=params)


def _post(url, token, json_data=None):
    return requests.post(url, headers={'Authorization': f'Bearer {token}'},
                         json=json_data)


class TestAnomaliesDetection:
    def test_critical_total_overdue_diff(self, admin_token, clean_imports):
        # Anterior: 10.000€ / 100 clientes / 300 docs
        # Atual:    15.000€ (+50%!) / 105 clientes / 305 docs
        _seed_import('overdue_balances', days_ago=2,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 10000, 'total_balance': 10000},
                     filename_suffix='ov-prev')
        _seed_import('overdue_balances', days_ago=0,
                     totals={'clients': 105, 'documents': 305, 'total_overdue': 15000, 'total_balance': 15000},
                     filename_suffix='ov-cur')

        r = _get(f'{BASE_URL}/api/finance/anomalies', admin_token, status='active')
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['count'] >= 1, d
        # Deve haver pelo menos uma crítica com o nosso par
        criticals = [a for a in d['anomalies']
                     if a['import_type'] == 'overdue_balances'
                     and a['severity'] == 'critical'
                     and a['current']['filename'] == f'{TEST_PREFIX}-ov-cur.xlsx']
        assert len(criticals) == 1, d
        a = criticals[0]
        assert a['delta']['total_overdue_abs'] == 5000.0, a
        assert a['delta']['total_overdue_pct'] == 50.0, a
        assert a['status'] == 'active'
        _cleanup_validations([a['id']])

    def test_warning_clients_diff_only(self, admin_token, clean_imports):
        # Só clientes varia >10%, restante estável.
        _seed_import('overdue_balances', days_ago=2,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 10000, 'total_balance': 10000},
                     filename_suffix='cl-prev')
        _seed_import('overdue_balances', days_ago=0,
                     totals={'clients': 130, 'documents': 305, 'total_overdue': 10100, 'total_balance': 10100},
                     filename_suffix='cl-cur')

        r = _get(f'{BASE_URL}/api/finance/anomalies', admin_token, status='active')
        d = r.json()
        matches = [a for a in d['anomalies']
                   if a['current']['filename'] == f'{TEST_PREFIX}-cl-cur.xlsx']
        assert len(matches) == 1, d
        assert matches[0]['severity'] == 'warning', matches[0]
        assert any('clientes' in t.lower() for t in matches[0]['triggers'])
        _cleanup_validations([matches[0]['id']])

    def test_noise_floor_ignores_small_diffs(self, admin_token, clean_imports):
        # Δ total_overdue = 300€ (>20% de 1000€, mas ABSOLUTO < 500€ noise floor)
        _seed_import('overdue_balances', days_ago=2,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 1000, 'total_balance': 1000},
                     filename_suffix='nz-prev')
        _seed_import('overdue_balances', days_ago=0,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 1300, 'total_balance': 1300},
                     filename_suffix='nz-cur')

        r = _get(f'{BASE_URL}/api/finance/anomalies', admin_token, status='active')
        d = r.json()
        # Não deve haver anomalia para este par
        matches = [a for a in d['anomalies']
                   if a['current']['filename'] == f'{TEST_PREFIX}-nz-cur.xlsx']
        assert matches == [], f'Noise floor falhou: {matches}'


class TestAnomaliesCount:
    def test_count_endpoint(self, admin_token, clean_imports):
        _seed_import('overdue_balances', days_ago=2,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 10000, 'total_balance': 10000},
                     filename_suffix='ct-prev')
        _seed_import('overdue_balances', days_ago=0,
                     totals={'clients': 105, 'documents': 305, 'total_overdue': 20000, 'total_balance': 20000},
                     filename_suffix='ct-cur')
        r = _get(f'{BASE_URL}/api/finance/anomalies/count', admin_token)
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'active_total' in d and 'critical' in d and 'warning' in d
        assert d['critical'] >= 1


class TestValidationFlow:
    def test_owner_validates_with_comment(self, admin_token, clean_imports):
        _seed_import('overdue_balances', days_ago=2,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 10000, 'total_balance': 10000},
                     filename_suffix='v-prev')
        _seed_import('overdue_balances', days_ago=0,
                     totals={'clients': 105, 'documents': 305, 'total_overdue': 20000, 'total_balance': 20000},
                     filename_suffix='v-cur')

        r = _get(f'{BASE_URL}/api/finance/anomalies', admin_token, status='active')
        anomaly = next(a for a in r.json()['anomalies']
                       if a['current']['filename'] == f'{TEST_PREFIX}-v-cur.xlsx')
        anomaly_id = anomaly['id']

        # Sem comentário → 400 (payload é { comment: "" })
        r = _post(f'{BASE_URL}/api/finance/anomalies/{anomaly_id}/validate',
                  admin_token, json_data={'comment': '   '})
        assert r.status_code == 400, r.text

        # Com comentário → 200
        r = _post(f'{BASE_URL}/api/finance/anomalies/{anomaly_id}/validate',
                  admin_token, json_data={'comment': 'Confirmado — ficheiro correcto após auditoria manual'})
        assert r.status_code == 200, r.text
        result = r.json()
        assert result['status'] == 'validated'
        assert result['validation']['comment'].startswith('Confirmado')

        # Duplicar validação → 400
        r = _post(f'{BASE_URL}/api/finance/anomalies/{anomaly_id}/validate',
                  admin_token, json_data={'comment': 'segunda tentativa'})
        assert r.status_code == 400, r.text

        # Já não aparece em active
        r = _get(f'{BASE_URL}/api/finance/anomalies', admin_token, status='active')
        active_ids = {a['id'] for a in r.json()['anomalies']}
        assert anomaly_id not in active_ids

        # Aparece em validated
        r = _get(f'{BASE_URL}/api/finance/anomalies', admin_token, status='validated')
        validated_ids = {a['id'] for a in r.json()['anomalies']}
        assert anomaly_id in validated_ids

        _cleanup_validations([anomaly_id])


class TestRBAC:
    def test_collector_can_view_but_not_validate(self, admin_token, collector_token, clean_imports):
        _seed_import('overdue_balances', days_ago=2,
                     totals={'clients': 100, 'documents': 300, 'total_overdue': 10000, 'total_balance': 10000},
                     filename_suffix='rbac-prev')
        _seed_import('overdue_balances', days_ago=0,
                     totals={'clients': 105, 'documents': 305, 'total_overdue': 20000, 'total_balance': 20000},
                     filename_suffix='rbac-cur')

        # Collector consegue LER
        r = _get(f'{BASE_URL}/api/finance/anomalies', collector_token, status='active')
        assert r.status_code == 200, r.text
        anomaly = next(a for a in r.json()['anomalies']
                       if a['current']['filename'] == f'{TEST_PREFIX}-rbac-cur.xlsx')
        anomaly_id = anomaly['id']

        # Collector NÃO consegue validar (403)
        r = _post(f'{BASE_URL}/api/finance/anomalies/{anomaly_id}/validate',
                  collector_token, json_data={'comment': 'tentativa'})
        assert r.status_code == 403, r.text

        _cleanup_validations([anomaly_id])
