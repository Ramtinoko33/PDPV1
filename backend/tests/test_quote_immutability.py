"""
Tests for Quote Immutability Features:
- A) Backoffice locking: quote_locked_at, quote_decided_at, quote_decision
- B) Public quote one-time decision: first response recorded, second blocked (409)
- C) Change-after-send workflow: 'Criar nova versão' generates new link
"""

import pytest
import requests
import os
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="function")
def test_ticket(auth_headers):
    """Create a fresh test ticket for each test"""
    resp = requests.post(f"{BASE_URL}/api/tickets", json={
        "customer_name": "TEST_QuoteImmutability Client",
        "customer_phone": "912345678",
        "customer_email": "test@example.com",
        "vehicle_plate": "TEST-IMM",
        "type": "ORCAMENTO_PNEUS",
        "description": "Test ticket for quote immutability",
        "priority": "NORMAL"
    }, headers=auth_headers)
    assert resp.status_code in [200, 201], f"Failed to create ticket: {resp.text}"
    ticket = resp.json()
    yield ticket
    # Cleanup
    requests.delete(f"{BASE_URL}/api/tickets/{ticket['id']}", headers=auth_headers)


@pytest.fixture(scope="function")
def ticket_with_options(auth_headers, test_ticket):
    """Create ticket with quote options"""
    ticket_id = test_ticket["id"]
    resp = requests.post(
        f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
        json={
            "options": [
                {"description": "Pneu Michelin 205/55R16", "amount": 120.00, "attachment_ids": []},
                {"description": "Montagem e equilibragem", "amount": 30.00, "attachment_ids": []}
            ]
        },
        headers=auth_headers
    )
    assert resp.status_code == 200, f"Failed to create options: {resp.text}"
    return test_ticket


# ============ QUOTE LOCKING TESTS ============

class TestQuoteLocking:
    """Test backoffice quote locking functionality"""

    def test_initial_ticket_not_locked(self, ticket_with_options, auth_headers):
        """New ticket should not have quote_locked_at"""
        ticket_id = ticket_with_options["id"]
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("quote_locked_at") is None, "New ticket should not be locked"
        assert data.get("quote_decided_at") is None, "New ticket should not have decision"
        assert data.get("quote_decision") is None, "New ticket should not have decision value"
        print("PASS: New ticket is not locked")

    def test_generate_link_locks_quote(self, ticket_with_options, auth_headers):
        """Generating quote link should set quote_locked_at"""
        ticket_id = ticket_with_options["id"]
        
        # Generate link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to generate link: {resp.text}"
        link_data = resp.json()
        assert "token" in link_data, "Should return token"
        
        # Verify ticket is now locked
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("quote_locked_at") is not None, "Ticket should be locked after generating link"
        print(f"PASS: Quote locked at {data['quote_locked_at']}")
        return link_data["token"]

    def test_editing_locked_quote_returns_409(self, ticket_with_options, auth_headers):
        """Editing quote options after lock should return 409"""
        ticket_id = ticket_with_options["id"]
        
        # First generate link to lock the quote
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to generate link: {resp.text}"
        
        # Try to update options - should fail with 409
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={
                "options": [
                    {"description": "Updated option", "amount": 999.00, "attachment_ids": []}
                ]
            },
            headers=auth_headers
        )
        assert resp.status_code == 409, f"Expected 409 Conflict, got {resp.status_code}: {resp.text}"
        assert "bloqueado" in resp.json().get("detail", "").lower(), "Error should mention locked/blocked"
        print("PASS: Editing locked quote returns 409 Conflict")


# ============ ONE-TIME DECISION TESTS ============

class TestOneTimeDecision:
    """Test public quote one-time decision functionality"""

    def test_first_response_accepted(self, ticket_with_options, auth_headers):
        """First response should be accepted"""
        ticket_id = ticket_with_options["id"]
        
        # Generate link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        
        # Get quote options to find IDs
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-options", headers=auth_headers)
        options = resp.json()
        option_ids = [opt["id"] for opt in options]
        
        # Submit acceptance
        resp = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Aceito o orçamento",
                "accepted_option_ids": option_ids
            }
        )
        assert resp.status_code == 200, f"First response should succeed: {resp.text}"
        print("PASS: First response accepted successfully")
        
        # Verify ticket has decision recorded
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        data = resp.json()
        assert data.get("quote_decided_at") is not None, "Should have decision timestamp"
        assert data.get("quote_decision") == "ACCEPTED", "Decision should be ACCEPTED"
        print(f"PASS: Decision recorded - quote_decided_at: {data['quote_decided_at']}, decision: {data['quote_decision']}")

    def test_second_response_rejected_409(self, ticket_with_options, auth_headers):
        """Second response should return 409 Conflict"""
        ticket_id = ticket_with_options["id"]
        
        # Generate link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        
        # Get options for acceptance
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-options", headers=auth_headers)
        options = resp.json()
        option_ids = [opt["id"] for opt in options]
        
        # First response - should succeed
        resp = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={
                "status": "REJECTED",
                "comments": "Recuso",
                "accepted_option_ids": []
            }
        )
        assert resp.status_code == 200, f"First response should succeed: {resp.text}"
        
        # Second response - should fail with 409
        resp = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "Changed my mind",
                "accepted_option_ids": option_ids
            }
        )
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
        print("PASS: Second response blocked with 409")

    def test_public_page_shows_decision_info(self, ticket_with_options, auth_headers):
        """Public page should show decision timestamp after response"""
        ticket_id = ticket_with_options["id"]
        
        # Generate link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        
        # Submit response
        resp = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "OK",
                "accepted_option_ids": []
            }
        )
        assert resp.status_code == 200
        
        # Get public quote data
        resp = requests.get(f"{BASE_URL}/api/public/quote/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("quote_decided_at") is not None, "Public data should include decision timestamp"
        print(f"PASS: Public page includes quote_decided_at: {data['quote_decided_at']}")


# ============ NEW VERSION WORKFLOW TESTS ============

class TestNewVersionWorkflow:
    """Test 'Nova Versão' workflow for quote changes"""

    def test_new_version_unlocks_quote(self, ticket_with_options, auth_headers):
        """Creating new version should unlock quote for editing"""
        ticket_id = ticket_with_options["id"]
        
        # Lock by generating link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        # Verify locked
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        assert resp.json().get("quote_locked_at") is not None
        
        # Create new version
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-new-version",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"New version should succeed: {resp.text}"
        
        # Verify unlocked
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        data = resp.json()
        assert data.get("quote_locked_at") is None, "Quote should be unlocked"
        assert data.get("quote_decided_at") is None, "Decision should be reset"
        assert data.get("quote_decision") is None, "Decision value should be reset"
        print("PASS: New version unlocks quote")

    def test_new_version_allows_editing(self, ticket_with_options, auth_headers):
        """After new version, quote options can be edited again"""
        ticket_id = ticket_with_options["id"]
        
        # Lock by generating link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        # Create new version
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-new-version",
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        # Edit options - should succeed now
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={
                "options": [
                    {"description": "New option after version", "amount": 150.00, "attachment_ids": []}
                ]
            },
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Editing after new version should succeed: {resp.text}"
        print("PASS: Editing allowed after new version")

    def test_new_version_resets_options_acceptance(self, ticket_with_options, auth_headers):
        """New version should reset is_accepted status on options"""
        ticket_id = ticket_with_options["id"]
        
        # Lock by generating link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        
        # Accept quote
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-options", headers=auth_headers)
        options = resp.json()
        option_ids = [opt["id"] for opt in options]
        
        resp = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={
                "status": "ACCEPTED",
                "comments": "OK",
                "accepted_option_ids": option_ids
            }
        )
        assert resp.status_code == 200
        
        # Verify options are accepted
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-options", headers=auth_headers)
        options = resp.json()
        assert any(opt["is_accepted"] for opt in options), "Some options should be accepted"
        
        # Create new version
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-new-version",
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        # Verify options are reset
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/quote-options", headers=auth_headers)
        options = resp.json()
        assert not any(opt["is_accepted"] for opt in options), "All options should be reset to not accepted"
        print("PASS: New version resets option acceptance")

    def test_new_version_on_unlocked_quote_fails(self, ticket_with_options, auth_headers):
        """Creating new version on unlocked quote should fail"""
        ticket_id = ticket_with_options["id"]
        
        # Try new version without locking first
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-new-version",
            headers=auth_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "não está bloqueado" in resp.json().get("detail", "").lower() or "not" in resp.json().get("detail", "").lower()
        print("PASS: New version on unlocked quote returns 400")


# ============ EDGE CASES ============

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_locked_ticket_fields_in_response(self, ticket_with_options, auth_headers):
        """GET ticket should return lock fields"""
        ticket_id = ticket_with_options["id"]
        
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # These fields should exist (even if null)
        assert "quote_locked_at" in data, "Response should include quote_locked_at"
        assert "quote_decided_at" in data, "Response should include quote_decided_at"
        assert "quote_decision" in data, "Response should include quote_decision"
        print("PASS: Ticket response includes all lock fields")

    def test_multiple_link_generations_same_lock(self, ticket_with_options, auth_headers):
        """Generating link multiple times should maintain lock"""
        ticket_id = ticket_with_options["id"]
        
        # First generation
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        first_token = resp.json()["token"]
        
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        first_lock_time = resp.json()["quote_locked_at"]
        
        # Second generation
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        second_lock_time = resp.json()["quote_locked_at"]
        
        # Lock time should be the same (not re-locked)
        assert first_lock_time == second_lock_time, "Lock time should not change on regeneration"
        print("PASS: Multiple link generations maintain same lock time")
