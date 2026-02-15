"""
Test P1, P2, P4 Features for PDPV Tickets System

P1: Attachments in messages - verify attachments appear in message timeline
P2: Admin Settings - Ticket Types CRUD, Ticket Statuses CRUD, SLA Config
P4: Quote acceptance link generation and public quote response flow
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAdminAuth:
    """Test authentication and get tokens for testing"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Login as admin and return token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def supervisor_token(self):
        """Login as supervisor and return token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "supervisor@pdpv.pt", "password": "super123"}
        )
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_admin_login(self):
        """Test admin can login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "ADMIN"
        print("Admin login - PASSED")


class TestP2AdminTicketTypes:
    """P2: Test Ticket Types CRUD in Admin Settings"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        """Get admin auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def supervisor_headers(self):
        """Get supervisor auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "supervisor@pdpv.pt", "password": "super123"}
        )
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_ticket_types_admin(self, admin_headers):
        """Test admin can get ticket types"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ticket-types",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have default types
        assert len(data) >= 6  # Default types: ORCAMENTO_PNEUS, ORCAMENTO_MECANICA, MARCACAO, INFORMACAO, INTERNO, RECLAMACAO
        print(f"GET Ticket Types - PASSED ({len(data)} types returned)")
    
    def test_get_ticket_types_supervisor_forbidden(self, supervisor_headers):
        """Test supervisor cannot get ticket types (admin only)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ticket-types",
            headers=supervisor_headers
        )
        assert response.status_code == 403
        print("GET Ticket Types as supervisor - PASSED (403 Forbidden)")
    
    def test_create_ticket_type_admin(self, admin_headers):
        """Test admin can create ticket type"""
        unique_code = f"TEST_TYPE_{uuid.uuid4().hex[:6].upper()}"
        response = requests.post(
            f"{BASE_URL}/api/admin/ticket-types",
            headers=admin_headers,
            json={
                "code": unique_code,
                "label": "Test Ticket Type",
                "color": "#ff0000"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == unique_code
        assert data["label"] == "Test Ticket Type"
        assert data["color"] == "#ff0000"
        print(f"CREATE Ticket Type - PASSED (created {unique_code})")
        return data["id"]
    
    def test_update_ticket_type_admin(self, admin_headers):
        """Test admin can update ticket type"""
        # First get types
        get_response = requests.get(
            f"{BASE_URL}/api/admin/ticket-types",
            headers=admin_headers
        )
        types = get_response.json()
        # Find a test type or use first one
        test_type = next((t for t in types if "TEST" in t["code"]), types[0] if types else None)
        
        if test_type:
            response = requests.put(
                f"{BASE_URL}/api/admin/ticket-types/{test_type['id']}",
                headers=admin_headers,
                json={
                    "label": f"{test_type['label']} Updated",
                    "color": "#00ff00"
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["label"].endswith("Updated")
            print(f"UPDATE Ticket Type - PASSED (updated {test_type['code']})")


class TestP2AdminTicketStatuses:
    """P2: Test Ticket Statuses CRUD in Admin Settings"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        """Get admin auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_ticket_statuses_admin(self, admin_headers):
        """Test admin can get ticket statuses"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ticket-statuses",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have default statuses
        assert len(data) >= 4  # Default: ABERTO, EM_TRATAMENTO, AGUARDA_CLIENTE, FECHADO
        
        # Verify status structure
        for status in data:
            assert "id" in status
            assert "code" in status
            assert "label" in status
            assert "color" in status
            assert "is_final" in status
        
        print(f"GET Ticket Statuses - PASSED ({len(data)} statuses returned)")
    
    def test_create_ticket_status_admin(self, admin_headers):
        """Test admin can create ticket status"""
        unique_code = f"TEST_STATUS_{uuid.uuid4().hex[:6].upper()}"
        response = requests.post(
            f"{BASE_URL}/api/admin/ticket-statuses",
            headers=admin_headers,
            json={
                "code": unique_code,
                "label": "Test Status",
                "color": "#ff00ff",
                "is_final": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == unique_code
        assert data["label"] == "Test Status"
        assert data["is_final"] == False
        print(f"CREATE Ticket Status - PASSED (created {unique_code})")


class TestP2AdminSlaConfig:
    """P2: Test SLA Config in Admin Settings"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        """Get admin auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_sla_config_admin(self, admin_headers):
        """Test admin can get SLA config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/sla-config",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "first_response_hours" in data
        assert "quote_response_hours" in data
        assert "enabled" in data
        print(f"GET SLA Config - PASSED (first_response={data['first_response_hours']}h, quote_response={data['quote_response_hours']}h)")
    
    def test_update_sla_config_admin(self, admin_headers):
        """Test admin can update SLA config"""
        response = requests.put(
            f"{BASE_URL}/api/admin/sla-config",
            headers=admin_headers,
            json={
                "first_response_hours": 4,
                "quote_response_hours": 48,
                "enabled": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_response_hours"] == 4
        assert data["quote_response_hours"] == 48
        print("UPDATE SLA Config - PASSED")
        
        # Reset to default
        requests.put(
            f"{BASE_URL}/api/admin/sla-config",
            headers=admin_headers,
            json={
                "first_response_hours": 2,
                "quote_response_hours": 24,
                "enabled": True
            }
        )


class TestP4QuoteLinkGeneration:
    """P4: Test Quote Link Generation for Customer"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        """Get admin auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_ticket_with_quote(self, admin_headers):
        """Create a test ticket with quote value"""
        response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=admin_headers,
            json={
                "customer_name": "TEST_P4_Cliente",
                "customer_phone": "999999999",
                "customer_email": "test_p4@test.com",
                "vehicle_plate": "TEST-P4",
                "type": "ORCAMENTO_PNEUS",
                "channel": "TELEFONE",
                "description": "Test quote flow"
            }
        )
        assert response.status_code == 200
        ticket = response.json()
        
        # Set quote value
        update_response = requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            headers=admin_headers,
            json={"quote_value": 150.00}
        )
        assert update_response.status_code == 200
        
        return ticket
    
    def test_generate_quote_link(self, admin_headers, test_ticket_with_quote):
        """Test generating quote link for customer"""
        ticket_id = test_ticket_with_quote["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "expires_at" in data
        assert "link" in data
        print(f"GENERATE Quote Link - PASSED (token={data['token'][:8]}...)")
        return data["token"]
    
    def test_generate_quote_link_no_quote_value(self, admin_headers):
        """Test that generating quote link fails if no quote value set"""
        # Create ticket without quote value
        response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=admin_headers,
            json={
                "customer_name": "TEST_P4_NoQuote",
                "customer_phone": "888888888",
                "type": "INFORMACAO",
                "channel": "TELEFONE"
            }
        )
        ticket = response.json()
        
        # Try to generate link without quote value
        link_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket['id']}/generate-quote-link",
            headers=admin_headers
        )
        assert link_response.status_code == 400
        assert "orçamento" in link_response.json()["detail"].lower()
        print("GENERATE Quote Link without value - PASSED (400 error as expected)")


class TestP4PublicQuoteResponse:
    """P4: Test Public Quote Response Page"""
    
    @pytest.fixture(scope="class")
    def quote_token(self):
        """Get a valid quote token"""
        # Login as admin
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['token']}"}
        
        # Create ticket with quote value
        ticket_response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=admin_headers,
            json={
                "customer_name": "TEST_P4_PublicQuote",
                "customer_phone": "777777777",
                "customer_email": "public_quote@test.com",
                "vehicle_plate": "QUOTE-01",
                "type": "ORCAMENTO_PNEUS",
                "channel": "EMAIL",
                "description": "Testing public quote response"
            }
        )
        ticket = ticket_response.json()
        
        # Set quote value
        requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            headers=admin_headers,
            json={"quote_value": 250.00}
        )
        
        # Generate quote link
        link_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket['id']}/generate-quote-link",
            headers=admin_headers
        )
        return link_response.json()["token"]
    
    def test_get_public_quote_no_auth(self, quote_token):
        """Test public quote endpoint works without auth"""
        response = requests.get(f"{BASE_URL}/api/public/quote/{quote_token}")
        assert response.status_code == 200
        data = response.json()
        assert "ticket_number" in data
        assert "customer_name" in data
        assert "quote_value" in data
        assert data["quote_value"] == 250.00
        print(f"GET Public Quote - PASSED (ticket={data['ticket_number']}, value={data['quote_value']})")
    
    def test_get_public_quote_invalid_token(self):
        """Test public quote with invalid token returns 404"""
        response = requests.get(f"{BASE_URL}/api/public/quote/invalid-token-123")
        assert response.status_code == 404
        print("GET Public Quote invalid token - PASSED (404)")
    
    def test_respond_to_quote_accept(self):
        """Test customer can accept a quote"""
        # Create a new quote for this test
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['token']}"}
        
        # Create ticket
        ticket_response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=admin_headers,
            json={
                "customer_name": "TEST_P4_Accept",
                "customer_phone": "666666666",
                "type": "ORCAMENTO_MECANICA",
                "channel": "TELEFONE"
            }
        )
        ticket = ticket_response.json()
        
        # Set quote value
        requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            headers=admin_headers,
            json={"quote_value": 300.00}
        )
        
        # Generate quote link
        link_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket['id']}/generate-quote-link",
            headers=admin_headers
        )
        token = link_response.json()["token"]
        
        # Accept quote (no auth required)
        response = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={"status": "ACCEPTED", "comments": "Aceito o orçamento proposto"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        print("ACCEPT Quote - PASSED")
        
        # Verify ticket status changed
        ticket_check = requests.get(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            headers=admin_headers
        )
        ticket_data = ticket_check.json()
        assert ticket_data["quote_response_status"] == "ACCEPTED"
        assert ticket_data["status"] == "EM_TRATAMENTO"  # Status changes to EM_TRATAMENTO on accept
        print("ACCEPT Quote - Ticket status updated correctly")
    
    def test_respond_to_quote_reject(self):
        """Test customer can reject a quote"""
        # Create a new quote for this test
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['token']}"}
        
        # Create ticket
        ticket_response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=admin_headers,
            json={
                "customer_name": "TEST_P4_Reject",
                "customer_phone": "555555555",
                "type": "ORCAMENTO_MECANICA",
                "channel": "TELEFONE"
            }
        )
        ticket = ticket_response.json()
        
        # Set quote value
        requests.put(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            headers=admin_headers,
            json={"quote_value": 500.00}
        )
        
        # Generate quote link
        link_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket['id']}/generate-quote-link",
            headers=admin_headers
        )
        token = link_response.json()["token"]
        
        # Reject quote (no auth required)
        response = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={"status": "REJECTED", "comments": "Valor muito alto"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        print("REJECT Quote - PASSED")
        
        # Verify ticket status changed
        ticket_check = requests.get(
            f"{BASE_URL}/api/tickets/{ticket['id']}",
            headers=admin_headers
        )
        ticket_data = ticket_check.json()
        assert ticket_data["quote_response_status"] == "REJECTED"
        assert ticket_data["status"] == "FECHADO"  # Status changes to FECHADO on reject
        print("REJECT Quote - Ticket status updated correctly")
    
    def test_respond_twice_fails(self, quote_token):
        """Test that responding twice to the same quote fails"""
        # First response
        first_response = requests.post(
            f"{BASE_URL}/api/public/quote/{quote_token}/respond",
            json={"status": "ACCEPTED"}
        )
        
        # Second response should fail
        second_response = requests.post(
            f"{BASE_URL}/api/public/quote/{quote_token}/respond",
            json={"status": "REJECTED"}
        )
        assert second_response.status_code == 400
        print("RESPOND twice - PASSED (400 error on second response)")


class TestP1Attachments:
    """P1: Test Attachments in Messages"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        """Get admin auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_ticket(self, admin_headers):
        """Create a test ticket"""
        response = requests.post(
            f"{BASE_URL}/api/tickets",
            headers=admin_headers,
            json={
                "customer_name": "TEST_P1_Attachments",
                "customer_phone": "444444444",
                "customer_email": "attachments@test.com",
                "type": "INFORMACAO",
                "channel": "EMAIL"
            }
        )
        return response.json()
    
    def test_upload_attachment(self, admin_headers, test_ticket):
        """Test uploading attachment to ticket"""
        ticket_id = test_ticket["id"]
        
        # Create a simple test file
        files = {
            'file': ('test.txt', b'Test content for attachment', 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/attachments",
            headers=admin_headers,
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["original_filename"] == "test.txt"
        print(f"UPLOAD Attachment - PASSED (id={data['id']})")
        return data["id"]
    
    def test_list_attachments(self, admin_headers, test_ticket):
        """Test listing attachments for ticket"""
        ticket_id = test_ticket["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}/attachments",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"LIST Attachments - PASSED ({len(data)} attachments)")
    
    def test_send_message_with_attachments(self, admin_headers, test_ticket):
        """Test sending message with attachment IDs"""
        ticket_id = test_ticket["id"]
        
        # First upload an attachment
        files = {
            'file': ('quote.pdf', b'PDF content here', 'application/pdf')
        }
        upload_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/attachments",
            headers=admin_headers,
            files=files
        )
        attachment_id = upload_response.json()["id"]
        
        # Now send message with attachment
        message_response = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            headers=admin_headers,
            json={
                "body": "Aqui está o orçamento em anexo",
                "channel": "EMAIL",
                "is_quote_response": False,
                "attachment_ids": [attachment_id]
            }
        )
        assert message_response.status_code == 200
        message_data = message_response.json()
        assert attachment_id in message_data["attachment_ids"]
        print("SEND Message with Attachment - PASSED")
    
    def test_get_messages_with_attachments(self, admin_headers, test_ticket):
        """Test that messages return attachment_ids"""
        ticket_id = test_ticket["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            headers=admin_headers
        )
        assert response.status_code == 200
        messages = response.json()
        
        # Find message with attachments
        msg_with_attachments = [m for m in messages if m.get("attachment_ids")]
        assert len(msg_with_attachments) > 0, "Should have message with attachments"
        print(f"GET Messages with Attachments - PASSED ({len(msg_with_attachments)} messages with attachments)")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_data(self):
        """Archive test tickets created during tests"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        admin_headers = {"Authorization": f"Bearer {login_response.json()['token']}"}
        
        # Get tickets
        tickets_response = requests.get(
            f"{BASE_URL}/api/tickets?search=TEST_",
            headers=admin_headers
        )
        
        if tickets_response.status_code == 200:
            test_tickets = [t for t in tickets_response.json() if "TEST_" in t.get("customer_name", "")]
            for ticket in test_tickets[:10]:  # Limit to 10
                requests.post(
                    f"{BASE_URL}/api/tickets/{ticket['id']}/archive",
                    headers=admin_headers
                )
        
        print(f"CLEANUP - Archived test tickets")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
