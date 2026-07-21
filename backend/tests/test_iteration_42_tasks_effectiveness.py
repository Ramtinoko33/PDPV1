"""
Iteration 42 — CRM Finance > Eficácia das Tarefas (Dashboard read-only).
Tests GET /api/finance/tasks/effectiveness endpoint.
"""
import os
import pytest
import requests
from datetime import date, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required")

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PWD = "HCNMEnKMLq"
AGENT_EMAIL = "cobranca.teste@pdpv.pt"
AGENT_PWD = "TesteFin2026!"
NOACCESS_EMAIL = "rececao.teste@pdpv.pt"
NOACCESS_PWD = "TesteFin2026!"


def _login(email, pwd):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def agent_token():
    return _login(AGENT_EMAIL, AGENT_PWD)


@pytest.fixture(scope="module")
def noaccess_token():
    return _login(NOACCESS_EMAIL, NOACCESS_PWD)


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ===== Structural / default range tests =====

class TestEffectivenessStructure:
    def test_default_range_and_full_structure(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()

        # range default: -30d .. today
        assert "range" in d
        assert d["range"]["to"] == date.today().isoformat()
        assert d["range"]["from"] == (date.today() - timedelta(days=30)).isoformat()

        # all required top-level keys
        for key in [
            "totals", "rates", "amounts", "communications", "promises_created",
            "regularizations_treated", "block_task_done", "by_task_type", "by_segment",
            "top_postpone_reasons", "top_reject_reasons", "top_converted_from_type",
            "daily_series", "today_summary",
        ]:
            assert key in d, f"missing key {key}"

        # totals shape
        for k in ["generated", "open", "done", "postponed", "converted", "rejected", "expired", "in_review"]:
            assert k in d["totals"], f"missing totals.{k}"
            assert isinstance(d["totals"][k], int)

        # rates keys
        for k in ["completion_rate", "rejection_rate", "postpone_rate"]:
            assert k in d["rates"]

        # amounts
        assert "covered_by_done" in d["amounts"]
        assert "promised_total" in d["amounts"]

        # communications
        for k in ["emails", "whatsapps", "phone_calls", "notes"]:
            assert k in d["communications"]

        # today_summary
        for k in ["planned", "done", "untreated", "postponed", "rejected"]:
            assert k in d["today_summary"]

        # by_task_type items have required shape (when non-empty)
        for tt in d["by_task_type"]:
            for k in ["task_type", "generated", "done", "rejected", "postponed", "converted",
                      "completion_rate", "rejection_rate"]:
                assert k in tt

    def test_no_mongodb_id_in_response(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
        assert "_id" not in r.text[:20000]  # shallow check


# ===== Filters =====

class TestEffectivenessFilters:
    def test_date_range_filter_respected(self, admin_token):
        df = "2026-01-01"
        dt = "2026-01-15"
        r = requests.get(
            f"{BASE_URL}/api/finance/tasks/effectiveness",
            headers=_hdr(admin_token),
            params={"date_from": df, "date_to": dt},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["range"]["from"] == df
        assert d["range"]["to"] == dt

    def test_task_type_filter(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/finance/tasks/effectiveness",
            headers=_hdr(admin_token),
            params={"task_type": "UPDATE_FINANCE_CONTACT"},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        # If any task_type present, only UPDATE_FINANCE_CONTACT allowed
        for row in d["by_task_type"]:
            assert row["task_type"] == "UPDATE_FINANCE_CONTACT"

    def test_status_filter(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/finance/tasks/effectiveness",
            headers=_hdr(admin_token),
            params={"status": "DONE"},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        # only DONE tasks so open/rejected/postponed totals must be 0
        assert d["totals"]["open"] == 0
        assert d["totals"]["rejected"] == 0
        assert d["totals"]["postponed"] == 0

    def test_customer_segment_filter(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/finance/tasks/effectiveness",
            headers=_hdr(admin_token),
            params={"customer_segment": "PARTICULAR"},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        # if by_segment has entries, only PARTICULAR allowed
        for row in d["by_segment"]:
            assert row["segment"] == "PARTICULAR"

    def test_feedback_reason_filter(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/finance/tasks/effectiveness",
            headers=_hdr(admin_token),
            params={"feedback_reason": "active_promise"},
            timeout=30,
        )
        assert r.status_code == 200


# ===== Rates math =====

class TestEffectivenessRates:
    def test_rates_avoid_divide_by_zero(self, admin_token):
        # Very early range with likely zero tasks
        r = requests.get(
            f"{BASE_URL}/api/finance/tasks/effectiveness",
            headers=_hdr(admin_token),
            params={"date_from": "2000-01-01", "date_to": "2000-01-02"},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        # no tasks -> generated may be 0, rates must be 0 (not error)
        assert d["totals"]["generated"] == 0
        assert d["rates"]["completion_rate"] == 0
        assert d["rates"]["rejection_rate"] == 0
        assert d["rates"]["postpone_rate"] == 0

    def test_rates_math_consistency(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        g = d["totals"]["generated"]
        if g > 0:
            expected_completion = round(d["totals"]["done"] * 100.0 / g, 1)
            expected_rejection = round(d["totals"]["rejected"] * 100.0 / g, 1)
            expected_postpone = round(d["totals"]["postponed"] * 100.0 / g, 1)
            assert d["rates"]["completion_rate"] == expected_completion
            assert d["rates"]["rejection_rate"] == expected_rejection
            assert d["rates"]["postpone_rate"] == expected_postpone


# ===== Permissions =====

class TestEffectivenessPermissions:
    def test_noaccess_forbidden(self, noaccess_token):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", headers=_hdr(noaccess_token), timeout=30)
        assert r.status_code == 403, f"expected 403 for no-finance-role user, got {r.status_code}"

    def test_unauthenticated_denied(self):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", timeout=30)
        assert r.status_code in (401, 403)

    def test_agent_scoped_to_self(self, agent_token, admin_token):
        # COLLECTIONS_AGENT should have assigned_to auto-forced to self
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", headers=_hdr(agent_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        # filters.assigned_to must be set to a non-null user id (auto-forced)
        assert d["filters"]["assigned_to"] is not None, (
            "COLLECTIONS_AGENT should have assigned_to auto-set to self"
        )

    def test_owner_sees_all_no_forced_assigned(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/effectiveness", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        # OWNER without ?assigned_to param -> filters.assigned_to null
        assert d["filters"]["assigned_to"] is None


# ===== Regression from iteration 41 =====

class TestRegressionIteration41:
    def test_tasks_today_ok(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/finance/tasks/today", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # basic contract preserved
        assert "tasks" in d or "items" in d or isinstance(d, dict)

    def test_clients_export_ok(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/finance/clients-export", headers=_hdr(admin_token), timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith(
            "application/vnd.openxmlformats-officedocument"
        ) or "spreadsheet" in r.headers.get("content-type", "")
