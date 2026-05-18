import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
AGENT_EMAIL = "agente@pdpv.pt"
AGENT_PASSWORD = "yHprFGvPUJ"

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def agent_token():
    """Get agent authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASSWORD
    })
    assert response.status_code == 200, f"Agent login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

@pytest.fixture
def agent_headers(agent_token):
    return {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}

class TestStatusBugFixes:
    """Test the 3 bug fixes: ACEITE_LINK display, auto EM_TRATAMENTO, and quote link generation"""
    
    def test_aceite_link_status_exists_and_is_auto(self, admin_headers):
        """Bug 1: Verify ACEITE_LINK status is in the system with is_auto=true"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=admin_headers)
        assert response.status_code == 200, f"Failed to get statuses: {response.text}"
        
        statuses = response.json()
        aceite_link = next((s for s in statuses if s["code"] == "ACEITE_LINK"), None)
        
        assert aceite_link is not None, "ACEITE_LINK status not found in system"
        assert aceite_link["is_auto"] == True, "ACEITE_LINK should have is_auto=true"
        assert aceite_link["label"] == "Aceite (Link)", f"ACEITE_LINK label incorrect: {aceite_link['label']}"
    
    def test_rejeitado_link_status_exists_and_is_auto(self, admin_headers):
        """Verify REJEITADO_LINK status is in the system with is_auto=true"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=admin_headers)
        assert response.status_code == 200
        
        statuses = response.json()
        rejeitado_link = next((s for s in statuses if s["code"] == "REJEITADO_LINK"), None)
        
        assert rejeitado_link is not None, "REJEITADO_LINK status not found in system"
        assert rejeitado_link["is_auto"] == True, "REJEITADO_LINK should have is_auto=true"
    
    def test_ticket_with_aceite_link_status_returns_correctly(self, admin_headers):
        """Bug 1: Verify ticket with ACEITE_LINK status returns the status correctly in API"""
        ticket_id = "45f94275-0164-40db-b3cc-6c658bf0cd70"  # Test ticket with ACEITE_LINK
        response = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_headers)
        
        assert response.status_code == 200, f"Failed to get ticket: {response.text}"
        ticket = response.json()
        assert ticket["status"] == "ACEITE_LINK", f"Expected ACEITE_LINK but got {ticket['status']}"
    
    def test_auto_status_change_on_assignment(self, admin_headers):
        """Bug 3: When ticket is assigned, status should auto-change from ABERTO to EM_TRATAMENTO"""
        # Create a new ticket without assignment
        ticket_data = {
            "customer_name": f"TEST_AutoStatus_{uuid.uuid4().hex[:6]}",
            "customer_phone": "919888777",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "description": "Testing auto status change on assignment"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tickets", headers=admin_headers, json=ticket_data)
        assert create_response.status_code == 200, f"Failed to create ticket: {create_response.text}"
        
        ticket = create_response.json()
        ticket_id = ticket["id"]
        
        # Verify initial status is ABERTO (since not assigned)
        assert ticket["status"] == "ABERTO", f"Expected ABERTO but got {ticket['status']}"
        assert ticket["assigned_to_user_id"] is None, "Ticket should be unassigned"
        
        # Get an agent user ID
        users_response = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        users = users_response.json()
        agent = next((u for u in users if u["role"] == "AGENT"), None)
        assert agent is not None, "No agent user found"
        
        # Assign the ticket to the agent
        update_response = requests.put(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_headers, json={
            "assigned_to_user_id": agent["id"]
        })
        assert update_response.status_code == 200, f"Failed to update ticket: {update_response.text}"
        
        updated_ticket = update_response.json()
        
        # Verify status auto-changed to EM_TRATAMENTO
        assert updated_ticket["status"] == "EM_TRATAMENTO", f"Expected EM_TRATAMENTO but got {updated_ticket['status']}"
        assert updated_ticket["assigned_to_user_id"] == agent["id"], "Ticket should be assigned to agent"
        
        # Clean up - archive the test ticket
        try:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=admin_headers)
        except:
            pass
    
    def test_status_does_not_change_if_not_aberto(self, admin_headers):
        """Verify that assigning a ticket that is NOT in ABERTO status doesn't change its status"""
        # Create a new ticket without assignment (status = ABERTO)
        ticket_data = {
            "customer_name": f"TEST_NoAutoStatus_{uuid.uuid4().hex[:6]}",
            "customer_phone": "919888666",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "description": "Testing no auto status change when not ABERTO"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tickets", headers=admin_headers, json=ticket_data)
        assert create_response.status_code == 200
        ticket = create_response.json()
        ticket_id = ticket["id"]
        
        # First, change status to AGUARDA_CLIENTE (not ABERTO)
        update1 = requests.put(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_headers, json={
            "status": "AGUARDA_CLIENTE"
        })
        assert update1.status_code == 200
        assert update1.json()["status"] == "AGUARDA_CLIENTE"
        
        # Get an agent user ID
        users_response = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        users = users_response.json()
        agent = next((u for u in users if u["role"] == "AGENT"), None)
        
        # Now assign the ticket - status should NOT auto-change
        update2 = requests.put(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_headers, json={
            "assigned_to_user_id": agent["id"]
        })
        assert update2.status_code == 200
        
        # Verify status stayed as AGUARDA_CLIENTE
        assert update2.json()["status"] == "AGUARDA_CLIENTE", f"Status should remain AGUARDA_CLIENTE, got {update2.json()['status']}"
        
        # Clean up
        try:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=admin_headers)
        except:
            pass
    
    def test_quote_link_generation(self, admin_headers):
        """Bug 2: Verify quote link generation works without errors"""
        # Create a ticket with quote value
        ticket_data = {
            "customer_name": f"TEST_QuoteLink_{uuid.uuid4().hex[:6]}",
            "customer_phone": "919777555",
            "customer_email": "test@example.com",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "description": "Testing quote link generation"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tickets", headers=admin_headers, json=ticket_data)
        assert create_response.status_code == 200
        ticket = create_response.json()
        ticket_id = ticket["id"]
        
        # Set quote value
        quote_update = requests.put(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_headers, json={
            "quote_value": 250.50
        })
        assert quote_update.status_code == 200
        
        # Generate quote link
        link_response = requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link", headers=admin_headers)
        assert link_response.status_code == 200, f"Failed to generate quote link: {link_response.text}"
        
        link_data = link_response.json()
        assert "token" in link_data, "Response should contain token"
        assert "expires_at" in link_data, "Response should contain expires_at"
        
        # Clean up
        try:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=admin_headers)
        except:
            pass
    
    def test_all_status_labels_and_colors_exist(self, admin_headers):
        """Verify all statuses have proper labels and colors defined"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=admin_headers)
        assert response.status_code == 200
        
        statuses = response.json()
        expected_statuses = ["ABERTO", "EM_TRATAMENTO", "AGUARDA_CLIENTE", "ACEITE_LINK", "REJEITADO_LINK", "AGENDADO", "FECHADO"]
        
        for expected in expected_statuses:
            status = next((s for s in statuses if s["code"] == expected), None)
            assert status is not None, f"Status {expected} not found"
            assert "label" in status and status["label"], f"Status {expected} missing label"
            assert "color" in status and status["color"], f"Status {expected} missing color"


class TestTicketStatusIntegration:
    """Additional tests for ticket status handling"""
    
    def test_manual_statuses_are_editable(self, admin_headers):
        """Verify manual statuses (is_auto=false) can be changed via update"""
        # Create ticket
        ticket_data = {
            "customer_name": f"TEST_ManualStatus_{uuid.uuid4().hex[:6]}",
            "customer_phone": "919666444",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "description": "Testing manual status changes"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tickets", headers=admin_headers, json=ticket_data)
        assert create_response.status_code == 200
        ticket_id = create_response.json()["id"]
        
        # Test changing to each manual status
        manual_statuses = ["EM_TRATAMENTO", "AGUARDA_CLIENTE", "AGENDADO", "FECHADO"]
        
        for status in manual_statuses:
            update_response = requests.put(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_headers, json={
                "status": status
            })
            assert update_response.status_code == 200, f"Failed to change to {status}: {update_response.text}"
            assert update_response.json()["status"] == status
        
        # Clean up
        try:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=admin_headers)
        except:
            pass
