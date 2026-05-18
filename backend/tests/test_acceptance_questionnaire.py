"""
Test Acceptance Questionnaire Feature - Iteration 19
Tests the new acceptance intent fields for quote responses:
- acceptance_intent: 'agendar', 'avancar', 'contactar'
- preferred_date: date string for scheduling
- preferred_period: 'manha' or 'tarde'
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAcceptanceQuestionnaire:
    """Tests for the new acceptance questionnaire feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.admin_email = "admin@pdpv.pt"
        self.admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
    def get_auth_token(self):
        """Get authentication token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code}")
        
    def create_test_ticket_with_quote(self, token):
        """Create a test ticket with quote options and generate quote link"""
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create ticket
        ticket_data = {
            "customer_name": f"TEST_AcceptanceQuestionnaire_{uuid.uuid4().hex[:8]}",
            "customer_phone": "912345678",
            "description": "Test ticket for acceptance questionnaire",
            "ticket_type_id": "pedido_orcamento",
            "vehicle_plate": "AA-00-BB"
        }
        ticket_response = self.session.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers=headers
        )
        assert ticket_response.status_code == 200, f"Failed to create ticket: {ticket_response.text}"
        ticket = ticket_response.json()
        ticket_id = ticket["id"]
        
        # Create quote options
        quote_options = {
            "options": [
                {"description": "Opção 1 - Serviço básico", "amount": 50.00, "attachment_ids": []},
                {"description": "Opção 2 - Serviço completo", "amount": 100.00, "attachment_ids": []}
            ]
        }
        options_response = self.session.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json=quote_options,
            headers=headers
        )
        assert options_response.status_code == 200, f"Failed to create quote options: {options_response.text}"
        options = options_response.json()
        
        # Generate quote link
        link_response = self.session.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=headers
        )
        assert link_response.status_code == 200, f"Failed to generate quote link: {link_response.text}"
        link_data = link_response.json()
        
        return {
            "ticket_id": ticket_id,
            "ticket_number": ticket["ticket_number"],
            "token": link_data["token"],
            "option_ids": [opt["id"] for opt in options]
        }
    
    # ============== ACCEPTANCE INTENT TESTS ==============
    
    def test_acceptance_with_agendar_intent(self):
        """Test acceptance with 'agendar' intent - schedule for specific date"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        # Respond with 'agendar' intent
        future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        response = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Quero agendar para esta data",
                "accepted_option_ids": test_data["option_ids"],
                "acceptance_intent": "agendar",
                "preferred_date": future_date,
                "preferred_period": "manha"
            }
        )
        
        assert response.status_code == 200, f"Failed to respond: {response.text}"
        data = response.json()
        assert data["status"] == "success"
        print(f"SUCCESS: Acceptance with 'agendar' intent - date: {future_date}, period: manha")
        
        # Verify ticket was updated with intent fields
        headers = {"Authorization": f"Bearer {token}"}
        ticket_response = self.session.get(
            f"{BASE_URL}/api/tickets/{test_data['ticket_id']}",
            headers=headers
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        
        assert ticket.get("acceptance_intent") == "agendar", f"Expected 'agendar', got {ticket.get('acceptance_intent')}"
        assert ticket.get("acceptance_intent_label") == "Quero agendar para uma data específica"
        assert ticket.get("preferred_date") == future_date
        assert ticket.get("preferred_period") == "manha"
        print(f"SUCCESS: Ticket updated with acceptance_intent='agendar', preferred_date={future_date}, preferred_period='manha'")
    
    def test_acceptance_with_avancar_intent(self):
        """Test acceptance with 'avancar' intent - proceed with service"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        # Respond with 'avancar' intent
        response = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Podem avançar",
                "accepted_option_ids": test_data["option_ids"],
                "acceptance_intent": "avancar"
            }
        )
        
        assert response.status_code == 200, f"Failed to respond: {response.text}"
        data = response.json()
        assert data["status"] == "success"
        print("SUCCESS: Acceptance with 'avancar' intent")
        
        # Verify ticket was updated
        headers = {"Authorization": f"Bearer {token}"}
        ticket_response = self.session.get(
            f"{BASE_URL}/api/tickets/{test_data['ticket_id']}",
            headers=headers
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        
        assert ticket.get("acceptance_intent") == "avancar"
        assert ticket.get("acceptance_intent_label") == "Podem avançar com o serviço"
        assert ticket.get("preferred_date") is None
        assert ticket.get("preferred_period") is None
        print("SUCCESS: Ticket updated with acceptance_intent='avancar'")
    
    def test_acceptance_with_contactar_intent(self):
        """Test acceptance with 'contactar' intent - wants to be contacted"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        # Respond with 'contactar' intent
        response = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Tenho algumas dúvidas",
                "accepted_option_ids": test_data["option_ids"],
                "acceptance_intent": "contactar"
            }
        )
        
        assert response.status_code == 200, f"Failed to respond: {response.text}"
        data = response.json()
        assert data["status"] == "success"
        print("SUCCESS: Acceptance with 'contactar' intent")
        
        # Verify ticket was updated
        headers = {"Authorization": f"Bearer {token}"}
        ticket_response = self.session.get(
            f"{BASE_URL}/api/tickets/{test_data['ticket_id']}",
            headers=headers
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        
        assert ticket.get("acceptance_intent") == "contactar"
        assert ticket.get("acceptance_intent_label") == "Tenho dúvidas / Quero ser contactado"
        print("SUCCESS: Ticket updated with acceptance_intent='contactar'")
    
    def test_acceptance_with_tarde_period(self):
        """Test acceptance with 'agendar' intent and 'tarde' period"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        future_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        response = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Prefiro à tarde",
                "accepted_option_ids": test_data["option_ids"],
                "acceptance_intent": "agendar",
                "preferred_date": future_date,
                "preferred_period": "tarde"
            }
        )
        
        assert response.status_code == 200, f"Failed to respond: {response.text}"
        
        # Verify ticket
        headers = {"Authorization": f"Bearer {token}"}
        ticket_response = self.session.get(
            f"{BASE_URL}/api/tickets/{test_data['ticket_id']}",
            headers=headers
        )
        ticket = ticket_response.json()
        
        assert ticket.get("preferred_period") == "tarde"
        print(f"SUCCESS: Acceptance with 'tarde' period - date: {future_date}")
    
    # ============== REGRESSION TESTS ==============
    
    def test_rejection_still_works(self):
        """Regression: Rejection flow still works"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        response = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "REJECTED",
                "comments": "Preço muito alto",
                "accepted_option_ids": [],
                "rejection_reason_code": "preco_alto",
                "rejection_reason_label": "Preço alto"
            }
        )
        
        assert response.status_code == 200, f"Rejection failed: {response.text}"
        data = response.json()
        assert data["status"] == "success"
        print("SUCCESS: Rejection flow still works")
    
    def test_public_branding_endpoint(self):
        """Regression: GET /api/public/branding still works"""
        response = self.session.get(f"{BASE_URL}/api/public/branding")
        
        assert response.status_code == 200, f"Public branding failed: {response.text}"
        data = response.json()
        assert "company_name" in data
        assert "primary_color" in data
        print(f"SUCCESS: Public branding endpoint works - company: {data.get('company_name')}")
    
    def test_public_quote_get_endpoint(self):
        """Regression: GET /api/public/quote/{token} still works"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        response = self.session.get(f"{BASE_URL}/api/public/quote/{test_data['token']}")
        
        assert response.status_code == 200, f"Public quote GET failed: {response.text}"
        data = response.json()
        assert "ticket_number" in data
        assert "customer_name" in data
        assert "quote_options" in data
        print(f"SUCCESS: Public quote GET works - ticket: {data.get('ticket_number')}")
    
    def test_login_flow(self):
        """Regression: Login flow still works"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        print("SUCCESS: Login flow works")
    
    def test_tire_analysis_report(self):
        """Regression: GET /api/admin/reports/tire-analysis still works"""
        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        response = self.session.get(
            f"{BASE_URL}/api/admin/reports/tire-analysis",
            headers=headers
        )
        
        assert response.status_code == 200, f"Tire analysis report failed: {response.text}"
        data = response.json()
        # Tire analysis returns a dict with tire_sizes, brands, keywords, etc.
        assert isinstance(data, dict)
        assert "tire_sizes" in data or "brands" in data or "keywords" in data
        print(f"SUCCESS: Tire analysis report works - keys: {list(data.keys())}")
    
    # ============== ACCEPTANCE WITHOUT INTENT (backward compatibility) ==============
    
    def test_acceptance_without_intent_still_works(self):
        """Test that acceptance without intent fields still works (backward compatibility)"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        # Respond without acceptance_intent (old behavior)
        response = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Aceito sem especificar intenção",
                "accepted_option_ids": test_data["option_ids"]
            }
        )
        
        assert response.status_code == 200, f"Failed to respond: {response.text}"
        data = response.json()
        assert data["status"] == "success"
        print("SUCCESS: Acceptance without intent still works (backward compatibility)")


class TestAcceptanceQuestionnaireValidation:
    """Tests for validation of acceptance questionnaire fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.admin_email = "admin@pdpv.pt"
        self.admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
    def get_auth_token(self):
        """Get authentication token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code}")
    
    def create_test_ticket_with_quote(self, token):
        """Create a test ticket with quote options and generate quote link"""
        headers = {"Authorization": f"Bearer {token}"}
        
        ticket_data = {
            "customer_name": f"TEST_Validation_{uuid.uuid4().hex[:8]}",
            "customer_phone": "912345679",
            "description": "Test ticket for validation",
            "ticket_type_id": "pedido_orcamento",
            "vehicle_plate": "CC-11-DD"
        }
        ticket_response = self.session.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers=headers
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        ticket_id = ticket["id"]
        
        quote_options = {
            "options": [
                {"description": "Opção teste", "amount": 75.00, "attachment_ids": []}
            ]
        }
        options_response = self.session.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json=quote_options,
            headers=headers
        )
        assert options_response.status_code == 200
        options = options_response.json()
        
        link_response = self.session.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=headers
        )
        assert link_response.status_code == 200
        link_data = link_response.json()
        
        return {
            "ticket_id": ticket_id,
            "token": link_data["token"],
            "option_ids": [opt["id"] for opt in options]
        }
    
    def test_cannot_respond_twice(self):
        """Test that quote cannot be responded to twice"""
        token = self.get_auth_token()
        test_data = self.create_test_ticket_with_quote(token)
        
        # First response
        response1 = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "accepted_option_ids": test_data["option_ids"],
                "acceptance_intent": "avancar"
            }
        )
        assert response1.status_code == 200
        
        # Second response should fail
        response2 = self.session.post(
            f"{BASE_URL}/api/public/quote/{test_data['token']}/respond",
            json={
                "status": "ACCEPTED",
                "accepted_option_ids": test_data["option_ids"],
                "acceptance_intent": "contactar"
            }
        )
        assert response2.status_code == 409, f"Expected 409, got {response2.status_code}"
        print("SUCCESS: Cannot respond to quote twice")
    
    def test_invalid_token_returns_404(self):
        """Test that invalid token returns 404"""
        response = self.session.get(f"{BASE_URL}/api/public/quote/invalid-token-12345")
        assert response.status_code == 404
        print("SUCCESS: Invalid token returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
