"""
Telegram Alerts Module - API Tests
Tests for: alerts CRUD, stats, convert, dismiss, delete, alerts-count, user alerts access
"""
import pytest
import requests
import os
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")


@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestModuleStatus:
    """Test module status endpoint"""
    
    def test_telegram_alerts_module_enabled(self, auth_headers):
        """Verify telegram_alerts module is enabled"""
        response = requests.get(f"{BASE_URL}/api/modules/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert data["modules"].get("telegram_alerts") == True, "telegram_alerts module should be enabled"
        print(f"✓ Module status: telegram_alerts = {data['modules'].get('telegram_alerts')}")


class TestAlertsStats:
    """Test GET /api/telegram-alerts/alerts/stats"""
    
    def test_get_stats(self, auth_headers):
        """Get alert statistics"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify stats structure
        assert "pending" in data
        assert "converted" in data
        assert "dismissed" in data
        assert "total" in data
        
        # Verify types
        assert isinstance(data["pending"], int)
        assert isinstance(data["converted"], int)
        assert isinstance(data["dismissed"], int)
        assert isinstance(data["total"], int)
        
        # Total should be sum of all statuses
        assert data["total"] == data["pending"] + data["converted"] + data["dismissed"]
        
        print(f"✓ Stats: pending={data['pending']}, converted={data['converted']}, dismissed={data['dismissed']}, total={data['total']}")


class TestAlertsCount:
    """Test GET /api/telegram-alerts/alerts-count (sidebar badge)"""
    
    def test_get_pending_count(self, auth_headers):
        """Get pending alerts count for sidebar badge"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "count" in data
        assert isinstance(data["count"], int)
        assert data["count"] >= 0
        
        print(f"✓ Pending alerts count: {data['count']}")


class TestAlertsList:
    """Test GET /api/telegram-alerts/alerts"""
    
    def test_list_all_alerts(self, auth_headers):
        """List all alerts without filters"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "alerts" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        
        assert isinstance(data["alerts"], list)
        print(f"✓ Listed {len(data['alerts'])} alerts (total: {data['total']})")
    
    def test_list_pending_alerts(self, auth_headers):
        """List only pending alerts"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=pending", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # All returned alerts should be pending
        for alert in data["alerts"]:
            assert alert["status"] == "pending", f"Expected pending, got {alert['status']}"
        
        print(f"✓ Listed {len(data['alerts'])} pending alerts")
    
    def test_list_converted_alerts(self, auth_headers):
        """List only converted alerts"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=converted", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for alert in data["alerts"]:
            assert alert["status"] == "converted"
        
        print(f"✓ Listed {len(data['alerts'])} converted alerts")
    
    def test_list_dismissed_alerts(self, auth_headers):
        """List only dismissed alerts"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=dismissed", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for alert in data["alerts"]:
            assert alert["status"] == "dismissed"
        
        print(f"✓ Listed {len(data['alerts'])} dismissed alerts")
    
    def test_pagination(self, auth_headers):
        """Test pagination parameters"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?page=1&page_size=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["alerts"]) <= 5
        
        print(f"✓ Pagination works: page={data['page']}, page_size={data['page_size']}")


class TestAlertDetail:
    """Test GET /api/telegram-alerts/alerts/{id}"""
    
    def test_get_alert_detail(self, auth_headers):
        """Get single alert detail"""
        # First get list to find an alert ID
        list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts", headers=auth_headers)
        assert list_response.status_code == 200
        alerts = list_response.json()["alerts"]
        
        if not alerts:
            pytest.skip("No alerts available to test detail")
        
        alert_id = alerts[0]["id"]
        
        # Get detail
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify alert structure
        assert data["id"] == alert_id
        assert "source" in data
        assert data["source"] == "telegram_alerts"
        assert "status" in data
        assert "license_plate" in data
        assert "client_name" in data
        assert "items" in data
        assert "created_at" in data
        assert "attachments" in data
        assert "extraction_failed" in data
        
        print(f"✓ Got alert detail: id={alert_id}, plate={data.get('license_plate')}, status={data['status']}")
    
    def test_get_nonexistent_alert(self, auth_headers):
        """Get non-existent alert returns 404"""
        response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/nonexistent-id-12345", headers=auth_headers)
        assert response.status_code == 404
        print("✓ Non-existent alert returns 404")


class TestAlertUpdate:
    """Test PUT /api/telegram-alerts/alerts/{id}"""
    
    def test_update_alert_fields(self, auth_headers):
        """Update alert license_plate, client_name, items"""
        # Get a pending alert
        list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=pending", headers=auth_headers)
        alerts = list_response.json()["alerts"]
        
        if not alerts:
            pytest.skip("No pending alerts to test update")
        
        alert_id = alerts[0]["id"]
        original_plate = alerts[0].get("license_plate")
        
        # Update fields
        new_plate = "TEST-99-ZZ"
        new_name = "Test Client Updated"
        new_items = ["Pneus", "Travões", "Óleo"]
        
        response = requests.put(
            f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}",
            json={
                "license_plate": new_plate,
                "client_name": new_name,
                "items": new_items
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["license_plate"] == new_plate
        assert data["client_name"] == new_name
        assert data["items"] == new_items
        
        # Verify persistence with GET
        get_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}", headers=auth_headers)
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["license_plate"] == new_plate
        assert fetched["client_name"] == new_name
        
        # Restore original if it existed
        if original_plate:
            requests.put(
                f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}",
                json={"license_plate": original_plate},
                headers=auth_headers
            )
        
        print(f"✓ Updated alert {alert_id}: plate={new_plate}, name={new_name}")
    
    def test_update_nonexistent_alert(self, auth_headers):
        """Update non-existent alert returns 404"""
        response = requests.put(
            f"{BASE_URL}/api/telegram-alerts/alerts/nonexistent-id-12345",
            json={"license_plate": "XX-00-XX"},
            headers=auth_headers
        )
        assert response.status_code == 404
        print("✓ Update non-existent alert returns 404")


class TestAlertConvert:
    """Test POST /api/telegram-alerts/alerts/{id}/convert"""
    
    def test_convert_alert_to_ticket_full_form(self, auth_headers):
        """Convert alert to ticket with full form data (intake-style)"""
        # Get a pending alert
        list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=pending", headers=auth_headers)
        alerts = list_response.json()["alerts"]
        
        if not alerts:
            pytest.skip("No pending alerts to test conversion")
        
        alert_id = alerts[0]["id"]
        
        # Convert with full form data
        convert_data = {
            "customer_name": "Test Customer Convert",
            "customer_phone": "912345678",
            "customer_email": "test@convert.pt",
            "vehicle_plate": "AA-11-BB",
            "ticket_type": "ORCAMENTO_MECANICA",
            "description": "Test conversion from alert"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}/convert",
            json=convert_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response
        assert "ticket_id" in data
        assert "ticket_number" in data
        assert data["ticket_number"].startswith("TK")
        
        print(f"✓ Converted alert {alert_id} to ticket {data['ticket_number']}")
        
        # Verify alert is now converted
        alert_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}", headers=auth_headers)
        assert alert_response.status_code == 200
        alert_data = alert_response.json()
        assert alert_data["status"] == "converted"
        assert alert_data["converted"] == True
        assert alert_data["ticket_id"] == data["ticket_id"]
        
        print(f"✓ Alert status updated to 'converted', ticket_id={data['ticket_id']}")
        
        # Verify ticket was created
        ticket_response = requests.get(f"{BASE_URL}/api/tickets/{data['ticket_id']}", headers=auth_headers)
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()
        assert ticket["customer_name"] == convert_data["customer_name"]
        assert ticket["vehicle_plate"] == convert_data["vehicle_plate"]
        assert ticket["channel"] == "TELEGRAM"
        
        print(f"✓ Ticket created with correct data: customer={ticket['customer_name']}, plate={ticket['vehicle_plate']}")
    
    def test_convert_already_converted_alert(self, auth_headers):
        """Converting already converted alert returns 400"""
        # Get a converted alert
        list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=converted", headers=auth_headers)
        alerts = list_response.json()["alerts"]
        
        if not alerts:
            pytest.skip("No converted alerts to test")
        
        alert_id = alerts[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}/convert",
            json={"customer_name": "Test"},
            headers=auth_headers
        )
        assert response.status_code == 400
        print("✓ Converting already converted alert returns 400")


class TestAlertDismiss:
    """Test POST /api/telegram-alerts/alerts/{id}/dismiss"""
    
    def test_dismiss_alert(self, auth_headers):
        """Dismiss a pending alert"""
        # Get a pending alert
        list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=pending", headers=auth_headers)
        alerts = list_response.json()["alerts"]
        
        if not alerts:
            pytest.skip("No pending alerts to test dismiss")
        
        alert_id = alerts[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}/dismiss",
            json={},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "dismissed"
        print(f"✓ Dismissed alert {alert_id}")
        
        # Verify persistence
        get_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}", headers=auth_headers)
        assert get_response.json()["status"] == "dismissed"
        print("✓ Alert status persisted as 'dismissed'")


class TestAlertDelete:
    """Test DELETE /api/telegram-alerts/alerts/{id}"""
    
    def test_delete_alert(self, auth_headers):
        """Delete an alert (admin only)"""
        # Get any alert (preferably dismissed)
        list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=dismissed", headers=auth_headers)
        alerts = list_response.json()["alerts"]
        
        if not alerts:
            # Try pending
            list_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts?status=pending", headers=auth_headers)
            alerts = list_response.json()["alerts"]
        
        if not alerts:
            pytest.skip("No alerts to test delete")
        
        alert_id = alerts[0]["id"]
        
        response = requests.delete(
            f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        print(f"✓ Deleted alert {alert_id}")
        
        # Verify deleted
        get_response = requests.get(f"{BASE_URL}/api/telegram-alerts/alerts/{alert_id}", headers=auth_headers)
        assert get_response.status_code == 404
        print("✓ Deleted alert returns 404")


class TestUserAlertsAccess:
    """Test user has_alerts_access field"""
    
    def test_list_users_shows_alerts_access(self, auth_headers):
        """List users includes has_alerts_access field"""
        response = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
        assert response.status_code == 200
        users = response.json()
        
        assert len(users) > 0
        # Check that has_alerts_access field exists
        for user in users:
            assert "has_alerts_access" in user or user["role"] in ["ADMIN", "SUPERVISOR"]
        
        print(f"✓ Listed {len(users)} users with has_alerts_access field")
    
    def test_update_user_alerts_access(self, auth_headers):
        """Update user has_alerts_access field"""
        # Get users
        response = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
        users = response.json()
        
        # Find an AGENT user to test
        agent_user = next((u for u in users if u["role"] == "AGENT"), None)
        
        if not agent_user:
            pytest.skip("No AGENT user to test alerts access toggle")
        
        user_id = agent_user["id"]
        original_access = agent_user.get("has_alerts_access", False)
        
        # Toggle access
        new_access = not original_access
        response = requests.put(
            f"{BASE_URL}/api/users/{user_id}",
            json={"has_alerts_access": new_access},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_alerts_access"] == new_access
        
        print(f"✓ Updated user {user_id} has_alerts_access to {new_access}")
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/users/{user_id}",
            json={"has_alerts_access": original_access},
            headers=auth_headers
        )
        print(f"✓ Restored user {user_id} has_alerts_access to {original_access}")


class TestTicketTypes:
    """Test ticket types endpoint (used in convert modal)"""
    
    def test_get_ticket_types(self, auth_headers):
        """Get ticket types for convert modal dropdown"""
        response = requests.get(f"{BASE_URL}/api/ticket-types", headers=auth_headers)
        assert response.status_code == 200
        types = response.json()
        
        assert isinstance(types, list)
        assert len(types) > 0
        
        # Verify structure
        for t in types:
            assert "code" in t
            assert "label" in t
        
        # Check ORCAMENTO_MECANICA exists (default for alerts)
        codes = [t["code"] for t in types]
        assert "ORCAMENTO_MECANICA" in codes
        
        print(f"✓ Got {len(types)} ticket types, including ORCAMENTO_MECANICA")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
