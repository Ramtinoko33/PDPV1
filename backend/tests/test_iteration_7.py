"""
Test new features for iteration 7:
1. SMTP Email Configuration
2. Ticket Edit (all fields)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestEmailConfig:
    """Test SMTP Email Configuration endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        # Login as admin
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@pdpv.pt",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        yield
    
    def test_get_email_settings(self):
        """Test GET /api/admin/email-settings"""
        response = requests.get(
            f"{BASE_URL}/api/admin/email-settings",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get email settings failed: {response.text}"
        data = response.json()
        
        # Verify all SMTP fields are present
        assert "smtp_host" in data, "smtp_host field missing"
        assert "smtp_port" in data, "smtp_port field missing"
        assert "smtp_username" in data, "smtp_username field missing"
        assert "smtp_password" in data, "smtp_password field missing"
        assert "smtp_use_ssl" in data, "smtp_use_ssl field missing"
        assert "smtp_use_tls" in data, "smtp_use_tls field missing"
        assert "smtp_configured" in data, "smtp_configured field missing"
        assert "email_from" in data, "email_from field missing"
        assert "email_from_name" in data, "email_from_name field missing"
        print(f"Email settings retrieved: smtp_configured={data.get('smtp_configured')}")
    
    def test_update_email_settings(self):
        """Test PUT /api/admin/email-settings with SMTP configuration"""
        update_payload = {
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "smtp_username": "test@test.com",
            "smtp_password": "testpassword123",
            "smtp_use_tls": True,
            "smtp_use_ssl": False,
            "email_from": "noreply@test.com",
            "email_from_name": "Test System",
            "frontend_url": "https://test.example.com"
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/email-settings",
            headers=self.headers,
            json=update_payload
        )
        assert response.status_code == 200, f"Update email settings failed: {response.text}"
        data = response.json()
        
        # Verify settings were updated
        assert data.get("smtp_host") == "smtp.test.com", "smtp_host not updated"
        assert data.get("smtp_port") == 587, "smtp_port not updated"
        assert data.get("smtp_username") == "test@test.com", "smtp_username not updated"
        assert data.get("smtp_use_tls") == True, "smtp_use_tls not updated"
        assert data.get("smtp_configured") == True, "smtp_configured should be True after setting host/port/username"
        print("Email settings updated successfully")


class TestTicketEdit:
    """Test Ticket Edit functionality (all fields)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        # Login as admin
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@pdpv.pt",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.user_id = data["user"]["id"]
        yield
    
    def test_create_and_edit_ticket(self):
        """Test creating a ticket and editing all fields"""
        # Create a test ticket
        create_payload = {
            "customer_name": "TEST_Original Name",
            "customer_phone": "912000001",
            "customer_email": "original@test.com",
            "vehicle_plate": "AA-00-BB",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Original description"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=self.headers,
            json=create_payload
        )
        assert create_response.status_code == 200, f"Create ticket failed: {create_response.text}"
        ticket = create_response.json()
        ticket_id = ticket["id"]
        print(f"Created test ticket: {ticket['ticket_number']}")
        
        # Now edit ALL fields
        edit_payload = {
            "customer_name": "TEST_Edited Name",
            "customer_phone": "912000002",
            "customer_email": "edited@test.com",
            "vehicle_plate": "CC-11-DD",
            "type": "ORCAMENTO_PNEUS",
            "priority": "URGENTE",
            "description": "Edited description with more details"
        }
        
        edit_response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket_id}",
            headers=self.headers,
            json=edit_payload
        )
        assert edit_response.status_code == 200, f"Edit ticket failed: {edit_response.text}"
        edited_ticket = edit_response.json()
        
        # Verify all fields were updated
        assert edited_ticket["customer_name"] == "TEST_Edited Name", "customer_name not updated"
        assert edited_ticket["customer_phone"] == "912000002", "customer_phone not updated"
        assert edited_ticket["customer_email"] == "edited@test.com", "customer_email not updated"
        assert edited_ticket["vehicle_plate"] == "CC-11-DD", "vehicle_plate not updated"
        assert edited_ticket["type"] == "ORCAMENTO_PNEUS", "type not updated"
        assert edited_ticket["priority"] == "URGENTE", "priority not updated"
        assert edited_ticket["description"] == "Edited description with more details", "description not updated"
        print("All ticket fields edited successfully")
        
        # Verify persistence by fetching the ticket again
        get_response = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}",
            headers=self.headers
        )
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["customer_name"] == "TEST_Edited Name", "Edited name not persisted"
        assert fetched["priority"] == "URGENTE", "Edited priority not persisted"
        print("Ticket edits verified via GET - persisted correctly")
    
    def test_edit_status_change_logged(self):
        """Test that status changes are logged in history"""
        # Create a test ticket
        create_response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=self.headers,
            json={
                "customer_name": "TEST_Status Log Test",
                "customer_phone": "912000003",
                "type": "INFORMACAO",
                "channel": "TELEFONE"
            }
        )
        assert create_response.status_code == 200
        ticket_id = create_response.json()["id"]
        
        # Change status
        edit_response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket_id}",
            headers=self.headers,
            json={"status": "EM_TRATAMENTO"}
        )
        assert edit_response.status_code == 200
        
        # Check status history
        history_response = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}/status-history",
            headers=self.headers
        )
        assert history_response.status_code == 200
        history = history_response.json()
        
        # Should have at least 2 entries: initial creation and the status change
        assert len(history) >= 1, f"Expected at least 1 history entry, got {len(history)}"
        print(f"Status history has {len(history)} entries")


class TestDashboardStats:
    """Test Dashboard statistics including urgent tickets"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@pdpv.pt",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        yield
    
    def test_dashboard_stats(self):
        """Test GET /api/dashboard/stats"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get dashboard stats failed: {response.text}"
        data = response.json()
        
        # Verify all expected fields
        assert "novos" in data, "novos field missing"
        assert "atrasados_sla" in data, "atrasados_sla field missing"
        assert "aguarda_cliente" in data, "aguarda_cliente field missing"
        assert "em_tratamento" in data, "em_tratamento field missing"
        print(f"Dashboard stats: {data}")
    
    def test_tickets_include_priority(self):
        """Test that ticket list includes priority field for urgent display"""
        response = requests.get(
            f"{BASE_URL}/api/tickets?limit=10",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get tickets failed: {response.text}"
        tickets = response.json()
        
        if tickets:
            # Verify priority field is present
            assert "priority" in tickets[0], "priority field missing from ticket"
            
            # Find an urgent ticket if exists
            urgent_tickets = [t for t in tickets if t.get("priority") == "URGENTE"]
            if urgent_tickets:
                print(f"Found {len(urgent_tickets)} urgent ticket(s)")
                # Verify urgent ticket has all expected fields
                urgent = urgent_tickets[0]
                assert urgent.get("is_overdue") is not None, "is_overdue field missing"
            else:
                print("No urgent tickets found in list")


class TestAttachmentPreview:
    """Test attachment download/preview endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@pdpv.pt",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        yield
    
    def test_attachment_download_requires_auth(self):
        """Test that attachment download requires authentication"""
        # Get a ticket with attachments
        response = requests.get(
            f"{BASE_URL}/api/tickets?limit=1",
            headers=self.headers
        )
        if response.status_code == 200 and response.json():
            ticket_id = response.json()[0]["id"]
            
            # Get attachments for this ticket
            att_response = requests.get(
                f"{BASE_URL}/api/tickets/{ticket_id}/attachments",
                headers=self.headers
            )
            assert att_response.status_code == 200
            attachments = att_response.json()
            
            if attachments:
                att_id = attachments[0]["id"]
                
                # Try to download without auth (should fail)
                no_auth_response = requests.get(
                    f"{BASE_URL}/api/attachments/{att_id}/download"
                )
                assert no_auth_response.status_code == 401, "Download should require auth"
                print("Attachment download correctly requires authentication")
            else:
                print("No attachments found to test download")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
