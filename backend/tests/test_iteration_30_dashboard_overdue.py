"""
Iteration 30 — Backend tests for the Dashboard 'Tickets Atrasados' bug fix.

Bug: /api/tickets applied `overdue=true` filter AFTER .limit(100), so overdue
tickets older than the 100 newest were invisible; Dashboard also filtered
overdueTickets client-side by dashboard_default_states.

Fix (backend):
  - Apply overdue filter DB-side (before .limit) using
    sla_breached=True  OR  (first_response_done!=True AND sla_paused_at=None
    AND sla_due<now), plus status != FECHADO.
  - Coexist safely with existing $or (search), status, type, assigned_to filters.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "HCNMEnKMLq")
AGENT_EMAIL = "cobranca.teste@pdpv.pt"
AGENT_PASSWORD = os.environ.get("TEST_AGENT_PASSWORD", "TesteFin2026!")


# ---------- fixtures ----------
def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASSWORD)}"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login(AGENT_EMAIL, AGENT_PASSWORD)}"}


@pytest.fixture(scope="module")
def admin_stats(admin_headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Feature: ?overdue=true returns only overdue tickets ----------
class TestOverdueTrueOnlyOverdue:
    def test_overdue_true_limit_5_returns_only_overdue(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&limit=5",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) <= 5
        # Every ticket returned must be flagged as overdue
        for t in data:
            assert t.get("is_overdue") is True, (
                f"ticket {t.get('ticket_number')} returned by overdue=true "
                f"has is_overdue={t.get('is_overdue')}"
            )
            # And never FECHADO
            assert t.get("status") != "FECHADO"

    def test_overdue_true_large_limit_matches_stats(self, admin_headers, admin_stats):
        """
        With limit=200, count of overdue tickets returned should be >=
        stats.atrasados_sla (check_ticket_overdue is a superset: includes
        sla_breached=True even if first_response_done is now True).
        Delta should stay small in a healthy DB.
        """
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&limit=200",
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        atrasados_stats = admin_stats.get("atrasados_sla", 0)
        # Superset relation: overdue endpoint count >= stats count
        assert len(data) >= atrasados_stats, (
            f"overdue endpoint returned {len(data)} but stats.atrasados_sla="
            f"{atrasados_stats}; expected endpoint >= stats"
        )
        # Every ticket is really overdue
        for t in data:
            assert t.get("is_overdue") is True


# ---------- Feature: role-based filtering still applies with overdue ----------
class TestOverdueRoleGating:
    def test_agent_only_sees_own_or_unassigned(self, agent_headers):
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&limit=200",
            headers=agent_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Get the agent's own user id from the token via /auth/me
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=agent_headers, timeout=10)
        assert me.status_code == 200
        my_id = me.json()["id"]
        for t in data:
            assigned = t.get("assigned_to_user_id")
            assert assigned in (None, my_id), (
                f"AGENT saw ticket assigned to {assigned}, not own ({my_id})"
            )
            assert t.get("is_overdue") is True

    def test_admin_sees_more_or_equal_than_agent(self, admin_headers, agent_headers):
        ra = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&limit=500",
            headers=admin_headers,
            timeout=30,
        )
        rg = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&limit=500",
            headers=agent_headers,
            timeout=30,
        )
        assert ra.status_code == 200 and rg.status_code == 200
        assert len(ra.json()) >= len(rg.json())


# ---------- Feature: overdue=false / no overdue param (regression) ----------
class TestOverdueFalseAndDefault:
    def test_overdue_false_returns_only_not_overdue(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=false&limit=50",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200
        for t in r.json():
            assert t.get("is_overdue") is False

    def test_no_overdue_param_returns_mix(self, admin_headers, admin_stats):
        """Without overdue param the list should not be filtered to overdue only."""
        r = requests.get(
            f"{BASE_URL}/api/tickets?limit=100",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        # If stats.atrasados_sla > 0 AND stats.total > atrasados the list must
        # contain at least one non-overdue ticket (proves we're not accidentally
        # filtering to overdue only)
        if admin_stats.get("total", 0) - admin_stats.get("atrasados_sla", 0) > 20:
            non_overdue = [t for t in data if not t.get("is_overdue")]
            assert len(non_overdue) > 0, (
                "GET /api/tickets without overdue param returned only overdue tickets"
            )


# ---------- Feature: overdue combined with other filters ----------
class TestOverdueCombinedFilters:
    def test_overdue_with_search(self, admin_headers):
        """search + overdue must coexist via $and, not overwrite each other."""
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&search=a&limit=20",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        for t in r.json():
            assert t.get("is_overdue") is True
            hay = " ".join(
                str(t.get(k) or "")
                for k in (
                    "customer_phone",
                    "customer_name",
                    "vehicle_plate",
                    "ticket_number",
                    "description",
                )
            ).lower()
            assert "a" in hay, f"search=a did not match ticket fields: {t.get('ticket_number')}"

    def test_overdue_with_status_em_tratamento(self, admin_headers):
        """
        status=EM_TRATAMENTO should NOT be overwritten by the {$ne: FECHADO}
        default inside the overdue branch.
        """
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&status=EM_TRATAMENTO&limit=100",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        for t in r.json():
            assert t.get("status") == "EM_TRATAMENTO", (
                f"expected EM_TRATAMENTO, got {t.get('status')}"
            )
            assert t.get("is_overdue") is True

    def test_overdue_with_status_fechado_returns_empty(self, admin_headers):
        """FECHADO tickets can never be overdue."""
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&status=FECHADO&limit=50",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json() == [], "FECHADO tickets should never appear as overdue"


# ---------- Regression: Dashboard reported bug scenario ----------
class TestDashboardBugScenario:
    def test_atrasados_sla_gt_zero_implies_overdue_endpoint_non_empty(
        self, admin_headers, admin_stats
    ):
        """
        The original bug: stats.atrasados_sla=62 but the panel showed
        'Sem tickets atrasados' because /api/tickets?overdue=true came back
        empty. This asserts that whenever stats say there are overdue
        tickets, the endpoint used by the panel returns at least one.
        """
        atrasados = admin_stats.get("atrasados_sla", 0)
        if atrasados == 0:
            pytest.skip("No overdue tickets in preview DB right now — cannot reproduce bug scenario")
        r = requests.get(
            f"{BASE_URL}/api/tickets?overdue=true&limit=5",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, (
            f"stats.atrasados_sla={atrasados} but /api/tickets?overdue=true "
            "returned empty — original bug not fixed"
        )
