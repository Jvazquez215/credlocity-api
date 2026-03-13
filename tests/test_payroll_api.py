"""
Payroll System API Tests
Tests: Profiles, Commissions, Bonuses, Pay Periods, Pay Stubs, Dashboard
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "Admin@credlocity.com",
        "password": "Credit123!"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client

@pytest.fixture(scope="module")
def employee_id(authenticated_client):
    """Get an existing employee ID for testing"""
    response = authenticated_client.get(f"{BASE_URL}/api/training/employees?q=")
    if response.status_code == 200:
        employees = response.json().get("employees", [])
        # Prefer non-admin employee if available
        for emp in employees:
            if emp.get("role") != "super_admin":
                return emp["id"], emp.get("full_name", "Test Employee"), emp.get("email", "")
        # Fallback to first employee
        if employees:
            return employees[0]["id"], employees[0].get("full_name", "Admin"), employees[0].get("email", "")
    pytest.skip("No employees found for testing")

# ============ DASHBOARD TESTS ============
class TestPayrollDashboard:
    """Payroll dashboard endpoint tests"""
    
    def test_dashboard_returns_200(self, authenticated_client):
        """Dashboard endpoint should return 200"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/dashboard")
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        print("PASS: Dashboard returns 200")
    
    def test_dashboard_has_required_fields(self, authenticated_client):
        """Dashboard should have all required stats fields"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/dashboard")
        data = response.json()
        
        required_fields = ["active_employees", "total_annual_salaries", "month_commissions", 
                          "month_bonuses", "last_pay_period", "commission_leaderboard"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print(f"PASS: Dashboard has all required fields: {required_fields}")
    
    def test_dashboard_requires_auth(self, api_client):
        """Dashboard should require authentication"""
        response = api_client.get(f"{BASE_URL}/api/payroll/dashboard", 
                                  headers={"Authorization": ""})
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: Dashboard requires authentication")


# ============ PROFILES TESTS ============
class TestPayrollProfiles:
    """Payroll profiles CRUD tests"""
    
    def test_list_profiles_returns_200(self, authenticated_client):
        """List profiles should return 200"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/profiles")
        assert response.status_code == 200
        assert "profiles" in response.json()
        print("PASS: List profiles returns 200")
    
    def test_create_profile(self, authenticated_client, employee_id):
        """Create a new payroll profile"""
        emp_id, emp_name, emp_email = employee_id
        
        # First delete any existing profile for this employee
        profiles_resp = authenticated_client.get(f"{BASE_URL}/api/payroll/profiles")
        for p in profiles_resp.json().get("profiles", []):
            if p.get("employee_id") == emp_id:
                authenticated_client.delete(f"{BASE_URL}/api/payroll/profiles/{p['id']}")
        
        # Create new profile
        response = authenticated_client.post(f"{BASE_URL}/api/payroll/profiles", json={
            "employee_id": emp_id,
            "employee_name": f"TEST_{emp_name}",
            "employee_email": emp_email,
            "pay_type": "salary",
            "base_salary": 60000,
            "pay_schedule": "biweekly",
            "tax_rate": 22,
            "department": "Collections",
            "deductions": [{"name": "Health Insurance", "amount": 200}]
        })
        
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        profile = response.json()
        
        assert profile["employee_id"] == emp_id
        assert profile["pay_type"] == "salary"
        assert profile["base_salary"] == 60000
        assert len(profile.get("deductions", [])) == 1
        
        print(f"PASS: Created profile ID: {profile['id']}")
        return profile["id"]
    
    def test_get_profile(self, authenticated_client, employee_id):
        """Get a profile by ID"""
        # First get profile list to find one
        profiles_resp = authenticated_client.get(f"{BASE_URL}/api/payroll/profiles")
        profiles = profiles_resp.json().get("profiles", [])
        if not profiles:
            pytest.skip("No profiles to test")
        
        profile_id = profiles[0]["id"]
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/profiles/{profile_id}")
        
        assert response.status_code == 200
        profile = response.json()
        assert profile["id"] == profile_id
        print(f"PASS: Retrieved profile {profile_id}")
    
    def test_update_profile(self, authenticated_client):
        """Update an existing profile"""
        profiles_resp = authenticated_client.get(f"{BASE_URL}/api/payroll/profiles")
        profiles = profiles_resp.json().get("profiles", [])
        if not profiles:
            pytest.skip("No profiles to test")
        
        profile_id = profiles[0]["id"]
        response = authenticated_client.put(f"{BASE_URL}/api/payroll/profiles/{profile_id}", json={
            "base_salary": 65000,
            "department": "Sales"
        })
        
        assert response.status_code == 200
        print(f"PASS: Updated profile {profile_id}")


# ============ COMMISSIONS TESTS ============
class TestPayrollCommissions:
    """Commission logging tests"""
    
    def test_list_commissions_returns_200(self, authenticated_client):
        """List commissions should return 200"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/commissions")
        assert response.status_code == 200
        data = response.json()
        assert "commissions" in data
        assert "total_commission" in data
        print("PASS: List commissions returns 200")
    
    def test_create_commission(self, authenticated_client, employee_id):
        """Create a new commission entry"""
        emp_id, emp_name, _ = employee_id
        today = datetime.now().strftime("%Y-%m-%d")
        
        response = authenticated_client.post(f"{BASE_URL}/api/payroll/commissions", json={
            "employee_id": emp_id,
            "employee_name": f"TEST_{emp_name}",
            "amount_collected": 5000,
            "commission_rate": 10,
            "description": "TEST Commission - Client XYZ payment",
            "date": today
        })
        
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        commission = response.json()
        
        assert commission["employee_id"] == emp_id
        assert commission["amount_collected"] == 5000
        assert commission["commission_rate"] == 10
        # Auto-calculated commission amount
        assert commission["commission_amount"] == 500
        
        print(f"PASS: Created commission ID: {commission['id']}, amount: ${commission['commission_amount']}")
        return commission["id"]


# ============ BONUSES TESTS ============
class TestPayrollBonuses:
    """Bonus management tests"""
    
    def test_list_bonuses_returns_200(self, authenticated_client):
        """List bonuses should return 200"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/bonuses")
        assert response.status_code == 200
        data = response.json()
        assert "bonuses" in data
        assert "total_bonuses" in data
        print("PASS: List bonuses returns 200")
    
    def test_create_bonus(self, authenticated_client, employee_id):
        """Create a new bonus entry"""
        emp_id, emp_name, _ = employee_id
        today = datetime.now().strftime("%Y-%m-%d")
        
        response = authenticated_client.post(f"{BASE_URL}/api/payroll/bonuses", json={
            "employee_id": emp_id,
            "employee_name": f"TEST_{emp_name}",
            "bonus_type": "performance",
            "amount": 1000,
            "description": "TEST Bonus - Q1 Performance Target Met",
            "date": today,
            "metric_name": "Collections Target",
            "metric_value": 50000,
            "metric_target": 45000
        })
        
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        bonus = response.json()
        
        assert bonus["employee_id"] == emp_id
        assert bonus["amount"] == 1000
        assert bonus["bonus_type"] == "performance"
        
        print(f"PASS: Created bonus ID: {bonus['id']}, amount: ${bonus['amount']}")
        return bonus["id"]
    
    def test_delete_bonus(self, authenticated_client, employee_id):
        """Create and delete a bonus"""
        emp_id, emp_name, _ = employee_id
        
        # Create a bonus to delete
        create_resp = authenticated_client.post(f"{BASE_URL}/api/payroll/bonuses", json={
            "employee_id": emp_id,
            "employee_name": f"TEST_{emp_name}",
            "bonus_type": "custom",
            "amount": 500,
            "description": "TEST Bonus - To be deleted"
        })
        assert create_resp.status_code == 200
        bonus_id = create_resp.json()["id"]
        
        # Delete the bonus
        delete_resp = authenticated_client.delete(f"{BASE_URL}/api/payroll/bonuses/{bonus_id}")
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        # Verify deletion
        get_resp = authenticated_client.get(f"{BASE_URL}/api/payroll/bonuses")
        bonus_ids = [b["id"] for b in get_resp.json().get("bonuses", [])]
        assert bonus_id not in bonus_ids
        
        print(f"PASS: Deleted bonus {bonus_id}")


# ============ PAY PERIODS TESTS ============
class TestPayPeriods:
    """Pay period management tests"""
    
    def test_list_pay_periods_returns_200(self, authenticated_client):
        """List pay periods should return 200"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/pay-periods")
        assert response.status_code == 200
        assert "pay_periods" in response.json()
        print("PASS: List pay periods returns 200")
    
    def test_create_pay_period(self, authenticated_client):
        """Create a new pay period"""
        start = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        pay_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        
        response = authenticated_client.post(f"{BASE_URL}/api/payroll/pay-periods", json={
            "name": f"TEST Pay Period {start} to {end}",
            "start_date": start,
            "end_date": end,
            "pay_date": pay_date,
            "schedule_type": "biweekly"
        })
        
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        period = response.json()
        
        assert period["start_date"] == start
        assert period["end_date"] == end
        assert period["status"] == "open"
        
        print(f"PASS: Created pay period ID: {period['id']}")
        return period["id"]


# ============ PAYROLL RUN TESTS ============
class TestPayrollRun:
    """Payroll processing tests"""
    
    def test_run_payroll_on_open_period(self, authenticated_client, employee_id):
        """Run payroll on an open pay period"""
        emp_id, emp_name, emp_email = employee_id
        
        # Ensure we have a profile (create if not exists)
        profiles_resp = authenticated_client.get(f"{BASE_URL}/api/payroll/profiles")
        existing_profile = next((p for p in profiles_resp.json().get("profiles", []) 
                                 if p.get("employee_id") == emp_id), None)
        
        if not existing_profile:
            authenticated_client.post(f"{BASE_URL}/api/payroll/profiles", json={
                "employee_id": emp_id,
                "employee_name": emp_name,
                "employee_email": emp_email,
                "pay_type": "salary",
                "base_salary": 52000,
                "pay_schedule": "biweekly",
                "tax_rate": 22,
                "department": "General"
            })
        
        # Create a new pay period
        start = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        
        period_resp = authenticated_client.post(f"{BASE_URL}/api/payroll/pay-periods", json={
            "name": f"TEST Payroll Run Period {start}",
            "start_date": start,
            "end_date": end,
            "schedule_type": "biweekly"
        })
        assert period_resp.status_code == 200
        period_id = period_resp.json()["id"]
        
        # Run payroll
        run_resp = authenticated_client.post(f"{BASE_URL}/api/payroll/pay-periods/{period_id}/run")
        assert run_resp.status_code == 200, f"Run payroll failed: {run_resp.text}"
        
        result = run_resp.json()
        assert "employees_processed" in result
        assert "total_net" in result
        assert result["employees_processed"] >= 1
        
        print(f"PASS: Payroll processed - {result['employees_processed']} employees, net: ${result['total_net']}")
        return period_id


# ============ PAY STUBS TESTS ============
class TestPayStubs:
    """Pay stub tests"""
    
    def test_list_pay_stubs(self, authenticated_client):
        """List pay stubs should return 200"""
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/pay-stubs")
        assert response.status_code == 200
        assert "stubs" in response.json()
        print("PASS: List pay stubs returns 200")
    
    def test_download_pay_stub_pdf(self, authenticated_client):
        """Download pay stub as PDF"""
        # Get stubs list
        stubs_resp = authenticated_client.get(f"{BASE_URL}/api/payroll/pay-stubs")
        stubs = stubs_resp.json().get("stubs", [])
        
        if not stubs:
            pytest.skip("No pay stubs to download")
        
        stub_id = stubs[0]["id"]
        response = authenticated_client.get(f"{BASE_URL}/api/payroll/pay-stubs/{stub_id}/download")
        
        assert response.status_code == 200, f"Download failed: {response.status_code}"
        assert response.headers.get("content-type") == "application/pdf"
        assert response.content[:5] == b"%PDF-"  # Valid PDF header
        
        print(f"PASS: Downloaded PDF for stub {stub_id}, size: {len(response.content)} bytes")


# ============ AUTHENTICATION TESTS ============
class TestPayrollAuth:
    """Authentication requirement tests"""
    
    def test_profiles_require_auth(self, api_client):
        """Profiles endpoint requires auth"""
        response = api_client.get(f"{BASE_URL}/api/payroll/profiles")
        assert response.status_code in [401, 403]
        print("PASS: Profiles require authentication")
    
    def test_commissions_require_auth(self, api_client):
        """Commissions endpoint requires auth"""
        response = api_client.get(f"{BASE_URL}/api/payroll/commissions")
        assert response.status_code in [401, 403]
        print("PASS: Commissions require authentication")
    
    def test_bonuses_require_auth(self, api_client):
        """Bonuses endpoint requires auth"""
        response = api_client.get(f"{BASE_URL}/api/payroll/bonuses")
        assert response.status_code in [401, 403]
        print("PASS: Bonuses require authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
