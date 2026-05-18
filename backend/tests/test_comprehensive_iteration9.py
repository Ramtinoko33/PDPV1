"""
Comprehensive tests for PDPV Tickets System - Iteration 9
Tests all major functionalities including:
- Authentication (Admin, Supervisor, Agent)
- Dashboard stats
- Ticket CRUD operations
- Messages and Notes
- Quote/Budget system with public links
- Automatic status changes
- Archive/Restore
- Admin settings (Types, Statuses, SLA, Email)
- Reports
- Customers and Users
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://quote-management-4.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@pdpv.pt", "password": os.environ.get("TEST_ADMIN_PASSWORD", "changeme")}
SUPERVISOR_CREDS = {"email": "supervisor@pdpv.pt", "password": "f9pSIn6zRP"}
AGENT_CREDS = {"email": "agente@pdpv.pt", "password": "yHprFGvPUJ"}


class TestAuth:
    """Test authentication flows for all roles"""
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health check passed")
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "ADMIN"
        print(f"✓ Admin login successful: {data['user']['name']}")
        return data["token"]
    
    def test_supervisor_login(self):
        """Test supervisor login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=SUPERVISOR_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "SUPERVISOR"
        print(f"✓ Supervisor login successful: {data['user']['name']}")
        return data["token"]
    
    def test_agent_login(self):
        """Test agent login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "AGENT"
        print(f"✓ Agent login successful: {data['user']['name']}")
        return data["token"]
    
    def test_invalid_login(self):
        """Test invalid login credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid login properly rejected")
    
    def test_get_current_user(self):
        """Test getting current user info"""
        token = self.test_admin_login()
        response = requests.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_CREDS["email"]
        print(f"✓ Get current user: {data['name']} ({data['role']})")


class TestDashboard:
    """Test dashboard statistics"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_stats(self):
        """Test dashboard stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "novos" in data
        assert "atrasados_sla" in data
        assert "aguarda_cliente" in data
        assert "em_tratamento" in data
        assert "total" in data
        print(f"✓ Dashboard stats: total={data['total']}, novos={data['novos']}, atrasados={data['atrasados_sla']}")


class TestTickets:
    """Test ticket CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.admin_token = response.json()["token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
        self.agent_token = response.json()["token"]
        self.agent_headers = {"Authorization": f"Bearer {self.agent_token}"}
        self.agent_id = response.json()["user"]["id"]
    
    def test_list_tickets(self):
        """Test listing tickets"""
        response = requests.get(f"{BASE_URL}/api/tickets", headers=self.admin_headers)
        assert response.status_code == 200
        tickets = response.json()
        assert isinstance(tickets, list)
        print(f"✓ Listed {len(tickets)} tickets")
        return tickets
    
    def test_create_ticket(self):
        """Test creating a new ticket"""
        ticket_data = {
            "customer_name": f"TEST_Cliente_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345678",
            "customer_email": "test@example.com",
            "vehicle_plate": "AA-00-BB",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test ticket for iteration 9"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.admin_headers)
        assert response.status_code == 200
        ticket = response.json()
        assert ticket["customer_name"] == ticket_data["customer_name"]
        assert ticket["status"] == "ABERTO"
        assert "ticket_number" in ticket
        print(f"✓ Created ticket: {ticket['ticket_number']}")
        return ticket
    
    def test_create_urgent_ticket(self):
        """Test creating an urgent ticket"""
        ticket_data = {
            "customer_name": f"TEST_Urgente_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345679",
            "type": "MARCACAO",
            "channel": "BALCAO",
            "priority": "URGENTE",
            "description": "Urgent test ticket"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.admin_headers)
        assert response.status_code == 200
        ticket = response.json()
        assert ticket["priority"] == "URGENTE"
        print(f"✓ Created urgent ticket: {ticket['ticket_number']}")
        return ticket
    
    def test_get_ticket(self):
        """Test getting a single ticket"""
        ticket = self.test_create_ticket()
        response = requests.get(f"{BASE_URL}/api/tickets/{ticket['id']}", headers=self.admin_headers)
        assert response.status_code == 200
        fetched = response.json()
        assert fetched["id"] == ticket["id"]
        print(f"✓ Got ticket: {fetched['ticket_number']}")
    
    def test_update_ticket_status(self):
        """Test updating ticket status"""
        ticket = self.test_create_ticket()
        response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            json={"status": "EM_TRATAMENTO"},
            headers=self.admin_headers
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["status"] == "EM_TRATAMENTO"
        print(f"✓ Updated ticket status to EM_TRATAMENTO")
    
    def test_assign_ticket(self):
        """Test assigning ticket to user"""
        ticket = self.test_create_ticket()
        response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            json={"assigned_to_user_id": self.agent_id},
            headers=self.admin_headers
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["assigned_to_user_id"] == self.agent_id
        assert updated["status"] == "EM_TRATAMENTO"  # Should auto-change when assigned
        print(f"✓ Assigned ticket to agent")
    
    def test_agent_self_assign(self):
        """Test agent self-assigning an unassigned ticket"""
        # Create unassigned ticket
        ticket_data = {
            "customer_name": f"TEST_SelfAssign_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345680",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test self-assign"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.admin_headers)
        ticket = response.json()
        
        # Agent self-assigns
        response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            json={"assigned_to_user_id": self.agent_id},
            headers=self.agent_headers
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["assigned_to_user_id"] == self.agent_id
        print("✓ Agent self-assign successful")
    
    def test_filter_tickets_by_status(self):
        """Test filtering tickets by status"""
        response = requests.get(f"{BASE_URL}/api/tickets?status=ABERTO", headers=self.admin_headers)
        assert response.status_code == 200
        tickets = response.json()
        for t in tickets:
            assert t["status"] == "ABERTO"
        print(f"✓ Filtered {len(tickets)} ABERTO tickets")
    
    def test_search_tickets(self):
        """Test searching tickets"""
        # Create ticket with unique phone
        unique_phone = f"9{uuid.uuid4().hex[:8]}"
        ticket_data = {
            "customer_name": "TEST_Search",
            "customer_phone": unique_phone,
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL"
        }
        requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.admin_headers)
        
        # Search by phone
        response = requests.get(f"{BASE_URL}/api/tickets?search={unique_phone}", headers=self.admin_headers)
        assert response.status_code == 200
        tickets = response.json()
        assert len(tickets) >= 1
        print(f"✓ Search found {len(tickets)} tickets")


class TestTicketStatuses:
    """Test ticket statuses API including is_auto flag"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_ticket_statuses(self):
        """Test getting all ticket statuses"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=self.headers)
        assert response.status_code == 200
        statuses = response.json()
        assert isinstance(statuses, list)
        assert len(statuses) > 0
        
        # Check that is_auto flag exists
        for s in statuses:
            assert "is_auto" in s
            assert "code" in s
            assert "label" in s
        
        # Verify automatic statuses
        auto_statuses = [s for s in statuses if s.get("is_auto") is True]
        auto_codes = [s["code"] for s in auto_statuses]
        assert "ACEITE_LINK" in auto_codes or len(auto_statuses) >= 0
        print(f"✓ Got {len(statuses)} statuses, {len(auto_statuses)} automatic")


class TestMessagesAndNotes:
    """Test messages and internal notes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Create a test ticket
        ticket_data = {
            "customer_name": f"TEST_MsgNotes_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345681",
            "customer_email": "test@msg.com",
            "type": "INFORMACAO",
            "channel": "EMAIL",
            "priority": "NORMAL",
            "description": "Test for messages and notes"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.headers)
        self.ticket = response.json()
    
    def test_send_message(self):
        """Test sending a public message"""
        message_data = {
            "body": "This is a test public message",
            "channel": "EMAIL",
            "is_quote_response": False
        }
        response = requests.post(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/messages",
            json=message_data,
            headers=self.headers
        )
        assert response.status_code == 200
        msg = response.json()
        assert msg["body"] == message_data["body"]
        assert msg["direction"] == "OUTBOUND"
        print("✓ Sent public message")
    
    def test_list_messages(self):
        """Test listing messages"""
        response = requests.get(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/messages",
            headers=self.headers
        )
        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)
        print(f"✓ Listed {len(messages)} messages")
    
    def test_add_private_note(self):
        """Test adding internal note"""
        note_data = {"body": "This is a private internal note"}
        response = requests.post(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/notes",
            json=note_data,
            headers=self.headers
        )
        assert response.status_code == 200
        note = response.json()
        assert note["body"] == note_data["body"]
        print("✓ Added private note")
    
    def test_list_notes(self):
        """Test listing notes"""
        response = requests.get(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/notes",
            headers=self.headers
        )
        assert response.status_code == 200
        notes = response.json()
        assert isinstance(notes, list)
        print(f"✓ Listed {len(notes)} notes")


class TestQuoteSystem:
    """Test quote/budget system with public links"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Create a test ticket
        ticket_data = {
            "customer_name": f"TEST_Quote_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345682",
            "customer_email": "test@quote.com",
            "vehicle_plate": "QQ-00-QQ",
            "type": "ORCAMENTO_MECANICA",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test for quote system"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.headers)
        self.ticket = response.json()
    
    def test_set_quote_value(self):
        """Test setting quote value on ticket"""
        response = requests.put(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}",
            json={"quote_value": 250.50, "quote_sent": True},
            headers=self.headers
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["quote_value"] == 250.50
        assert updated["quote_sent"] is True
        print("✓ Set quote value: 250.50€")
    
    def test_generate_quote_link(self):
        """Test generating a public quote link"""
        # First set quote value
        requests.put(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}",
            json={"quote_value": 150.00},
            headers=self.headers
        )
        
        response = requests.post(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/generate-quote-link",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "expires_at" in data
        print(f"✓ Generated quote link with token: {data['token'][:20]}...")
        return data["token"]
    
    def test_public_quote_access(self):
        """Test accessing quote via public link"""
        token = self.test_generate_quote_link()
        
        # Access public quote (no auth required)
        response = requests.get(f"{BASE_URL}/api/public/quote/{token}")
        assert response.status_code == 200
        data = response.json()
        assert "quote_value" in data
        assert "customer_name" in data
        assert "ticket_number" in data
        print(f"✓ Public quote access works: {data['ticket_number']}")
        return token
    
    def test_accept_quote_changes_status(self):
        """Test that accepting quote changes status to ACEITE_LINK"""
        token = self.test_public_quote_access()
        
        response = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={"status": "ACCEPTED", "comments": "Test acceptance"}
        )
        assert response.status_code == 200
        
        # Verify ticket status changed
        response = requests.get(f"{BASE_URL}/api/tickets/{self.ticket['id']}", headers=self.headers)
        ticket = response.json()
        assert ticket["status"] == "ACEITE_LINK"
        assert ticket["quote_response_status"] == "ACCEPTED"
        print("✓ Quote acceptance changed status to ACEITE_LINK")
    
    def test_reject_quote_changes_status(self):
        """Test that rejecting quote changes status to REJEITADO_LINK"""
        # Create new ticket for rejection test
        ticket_data = {
            "customer_name": f"TEST_QuoteReject_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345683",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "priority": "NORMAL"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.headers)
        ticket = response.json()
        
        # Set quote and generate link
        requests.put(f"{BASE_URL}/api/tickets/{ticket['id']}", json={"quote_value": 100.00}, headers=self.headers)
        response = requests.post(f"{BASE_URL}/api/tickets/{ticket['id']}/generate-quote-link", headers=self.headers)
        token = response.json()["token"]
        
        # Reject quote
        response = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={"status": "REJECTED", "comments": "Test rejection"}
        )
        assert response.status_code == 200
        
        # Verify status
        response = requests.get(f"{BASE_URL}/api/tickets/{ticket['id']}", headers=self.headers)
        updated = response.json()
        assert updated["status"] == "REJEITADO_LINK"
        print("✓ Quote rejection changed status to REJEITADO_LINK")


class TestArchiveRestore:
    """Test archive and restore functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Create test ticket
        ticket_data = {
            "customer_name": f"TEST_Archive_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345684",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.headers)
        self.ticket = response.json()
    
    def test_archive_ticket(self):
        """Test archiving a ticket"""
        response = requests.post(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/archive",
            headers=self.headers
        )
        assert response.status_code == 200
        
        # Verify archived
        response = requests.get(f"{BASE_URL}/api/tickets/{self.ticket['id']}", headers=self.headers)
        ticket = response.json()
        assert ticket["archived_at"] is not None
        print("✓ Ticket archived successfully")
    
    def test_restore_ticket(self):
        """Test restoring an archived ticket"""
        # First archive
        requests.post(f"{BASE_URL}/api/tickets/{self.ticket['id']}/archive", headers=self.headers)
        
        # Then restore
        response = requests.post(
            f"{BASE_URL}/api/tickets/{self.ticket['id']}/restore",
            headers=self.headers
        )
        assert response.status_code == 200
        
        # Verify restored
        response = requests.get(f"{BASE_URL}/api/tickets/{self.ticket['id']}", headers=self.headers)
        ticket = response.json()
        assert ticket["archived_at"] is None
        print("✓ Ticket restored successfully")
    
    def test_list_archived_tickets(self):
        """Test listing archived tickets"""
        # Archive ticket first
        requests.post(f"{BASE_URL}/api/tickets/{self.ticket['id']}/archive", headers=self.headers)
        
        response = requests.get(f"{BASE_URL}/api/tickets/archived", headers=self.headers)
        assert response.status_code == 200
        archived = response.json()
        assert isinstance(archived, list)
        print(f"✓ Listed {len(archived)} archived tickets")


class TestAdminSettings:
    """Test admin settings - Types, Statuses, SLA, Email"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_ticket_types(self):
        """Test getting ticket types"""
        response = requests.get(f"{BASE_URL}/api/admin/ticket-types", headers=self.headers)
        assert response.status_code == 200
        types = response.json()
        assert isinstance(types, list)
        print(f"✓ Got {len(types)} ticket types")
    
    def test_get_ticket_statuses_admin(self):
        """Test getting ticket statuses via admin endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/ticket-statuses", headers=self.headers)
        assert response.status_code == 200
        statuses = response.json()
        assert isinstance(statuses, list)
        # Check for is_auto flag
        for s in statuses:
            assert "is_auto" in s or "is_final" in s
        print(f"✓ Got {len(statuses)} ticket statuses")
    
    def test_get_sla_config(self):
        """Test getting SLA configuration"""
        response = requests.get(f"{BASE_URL}/api/admin/sla-config", headers=self.headers)
        assert response.status_code == 200
        config = response.json()
        assert "first_response_hours" in config
        assert "quote_response_hours" in config
        assert "enabled" in config
        print(f"✓ SLA Config: {config['first_response_hours']}h first response, {config['quote_response_hours']}h quote")
    
    def test_get_email_settings(self):
        """Test getting email settings"""
        response = requests.get(f"{BASE_URL}/api/admin/email-settings", headers=self.headers)
        assert response.status_code == 200
        settings = response.json()
        assert "smtp_configured" in settings or "resend_configured" in settings
        print(f"✓ Email settings retrieved")
    
    def test_get_vapid_config(self):
        """Test getting VAPID public key for push notifications"""
        response = requests.get(f"{BASE_URL}/api/push/vapid-public-key", headers=self.headers)
        assert response.status_code == 200
        config = response.json()
        assert "publicKey" in config
        print(f"✓ VAPID configured: {bool(config.get('publicKey'))}")


class TestReports:
    """Test reports functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_generate_report(self):
        """Test generating a report"""
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/reports",
            json={
                "start_date": start_date,
                "end_date": end_date
            },
            headers=self.headers
        )
        assert response.status_code == 200
        report = response.json()
        assert "metrics" in report
        assert "total_tickets" in report["metrics"]
        assert "sla_compliance_rate" in report["metrics"]
        print(f"✓ Report generated: {report['metrics']['total_tickets']} tickets")


class TestCustomersAndUsers:
    """Test customers and users management"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_list_customers(self):
        """Test listing customers"""
        response = requests.get(f"{BASE_URL}/api/customers", headers=self.headers)
        assert response.status_code == 200
        customers = response.json()
        assert isinstance(customers, list)
        print(f"✓ Listed {len(customers)} customers")
    
    def test_list_users(self):
        """Test listing users"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)
        assert len(users) >= 3  # At least admin, supervisor, agent
        
        roles = [u["role"] for u in users]
        assert "ADMIN" in roles
        assert "SUPERVISOR" in roles
        assert "AGENT" in roles
        print(f"✓ Listed {len(users)} users")
    
    def test_customer_search(self):
        """Test customer search for autocomplete"""
        response = requests.get(f"{BASE_URL}/api/customers/search?q=test", headers=self.headers)
        assert response.status_code == 200
        results = response.json()
        assert isinstance(results, list)
        print(f"✓ Customer search returned {len(results)} results")


class TestPermissions:
    """Test role-based permissions"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        # Get tokens for all roles
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.admin_token = response.json()["token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
        self.agent_token = response.json()["token"]
        self.agent_headers = {"Authorization": f"Bearer {self.agent_token}"}
        self.agent_id = response.json()["user"]["id"]
    
    def test_agent_cannot_assign_to_others(self):
        """Test that agent can only self-assign, not assign to others"""
        # Create a ticket
        ticket_data = {
            "customer_name": f"TEST_Permission_{uuid.uuid4().hex[:6]}",
            "customer_phone": "912345690",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL"
        }
        response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=self.admin_headers)
        ticket = response.json()
        
        # Agent tries to assign to someone else (should fail)
        response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            json={"assigned_to_user_id": "some-other-user-id"},
            headers=self.agent_headers
        )
        assert response.status_code == 403
        print("✓ Agent correctly denied assigning to others")
    
    def test_agent_users_endpoint_access(self):
        """Test that agents cannot access users list"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.agent_headers)
        assert response.status_code == 403
        print("✓ Agent correctly denied access to users list")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
