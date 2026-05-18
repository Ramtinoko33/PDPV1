"""
Test Web Push Notifications and Authentication API Endpoints
Tests: VAPID key, push subscribe/unsubscribe, auth login, health check
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "changeme")
SUPERVISOR_EMAIL = "supervisor@pdpv.pt"
SUPERVISOR_PASSWORD = os.environ.get("TEST_SUPERVISOR_PASSWORD", "changeme")


class TestHealthCheck:
    """Health check endpoint tests"""

    def test_health_check_api(self):
        """GET /api/health - should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data}")


class TestAuthentication:
    """Authentication endpoint tests"""

    def test_login_admin_success(self):
        """POST /api/auth/login - admin login should work with bcrypt"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        # Can be 200 (success) or 401 (if user not seeded)
        if response.status_code == 401:
            print(f"⚠ Admin user not seeded yet: {response.json()}")
            pytest.skip("Admin user not seeded - need to create user first")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert "user" in data, "Response should contain user"
        assert data["user"]["email"] == ADMIN_EMAIL
        print(f"✓ Admin login successful: user_id={data['user'].get('id')}")

    def test_login_supervisor_success(self):
        """POST /api/auth/login - supervisor login should work with bcrypt"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPERVISOR_EMAIL, "password": SUPERVISOR_PASSWORD}
        )
        
        # Can be 200 (success) or 401 (if user not seeded)
        if response.status_code == 401:
            print(f"⚠ Supervisor user not seeded yet: {response.json()}")
            pytest.skip("Supervisor user not seeded - need to create user first")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"✓ Supervisor login successful")

    def test_login_invalid_credentials(self):
        """POST /api/auth/login - invalid credentials should return 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@example.com", "password": "wrongpass"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Invalid credentials correctly rejected")


@pytest.fixture
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        # Try to register the user first
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "name": "Admin User",
                "role": "ADMIN"
            }
        )
        if register_response.status_code in [200, 201]:
            return register_response.json().get("token")
        pytest.skip("Could not authenticate or register admin user")
    return response.json().get("token")


class TestWebPushAPI:
    """Web Push API endpoint tests"""

    def test_vapid_public_key_no_auth(self):
        """GET /api/push/vapid-public-key - should work without auth"""
        response = requests.get(f"{BASE_URL}/api/push/vapid-public-key")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "publicKey" in data, "Response should contain publicKey"
        assert len(data["publicKey"]) > 0, "Public key should not be empty"
        print(f"✓ VAPID public key returned: {data['publicKey'][:30]}...")

    def test_push_subscribe_requires_auth(self):
        """POST /api/push/subscribe - should require authentication"""
        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint",
            "keys": {
                "p256dh": "test-p256dh-key",
                "auth": "test-auth-key"
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/push/subscribe",
            json=subscription_data
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Subscribe endpoint correctly requires auth")

    def test_push_subscribe_with_auth(self, auth_token):
        """POST /api/push/subscribe - should save subscription with valid auth"""
        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-pytest",
            "keys": {
                "p256dh": "BNFINs0vJLBJAGgFDNDZB5Pz0t3OQXVFZ5mMGnBVuY4",
                "auth": "dGVzdC1hdXRoLWtleQ=="
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/push/subscribe",
            json=subscription_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data
        print(f"✓ Push subscription saved: {data['message']}")

    def test_push_unsubscribe_requires_auth(self):
        """DELETE /api/push/unsubscribe - should require authentication"""
        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint",
            "keys": {
                "p256dh": "test-p256dh-key",
                "auth": "test-auth-key"
            }
        }
        response = requests.delete(
            f"{BASE_URL}/api/push/unsubscribe",
            json=subscription_data
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Unsubscribe endpoint correctly requires auth")

    def test_push_unsubscribe_with_auth(self, auth_token):
        """DELETE /api/push/unsubscribe - should remove subscription"""
        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-pytest",
            "keys": {
                "p256dh": "BNFINs0vJLBJAGgFDNDZB5Pz0t3OQXVFZ5mMGnBVuY4",
                "auth": "dGVzdC1hdXRoLWtleQ=="
            }
        }
        response = requests.delete(
            f"{BASE_URL}/api/push/unsubscribe",
            json=subscription_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data
        print(f"✓ Push subscription removed: {data['message']}")


class TestAuthProtectedEndpoints:
    """Test that auth-protected endpoints work correctly"""

    def test_get_me_with_auth(self, auth_token):
        """GET /api/auth/me - should return current user"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "id" in data
        assert "email" in data
        print(f"✓ Get current user: {data['email']}")

    def test_notifications_with_auth(self, auth_token):
        """GET /api/notifications - should return notifications list"""
        response = requests.get(
            f"{BASE_URL}/api/notifications",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        print(f"✓ Notifications endpoint works: {len(data)} notifications")

    def test_unread_count_with_auth(self, auth_token):
        """GET /api/notifications/unread-count - should return count"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)
        print(f"✓ Unread count: {data['count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
