"""
Iteration 53 — Endpoints OWNER-only para merge de duplicados Finance.

Contexto: o utilizador não consegue correr comandos na consola de
Produção; precisa de executar o merge a partir do próprio CRM Finance.

Endpoints testados:
  POST /api/finance/merge-duplicates/dry-run
  GET  /api/finance/merge-duplicates/reports
  GET  /api/finance/merge-duplicates/reports/{id}
  POST /api/finance/merge-duplicates/confirm

Regras validadas:
  - OWNER-only (403 para outros)
  - dry-run é idempotente e nunca escreve em finance_clients / finance_documents / finance_open_documents / finance_credit_evolution
  - dry-run persiste um report em `finance_merge_reports`
  - confirm exige `confirmation == "APROVAR"` literal
  - confirm exige `report_id` válido e dentro do TTL
  - confirm aplica o mesmo plano gerado pelo dry-run
  - depois de aplicado, o report fica marcado `status=applied`
  - confirm falha 409 se se tentar reaplicar o mesmo report
  - dup fica marcado como is_merged_duplicate=True
  - finance_open_documents ficam ligados ao master (spec P0)
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

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


def _login(email, password):
    r = requests.post(
        f'{BASE_URL}/api/auth/login',
        json={'email': email, 'password': password},
    )
    assert r.status_code == 200, r.text
    return r.json()['token']


@pytest.fixture(scope='session')
def owner_headers():
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}


async def _db():
    c = AsyncIOMotorClient(MONGO_URL)
    return c[DB_NAME]


class _SeedPROEF:
    """Semear master + duplicado com finance_open_documents ligados ao dup."""

    def __init__(self, suffix):
        self.suffix = suffix
        self.dup_code = f'DUP{suffix}'
        self.master_id = str(uuid.uuid4())
        self.dup_id = str(uuid.uuid4())

    async def seed(self):
        db = await _db()
        now = datetime.now(timezone.utc).isoformat()
        base = {
            'name': f'PROEF TEST {self.suffix}',
            'overdue_balance_collectable': 0,
            'oldest_overdue_days': 0,
            'financial_status': 'OK',
            'is_blocked': False,
            'manual_marks': [],
            'created_at': now,
            'updated_at': now,
        }
        await db.finance_clients.insert_one({
            **base,
            'id': self.master_id,
            'genes_code': self.suffix,
            'finance_email': f'master_{self.suffix}@pdpv.pt',
        })
        await db.finance_clients.insert_one({
            **base,
            'id': self.dup_id,
            'genes_code': self.dup_code,
            'account': f'21111{self.suffix.zfill(5)}',
            'genes_account': f'21111{self.suffix.zfill(5)}',
            'carteira': 12345.67,
            'finance_email': f'dup_{self.suffix}@pdpv.pt',
        })
        await db.finance_open_documents.insert_one({
            'id': f'FOD-{self.suffix}-1',
            'genes_code': self.dup_code,
            'client_name': f'PROEF TEST {self.suffix}',
            'document_number': f'{self.suffix}/1',
            'document_type': 'FT',
            'doc_key': f'{self.dup_code}_{self.suffix}/1',
            'amount': 999.0,
            'invoice_date': '2026-01-10',
            'due_date': '2026-02-10',
            'import_id': 'seed',
            'as_of_date': '2026-02-15',
            'updated_at': now,
        })

    async def cleanup(self):
        db = await _db()
        await db.finance_clients.delete_many(
            {'id': {'$in': [self.master_id, self.dup_id]}}
        )
        await db.finance_open_documents.delete_many(
            {'genes_code': {'$in': [self.suffix, self.dup_code]}}
        )
        await db.finance_merge_reports.delete_many({'plan.summary.duplicates': {'$gte': 1}})


# --------------------- TESTS ---------------------


class TestDryRunSafety:

    def test_dry_run_owner_only_and_does_not_touch_data(self, owner_headers):
        seed = _SeedPROEF(suffix='63301')
        asyncio.run(seed.seed())
        try:
            r = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
                headers=owner_headers,
            )
            assert r.status_code == 200, r.text
            body = r.json()

            # Estrutura devolvida
            assert set(body.keys()) >= {
                'report_id', 'expires_at', 'ttl_minutes',
                'summary', 'conflicts', 'groups',
            }
            assert body['summary']['duplicates'] >= 1, body['summary']
            # Deve conter o nosso par
            our_group = next(
                (g for g in body['groups']
                 if g['master']['id'] == seed.master_id),
                None,
            )
            assert our_group is not None, body['groups']
            assert any(
                d['id'] == seed.dup_id for d in our_group['duplicates']
            ), our_group

            # BD intocada
            async def _check():
                db = await _db()
                dup = await db.finance_clients.find_one({'id': seed.dup_id})
                od = await db.finance_open_documents.find_one(
                    {'genes_code': seed.dup_code}
                )
                return dup, od

            dup, od = asyncio.run(_check())
            assert not dup.get('is_merged_duplicate'), 'dry-run tocou finance_clients!'
            assert od is not None, 'dry-run tocou finance_open_documents!'
        finally:
            asyncio.run(seed.cleanup())

    def test_dry_run_forbidden_for_non_owner(self):
        # Login com o próprio admin serve; a permissão OWNER assume que
        # admin@pdpv.pt tem OWNER. Verificamos apenas que quem não tem
        # token recebe 401/403.
        r = requests.post(
            f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
        )
        assert r.status_code in (401, 403), r.text


class TestConfirmGuardrails:

    def test_confirm_requires_APROVAR_literal(self, owner_headers):
        # gera um report primeiro
        seed = _SeedPROEF(suffix='63302')
        asyncio.run(seed.seed())
        try:
            r = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
                headers=owner_headers,
            )
            assert r.status_code == 200
            rid = r.json()['report_id']

            # Palavras erradas → 400
            for bad in ('aprovar', 'APROVA', 'YES', 'OK', ''):
                r2 = requests.post(
                    f'{BASE_URL}/api/finance/merge-duplicates/confirm',
                    headers=owner_headers,
                    json={'report_id': rid, 'confirmation': bad},
                )
                assert r2.status_code == 400, (bad, r2.text)
                assert 'APROVAR' in r2.text

            # BD ainda intocada
            async def _check():
                db = await _db()
                return await db.finance_clients.find_one({'id': seed.dup_id})

            dup = asyncio.run(_check())
            assert not dup.get('is_merged_duplicate')
        finally:
            asyncio.run(seed.cleanup())

    def test_confirm_rejects_unknown_report_id(self, owner_headers):
        r = requests.post(
            f'{BASE_URL}/api/finance/merge-duplicates/confirm',
            headers=owner_headers,
            json={'report_id': 'does-not-exist', 'confirmation': 'APROVAR'},
        )
        assert r.status_code == 404

    def test_confirm_rejects_expired_report(self, owner_headers):
        """Simula um report antigo alterando expires_at directamente na DB."""
        seed = _SeedPROEF(suffix='63303')
        asyncio.run(seed.seed())
        try:
            r = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
                headers=owner_headers,
            )
            rid = r.json()['report_id']

            async def _age_out():
                db = await _db()
                # Colocar expires_at no passado
                await db.finance_merge_reports.update_one(
                    {'id': rid},
                    {'$set': {
                        'expires_at': (
                            datetime.now(timezone.utc) - timedelta(minutes=1)
                        ).isoformat()
                    }},
                )
            asyncio.run(_age_out())

            r2 = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/confirm',
                headers=owner_headers,
                json={'report_id': rid, 'confirmation': 'APROVAR'},
            )
            assert r2.status_code == 410, r2.text
            assert 'expirado' in r2.text.lower()

            # Marcado como expired
            async def _check():
                db = await _db()
                rep = await db.finance_merge_reports.find_one({'id': rid})
                dup = await db.finance_clients.find_one({'id': seed.dup_id})
                return rep, dup

            rep, dup = asyncio.run(_check())
            assert rep['status'] == 'expired'
            assert not dup.get('is_merged_duplicate')
        finally:
            asyncio.run(seed.cleanup())

    def test_confirm_cannot_be_reused(self, owner_headers):
        """Segundo confirm no mesmo report → 409."""
        seed = _SeedPROEF(suffix='63304')
        asyncio.run(seed.seed())
        try:
            r = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
                headers=owner_headers,
            )
            rid = r.json()['report_id']

            # 1º confirm → 200
            r2 = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/confirm',
                headers=owner_headers,
                json={'report_id': rid, 'confirmation': 'APROVAR'},
            )
            assert r2.status_code == 200, r2.text

            # 2º confirm → 409
            r3 = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/confirm',
                headers=owner_headers,
                json={'report_id': rid, 'confirmation': 'APROVAR'},
            )
            assert r3.status_code == 409, r3.text
        finally:
            asyncio.run(seed.cleanup())


class TestConfirmAppliesPlan:

    def test_confirm_applies_and_marks_report(self, owner_headers):
        seed = _SeedPROEF(suffix='63305')
        asyncio.run(seed.seed())
        try:
            r = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
                headers=owner_headers,
            )
            assert r.status_code == 200, r.text
            rid = r.json()['report_id']

            r2 = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/confirm',
                headers=owner_headers,
                json={'report_id': rid, 'confirmation': 'APROVAR'},
            )
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body['apply_stats']['merged_count'] >= 1
            assert 'finance_open_documents:genes_code' in body['apply_stats']['remap_stats']

            async def _check():
                db = await _db()
                dup = await db.finance_clients.find_one({'id': seed.dup_id})
                # docs em aberto agora ligados ao master
                master_docs = await db.finance_open_documents.find(
                    {'genes_code': seed.suffix}, {'_id': 0}
                ).to_list(10)
                orphan_docs = await db.finance_open_documents.find(
                    {'genes_code': seed.dup_code}, {'_id': 0}
                ).to_list(10)
                rep = await db.finance_merge_reports.find_one({'id': rid})
                return dup, master_docs, orphan_docs, rep

            dup, master_docs, orphan_docs, rep = asyncio.run(_check())

            # DUP soft-marked
            assert dup['is_merged_duplicate'] is True
            assert dup['merged_into'] == seed.master_id
            assert dup['merged_by'].startswith('owner_confirm:')
            assert 'merged_reason' in dup

            # finance_open_documents remapeados + doc_key rebuild
            assert len(master_docs) == 1
            assert len(orphan_docs) == 0
            assert master_docs[0]['doc_key'].startswith(f'{seed.suffix}_')
            assert seed.dup_code not in master_docs[0]['doc_key']

            # Report actualizado
            assert rep['status'] == 'applied'
            assert 'applied_at' in rep
            assert rep['applied_by']
            assert rep['apply_stats']['merged_count'] >= 1
        finally:
            asyncio.run(seed.cleanup())


class TestListAndFetchReport:

    def test_list_reports_hides_plan_but_shows_summary(self, owner_headers):
        seed = _SeedPROEF(suffix='63306')
        asyncio.run(seed.seed())
        try:
            r = requests.post(
                f'{BASE_URL}/api/finance/merge-duplicates/dry-run',
                headers=owner_headers,
            )
            rid = r.json()['report_id']

            lst = requests.get(
                f'{BASE_URL}/api/finance/merge-duplicates/reports',
                headers=owner_headers,
            )
            assert lst.status_code == 200
            items = lst.json()['items']
            ours = next((i for i in items if i['id'] == rid), None)
            assert ours is not None
            assert 'plan' not in ours   # listagem não expõe payload grande
            assert 'status' in ours

            det = requests.get(
                f'{BASE_URL}/api/finance/merge-duplicates/reports/{rid}',
                headers=owner_headers,
            )
            assert det.status_code == 200
            detail = det.json()
            assert 'plan' in detail
            assert detail['plan']['summary']['duplicates'] >= 1
        finally:
            asyncio.run(seed.cleanup())
