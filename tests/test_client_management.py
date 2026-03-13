#!/usr/bin/env python3
"""
Client Management System Backend API Tests
Tests the backend APIs for client intake, management, CMS settings, and calendar round-robin.
"""

import requests
import json
import sys
from typing import Optional, Dict, Any

# Base URL for the API
BASE_URL = "https://condescending-wozniak-3.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"

class ClientManagementTester:
    def __init__(self):
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {
            "Content-Type": "application/json"
        }
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, details: str, response_data: Any = None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{status} {test_name}")
        print(f"Details: {details}")
        if response_data:
            print(f"Response: {json.dumps(response_data, indent=2)}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "response": response_data
        })
    
    def test_admin_login(self) -> bool:
        """Test admin authentication"""
        print("\n" + "="*60)
        print("TESTING: Admin Authentication API")
        print("="*60)
        
        try:
            url = f"{BASE_URL}/auth/login"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            print(f"POST {url}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if "access_token" in data and "token_type" in data:
                    self.token = data["access_token"]
                    self.headers["Authorization"] = f"Bearer {self.token}"
                    
                    self.log_test(
                        "Admin Authentication API",
                        True,
                        f"Login successful. Token received and authenticated.",
                        {
                            "status_code": response.status_code,
                            "token_type": data.get("token_type"),
                            "user_info": data.get("user", {})
                        }
                    )
                    return True
                else:
                    self.log_test(
                        "Admin Authentication API",
                        False,
                        "Login response missing required fields (access_token, token_type)",
                        data
                    )
                    return False
            else:
                error_msg = f"Login failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f": {error_data.get('detail', 'Unknown error')}"
                except:
                    error_msg += f": {response.text}"
                
                self.log_test(
                    "Admin Authentication API",
                    False,
                    error_msg,
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Admin Authentication API",
                False,
                f"Error during login: {str(e)}",
                None
            )
            return False
    
    def test_client_intake_hot_lead(self) -> bool:
        """TEST 1: Public Client Intake - HOT Lead (no auth required)"""
        print("\n" + "="*60)
        print("TESTING: Client Intake API - HOT Lead Creation")
        print("="*60)
        
        try:
            url = f"{BASE_URL}/clients/intake"
            
            # HOT lead criteria: score >= 37
            payload = {
                "first_name": "John",
                "last_name": "Smith",
                "email": "john.smith@example.com",
                "phone": "555-123-4567",
                "creditScore": "poor",  # +12 points
                "timeline": "asap",      # +12 points
                "budget": "aggressive",  # +11 points
                "experience": "other-company",  # +12 points
                "decision": "me-alone",  # +12 points
                "zip_code": "90210",
                "source": "website"
            }
            # Total score: 12+12+11+12+12 = 59 (HOT lead)
            
            print(f"POST {url}")
            print(f"Creating HOT lead with score 59 (poor credit, asap timeline, aggressive budget)")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ["client_id", "lead_status", "score", "redirect_url", "cta"]
                missing_fields = [field for field in required_fields if field not in data]
                
                correct_status = data.get("lead_status") == "hot"
                correct_score = data.get("score") == 59
                has_redirect = "redirect_url" in data and data["redirect_url"]
                correct_cta = "Get My Credit Report" in data.get("cta", "")
                
                if not missing_fields and correct_status and correct_score and has_redirect and correct_cta:
                    self.log_test(
                        "Client Intake API - HOT Lead",
                        True,
                        f"✅ Successfully created HOT lead with score {data.get('score')}. Lead status: {data.get('lead_status')}, Redirect: Credit Report URL",
                        {
                            "status_code": response.status_code,
                            "client_id": data.get("client_id"),
                            "lead_status": data.get("lead_status"),
                            "score": data.get("score"),
                            "redirect_type": "credit_report",
                            "cta": data.get("cta")
                        }
                    )
                    return True
                else:
                    issues = []
                    if missing_fields:
                        issues.append(f"Missing fields: {missing_fields}")
                    if not correct_status:
                        issues.append(f"Wrong lead_status: expected 'hot', got '{data.get('lead_status')}'")
                    if not correct_score:
                        issues.append(f"Wrong score: expected 59, got {data.get('score')}")
                    if not has_redirect:
                        issues.append("Missing or empty redirect_url")
                    if not correct_cta:
                        issues.append(f"Wrong CTA: expected credit report CTA, got '{data.get('cta')}'")
                    
                    self.log_test(
                        "Client Intake API - HOT Lead",
                        False,
                        f"❌ HOT lead creation issues: {'; '.join(issues)}",
                        {
                            "status_code": response.status_code,
                            "expected_score": 59,
                            "expected_status": "hot",
                            "actual_data": data,
                            "issues": issues
                        }
                    )
                    return False
            else:
                error_msg = f"❌ Client intake failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f": {error_data.get('detail', 'Unknown error')}"
                except:
                    error_msg += f": {response.text}"
                
                self.log_test(
                    "Client Intake API - HOT Lead",
                    False,
                    error_msg,
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Client Intake API - HOT Lead",
                False,
                f"❌ Error: {str(e)}",
                None
            )
            return False
    
    def test_client_intake_cold_lead(self) -> bool:
        """TEST 2: Public Client Intake - WARM Lead (no auth required)"""
        print("\n" + "="*60)
        print("TESTING: Client Intake API - WARM Lead Creation")
        print("="*60)
        
        try:
            url = f"{BASE_URL}/clients/intake"
            
            # COLD lead criteria: score < 25
            payload = {
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane.doe@example.com",
                "phone": "555-987-6543",
                "creditScore": "excellent",  # +3 points
                "timeline": "6months+",      # +4 points
                "budget": "unsure",          # +7 points
                "experience": "never",       # +8 points
                "decision": "family-input",  # +4 points
                "zip_code": "10001",
                "source": "google"
            }
            # Total score: 3+4+7+8+4 = 26 (WARM lead, but let's test boundary)
            
            print(f"POST {url}")
            print(f"Creating WARM lead with score 26 (excellent credit, 6months+ timeline, unsure budget)")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ["client_id", "lead_status", "score", "redirect_url"]
                missing_fields = [field for field in required_fields if field not in data]
                
                correct_status = data.get("lead_status") == "warm"  # 26 points = warm
                correct_score = data.get("score") == 26
                has_redirect = "redirect_url" in data and data["redirect_url"]
                has_calendar_id = "assigned_calendar_id" in data  # Should get calendar assignment
                
                if not missing_fields and correct_status and correct_score and has_redirect:
                    self.log_test(
                        "Client Intake API - WARM Lead",
                        True,
                        f"✅ Successfully created WARM lead with score {data.get('score')}. Lead status: {data.get('lead_status')}, Redirect: Calendar URL",
                        {
                            "status_code": response.status_code,
                            "client_id": data.get("client_id"),
                            "lead_status": data.get("lead_status"),
                            "score": data.get("score"),
                            "redirect_type": "calendar",
                            "has_calendar_assignment": has_calendar_id
                        }
                    )
                    return True
                else:
                    issues = []
                    if missing_fields:
                        issues.append(f"Missing fields: {missing_fields}")
                    if not correct_status:
                        issues.append(f"Wrong lead_status: expected 'warm', got '{data.get('lead_status')}'")
                    if not correct_score:
                        issues.append(f"Wrong score: expected 26, got {data.get('score')}")
                    if not has_redirect:
                        issues.append("Missing or empty redirect_url")
                    
                    self.log_test(
                        "Client Intake API - WARM Lead",
                        False,
                        f"❌ WARM lead creation issues: {'; '.join(issues)}",
                        {
                            "status_code": response.status_code,
                            "expected_score": 26,
                            "expected_status": "warm",
                            "actual_data": data,
                            "issues": issues
                        }
                    )
                    return False
            else:
                error_msg = f"❌ Client intake failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f": {error_data.get('detail', 'Unknown error')}"
                except:
                    error_msg += f": {response.text}"
                
                self.log_test(
                    "Client Intake API - WARM Lead",
                    False,
                    error_msg,
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Client Intake API - WARM Lead",
                False,
                f"❌ Error: {str(e)}",
                None
            )
            return False
    
    def test_client_management_apis(self) -> tuple[bool, list]:
        """TEST 3: Client Management APIs (auth required)"""
        print("\n" + "="*60)
        print("TESTING: Client Management APIs - List & Stats")
        print("="*60)
        
        if not self.token:
            self.log_test(
                "Client Management APIs",
                False,
                "❌ Cannot test - no authentication token available",
                None
            )
            return False, []
        
        try:
            # Test GET /api/admin/clients
            clients_url = f"{BASE_URL}/admin/clients"
            print(f"GET {clients_url}")
            print(f"Headers: Authorization: Bearer {self.token[:20]}...")
            
            clients_response = requests.get(clients_url, headers=self.headers, timeout=30)
            print(f"Clients Status Code: {clients_response.status_code}")
            
            # Test GET /api/admin/clients/stats
            stats_url = f"{BASE_URL}/admin/clients/stats"
            print(f"GET {stats_url}")
            
            stats_response = requests.get(stats_url, headers=self.headers, timeout=30)
            print(f"Stats Status Code: {stats_response.status_code}")
            
            clients_success = clients_response.status_code == 200
            stats_success = stats_response.status_code == 200
            
            if clients_success and stats_success:
                clients_data = clients_response.json()
                stats_data = stats_response.json()
                
                # Verify clients response
                clients_valid = isinstance(clients_data, list)
                
                # Verify stats response structure
                required_stats = ["total", "by_lead_status", "by_period", "income"]
                missing_stats = [field for field in required_stats if field not in stats_data]
                
                if clients_valid and not missing_stats:
                    client_count = len(clients_data)
                    total_from_stats = stats_data.get("total", 0)
                    
                    self.log_test(
                        "Client Management APIs",
                        True,
                        f"✅ Client management APIs working correctly. Found {client_count} clients, stats show total: {total_from_stats}. Stats include income calculations and lead status breakdown.",
                        {
                            "clients_status": clients_response.status_code,
                            "stats_status": stats_response.status_code,
                            "client_count": client_count,
                            "stats_total": total_from_stats,
                            "stats_structure": list(stats_data.keys()),
                            "sample_client": clients_data[0] if clients_data else None
                        }
                    )
                    return True, clients_data
                else:
                    issues = []
                    if not clients_valid:
                        issues.append(f"Clients response not a list: {type(clients_data)}")
                    if missing_stats:
                        issues.append(f"Stats missing fields: {missing_stats}")
                    
                    self.log_test(
                        "Client Management APIs",
                        False,
                        f"❌ Response structure issues: {'; '.join(issues)}",
                        {
                            "clients_valid": clients_valid,
                            "missing_stats": missing_stats,
                            "clients_data": clients_data,
                            "stats_data": stats_data
                        }
                    )
                    return False, []
            else:
                issues = []
                if not clients_success:
                    issues.append(f"Clients API failed: {clients_response.status_code}")
                if not stats_success:
                    issues.append(f"Stats API failed: {stats_response.status_code}")
                
                self.log_test(
                    "Client Management APIs",
                    False,
                    f"❌ API failures: {'; '.join(issues)}",
                    {
                        "clients_status": clients_response.status_code,
                        "stats_status": stats_response.status_code,
                        "clients_response": clients_response.text if not clients_success else None,
                        "stats_response": stats_response.text if not stats_success else None
                    }
                )
                return False, []
                
        except Exception as e:
            self.log_test(
                "Client Management APIs",
                False,
                f"❌ Error: {str(e)}",
                None
            )
            return False, []
    
    def test_client_operations(self, clients_data: list) -> bool:
        """TEST 4: Client Operations - Get Single, Update, Notes, Credits"""
        print("\n" + "="*60)
        print("TESTING: Client Operations - Individual Client APIs")
        print("="*60)
        
        if not self.token:
            self.log_test(
                "Client Operations",
                False,
                "❌ Cannot test - no authentication token available",
                None
            )
            return False
        
        if not clients_data:
            print("SKIPPED: No clients available to test operations")
            return True  # Not a failure, just no data
        
        try:
            # Use the first client for testing
            test_client = clients_data[0]
            client_id = test_client.get("id")
            client_name = f"{test_client.get('first_name', 'Unknown')} {test_client.get('last_name', 'Client')}"
            
            if not client_id:
                self.log_test(
                    "Client Operations",
                    False,
                    "❌ Cannot test - client missing 'id' field",
                    test_client
                )
                return False
            
            results = []
            
            # Test 1: GET single client
            get_url = f"{BASE_URL}/admin/clients/{client_id}"
            get_response = requests.get(get_url, headers=self.headers, timeout=30)
            
            if get_response.status_code == 200:
                results.append("✅ GET single client")
            else:
                results.append(f"❌ GET single client failed: {get_response.status_code}")
            
            # Test 2: UPDATE client status
            update_url = f"{BASE_URL}/admin/clients/{client_id}"
            update_payload = {"status": "consultation_scheduled"}
            update_response = requests.put(update_url, json=update_payload, headers=self.headers, timeout=30)
            
            if update_response.status_code == 200:
                results.append("✅ UPDATE client status")
            else:
                results.append(f"❌ UPDATE client failed: {update_response.status_code}")
            
            # Test 3: GET client agreements
            agreements_url = f"{BASE_URL}/admin/clients/{client_id}/agreements"
            agreements_response = requests.get(agreements_url, headers=self.headers, timeout=30)
            
            if agreements_response.status_code == 200:
                results.append("✅ GET client agreements")
            else:
                results.append(f"❌ GET agreements failed: {agreements_response.status_code}")
            
            # Test 4: POST client note
            notes_url = f"{BASE_URL}/admin/clients/{client_id}/notes"
            note_payload = {
                "note_text": "Test note for client operations testing",
                "note_type": "general",
                "is_important": False
            }
            notes_response = requests.post(notes_url, json=note_payload, headers=self.headers, timeout=30)
            
            if notes_response.status_code == 200:
                results.append("✅ POST client note")
            else:
                results.append(f"❌ POST note failed: {notes_response.status_code}")
            
            # Test 5: GET client credits
            credits_url = f"{BASE_URL}/admin/clients/{client_id}/credits"
            credits_response = requests.get(credits_url, headers=self.headers, timeout=30)
            
            if credits_response.status_code == 200:
                results.append("✅ GET client credits")
            else:
                results.append(f"❌ GET credits failed: {credits_response.status_code}")
            
            # Test 6: POST client credit
            post_credit_url = f"{BASE_URL}/admin/clients/{client_id}/credits"
            credit_payload = {
                "credit_type": "month",
                "amount": 2,
                "reason": "Testing client credit system"
            }
            post_credit_response = requests.post(post_credit_url, json=credit_payload, headers=self.headers, timeout=30)
            
            if post_credit_response.status_code == 200:
                results.append("✅ POST client credit")
            else:
                results.append(f"❌ POST credit failed: {post_credit_response.status_code}")
            
            # Evaluate results
            passed_tests = sum(1 for result in results if result.startswith("✅"))
            total_tests = len(results)
            success = passed_tests == total_tests
            
            self.log_test(
                "Client Operations",
                success,
                f"{'✅' if success else '❌'} Client operations: {passed_tests}/{total_tests} passed. Tested with client: {client_name}. " + "; ".join(results),
                {
                    "client_id": client_id,
                    "client_name": client_name,
                    "total_operations": total_tests,
                    "passed_operations": passed_tests,
                    "results": results
                }
            )
            
            return success
                
        except Exception as e:
            self.log_test(
                "Client Operations",
                False,
                f"❌ Error: {str(e)}",
                None
            )
            return False
    
    def test_cms_settings_apis(self) -> bool:
        """TEST 5: CMS Settings APIs (auth required)"""
        print("\n" + "="*60)
        print("TESTING: CMS Settings APIs")
        print("="*60)
        
        if not self.token:
            self.log_test(
                "CMS Settings APIs",
                False,
                "❌ Cannot test - no authentication token available",
                None
            )
            return False
        
        try:
            results = []
            
            # Test 1: GET all CMS settings
            get_all_url = f"{BASE_URL}/admin/cms-settings"
            get_all_response = requests.get(get_all_url, headers=self.headers, timeout=30)
            
            if get_all_response.status_code == 200:
                settings_data = get_all_response.json()
                if isinstance(settings_data, list):
                    results.append(f"✅ GET all settings ({len(settings_data)} settings)")
                else:
                    results.append(f"❌ GET all settings wrong format: {type(settings_data)}")
            else:
                results.append(f"❌ GET all settings failed: {get_all_response.status_code}")
            
            # Test 2: UPDATE credit report URL
            credit_url_update = f"{BASE_URL}/admin/cms-settings/credit_report_url"
            credit_payload = {
                "setting_value": "https://credlocity.scorexer.com/scorefusion/scorefusion-signup.jsp?code=test123",
                "description": "Updated credit report URL for testing"
            }
            credit_response = requests.put(credit_url_update, json=credit_payload, headers=self.headers, timeout=30)
            
            if credit_response.status_code == 200:
                results.append("✅ UPDATE credit report URL")
            else:
                results.append(f"❌ UPDATE credit URL failed: {credit_response.status_code}")
            
            # Test 3: UPDATE default calendar URL
            calendar_url_update = f"{BASE_URL}/admin/cms-settings/default_calendar_url"
            calendar_payload = {
                "setting_value": "https://calendly.com/credlocity/test-calendar",
                "description": "Updated default calendar URL for testing"
            }
            calendar_response = requests.put(calendar_url_update, json=calendar_payload, headers=self.headers, timeout=30)
            
            if calendar_response.status_code == 200:
                results.append("✅ UPDATE default calendar URL")
            else:
                results.append(f"❌ UPDATE calendar URL failed: {calendar_response.status_code}")
            
            # Test 4: GET specific setting
            get_specific_url = f"{BASE_URL}/admin/cms-settings/credit_report_url"
            get_specific_response = requests.get(get_specific_url, headers=self.headers, timeout=30)
            
            if get_specific_response.status_code == 200:
                setting_data = get_specific_response.json()
                if setting_data.get("setting_key") == "credit_report_url":
                    results.append("✅ GET specific setting")
                else:
                    results.append(f"❌ GET specific setting wrong key: {setting_data.get('setting_key')}")
            else:
                results.append(f"❌ GET specific setting failed: {get_specific_response.status_code}")
            
            # Evaluate results
            passed_tests = sum(1 for result in results if result.startswith("✅"))
            total_tests = len(results)
            success = passed_tests == total_tests
            
            self.log_test(
                "CMS Settings APIs",
                success,
                f"{'✅' if success else '❌'} CMS Settings: {passed_tests}/{total_tests} passed. " + "; ".join(results),
                {
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "results": results
                }
            )
            
            return success
                
        except Exception as e:
            self.log_test(
                "CMS Settings APIs",
                False,
                f"❌ Error: {str(e)}",
                None
            )
            return False
    
    def test_calendar_round_robin_apis(self) -> bool:
        """TEST 6: Calendar Round-Robin APIs (auth required)"""
        print("\n" + "="*60)
        print("TESTING: Calendar Round-Robin APIs")
        print("="*60)
        
        if not self.token:
            self.log_test(
                "Calendar Round-Robin APIs",
                False,
                "❌ Cannot test - no authentication token available",
                None
            )
            return False
        
        try:
            results = []
            created_calendar_id = None
            
            # Test 1: GET all calendars
            get_calendars_url = f"{BASE_URL}/admin/calendars"
            get_calendars_response = requests.get(get_calendars_url, headers=self.headers, timeout=30)
            
            if get_calendars_response.status_code == 200:
                calendars_data = get_calendars_response.json()
                if isinstance(calendars_data, list):
                    results.append(f"✅ GET calendars ({len(calendars_data)} calendars)")
                else:
                    results.append(f"❌ GET calendars wrong format: {type(calendars_data)}")
            else:
                results.append(f"❌ GET calendars failed: {get_calendars_response.status_code}")
            
            # Test 2: CREATE calendar
            create_calendar_url = f"{BASE_URL}/admin/calendars"
            create_payload = {
                "name": "Test Calendar - Delete Me",
                "url": "https://calendly.com/test-calendar-delete-me",
                "is_active": True,
                "weight": 1
            }
            create_response = requests.post(create_calendar_url, json=create_payload, headers=self.headers, timeout=30)
            
            if create_response.status_code == 200:
                create_data = create_response.json()
                created_calendar_id = create_data.get("id")
                results.append("✅ CREATE calendar")
            else:
                results.append(f"❌ CREATE calendar failed: {create_response.status_code}")
            
            # Test 3: GET next calendar (round-robin)
            get_next_url = f"{BASE_URL}/admin/calendars/next"
            get_next_response = requests.get(get_next_url, headers=self.headers, timeout=30)
            
            if get_next_response.status_code == 200:
                next_data = get_next_response.json()
                if "url" in next_data:
                    results.append("✅ GET next calendar (round-robin)")
                else:
                    results.append(f"❌ GET next calendar missing URL: {next_data}")
            else:
                results.append(f"❌ GET next calendar failed: {get_next_response.status_code}")
            
            # Test 4: UPDATE calendar (if created successfully)
            if created_calendar_id:
                update_calendar_url = f"{BASE_URL}/admin/calendars/{created_calendar_id}"
                update_payload = {"weight": 2, "name": "Updated Test Calendar"}
                update_response = requests.put(update_calendar_url, json=update_payload, headers=self.headers, timeout=30)
                
                if update_response.status_code == 200:
                    results.append("✅ UPDATE calendar")
                else:
                    results.append(f"❌ UPDATE calendar failed: {update_response.status_code}")
            
            # Test 5: DELETE calendar (cleanup)
            if created_calendar_id:
                delete_calendar_url = f"{BASE_URL}/admin/calendars/{created_calendar_id}"
                delete_response = requests.delete(delete_calendar_url, headers=self.headers, timeout=30)
                
                if delete_response.status_code == 200:
                    results.append("✅ DELETE calendar")
                else:
                    results.append(f"❌ DELETE calendar failed: {delete_response.status_code}")
            
            # Evaluate results
            passed_tests = sum(1 for result in results if result.startswith("✅"))
            total_tests = len(results)
            success = passed_tests == total_tests
            
            self.log_test(
                "Calendar Round-Robin APIs",
                success,
                f"{'✅' if success else '❌'} Calendar APIs: {passed_tests}/{total_tests} passed. " + "; ".join(results),
                {
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "created_calendar_id": created_calendar_id,
                    "results": results
                }
            )
            
            return success
                
        except Exception as e:
            self.log_test(
                "Calendar Round-Robin APIs",
                False,
                f"❌ Error: {str(e)}",
                None
            )
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("🏢 CLIENT MANAGEMENT SYSTEM TEST SUMMARY")
        print("="*80)
        
        passed = sum(1 for result in self.test_results if result["success"])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%" if total > 0 else "No tests run")
        
        print("\n📋 DETAILED RESULTS:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']}")
            if not result["success"]:
                print(f"   └─ {result['details']}")
        
        print("\n" + "="*80)
        return passed == total

    def run_all_tests(self):
        """Run all client management system tests"""
        print("🚀 Starting Client Management System Backend API Tests")
        print("=" * 80)
        
        # Test 1: Admin Authentication
        auth_success = self.test_admin_login()
        if not auth_success:
            print("\n❌ CRITICAL: Authentication failed. Cannot proceed with other tests.")
            return self.print_summary()
        
        # Test 2: Public Client Intake - HOT Lead
        self.test_client_intake_hot_lead()
        
        # Test 3: Public Client Intake - WARM Lead
        self.test_client_intake_cold_lead()
        
        # Test 4: Client Management APIs
        client_mgmt_success, clients_data = self.test_client_management_apis()
        
        # Test 5: Client Operations
        if client_mgmt_success:
            self.test_client_operations(clients_data)
        
        # Test 6: CMS Settings APIs
        self.test_cms_settings_apis()
        
        # Test 7: Calendar Round-Robin APIs
        self.test_calendar_round_robin_apis()
        
        return self.print_summary()


if __name__ == "__main__":
    tester = ClientManagementTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)