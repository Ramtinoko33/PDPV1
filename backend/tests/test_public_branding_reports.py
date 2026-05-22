"""
Test suite for public branding endpoint, tire analysis, and rejection reasons reports.
Tests the fixes applied:
1) /api/public/branding - public endpoint (no auth)
2) /api/public/quote/{token} - public quote data
3) /api/admin/reports/tire-analysis - tire size stats (requires auth)
4) /api/admin/reports/rejection-reasons - rejection stats with by_reason, with_reason, without_reason, by_ticket_type
5) POST /api/admin/reports - report metrics (requires auth)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://intake-ai-gateway.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
VALID_QUOTE_TOKEN = os.environ.get("TEST_VALID_QUOTE_TOKEN", "0e0e05ea-ecfb-48a6-bfb3-d593ab488f52")


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        # Backend returns 'token' not 'access_token'
        return data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestPublicBrandingEndpoint:
    """Tests for /api/public/branding - NO AUTH REQUIRED"""
    
    def test_public_branding_returns_200_without_auth(self):
        """GET /api/public/branding should return 200 without authentication"""
        response = requests.get(f"{BASE_URL}/api/public/branding")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_public_branding_returns_expected_fields(self):
        """GET /api/public/branding should return all expected branding fields"""
        response = requests.get(f"{BASE_URL}/api/public/branding")
        assert response.status_code == 200
        
        data = response.json()
        # Check required fields exist
        assert "company_name" in data
        assert "primary_color" in data
        assert "logo_url" in data
        assert "quote_header_text" in data
        assert "quote_footer_text" in data
        
        # Check optional fields exist
        assert "company_phone" in data
        assert "company_email" in data
        assert "quote_page_accepted_title" in data
        assert "quote_page_accepted_message" in data
        assert "quote_page_rejected_title" in data
        assert "quote_page_rejected_message" in data
    
    def test_public_branding_default_values(self):
        """GET /api/public/branding should return sensible defaults"""
        response = requests.get(f"{BASE_URL}/api/public/branding")
        assert response.status_code == 200
        
        data = response.json()
        # Check default values
        assert data["company_name"] == "PDPV Tickets"
        assert data["primary_color"] == "#f97316"
        assert data["quote_header_text"] == "Proposta de Orçamento"
        assert data["quote_footer_text"] == "Obrigado pela sua preferência."


class TestPublicQuoteEndpoint:
    """Tests for /api/public/quote/{token} - NO AUTH REQUIRED"""
    
    def test_public_quote_returns_200_for_valid_token(self):
        """GET /api/public/quote/{token} should return 200 for valid token"""
        response = requests.get(f"{BASE_URL}/api/public/quote/{VALID_QUOTE_TOKEN}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_public_quote_returns_expected_fields(self):
        """GET /api/public/quote/{token} should return all expected quote fields"""
        response = requests.get(f"{BASE_URL}/api/public/quote/{VALID_QUOTE_TOKEN}")
        assert response.status_code == 200
        
        data = response.json()
        # Check required fields
        assert "ticket_number" in data
        assert "customer_name" in data
        assert "quote_value" in data
        assert "quote_sent_at" in data
        assert "quote_options" in data
        
        # Check optional fields
        assert "vehicle_plate" in data
        assert "description" in data
        assert "response_status" in data
        assert "quote_valid_until" in data
        assert "quote_decided_at" in data
        assert "quote_decision" in data
        assert "ticket_attachments" in data
    
    def test_public_quote_returns_404_for_invalid_token(self):
        """GET /api/public/quote/{token} should return 404 for invalid token"""
        response = requests.get(f"{BASE_URL}/api/public/quote/invalid-token-12345")
        assert response.status_code == 404


class TestTireAnalysisEndpoint:
    """Tests for /api/admin/reports/tire-analysis - REQUIRES AUTH"""
    
    def test_tire_analysis_requires_auth(self):
        """GET /api/admin/reports/tire-analysis should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/tire-analysis")
        assert response.status_code == 401
    
    def test_tire_analysis_returns_200_with_auth(self, auth_headers):
        """GET /api/admin/reports/tire-analysis should return 200 with auth"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/tire-analysis",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_tire_analysis_returns_expected_fields(self, auth_headers):
        """GET /api/admin/reports/tire-analysis should return expected structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/tire-analysis",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check required fields
        assert "total_tickets_analyzed" in data
        assert "tickets_with_sizes" in data
        assert "tire_sizes" in data
        assert "brands" in data
        assert "keywords" in data
        
        # Check tire_sizes structure
        assert isinstance(data["tire_sizes"], list)
        if len(data["tire_sizes"]) > 0:
            size = data["tire_sizes"][0]
            assert "size" in size
            assert "count" in size
            assert "percentage" in size
        
        # Check brands structure
        assert isinstance(data["brands"], list)
        
        # Check keywords structure
        assert isinstance(data["keywords"], list)
    
    def test_tire_analysis_with_date_filters(self, auth_headers):
        """GET /api/admin/reports/tire-analysis should accept date filters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/tire-analysis",
            headers=auth_headers,
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"}
        )
        assert response.status_code == 200


class TestRejectionReasonsEndpoint:
    """Tests for /api/admin/reports/rejection-reasons - REQUIRES AUTH"""
    
    def test_rejection_reasons_requires_auth(self):
        """GET /api/admin/reports/rejection-reasons should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/rejection-reasons")
        assert response.status_code == 401
    
    def test_rejection_reasons_returns_200_with_auth(self, auth_headers):
        """GET /api/admin/reports/rejection-reasons should return 200 with auth"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/rejection-reasons",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_rejection_reasons_returns_correct_structure(self, auth_headers):
        """GET /api/admin/reports/rejection-reasons should return by_reason, with_reason, without_reason, by_ticket_type"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/rejection-reasons",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check required fields (the fix was to return these instead of 'reasons')
        assert "total_rejected" in data
        assert "with_reason" in data, "Missing 'with_reason' field - this was part of the fix"
        assert "without_reason" in data, "Missing 'without_reason' field - this was part of the fix"
        assert "by_reason" in data, "Missing 'by_reason' field - this was part of the fix"
        assert "by_ticket_type" in data, "Missing 'by_ticket_type' field - this was part of the fix"
        assert "period" in data
        
        # Verify 'reasons' field does NOT exist (old incorrect field)
        assert "reasons" not in data, "'reasons' field should not exist - it was replaced by 'by_reason'"
    
    def test_rejection_reasons_by_reason_structure(self, auth_headers):
        """by_reason should have code, label, count, percentage"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/rejection-reasons",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data["by_reason"], list)
        
        if len(data["by_reason"]) > 0:
            reason = data["by_reason"][0]
            assert "code" in reason
            assert "label" in reason
            assert "count" in reason
            assert "percentage" in reason
    
    def test_rejection_reasons_by_ticket_type_structure(self, auth_headers):
        """by_ticket_type should have type, count, percentage"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/rejection-reasons",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data["by_ticket_type"], list)
        
        if len(data["by_ticket_type"]) > 0:
            item = data["by_ticket_type"][0]
            assert "type" in item
            assert "count" in item
            assert "percentage" in item
    
    def test_rejection_reasons_with_date_filters(self, auth_headers):
        """GET /api/admin/reports/rejection-reasons should accept date filters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/reports/rejection-reasons",
            headers=auth_headers,
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"}
        )
        assert response.status_code == 200


class TestReportsEndpoint:
    """Tests for POST /api/admin/reports - REQUIRES AUTH"""
    
    def test_reports_requires_auth(self):
        """POST /api/admin/reports should return 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/admin/reports",
            json={"start_date": "2026-01-01", "end_date": "2026-12-31"}
        )
        assert response.status_code == 401
    
    def test_reports_returns_200_with_auth(self, auth_headers):
        """POST /api/admin/reports should return 200 with auth"""
        response = requests.post(
            f"{BASE_URL}/api/admin/reports",
            headers=auth_headers,
            json={"start_date": "2026-01-01", "end_date": "2026-12-31"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_reports_returns_expected_structure(self, auth_headers):
        """POST /api/admin/reports should return period, metrics, agent_performance, daily_ticket_counts"""
        response = requests.post(
            f"{BASE_URL}/api/admin/reports",
            headers=auth_headers,
            json={"start_date": "2026-01-01", "end_date": "2026-12-31"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check required fields
        assert "period" in data
        assert "metrics" in data
        assert "agent_performance" in data
        assert "daily_ticket_counts" in data
    
    def test_reports_metrics_structure(self, auth_headers):
        """metrics should contain all expected fields"""
        response = requests.post(
            f"{BASE_URL}/api/admin/reports",
            headers=auth_headers,
            json={"start_date": "2026-01-01", "end_date": "2026-12-31"}
        )
        assert response.status_code == 200
        
        metrics = response.json()["metrics"]
        assert "total_tickets" in metrics
        assert "tickets_by_status" in metrics
        assert "tickets_by_type" in metrics
        assert "tickets_by_channel" in metrics
        assert "sla_compliance_rate" in metrics
        assert "tickets_overdue" in metrics
        assert "quotes_sent" in metrics
        assert "quotes_accepted" in metrics
        assert "quotes_rejected" in metrics
        assert "total_quote_value" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
