"""
Iteration 40 — CRM Finance Bloco B: customer_segment, finance contactos, backfill,
filtros avançados e ordenações em GET /finance/clients.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"
COLLECTIONS_AGENT_EMAIL = "cobranca.teste@pdpv.pt"
COLLECTIONS_AGENT_PASSWORD = "TesteFin2026!"
RECEPCAO_EMAIL = "rececao.teste@pdpv.pt"
RECEPCAO_PASSWORD = "TesteFin2026!"


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# --------- Shared fixtures ---------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def collections_agent_token():
    r = requests.post(f"{API}/auth/login", json={"email": COLLECTIONS_AGENT_EMAIL, "password": COLLECTIONS_AGENT_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"COLLECTIONS_AGENT login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def rececao_token():
    r = requests.post(f"{API}/auth/login", json={"email": RECEPCAO_EMAIL, "password": RECEPCAO_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"RECECAO login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def agent_headers(collections_agent_token):
    return {"Authorization": f"Bearer {collections_agent_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def rececao_headers(rececao_token):
    return {"Authorization": f"Bearer {rececao_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def db():
    client = AsyncIOMotorClient(MONGO_URL)
    d = client[DB_NAME]
    yield d
    client.close()


# ============================================================
# 1) MODEL fields present
# ============================================================
def test_get_client_returns_new_fields(admin_headers):
    r = requests.get(f"{API}/finance/clients?page_size=5", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    clients = r.json().get("clients", [])
    if not clients:
        pytest.skip("Sem finance_clients")
    cid = clients[0]["id"]
    r2 = requests.get(f"{API}/finance/clients/{cid}", headers=admin_headers, timeout=30)
    assert r2.status_code == 200
    body = r2.json()
    for f in ("customer_segment", "finance_email", "finance_phone", "finance_mobile",
              "finance_contact_name", "finance_contacts_updated_at", "finance_contacts_updated_by"):
        assert f in body, f"Missing field '{f}'"
    from modules.finance.models import CustomerSegment
    assert body["customer_segment"] in [s.value for s in CustomerSegment]


# ============================================================
# 2) resolve_segment mapping unit
# ============================================================
def test_resolve_segment_mapping():
    from modules.finance.services.customer_link import resolve_segment
    from modules.finance.models import CustomerSegment
    cases = {
        "PARTICULAR": CustomerSegment.PARTICULAR,
        "particular": CustomerSegment.PARTICULAR,
        "EMPRESA": CustomerSegment.EMPRESA,
        "FROTISTA LIGEIRO": CustomerSegment.FROTA,
        "FROTISTA PESADOS": CustomerSegment.FROTA,
        "AGRICULTOR": CustomerSegment.EMPRESA,
        "VINICULTOR": CustomerSegment.EMPRESA,
        "COOPERATIVA AGRICOLA": CustomerSegment.EMPRESA,
        "INDUSTRIA": CustomerSegment.EMPRESA,
        "OFICINA REPARADORA AUTO": CustomerSegment.EMPRESA,
        "CONCESS. AUTOMOVEIS": CustomerSegment.EMPRESA,
        "FUNCIONARIOS": CustomerSegment.PARTICULAR,
        "SEGURADORA": CustomerSegment.SEGURADORA,
        "ENTIDADE DO ESTADO": CustomerSegment.OUTRO,
        "": CustomerSegment.UNKNOWN,
        None: CustomerSegment.UNKNOWN,
        "TIPO INEXISTENTE": CustomerSegment.UNKNOWN,
    }
    for src, expected in cases.items():
        got = resolve_segment(src)
        assert got == expected, f"resolve_segment({src!r}) → {got}, esperado {expected}"


# ============================================================
# 3) backfill via nome — idempotente + não sobrescreve manual
# ============================================================
def test_backfill_via_name_match_and_idempotent(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    cust_name = f"TEST BACKFILL EMPRESA {unique}"
    cust_id = f"TEST_ITER40_CUST_{unique}"
    fc_id = f"TEST_ITER40_FC_{unique}"

    _run(db.customers.delete_many({"id": cust_id}))
    _run(db.finance_clients.delete_many({"id": fc_id}))

    _run(db.customers.insert_one({
        "id": cust_id,
        "name": cust_name,
        "customer_type": "EMPRESA",
        "emails": ["test-empresa@example.com"],
        "phones": ["351911111111"],
        "mobile": "351922222222",
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40{unique}",
        "name": cust_name,
        "customer_segment": "UNKNOWN",
        "total_balance": 0.0,
        "overdue_balance_accounting": 0.0,
        "overdue_balance_collectable": 0.0,
        "residual_balance": 0.0,
        "oldest_overdue_days": 0,
        "collection_index": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))

    try:
        r = requests.post(f"{API}/finance/clients/{fc_id}/backfill-contacts", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("linked") is True
        fu = body.get("fields_updated", [])
        for expected in ("linked_customer_id", "customer_segment", "finance_email", "finance_phone"):
            assert expected in fu, f"Backfill não preencheu {expected}: {fu}"

        fc = _run(db.finance_clients.find_one({"id": fc_id}, {"_id": 0}))
        assert fc["linked_customer_id"] == cust_id
        assert fc["customer_segment"] == "EMPRESA"
        assert fc["finance_email"] == "test-empresa@example.com"
        assert fc["finance_phone"] == "351911111111"
        assert fc["finance_mobile"] == "351922222222"

        # segundo run — idempotente
        r2 = requests.post(f"{API}/finance/clients/{fc_id}/backfill-contacts", headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        fu2 = r2.json().get("fields_updated", [])
        assert fu2 == [] or fu2 == ["updated_at"], f"Segundo run: {fu2}"

        # override manual — não sobrescreve
        _run(db.finance_clients.update_one({"id": fc_id}, {"$set": {"finance_email": "manual-override@example.com"}}))
        r3 = requests.post(f"{API}/finance/clients/{fc_id}/backfill-contacts", headers=admin_headers, timeout=30)
        assert r3.status_code == 200
        fc_after = _run(db.finance_clients.find_one({"id": fc_id}, {"_id": 0}))
        assert fc_after["finance_email"] == "manual-override@example.com", "Backfill sobrescreveu manual!"
    finally:
        _run(db.customers.delete_many({"id": cust_id}))
        _run(db.finance_clients.delete_many({"id": fc_id}))


# ============================================================
# 4) Startup migration recorded
# ============================================================
def test_startup_backfill_migration_recorded(db):
    entry = _run(db.finance_recompute_log.find_one(
        {"migration_key": "finance_backfill_customer_link_v1_2026_02"}, {"_id": 0}
    ))
    assert entry is not None, "Startup migration key não gravada"
    assert "summary" in entry


# ============================================================
# 5) PATCH /clients/{id}/contacts — auditoria, empty→None, no-op
# ============================================================
def test_patch_contacts_full_flow(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_FC_PATCH_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40P{unique}",
        "name": f"TEST PATCH {unique}",
        "customer_segment": "UNKNOWN",
        "total_balance": 0.0,
        "overdue_balance_collectable": 0.0,
        "oldest_overdue_days": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.patch(f"{API}/finance/clients/{fc_id}/contacts", json={
            "customer_segment": "EMPRESA",
            "finance_email": "patched@example.com",
            "finance_phone": "351933333333",
            "reason": "teste iteration_40",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["customer_segment"] == "EMPRESA"
        assert body["finance_email"] == "patched@example.com"
        assert body["finance_contacts_updated_at"] is not None
        assert body["finance_contacts_updated_by"] is not None

        hist = _run(db.finance_client_contact_history.find_one({"client_id": fc_id}, {"_id": 0}))
        assert hist is not None
        assert hist["reason"] == "teste iteration_40"
        change_fields = [c["field"] for c in hist["changes"]]
        assert "customer_segment" in change_fields
        assert "finance_email" in change_fields
        assert "finance_phone" in change_fields

        act = _run(db.finance_actions.find_one({"client_id": fc_id, "action_type": "note"}, {"_id": 0}))
        assert act is not None
        assert "Contactos/Segmento atualizados" in act["notes"]

        # empty string → None
        r2 = requests.patch(f"{API}/finance/clients/{fc_id}/contacts", json={
            "finance_phone": "", "reason": "clear phone"
        }, headers=admin_headers, timeout=30)
        assert r2.status_code == 200, r2.text
        assert r2.json()["finance_phone"] is None

        # no-op: mesmo valor não escreve nova auditoria
        before = _run(db.finance_client_contact_history.count_documents({"client_id": fc_id}))
        r3 = requests.patch(f"{API}/finance/clients/{fc_id}/contacts", json={
            "finance_email": "patched@example.com",
        }, headers=admin_headers, timeout=30)
        assert r3.status_code == 200
        after = _run(db.finance_client_contact_history.count_documents({"client_id": fc_id}))
        assert after == before, "No-op não devia criar entrada de auditoria"
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))
        _run(db.finance_client_contact_history.delete_many({"client_id": fc_id}))
        _run(db.finance_actions.delete_many({"client_id": fc_id}))


# ============================================================
# 6) Permissões
# ============================================================
def test_collections_agent_can_patch_contacts(agent_headers, admin_headers):
    r = requests.get(f"{API}/finance/clients?page_size=1", headers=admin_headers, timeout=30)
    clients = r.json().get("clients", [])
    if not clients:
        pytest.skip("Sem clients")
    cid = clients[0]["id"]
    r2 = requests.patch(f"{API}/finance/clients/{cid}/contacts", json={"reason": "teste perms"},
                        headers=agent_headers, timeout=30)
    assert r2.status_code == 200, f"COLLECTIONS_AGENT deveria conseguir; got {r2.status_code} {r2.text[:200]}"


def test_collections_agent_forbidden_backfill_all(agent_headers):
    r = requests.post(f"{API}/finance/clients/backfill-all", headers=agent_headers, timeout=30)
    assert r.status_code == 403, f"backfill-all deveria exigir OWNER; got {r.status_code}"


def test_rececao_forbidden_on_clients_list(rececao_headers):
    r = requests.get(f"{API}/finance/clients", headers=rececao_headers, timeout=30)
    assert r.status_code == 403, f"rececao deveria receber 403; got {r.status_code}"


# ============================================================
# 7) Filtros avançados
# ============================================================
def test_filter_by_customer_segment(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_SEG_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40S{unique}",
        "name": f"TEST SEG {unique}",
        "customer_segment": "EMPRESA",
        "total_balance": 0.0,
        "overdue_balance_collectable": 0.0,
        "oldest_overdue_days": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.get(f"{API}/finance/clients?customer_segment=EMPRESA&page_size=200",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json().get("clients", [])]
        assert fc_id in ids

        r2 = requests.get(f"{API}/finance/clients?customer_segment=PARTICULAR&page_size=200",
                          headers=admin_headers, timeout=30)
        assert fc_id not in [c["id"] for c in r2.json().get("clients", [])]
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))


def test_filter_ate_10_euros(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_TEN_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40T{unique}",
        "name": f"TEST TEN {unique}",
        "customer_segment": "UNKNOWN",
        "total_balance": 5.0,
        "overdue_balance_collectable": 5.0,
        "oldest_overdue_days": 15,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.get(f"{API}/finance/clients?min_overdue=0&max_overdue=10&page_size=200",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert fc_id in [c["id"] for c in r.json().get("clients", [])]

        r2 = requests.get(f"{API}/finance/clients?min_overdue=50&max_overdue=200&page_size=200",
                          headers=admin_headers, timeout=30)
        assert fc_id not in [c["id"] for c in r2.json().get("clients", [])]
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))


def test_filter_aging_bucket_365p(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_AGE_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40A{unique}",
        "name": f"TEST AGE {unique}",
        "customer_segment": "UNKNOWN",
        "total_balance": 100.0,
        "overdue_balance_collectable": 100.0,
        "oldest_overdue_days": 400,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.get(f"{API}/finance/clients?aging_bucket=365p&page_size=200",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert fc_id in [c["id"] for c in r.json().get("clients", [])]

        r2 = requests.get(f"{API}/finance/clients?aging_bucket=0_30&page_size=200",
                          headers=admin_headers, timeout=30)
        assert fc_id not in [c["id"] for c in r2.json().get("clients", [])]
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))


def test_filter_has_residual(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_RES_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40R{unique}",
        "name": f"TEST RES {unique}",
        "customer_segment": "UNKNOWN",
        "total_balance": -3.50,
        "overdue_balance_collectable": 0.0,
        "residual_balance": 2.0,
        "oldest_overdue_days": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.get(f"{API}/finance/clients?has_residual=true&page_size=200",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert fc_id in [c["id"] for c in r.json().get("clients", [])]
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))


def test_filter_missing_finance_email_before_after_patch(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_MEM_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40M{unique}",
        "name": f"TEST MISS EMAIL {unique}",
        "customer_segment": "UNKNOWN",
        "total_balance": 0.0,
        "overdue_balance_collectable": 0.0,
        "oldest_overdue_days": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.get(f"{API}/finance/clients?missing_finance_email=true&page_size=200",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert fc_id in [c["id"] for c in r.json().get("clients", [])]

        r2 = requests.patch(f"{API}/finance/clients/{fc_id}/contacts",
                            json={"finance_email": "now-set@example.com"},
                            headers=admin_headers, timeout=30)
        assert r2.status_code == 200

        r3 = requests.get(f"{API}/finance/clients?missing_finance_email=true&page_size=200",
                          headers=admin_headers, timeout=30)
        assert fc_id not in [c["id"] for c in r3.json().get("clients", [])]
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))
        _run(db.finance_client_contact_history.delete_many({"client_id": fc_id}))
        _run(db.finance_actions.delete_many({"client_id": fc_id}))


def test_filter_never_contacted(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    fc_id = f"TEST_ITER40_NEV_{unique}"
    _run(db.finance_clients.insert_one({
        "id": fc_id,
        "genes_code": f"TESTITER40N{unique}",
        "name": f"TEST NEVER {unique}",
        "customer_segment": "UNKNOWN",
        "total_balance": 100.0,
        "overdue_balance_collectable": 100.0,
        "oldest_overdue_days": 50,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        r = requests.get(f"{API}/finance/clients?never_contacted=true&page_size=200",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert fc_id in [c["id"] for c in r.json().get("clients", [])]
    finally:
        _run(db.finance_clients.delete_many({"id": fc_id}))


# ============================================================
# 8) Ordenação
# ============================================================
def test_sort_by_overdue_asc_desc(db, admin_headers):
    unique = uuid.uuid4().hex[:8]
    ids = {}
    values = [10.0, 100.0, 50.0]
    for v in values:
        fid = f"TEST_ITER40_SORT_{unique}_{int(v)}"
        ids[v] = fid
        _run(db.finance_clients.insert_one({
            "id": fid,
            "genes_code": f"TESTITER40SO{unique}{int(v)}",
            "name": f"ZZZZ SORT {unique} {int(v):03d}",
            "customer_segment": "UNKNOWN",
            "total_balance": v,
            "overdue_balance_collectable": v,
            "oldest_overdue_days": 30,
            "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
        }))
    try:
        r = requests.get(
            f"{API}/finance/clients?min_overdue=10&max_overdue=100&sort_by=overdue_desc&page_size=200",
            headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        ours = [c for c in r.json().get("clients", []) if c["id"].startswith(f"TEST_ITER40_SORT_{unique}")]
        assert len(ours) == 3
        assert [c["overdue_balance_collectable"] for c in ours] == [100.0, 50.0, 10.0]

        r2 = requests.get(
            f"{API}/finance/clients?min_overdue=10&max_overdue=100&sort_by=overdue_asc&page_size=200",
            headers=admin_headers, timeout=30)
        ours2 = [c for c in r2.json().get("clients", []) if c["id"].startswith(f"TEST_ITER40_SORT_{unique}")]
        assert [c["overdue_balance_collectable"] for c in ours2] == [10.0, 50.0, 100.0]
    finally:
        for fid in ids.values():
            _run(db.finance_clients.delete_many({"id": fid}))


# ============================================================
# 9) Regressão iteration_39
# ============================================================
def test_regression_email_templates_seed(admin_headers):
    r = requests.get(f"{API}/finance/email-templates", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    templates = body.get("templates") if isinstance(body, dict) else body
    if templates is None:
        templates = body
    assert isinstance(templates, list) and len(templates) >= 8, f"Esperado >=8 templates: got {len(templates) if hasattr(templates,'__len__') else '?'}"


def test_regression_dunning_ladder(admin_headers):
    r = requests.get(f"{API}/finance/dunning-ladder", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    ladder = body.get("buckets") if isinstance(body, dict) else body
    if ladder is None:
        ladder = body.get("ladder") if isinstance(body, dict) else body
    assert isinstance(ladder, list) and len(ladder) >= 6, f"Dunning ladder deveria ter 6 buckets"


def test_regression_imports_pagination(admin_headers):
    r = requests.get(f"{API}/finance/imports?limit=5&offset=0", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("imports", "total", "limit", "offset", "has_more"):
        assert k in body, f"Missing '{k}'"
