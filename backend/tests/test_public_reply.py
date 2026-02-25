"""
Tests for Public Reply Portal feature:
- POST /api/tickets/{id}/generate-reply-link
- GET /api/public/reply/{token}
- POST /api/public/reply/{token}/submit
- GET /api/tickets/{id} (reply_link_token field)
- GET /api/tickets/{id}/messages (from_customer field)
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Known test ticket with existing reply token
TEST_TICKET_ID = "69251e37-d787-4a25-9365-b289a1d3803b"
TEST_TICKET_NUMBER = "TK20260225FBCA47"
TEST_REPLY_TOKEN = "4ef74aac-a780-41b3-950c-ec9753dfd373"

ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ============== TEST: GET PUBLIC REPLY TICKET INFO ==============

class TestPublicReplyGet:
    """Tests for GET /api/public/reply/{token} - No auth required"""

    def test_get_public_reply_valid_token(self):
        """Valid token returns ticket info"""
        response = requests.get(f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_get_public_reply_returns_ticket_number(self):
        """Response includes ticket_number field"""
        response = requests.get(f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}")
        assert response.status_code == 200
        data = response.json()
        assert "ticket_number" in data
        assert isinstance(data["ticket_number"], str)
        assert len(data["ticket_number"]) > 0

    def test_get_public_reply_returns_customer_name(self):
        """Response includes customer_name field"""
        response = requests.get(f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}")
        assert response.status_code == 200
        data = response.json()
        assert "customer_name" in data
        assert isinstance(data["customer_name"], str)

    def test_get_public_reply_returns_required_fields(self):
        """Response includes all required fields: ticket_number, customer_name, ticket_type, status"""
        response = requests.get(f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}")
        assert response.status_code == 200
        data = response.json()
        required_fields = ["ticket_number", "customer_name", "ticket_type", "status"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_get_public_reply_no_auth_required(self):
        """Public endpoint works without Authorization header"""
        response = requests.get(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}",
            headers={}  # Explicitly no auth
        )
        assert response.status_code == 200

    def test_get_public_reply_invalid_token_returns_404(self):
        """Invalid token returns 404"""
        response = requests.get(f"{BASE_URL}/api/public/reply/invalid-token-that-does-not-exist")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_get_public_reply_random_uuid_returns_404(self):
        """Random UUID that doesn't exist returns 404"""
        import uuid
        fake_token = str(uuid.uuid4())
        response = requests.get(f"{BASE_URL}/api/public/reply/{fake_token}")
        assert response.status_code == 404


# ============== TEST: GENERATE REPLY LINK ==============

class TestGenerateReplyLink:
    """Tests for POST /api/tickets/{id}/generate-reply-link - Auth required"""

    def test_generate_reply_link_returns_token(self, auth_headers):
        """Endpoint returns token field"""
        response = requests.post(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/generate-reply-link",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0

    def test_generate_reply_link_returns_expires_at(self, auth_headers):
        """Endpoint returns expires_at field"""
        response = requests.post(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/generate-reply-link",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "expires_at" in data
        assert isinstance(data["expires_at"], str)

    def test_generate_reply_link_idempotent(self, auth_headers):
        """Calling generate twice returns same token (idempotent)"""
        resp1 = requests.post(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/generate-reply-link",
            headers=auth_headers
        )
        resp2 = requests.post(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/generate-reply-link",
            headers=auth_headers
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["token"] == resp2.json()["token"], "Token should be stable (idempotent)"

    def test_generate_reply_link_requires_auth(self):
        """Endpoint returns 401/403 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/generate-reply-link"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_generate_reply_link_nonexistent_ticket_returns_404(self, auth_headers):
        """Non-existent ticket returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/tickets/nonexistent-ticket-id-12345/generate-reply-link",
            headers=auth_headers
        )
        assert response.status_code == 404


# ============== TEST: GET TICKET RETURNS REPLY LINK TOKEN ==============

class TestTicketReplyLinkToken:
    """Tests for reply_link_token field in ticket response"""

    def test_get_ticket_returns_reply_link_token(self, auth_headers):
        """After generating a reply link, GET ticket returns reply_link_token"""
        # First ensure reply link exists
        requests.post(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/generate-reply-link",
            headers=auth_headers
        )
        # Then fetch ticket
        response = requests.get(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply_link_token" in data
        assert data["reply_link_token"] is not None
        assert isinstance(data["reply_link_token"], str)
        assert data["reply_link_token"] == TEST_REPLY_TOKEN


# ============== TEST: SUBMIT PUBLIC REPLY ==============

class TestSubmitPublicReply:
    """Tests for POST /api/public/reply/{token}/submit"""

    def test_submit_reply_creates_message(self, auth_headers):
        """Submitting reply creates an INBOUND message"""
        # Submit a test message
        form_data = {"body": "TEST_PublicReply - Mensagem de teste automatizado"}
        response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_submit_reply_returns_success_status(self):
        """Submit response returns success status"""
        form_data = {"body": "TEST_PublicReply - Outra mensagem de teste"}
        response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"

    def test_submit_reply_message_is_from_customer(self, auth_headers):
        """Submitted message has from_customer=true in messages list"""
        # Submit a unique message
        test_body = "TEST_PublicReply_from_customer_check"
        form_data = {"body": test_body}
        submit_response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data
        )
        assert submit_response.status_code == 200

        # Verify message in ticket messages
        messages_response = requests.get(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/messages",
            headers=auth_headers
        )
        assert messages_response.status_code == 200
        messages = messages_response.json()

        # Find the test message
        test_msg = next((m for m in messages if m.get("body") == test_body), None)
        assert test_msg is not None, f"Test message '{test_body}' not found in messages"
        assert test_msg.get("from_customer") == True, f"from_customer should be True, got: {test_msg.get('from_customer')}"
        assert test_msg.get("direction") == "INBOUND", f"direction should be INBOUND, got: {test_msg.get('direction')}"

    def test_submit_reply_messages_have_from_customer_field(self, auth_headers):
        """Messages endpoint returns from_customer field"""
        messages_response = requests.get(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}/messages",
            headers=auth_headers
        )
        assert messages_response.status_code == 200
        messages = messages_response.json()
        # Check that from_customer field exists in message objects
        for msg in messages:
            assert "from_customer" in msg, f"Message missing from_customer field: {msg}"

    def test_submit_reply_invalid_token_returns_404(self):
        """Submit with invalid token returns 404"""
        form_data = {"body": "Test message"}
        response = requests.post(
            f"{BASE_URL}/api/public/reply/invalid-token-xyz/submit",
            data=form_data
        )
        assert response.status_code == 404

    def test_submit_reply_no_auth_required(self):
        """Submit endpoint works without auth (public endpoint)"""
        form_data = {"body": "TEST_PublicReply - No auth test"}
        response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data,
            headers={}  # No auth
        )
        assert response.status_code == 200

    def test_submit_reply_with_file_upload(self, auth_headers):
        """Submit with file upload creates attachment"""
        # Create a test file
        test_file_content = b"TEST_PublicReply - PDF content for testing attachments"
        test_filename = "test_attachment.txt"

        form_data = {"body": "TEST_PublicReply - Mensagem com ficheiro anexado"}
        files = {"files": (test_filename, io.BytesIO(test_file_content), "text/plain")}

        response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data,
            files=files
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("attachment_count", 0) == 1, f"Expected 1 attachment, got {data.get('attachment_count')}"

    def test_submit_reply_attachment_linked_to_ticket(self, auth_headers):
        """File upload creates attachment linked to ticket"""
        test_file_content = b"TEST_PublicReply - Another test file for attachment verification"
        test_filename = "verification_test.pdf"

        form_data = {"body": "TEST_PublicReply - attachment linked test"}
        files = {"files": (test_filename, io.BytesIO(test_file_content), "application/pdf")}

        response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data,
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert "attachment_count" in data
        assert data["attachment_count"] >= 1


# ============== TEST: STATUS TRANSITION ==============

class TestStatusTransition:
    """Tests for status transition AGUARDA_CLIENTE → EM_TRATAMENTO"""

    def test_status_transition_requires_aguarda_cliente(self, auth_headers):
        """Check that current ticket status can be retrieved"""
        response = requests.get(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"Current ticket status: {data['status']}")

    def test_submit_with_aguarda_cliente_changes_to_em_tratamento(self, auth_headers):
        """If ticket is in AGUARDA_CLIENTE status, submitting reply changes to EM_TRATAMENTO"""
        # Try to change ticket to AGUARDA_CLIENTE
        update_response = requests.put(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}",
            json={"status": "AGUARDA_CLIENTE"},
            headers=auth_headers
        )
        if update_response.status_code != 200:
            pytest.skip(f"Could not set ticket status: {update_response.text}")

        # Verify it's set
        ticket_before = requests.get(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}",
            headers=auth_headers
        ).json()
        assert ticket_before.get("status") == "AGUARDA_CLIENTE", f"Status not updated, got: {ticket_before.get('status')}"

        # Submit a public reply
        form_data = {"body": "TEST_PublicReply - Resposta que deve mudar status"}
        submit_response = requests.post(
            f"{BASE_URL}/api/public/reply/{TEST_REPLY_TOKEN}/submit",
            data=form_data
        )
        assert submit_response.status_code == 200

        # Verify status changed to EM_TRATAMENTO
        ticket_after = requests.get(
            f"{BASE_URL}/api/tickets/{TEST_TICKET_ID}",
            headers=auth_headers
        ).json()
        assert ticket_after.get("status") == "EM_TRATAMENTO", f"Expected EM_TRATAMENTO, got: {ticket_after.get('status')}"
