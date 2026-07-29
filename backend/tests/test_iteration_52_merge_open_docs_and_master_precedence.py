"""
Iteration 52 — P0 hardening do script de merge de duplicados Finance.

Fixa os requisitos que o utilizador levantou antes do deploy em Produção:

  A. `finance_open_documents` deve ser remapeado do duplicado para o master
     (dup_id → master_id via genes_code) e o `doc_key` derivado
     `<genes_code>_<document_number>` deve ficar reconstruído com o
     genes_code do master.
  B. A precedência do master é ABSOLUTA:
       - master vazio + duplicado preenchido → migrar para master
       - master preenchido + duplicado diferente → PRESERVAR master
         e registar `merge_conflicts` (dict estruturado com master_value
         e duplicate_value)
       - master preenchido + duplicado vazio → não mexer
       - ambos vazios → não mexer
  C. Duplicado fica soft-marcado (`is_merged_duplicate=True`), a
     `finance_credit_evolution` migra para o master, e a lista pública de
     clientes esconde o duplicado.
  D. Sumário e ficheiro de audit (backup JSON) reportam explicitamente
     os conflitos preservados.
"""
import io
import os
import sys
import json
import glob
import uuid
import asyncio
import subprocess
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

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

SCRIPT = '/app/backend/scripts/merge_duplicate_finance_clients.py'


session = requests.Session()
session.headers.update({'Content-Type': 'application/json'})


def _login():
    r = session.post(
        f'{BASE_URL}/api/auth/login',
        json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    session.headers.update({'Authorization': f'Bearer {r.json()["token"]}'})


@pytest.fixture(scope='session', autouse=True)
def _auth():
    _login()


async def _db():
    c = AsyncIOMotorClient(MONGO_URL)
    return c[DB_NAME]


# ============ FIXTURE COMUM: master preenchido + dup PROEF-style ============
#
# Cenário canónico PROEF (bug reportado pelo utilizador):
#   MASTER 163: já tem finance_email, saldo_conta, forma_pagamento
#   DUP     120 com account=2111100163: tem carteira, domiciliacoes,
#     saldo_conta diferente, finance_email diferente, finance_open_documents
#     e finance_credit_evolution ligados a genes_code='120'.
# Após merge:
#   - finance_open_documents devem passar para genes_code='163' (com doc_key
#     rebuild).
#   - master preserva finance_email, saldo_conta e forma_pagamento — conflicts
#     ficam registados.
#   - master absorve `carteira`, `domiciliacoes` (estava vazio).
#   - dup fica marcado com `is_merged_duplicate=True`, `merged_conflicts` com
#     entradas estruturadas.


class _Seed:
    """Encapsula seed + teardown de um cenário PROEF completo."""

    def __init__(self, suffix='79163'):
        self.suffix = suffix
        self.dup_code = '9120'  # numérico curto SEM master directo
        self.master_id = str(uuid.uuid4())
        self.dup_id = str(uuid.uuid4())

    async def seed(self):
        db = await _db()
        now = datetime.now(timezone.utc).isoformat()
        base = {
            'name': 'PROEF EURICO FERREIRA (test)',
            'overdue_balance_collectable': 0,
            'oldest_overdue_days': 0,
            'financial_status': 'OK',
            'is_blocked': False,
            'manual_marks': [],
            'created_at': now,
            'updated_at': now,
        }
        # MASTER preenchido em CAMPOS SENSÍVEIS
        await db.finance_clients.insert_one({
            **base,
            'id': self.master_id,
            'genes_code': self.suffix,
            'finance_email': f'master_{self.suffix}@pdpv.pt',
            'saldo_conta': 43615.0,
            'forma_pagamento': 'MASTER-PAG',
            # deixa em vazio: carteira, domiciliacoes, risco_raw
        })
        # DUP com account 21111<suffix> — inferência via account
        await db.finance_clients.insert_one({
            **base,
            'id': self.dup_id,
            'genes_code': self.dup_code,
            'account': f'21111{self.suffix}'.zfill(10),
            'genes_account': f'21111{self.suffix}'.zfill(10),
            # conflitos que devem PRESERVAR master:
            'finance_email': f'dup_{self.suffix}@pdpv.pt',
            'saldo_conta': 99999.0,
            'forma_pagamento': 'DUP-PAG',
            # migráveis (master vazio):
            'carteira': 44109.18,
            'domiciliacoes': 0,
            'risco_raw': 5000,
            'customer_segment': 'EMPRESA',
        })
        # 2 finance_open_documents ligados ao DUP
        for i, val in enumerate([100.0, 250.0], start=1):
            await db.finance_open_documents.insert_one({
                'id': f'FOD-DUP-{self.suffix}-{i}',
                'genes_code': self.dup_code,
                'client_name': 'PROEF (dup)',
                'document_number': f'{self.suffix}/{i}',
                'document_type': 'FT',
                'doc_key': f'{self.dup_code}_{self.suffix}/{i}',
                'amount': val,
                'invoice_date': '2026-01-10',
                'due_date': '2026-02-10',
                'import_id': 'seed',
                'as_of_date': '2026-02-15',
                'updated_at': now,
            })
        # finance_credit_evolution no dup
        await db.finance_credit_evolution.insert_one({
            'genes_code': self.dup_code,
            'client_name': 'PROEF (dup)',
            'periods': {'03-2026': 100, '06-2026': 150},
            'evolution': {'03-2026': 100, '06-2026': 150},
            'updated_at': now,
        })
        return self.master_id, self.dup_id

    async def cleanup(self):
        db = await _db()
        await db.finance_clients.delete_many(
            {'id': {'$in': [self.master_id, self.dup_id]}}
        )
        await db.finance_open_documents.delete_many(
            {'genes_code': {'$in': [self.suffix, self.dup_code]}}
        )
        await db.finance_credit_evolution.delete_many(
            {'genes_code': {'$in': [self.suffix, self.dup_code]}}
        )


def _run_script(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, timeout=60,
    )


# ============ TESTS ============


class TestP0MergeOpenDocsAndMasterPrecedence:

    def test_open_docs_migrate_from_dup_to_master_with_doc_key_rebuild(self):
        seed = _Seed(suffix='79163')
        master_id, dup_id = asyncio.run(seed.seed())
        try:
            r = _run_script('--confirm')
            assert r.returncode == 0, r.stderr

            async def _check():
                db = await _db()
                master_docs = await db.finance_open_documents.find(
                    {'genes_code': seed.suffix}, {'_id': 0}
                ).to_list(10)
                dup_docs = await db.finance_open_documents.find(
                    {'genes_code': seed.dup_code}, {'_id': 0}
                ).to_list(10)
                return master_docs, dup_docs

            master_docs, dup_docs = asyncio.run(_check())
            # A) todos os finance_open_documents passam para o master
            assert len(master_docs) == 2, master_docs
            assert len(dup_docs) == 0, dup_docs
            # doc_key foi reconstruído com genes_code do master
            for d in master_docs:
                assert d['doc_key'].startswith(f'{seed.suffix}_'), d
                assert seed.dup_code not in d['doc_key'], d
        finally:
            asyncio.run(seed.cleanup())

    def test_master_precedence_and_structured_conflicts(self):
        seed = _Seed(suffix='79164')
        master_id, dup_id = asyncio.run(seed.seed())
        try:
            r = _run_script('--confirm')
            assert r.returncode == 0, r.stderr

            async def _check():
                db = await _db()
                master = await db.finance_clients.find_one({'id': master_id})
                dup = await db.finance_clients.find_one({'id': dup_id})
                return master, dup

            master, dup = asyncio.run(_check())

            # B) master preserva TODOS os campos que já tinha preenchidos
            assert master['finance_email'] == f'master_{seed.suffix}@pdpv.pt', master
            assert master['saldo_conta'] == 43615.0, master
            assert master['forma_pagamento'] == 'MASTER-PAG', master

            # B) master absorve campos que estavam vazios
            assert master['carteira'] == 44109.18, master
            assert master.get('risco_raw') == 5000, master
            assert master.get('customer_segment') == 'EMPRESA', master

            # B) merge_conflicts é lista de dicts estruturados
            conflicts = dup.get('merge_conflicts') or []
            assert isinstance(conflicts, list) and conflicts, dup
            conflicted_fields = {c['field'] for c in conflicts if isinstance(c, dict)}
            assert 'finance_email' in conflicted_fields
            assert 'saldo_conta' in conflicted_fields
            assert 'forma_pagamento' in conflicted_fields
            # cada conflict deve ter master_value/duplicate_value/action
            for c in conflicts:
                assert set(c.keys()) >= {
                    'field', 'master_value', 'duplicate_value', 'action', 'reason'
                }, c
                assert c['action'] == 'preserved_master'

            # C) soft mark
            assert dup['is_merged_duplicate'] is True
            assert dup['merged_into'] == master_id
            assert dup['merged_into_genes_code'] == seed.suffix
            assert 'merged_at' in dup and 'merged_reason' in dup
        finally:
            asyncio.run(seed.cleanup())

    def test_credit_evolution_moves_to_master(self):
        seed = _Seed(suffix='79165')
        master_id, dup_id = asyncio.run(seed.seed())
        try:
            r = _run_script('--confirm')
            assert r.returncode == 0, r.stderr

            async def _check():
                db = await _db()
                evo_master = await db.finance_credit_evolution.find_one(
                    {'genes_code': seed.suffix}
                )
                evo_dup = await db.finance_credit_evolution.find_one(
                    {'genes_code': seed.dup_code}
                )
                return evo_master, evo_dup

            evo_master, evo_dup = asyncio.run(_check())
            assert evo_master is not None
            assert evo_dup is None
        finally:
            asyncio.run(seed.cleanup())

    def test_dup_hidden_from_public_clients_list(self):
        seed = _Seed(suffix='79166')
        master_id, dup_id = asyncio.run(seed.seed())
        try:
            r = _run_script('--confirm')
            assert r.returncode == 0, r.stderr

            resp = requests.get(
                f'{BASE_URL}/api/finance/clients',
                params={'search': seed.suffix},
                headers={'Authorization': session.headers['Authorization']},
            )
            assert resp.status_code == 200, resp.text
            ids = {c['id'] for c in resp.json().get('clients', [])}
            assert master_id in ids
            assert dup_id not in ids
        finally:
            asyncio.run(seed.cleanup())

    def test_backup_json_contains_structured_conflicts_and_summary(self):
        seed = _Seed(suffix='79167')
        master_id, dup_id = asyncio.run(seed.seed())
        try:
            # Snapshot timestamp before running
            before = datetime.now(timezone.utc)
            r = _run_script()  # DRY-RUN
            assert r.returncode == 0, r.stderr
            assert 'DRY-RUN' in r.stdout

            # Descobrir o backup mais recente
            candidates = sorted(
                glob.glob('/tmp/finance_merge_backup_*.json'),
                key=os.path.getmtime,
            )
            assert candidates, 'Backup JSON não gerado!'
            latest = candidates[-1]
            assert os.path.getmtime(latest) >= before.timestamp() - 5

            with open(latest, encoding='utf-8') as f:
                payload = json.load(f)

            # Estrutura do backup
            assert payload['mode'] == 'dry-run', payload.get('mode')
            assert 'summary' in payload and 'conflicts' in payload and 'groups' in payload
            # Conflict do nosso seed presente
            found = [
                c for c in payload['conflicts']
                if c.get('duplicate_id') == dup_id and c.get('field') == 'finance_email'
            ]
            assert found, payload['conflicts']
            entry = found[0]
            assert entry['master_value'] == f'master_{seed.suffix}@pdpv.pt'
            assert entry['duplicate_value'] == f'dup_{seed.suffix}@pdpv.pt'
            assert entry['action'] == 'preserved_master'

            # E o stdout também reportou o conflict
            assert 'CONFLICT' in r.stdout
        finally:
            asyncio.run(seed.cleanup())

    def test_master_field_not_touched_when_dup_empty(self):
        """Regra: master preenchido + dup vazio → NADA muda."""
        db_key = '79168'
        master_id = str(uuid.uuid4())
        dup_id = str(uuid.uuid4())

        async def _seed():
            db = await _db()
            now = datetime.now(timezone.utc).isoformat()
            base = {
                'name': 'X', 'overdue_balance_collectable': 0,
                'oldest_overdue_days': 0, 'financial_status': 'OK',
                'is_blocked': False, 'manual_marks': [],
                'created_at': now, 'updated_at': now,
            }
            await db.finance_clients.insert_one({
                **base, 'id': master_id, 'genes_code': db_key,
                'finance_email': 'stays@pdpv.pt',
                'saldo_conta': 100.0,
                'carteira': 50.0,
            })
            await db.finance_clients.insert_one({
                **base, 'id': dup_id, 'genes_code': '99998',
                'account': f'21111{db_key}'.zfill(10),
                # dup vazio nos campos sensíveis:
                'finance_email': None,
                'saldo_conta': None,
                'carteira': '',
            })

        async def _cleanup():
            db = await _db()
            await db.finance_clients.delete_many(
                {'id': {'$in': [master_id, dup_id]}}
            )

        asyncio.run(_seed())
        try:
            r = _run_script('--confirm')
            assert r.returncode == 0, r.stderr

            async def _check():
                db = await _db()
                return await db.finance_clients.find_one({'id': master_id})

            master = asyncio.run(_check())
            # Master intocado
            assert master['finance_email'] == 'stays@pdpv.pt'
            assert master['saldo_conta'] == 100.0
            assert master['carteira'] == 50.0
            # E nenhum conflict foi levantado (dup era vazio)
        finally:
            asyncio.run(_cleanup())
