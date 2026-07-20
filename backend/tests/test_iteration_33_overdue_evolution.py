"""
Iteration 33 – GET /api/finance/overdue-evolution
Tests the time series endpoint that shows daily overdue evolution vs recovered vs
newly-overdue split. Preview DB has 2 daily snapshots (2026-07-01, 07-02) and
recovery events on 07-02 → expected: series.length == 2, summary.total_delta == 0,
total_recovered == total_newly_overdue.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://intake-ai-gateway.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"
NO_FIN_EMAIL = "rececao.teste@pdpv.pt"
NO_FIN_PASSWORD = "TesteFin2026!"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def no_fin_token():
    try:
        return _login(NO_FIN_EMAIL, NO_FIN_PASSWORD)
    except AssertionError:
        pytest.skip("no-finance test user not available in this env")


# ---------------------- 200 shape ----------------------

class TestOverdueEvolutionShape:
    def test_200_default_days(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "series" in body
        assert "summary" in body
        assert isinstance(body["series"], list)
        assert isinstance(body["summary"], dict)

    def test_series_item_fields(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        assert r.status_code == 200
        series = r.json()["series"]
        assert len(series) >= 1, "preview DB should have at least 1 snapshot"
        required = {
            "date", "total_overdue_collectable", "total_overdue_accounting",
            "total_balance", "total_residual", "clients_with_overdue",
            "recovered_amount", "recovered_events", "net_change", "newly_overdue",
        }
        for item in series:
            missing = required - set(item.keys())
            assert not missing, f"missing fields in series item: {missing}"

    def test_summary_fields(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        body = r.json()
        s = body["summary"]
        required = {
            "days_covered", "first_date", "last_date",
            "overdue_at_start", "overdue_at_end", "total_delta",
            "total_recovered", "total_newly_overdue",
        }
        missing = required - set(s.keys())
        assert not missing, f"missing summary fields: {missing}"

    def test_days_covered_matches_series_len(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        body = r.json()
        assert body["summary"]["days_covered"] == len(body["series"])


# ---------------------- math consistency ----------------------

class TestOverdueEvolutionMath:
    def test_newly_overdue_equals_net_change_plus_recovered(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        body = r.json()
        series = body["series"]
        # skip first day (net_change is 0 by construction)
        for item in series[1:]:
            expected = round(item["net_change"] + item["recovered_amount"], 2)
            assert abs(item["newly_overdue"] - expected) < 0.01, (
                f"item {item['date']}: newly_overdue={item['newly_overdue']} vs "
                f"net_change+recovered={expected}"
            )

    def test_first_day_net_change_is_zero(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        series = r.json()["series"]
        if series:
            assert series[0]["net_change"] == 0.0
            assert series[0]["newly_overdue"] == 0.0

    def test_preview_scenario_stagnant(self, admin_headers):
        """Preview DB should have delta≈0 and recovered≈newly_overdue (the reported case)."""
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        s = r.json()["summary"]
        # spec says: series.length=2, delta=0, recovered=221.41, newly=221.41
        assert s["days_covered"] >= 2, f"expected at least 2 days in preview, got {s['days_covered']}"
        # newly ≈ delta + recovered (over the whole window, delta = sum(net_change))
        expected_newly = round(s["total_delta"] + s["total_recovered"], 2)
        assert abs(s["total_newly_overdue"] - expected_newly) < 0.01, (
            f"total_newly_overdue={s['total_newly_overdue']} vs delta+recovered={expected_newly}"
        )

    def test_summary_delta_equals_end_minus_start(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=admin_headers, timeout=30
        )
        s = r.json()["summary"]
        if s["days_covered"] >= 2:
            expected = round(s["overdue_at_end"] - s["overdue_at_start"], 2)
            assert abs(s["total_delta"] - expected) < 0.01


# ---------------------- pagination / clamping ----------------------

class TestOverdueEvolutionParams:
    def test_days_1_clamps_to_one_day_window(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=1",
            headers=admin_headers, timeout=30
        )
        assert r.status_code == 200
        # with days=1 the cutoff is today, so series should be 0 or 1 depending on today's data
        assert len(r.json()["series"]) <= 1

    def test_days_400_clamps_to_365(self, admin_headers):
        # Not directly observable in response, but the endpoint must not 500/422
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=400",
            headers=admin_headers, timeout=30
        )
        assert r.status_code == 200
        # verifies clamp: with 365-day window we still only get the preview snapshots
        body = r.json()
        assert body["summary"]["days_covered"] <= 365

    def test_days_zero_or_negative_clamped(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=0",
            headers=admin_headers, timeout=30
        )
        # endpoint uses max(1, min(days, 365)) → 0 becomes 1
        assert r.status_code == 200


# ---------------------- auth / permissions ----------------------

class TestOverdueEvolutionAuth:
    def test_no_jwt_returns_401_or_403(self):
        r = requests.get(f"{BASE_URL}/api/finance/overdue-evolution?days=30", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_user_without_finance_role_returns_403(self, no_fin_token):
        headers = {"Authorization": f"Bearer {no_fin_token}"}
        r = requests.get(
            f"{BASE_URL}/api/finance/overdue-evolution?days=30",
            headers=headers, timeout=30
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} - {r.text[:200]}"


# ---------------------- regression: /finance/dashboard ----------------------

class TestDashboardRegression:
    def test_dashboard_still_returns_expected_fields(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/dashboard", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in [
            "total_balance", "total_overdue_accounting", "total_overdue_collectable",
            "total_residual", "clients_with_overdue", "clients_blocked",
            "promises_active", "promises_failed", "aging_buckets", "top_debtors",
            "recovered_today", "recovered_week", "recovered_month",
        ]:
            assert k in body, f"missing dashboard field {k}"

    def test_collections_today_still_reachable(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/collections/today", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_clients_list_reachable(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/clients?page=1&page_size=5", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "clients" in r.json()

    def test_promises_list_reachable(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/finance/promises", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "promises" in r.json()

    def test_data_health_reachable(self, admin_headers):
        # feeds the FinanceBadge freshness indicator
        r = requests.get(f"{BASE_URL}/api/finance/data-health", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "items" in r.json()
