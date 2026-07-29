"""
Iteration 51 — CodPersona/Conta bug + merge duplicados Finance.

Bug reportado pelo utilizador: cliente PROEF Eurico Ferreira aparece
duplicado em Finance:
  - genes_code=163  (correcto, veio de Saldos Vencidos)
  - genes_code=2111100163 (errado, veio de InfoClientes/Evolução da iter 48)
  - genes_code=120 (errado, veio de CodPersona no Docs Aberto)

Fix (iter 51):
  1. Novo normalizador extrai o sufixo da Conta contabilística
     (`21111NNN` → `NNN`, sem zeros à esquerda).
  2. Parsers `client_info`, `evolution`, `documents` deixam de usar
     CodPersona e usam o normalizador da Conta.
  3. Script `merge_duplicate_finance_clients.py` consolida duplicados
     existentes no master, migra colecções relacionadas e marca duplicados
     como `is_merged_duplicate=True` (não apaga).
  4. GET /finance/clients exclui automaticamente `is_merged_duplicate`.
"""
import io
import os
import sys
import uuid
import asyncio
import subprocess
from datetime import datetime, timezone

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

TP = 'TSTMRG51'

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


# ============ NORMALIZER ============

class TestNormalizer:
    def test_extracts_suffix_and_strips_zeros(self):
        from modules.finance.parsers.account_normalizer import normalize_account_to_client_code
        assert normalize_account_to_client_code('2111100163') == '163'
        assert normalize_account_to_client_code('2111103092') == '3092'
        assert normalize_account_to_client_code('2111122485') == '22485'
        assert normalize_account_to_client_code('2111100001') == '1'
        # Padrão inválido → None
        assert normalize_account_to_client_code('120') is None
        assert normalize_account_to_client_code('') is None
        assert normalize_account_to_client_code(None) is None
        assert normalize_account_to_client_code('9999999999') is None


# ============ PARSERS (não usar CodPersona) ============

class TestOpenDocsParserUsesConta:
    def test_open_docs_uses_conta_not_codpersona(self):
        from modules.finance.parsers import parse_open_documents
        wb = Workbook()
        ws = wb.active
        ws.append(['CodPersona', 'Conta', 'Tipo D. Pagamento', 'Forma Pagamento',
                   'Data Fat.', 'Data Venc.', 'Cliente', 'Descritivo', 'Saldo',
                   'Registo B.', 'Registo C.', 'Registo D.', 'Quantia', 'Vencido',
                   'Cobrado', 'Estado', 'Eventos'])
        ws.append([120, '2111100163', 'TB', '30D', datetime(2026,6,15), datetime(2026,7,15),
                   'PROEF EURICO', 'VTO. FAT./FT 026/4645', 44109.18, 0, 0, 0, 274, 274, 0, 'PP', ''])
        ws.append([2343, '2111103092', 'TB', '30D', datetime(2026,4,21), datetime(2026,5,21),
                   '3LD COMERCIO', 'VTO. FAT./FT 026/3119', 327.94, 0, 0, 0, 125.41, 125.41, 0, 'PP', ''])
        buf = io.BytesIO(); wb.save(buf)
        result = parse_open_documents(buf.getvalue())
        assert result['errors'] == []
        codes = {c['genes_code'] for c in result['clients'].values()}
        assert codes == {'163', '3092'}, codes
        # CodPersona não aparece
        assert '120' not in codes and '2343' not in codes
        assert '2111100163' not in codes and '2111103092' not in codes


class TestClientInfoParserUsesNormalizer:
    def test_client_info_uses_normalized_suffix(self):
        from modules.finance.parsers import parse_client_info
        wb = Workbook()
        ws = wb.active
        ws.append(['Alm.', 'Conta', 'Cliente', 'Saldo Conta', 'Saldo Efec.',
                   'Saldo Desc.', 'Saldo Dev.', 'Carteira', 'Domiciliações',
                   'Risco', 'Albaranado', 'Forma Pagamento', 'Eventos'])
        ws.append([1, '2111100163', 'PROEF EURICO', 43615, 0, 0, 0, 44109, 0, 5000, 20866, 'PP', ''])
        buf = io.BytesIO(); wb.save(buf)
        result = parse_client_info(buf.getvalue())
        assert result['errors'] == []
        assert len(result['clients']) == 1
        assert result['clients'][0]['genes_code'] == '163'


# ============ MERGE SCRIPT ============

class TestMergeScript:
    SCRIPT = '/app/backend/scripts/merge_duplicate_finance_clients.py'

    def _seed_pair(self, suffix, dup_code, name):
        """Cria master (com docs) + duplicado (com carteira/evolution)."""
        async def _go():
            db = await _db()
            master_id = str(uuid.uuid4())
            dup_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            base_client = {
                'name': name,
                'overdue_balance_collectable': 0,
                'oldest_overdue_days': 0,
                'financial_status': 'OK',
                'is_blocked': False,
                'manual_marks': [],
                'created_at': now,
                'updated_at': now,
            }
            # MASTER (correcto)
            await db.finance_clients.insert_one({
                **base_client, 'id': master_id, 'genes_code': suffix,
                'finance_email': f'master{suffix}@x.pt',
                # sem carteira
            })
            # DUP (errado — tem enrichment)
            await db.finance_clients.insert_one({
                **base_client, 'id': dup_id, 'genes_code': dup_code,
                'carteira': 44109.18, 'domiciliacoes': 0,
                'forma_pagamento': 'Pagamento a 30 dias',
                'finance_email': f'dup{suffix}@x.pt',  # conflict
            })
            # 1 doc no master, 1 evolution no dup
            await db.finance_documents.insert_one({
                'id': f'DOC-{suffix}', 'client_id': master_id, 'genes_code': suffix,
                'document_type': 'FT', 'document_number': f'{suffix}/1',
                'invoice_date': '2025-11-01', 'due_date': '2025-12-01',
                'amount_original': 100, 'amount_open': 100, 'amount_overdue': 100,
                'days_overdue': 30, 'classification': 'collectable',
                'effective_classification': 'collectable',
                'manually_marked_collectable': False, 'manual_action': None,
                'last_import_id': 'seed', 'created_at': now, 'updated_at': now,
            })
            await db.finance_credit_evolution.insert_one({
                'genes_code': dup_code, 'client_name': name,
                'periods': {'03-2025': 100, '06-2026': 150},
                'evolution': {'03-2025': 100, '06-2026': 150},
                'updated_at': now,
            })
            return master_id, dup_id
        return asyncio.run(_go())

    def _cleanup(self, master_id, dup_id, suffix, dup_code):
        async def _go():
            db = await _db()
            await db.finance_clients.delete_many({'id': {'$in': [master_id, dup_id]}})
            await db.finance_documents.delete_many({'client_id': {'$in': [master_id, dup_id]}})
            await db.finance_credit_evolution.delete_many(
                {'genes_code': {'$in': [suffix, dup_code]}}
            )
        asyncio.run(_go())

    def test_dry_run_leaves_db_intact(self):
        master_id, dup_id = self._seed_pair('89163', '2111189163', 'PROEF TEST')
        try:
            r = subprocess.run(
                [sys.executable, self.SCRIPT], capture_output=True, text=True, timeout=45
            )
            assert r.returncode == 0, r.stderr
            assert 'DRY-RUN' in r.stdout

            async def _check():
                db = await _db()
                dup = await db.finance_clients.find_one({'id': dup_id})
                return dup
            dup = asyncio.run(_check())
            assert not dup.get('is_merged_duplicate'), 'dry-run alterou a BD!'
        finally:
            self._cleanup(master_id, dup_id, '89163', '2111189163')


    def test_proef_scenario_codpersona_dup_merged_by_account_field(self):
        """Cenário EXACTO do bug: duplicado com genes_code='120' mas
        account='2111105163' deve ser fundido no master '5163' via
        inferência do sufixo da Conta contabilística."""
        async def _seed():
            db = await _db()
            master_id = str(uuid.uuid4())
            dup_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            base = {
                'name': 'PROEF EURICO FERREIRA',
                'overdue_balance_collectable': 0,
                'oldest_overdue_days': 0,
                'financial_status': 'OK',
                'is_blocked': False,
                'manual_marks': [],
                'created_at': now,
                'updated_at': now,
            }
            await db.finance_clients.insert_one({
                **base, 'id': master_id, 'genes_code': '5163',
            })
            await db.finance_clients.insert_one({
                **base, 'id': dup_id, 'genes_code': '120',
                'account': '2111105163',
                'genes_account': '2111105163',
                'carteira': 44109.18,
            })
            await db.finance_credit_evolution.insert_one({
                'genes_code': '120', 'client_name': 'PROEF',
                'periods': {'03-2026': 100},
                'updated_at': now,
            })
            return master_id, dup_id
        master_id, dup_id = asyncio.run(_seed())
        try:
            r = subprocess.run(
                [sys.executable, self.SCRIPT, '--confirm'],
                capture_output=True, text=True, timeout=45,
            )
            assert r.returncode == 0, r.stderr

            async def _check():
                db = await _db()
                master = await db.finance_clients.find_one({'id': master_id})
                dup = await db.finance_clients.find_one({'id': dup_id})
                evo_master = await db.finance_credit_evolution.find_one({'genes_code': '5163'})
                evo_dup = await db.finance_credit_evolution.find_one({'genes_code': '120'})
                return master, dup, evo_master, evo_dup
            master, dup, evo_master, evo_dup = asyncio.run(_check())

            assert master['carteira'] == 44109.18, master
            assert dup['is_merged_duplicate'] is True, dup
            assert dup['merged_into'] == master_id, dup
            assert dup['merged_into_genes_code'] == '5163', dup
            assert evo_master is not None, 'Evolution não migrou para o master'
            assert evo_dup is None, 'Evolution original ainda existe no genes_code errado'
        finally:
            async def _cleanup():
                db = await _db()
                await db.finance_clients.delete_many({'id': {'$in': [master_id, dup_id]}})
                await db.finance_credit_evolution.delete_many(
                    {'genes_code': {'$in': ['120', '5163']}}
                )
            asyncio.run(_cleanup())

    def test_confirm_merges_and_marks_duplicate(self):
        # Usa formato numérico real (só dígitos após 21111)
        master_id, dup_id = self._seed_pair('9163', '21111009163', 'PROEF MERGE')
        try:
            r = subprocess.run(
                [sys.executable, self.SCRIPT, '--confirm'],
                capture_output=True, text=True, timeout=45
            )
            assert r.returncode == 0, r.stderr

            async def _check():
                db = await _db()
                master = await db.finance_clients.find_one({'id': master_id})
                dup = await db.finance_clients.find_one({'id': dup_id})
                # docs sob master
                doc = await db.finance_documents.find_one({'genes_code': '9163'})
                # evolution remapeada para master genes_code
                evo = await db.finance_credit_evolution.find_one({'genes_code': '9163'})
                orphan_evo = await db.finance_credit_evolution.find_one({'genes_code': '21111009163'})
                return master, dup, doc, evo, orphan_evo
            master, dup, doc, evo, orphan_evo = asyncio.run(_check())

            # MASTER absorveu enrichment
            assert master['carteira'] == 44109.18, master
            assert master['forma_pagamento'] == 'Pagamento a 30 dias'
            # Conflicts: master mantém o SEU finance_email, guarda conflict
            assert master['finance_email'] == 'master9163@x.pt'

            # DUP marcado
            assert dup['is_merged_duplicate'] is True
            assert dup['merged_into'] == master_id
            assert dup['merged_into_genes_code'] == '9163'
            assert 'merged_at' in dup and dup['merged_by'] == 'merge_script_iter51'
            assert any('finance_email' in c for c in dup.get('merge_conflicts', []))

            # Evolution migrada
            assert evo is not None
            assert orphan_evo is None
        finally:
            self._cleanup(master_id, dup_id, '9163', '21111009163')

    def test_list_clients_excludes_merged_duplicates(self):
        master_id, dup_id = self._seed_pair('88551', '2111188551', 'PROEF EXCL')
        try:
            # Marca manualmente o duplicado
            async def _mark():
                db = await _db()
                await db.finance_clients.update_one(
                    {'id': dup_id},
                    {'$set': {'is_merged_duplicate': True, 'merged_into': master_id}}
                )
            asyncio.run(_mark())

            # GET /clients busca por search='88551' → só devolve master
            r = requests.get(
                f'{BASE_URL}/api/finance/clients',
                params={'search': '88551'},
                headers={'Authorization': session.headers['Authorization']},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            ids = {c['id'] for c in data.get('clients', [])}
            assert master_id in ids
            assert dup_id not in ids
        finally:
            self._cleanup(master_id, dup_id, '88551', '2111188551')
