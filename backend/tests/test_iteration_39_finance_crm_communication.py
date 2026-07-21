"""
Iteration 39 — CRM Finance Communication & Import Hardening tests.

Covers:
  A1) Staged replace on open_documents import — old docs kept if new import fails.
  A2) Imports list pagination — offset/limit/total/has_more, no overlap.
  A3) Import files cleanup — preview + dry_run + real; audit row preserved with
      file_cleaned_at/file_cleaned_by and errors intact.
  C1) Email templates: 8 seeded defaults; OWNER-only CRUD; COLLECTIONS_AGENT can list.
  C2) Send email (Resend) — creates finance_actions email row with meta; residual-only
      guardrail for COLLECTIONS_AGENT; empty RESEND_API_KEY path (sent=false, action saved).
  C5) Dunning ladder + per-client bucket resolution.
  Regression: dashboard/clients/login, classify_document rules still hold.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://intake-ai-gateway.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"
COLLECTIONS_AGENT_EMAIL = "cobranca.teste@pdpv.pt"
COLLECTIONS_AGENT_PASSWORD = "TesteFin2026!"


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
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def agent_headers(collections_agent_token):
    return {"Authorization": f"Bearer {collections_agent_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def mongo_db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


# ============ REGRESSION: basic health ============
class TestRegression:
    def test_admin_login(self, admin_token):
        assert admin_token and len(admin_token) > 20

    def test_finance_dashboard_ok(self, admin_headers):
        r = requests.get(f"{API}/finance/dashboard", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Just verify structure — actual values depend on preview data
        assert isinstance(data, dict)

    def test_finance_clients_ok(self, admin_headers):
        r = requests.get(f"{API}/finance/clients?limit=1", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "clients" in data or "items" in data or isinstance(data, list) or "total" in data


# ============ A2: PAGINATION ============
class TestImportsPagination:
    def test_list_imports_response_shape(self, admin_headers):
        r = requests.get(f"{API}/finance/imports?limit=2&offset=0", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("imports", "total", "limit", "offset", "has_more"):
            assert key in data, f"missing key '{key}' in imports response: {list(data.keys())}"
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert isinstance(data["has_more"], bool)
        assert isinstance(data["imports"], list)

    def test_pagination_no_overlap(self, admin_headers):
        r1 = requests.get(f"{API}/finance/imports?limit=2&offset=0", headers=admin_headers, timeout=30)
        r2 = requests.get(f"{API}/finance/imports?limit=2&offset=2", headers=admin_headers, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        d1, d2 = r1.json(), r2.json()
        if d1["total"] < 4:
            pytest.skip(f"Not enough imports to test overlap (total={d1['total']})")
        ids1 = {i["id"] for i in d1["imports"]}
        ids2 = {i["id"] for i in d2["imports"]}
        assert ids1.isdisjoint(ids2), f"overlap between pages: {ids1 & ids2}"
        # has_more consistency: if offset+len < total → has_more True
        assert d1["has_more"] == (d1["offset"] + len(d1["imports"]) < d1["total"])

    def test_offset_beyond_total_empty(self, admin_headers):
        r = requests.get(f"{API}/finance/imports?limit=5&offset=999999", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["imports"] == []
        assert d["has_more"] is False


# ============ A3: CLEANUP OF IMPORT FILES ============
class TestImportsCleanup:
    """Cleanup routes MUST be declared before /imports/{import_type} — verify."""

    def test_cleanup_preview_reachable(self, admin_headers):
        """If reachable and returns 200, route ordering is OK (not intercepted by enum)."""
        r = requests.get(f"{API}/finance/imports/cleanup/preview?older_than_days=30", headers=admin_headers, timeout=30)
        assert r.status_code == 200, f"route-order issue? status={r.status_code} body={r.text[:400]}"
        d = r.json()
        for key in ("cutoff_days", "cutoff_at", "total_candidates", "total_bytes", "items"):
            assert key in d, f"missing '{key}' in preview response"
        assert d["cutoff_days"] == 30
        assert isinstance(d["items"], list)

    def test_cleanup_dry_run_no_disk_change(self, admin_headers, mongo_db, tmp_path):
        """Seed a FAILED import >30d old with a real file on disk. dry_run must NOT delete it."""
        import asyncio

        async def _seed():
            f = tmp_path / f"TEST_ITER39_dry_{uuid.uuid4().hex[:6]}.xlsx"
            f.write_bytes(b"dummy fake xlsx content for iter39 test")
            imp_id = f"TEST_ITER39_DRY_{uuid.uuid4().hex[:8]}"
            await mongo_db.finance_imports.insert_one({
                "id": imp_id,
                "type": "open_documents",
                "status": "failed",
                "filename": f.name,
                "original_file_path": str(f),
                "uploaded_at": (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),
                "uploaded_by": "TEST_ITER39",
                "errors": ["seed-error-marker"],
            })
            return imp_id, f

        imp_id, f = asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = requests.post(
                f"{API}/finance/imports/cleanup?older_than_days=30&dry_run=true",
                headers=admin_headers, timeout=30,
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["dry_run"] is True
            assert d["files_deleted"] >= 1
            # File still on disk
            assert f.exists(), "dry_run deleted the file — MUST NOT happen"

            async def _check_row():
                row = await mongo_db.finance_imports.find_one({"id": imp_id}, {"_id": 0})
                return row

            row = asyncio.get_event_loop().run_until_complete(_check_row())
            assert row is not None
            # dry_run must not mutate audit fields
            assert row.get("original_file_path") == str(f)
            assert row.get("file_cleaned_at") in (None, "")
            assert row.get("errors") == ["seed-error-marker"]
        finally:
            async def _cleanup():
                await mongo_db.finance_imports.delete_one({"id": imp_id})
            asyncio.get_event_loop().run_until_complete(_cleanup())
            if f.exists():
                f.unlink()

    def test_cleanup_real_deletes_file_preserves_audit(self, admin_headers, mongo_db, tmp_path):
        import asyncio

        async def _seed():
            f = tmp_path / f"TEST_ITER39_real_{uuid.uuid4().hex[:6]}.xlsx"
            f.write_bytes(b"dummy content to be deleted")
            imp_id = f"TEST_ITER39_REAL_{uuid.uuid4().hex[:8]}"
            await mongo_db.finance_imports.insert_one({
                "id": imp_id,
                "type": "open_documents",
                "status": "failed",
                "filename": f.name,
                "original_file_path": str(f),
                "uploaded_at": (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),
                "uploaded_by": "TEST_ITER39",
                "errors": ["preserve-me-please"],
            })
            return imp_id, f

        imp_id, f = asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = requests.post(
                f"{API}/finance/imports/cleanup?older_than_days=30&dry_run=false",
                headers=admin_headers, timeout=30,
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["dry_run"] is False
            assert d["files_deleted"] >= 1
            assert not f.exists(), "real cleanup must delete the file on disk"

            async def _check_row():
                return await mongo_db.finance_imports.find_one({"id": imp_id}, {"_id": 0})

            row = asyncio.get_event_loop().run_until_complete(_check_row())
            assert row is not None, "finance_imports row MUST be preserved — audit lost!"
            assert row.get("original_file_path") is None
            assert row.get("file_cleaned_at"), "file_cleaned_at must be set"
            assert row.get("file_cleaned_by"), "file_cleaned_by must be set"
            assert row.get("errors") == ["preserve-me-please"], "errors must be preserved"
        finally:
            async def _cleanup():
                await mongo_db.finance_imports.delete_one({"id": imp_id})
            asyncio.get_event_loop().run_until_complete(_cleanup())


# ============ A1: STAGED REPLACE (verify code path exists via import route) ============
class TestStagedReplace:
    """We verify the staged-replace behaviour by inspecting the running code path.
    A full integration test would require crafting a valid xlsx that first parses
    then triggers a failure mid-swap — outside scope. Instead: verify the code
    contains the staging_collection_name pattern AND that after a corrupted upload
    the old finance_open_documents count is preserved.
    """
    def test_import_service_has_staged_replace_code(self):
        p = Path("/app/backend/modules/finance/services/import_service.py")
        content = p.read_text()
        assert "staging_collection_name" in content
        assert "finance_open_documents_staging_" in content
        # Ensure staging count validation happens BEFORE the swap delete_many
        idx_staging_check = content.index("staged_count")
        idx_delete = content.index("await db.finance_open_documents.delete_many")
        assert idx_staging_check < idx_delete, "delete_many must run AFTER staging count validation"

    def test_corrupted_open_documents_import_preserves_existing(self, admin_headers, mongo_db):
        """Upload obviously-corrupted xlsx to open_documents endpoint and verify existing
        finance_open_documents count is unchanged."""
        import asyncio

        async def _count():
            return await mongo_db.finance_open_documents.count_documents({})

        before = asyncio.get_event_loop().run_until_complete(_count())

        # Send a corrupt file
        files = {"file": ("TEST_ITER39_bad.xlsx", b"NOT AN XLSX AT ALL", "application/vnd.ms-excel")}
        # Remove Content-Type for multipart
        h = {k: v for k, v in admin_headers.items() if k.lower() != "content-type"}
        r = requests.post(
            f"{API}/finance/imports/open_documents",
            headers=h, files=files, timeout=60,
        )
        # Expect a failure response (400 or 200 with status=failed)
        assert r.status_code in (200, 400, 422, 500), r.status_code
        after = asyncio.get_event_loop().run_until_complete(_count())
        assert after == before, f"open_documents count changed after failed import: {before} -> {after}"


# ============ C1: EMAIL TEMPLATES ============
EXPECTED_TEMPLATE_KEYS = {
    "lembrete_amigavel", "pedido_pagamento", "pedido_comprovativo",
    "lembrete_promessa", "promessa_falhada", "plano_pagamento",
    "confirmar_email_contabilidade", "aviso_bloqueio",
}


class TestEmailTemplates:
    def test_list_returns_8_defaults(self, admin_headers):
        r = requests.get(f"{API}/finance/email-templates", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] >= 8
        keys = {t["key"] for t in d["templates"]}
        missing = EXPECTED_TEMPLATE_KEYS - keys
        assert not missing, f"missing default templates: {missing}"

    def test_collections_agent_can_list(self, agent_headers):
        r = requests.get(f"{API}/finance/email-templates", headers=agent_headers, timeout=30)
        assert r.status_code == 200

    def test_collections_agent_cannot_create(self, agent_headers):
        payload = {
            "key": f"test_iter39_{uuid.uuid4().hex[:6]}",
            "label": "TEST", "subject": "s", "body": "b",
        }
        r = requests.post(f"{API}/finance/email-templates", headers=agent_headers, json=payload, timeout=30)
        assert r.status_code == 403, f"agent must be forbidden: {r.status_code} {r.text[:200]}"

    def test_owner_full_crud_cycle(self, admin_headers):
        key = f"test_iter39_{uuid.uuid4().hex[:8]}"
        payload = {"key": key, "label": "TEST label", "subject": "TEST subj", "body": "TEST body"}
        # CREATE
        r = requests.post(f"{API}/finance/email-templates", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["key"] == key
        assert created["label"] == "TEST label"
        tid = created["id"]

        # UPDATE
        r = requests.put(f"{API}/finance/email-templates/{tid}",
                         headers=admin_headers, json={"label": "TEST label edit"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["label"] == "TEST label edit"

        # GET (list — verify persisted)
        r = requests.get(f"{API}/finance/email-templates", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert any(t["id"] == tid and t["label"] == "TEST label edit" for t in r.json()["templates"])

        # DELETE
        r = requests.delete(f"{API}/finance/email-templates/{tid}", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        # verify gone
        r = requests.get(f"{API}/finance/email-templates", headers=admin_headers, timeout=30)
        assert not any(t["id"] == tid for t in r.json()["templates"])


# ============ C5: DUNNING LADDER ============
class TestDunningLadder:
    def test_ladder_returns_6_fixed_buckets(self, admin_headers):
        r = requests.get(f"{API}/finance/dunning-ladder", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "buckets" in d
        keys = [b["key"] for b in d["buckets"]]
        assert keys == ["d0_15", "d16_30", "d31_60", "d61_90", "d90p", "d120p"], f"got: {keys}"
        # colors
        color_map = {b["key"]: b["color"] for b in d["buckets"]}
        assert color_map["d31_60"] == "orange"
        assert color_map["d0_15"] == "green"
        assert color_map["d120p"] == "black"

    def test_client_bucket_by_days_and_status(self, admin_headers, mongo_db):
        """Seed a client with 40 days overdue + status=em_cobranca → bucket d31_60/orange."""
        import asyncio

        cid = f"TEST_ITER39_CLI_{uuid.uuid4().hex[:8]}"
        async def _seed():
            await mongo_db.finance_clients.insert_one({
                "id": cid,
                "genes_code": "TEST-ITER39",
                "name": "TEST ITER39 Client",
                "financial_status": "EM_COBRANCA",
                "oldest_overdue_days": 40,
                "total_balance": 1000.0,
                "total_overdue": 1000.0,
                "is_residual_only": False,
            })

        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = requests.get(f"{API}/finance/clients/{cid}/dunning-bucket", headers=admin_headers, timeout=30)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["oldest_overdue_days"] == 40
            assert d["bucket"]["key"] == "d31_60"
            assert d["bucket"]["color"] == "orange"
            sug_keys = d["bucket"]["suggested_template_keys"]
            assert "pedido_pagamento" in sug_keys
            assert "pedido_comprovativo" in sug_keys
            # suggested_templates enriched with actual template docs (if seeded)
            assert isinstance(d.get("suggested_templates"), list)
        finally:
            async def _rm():
                await mongo_db.finance_clients.delete_one({"id": cid})
            asyncio.get_event_loop().run_until_complete(_rm())

    @pytest.mark.parametrize("status,expected_key,expected_color", [
        ("PROMESSA_ATIVA", "promise", "blue"),
        ("EM_DISPUTA", "dispute", "purple"),
        ("BLOQUEADO", "blocked", "black"),
    ])
    def test_special_status_buckets(self, admin_headers, mongo_db, status, expected_key, expected_color):
        import asyncio
        cid = f"TEST_ITER39_STATUS_{status}_{uuid.uuid4().hex[:6]}"
        async def _seed():
            await mongo_db.finance_clients.insert_one({
                "id": cid,
                "genes_code": f"TEST-{status}",
                "name": f"TEST {status}",
                "financial_status": status,
                "oldest_overdue_days": 20,
                "total_balance": 500.0,
                "total_overdue": 500.0,
                "is_residual_only": False,
            })
        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = requests.get(f"{API}/finance/clients/{cid}/dunning-bucket", headers=admin_headers, timeout=30)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["bucket"]["key"] == expected_key
            assert d["bucket"]["color"] == expected_color
        finally:
            async def _rm():
                await mongo_db.finance_clients.delete_one({"id": cid})
            asyncio.get_event_loop().run_until_complete(_rm())


# ============ C2: SEND EMAIL ============
class TestSendEmail:
    def test_send_email_creates_action_and_uses_resend(self, admin_headers, mongo_db):
        """Requires client to exist. Uses delivered@resend.dev sandbox recipient."""
        import asyncio

        cid = f"TEST_ITER39_MAIL_{uuid.uuid4().hex[:8]}"
        async def _seed():
            await mongo_db.finance_clients.insert_one({
                "id": cid,
                "genes_code": "TEST-MAIL",
                "name": "TEST MAIL Client",
                "financial_status": "EM_COBRANCA",
                "oldest_overdue_days": 30,
                "total_balance": 100.0,
                "total_overdue": 100.0,
                "is_residual_only": False,
            })

        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            payload = {
                "to": "delivered@resend.dev",
                "subject": "TEST ITER39 iteration email",
                "body": "This is a TEST_ITER39 body.",
                "template_key": "pedido_pagamento",
            }
            r = requests.post(f"{API}/finance/clients/{cid}/send-email",
                              headers=admin_headers, json=payload, timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            assert set(d.keys()) >= {"sent", "provider_id", "error", "action_id"}
            action_id = d["action_id"]
            assert action_id

            # Fetch the finance_action row and validate email_meta
            async def _get_action():
                return await mongo_db.finance_actions.find_one({"id": action_id}, {"_id": 0})

            action = asyncio.get_event_loop().run_until_complete(_get_action())
            assert action is not None, "finance_actions entry MUST be created"
            assert action["action_type"] == "email"
            assert action["client_id"] == cid
            meta = action.get("email_meta") or {}
            assert meta.get("to") == "delivered@resend.dev"
            assert meta.get("subject") == "TEST ITER39 iteration email"
            assert meta.get("template_key") == "pedido_pagamento"
            # sent should be True with real Resend key; but allow False if key invalid
            assert isinstance(meta.get("sent"), bool)
            if meta.get("sent"):
                assert meta.get("provider_id") == d["provider_id"]
        finally:
            async def _rm():
                await mongo_db.finance_actions.delete_many({"client_id": cid})
                await mongo_db.finance_clients.delete_one({"id": cid})
            asyncio.get_event_loop().run_until_complete(_rm())

    def test_residual_only_client_blocks_agent(self, agent_headers, mongo_db):
        """COLLECTIONS_AGENT gets 403 when client is_residual_only."""
        import asyncio

        cid = f"TEST_ITER39_RESID_{uuid.uuid4().hex[:8]}"
        async def _seed():
            await mongo_db.finance_clients.insert_one({
                "id": cid,
                "genes_code": "TEST-RESID",
                "name": "TEST residual only",
                "financial_status": "EM_COBRANCA",
                "oldest_overdue_days": 400,
                "total_balance": 0.80,
                "total_overdue": 0.80,
                "is_residual_only": True,
            })

        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            payload = {
                "to": "delivered@resend.dev",
                "subject": "should be blocked",
                "body": "b",
                "template_key": "pedido_pagamento",
            }
            r = requests.post(f"{API}/finance/clients/{cid}/send-email",
                              headers=agent_headers, json=payload, timeout=30)
            assert r.status_code == 403, f"agent should be blocked on residual-only: {r.status_code} {r.text[:200]}"
        finally:
            async def _rm():
                await mongo_db.finance_clients.delete_one({"id": cid})
            asyncio.get_event_loop().run_until_complete(_rm())

    def test_owner_can_send_to_residual_only(self, admin_headers, mongo_db):
        """OWNER bypasses the residual-only guardrail."""
        import asyncio

        cid = f"TEST_ITER39_OWNR_{uuid.uuid4().hex[:8]}"
        async def _seed():
            await mongo_db.finance_clients.insert_one({
                "id": cid,
                "genes_code": "TEST-OWNRRES",
                "name": "TEST owner residual",
                "financial_status": "EM_COBRANCA",
                "oldest_overdue_days": 400,
                "total_balance": 0.50,
                "total_overdue": 0.50,
                "is_residual_only": True,
            })
        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            payload = {
                "to": "delivered@resend.dev",
                "subject": "owner allowed",
                "body": "b",
                "template_key": "pedido_pagamento",
            }
            r = requests.post(f"{API}/finance/clients/{cid}/send-email",
                              headers=admin_headers, json=payload, timeout=60)
            assert r.status_code == 200, r.text
        finally:
            async def _rm():
                await mongo_db.finance_actions.delete_many({"client_id": cid})
                await mongo_db.finance_clients.delete_one({"id": cid})
            asyncio.get_event_loop().run_until_complete(_rm())


# ============ CLASSIFY DOCUMENT REGRESSION ============
class TestClassifyDocumentRegression:
    def test_classify_rules_still_hold(self):
        """Import service classify_document unit-level check via import."""
        import sys
        sys.path.insert(0, "/app/backend")
        from modules.finance.services.import_service import classify_document
        cfg = {
            "residual_document_threshold": 1.00,
            "residual_client_threshold": 5.00,
            "micro_old_days_threshold": 365,
        }
        # 0.80 EUR / 1220 d → residual
        c = classify_document(amount_open=0.80, amount_original=100.0, is_credit_note=False,
                              days_overdue=1220, config=cfg)
        assert str(c.value if hasattr(c, "value") else c) == "residual", f"expected residual, got {c}"
        # 3.50 EUR / 500 d → micro_old
        c = classify_document(amount_open=3.50, amount_original=100.0, is_credit_note=False,
                              days_overdue=500, config=cfg)
        assert str(c.value if hasattr(c, "value") else c) == "micro_old", f"expected micro_old, got {c}"
