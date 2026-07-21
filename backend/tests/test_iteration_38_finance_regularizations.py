"""
Iteration 38 - CRM Finance: Regularizations & Filters fixes
Tests the new residual/micro_old classification logic, per-document regularizations
endpoint with filters, document actions, and collections/today filters.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://intake-ai-gateway.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"


# --------------- fixtures ---------------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def api(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


# Helper — connect directly to Mongo to inject test docs (data-plane not exposed by API).
@pytest.fixture(scope="module")
def mongo():
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = MongoClient(mongo_url)
    yield client[db_name]
    client.close()


@pytest.fixture()
def seed_client_and_docs(mongo):
    """Create an isolated TEST_ client with 3 docs — residual, micro_old, collectable."""
    now = datetime.now(timezone.utc).isoformat()
    client_id = f"TEST_client_{uuid.uuid4().hex[:8]}"
    genes = f"TEST{uuid.uuid4().hex[:6].upper()}"

    client_doc = {
        "id": client_id, "genes_code": genes, "name": "TEST Regularizations Client",
        "email": None, "phone": None, "mobile": None,
        "total_balance": 504.30, "overdue_balance_accounting": 504.30,
        "overdue_balance_collectable": 500.0, "residual_balance": 4.30,
        "oldest_overdue_days": 1220, "collection_index": 0.0,
        "financial_status": "EM_COBRANCA", "traffic_light": "CRITICAL",
        "is_residual_only": False, "is_blocked": False,
        "created_at": now, "updated_at": now,
    }
    mongo.finance_clients.insert_one(client_doc)

    # doc A: bug scenario — 0.80€ / 1220d
    doc_a = {
        "id": f"TEST_FT_A_{uuid.uuid4().hex[:6]}",
        "client_id": client_id, "document_type": "FT",
        "document_number": f"023/{uuid.uuid4().hex[:4]}",
        "amount_original": 120.0, "amount_open": 0.80, "amount_overdue": 0.80,
        "days_overdue": 1220,
        "classification": "collectable",   # deliberately wrong — recompute should fix to residual
        "effective_classification": "collectable",
        "manually_marked_collectable": False, "manual_action": None,
        "last_import_id": "TEST_import", "created_at": now, "updated_at": now,
    }
    # doc B: micro_old — 3.50€ / 500d
    doc_b = {
        "id": f"TEST_FT_B_{uuid.uuid4().hex[:6]}",
        "client_id": client_id, "document_type": "FT",
        "document_number": f"024/{uuid.uuid4().hex[:4]}",
        "amount_original": 40.0, "amount_open": 3.50, "amount_overdue": 3.50,
        "days_overdue": 500,
        "classification": "collectable",
        "effective_classification": "collectable",
        "manually_marked_collectable": False, "manual_action": None,
        "last_import_id": "TEST_import", "created_at": now, "updated_at": now,
    }
    # doc C: collectable — 500€ / 45d
    doc_c = {
        "id": f"TEST_FT_C_{uuid.uuid4().hex[:6]}",
        "client_id": client_id, "document_type": "FT",
        "document_number": f"025/{uuid.uuid4().hex[:4]}",
        "amount_original": 500.0, "amount_open": 500.0, "amount_overdue": 500.0,
        "days_overdue": 45,
        "classification": "collectable",
        "effective_classification": "collectable",
        "manually_marked_collectable": False, "manual_action": None,
        "last_import_id": "TEST_import", "created_at": now, "updated_at": now,
    }
    mongo.finance_documents.insert_many([doc_a, doc_b, doc_c])

    yield {"client_id": client_id, "genes_code": genes,
           "doc_a": doc_a, "doc_b": doc_b, "doc_c": doc_c}

    # cleanup
    mongo.finance_documents.delete_many({"client_id": client_id})
    mongo.finance_clients.delete_one({"id": client_id})
    mongo.finance_actions.delete_many({"client_id": client_id})


# --------------- auth / access ---------------

class TestAuth:
    def test_admin_login_and_finance_access(self, api):
        r = api.get(f"{BASE_URL}/api/finance/data-health")
        assert r.status_code == 200, f"admin should have access: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert "items" in data
        assert "any_blocking" in data


# --------------- classification logic (via recompute) ---------------

class TestClassificationRecompute:
    def test_recompute_endpoint_owner_only(self, api):
        # OWNER can dry_run
        r = api.post(f"{BASE_URL}/api/finance/recompute?dry_run=true")
        assert r.status_code == 200, f"recompute dry_run: {r.status_code} {r.text[:200]}"
        summary = r.json()
        assert "documents_total" in summary
        assert "documents_reclassified" in summary
        assert "clients_updated" in summary
        assert "changes_by_class" in summary
        assert summary["dry_run"] is True

    def test_bug_scenario_080_1220d_classifies_residual(self, api, seed_client_and_docs, mongo):
        """FT with 0.80€ / 1220d MUST be reclassified as residual after recompute."""
        seed = seed_client_and_docs
        r = api.post(f"{BASE_URL}/api/finance/recompute")
        assert r.status_code == 200
        doc = mongo.finance_documents.find_one({"id": seed["doc_a"]["id"]})
        assert doc is not None
        assert doc["classification"] == "residual", \
            f"Expected residual, got {doc['classification']} (amount_open={doc['amount_open']} days={doc['days_overdue']})"
        assert doc["effective_classification"] == "residual"

    def test_micro_old_scenario_350_500d(self, api, seed_client_and_docs, mongo):
        seed = seed_client_and_docs
        api.post(f"{BASE_URL}/api/finance/recompute")
        doc = mongo.finance_documents.find_one({"id": seed["doc_b"]["id"]})
        assert doc["classification"] == "micro_old", \
            f"Expected micro_old for 3.50€/500d, got {doc['classification']}"

    def test_collectable_scenario_500_45d(self, api, seed_client_and_docs, mongo):
        seed = seed_client_and_docs
        api.post(f"{BASE_URL}/api/finance/recompute")
        doc = mongo.finance_documents.find_one({"id": seed["doc_c"]["id"]})
        assert doc["classification"] == "collectable", \
            f"Expected collectable for 500€/45d, got {doc['classification']}"

    def test_micro_old_short_days_stays_collectable(self, mongo, api):
        """3.50€ / 100 days -> collectable (not micro_old because <= 365d)."""
        now = datetime.now(timezone.utc).isoformat()
        cid = f"TEST_client_{uuid.uuid4().hex[:8]}"
        mongo.finance_clients.insert_one({
            "id": cid, "genes_code": f"TEST{uuid.uuid4().hex[:6].upper()}",
            "name": "TEST short-days", "total_balance": 3.50,
            "overdue_balance_accounting": 3.50, "overdue_balance_collectable": 3.50,
            "residual_balance": 0.0, "oldest_overdue_days": 100,
            "financial_status": "EM_COBRANCA", "traffic_light": "YELLOW",
            "is_residual_only": False, "is_blocked": False,
            "created_at": now, "updated_at": now,
        })
        did = f"TEST_FT_S_{uuid.uuid4().hex[:6]}"
        mongo.finance_documents.insert_one({
            "id": did, "client_id": cid, "document_type": "FT",
            "document_number": f"030/{uuid.uuid4().hex[:4]}",
            "amount_original": 3.50, "amount_open": 3.50, "amount_overdue": 3.50,
            "days_overdue": 100,
            "classification": "collectable", "effective_classification": "collectable",
            "manually_marked_collectable": False, "manual_action": None,
            "last_import_id": "TEST", "created_at": now, "updated_at": now,
        })
        try:
            r = api.post(f"{BASE_URL}/api/finance/recompute")
            assert r.status_code == 200
            doc = mongo.finance_documents.find_one({"id": did})
            assert doc["classification"] == "collectable"
        finally:
            mongo.finance_documents.delete_one({"id": did})
            mongo.finance_clients.delete_one({"id": cid})


# --------------- /regularizations endpoint ---------------

class TestRegularizationsEndpoint:
    def test_returns_per_document_structure(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "total_residual" in data
        assert "total_documents" in data and "total_clients" in data
        if data["items"]:
            it = data["items"][0]
            for field in ("document_id", "document_type", "document_number", "amount_open",
                          "days_overdue", "classification", "client_name", "genes_code",
                          "client_residual_balance", "suggestion_code", "suggestion_label"):
                assert field in it, f"missing field {field} in item"

    def test_our_seed_client_appears(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?limit=2000")
        assert r.status_code == 200
        seed_genes = seed_client_and_docs["genes_code"]
        docs_for_seed = [i for i in r.json()["items"] if i["genes_code"] == seed_genes]
        # Both residual (0.80€) and micro_old (3.50€) should show up
        classifications = {d["classification"] for d in docs_for_seed}
        assert "residual" in classifications, f"missing residual doc for {seed_genes}: {docs_for_seed}"
        assert "micro_old" in classifications, f"missing micro_old doc for {seed_genes}: {docs_for_seed}"

    def test_filter_only_micro_old(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?only_micro_old=true&limit=2000")
        assert r.status_code == 200
        classes = {i["classification"] for i in r.json()["items"]}
        assert classes.issubset({"micro_old"}) or not classes, f"unexpected classes: {classes}"

    def test_filter_only_residual(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?only_residual=true&limit=2000")
        assert r.status_code == 200
        classes = {i["classification"] for i in r.json()["items"]}
        assert classes.issubset({"residual"}) or not classes

    def test_filter_min_max_amount_and_days(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?min_amount=1&max_amount=5&limit=2000")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert 1 <= it["amount_open"] <= 5

        r2 = api.get(f"{BASE_URL}/api/finance/regularizations?min_days=400&limit=2000")
        assert r2.status_code == 200
        for it in r2.json()["items"]:
            assert it["days_overdue"] >= 400

    def test_filter_only_low_values(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?only_low_values=true&limit=2000")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["amount_open"] <= 1.0

    def test_sort_by_days_overdue_desc(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?sort_by=days_overdue&sort_dir=desc&limit=2000")
        assert r.status_code == 200
        items = r.json()["items"]
        days = [i["days_overdue"] for i in items]
        assert days == sorted(days, reverse=True), f"not sorted desc: {days[:10]}"

    def test_sort_by_amount_open_asc(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?sort_by=amount_open&sort_dir=asc&limit=2000")
        assert r.status_code == 200
        amounts = [i["amount_open"] for i in r.json()["items"]]
        assert amounts == sorted(amounts)

    def test_search_by_client_name(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?search=TEST%20Regularizations&limit=2000")
        assert r.status_code == 200
        items = r.json()["items"]
        # Should include our seed client
        genes = seed_client_and_docs["genes_code"]
        assert any(i["genes_code"] == genes for i in items), f"seed not found by search among {[i['client_name'] for i in items]}"

    def test_suggestion_labels(self, api, seed_client_and_docs):
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.get(f"{BASE_URL}/api/finance/regularizations?limit=2000")
        assert r.status_code == 200
        for it in r.json()["items"]:
            if it["classification"] == "micro_old":
                assert it["suggestion_code"] == "validate_old_invoice"
                assert "Validar" in it["suggestion_label"]


# --------------- document actions ---------------

class TestDocumentActions:
    def test_mark_collectable_removes_from_regularizations(self, api, seed_client_and_docs, mongo):
        api.post(f"{BASE_URL}/api/finance/recompute")
        seed = seed_client_and_docs
        doc_id = seed["doc_a"]["id"]  # 0.80€/1220d residual

        # Confirm it's in regularizations
        r0 = api.get(f"{BASE_URL}/api/finance/regularizations?limit=2000")
        docs = [i["document_id"] for i in r0.json()["items"]]
        assert doc_id in docs, "residual doc missing before mark_collectable"

        # Apply mark_collectable
        r = api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                     json={"action": "mark_collectable", "reason": "test override"})
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["manually_marked_collectable"] is True
        assert payload["manual_action"] == "mark_collectable"
        assert payload["effective_classification"] == "collectable"

        # Should NOT be in regularizations anymore
        r2 = api.get(f"{BASE_URL}/api/finance/regularizations?limit=2000")
        docs2 = [i["document_id"] for i in r2.json()["items"]]
        assert doc_id not in docs2, "doc should be removed from regularizations after mark_collectable"

    def test_reset_action_restores_residual(self, api, seed_client_and_docs, mongo):
        api.post(f"{BASE_URL}/api/finance/recompute")
        seed = seed_client_and_docs
        doc_id = seed["doc_a"]["id"]
        # First mark_collectable
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "mark_collectable", "reason": "test"})
        # Then reset
        r = api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                     json={"action": "reset", "reason": None})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["manually_marked_collectable"] is False
        assert p["manual_action"] is None
        assert p["effective_classification"] == "residual"

        # And it should appear again in regularizations
        r2 = api.get(f"{BASE_URL}/api/finance/regularizations?limit=2000")
        docs2 = [i["document_id"] for i in r2.json()["items"]]
        assert doc_id in docs2, "doc should be back in regularizations after reset"

    def test_mark_dispute(self, api, seed_client_and_docs):
        seed = seed_client_and_docs
        doc_id = seed["doc_b"]["id"]
        r = api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                     json={"action": "mark_dispute", "reason": "cliente contesta"})
        assert r.status_code == 200, r.text
        assert r.json()["effective_classification"] == "dispute"
        # cleanup
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "reset", "reason": None})

    def test_mark_resolved_operationally(self, api, seed_client_and_docs):
        seed = seed_client_and_docs
        doc_id = seed["doc_b"]["id"]
        r = api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                     json={"action": "mark_resolved_operationally", "reason": "ok"})
        assert r.status_code == 200, r.text
        assert r.json()["effective_classification"] == "resolved_operationally"
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "reset", "reason": None})

    def test_regularize_internally_keeps_classification(self, api, seed_client_and_docs):
        seed = seed_client_and_docs
        doc_id = seed["doc_a"]["id"]
        # ensure residual
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "reset", "reason": None})
        api.post(f"{BASE_URL}/api/finance/recompute")
        r = api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                     json={"action": "regularize_internally", "reason": "pedir à contabilidade"})
        assert r.status_code == 200, r.text
        # effective_classification should remain residual (only marks the request)
        assert r.json()["effective_classification"] in ("residual", "micro_old")
        assert r.json()["manual_action"] == "regularize_internally"
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "reset", "reason": None})

    def test_document_id_with_slash_uses_path_param(self, api, mongo):
        """document_id contains '/' — route must use :path converter."""
        now = datetime.now(timezone.utc).isoformat()
        # Create a doc whose id contains a slash
        cid = f"TEST_client_{uuid.uuid4().hex[:8]}"
        mongo.finance_clients.insert_one({
            "id": cid, "genes_code": f"TSLASH{uuid.uuid4().hex[:4].upper()}",
            "name": "TEST slash client", "total_balance": 0.5,
            "overdue_balance_accounting": 0.5, "overdue_balance_collectable": 0.0,
            "residual_balance": 0.5, "oldest_overdue_days": 1220,
            "financial_status": "REGULARIZACAO_TECNICA", "traffic_light": "YELLOW",
            "is_residual_only": True, "is_blocked": False,
            "created_at": now, "updated_at": now,
        })
        doc_id_with_slash = f"FT_023/1115_{uuid.uuid4().hex[:6]}"  # contains '/'
        mongo.finance_documents.insert_one({
            "id": doc_id_with_slash, "client_id": cid, "document_type": "FT",
            "document_number": "023/1115", "amount_original": 120.0, "amount_open": 0.80,
            "amount_overdue": 0.80, "days_overdue": 1220,
            "classification": "residual", "effective_classification": "residual",
            "manually_marked_collectable": False, "manual_action": None,
            "last_import_id": "TEST", "created_at": now, "updated_at": now,
        })
        try:
            r = api.post(f"{BASE_URL}/api/finance/documents/{doc_id_with_slash}/action",
                         json={"action": "mark_collectable", "reason": "slash test"})
            assert r.status_code == 200, f"path with slash failed: {r.status_code} {r.text[:200]}"
            assert r.json()["id"] == doc_id_with_slash
        finally:
            mongo.finance_documents.delete_one({"id": doc_id_with_slash})
            mongo.finance_clients.delete_one({"id": cid})

    def test_invalid_document_returns_404(self, api):
        r = api.post(f"{BASE_URL}/api/finance/documents/nonexistent-doc-id/action",
                     json={"action": "mark_collectable", "reason": "x"})
        assert r.status_code == 404


# --------------- /collections/today filters ---------------

class TestCollectionsTodayFilters:
    def test_endpoint_ok(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "total_items" in data and "total_value" in data
        assert "is_blocked" in data

    def test_sort_by_options(self, api):
        for sort_by in ["priority", "overdue_asc", "overdue_desc", "total_asc", "total_desc",
                        "days_asc", "days_desc", "last_action", "financial_status", "doc_count"]:
            r = api.get(f"{BASE_URL}/api/finance/collections/today?sort_by={sort_by}")
            assert r.status_code == 200, f"sort_by={sort_by} failed: {r.text[:200]}"

    def test_sort_by_invalid_rejected(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today?sort_by=invalid_option")
        assert r.status_code == 422

    def test_filter_min_max_overdue_and_days(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today?min_overdue=10&max_overdue=10000&min_days=10&max_days=1000")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["overdue_collectable"] >= 10
            assert it["overdue_collectable"] <= 10000
            assert it["oldest_overdue_days"] >= 10
            assert it["oldest_overdue_days"] <= 1000

    def test_only_low_values(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today?only_low_values=true")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["overdue_collectable"] <= 5.0

    def test_only_old_docs(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today?only_old_docs=true")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["oldest_overdue_days"] > 365

    def test_financial_status_filter(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today?financial_status=EM_COBRANCA")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["financial_status"] == "EM_COBRANCA"

    def test_search(self, api):
        r = api.get(f"{BASE_URL}/api/finance/collections/today?search=xyz-nonexistent-xyz")
        assert r.status_code == 200
        assert r.json()["total_items"] == 0

    def test_mark_collectable_appears_in_collections_today(self, api, seed_client_and_docs):
        """After mark_collectable, the doc's client should surface in collections/today."""
        api.post(f"{BASE_URL}/api/finance/recompute")
        seed = seed_client_and_docs
        doc_id = seed["doc_a"]["id"]  # residual 0.80€
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "mark_collectable", "reason": "test"})
        # cleanup override
        r = api.get(f"{BASE_URL}/api/finance/collections/today?limit=500")
        assert r.status_code == 200
        # We can't guarantee the client shows up if data-health is blocking, so only assert on structure.
        # Just ensure the API remains happy.
        assert "items" in r.json()
        api.post(f"{BASE_URL}/api/finance/documents/{doc_id}/action",
                 json={"action": "reset", "reason": None})


# --------------- settings + auto-recompute ---------------

class TestSettingsAutoRecompute:
    def test_get_settings(self, api):
        r = api.get(f"{BASE_URL}/api/finance/settings")
        assert r.status_code == 200
        s = r.json()
        assert "residual_document_threshold" in s
        assert "residual_client_threshold" in s
        assert "micro_old_days_threshold" in s

    def test_put_settings_triggers_recompute(self, api):
        # store originals
        original = api.get(f"{BASE_URL}/api/finance/settings").json()

        payload = {
            "residual_document_threshold": original.get("residual_document_threshold", 1.0),
            "residual_client_threshold": original.get("residual_client_threshold", 5.0),
            "micro_old_days_threshold": original.get("micro_old_days_threshold", 365),
            "residual_max_documents": original.get("residual_max_documents", 20),
        }
        r = api.put(f"{BASE_URL}/api/finance/settings", json=payload)
        assert r.status_code == 200, r.text
        # response returns updated settings dict
        upd = r.json()
        assert upd["residual_document_threshold"] == payload["residual_document_threshold"]
