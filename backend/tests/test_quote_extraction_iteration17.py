"""
Test Suite for PDPV Tickets - Iteration 17
Tests quote route extraction from server.py to routes/quotes.py
All quote-related endpoints should work after extraction.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://quote-management-4.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"
VALID_QUOTE_TOKEN = "0e0e05ea-ecfb-48a6-bfb3-d593ab488f52"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        # Login returns {token} field (not access_token)
        return data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ API health check passed")
    
    def test_login_success(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print("✓ Login successful")


class TestPublicEndpointsNoAuth:
    """Test public endpoints that don't require authentication"""
    
    def test_public_branding_no_auth(self):
        """GET /api/public/branding - should work without auth"""
        response = requests.get(f"{BASE_URL}/api/public/branding")
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "company_name" in data
        assert "primary_color" in data
        assert "quote_header_text" in data
        assert "quote_footer_text" in data
        print(f"✓ Public branding returned: company_name={data.get('company_name')}")
    
    def test_public_quote_no_auth(self):
        """GET /api/public/quote/{token} - should work without auth"""
        response = requests.get(f"{BASE_URL}/api/public/quote/{VALID_QUOTE_TOKEN}")
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "ticket_number" in data
        assert "customer_name" in data
        assert "quote_value" in data or "quote_options" in data
        assert "quote_sent_at" in data
        print(f"✓ Public quote returned: ticket_number={data.get('ticket_number')}, customer={data.get('customer_name')}")
    
    def test_public_quote_invalid_token(self):
        """GET /api/public/quote/{invalid_token} - should return 404"""
        response = requests.get(f"{BASE_URL}/api/public/quote/invalid-token-12345")
        assert response.status_code == 404
        print("✓ Invalid quote token returns 404")
    
    def test_public_quote_pdf_generation(self):
        """GET /api/public/quote/{token}/pdf - should generate PDF"""
        response = requests.get(f"{BASE_URL}/api/public/quote/{VALID_QUOTE_TOKEN}/pdf")
        # Should return 200 with PDF content or 410 if expired
        assert response.status_code in [200, 410]
        if response.status_code == 200:
            assert "application/pdf" in response.headers.get("Content-Type", "")
            print("✓ PDF generation works")
        else:
            print("✓ PDF endpoint returns 410 (expired) as expected")


class TestQuoteOptionsWithAuth:
    """Test quote options endpoints that require authentication"""
    
    def test_get_quote_options_requires_auth(self):
        """GET /api/tickets/{ticket_id}/quote-options - requires auth"""
        # Without auth should fail
        response = requests.get(f"{BASE_URL}/api/tickets/test-ticket-id/quote-options")
        assert response.status_code == 401
        print("✓ Quote options endpoint requires auth")
    
    def test_get_quote_options_with_auth(self, auth_headers):
        """GET /api/tickets/{ticket_id}/quote-options - with auth"""
        # First get a ticket to test with
        tickets_response = requests.get(f"{BASE_URL}/api/tickets", headers=auth_headers)
        if tickets_response.status_code == 200:
            tickets = tickets_response.json()
            if tickets and len(tickets) > 0:
                ticket_id = tickets[0].get("id")
                response = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-options", headers=auth_headers)
                assert response.status_code == 200
                assert isinstance(response.json(), list)
                print(f"✓ Quote options retrieved for ticket {ticket_id}")
            else:
                print("⚠ No tickets found to test quote options")
        else:
            print(f"⚠ Could not get tickets: {tickets_response.status_code}")
    
    def test_save_quote_options_requires_auth(self):
        """POST /api/tickets/{ticket_id}/quote-options - requires auth"""
        response = requests.post(
            f"{BASE_URL}/api/tickets/test-ticket-id/quote-options",
            json={"options": []}
        )
        assert response.status_code == 401
        print("✓ Save quote options requires auth")


class TestQuoteLinkGeneration:
    """Test quote link generation endpoints"""
    
    def test_generate_quote_link_requires_auth(self):
        """POST /api/tickets/{ticket_id}/generate-quote-link - requires auth"""
        response = requests.post(f"{BASE_URL}/api/tickets/test-ticket-id/generate-quote-link")
        assert response.status_code == 401
        print("✓ Generate quote link requires auth")
    
    def test_generate_reply_link_requires_auth(self):
        """POST /api/tickets/{ticket_id}/generate-reply-link - requires auth (still in server.py)"""
        response = requests.post(f"{BASE_URL}/api/tickets/test-ticket-id/generate-reply-link")
        assert response.status_code == 401
        print("✓ Generate reply link requires auth (still in server.py)")


class TestQuoteRespond:
    """Test public quote respond endpoint"""
    
    def test_respond_to_quote_already_decided(self):
        """POST /api/public/quote/{token}/respond - should fail if already decided"""
        response = requests.post(
            f"{BASE_URL}/api/public/quote/{VALID_QUOTE_TOKEN}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Test",
                "accepted_option_ids": []
            }
        )
        # Should return 409 if already decided
        assert response.status_code in [200, 409]
        if response.status_code == 409:
            print("✓ Quote respond correctly returns 409 for already decided quote")
        else:
            print("✓ Quote respond endpoint works")


class TestAdminReports:
    """Test admin reports endpoints"""
    
    def test_tire_analysis_requires_auth(self):
        """GET /api/admin/reports/tire-analysis - requires auth"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/tire-analysis")
        assert response.status_code == 401
        print("✓ Tire analysis requires auth")
    
    def test_tire_analysis_with_auth(self, auth_headers):
        """GET /api/admin/reports/tire-analysis - with auth"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/tire-analysis", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "total_tickets_analyzed" in data
        assert "tickets_with_sizes" in data
        assert "tire_sizes" in data
        assert "brands" in data
        assert "keywords" in data
        print(f"✓ Tire analysis returned: {data.get('total_tickets_analyzed')} tickets analyzed")
    
    def test_rejection_reasons_requires_auth(self):
        """GET /api/admin/reports/rejection-reasons - requires auth"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/rejection-reasons")
        assert response.status_code == 401
        print("✓ Rejection reasons requires auth")
    
    def test_rejection_reasons_with_auth(self, auth_headers):
        """GET /api/admin/reports/rejection-reasons - with auth"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/rejection-reasons", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields (fixed in this session)
        assert "total_rejected" in data
        assert "with_reason" in data
        assert "without_reason" in data
        assert "by_reason" in data
        assert "by_ticket_type" in data
        print(f"✓ Rejection reasons returned: {data.get('total_rejected')} total rejected")
    
    def test_reports_endpoint_requires_auth(self):
        """POST /api/admin/reports - requires auth"""
        response = requests.post(f"{BASE_URL}/api/admin/reports", json={})
        assert response.status_code == 401
        print("✓ Reports endpoint requires auth")
    
    def test_reports_endpoint_with_auth(self, auth_headers):
        """POST /api/admin/reports - with auth"""
        response = requests.post(
            f"{BASE_URL}/api/admin/reports",
            headers=auth_headers,
            json={
                "start_date": "2024-01-01",
                "end_date": "2026-12-31"
            }
        )
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "period" in data
        assert "metrics" in data
        assert "agent_performance" in data
        assert "daily_ticket_counts" in data
        print(f"✓ Reports returned: {data['metrics'].get('total_tickets')} total tickets")


class TestDashboardAndTickets:
    """Test dashboard and ticket endpoints (regression check)"""
    
    def test_dashboard_stats(self, auth_headers):
        """GET /api/dashboard/stats - regression check"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        print(f"✓ Dashboard stats: {data.get('total')} total tickets")
    
    def test_tickets_list(self, auth_headers):
        """GET /api/tickets - regression check"""
        response = requests.get(f"{BASE_URL}/api/tickets", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Tickets list returned {len(response.json())} tickets")
    
    def test_ticket_types(self, auth_headers):
        """GET /api/ticket-types - regression check"""
        response = requests.get(f"{BASE_URL}/api/ticket-types", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Ticket types returned {len(response.json())} types")
    
    def test_ticket_statuses(self, auth_headers):
        """GET /api/ticket-statuses - regression check"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Ticket statuses returned {len(response.json())} statuses")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
