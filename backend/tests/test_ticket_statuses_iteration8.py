"""
Test Ticket Status Feature - Iteration 8
Tests for:
1. API /api/ticket-statuses returns all statuses with is_auto flag
2. ACEITE_LINK and REJEITADO_LINK have is_auto: true
3. ABERTO, EM_TRATAMENTO, AGUARDA_CLIENTE, AGENDADO, FECHADO have is_auto: false
4. When client responds ACCEPTED, ticket changes to ACEITE_LINK
5. When client responds REJECTED, ticket changes to REJEITADO_LINK
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")


@pytest.fixture
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Admin authentication failed")


@pytest.fixture
def auth_headers(admin_token):
    """Get authentication headers"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestTicketStatusesAPI:
    """Tests for /api/ticket-statuses endpoint"""
    
    def test_get_ticket_statuses_returns_all_statuses(self, auth_headers):
        """Test that API returns all ticket statuses with required fields"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json()
        
        # Should have at least 7 statuses
        assert len(statuses) >= 7, f"Expected at least 7 statuses, got {len(statuses)}"
        
        # Check all status codes exist
        status_codes = [s["code"] for s in statuses]
        required_codes = ["ABERTO", "EM_TRATAMENTO", "AGUARDA_CLIENTE", "ACEITE_LINK", "REJEITADO_LINK", "AGENDADO", "FECHADO"]
        for code in required_codes:
            assert code in status_codes, f"Missing status code: {code}"
    
    def test_statuses_have_is_auto_flag(self, auth_headers):
        """Test that all statuses have is_auto flag"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json()
        
        for status in statuses:
            assert "is_auto" in status, f"Status {status.get('code')} missing is_auto flag"
            assert isinstance(status["is_auto"], bool), f"is_auto should be boolean for {status.get('code')}"
    
    def test_aceite_link_has_is_auto_true(self, auth_headers):
        """Test ACEITE_LINK has is_auto: true"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json()
        
        aceite_status = next((s for s in statuses if s["code"] == "ACEITE_LINK"), None)
        assert aceite_status is not None, "ACEITE_LINK status not found"
        assert aceite_status["is_auto"] is True, "ACEITE_LINK should have is_auto: true"
    
    def test_rejeitado_link_has_is_auto_true(self, auth_headers):
        """Test REJEITADO_LINK has is_auto: true"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json()
        
        rejeitado_status = next((s for s in statuses if s["code"] == "REJEITADO_LINK"), None)
        assert rejeitado_status is not None, "REJEITADO_LINK status not found"
        assert rejeitado_status["is_auto"] == True, "REJEITADO_LINK should have is_auto: true"
    
    def test_manual_statuses_have_is_auto_false(self, auth_headers):
        """Test ABERTO, EM_TRATAMENTO, AGUARDA_CLIENTE, AGENDADO, FECHADO have is_auto: false"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json()
        
        manual_codes = ["ABERTO", "EM_TRATAMENTO", "AGUARDA_CLIENTE", "AGENDADO", "FECHADO"]
        
        for code in manual_codes:
            status = next((s for s in statuses if s["code"] == code), None)
            assert status is not None, f"{code} status not found"
            assert status["is_auto"] == False, f"{code} should have is_auto: false, got {status['is_auto']}"
    
    def test_agendado_status_exists_with_correct_label(self, auth_headers):
        """Test AGENDADO status exists with correct label"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json()
        
        agendado_status = next((s for s in statuses if s["code"] == "AGENDADO"), None)
        assert agendado_status is not None, "AGENDADO status not found"
        assert agendado_status["label"] == "Agendado", f"AGENDADO label incorrect: {agendado_status['label']}"
        assert agendado_status["is_auto"] == False, "AGENDADO should be manual (is_auto: false)"


class TestQuoteLinkResponse:
    """Tests for quote link acceptance/rejection changing status"""
    
    def test_create_ticket_generate_link_and_accept(self, auth_headers):
        """Test full flow: create ticket -> set quote value -> generate link -> client accepts -> status changes to ACEITE_LINK"""
        # Step 1: Create ticket
        ticket_data = {
            "customer_name": "TEST_Client_Accept",
            "customer_phone": "910000001",
            "customer_email": "test_accept@example.com",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "description": "Test ticket for quote acceptance"
        }
        create_response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=auth_headers)
        assert create_response.status_code == 200, f"Failed to create ticket: {create_response.text}"
        ticket = create_response.json()
        ticket_id = ticket["id"]
        
        try:
            # Step 2: Set quote value
            update_response = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"quote_value": 150.00},
                headers=auth_headers
            )
            assert update_response.status_code == 200, f"Failed to set quote value: {update_response.text}"
            
            # Step 3: Generate quote link
            link_response = requests.post(
                f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
                json={},
                headers=auth_headers
            )
            assert link_response.status_code == 200, f"Failed to generate link: {link_response.text}"
            quote_link = link_response.json()
            token = quote_link["token"]
            
            # Step 4: Client accepts via public endpoint (NO AUTH)
            accept_response = requests.post(
                f"{BASE_URL}/api/public/quote/{token}/respond",
                json={"status": "ACCEPTED", "comments": "Aceito o orçamento"},
                headers={"Content-Type": "application/json"}  # No auth header
            )
            assert accept_response.status_code == 200, f"Failed to accept: {accept_response.text}"
            
            # Step 5: Verify ticket status changed to ACEITE_LINK
            get_response = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
            assert get_response.status_code == 200
            updated_ticket = get_response.json()
            assert updated_ticket["status"] == "ACEITE_LINK", f"Expected status ACEITE_LINK, got {updated_ticket['status']}"
            assert updated_ticket["quote_response_status"] == "ACCEPTED", f"Expected quote_response_status ACCEPTED"
        
        finally:
            # Cleanup - archive the ticket
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=auth_headers)
    
    def test_create_ticket_generate_link_and_reject(self, auth_headers):
        """Test full flow: create ticket -> set quote value -> generate link -> client rejects -> status changes to REJEITADO_LINK"""
        # Step 1: Create ticket
        ticket_data = {
            "customer_name": "TEST_Client_Reject",
            "customer_phone": "910000002",
            "customer_email": "test_reject@example.com",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "description": "Test ticket for quote rejection"
        }
        create_response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=auth_headers)
        assert create_response.status_code == 200, f"Failed to create ticket: {create_response.text}"
        ticket = create_response.json()
        ticket_id = ticket["id"]
        
        try:
            # Step 2: Set quote value
            update_response = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"quote_value": 250.00},
                headers=auth_headers
            )
            assert update_response.status_code == 200
            
            # Step 3: Generate quote link
            link_response = requests.post(
                f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
                json={},
                headers=auth_headers
            )
            assert link_response.status_code == 200
            quote_link = link_response.json()
            token = quote_link["token"]
            
            # Step 4: Client rejects via public endpoint (NO AUTH)
            reject_response = requests.post(
                f"{BASE_URL}/api/public/quote/{token}/respond",
                json={"status": "REJECTED", "comments": "Muito caro"},
                headers={"Content-Type": "application/json"}  # No auth header
            )
            assert reject_response.status_code == 200, f"Failed to reject: {reject_response.text}"
            
            # Step 5: Verify ticket status changed to REJEITADO_LINK
            get_response = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
            assert get_response.status_code == 200
            updated_ticket = get_response.json()
            assert updated_ticket["status"] == "REJEITADO_LINK", f"Expected status REJEITADO_LINK, got {updated_ticket['status']}"
            assert updated_ticket["quote_response_status"] == "REJECTED", f"Expected quote_response_status REJECTED"
        
        finally:
            # Cleanup
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=auth_headers)
    
    def test_public_quote_endpoint_requires_no_auth(self, auth_headers):
        """Test that public quote view endpoint works without authentication"""
        # Create ticket and generate link
        ticket_data = {
            "customer_name": "TEST_Public_Access",
            "customer_phone": "910000003",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "description": "Test public access"
        }
        create_response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=auth_headers)
        assert create_response.status_code == 200
        ticket_id = create_response.json()["id"]
        
        try:
            # Set quote value
            requests.put(f"{BASE_URL}/api/tickets/{ticket_id}", json={"quote_value": 100.00}, headers=auth_headers)
            
            # Generate link
            link_response = requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link", json={}, headers=auth_headers)
            assert link_response.status_code == 200
            token = link_response.json()["token"]
            
            # Access public quote view WITHOUT authentication
            public_response = requests.get(f"{BASE_URL}/api/public/quote/{token}")
            assert public_response.status_code == 200, f"Public quote view should work without auth: {public_response.text}"
            quote_data = public_response.json()
            assert "quote_value" in quote_data
            assert quote_data["quote_value"] == 100.00
        
        finally:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=auth_headers)


class TestStatusChangeValidation:
    """Tests to verify manual status changes still work"""
    
    def test_can_change_status_to_agendado_manually(self, auth_headers):
        """Test that AGENDADO can be selected manually"""
        # Create ticket
        ticket_data = {
            "customer_name": "TEST_Manual_Agendado",
            "customer_phone": "910000004",
            "type": "MARCACAO",
            "channel": "TELEFONE",
            "description": "Test manual AGENDADO status"
        }
        create_response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=auth_headers)
        assert create_response.status_code == 200
        ticket_id = create_response.json()["id"]
        
        try:
            # Change status to AGENDADO
            update_response = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"status": "AGENDADO"},
                headers=auth_headers
            )
            assert update_response.status_code == 200, f"Failed to change status to AGENDADO: {update_response.text}"
            
            # Verify status changed
            get_response = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
            assert get_response.status_code == 200
            assert get_response.json()["status"] == "AGENDADO"
        
        finally:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=auth_headers)
    
    def test_can_change_status_through_all_manual_options(self, auth_headers):
        """Test that all manual statuses can be selected"""
        # Create ticket
        ticket_data = {
            "customer_name": "TEST_All_Manual_Statuses",
            "customer_phone": "910000005",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "description": "Test all manual statuses"
        }
        create_response = requests.post(f"{BASE_URL}/api/tickets", json=ticket_data, headers=auth_headers)
        assert create_response.status_code == 200
        ticket_id = create_response.json()["id"]
        
        manual_statuses = ["EM_TRATAMENTO", "AGUARDA_CLIENTE", "AGENDADO", "FECHADO"]
        
        try:
            for status in manual_statuses:
                update_response = requests.put(
                    f"{BASE_URL}/api/tickets/{ticket_id}",
                    json={"status": status},
                    headers=auth_headers
                )
                assert update_response.status_code == 200, f"Failed to change to {status}: {update_response.text}"
                
                # Verify
                get_response = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
                assert get_response.status_code == 200
                assert get_response.json()["status"] == status, f"Status should be {status}"
        
        finally:
            requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/archive", headers=auth_headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
