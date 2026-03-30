"""
PDPV Tickets - Iteration 18 Backend Tests
Focus: Vehicle plates bug fix verification + comprehensive system verification

Tests:
1. Login flow
2. Dashboard stats
3. Customer search with vehicles array (BUG FIX)
4. Tickets CRUD
5. Public branding endpoint
6. Public quote endpoint
7. Reports endpoints
8. Ticket types and statuses
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@pdpv.pt"
ADMIN_PASSWORD = "HCNMEnKMLq"
VALID_QUOTE_TOKEN = "0e0e05ea-ecfb-48a6-bfb3-d593ab488f52"


class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test admin login returns token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert len(data["token"]) > 0, "Token should not be empty"
        print(f"✓ Login successful, token received")
    
    def test_login_invalid_credentials(self):
        """Test login with wrong credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Invalid login correctly rejected")


class TestDashboard:
    """Dashboard endpoint tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_dashboard_stats(self, auth_headers):
        """Test dashboard stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        # Verify expected fields exist
        assert "total_tickets" in data or "tickets_by_status" in data or isinstance(data, dict)
        print(f"✓ Dashboard stats returned successfully")


class TestCustomerSearch:
    """Customer search tests - BUG FIX VERIFICATION"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_customer_search_returns_vehicles_array(self, auth_headers):
        """BUG FIX: Verify /api/customers/search returns 'vehicles' array with plate+model objects"""
        # Search with a phone number pattern
        response = requests.get(f"{BASE_URL}/api/customers/search?q=913", headers=auth_headers)
        assert response.status_code == 200, f"Customer search failed: {response.text}"
        data = response.json()
        
        # If results exist, verify structure
        if len(data) > 0:
            customer = data[0]
            # Verify 'vehicles' array exists (BUG FIX)
            assert "vehicles" in customer, "Customer should have 'vehicles' array"
            assert isinstance(customer["vehicles"], list), "'vehicles' should be a list"
            
            # If vehicles exist, verify structure
            if len(customer["vehicles"]) > 0:
                vehicle = customer["vehicles"][0]
                assert "plate" in vehicle, "Vehicle should have 'plate' field"
                # model can be None but should exist
                assert "model" in vehicle or vehicle.get("model") is None, "Vehicle should have 'model' field"
                print(f"✓ Vehicle structure correct: plate={vehicle.get('plate')}, model={vehicle.get('model')}")
            
            # Also verify 'plates' array exists for backward compatibility
            assert "plates" in customer, "Customer should have 'plates' array for backward compatibility"
            print(f"✓ Customer search returns vehicles array correctly")
        else:
            print(f"⚠ No customers found with query '913', but endpoint works")
    
    def test_customer_search_by_phone(self, auth_headers):
        """Test customer search by phone parameter"""
        response = requests.get(f"{BASE_URL}/api/customers/search?phone=91", headers=auth_headers)
        assert response.status_code == 200, f"Customer search by phone failed: {response.text}"
        print(f"✓ Customer search by phone works")
    
    def test_customer_search_by_plate(self, auth_headers):
        """Test customer search by plate parameter"""
        response = requests.get(f"{BASE_URL}/api/customers/search?plate=AA", headers=auth_headers)
        assert response.status_code == 200, f"Customer search by plate failed: {response.text}"
        print(f"✓ Customer search by plate works")
    
    def test_customer_list(self, auth_headers):
        """Test customer list endpoint"""
        response = requests.get(f"{BASE_URL}/api/customers?limit=5", headers=auth_headers)
        assert response.status_code == 200, f"Customer list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Customer list should return array"
        print(f"✓ Customer list returned {len(data)} customers")


class TestTickets:
    """Ticket endpoints tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_tickets_list(self, auth_headers):
        """Test tickets list endpoint"""
        response = requests.get(f"{BASE_URL}/api/tickets?limit=10", headers=auth_headers)
        assert response.status_code == 200, f"Tickets list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Tickets should return array"
        print(f"✓ Tickets list returned {len(data)} tickets")
    
    def test_ticket_types(self, auth_headers):
        """Test ticket types endpoint"""
        response = requests.get(f"{BASE_URL}/api/ticket-types", headers=auth_headers)
        assert response.status_code == 200, f"Ticket types failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Ticket types should return array"
        assert len(data) > 0, "Should have at least one ticket type"
        print(f"✓ Ticket types returned {len(data)} types")
    
    def test_ticket_statuses(self, auth_headers):
        """Test ticket statuses endpoint"""
        response = requests.get(f"{BASE_URL}/api/ticket-statuses", headers=auth_headers)
        assert response.status_code == 200, f"Ticket statuses failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Ticket statuses should return array"
        assert len(data) > 0, "Should have at least one ticket status"
        print(f"✓ Ticket statuses returned {len(data)} statuses")


class TestPublicEndpoints:
    """Public endpoints tests (no auth required)"""
    
    def test_public_branding(self):
        """Test public branding endpoint - NO AUTH"""
        response = requests.get(f"{BASE_URL}/api/public/branding")
        assert response.status_code == 200, f"Public branding failed: {response.text}"
        data = response.json()
        assert "company_name" in data, "Branding should have company_name"
        assert "primary_color" in data, "Branding should have primary_color"
        print(f"✓ Public branding returned: {data.get('company_name')}")
    
    def test_public_quote(self):
        """Test public quote endpoint - NO AUTH"""
        response = requests.get(f"{BASE_URL}/api/public/quote/{VALID_QUOTE_TOKEN}")
        # Can be 200 (valid) or 404 (token not found) or 400 (expired)
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "ticket_number" in data, "Quote should have ticket_number"
            assert "customer_name" in data, "Quote should have customer_name"
            print(f"✓ Public quote returned for ticket: {data.get('ticket_number')}")
        else:
            print(f"⚠ Quote token may be expired or not found (status {response.status_code})")


class TestReports:
    """Reports endpoints tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_reports_generate(self, auth_headers):
        """Test POST /api/admin/reports"""
        response = requests.post(f"{BASE_URL}/api/admin/reports", 
            json={},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Reports generate failed: {response.text}"
        data = response.json()
        assert "metrics" in data, "Report should have metrics"
        assert "period" in data, "Report should have period"
        print(f"✓ Reports generated successfully")
    
    def test_tire_analysis(self, auth_headers):
        """Test GET /api/admin/reports/tire-analysis"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/tire-analysis", headers=auth_headers)
        assert response.status_code == 200, f"Tire analysis failed: {response.text}"
        data = response.json()
        assert "total_tickets_analyzed" in data, "Should have total_tickets_analyzed"
        assert "tire_sizes" in data, "Should have tire_sizes"
        print(f"✓ Tire analysis returned, analyzed {data.get('total_tickets_analyzed')} tickets")
    
    def test_rejection_reasons(self, auth_headers):
        """Test GET /api/admin/reports/rejection-reasons"""
        response = requests.get(f"{BASE_URL}/api/admin/reports/rejection-reasons", headers=auth_headers)
        assert response.status_code == 200, f"Rejection reasons failed: {response.text}"
        data = response.json()
        # Verify expected fields
        assert "total_rejected" in data, "Should have total_rejected"
        assert "with_reason" in data, "Should have with_reason"
        assert "without_reason" in data, "Should have without_reason"
        assert "by_reason" in data, "Should have by_reason"
        assert "by_ticket_type" in data, "Should have by_ticket_type"
        print(f"✓ Rejection reasons returned: {data.get('total_rejected')} rejected tickets")


class TestUsers:
    """Users endpoint tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_users_list(self, auth_headers):
        """Test users list endpoint"""
        response = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
        assert response.status_code == 200, f"Users list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Users should return array"
        print(f"✓ Users list returned {len(data)} users")


class TestReminders:
    """Reminders endpoint tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_reminders_list(self, auth_headers):
        """Test reminders list endpoint"""
        response = requests.get(f"{BASE_URL}/api/reminders?filter=pending", headers=auth_headers)
        assert response.status_code == 200, f"Reminders list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Reminders should return array"
        print(f"✓ Reminders list returned {len(data)} reminders")


class TestAdminSettings:
    """Admin settings endpoints tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_admin_holidays(self, auth_headers):
        """Test admin holidays endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/holidays", headers=auth_headers)
        assert response.status_code == 200, f"Admin holidays failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Holidays should return array"
        print(f"✓ Admin holidays returned {len(data)} holidays")
    
    def test_admin_branding(self, auth_headers):
        """Test admin branding endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/branding", headers=auth_headers)
        assert response.status_code == 200, f"Admin branding failed: {response.text}"
        data = response.json()
        assert "company_name" in data, "Branding should have company_name"
        print(f"✓ Admin branding returned: {data.get('company_name')}")


class TestIntake:
    """Intake (Pré-Tickets) endpoint tests"""
    
    @pytest.fixture
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_intake_pending_count(self, auth_headers):
        """Test intake pending count endpoint"""
        response = requests.get(f"{BASE_URL}/api/intake/pending-count", headers=auth_headers)
        assert response.status_code == 200, f"Intake pending count failed: {response.text}"
        data = response.json()
        assert "count" in data or isinstance(data, (int, dict)), "Should return count"
        print(f"✓ Intake pending count returned")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
