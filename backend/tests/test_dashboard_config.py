"""
Dashboard Configuration Feature Tests
Tests: PUT /api/users/me/dashboard, GET /api/auth/me (dashboard fields),
GET /api/dashboard/stats (with pref_types and dashboard_only_mine filters)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
SUPERVISOR_EMAIL = "supervisor@pdpv.pt"
SUPERVISOR_PASS = "f9pSIn6zRP"
AGENT_EMAIL = "agente@pdpv.pt"
AGENT_PASS = "yHprFGvPUJ"


@pytest.fixture(scope="module")
def admin_token():
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASS
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def supervisor_token():
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPERVISOR_EMAIL,
        "password": SUPERVISOR_PASS
    })
    assert response.status_code == 200, f"Supervisor login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def agent_token():
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASS
    })
    assert response.status_code == 200, f"Agent login failed: {response.text}"
    return response.json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ===== GET /api/auth/me - dashboard fields =====

class TestAuthMeDashboardFields:
    """Verify GET /api/auth/me returns dashboard config fields"""

    def test_get_me_returns_dashboard_default_types(self, admin_token):
        """GET /api/auth/me should return dashboard_default_types field"""
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "dashboard_default_types" in data, "dashboard_default_types missing from /auth/me"
        assert isinstance(data["dashboard_default_types"], list)

    def test_get_me_returns_dashboard_default_states(self, admin_token):
        """GET /api/auth/me should return dashboard_default_states field"""
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "dashboard_default_states" in data, "dashboard_default_states missing from /auth/me"
        assert isinstance(data["dashboard_default_states"], list)

    def test_get_me_returns_dashboard_only_mine(self, admin_token):
        """GET /api/auth/me should return dashboard_only_mine field"""
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "dashboard_only_mine" in data, "dashboard_only_mine missing from /auth/me"
        assert isinstance(data["dashboard_only_mine"], bool)

    def test_get_me_unauthenticated_returns_401(self):
        """Unauthenticated request to /auth/me should return 401"""
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# ===== PUT /api/users/me/dashboard - save dashboard config =====

class TestPutDashboardConfig:
    """Verify PUT /api/users/me/dashboard saves preferences"""

    def test_save_dashboard_types_only(self, admin_token):
        """Save dashboard_default_types and verify persistence"""
        payload = {
            "dashboard_default_types": ["MARCACAO", "INFORMACAO"],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_default_types"] == ["MARCACAO", "INFORMACAO"]
        assert data["dashboard_default_states"] == []
        assert data["dashboard_only_mine"] == False

    def test_save_types_persisted_in_get_me(self, admin_token):
        """After saving types, GET /auth/me should return the saved values"""
        payload = {
            "dashboard_default_types": ["ORCAMENTO_PNEUS"],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(admin_token))
        
        # Verify persistence with GET
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "ORCAMENTO_PNEUS" in data["dashboard_default_types"]

    def test_save_dashboard_states_only(self, admin_token):
        """Save dashboard_default_states and verify persistence"""
        payload = {
            "dashboard_default_types": [],
            "dashboard_default_states": ["ABERTO", "EM_TRATAMENTO"],
            "dashboard_only_mine": False
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_default_states"] == ["ABERTO", "EM_TRATAMENTO"]

    def test_save_dashboard_only_mine(self, admin_token):
        """Save dashboard_only_mine=True and verify persistence"""
        payload = {
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": True
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_only_mine"] == True

    def test_save_only_mine_persisted(self, admin_token):
        """After saving only_mine=True, GET /auth/me should return True"""
        payload = {
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": True
        }
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(admin_token))
        
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_only_mine"] == True

    def test_save_all_fields_together(self, supervisor_token):
        """Save all three dashboard fields at once"""
        payload = {
            "dashboard_default_types": ["MARCACAO", "RECLAMACAO"],
            "dashboard_default_states": ["ABERTO"],
            "dashboard_only_mine": True
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_default_types"] == ["MARCACAO", "RECLAMACAO"]
        assert data["dashboard_default_states"] == ["ABERTO"]
        assert data["dashboard_only_mine"] == True

    def test_save_returns_user_response_with_correct_fields(self, admin_token):
        """Response of PUT should include id, email, name, role"""
        payload = {
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert "email" in data
        assert "name" in data
        assert "role" in data

    def test_save_requires_auth(self):
        """PUT /api/users/me/dashboard without auth returns 401"""
        payload = {
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload)
        assert r.status_code == 401

    def test_clear_all_prefs(self, admin_token):
        """Can clear all prefs by saving empty arrays and False"""
        # First set some prefs
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": ["MARCACAO"],
            "dashboard_default_states": ["ABERTO"],
            "dashboard_only_mine": True
        }, headers=auth_headers(admin_token))
        
        # Now clear all
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_default_types"] == []
        assert data["dashboard_default_states"] == []
        assert data["dashboard_only_mine"] == False

    def test_agent_can_save_dashboard_config(self, agent_token):
        """Agent role can also save dashboard config"""
        payload = {
            "dashboard_default_types": ["INFORMACAO"],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json=payload, headers=auth_headers(agent_token))
        assert r.status_code == 200
        data = r.json()
        assert "INFORMACAO" in data["dashboard_default_types"]


# ===== GET /api/dashboard/stats - preference filtering =====

class TestDashboardStatsWithPrefs:
    """Verify GET /api/dashboard/stats applies preference filters"""

    def test_dashboard_stats_returns_correct_fields(self, admin_token):
        """GET /api/dashboard/stats returns all required stats fields"""
        r = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "novos" in data
        assert "atrasados_sla" in data
        assert "aguarda_cliente" in data
        assert "em_tratamento" in data
        assert "total" in data

    def test_stats_without_prefs_returns_all(self, admin_token):
        """Stats without type prefs should count all ticket types"""
        # Clear prefs first
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(admin_token))
        
        r = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        total_no_filter = data["total"]
        assert isinstance(total_no_filter, int)

    def test_stats_with_type_filter_reduces_or_equal_count(self, admin_token):
        """Stats with type filter should return <= count vs no filter"""
        # First get count without filter
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(admin_token))
        
        r_all = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers(admin_token))
        total_all = r_all.json()["total"]
        
        # Set a specific type filter
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": ["MARCACAO"],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(admin_token))
        
        r_filtered = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers(admin_token))
        total_filtered = r_filtered.json()["total"]
        
        assert total_filtered <= total_all, f"Filtered total ({total_filtered}) should be <= total without filter ({total_all})"

    def test_stats_with_only_mine_reduces_or_equal(self, supervisor_token):
        """Stats with only_mine should return <= count vs no filter (for non-agent)"""
        # Clear filter
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(supervisor_token))
        
        r_all = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers(supervisor_token))
        total_all = r_all.json()["total"]
        
        # Enable only_mine
        requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": True
        }, headers=auth_headers(supervisor_token))
        
        r_mine = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers(supervisor_token))
        total_mine = r_mine.json()["total"]
        
        assert total_mine <= total_all, f"only_mine total ({total_mine}) should be <= all ({total_all})"

    def test_stats_unauthenticated_returns_401(self):
        """GET /api/dashboard/stats without auth returns 401"""
        r = requests.get(f"{BASE_URL}/api/dashboard/stats")
        assert r.status_code == 401

    def test_cleanup_reset_admin_prefs(self, admin_token):
        """Reset admin prefs to empty after tests"""
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(admin_token))
        assert r.status_code == 200

    def test_cleanup_reset_supervisor_prefs(self, supervisor_token):
        """Reset supervisor prefs to empty after tests"""
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(supervisor_token))
        assert r.status_code == 200

    def test_cleanup_reset_agent_prefs(self, agent_token):
        """Reset agent prefs to empty after tests"""
        r = requests.put(f"{BASE_URL}/api/users/me/dashboard", json={
            "dashboard_default_types": [],
            "dashboard_default_states": [],
            "dashboard_only_mine": False
        }, headers=auth_headers(agent_token))
        assert r.status_code == 200
