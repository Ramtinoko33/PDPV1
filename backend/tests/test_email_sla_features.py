"""
Test suite for PDPV Tickets - Email and SLA Features
Features:
1. GET /api/admin/email-config - Returns email configuration (Resend status)
2. POST /api/admin/test-email - Test email sending (admin only)
3. Dashboard stats showing atrasados_sla count
4. SLA background job runs every 15 minutes
5. Create message with email integration
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDENTIALS = {"email": "admin@pdpv.pt", "password": "admin123"}
SUPERVISOR_CREDENTIALS = {"email": "supervisor@pdpv.pt", "password": "super123"}


class TestAuthSetup:
    """Setup tests - verify auth works"""
    
    def test_health_check(self):
        """API should be accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health check passed")
    
    def test_admin_login(self):
        """Admin login should work"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=ADMIN_CREDENTIALS
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "ADMIN"
        print(f"✓ Admin login successful: {data['user']['name']}")
    
    def test_supervisor_login(self):
        """Supervisor login should work"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=SUPERVISOR_CREDENTIALS
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "SUPERVISOR"
        print(f"✓ Supervisor login successful: {data['user']['name']}")


class TestEmailConfigEndpoint:
    """Tests for GET /api/admin/email-config"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        return response.json()["token"]
    
    @pytest.fixture
    def supervisor_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=SUPERVISOR_CREDENTIALS)
        return response.json()["token"]
    
    def test_get_email_config_admin(self, admin_token):
        """Admin should be able to get email config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/email-config",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "resend_configured" in data
        assert "email_from" in data
        assert isinstance(data["resend_configured"], bool)
        
        print(f"✓ Email config: resend_configured={data['resend_configured']}, email_from={data['email_from']}")
    
    def test_get_email_config_not_admin(self, supervisor_token):
        """Non-admin users should be rejected (403)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/email-config",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert response.status_code == 403
        print("✓ Supervisor correctly rejected from email config endpoint")
    
    def test_get_email_config_no_auth(self):
        """Unauthenticated requests should be rejected"""
        response = requests.get(f"{BASE_URL}/api/admin/email-config")
        assert response.status_code == 401
        print("✓ Unauthenticated request correctly rejected")


class TestEmailTestEndpoint:
    """Tests for POST /api/admin/test-email"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        return response.json()["token"]
    
    @pytest.fixture
    def supervisor_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=SUPERVISOR_CREDENTIALS)
        return response.json()["token"]
    
    def test_test_email_not_admin_rejected(self, supervisor_token):
        """POST /api/admin/test-email - Non-admin should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/test-email",
            json={"recipient_email": "test@example.com"},
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert response.status_code == 403
        data = response.json()
        assert "administrador" in data.get("detail", "").lower() or "admin" in data.get("detail", "").lower()
        print("✓ Supervisor correctly rejected from test-email endpoint")
    
    def test_test_email_no_api_key_configured(self, admin_token):
        """POST /api/admin/test-email - Should return error if RESEND_API_KEY not configured"""
        # First check if resend is configured
        config_response = requests.get(
            f"{BASE_URL}/api/admin/email-config",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        config = config_response.json()
        
        if not config.get("resend_configured"):
            # Resend not configured - should return 400 error
            response = requests.post(
                f"{BASE_URL}/api/admin/test-email",
                json={"recipient_email": "test@example.com"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 400
            data = response.json()
            assert "RESEND_API_KEY" in data.get("detail", "")
            print("✓ Test email correctly returns error when RESEND_API_KEY not configured")
        else:
            # Resend is configured - test would actually send email
            # Skip actual sending to not spam emails
            print("⚠ RESEND_API_KEY is configured - skipping actual email test to avoid spam")
    
    def test_test_email_no_auth(self):
        """Unauthenticated requests should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/test-email",
            json={"recipient_email": "test@example.com"}
        )
        assert response.status_code == 401
        print("✓ Unauthenticated request correctly rejected")
    
    def test_test_email_invalid_email_format(self, admin_token):
        """Invalid email format should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/test-email",
            json={"recipient_email": "not-an-email"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # Should be 422 for validation error
        assert response.status_code == 422
        print("✓ Invalid email format correctly rejected")


class TestDashboardSLAStats:
    """Tests for dashboard stats including SLA overdue count"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        return response.json()["token"]
    
    def test_dashboard_stats_structure(self, admin_token):
        """Dashboard stats should include atrasados_sla field"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expected fields
        assert "novos" in data
        assert "atrasados_sla" in data
        assert "aguarda_cliente" in data
        assert "em_tratamento" in data
        assert "total" in data
        
        # All should be integers >= 0
        assert isinstance(data["novos"], int) and data["novos"] >= 0
        assert isinstance(data["atrasados_sla"], int) and data["atrasados_sla"] >= 0
        assert isinstance(data["aguarda_cliente"], int) and data["aguarda_cliente"] >= 0
        assert isinstance(data["em_tratamento"], int) and data["em_tratamento"] >= 0
        assert isinstance(data["total"], int) and data["total"] >= 0
        
        print(f"✓ Dashboard stats: novos={data['novos']}, atrasados_sla={data['atrasados_sla']}, "
              f"aguarda_cliente={data['aguarda_cliente']}, em_tratamento={data['em_tratamento']}, total={data['total']}")


class TestTicketSLAOverdue:
    """Test SLA overdue functionality on tickets"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        return response.json()["token"]
    
    def test_ticket_has_sla_due_field(self, admin_token):
        """Tickets should have sla_due field set on creation"""
        # Create a test ticket
        unique_id = str(uuid.uuid4())[:8]
        ticket_data = {
            "customer_name": f"TEST_SLA_Customer_{unique_id}",
            "customer_phone": "912345678",
            "customer_email": "test@example.com",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test SLA ticket"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        ticket = response.json()
        
        # Verify SLA fields
        assert "sla_due" in ticket
        assert ticket["sla_due"] is not None
        assert "first_response_done" in ticket
        assert ticket["first_response_done"] == False
        assert "is_overdue" in ticket
        
        print(f"✓ Ticket created with sla_due={ticket['sla_due']}, first_response_done={ticket['first_response_done']}, is_overdue={ticket['is_overdue']}")
        
        # Cleanup - archive the test ticket
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket['id']}/archive",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"✓ Test ticket archived")
    
    def test_ticket_is_overdue_field(self, admin_token):
        """Ticket list should include is_overdue computed field"""
        response = requests.get(
            f"{BASE_URL}/api/tickets",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        tickets = response.json()
        
        if tickets:
            # Check first ticket has is_overdue field
            assert "is_overdue" in tickets[0]
            print(f"✓ Tickets have is_overdue field. First ticket is_overdue={tickets[0]['is_overdue']}")
        else:
            print("⚠ No tickets found to verify is_overdue field")


class TestMessageWithEmail:
    """Test message creation with email integration"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        return response.json()["token"]
    
    def test_create_message_on_ticket_with_email(self, admin_token):
        """Creating a message on a ticket with customer email should attempt to send email"""
        # First create a ticket with customer email
        unique_id = str(uuid.uuid4())[:8]
        ticket_data = {
            "customer_name": f"TEST_Email_Customer_{unique_id}",
            "customer_phone": "912345678",
            "customer_email": f"testcustomer{unique_id}@example.com",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test ticket for email integration"
        }
        
        ticket_response = requests.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        ticket_id = ticket["id"]
        
        # Create a message on this ticket
        message_data = {
            "body": "Este é uma mensagem de teste para verificar integração de email",
            "channel": "EMAIL",
            "is_quote_response": False
        }
        
        message_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            json=message_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert message_response.status_code == 200
        message = message_response.json()
        
        # Verify message was created
        assert message["ticket_id"] == ticket_id
        assert message["body"] == message_data["body"]
        assert message["channel"] == "EMAIL"
        assert message["direction"] == "OUTBOUND"
        
        print(f"✓ Message created on ticket with email. to_text={message.get('to_text')}")
        
        # Verify ticket was updated (first_response_done should be true)
        ticket_updated = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        
        assert ticket_updated["first_response_done"] == True
        print(f"✓ Ticket first_response_done updated to True after message")
        
        # Cleanup
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/archive",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"✓ Test ticket archived")


class TestQuoteResponse:
    """Test quote response flow with AGUARDA_CLIENTE status"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        return response.json()["token"]
    
    def test_quote_response_changes_status(self, admin_token):
        """Creating a message with is_quote_response=True should change status to AGUARDA_CLIENTE"""
        # Create ticket
        unique_id = str(uuid.uuid4())[:8]
        ticket_data = {
            "customer_name": f"TEST_Quote_Customer_{unique_id}",
            "customer_phone": "912345678",
            "customer_email": f"quote{unique_id}@example.com",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test quote ticket"
        }
        
        ticket_response = requests.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        ticket_id = ticket["id"]
        
        # Create quote response message
        message_data = {
            "body": "Orçamento enviado: 4x pneus Michelin 205/55R16 - €320",
            "channel": "EMAIL",
            "is_quote_response": True  # This should trigger status change
        }
        
        message_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            json=message_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert message_response.status_code == 200
        
        # Verify ticket status changed to AGUARDA_CLIENTE
        ticket_updated = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        
        assert ticket_updated["status"] == "AGUARDA_CLIENTE"
        assert ticket_updated["quote_sent"] == True
        
        print(f"✓ Quote response changed ticket status to AGUARDA_CLIENTE")
        
        # Cleanup
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/archive",
            headers={"Authorization": f"Bearer {admin_token}"}
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
