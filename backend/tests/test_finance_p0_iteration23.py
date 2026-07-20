"""
Finance P0 iteration 23 tests

Covers:
- Overdue balances import >30% diff → status=pending_approval and NO clients applied
- POST /api/finance/imports/{id}/approve → reprocess and apply clients (TST01/TST02 created)
- GET /api/finance/imports enriches uploaded_by_name
- GET /api/finance/promises enriches client_name + genes_code
- User finance_role selector persists via PATCH /api/users/{id}

Cleanup: removes all TST* clients and the test import (file + doc + promise/actions).
"""
import os
import io
import uuid
import time
import requests
from typing import Optional
from openpyxl import Workbook

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "HCNMEnKMLq")
COLLECTIONS_EMAIL = "cobranca.teste@pdpv.pt"
COLLECTIONS_PASSWORD = os.environ.get("TEST_COLLECTIONS_PASSWORD", "TesteFin2026!")
NOFIN_EMAIL = "rececao.teste@pdpv.pt"
NOFIN_PASSWORD = os.environ.get("TEST_NOFIN_PASSWORD", "TesteFin2026!")

# --- helpers ---

def login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("token") or body["access_token"]


def h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def build_overdue_xlsx(clients, marker: str) -> bytes:
    """clients = [(name, genes_code, total_overdue, total_balance, [(doc_num, days_overdue, amount_due, amount_overdue), ...]), ...]"""
    wb = Workbook()
    ws = wb.active
    # Non-header marker row for uniqueness (parser ignores it because not client/doc header/data)
    ws.append([f"MARKER-{marker}"])
    for (name, code, tot_over, tot_bal, docs) in clients:
        ws.append(["Cliente", "Cód. Cliente", "Localidade", "Região", "Email",
                   "Telefone1", "Telefone2", "Importe Total Vencido", "Saldo Cliente"])
        ws.append([name, code, "Lisboa", "Sul", f"{code.lower()}@test.pt",
                   "", "", tot_over, tot_bal])
        ws.append(["", "Documento", "Data da fatura", "Data Vencimento",
                   "CódSede", "Sede", "Dias Vencidos", "Importe Vencimiento", "Vencido Factura"])
        for (doc_num, days, amt_due, amt_over) in docs:
            ws.append(["", doc_num, "2025-01-01", "2025-02-01", "01", "Sede",
                       days, amt_due, amt_over])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- fixtures via module-level state ---
_state = {}


def setup_module(module):
    _state["admin"] = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    _state["collections"] = login(COLLECTIONS_EMAIL, COLLECTIONS_PASSWORD)
    _state["nofin"] = login(NOFIN_EMAIL, NOFIN_PASSWORD)


def teardown_module(module):
    """Cleanup test data via admin token."""
    tok = _state.get("admin")
    if not tok:
        return
    # We don't have direct DB access from HTTP; use dedicated cleanup endpoint if available,
    # otherwise rely on a Mongo call via a maintenance script. Here we call the DB via python.
    try:
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]

        async def _cleanup():
            # Delete TST* clients and related data
            tst_clients = await db.finance_clients.find({"genes_code": {"$regex": "^TST"}}, {"id": 1}).to_list(100)
            client_ids = [c["id"] for c in tst_clients]
            if client_ids:
                await db.finance_promises.delete_many({"client_id": {"$in": client_ids}})
                await db.finance_actions.delete_many({"client_id": {"$in": client_ids}})
                await db.finance_documents.delete_many({"client_id": {"$in": client_ids}})
                await db.block_requests.delete_many({"client_id": {"$in": client_ids}})
            await db.finance_clients.delete_many({"genes_code": {"$regex": "^TST"}})
            # Delete test imports (by filename prefix TESTP0-)
            imports = await db.finance_imports.find({"filename": {"$regex": "^TESTP0-"}}).to_list(100)
            for imp in imports:
                fp = imp.get("original_file_path")
                if fp and os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            await db.finance_imports.delete_many({"filename": {"$regex": "^TESTP0-"}})
            client.close()
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_cleanup())
            loop.close()
        except Exception as e:
            print(f"[teardown] loop error: {e}")
    except Exception as e:
        print(f"[teardown] cleanup error (non-fatal): {e}")


# --- tests ---

def test_01_pending_approval_does_not_apply_clients():
    tok = _state["admin"]
    # Build xlsx with total_overdue ~50€ (very different from baseline 23136€ => >30% diff)
    marker = uuid.uuid4().hex[:8]
    content = build_overdue_xlsx(
        clients=[
            ("Cliente Teste 01", "TST01", 30.0, 30.0, [("FT-TST-01", 10, 30.0, 30.0)]),
            ("Cliente Teste 02", "TST02", 20.0, 20.0, [("FT-TST-02", 5, 20.0, 20.0)]),
        ],
        marker=marker,
    )
    filename = f"TESTP0-{marker}.xlsx"
    files = {"file": (filename, content,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{API}/finance/imports/overdue_balances",
                      headers=h(tok), files=files, timeout=30)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    body = r.json()
    import_id = body.get("import_id")
    assert import_id, f"no import_id in response: {body}"
    _state["import_id"] = import_id
    # Expect pending_approval status
    assert body.get("status") == "pending_approval", f"expected pending_approval, got {body.get('status')} — full: {body}"

    # Confirm no TST clients yet
    r2 = requests.get(f"{API}/finance/clients", headers=h(tok),
                      params={"search": "TST01", "limit": 20}, timeout=15)
    assert r2.status_code == 200
    clients = r2.json().get("clients", [])
    tst_codes = [c["genes_code"] for c in clients if c["genes_code"].startswith("TST")]
    assert not tst_codes, f"TST clients should NOT exist before approval: {tst_codes}"


def test_02_approve_reprocesses_and_applies_clients():
    tok = _state["admin"]
    import_id = _state["import_id"]
    r = requests.post(f"{API}/finance/imports/{import_id}/approve", headers=h(tok), timeout=30)
    assert r.status_code == 200, f"approve failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("success") is True, f"approve did not succeed: {body}"

    # Now TST clients must exist
    time.sleep(0.5)
    r2 = requests.get(f"{API}/finance/clients", headers=h(tok),
                      params={"search": "TST", "limit": 20}, timeout=15)
    assert r2.status_code == 200
    clients = r2.json().get("clients", [])
    codes = sorted([c["genes_code"] for c in clients if c["genes_code"].startswith("TST")])
    assert codes == ["TST01", "TST02"], f"expected TST01/TST02 after approve, got {codes}"


def test_03_imports_list_enriches_uploaded_by_name():
    tok = _state["admin"]
    r = requests.get(f"{API}/finance/imports", headers=h(tok), params={"limit": 20}, timeout=15)
    assert r.status_code == 200, r.text
    imports = r.json().get("imports", [])
    assert imports, "no imports returned"
    # At least one import must have uploaded_by_name (Administrador expected for admin uploads)
    named = [i for i in imports if i.get("uploaded_by_name")]
    assert named, f"no import has uploaded_by_name: {[i.get('filename') for i in imports]}"
    # our test import should have uploaded_by_name set
    ours = next((i for i in imports if i["id"] == _state["import_id"]), None)
    assert ours is not None
    assert ours.get("uploaded_by_name"), f"our import lacks uploaded_by_name: {ours}"


def test_04_promises_list_enriches_client_name_and_genes_code():
    tok = _state["admin"]
    r = requests.get(f"{API}/finance/promises", headers=h(tok), timeout=15)
    assert r.status_code == 200, r.text
    promises = r.json().get("promises", [])
    if not promises:
        import pytest
        pytest.skip("no promises in DB to enrich — skipping enrichment check")
    p = promises[0]
    assert "client_name" in p, f"missing client_name field: {p}"
    assert "genes_code" in p, f"missing genes_code field: {p}"
    # client_name should not be None if client exists
    assert p.get("client_name"), f"client_name empty: {p}"


def test_05_user_finance_role_persists():
    tok = _state["admin"]
    # Fetch collections agent user id
    r = requests.get(f"{API}/users", headers=h(tok), timeout=15)
    assert r.status_code == 200, r.text
    users = r.json()
    if isinstance(users, dict):
        users = users.get("users", [])
    target = next((u for u in users if u.get("email") == COLLECTIONS_EMAIL), None)
    assert target, f"user {COLLECTIONS_EMAIL} not found"
    original_role = target.get("finance_role")

    # Toggle: set to FINANCE_REVIEWER
    new_role = "FINANCE_REVIEWER" if original_role != "FINANCE_REVIEWER" else "COLLECTIONS_AGENT"
    r2 = requests.put(f"{API}/users/{target['id']}",
                        headers=h(tok), json={"finance_role": new_role}, timeout=15)
    assert r2.status_code == 200, f"PATCH failed: {r2.status_code} {r2.text}"

    # Verify via GET
    r3 = requests.get(f"{API}/users", headers=h(tok), timeout=15)
    users3 = r3.json()
    if isinstance(users3, dict):
        users3 = users3.get("users", [])
    updated = next(u for u in users3 if u["id"] == target["id"])
    assert updated.get("finance_role") == new_role, f"finance_role did not persist: {updated}"

    # Restore original
    requests.put(f"{API}/users/{target['id']}",
                   headers=h(tok), json={"finance_role": original_role}, timeout=15)


def test_06_permissions_collections_agent_no_block_requests():
    tok = _state["collections"]
    r = requests.get(f"{API}/finance/block-requests", headers=h(tok), timeout=15)
    # COLLECTIONS_AGENT must be denied on block-requests review flows
    assert r.status_code == 403, f"expected 403 for collections agent on block-requests, got {r.status_code}: {r.text}"


def test_07_permissions_nofinance_no_finance_access():
    tok = _state["nofin"]
    r = requests.get(f"{API}/finance/dashboard", headers=h(tok), timeout=15)
    assert r.status_code == 403, f"expected 403 for no-finance user, got {r.status_code}: {r.text}"
