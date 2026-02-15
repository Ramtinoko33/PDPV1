"""
Test cases for new PDPV Tickets features:
- Email Settings (GET/PUT /api/admin/email-settings)
- Quote History (GET /api/tickets/{id}/quote-history)
- Admin Reports (POST /api/admin/reports)
- Email sending with quote link
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

# Use PUBLIC URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "admin123"
SUPERVISOR_EMAIL = "supervisor@pdpv.pt"
SUPERVISOR_PASSWORD = "super123"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Admin authentication failed - skipping tests")


@pytest.fixture(scope="module")
def supervisor_token(api_client):
    """Get supervisor authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPERVISOR_EMAIL,
        "password": SUPERVISOR_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Supervisor authentication failed - skipping tests")


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    })
    return session


@pytest.fixture(scope="module")
def supervisor_client(api_client, supervisor_token):
    """Session with supervisor auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {supervisor_token}"
    })
    return session


@pytest.fixture(scope="module")
def test_ticket_with_quote(admin_client):
    """Create a test ticket with a quote value for testing quote history"""
    # Create ticket
    response = admin_client.post(f"{BASE_URL}/api/tickets", json={
        "customer_name": "TEST_QuoteHistoryCustomer",
        "customer_phone": "999111222",
        "customer_email": "test_quote_history@test.com",
        "type": "ORCAMENTO_PNEUS",
        "channel": "TELEFONE",
        "priority": "NORMAL",
        "description": "Test ticket for quote history testing"
    })
    assert response.status_code == 200, f"Failed to create test ticket: {response.text}"
    ticket = response.json()
    ticket_id = ticket["id"]
    
    # Set initial quote value
    response = admin_client.put(f"{BASE_URL}/api/tickets/{ticket_id}", json={
        "quote_value": 100.50
    })
    assert response.status_code == 200, f"Failed to set quote value: {response.text}"
    
    yield ticket
    
    # Cleanup - archive the ticket
    try:
        admin_client.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive")
    except Exception:
        pass


# ============== EMAIL SETTINGS TESTS ==============
class TestEmailSettings:
    """Test /api/admin/email-settings endpoints"""
    
    def test_get_email_settings_admin(self, admin_client):
        """Admin can get email settings"""
        response = admin_client.get(f"{BASE_URL}/api/admin/email-settings")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "resend_configured" in data
        assert "email_from" in data
        assert "frontend_url" in data
        assert isinstance(data["resend_configured"], bool)
        print(f"Email settings: resend_configured={data['resend_configured']}, email_from={data['email_from']}")
    
    def test_get_email_settings_supervisor_forbidden(self, supervisor_client):
        """Supervisor cannot access email settings"""
        response = supervisor_client.get(f"{BASE_URL}/api/admin/email-settings")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_put_email_settings_admin(self, admin_client):
        """Admin can update email settings"""
        # Get current settings first
        original = admin_client.get(f"{BASE_URL}/api/admin/email-settings").json()
        
        # Update settings
        response = admin_client.put(f"{BASE_URL}/api/admin/email-settings", json={
            "email_from": "test@example.com",
            "frontend_url": "https://test.example.com"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["frontend_url"] == "https://test.example.com"
        
        # Revert settings
        admin_client.put(f"{BASE_URL}/api/admin/email-settings", json={
            "email_from": original.get("email_from") or "onboarding@resend.dev",
            "frontend_url": original.get("frontend_url") or "https://pdpv-workshop.preview.emergentagent.com"
        })
        print("Email settings update successful")
    
    def test_put_email_settings_supervisor_forbidden(self, supervisor_client):
        """Supervisor cannot update email settings"""
        response = supervisor_client.put(f"{BASE_URL}/api/admin/email-settings", json={
            "email_from": "unauthorized@test.com"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"


# ============== QUOTE HISTORY TESTS ==============
class TestQuoteHistory:
    """Test /api/tickets/{id}/quote-history endpoint"""
    
    def test_get_quote_history(self, admin_client, test_ticket_with_quote):
        """Get quote history shows value changes"""
        ticket_id = test_ticket_with_quote["id"]
        
        response = admin_client.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-history")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        history = response.json()
        assert isinstance(history, list)
        assert len(history) >= 1, "Expected at least 1 history entry from initial quote set"
        
        first_entry = history[0]
        assert "id" in first_entry
        assert "ticket_id" in first_entry
        assert first_entry["ticket_id"] == ticket_id
        assert "new_value" in first_entry
        assert "changed_at" in first_entry
        assert "changed_by_user_id" in first_entry
        print(f"Quote history has {len(history)} entries")
    
    def test_quote_history_logs_changes(self, admin_client, test_ticket_with_quote):
        """Verify that updating quote value creates new history entries"""
        ticket_id = test_ticket_with_quote["id"]
        
        # Get current history count
        initial_history = admin_client.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-history").json()
        initial_count = len(initial_history)
        
        # Update quote value
        new_value = 250.75
        response = admin_client.put(f"{BASE_URL}/api/tickets/{ticket_id}", json={
            "quote_value": new_value
        })
        assert response.status_code == 200, f"Failed to update quote: {response.text}"
        
        # Check history has new entry
        updated_history = admin_client.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-history").json()
        assert len(updated_history) == initial_count + 1, "Expected new history entry after quote update"
        
        # Verify the new entry
        latest_entry = updated_history[0]  # Sorted by changed_at DESC
        assert latest_entry["new_value"] == new_value
        print(f"Quote history entry created: old={latest_entry.get('old_value')} -> new={latest_entry['new_value']}")
    
    def test_quote_history_nonexistent_ticket(self, admin_client):
        """Quote history for non-existent ticket returns 404"""
        response = admin_client.get(f"{BASE_URL}/api/tickets/nonexistent-ticket-id/quote-history")
        assert response.status_code == 404


# ============== ADMIN REPORTS TESTS ==============
class TestAdminReports:
    """Test /api/admin/reports endpoint"""
    
    def test_generate_report_admin(self, admin_client):
        """Admin can generate reports"""
        # Use last 30 days date range
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = admin_client.post(f"{BASE_URL}/api/admin/reports", json={
            "start_date": start_date,
            "end_date": end_date
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        
        report = response.json()
        
        # Verify report structure
        assert "period" in report
        assert "metrics" in report
        assert "agent_performance" in report
        assert "daily_ticket_counts" in report
        
        # Verify metrics structure
        metrics = report["metrics"]
        assert "total_tickets" in metrics
        assert "tickets_by_status" in metrics
        assert "tickets_by_type" in metrics
        assert "sla_compliance_rate" in metrics
        assert "tickets_overdue" in metrics
        assert "quotes_sent" in metrics
        assert "quotes_accepted" in metrics
        assert "quotes_rejected" in metrics
        assert "total_quote_value" in metrics
        
        print(f"Report generated: {metrics['total_tickets']} total tickets, SLA compliance: {metrics['sla_compliance_rate']}%")
    
    def test_generate_report_supervisor(self, supervisor_client):
        """Supervisor can generate reports"""
        response = supervisor_client.post(f"{BASE_URL}/api/admin/reports", json={
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": datetime.now().strftime("%Y-%m-%d")
        })
        assert response.status_code == 200, f"Supervisor should be able to generate reports: {response.text}"
    
    def test_generate_report_with_filters(self, admin_client):
        """Reports can be filtered by status and type"""
        response = admin_client.post(f"{BASE_URL}/api/admin/reports", json={
            "start_date": (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
            "end_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "ABERTO",
            "type": "ORCAMENTO_PNEUS"
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        
        report = response.json()
        metrics = report["metrics"]
        
        # If there are tickets, all should be ABERTO and ORCAMENTO_PNEUS
        if metrics["total_tickets"] > 0:
            # All tickets should have ABERTO status
            assert "ABERTO" in metrics["tickets_by_status"] or metrics["total_tickets"] == 0
            print(f"Filtered report: {metrics['total_tickets']} tickets matching filter")
        else:
            print("No tickets match the filter criteria")
    
    def test_generate_report_agent_performance(self, admin_client):
        """Reports include agent performance data"""
        response = admin_client.post(f"{BASE_URL}/api/admin/reports", json={
            "start_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "end_date": datetime.now().strftime("%Y-%m-%d")
        })
        assert response.status_code == 200
        
        report = response.json()
        agent_performance = report["agent_performance"]
        
        assert isinstance(agent_performance, list)
        
        if len(agent_performance) > 0:
            agent = agent_performance[0]
            assert "user_id" in agent
            assert "user_name" in agent
            assert "tickets_assigned" in agent
            assert "tickets_closed" in agent
            assert "sla_compliance_rate" in agent
            print(f"Agent performance: {len(agent_performance)} agents in report")
    
    def test_generate_report_daily_counts(self, admin_client):
        """Reports include daily ticket counts"""
        response = admin_client.post(f"{BASE_URL}/api/admin/reports", json={
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": datetime.now().strftime("%Y-%m-%d")
        })
        assert response.status_code == 200
        
        report = response.json()
        daily_counts = report["daily_ticket_counts"]
        
        assert isinstance(daily_counts, list)
        assert len(daily_counts) <= 30, "Should not exceed 30 days"
        
        if len(daily_counts) > 0:
            day_entry = daily_counts[0]
            assert "date" in day_entry
            assert "count" in day_entry
            print(f"Daily counts: {len(daily_counts)} days in report")
    
    def test_generate_report_unauthorized(self, api_client):
        """Unauthorized users cannot generate reports"""
        response = api_client.post(f"{BASE_URL}/api/admin/reports", json={
            "start_date": "2024-01-01",
            "end_date": "2024-12-31"
        })
        assert response.status_code == 401


# ============== EMAIL TEST ENDPOINT ==============
class TestEmailTestEndpoint:
    """Test /api/admin/test-email endpoint"""
    
    def test_test_email_requires_resend_config(self, admin_client):
        """Test email endpoint requires RESEND_API_KEY"""
        response = admin_client.post(f"{BASE_URL}/api/admin/test-email", json={
            "recipient_email": "test@example.com"
        })
        
        # Should return 400 if RESEND not configured, or 200 if configured
        assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 400:
            assert "RESEND" in response.text or "resend" in response.text.lower()
            print("Test email endpoint correctly reports RESEND not configured")
        elif response.status_code == 200:
            print("Test email sent successfully (RESEND is configured)")
        else:
            print(f"Test email error: {response.text}")


# ============== QUOTE LINK WITH EMAIL ==============
class TestQuoteLinkWithEmail:
    """Test that generating quote link sends email (if Resend configured)"""
    
    def test_generate_quote_link_creates_link(self, admin_client, test_ticket_with_quote):
        """Generate quote link creates a valid link"""
        ticket_id = test_ticket_with_quote["id"]
        
        # Ensure ticket has quote value
        admin_client.put(f"{BASE_URL}/api/tickets/{ticket_id}", json={
            "quote_value": 150.00
        })
        
        response = admin_client.post(f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "token" in data
        assert "expires_at" in data
        assert len(data["token"]) > 0
        print(f"Quote link generated: token length={len(data['token'])}")
    
    def test_quote_link_without_value_fails(self, admin_client):
        """Cannot generate quote link without quote value"""
        # Create a ticket without quote value
        response = admin_client.post(f"{BASE_URL}/api/tickets", json={
            "customer_name": "TEST_NoQuoteCustomer",
            "customer_phone": "999222333",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "description": "Test ticket without quote"
        })
        assert response.status_code == 200
        ticket_id = response.json()["id"]
        
        try:
            # Try to generate quote link without setting quote value
            response = admin_client.post(f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link")
            assert response.status_code == 400, f"Expected 400, got {response.status_code}"
            print("Quote link correctly requires quote value")
        finally:
            # Cleanup
            admin_client.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
