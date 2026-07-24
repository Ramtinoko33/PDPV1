"""
Iteration 46b — File type auto-detection endpoint.

POST /api/finance/imports/detect-type recebe um xlsx e devolve:
  - detected: overdue_balances | open_documents | client_info |
              credit_evolution | null
  - confidence: high | medium | low | unknown
  - scores: breakdown por tipo

Usado pelo frontend para avisar quando o utilizador seleccionou o
tipo errado no dropdown antes de subir o ficheiro.
"""
import io
import os

import pytest
import requests
from openpyxl import Workbook

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')

ADMIN_EMAIL = 'admin@pdpv.pt'
ADMIN_PASSWORD = os.environ.get('TEST_ADMIN_PASSWORD', 'HCNMEnKMLq')

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


def _post_detect(content, filename='test.xlsx'):
    headers = {'Authorization': session.headers['Authorization']}
    files = {'file': (filename, content,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    return requests.post(f'{BASE_URL}/api/finance/imports/detect-type',
                         files=files, headers=headers)


def _build(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


class TestDetectOverdue:
    def test_overdue_high_confidence(self):
        c = _build([
            ['Cliente', 'Cód. Cliente', 'Localidade', 'Região', 'Email',
             'Telefone1', 'Telefone2', 'Importe Total Vencido', 'Saldo Cliente'],
            ['ACME', 'C001', 'Lx', 'Sul', 'x@x.pt', None, None, 100, 100],
            ['', 'Documento', 'Data da fatura', 'Data Vencimento', 'CódSede',
             'Sede', 'Dias Vencidos', 'Importe Vencimiento', 'Vencido Factura'],
        ])
        r = _post_detect(c, 'overdue.xlsx')
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['detected'] == 'overdue_balances', d
        assert d['confidence'] == 'high', d


class TestDetectOpenDocs:
    def test_open_docs_high_confidence(self):
        c = _build([
            ['CodPersona', 'Conta', 'Tipo D. Pagamento', 'Forma Pagamento',
             'Data Fat.', 'Data Venc.', 'Cliente', 'Descritivo', 'Saldo',
             'Registo B.', 'Registo C.', 'Registo D.', 'Quantia', 'Vencido',
             'Cobrado', 'Estado', 'Eventos'],
            ['C001', '21100001', 'TR', '30D', '2025-11-01', '2025-12-01',
             'ACME', 'VTO. FAT./FT 1', 100, '', '', '', 100, 100, 0, 'Aberto', ''],
        ])
        r = _post_detect(c, 'opendocs.xlsx')
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['detected'] == 'open_documents', d
        assert d['confidence'] == 'high', d


class TestDetectMismatch:
    def test_open_docs_file_not_confused_with_overdue(self):
        """O bug reportado: user selecciona 'Saldos Vencidos' mas o
        ficheiro é 'Documentos Aberto'. O detector distingue-os."""
        c = _build([
            ['CodPersona', 'Conta', 'Tipo D. Pagamento', 'Forma Pagamento',
             'Data Fat.', 'Data Venc.', 'Cliente', 'Descritivo', 'Saldo',
             'Registo B.', 'Registo C.', 'Registo D.', 'Quantia', 'Vencido',
             'Cobrado', 'Estado', 'Eventos'],
        ])
        r = _post_detect(c, 'mismatched.xlsx')
        assert r.status_code == 200, r.text
        d = r.json()
        # Detector deve preferir open_documents sobre overdue_balances
        assert d['detected'] == 'open_documents', d
        assert d['scores']['open_documents']['score'] > d['scores']['overdue_balances']['score']


class TestDetectUnknown:
    def test_random_file_unknown(self):
        c = _build([
            ['foo', 'bar', 'baz'],
            [1, 2, 3],
        ])
        r = _post_detect(c, 'random.xlsx')
        assert r.status_code == 200, r.text
        d = r.json()
        # Todas as required = 0 → detected None, confidence unknown
        assert d['confidence'] == 'unknown', d
        assert d['detected'] is None, d


class TestDetectEmptyFile:
    def test_empty_body_400(self):
        r = _post_detect(b'', 'empty.xlsx')
        assert r.status_code == 400


class TestDetectInvalidExtension:
    def test_pdf_rejected(self):
        r = _post_detect(b'%PDF-1.4 ...', 'nope.pdf')
        assert r.status_code == 400
