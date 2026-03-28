"""
Intake Module - Backend Integration Tests
Tests for CRUD operations, conversion to ticket, and module isolation.
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('API_BASE_URL', 'https://quote-management-4.preview.emergentagent.com').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@pdpv.pt",
        "password": "HCNMEnKMLq"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def api_client(auth_token):
    """Shared requests session with auth."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture
def cleanup_intake_ids():
    """Track created intake IDs for cleanup."""
    created_ids = []
    yield created_ids
    # Cleanup will be done by individual tests


class TestModuleStatus:
    """Test module status endpoint."""
    
    def test_module_status_returns_intake_enabled(self, api_client):
        """Verify intake module is enabled in status response."""
        response = api_client.get(f"{BASE_URL}/api/modules/status")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert data["modules"]["intake"] is True


class TestIntakeCreate:
    """Test CREATE intake request operations."""
    
    def test_create_intake_success(self, api_client, cleanup_intake_ids):
        """Create intake request with all fields."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "manual",
            "sender_name": f"TEST_IntakeCreate_{unique_id}",
            "sender_contact": "912345678",
            "raw_text": "Preciso de 4 pneus para teste",
            "license_plate": "AA-00-BB",
            "tire_size": "205/55 R16",
            "attachments": []
        }
        
        response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert data["sender_name"] == payload["sender_name"]
        assert data["sender_contact"] == payload["sender_contact"]
        assert data["source"] == "manual"
        assert data["status"] == "PENDING"
        assert data["raw_text"] == payload["raw_text"]
        assert data["license_plate"] == "AA-00-BB"
        assert data["tire_size"] == "205/55 R16"
        
        cleanup_intake_ids.append(data["id"])
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/intake/{data['id']}")
    
    def test_create_intake_minimal_fields(self, api_client, cleanup_intake_ids):
        """Create intake with only required fields."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "telefone",
            "sender_name": f"TEST_Minimal_{unique_id}",
            "sender_contact": "965000111",
            "raw_text": "Mensagem de teste"
        }
        
        response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["license_plate"] is None
        assert data["tire_size"] is None
        assert data["attachments"] == []
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/intake/{data['id']}")
    
    def test_create_intake_different_sources(self, api_client):
        """Test creating intake with different sources."""
        sources = ["manual", "telefone", "email", "whatsapp", "telegram", "web_form"]
        created_ids = []
        
        for source in sources:
            unique_id = str(uuid.uuid4())[:8]
            payload = {
                "source": source,
                "sender_name": f"TEST_Source_{source}_{unique_id}",
                "sender_contact": "912000000",
                "raw_text": f"Test from {source}"
            }
            response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
            assert response.status_code == 200, f"Failed for source: {source}"
            data = response.json()
            assert data["source"] == source
            created_ids.append(data["id"])
        
        # Cleanup
        for intake_id in created_ids:
            api_client.delete(f"{BASE_URL}/api/intake/{intake_id}")


class TestIntakeRead:
    """Test READ intake request operations."""
    
    def test_list_intake_requests(self, api_client):
        """List all intake requests with pagination."""
        response = api_client.get(f"{BASE_URL}/api/intake")
        assert response.status_code == 200
        data = response.json()
        # New paginated response format
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)
    
    def test_get_single_intake_request(self, api_client):
        """Get a specific intake request by ID."""
        # First create one
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "manual",
            "sender_name": f"TEST_GetSingle_{unique_id}",
            "sender_contact": "912345678",
            "raw_text": "Test get single"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        assert create_response.status_code == 200
        intake_id = create_response.json()["id"]
        
        # Now get it
        response = api_client.get(f"{BASE_URL}/api/intake/{intake_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == intake_id
        assert data["sender_name"] == payload["sender_name"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/intake/{intake_id}")
    
    def test_get_nonexistent_intake_returns_404(self, api_client):
        """Getting non-existent intake returns 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.get(f"{BASE_URL}/api/intake/{fake_id}")
        assert response.status_code == 404
    
    def test_list_intake_with_status_filter(self, api_client):
        """List intake requests filtered by status."""
        response = api_client.get(f"{BASE_URL}/api/intake?status=PENDING")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        for item in data["items"]:
            assert item["status"] == "PENDING"


class TestIntakeUpdate:
    """Test UPDATE intake request operations."""
    
    def test_update_intake_all_fields(self, api_client):
        """Update all editable fields of an intake request."""
        # Create
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "manual",
            "sender_name": f"TEST_UpdateAll_Original_{unique_id}",
            "sender_contact": "912000000",
            "raw_text": "Original message",
            "license_plate": "AA-00-AA",
            "tire_size": "195/65 R15"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Update
        update_payload = {
            "sender_name": f"TEST_UpdateAll_EDITED_{unique_id}",
            "sender_contact": "965111222",
            "raw_text": "Edited message",
            "license_plate": "BB-11-BB",
            "tire_size": "205/55 R16",
            "status": "PROCESSING"
        }
        update_response = api_client.put(f"{BASE_URL}/api/intake/{intake_id}", json=update_payload)
        assert update_response.status_code == 200
        data = update_response.json()
        
        # Verify updates
        assert data["sender_name"] == update_payload["sender_name"]
        assert data["sender_contact"] == update_payload["sender_contact"]
        assert data["raw_text"] == update_payload["raw_text"]
        assert data["license_plate"] == update_payload["license_plate"]
        assert data["tire_size"] == update_payload["tire_size"]
        assert data["status"] == "PROCESSING"
        
        # Verify with GET
        get_response = api_client.get(f"{BASE_URL}/api/intake/{intake_id}")
        get_data = get_response.json()
        assert get_data["sender_name"] == update_payload["sender_name"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/intake/{intake_id}")
    
    def test_update_single_field(self, api_client):
        """Update only one field."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "email",
            "sender_name": f"TEST_UpdateSingle_{unique_id}",
            "sender_contact": "test@example.com",
            "raw_text": "Test message"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Update only the name
        update_response = api_client.put(f"{BASE_URL}/api/intake/{intake_id}", json={
            "sender_name": f"TEST_UpdateSingle_EDITED_{unique_id}"
        })
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["sender_name"].endswith("_EDITED_" + unique_id)
        assert data["sender_contact"] == "test@example.com"  # Unchanged
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/intake/{intake_id}")
    
    def test_update_nonexistent_intake_returns_404(self, api_client):
        """Updating non-existent intake returns 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.put(f"{BASE_URL}/api/intake/{fake_id}", json={"sender_name": "Test"})
        assert response.status_code == 404


class TestIntakeDelete:
    """Test DELETE intake request operations."""
    
    def test_delete_pending_intake(self, api_client):
        """Delete a pending intake request."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "manual",
            "sender_name": f"TEST_ToDelete_{unique_id}",
            "sender_contact": "912000000",
            "raw_text": "Will be deleted"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Delete
        delete_response = api_client.delete(f"{BASE_URL}/api/intake/{intake_id}")
        assert delete_response.status_code == 200
        assert "eliminado" in delete_response.json()["message"].lower()
        
        # Verify it's gone
        get_response = api_client.get(f"{BASE_URL}/api/intake/{intake_id}")
        assert get_response.status_code == 404
    
    def test_delete_nonexistent_intake_returns_404(self, api_client):
        """Deleting non-existent intake returns 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.delete(f"{BASE_URL}/api/intake/{fake_id}")
        assert response.status_code == 404


class TestIntakeConversion:
    """Test CONVERT intake to ticket operations - MOST IMPORTANT."""
    
    def test_convert_intake_to_ticket_success(self, api_client):
        """Convert intake request to a real ticket."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "whatsapp",
            "sender_name": f"TEST_Convert_{unique_id}",
            "sender_contact": "912123456",
            "raw_text": "Preciso de orçamento para 4 pneus",
            "license_plate": "CC-33-DD",
            "tire_size": "205/55 R16"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        assert create_response.status_code == 200
        intake_id = create_response.json()["id"]
        
        # Convert to ticket
        convert_payload = {
            "ticket_type": "ORCAMENTO_PNEUS",
            "customer_email": "test@example.com"
        }
        convert_response = api_client.post(f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket", json=convert_payload)
        assert convert_response.status_code == 200
        data = convert_response.json()
        
        # Verify response
        assert "ticket_id" in data
        assert "ticket_number" in data
        assert data["intake_id"] == intake_id
        assert "Ticket criado" in data["message"]
        
        ticket_id = data["ticket_id"]
        
        # Verify intake is now CONVERTED
        get_intake_response = api_client.get(f"{BASE_URL}/api/intake/{intake_id}")
        assert get_intake_response.status_code == 200
        intake_data = get_intake_response.json()
        assert intake_data["status"] == "CONVERTED"
        assert intake_data["converted_ticket_id"] == ticket_id
        assert intake_data["converted_at"] is not None
        
        # Verify ticket was created
        get_ticket_response = api_client.get(f"{BASE_URL}/api/tickets/{ticket_id}")
        assert get_ticket_response.status_code == 200
        ticket_data = get_ticket_response.json()
        assert ticket_data["customer_name"] == payload["sender_name"]
        assert ticket_data["customer_phone"] == payload["sender_contact"]
        assert ticket_data["vehicle_plate"] == payload["license_plate"]
        # intake_request_id is stored but may not be in the response schema
    
    def test_convert_with_override_data(self, api_client):
        """Convert intake with overridden customer data."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "telegram",
            "sender_name": f"TEST_ConvertOverride_{unique_id}",
            "sender_contact": "912000000",
            "raw_text": "Original message"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Convert with overrides
        convert_payload = {
            "customer_name": f"OVERRIDE_Name_{unique_id}",
            "customer_phone": "965999888",
            "customer_email": "override@example.com",
            "vehicle_plate": "OV-ER-ID",
            "ticket_type": "INFORMACAO",
            "description": "Overridden description"
        }
        convert_response = api_client.post(f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket", json=convert_payload)
        assert convert_response.status_code == 200
        ticket_id = convert_response.json()["ticket_id"]
        
        # Verify ticket uses override data
        get_ticket_response = api_client.get(f"{BASE_URL}/api/tickets/{ticket_id}")
        ticket_data = get_ticket_response.json()
        assert ticket_data["customer_name"] == convert_payload["customer_name"]
        assert ticket_data["customer_phone"] == convert_payload["customer_phone"]
        assert ticket_data["customer_email"] == convert_payload["customer_email"]
        assert ticket_data["vehicle_plate"] == convert_payload["vehicle_plate"]
        assert ticket_data["description"] == convert_payload["description"]
    
    def test_convert_already_converted_returns_400(self, api_client):
        """Converting already converted intake returns 400."""
        # First, get a converted intake from the list
        list_response = api_client.get(f"{BASE_URL}/api/intake?status=CONVERTED&page_size=1")
        data = list_response.json()
        if list_response.status_code == 200 and data.get("items"):
            converted_intake = data["items"][0]
            
            # Try to convert again
            convert_response = api_client.post(f"{BASE_URL}/api/intake/{converted_intake['id']}/convert_to_ticket", json={
                "ticket_type": "INFORMACAO"
            })
            assert convert_response.status_code == 400
            assert "já convertido" in convert_response.json()["detail"].lower()
        else:
            pytest.skip("No converted intake to test with")
    
    def test_cannot_delete_converted_intake(self, api_client):
        """Cannot delete an intake that has been converted."""
        # Get a converted intake
        list_response = api_client.get(f"{BASE_URL}/api/intake?status=CONVERTED&page_size=1")
        data = list_response.json()
        if list_response.status_code == 200 and data.get("items"):
            converted_intake = data["items"][0]
            
            # Try to delete
            delete_response = api_client.delete(f"{BASE_URL}/api/intake/{converted_intake['id']}")
            assert delete_response.status_code == 400
            assert "convertido" in delete_response.json()["detail"].lower()
        else:
            pytest.skip("No converted intake to test with")
    
    def test_cannot_edit_converted_intake(self, api_client):
        """Cannot edit an intake that has been converted."""
        # Get a converted intake
        list_response = api_client.get(f"{BASE_URL}/api/intake?status=CONVERTED&page_size=1")
        data = list_response.json()
        if list_response.status_code == 200 and data.get("items"):
            converted_intake = data["items"][0]
            
            # Try to edit
            edit_response = api_client.put(f"{BASE_URL}/api/intake/{converted_intake['id']}", json={
                "sender_name": "Should Fail"
            })
            assert edit_response.status_code == 400
            assert "convertido" in edit_response.json()["detail"].lower()
        else:
            pytest.skip("No converted intake to test with")


class TestModuleIsolation:
    """Test that intake module doesn't affect regular tickets."""
    
    def test_tickets_endpoint_works_independently(self, api_client):
        """Verify /api/tickets endpoint works regardless of intake module."""
        response = api_client.get(f"{BASE_URL}/api/tickets")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_delete_intake_does_not_affect_tickets(self, api_client):
        """Deleting an intake doesn't affect the tickets collection."""
        # Get initial ticket count
        tickets_before = api_client.get(f"{BASE_URL}/api/tickets").json()
        count_before = len(tickets_before)
        
        # Create and delete an intake
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "manual",
            "sender_name": f"TEST_Isolation_{unique_id}",
            "sender_contact": "912000000",
            "raw_text": "Test isolation"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        api_client.delete(f"{BASE_URL}/api/intake/{intake_id}")
        
        # Verify ticket count unchanged
        tickets_after = api_client.get(f"{BASE_URL}/api/tickets").json()
        count_after = len(tickets_after)
        assert count_after == count_before
    
    def test_converted_ticket_exists_in_tickets_list(self, api_client):
        """A converted intake creates a ticket that appears in tickets list."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "manual",
            "sender_name": f"TEST_InTicketsList_{unique_id}",
            "sender_contact": "912123456",
            "raw_text": "Test"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Convert
        convert_response = api_client.post(f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket", json={
            "ticket_type": "INFORMACAO"
        })
        ticket_id = convert_response.json()["ticket_id"]
        
        # Verify ticket is in tickets list
        tickets_response = api_client.get(f"{BASE_URL}/api/tickets")
        ticket_ids = [t["id"] for t in tickets_response.json()]
        assert ticket_id in ticket_ids


class TestSourceToChannelMapping:
    """Test that source is correctly mapped to channel in created tickets."""
    
    def test_telegram_source_maps_to_telegram_channel(self, api_client):
        """Telegram source becomes TELEGRAM channel."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "telegram",
            "sender_name": f"TEST_TelegramChannel_{unique_id}",
            "sender_contact": "telegram_user",
            "raw_text": "Test"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Convert
        convert_response = api_client.post(f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket", json={
            "ticket_type": "INFORMACAO"
        })
        ticket_id = convert_response.json()["ticket_id"]
        
        # Verify channel
        ticket_response = api_client.get(f"{BASE_URL}/api/tickets/{ticket_id}")
        assert ticket_response.json()["channel"] == "TELEGRAM"
    
    def test_whatsapp_source_maps_to_whatsapp_channel(self, api_client):
        """WhatsApp source becomes WHATSAPP channel."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "whatsapp",
            "sender_name": f"TEST_WhatsAppChannel_{unique_id}",
            "sender_contact": "912000000",
            "raw_text": "Test"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Convert
        convert_response = api_client.post(f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket", json={
            "ticket_type": "INFORMACAO"
        })
        ticket_id = convert_response.json()["ticket_id"]
        
        # Verify channel
        ticket_response = api_client.get(f"{BASE_URL}/api/tickets/{ticket_id}")
        assert ticket_response.json()["channel"] == "WHATSAPP"
    
    def test_email_source_maps_to_email_channel(self, api_client):
        """Email source becomes EMAIL channel."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "source": "email",
            "sender_name": f"TEST_EmailChannel_{unique_id}",
            "sender_contact": "test@example.com",
            "raw_text": "Test"
        }
        create_response = api_client.post(f"{BASE_URL}/api/intake", json=payload)
        intake_id = create_response.json()["id"]
        
        # Convert
        convert_response = api_client.post(f"{BASE_URL}/api/intake/{intake_id}/convert_to_ticket", json={
            "ticket_type": "INFORMACAO"
        })
        ticket_id = convert_response.json()["ticket_id"]
        
        # Verify channel
        ticket_response = api_client.get(f"{BASE_URL}/api/tickets/{ticket_id}")
        assert ticket_response.json()["channel"] == "EMAIL"
