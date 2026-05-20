#!/usr/bin/env python3

import requests
import sys
from datetime import datetime
import json

class PDPVTicketsAPITester:
    def __init__(self, base_url="https://intake-ai-gateway.preview.emergentagent.com"):
        self.base_url = base_url
        self.admin_token = None
        self.supervisor_token = None
        self.agent_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, test_name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name} - PASSED")
        else:
            print(f"❌ {test_name} - FAILED: {details}")
        
        self.test_results.append({
            "test_name": test_name,
            "success": success,
            "details": details
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if headers:
            test_headers.update(headers)

        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {method} {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.log_result(name, True)
                try:
                    return response.json() if response.text else {}
                except:
                    return {}
            else:
                error_detail = f"Expected {expected_status}, got {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        if 'detail' in error_data:
                            error_detail += f" - {error_data['detail']}"
                    except:
                        error_detail += f" - {response.text[:200]}"
                
                self.log_result(name, False, error_detail)
                return {}

        except requests.exceptions.Timeout:
            self.log_result(name, False, "Request timeout (30s)")
            return {}
        except Exception as e:
            self.log_result(name, False, f"Request error: {str(e)}")
            return {}

    def test_seed_data(self):
        """Test seed data creation"""
        print("\n=== TESTING SEED DATA ===")
        result = self.run_test("Seed Data Creation", "POST", "seed", 200)
        return result

    def test_authentication(self):
        """Test authentication endpoints"""
        print("\n=== TESTING AUTHENTICATION ===")
        
        # Test admin login
        admin_response = self.run_test(
            "Admin Login",
            "POST", 
            "auth/login",
            200,
            {"email": "admin@pdpv.pt", "password": "admin123"}
        )
        
        if admin_response and 'token' in admin_response:
            self.admin_token = admin_response['token']
            print(f"   Admin token received: {self.admin_token[:20]}...")
        
        # Test supervisor login
        supervisor_response = self.run_test(
            "Supervisor Login",
            "POST",
            "auth/login", 
            200,
            {"email": "supervisor@pdpv.pt", "password": "super123"}
        )
        
        if supervisor_response and 'token' in supervisor_response:
            self.supervisor_token = supervisor_response['token']
        
        # Test agent login
        agent_response = self.run_test(
            "Agent Login",
            "POST",
            "auth/login",
            200,
            {"email": "agente@pdpv.pt", "password": "agente123"}
        )
        
        if agent_response and 'token' in agent_response:
            self.agent_token = agent_response['token']
        
        # Test invalid login
        self.run_test(
            "Invalid Login",
            "POST",
            "auth/login",
            401,
            {"email": "invalid@test.com", "password": "wrong"}
        )

    def test_dashboard_stats(self):
        """Test dashboard statistics"""
        print("\n=== TESTING DASHBOARD ===")
        
        if not self.admin_token:
            print("❌ Skipping dashboard tests - no admin token")
            return
            
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        stats = self.run_test(
            "Dashboard Stats",
            "GET",
            "dashboard/stats",
            200,
            headers=headers
        )
        
        if stats:
            print(f"   Dashboard stats: {stats}")
            return stats
        return {}

    def test_user_management(self):
        """Test user management endpoints"""
        print("\n=== TESTING USER MANAGEMENT ===")
        
        if not self.admin_token:
            print("❌ Skipping user management tests - no admin token") 
            return
            
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        # List users
        users = self.run_test(
            "List Users", 
            "GET",
            "users",
            200,
            headers=headers
        )
        
        if users:
            print(f"   Found {len(users)} users")
        
        # Create test user
        new_user_data = {
            "email": "test@pdpv.pt",
            "password": "test123",
            "name": "Test User",
            "role": "AGENT"
        }
        
        user_created = self.run_test(
            "Create User",
            "POST",
            "users",
            200,
            new_user_data,
            headers
        )
        
        return users

    def test_ticket_operations(self):
        """Test ticket CRUD operations"""
        print("\n=== TESTING TICKET OPERATIONS ===")
        
        if not self.admin_token:
            print("❌ Skipping ticket tests - no admin token")
            return
            
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        # Create ticket
        ticket_data = {
            "customer_phone": "912345678",
            "customer_name": "João Silva",
            "customer_email": "joao@test.pt", 
            "vehicle_plate": "AA-11-BB",
            "type": "INFORMACAO",
            "channel": "TELEFONE",
            "priority": "NORMAL",
            "description": "Pedido de informação sobre serviço"
        }
        
        created_ticket = self.run_test(
            "Create Ticket",
            "POST", 
            "tickets",
            200,
            ticket_data,
            headers
        )
        
        ticket_id = None
        if created_ticket and 'id' in created_ticket:
            ticket_id = created_ticket['id']
            print(f"   Created ticket ID: {ticket_id}")
        
        # List tickets
        tickets = self.run_test(
            "List Tickets",
            "GET",
            "tickets",
            200,
            headers=headers
        )
        
        if tickets:
            print(f"   Found {len(tickets)} tickets")
        
        # Get specific ticket
        if ticket_id:
            ticket = self.run_test(
                "Get Ticket Details",
                "GET",
                f"tickets/{ticket_id}",
                200,
                headers=headers
            )
        
        # Update ticket
        if ticket_id:
            update_data = {"status": "TRIAGEM"}
            self.run_test(
                "Update Ticket",
                "PUT",
                f"tickets/{ticket_id}",
                200,
                update_data,
                headers
            )
        
        return ticket_id

    def test_messages_and_notes(self, ticket_id):
        """Test messages and notes functionality"""
        print("\n=== TESTING MESSAGES & NOTES ===")
        
        if not self.admin_token or not ticket_id:
            print("❌ Skipping messages tests - missing token or ticket ID")
            return
            
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        # Add message
        message_data = {
            "body": "Obrigado pelo seu contacto. Iremos responder brevemente.",
            "channel": "EMAIL"
        }
        
        self.run_test(
            "Send Message",
            "POST",
            f"tickets/{ticket_id}/messages",
            200,
            message_data,
            headers
        )
        
        # List messages
        self.run_test(
            "List Messages",
            "GET",
            f"tickets/{ticket_id}/messages",
            200,
            headers=headers
        )
        
        # Add note
        note_data = {
            "body": "Cliente contactou por telefone. Parece ser um pedido simples."
        }
        
        self.run_test(
            "Add Note",
            "POST", 
            f"tickets/{ticket_id}/notes",
            200,
            note_data,
            headers
        )
        
        # List notes
        self.run_test(
            "List Notes",
            "GET",
            f"tickets/{ticket_id}/notes", 
            200,
            headers=headers
        )

    def test_webhooks(self):
        """Test webhook endpoints"""
        print("\n=== TESTING WEBHOOKS ===")
        
        # WhatsApp webhook
        whatsapp_data = {
            "phone": "912345679",
            "name": "Maria Santos",
            "message_text": "Olá, preciso de informação sobre pneus",
            "timestamp": datetime.now().isoformat()
        }
        
        self.run_test(
            "WhatsApp Webhook",
            "POST",
            "webhook/whatsapp/inbound",
            200,
            whatsapp_data
        )
        
        # Telegram webhook  
        telegram_data = {
            "sender_name": "Ana Costa",
            "sender_id": "123456789",
            "transcript_text": "Transcrição de áudio: Cliente quer agendar revisão",
            "timestamp": datetime.now().isoformat()
        }
        
        self.run_test(
            "Telegram Webhook",
            "POST",
            "webhook/telegram/transcribed",
            200,
            telegram_data
        )

    def test_role_based_access(self):
        """Test role-based access control"""
        print("\n=== TESTING RBAC ===")
        
        if not self.agent_token:
            print("❌ Skipping RBAC tests - no agent token")
            return
            
        # Test agent trying to access admin endpoint
        headers = {'Authorization': f'Bearer {self.agent_token}'}
        
        self.run_test(
            "Agent Access to User Management (should fail)",
            "GET",
            "users", 
            403,  # Should be forbidden
            headers=headers
        )

    def run_comprehensive_test(self):
        """Run all tests"""
        print("🚀 Starting PDPV Tickets API Comprehensive Test")
        print(f"   Backend URL: {self.base_url}")
        print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Test sequence
        self.test_seed_data()
        self.test_authentication() 
        self.test_dashboard_stats()
        self.test_user_management()
        ticket_id = self.test_ticket_operations()
        self.test_messages_and_notes(ticket_id)
        self.test_webhooks()
        self.test_role_based_access()
        
        # Print summary
        print(f"\n📊 TEST SUMMARY")
        print(f"   Tests Run: {self.tests_run}")
        print(f"   Tests Passed: {self.tests_passed}")
        print(f"   Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"   Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "   Success Rate: 0%")
        
        # Detailed failures
        failed_tests = [r for r in self.test_results if not r['success']]
        if failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"   • {test['test_name']}: {test['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = PDPVTicketsAPITester()
    success = tester.run_comprehensive_test()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())