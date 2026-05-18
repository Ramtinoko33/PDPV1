"""
Test Suite for Agent Self-Assignment and Quote Section Features

Features tested:
1. Agent can self-assign unassigned tickets
2. Agent cannot assign tickets to other agents
3. Admin/Supervisor can assign tickets to anyone
4. Quote section is present in the ticket detail (UI tests in Playwright)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAgentAssignment:
    """Tests for ticket assignment permissions"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test credentials and get auth tokens"""
        self.admin_email = "admin@pdpv.pt"
        self.admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
        self.supervisor_email = "supervisor@pdpv.pt"
        self.supervisor_password = os.environ.get("TEST_SUPERVISOR_PASSWORD", "changeme")
        self.agent_email = "agente@pdpv.pt"
        self.agent_password = os.environ.get("TEST_AGENT_PASSWORD", "changeme")
        
        # Get admin token
        admin_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_password}
        )
        assert admin_resp.status_code == 200, f"Admin login failed: {admin_resp.text}"
        self.admin_token = admin_resp.json()["token"]
        self.admin_user_id = admin_resp.json()["user"]["id"]
        
        # Get supervisor token
        supervisor_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.supervisor_email, "password": self.supervisor_password}
        )
        assert supervisor_resp.status_code == 200, f"Supervisor login failed: {supervisor_resp.text}"
        self.supervisor_token = supervisor_resp.json()["token"]
        self.supervisor_user_id = supervisor_resp.json()["user"]["id"]
        
        # Get agent token
        agent_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.agent_email, "password": self.agent_password}
        )
        assert agent_resp.status_code == 200, f"Agent login failed: {agent_resp.text}"
        self.agent_token = agent_resp.json()["token"]
        self.agent_user_id = agent_resp.json()["user"]["id"]
        
        # Get list of agents for tests
        users_resp = requests.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert users_resp.status_code == 200
        users = users_resp.json()
        self.agents = [u for u in users if u["role"] == "AGENT"]
        
        # Get a different agent ID for testing
        self.other_agent_id = None
        for agent in self.agents:
            if agent["id"] != self.agent_user_id:
                self.other_agent_id = agent["id"]
                break
        
        yield
    
    def _get_admin_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}
    
    def _get_supervisor_headers(self):
        return {"Authorization": f"Bearer {self.supervisor_token}", "Content-Type": "application/json"}
    
    def _get_agent_headers(self):
        return {"Authorization": f"Bearer {self.agent_token}", "Content-Type": "application/json"}
    
    def _create_unassigned_ticket(self):
        """Helper to create an unassigned ticket for testing"""
        ticket_data = {
            "customer_name": "TEST_Assignment_Customer",
            "customer_phone": "999888777",
            "customer_email": "test@example.com",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test ticket for assignment testing"
        }
        resp = requests.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers=self._get_admin_headers()
        )
        assert resp.status_code == 200, f"Failed to create ticket: {resp.text}"
        return resp.json()
    
    def _cleanup_ticket(self, ticket_id):
        """Archive test ticket"""
        try:
            requests.post(
                f"{BASE_URL}/api/tickets/{ticket_id}/archive",
                headers=self._get_admin_headers()
            )
        except:
            pass
    
    # =========================
    # TEST: Admin can assign to anyone
    # =========================
    def test_admin_can_assign_ticket_to_agent(self):
        """Admin should be able to assign a ticket to any agent"""
        ticket = self._create_unassigned_ticket()
        ticket_id = ticket["id"]
        
        try:
            # Admin assigns ticket to agent
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.agent_user_id},
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 200, f"Admin failed to assign ticket: {resp.text}"
            
            # Verify assignment
            updated_ticket = resp.json()
            assert updated_ticket["assigned_to_user_id"] == self.agent_user_id, "Ticket not assigned to agent"
            print(f"SUCCESS: Admin assigned ticket to agent {self.agent_user_id}")
        finally:
            self._cleanup_ticket(ticket_id)
    
    def test_admin_can_assign_ticket_to_supervisor(self):
        """Admin should be able to assign a ticket to a supervisor"""
        ticket = self._create_unassigned_ticket()
        ticket_id = ticket["id"]
        
        try:
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.supervisor_user_id},
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 200, f"Admin failed to assign ticket to supervisor: {resp.text}"
            
            updated_ticket = resp.json()
            assert updated_ticket["assigned_to_user_id"] == self.supervisor_user_id
            print(f"SUCCESS: Admin assigned ticket to supervisor {self.supervisor_user_id}")
        finally:
            self._cleanup_ticket(ticket_id)
    
    # =========================
    # TEST: Supervisor can assign to anyone
    # =========================
    def test_supervisor_can_assign_ticket_to_agent(self):
        """Supervisor should be able to assign a ticket to any agent"""
        ticket = self._create_unassigned_ticket()
        ticket_id = ticket["id"]
        
        try:
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.agent_user_id},
                headers=self._get_supervisor_headers()
            )
            assert resp.status_code == 200, f"Supervisor failed to assign ticket: {resp.text}"
            
            updated_ticket = resp.json()
            assert updated_ticket["assigned_to_user_id"] == self.agent_user_id
            print(f"SUCCESS: Supervisor assigned ticket to agent {self.agent_user_id}")
        finally:
            self._cleanup_ticket(ticket_id)
    
    # =========================
    # TEST: Agent can self-assign unassigned tickets
    # =========================
    def test_agent_can_self_assign_unassigned_ticket(self):
        """Agent should be able to assign an unassigned ticket to themselves"""
        # First create ticket and assign to agent so they can see it
        ticket = self._create_unassigned_ticket()
        ticket_id = ticket["id"]
        
        try:
            # Agent tries to self-assign the unassigned ticket
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.agent_user_id},
                headers=self._get_agent_headers()
            )
            assert resp.status_code == 200, f"Agent failed to self-assign ticket: {resp.text}"
            
            updated_ticket = resp.json()
            assert updated_ticket["assigned_to_user_id"] == self.agent_user_id, "Ticket not self-assigned"
            print(f"SUCCESS: Agent self-assigned ticket to themselves")
        finally:
            self._cleanup_ticket(ticket_id)
    
    # =========================
    # TEST: Agent CANNOT assign to others
    # =========================
    def test_agent_cannot_assign_ticket_to_other_agent(self):
        """Agent should NOT be able to assign a ticket to another agent"""
        if not self.other_agent_id:
            pytest.skip("No other agent found to test with")
        
        # Create ticket and assign to this agent first
        ticket = self._create_unassigned_ticket()
        ticket_id = ticket["id"]
        
        try:
            # First, assign ticket to the test agent so they have permission to edit
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.agent_user_id},
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 200
            
            # Now agent tries to re-assign to another agent (should fail)
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.other_agent_id},
                headers=self._get_agent_headers()
            )
            
            # Should be blocked with 403
            assert resp.status_code == 403, f"Agent should not be able to assign to others. Got: {resp.status_code} - {resp.text}"
            
            # Verify the error message
            error_detail = resp.json().get("detail", "")
            assert "si próprios" in error_detail or "próprios" in error_detail, f"Unexpected error message: {error_detail}"
            print(f"SUCCESS: Agent blocked from assigning ticket to another agent")
        finally:
            self._cleanup_ticket(ticket_id)
    
    def test_agent_cannot_assign_unassigned_ticket_to_other(self):
        """Agent should NOT be able to assign an unassigned ticket to another agent"""
        if not self.other_agent_id:
            pytest.skip("No other agent found to test with")
        
        ticket = self._create_unassigned_ticket()
        ticket_id = ticket["id"]
        
        try:
            # Agent tries to assign unassigned ticket to another agent (should fail)
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"assigned_to_user_id": self.other_agent_id},
                headers=self._get_agent_headers()
            )
            
            # Should be blocked with 403
            assert resp.status_code == 403, f"Agent should not be able to assign to others. Got: {resp.status_code}"
            print(f"SUCCESS: Agent blocked from assigning unassigned ticket to another agent")
        finally:
            self._cleanup_ticket(ticket_id)


class TestQuoteSectionAPI:
    """Tests for quote value API functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test credentials"""
        admin_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@pdpv.pt", "password": "admin123"}
        )
        assert admin_resp.status_code == 200
        self.admin_token = admin_resp.json()["token"]
        self.admin_user_id = admin_resp.json()["user"]["id"]
        yield
    
    def _get_admin_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}
    
    def _create_test_ticket(self):
        """Create a test ticket"""
        ticket_data = {
            "customer_name": "TEST_Quote_Customer",
            "customer_phone": "999888666",
            "customer_email": "quote@example.com",
            "type": "ORCAMENTO_PNEUS",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Test ticket for quote testing"
        }
        resp = requests.post(
            f"{BASE_URL}/api/tickets",
            json=ticket_data,
            headers=self._get_admin_headers()
        )
        assert resp.status_code == 200
        return resp.json()
    
    def _cleanup_ticket(self, ticket_id):
        try:
            requests.post(
                f"{BASE_URL}/api/tickets/{ticket_id}/archive",
                headers=self._get_admin_headers()
            )
        except:
            pass
    
    def test_update_quote_value(self):
        """Test updating quote value on a ticket"""
        ticket = self._create_test_ticket()
        ticket_id = ticket["id"]
        
        try:
            # Update quote value
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"quote_value": 250.50},
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 200, f"Failed to update quote value: {resp.text}"
            
            updated = resp.json()
            assert updated["quote_value"] == 250.50, f"Quote value mismatch: {updated['quote_value']}"
            print(f"SUCCESS: Quote value updated to 250.50")
        finally:
            self._cleanup_ticket(ticket_id)
    
    def test_generate_quote_link(self):
        """Test generating quote link for a ticket with quote value"""
        ticket = self._create_test_ticket()
        ticket_id = ticket["id"]
        
        try:
            # First set quote value
            resp = requests.put(
                f"{BASE_URL}/api/tickets/{ticket_id}",
                json={"quote_value": 300.00},
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 200
            
            # Generate quote link
            resp = requests.post(
                f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 200, f"Failed to generate quote link: {resp.text}"
            
            link_data = resp.json()
            assert "token" in link_data, "Token not in response"
            assert "expires_at" in link_data, "Expires at not in response"
            print(f"SUCCESS: Quote link generated with token: {link_data['token'][:20]}...")
        finally:
            self._cleanup_ticket(ticket_id)
    
    def test_generate_quote_link_without_value_fails(self):
        """Test that generating quote link without quote value fails"""
        ticket = self._create_test_ticket()
        ticket_id = ticket["id"]
        
        try:
            # Try to generate quote link without setting quote value
            resp = requests.post(
                f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
                headers=self._get_admin_headers()
            )
            assert resp.status_code == 400, f"Should fail without quote value, got: {resp.status_code}"
            print(f"SUCCESS: Quote link generation correctly blocked without quote value")
        finally:
            self._cleanup_ticket(ticket_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
