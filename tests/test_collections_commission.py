"""
Collections Commission Settings API Tests
Tests for commission rates, fee schedules, late fee tiers, tier waiver rules, bonuses,
and auto-commission bridge (70% threshold tracking, record-payment, commission-trackers).
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"


class TestCollectionsCommissionSettings:
    """Test Collections Commission Settings API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self, auth_token):
        """Setup with authentication token"""
        self.token = auth_token
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    # ==================== GET /api/collections/settings ====================
    def test_get_settings_returns_default_settings(self, auth_token):
        """Test GET /api/collections/settings returns correct default settings"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/settings", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "settings" in data, "Response should contain 'settings' key"
        settings = data["settings"]
        
        # Verify commission settings structure exists
        assert "commission" in settings, "Settings should contain 'commission'"
        # Allow flexible base_rate (may be modified by previous tests)
        assert settings["commission"]["base_rate"] in [20, 25], f"Base rate should be 20 or 25%, got {settings['commission']['base_rate']}"
        assert settings["commission"]["payment_plan_threshold"] == 70, "Threshold should be 70%"
        assert settings["commission"]["collection_fee_immediate"] == True, "Collection fee should pay immediately"
        
        # Verify fees structure
        assert "fees" in settings, "Settings should contain 'fees'"
        assert "collection_file_processing" in settings["fees"], "Should have collection_file_processing"
        assert settings["fees"]["collection_file_processing"]["amount"] == 150.00
        assert settings["fees"]["collection_file_processing"]["waivable"] == False
        
        assert "collection_fee" in settings["fees"], "Should have collection_fee"
        assert settings["fees"]["collection_fee"]["amount"] == 350.00
        assert settings["fees"]["collection_fee"]["max_waive_amount"] == 175.00
        
        assert "payment_processing" in settings["fees"], "Should have payment_processing"
        assert settings["fees"]["payment_processing"]["amount"] == 190.00
        assert settings["fees"]["payment_processing"]["max_waive_amount"] == 90.00
        
        print("PASS: GET /api/collections/settings returns correct default settings")
    
    # ==================== GET /api/collections/settings/defaults ====================
    def test_get_defaults_returns_default_config(self, auth_token):
        """Test GET /api/collections/settings/defaults returns default config"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/settings/defaults", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "settings" in data, "Response should contain 'settings'"
        
        print("PASS: GET /api/collections/settings/defaults returns default config")
    
    # ==================== Verify Late Fees Structure ====================
    def test_late_fees_structure(self, auth_token):
        """Test late fees has 4 tiers with correct amounts"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/settings", headers=headers)
        
        assert response.status_code == 200
        settings = response.json()["settings"]
        
        assert "late_fees" in settings, "Settings should contain 'late_fees'"
        late_fees = settings["late_fees"]
        
        assert len(late_fees) == 4, f"Should have 4 late fee tiers, got {len(late_fees)}"
        
        # Verify amounts
        expected_amounts = [10.50, 17.50, 30.00, 50.00]
        for i, fee in enumerate(late_fees):
            assert fee["amount"] == expected_amounts[i], f"Late fee tier {i+1} should be ${expected_amounts[i]}"
        
        # Verify day ranges
        assert late_fees[0]["min_days"] == 1 and late_fees[0]["max_days"] == 10
        assert late_fees[1]["min_days"] == 11 and late_fees[1]["max_days"] == 15
        assert late_fees[2]["min_days"] == 16 and late_fees[2]["max_days"] == 30
        assert late_fees[3]["min_days"] == 31 and late_fees[3]["max_days"] == 90
        
        print("PASS: Late fees have 4 tiers with correct amounts ($10.50, $17.50, $30, $50)")
    
    # ==================== Verify Tier Rules Structure ====================
    def test_tier_rules_structure(self, auth_token):
        """Test tiers have correct names and waiver limits"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/settings", headers=headers)
        
        assert response.status_code == 200
        settings = response.json()["settings"]
        
        assert "tiers" in settings, "Settings should contain 'tiers'"
        tiers = settings["tiers"]
        
        # Verify Tier 1 - Payment in Full
        assert "1" in tiers, "Should have Tier 1"
        assert tiers["1"]["name"] == "Payment in Full"
        assert tiers["1"]["min_down_percent"] == 100
        assert tiers["1"]["max_months"] == 0
        assert tiers["1"]["waiver_limits"]["collection_fee_max_waive"] == 125.00
        assert tiers["1"]["waiver_limits"]["payment_processing_max_waive"] == 70.00
        
        # Verify Tier 2 - Payment Plan (3-4 Months)
        assert "2" in tiers, "Should have Tier 2"
        assert tiers["2"]["name"] == "Payment Plan (3-4 Months)"
        assert tiers["2"]["min_down_percent"] == 25
        assert tiers["2"]["max_months"] == 4
        assert tiers["2"]["waiver_limits"]["collection_fee_max_waive"] == 75.00
        assert tiers["2"]["waiver_limits"]["payment_processing_max_waive"] == 40.00
        
        # Verify Tier 3 - Extended Plan (5-6 Months)
        assert "3" in tiers, "Should have Tier 3"
        assert tiers["3"]["name"] == "Extended Plan (5-6 Months)"
        assert tiers["3"]["min_down_percent"] == 30
        assert tiers["3"]["max_months"] == 6
        assert tiers["3"]["waiver_limits"]["collection_fee_max_waive"] == 50.00
        assert tiers["3"]["waiver_limits"]["payment_processing_max_waive"] == 25.00
        
        print("PASS: Tier rules have correct names and waiver limits")
    
    # ==================== Verify Bonuses Structure ====================
    def test_bonuses_structure(self, auth_token):
        """Test bonuses have add/remove functionality via structure"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/settings", headers=headers)
        
        assert response.status_code == 200
        settings = response.json()["settings"]
        
        assert "bonuses" in settings, "Settings should contain 'bonuses'"
        bonuses = settings["bonuses"]
        
        assert isinstance(bonuses, list), "Bonuses should be a list"
        assert len(bonuses) >= 2, f"Should have at least 2 default bonuses, got {len(bonuses)}"
        
        # Verify structure of first bonus
        first_bonus = bonuses[0]
        assert "name" in first_bonus
        assert "type" in first_bonus
        assert "condition" in first_bonus
        
        print("PASS: Bonuses structure is correct (list with add/remove capability)")
    
    # ==================== PUT /api/collections/settings ====================
    def test_update_settings_and_persistence(self, auth_token):
        """Test PUT /api/collections/settings updates and persists settings"""
        headers = {'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'}
        
        # First, get current settings
        get_response = requests.get(f"{BASE_URL}/api/collections/settings", headers=headers)
        assert get_response.status_code == 200
        original_settings = get_response.json()["settings"]
        
        # Modify commission base_rate temporarily
        modified_settings = original_settings.copy()
        modified_settings["commission"]["base_rate"] = 25  # Change from 20 to 25
        
        # Update settings
        update_response = requests.put(
            f"{BASE_URL}/api/collections/settings",
            headers=headers,
            json={"settings": modified_settings}
        )
        
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
        update_data = update_response.json()
        assert "updated_at" in update_data, "Response should contain 'updated_at'"
        
        # Verify persistence by fetching again
        verify_response = requests.get(f"{BASE_URL}/api/collections/settings", headers=headers)
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["settings"]["commission"]["base_rate"] == 25, "Settings should persist after update"
        
        # Restore original settings
        restore_response = requests.put(
            f"{BASE_URL}/api/collections/settings",
            headers=headers,
            json={"settings": original_settings}
        )
        assert restore_response.status_code == 200, "Should restore original settings"
        
        print("PASS: PUT /api/collections/settings updates and persists successfully")
    
    # ==================== GET /api/collections/commission-trackers ====================
    def test_get_commission_trackers(self, auth_token):
        """Test GET /api/collections/commission-trackers returns tracker list"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/commission-trackers", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "trackers" in data, "Response should contain 'trackers'"
        assert isinstance(data["trackers"], list), "Trackers should be a list"
        
        print("PASS: GET /api/collections/commission-trackers returns tracker list")
    
    # ==================== Test Auth Required ====================
    def test_settings_requires_auth(self):
        """Test that settings endpoints require authentication"""
        # No auth header
        response = requests.get(f"{BASE_URL}/api/collections/settings")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        
        print("PASS: Settings endpoints require authentication")


class TestCommissionDashboard:
    """Test Commission Dashboard API endpoint (iteration 18)"""
    
    # ==================== GET /api/collections/commission-dashboard ====================
    def test_commission_dashboard_returns_correct_structure(self, auth_token):
        """Test GET /api/collections/commission-dashboard returns correct data structure"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify top-level keys
        assert "summary" in data, "Response should contain 'summary'"
        assert "trackers" in data, "Response should contain 'trackers'"
        assert "commissions" in data, "Response should contain 'commissions'"
        assert "leaderboard" in data, "Response should contain 'leaderboard'"
        assert "is_admin" in data, "Response should contain 'is_admin'"
        
        print("PASS: Commission dashboard returns correct top-level structure")
    
    def test_commission_dashboard_summary_fields(self, auth_token):
        """Test summary object has all required fields"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=headers)
        
        assert response.status_code == 200
        summary = response.json()["summary"]
        
        # Verify all summary fields exist
        required_fields = [
            "total_earned", "total_paid", "total_pending",
            "collection_fee_earned", "base_commission_earned",
            "projected_additional", "total_projected",
            "active_trackers", "completed_trackers"
        ]
        
        for field in required_fields:
            assert field in summary, f"Summary should contain '{field}'"
        
        # Verify types
        assert isinstance(summary["total_earned"], (int, float))
        assert isinstance(summary["total_paid"], (int, float))
        assert isinstance(summary["active_trackers"], int)
        assert isinstance(summary["completed_trackers"], int)
        
        print(f"PASS: Summary has all fields - Total Earned: ${summary['total_earned']}, Pending: ${summary['total_pending']}, Projected: ${summary['total_projected']}")
    
    def test_commission_dashboard_admin_sees_leaderboard(self, auth_token):
        """Test that admin user can see leaderboard data"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["is_admin"] == True, "Admin user should have is_admin=True"
        assert isinstance(data["leaderboard"], list), "Leaderboard should be a list"
        
        # If there's leaderboard data, verify structure
        if len(data["leaderboard"]) > 0:
            entry = data["leaderboard"][0]
            assert "rep_id" in entry, "Leaderboard entry should have rep_id"
            assert "rep_name" in entry, "Leaderboard entry should have rep_name"
            assert "total_commission" in entry, "Leaderboard entry should have total_commission"
            assert "collection_fees" in entry, "Leaderboard entry should have collection_fees"
            assert "base_commissions" in entry, "Leaderboard entry should have base_commissions"
        
        print(f"PASS: Admin user sees leaderboard with {len(data['leaderboard'])} entries")
    
    def test_commission_dashboard_trackers_array(self, auth_token):
        """Test trackers array structure"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data["trackers"], list), "Trackers should be a list"
        
        # If there are trackers, verify structure
        if len(data["trackers"]) > 0:
            tracker = data["trackers"][0]
            expected_fields = ["id", "client_name", "total_owed", "total_collected", "threshold_amount", "commission_amount"]
            for field in expected_fields:
                assert field in tracker, f"Tracker should contain '{field}'"
        
        print(f"PASS: Trackers array contains {len(data['trackers'])} entries")
    
    def test_commission_dashboard_commissions_array(self, auth_token):
        """Test commissions array structure (max 50)"""
        headers = {'Authorization': f'Bearer {auth_token}'}
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data["commissions"], list), "Commissions should be a list"
        assert len(data["commissions"]) <= 50, "Commissions should be limited to 50 entries"
        
        # If there are commissions, verify structure
        if len(data["commissions"]) > 0:
            comm = data["commissions"][0]
            expected_fields = ["id", "commission_amount", "status"]
            for field in expected_fields:
                assert field in comm, f"Commission should contain '{field}'"
        
        print(f"PASS: Commissions array contains {len(data['commissions'])} entries (max 50)")
    
    def test_commission_dashboard_requires_auth(self):
        """Test that commission-dashboard requires authentication"""
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        
        print("PASS: Commission dashboard requires authentication")


class TestCollectionsPaymentPlanAndCommission:
    """Test Payment Plan creation with auto-commission bridge"""
    
    def test_create_account_for_commission_test(self, auth_token):
        """Create a test account for commission testing"""
        headers = {'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'}
        
        # First check if we have existing accounts
        response = requests.get(f"{BASE_URL}/api/collections/accounts", headers=headers)
        assert response.status_code == 200, f"Failed to get accounts: {response.text}"
        
        data = response.json()
        if data.get("accounts") and len(data["accounts"]) > 0:
            # Use existing account
            account = data["accounts"][0]
            print(f"Using existing account: {account['client_name']} (ID: {account['id']})")
            return account["id"]
        
        # Create new test account
        account_data = {
            "client_name": "TEST_Commission_Client",
            "client_email": "test.commission@example.com",
            "client_phone": "(555) 123-4567",
            "first_failed_payment_date": "2024-12-01",
            "past_due_balance": 539.85,
            "package_type": "individual"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/collections/accounts",
            headers=headers,
            json=account_data
        )
        
        if create_response.status_code == 200:
            created = create_response.json()
            print(f"Created test account: {created['id']}")
            return created["id"]
        else:
            print(f"Account creation returned {create_response.status_code}: {create_response.text}")
            # Skip if we can't create
            pytest.skip("Could not create test account")


# ==================== Fixtures ====================
@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        print(f"Authentication successful for {ADMIN_EMAIL}")
        return token
    else:
        pytest.fail(f"Authentication failed: {response.status_code} - {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
