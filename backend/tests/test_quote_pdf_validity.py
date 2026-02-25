"""
Tests for PDF viewing and quote validity features on public quote page.
Feature: QuoteOption attachment_ids, quote_valid_until, public download endpoint.
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"


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


@pytest.fixture(scope="module")
def test_ticket(auth_headers):
    """Create a test ticket for quote tests"""
    resp = requests.post(f"{BASE_URL}/api/tickets", json={
        "customer_name": "TEST_QuotePDF Client",
        "customer_phone": "912345678",
        "vehicle_plate": "TEST-01",
        "description": "Test ticket for PDF quote tests",
        "priority": "MEDIUM"
    }, headers=auth_headers)
    assert resp.status_code == 201, f"Failed to create ticket: {resp.text}"
    ticket = resp.json()
    yield ticket
    # Cleanup
    requests.delete(f"{BASE_URL}/api/tickets/{ticket['id']}", headers=auth_headers)


# ============ QUOTE OPTIONS WITH ATTACHMENT_IDS ============

class TestQuoteOptionsWithAttachments:
    """Test quote options CRUD with attachment_ids"""

    def test_save_quote_options_with_attachment_ids(self, test_ticket, auth_headers):
        """POST /api/tickets/{id}/quote-options accepts attachment_ids per option"""
        ticket_id = test_ticket["id"]
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={
                "options": [
                    {"description": "Opção A", "amount": 100.0, "attachment_ids": []},
                    {"description": "Opção B", "amount": 200.0, "attachment_ids": ["fake-att-id-1"]}
                ]
            },
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert len(data) == 2
        print(f"PASS: Saved 2 quote options with attachment_ids")

    def test_get_quote_options_returns_attachment_ids(self, test_ticket, auth_headers):
        """GET /api/tickets/{id}/quote-options returns attachment_ids per option"""
        ticket_id = test_ticket["id"]
        resp = requests.get(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert len(data) >= 1, "No options returned"
        # Check each option has attachment_ids field
        for opt in data:
            assert "attachment_ids" in opt, f"Option missing attachment_ids: {opt}"
            assert isinstance(opt["attachment_ids"], list), "attachment_ids should be a list"
        # Find option B with fake attachment
        option_b = next((o for o in data if o["description"] == "Opção B"), None)
        if option_b:
            assert "fake-att-id-1" in option_b["attachment_ids"], "attachment_ids not persisted"
        print(f"PASS: GET options returns attachment_ids correctly")


# ============ GENERATE QUOTE LINK - quote_valid_until ============

class TestGenerateQuoteLink:
    """Test that generating a quote link sets quote_valid_until on the ticket"""

    def test_generate_quote_link_sets_valid_until(self, test_ticket, auth_headers):
        """POST /api/tickets/{id}/generate-quote-link sets quote_valid_until (now+15 days)"""
        ticket_id = test_ticket["id"]
        
        # First ensure options exist (from previous test or create fresh)
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={"options": [{"description": "Test Option", "amount": 150.0, "attachment_ids": []}]},
            headers=auth_headers
        )
        
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to generate quote link: {resp.text}"
        data = resp.json()
        assert "token" in data, "No token in response"
        
        # Now check the ticket has quote_valid_until
        ticket_resp = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=auth_headers)
        assert ticket_resp.status_code == 200
        ticket_data = ticket_resp.json()
        
        assert "quote_valid_until" in ticket_data, "quote_valid_until not set on ticket"
        assert ticket_data["quote_valid_until"] is not None, "quote_valid_until is None"
        
        # Verify it's approximately 15 days from now
        valid_until = datetime.fromisoformat(ticket_data["quote_valid_until"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff_days = (valid_until - now).days
        assert 14 <= diff_days <= 15, f"Expected ~15 days validity, got {diff_days} days"
        
        # Store token for other tests
        TestGenerateQuoteLink.token = data["token"]
        print(f"PASS: quote_valid_until set to ~15 days from now: {ticket_data['quote_valid_until']}")

    def test_generate_quote_link_returns_token(self, test_ticket, auth_headers):
        """Generate quote link response contains token, expires_at, link"""
        ticket_id = test_ticket["id"]
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "expires_at" in data
        assert "link" in data
        assert data["link"].startswith("/quote/")
        print(f"PASS: generate-quote-link returns token, expires_at, link")


# ============ PUBLIC QUOTE ENDPOINT ============

class TestPublicQuoteEndpoint:
    """Test GET /api/public/quote/{token} returns new fields"""
    
    _token = None

    @pytest.fixture(autouse=True)
    def setup_token(self, test_ticket, auth_headers):
        """Ensure we have a valid token for public quote tests"""
        ticket_id = test_ticket["id"]
        
        # Save quote options
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={"options": [{"description": "Option for public test", "amount": 250.0, "attachment_ids": []}]},
            headers=auth_headers
        )
        
        # Generate quote link
        resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        if resp.status_code == 200:
            TestPublicQuoteEndpoint._token = resp.json()["token"]

    def test_public_quote_returns_quote_valid_until(self):
        """GET /api/public/quote/{token} returns quote_valid_until field"""
        if not TestPublicQuoteEndpoint._token:
            pytest.skip("No token available")
        resp = requests.get(f"{BASE_URL}/api/public/quote/{TestPublicQuoteEndpoint._token}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "quote_valid_until" in data, "quote_valid_until missing from public quote response"
        assert data["quote_valid_until"] is not None, "quote_valid_until is None"
        print(f"PASS: public quote returns quote_valid_until: {data['quote_valid_until']}")

    def test_public_quote_returns_ticket_attachments(self):
        """GET /api/public/quote/{token} returns ticket_attachments field"""
        if not TestPublicQuoteEndpoint._token:
            pytest.skip("No token available")
        resp = requests.get(f"{BASE_URL}/api/public/quote/{TestPublicQuoteEndpoint._token}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "ticket_attachments" in data, "ticket_attachments missing from public quote response"
        assert isinstance(data["ticket_attachments"], list), "ticket_attachments should be a list"
        print(f"PASS: public quote returns ticket_attachments field (count: {len(data['ticket_attachments'])})")

    def test_public_quote_options_have_attachments_field(self):
        """GET /api/public/quote/{token} quote_options contain attachments list"""
        if not TestPublicQuoteEndpoint._token:
            pytest.skip("No token available")
        resp = requests.get(f"{BASE_URL}/api/public/quote/{TestPublicQuoteEndpoint._token}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        options = data.get("quote_options", [])
        if options:
            for opt in options:
                assert "attachments" in opt, f"Option missing 'attachments' field: {opt}"
                assert isinstance(opt["attachments"], list)
        print(f"PASS: public quote options have attachments field")


# ============ PUBLIC DOWNLOAD ENDPOINT ============

class TestPublicDownloadEndpoint:
    """Test GET /api/public/quote/{token}/attachments/{attachment_id}/download"""
    
    def test_public_download_with_invalid_token(self):
        """Download endpoint returns 404 for invalid token"""
        resp = requests.get(
            f"{BASE_URL}/api/public/quote/invalid-token-12345/attachments/some-att-id/download"
        )
        assert resp.status_code == 404, f"Expected 404 for invalid token, got {resp.status_code}"
        print(f"PASS: public download returns 404 for invalid token")

    def test_public_download_with_invalid_attachment(self, test_ticket, auth_headers):
        """Download endpoint returns 404 for invalid attachment_id"""
        ticket_id = test_ticket["id"]
        
        # Generate a valid token
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={"options": [{"description": "Download Test", "amount": 50.0, "attachment_ids": []}]},
            headers=auth_headers
        )
        link_resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert link_resp.status_code == 200
        token = link_resp.json()["token"]
        
        resp = requests.get(
            f"{BASE_URL}/api/public/quote/{token}/attachments/non-existent-attachment-id/download"
        )
        assert resp.status_code == 404, f"Expected 404 for invalid attachment, got {resp.status_code}"
        print(f"PASS: public download returns 404 for invalid attachment_id")

    def test_public_download_endpoint_exists(self, test_ticket, auth_headers):
        """Download endpoint returns something (not 404/500) for valid token"""
        ticket_id = test_ticket["id"]
        link_resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        if link_resp.status_code != 200:
            pytest.skip("Cannot generate token")
        token = link_resp.json()["token"]
        
        # The endpoint should exist (not 404 for endpoint itself)
        resp = requests.get(
            f"{BASE_URL}/api/public/quote/{token}/attachments/some-id/download"
        )
        # Either 404 (attachment not found) or 200, not 500 or method not allowed
        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code} {resp.text}"
        print(f"PASS: public download endpoint exists and responds correctly ({resp.status_code})")


# ============ QUOTE EXPIRY VALIDATION ============

class TestQuoteExpiry:
    """Test that respond_to_quote returns 400 if quote_valid_until is in the past"""

    def test_respond_to_expired_quote_returns_400(self, test_ticket, auth_headers):
        """POST /api/public/quote/{token}/respond returns 400 with 'Orçamento expirado' if expired"""
        ticket_id = test_ticket["id"]
        
        # 1. Set options and generate link
        requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/quote-options",
            json={"options": [{"description": "Expiry Test Option", "amount": 75.0, "attachment_ids": []}]},
            headers=auth_headers
        )
        link_resp = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/generate-quote-link",
            headers=auth_headers
        )
        assert link_resp.status_code == 200, f"Failed to generate link: {link_resp.text}"
        token = link_resp.json()["token"]
        
        # 2. Directly update quote_valid_until to past via API (admin endpoint)
        # We need to update the ticket's quote_valid_until directly
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        update_resp = requests.put(
            f"{BASE_URL}/api/tickets/{ticket_id}",
            json={"quote_valid_until": past_date},
            headers=auth_headers
        )
        # If the PUT doesn't accept quote_valid_until, we'll try via MongoDB directly via the backend
        # Check the response
        if update_resp.status_code not in [200, 204]:
            pytest.skip(f"Cannot set quote_valid_until via API (status {update_resp.status_code}), need MongoDB access")
        
        # 3. Try to respond to quote
        respond_resp = requests.post(
            f"{BASE_URL}/api/public/quote/{token}/respond",
            json={"status": "ACCEPTED", "comments": "", "accepted_option_ids": []}
        )
        assert respond_resp.status_code == 400, f"Expected 400 for expired quote, got {respond_resp.status_code}"
        assert "Orçamento expirado" in respond_resp.text, f"Expected expiry message, got: {respond_resp.text}"
        print(f"PASS: expired quote returns 400 with 'Orçamento expirado'")

    def test_respond_to_valid_quote_succeeds(self, test_ticket, auth_headers):
        """POST /api/public/quote/{token}/respond succeeds for valid (non-expired) quote"""
        ticket_id = test_ticket["id"]
        
        # Create fresh ticket for this test
        ticket_resp = requests.post(f"{BASE_URL}/api/tickets", json={
            "customer_name": "TEST_ExpiredQuote Client",
            "customer_phone": "912345679",
            "vehicle_plate": "TEST-02",
            "description": "Test for non-expired quote",
            "priority": "MEDIUM"
        }, headers=auth_headers)
        assert ticket_resp.status_code == 201
        new_ticket = ticket_resp.json()
        new_ticket_id = new_ticket["id"]
        
        try:
            # Set options
            requests.post(
                f"{BASE_URL}/api/tickets/{new_ticket_id}/quote-options",
                json={"options": [{"description": "Valid Opt", "amount": 99.0, "attachment_ids": []}]},
                headers=auth_headers
            )
            
            # Generate link - this sets quote_valid_until to now+15days
            link_resp = requests.post(
                f"{BASE_URL}/api/tickets/{new_ticket_id}/generate-quote-link",
                headers=auth_headers
            )
            assert link_resp.status_code == 200
            token = link_resp.json()["token"]
            
            # Get options to find IDs
            opts_resp = requests.get(
                f"{BASE_URL}/api/tickets/{new_ticket_id}/quote-options",
                headers=auth_headers
            )
            opts = opts_resp.json()
            opt_ids = [o["id"] for o in opts]
            
            # Respond to quote (should succeed)
            respond_resp = requests.post(
                f"{BASE_URL}/api/public/quote/{token}/respond",
                json={"status": "ACCEPTED", "comments": "Test", "accepted_option_ids": opt_ids}
            )
            assert respond_resp.status_code == 200, f"Failed: {respond_resp.text}"
            print(f"PASS: Non-expired quote responds successfully")
        finally:
            requests.delete(f"{BASE_URL}/api/tickets/{new_ticket_id}", headers=auth_headers)


# ============ INVALID TOKEN ============

class TestPublicQuoteInvalidToken:
    """Test public quote endpoint with invalid token"""
    
    def test_invalid_token_returns_404(self):
        """GET /api/public/quote/{token} returns 404 for invalid token"""
        resp = requests.get(f"{BASE_URL}/api/public/quote/invalid-token-xyz-000")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print(f"PASS: invalid token returns 404")
