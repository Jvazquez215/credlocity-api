"""
Credlocity CMS Modernization Tests - Iteration 20
Tests RBAC system, Commission Dashboard, Payroll Dashboard, and Core Routes
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com')

# Test fixtures
@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "Admin@credlocity.com", "password": "Credit123!"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Return headers with auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


# ==================== RBAC API Tests ====================

class TestRBACAPI:
    """Test RBAC system endpoints"""

    def test_get_my_permissions_returns_admin_permissions(self, auth_headers):
        """GET /api/rbac/my-permissions returns all permissions for admin"""
        response = requests.get(f"{BASE_URL}/api/rbac/my-permissions", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "permissions" in data
        assert "is_admin" in data
        assert data["is_admin"] == True, "Admin should have is_admin=true"
        # Admin should have all 32 permissions
        assert len(data["permissions"]) >= 30, f"Expected 30+ permissions, got {len(data['permissions'])}"
        print(f"✓ Admin has {len(data['permissions'])} permissions, is_admin={data['is_admin']}")

    def test_get_groups_returns_8_plus_default_groups(self, auth_headers):
        """GET /api/rbac/groups returns 8+ default system groups"""
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "groups" in data
        groups = data["groups"]
        assert len(groups) >= 8, f"Expected 8+ groups, got {len(groups)}"
        
        # Check for expected default groups
        group_names = [g["name"] for g in groups]
        expected_groups = ["Super Admin", "Admin", "Collection Rep", "Collection Manager", "Marketing", "HR & Payroll", "Legal", "Finance"]
        for expected in expected_groups:
            assert expected in group_names, f"Missing group: {expected}"
        
        print(f"✓ Found {len(groups)} groups: {group_names[:8]}...")

    def test_get_permissions_returns_all_categories(self, auth_headers):
        """GET /api/rbac/permissions returns all permission categories"""
        response = requests.get(f"{BASE_URL}/api/rbac/permissions", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "permissions" in data
        permissions = data["permissions"]
        
        # Should have 16 categories
        assert len(permissions) >= 15, f"Expected 15+ permission categories, got {len(permissions)}"
        
        # Verify key categories exist
        expected_cats = ["dashboard", "collections", "payroll", "marketing", "reviews", "clients"]
        for cat in expected_cats:
            assert cat in permissions, f"Missing permission category: {cat}"
        
        print(f"✓ Found {len(permissions)} permission categories")

    def test_get_users_with_assignments(self, auth_headers):
        """GET /api/rbac/users returns users with group assignments"""
        response = requests.get(f"{BASE_URL}/api/rbac/users", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "users" in data
        users = data["users"]
        assert len(users) >= 1, "Expected at least 1 user"
        
        # Check user structure
        first_user = users[0]
        expected_fields = ["id", "email", "role"]
        for field in expected_fields:
            assert field in first_user, f"Missing field: {field}"
        
        print(f"✓ Found {len(users)} users in RBAC system")


# ==================== Commission Dashboard Tests ====================

class TestCommissionDashboard:
    """Test Commission Dashboard endpoint"""

    def test_commission_dashboard_returns_summary(self, auth_headers):
        """GET /api/collections/commission-dashboard returns summary data"""
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check summary structure
        assert "summary" in data, "Missing summary in response"
        summary = data["summary"]
        
        expected_fields = ["total_earned", "total_pending", "active_trackers"]
        for field in expected_fields:
            assert field in summary, f"Missing summary field: {field}"
        
        # Check other sections
        assert "trackers" in data, "Missing trackers list"
        assert "commissions" in data, "Missing commissions list"
        assert "is_admin" in data, "Missing is_admin flag"
        
        print(f"✓ Commission Dashboard: total_earned=${summary.get('total_earned', 0)}, active_trackers={summary.get('active_trackers', 0)}")


# ==================== Payroll Dashboard Tests ====================

class TestPayrollDashboard:
    """Test Payroll Dashboard endpoint"""

    def test_payroll_dashboard_returns_stats(self, auth_headers):
        """GET /api/payroll/dashboard returns payroll stats"""
        response = requests.get(f"{BASE_URL}/api/payroll/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check expected fields
        expected_fields = ["active_employees", "total_annual_salaries", "month_commissions"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ Payroll Dashboard: active_employees={data.get('active_employees', 0)}, total_annual=${data.get('total_annual_salaries', 0)}")


# ==================== Collections Dashboard Tests ====================

class TestCollectionsDashboard:
    """Test Collections Dashboard endpoint"""

    def test_collections_stats_returns_data(self, auth_headers):
        """GET /api/collections/dashboard/stats returns stats"""
        response = requests.get(f"{BASE_URL}/api/collections/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check expected fields
        expected_fields = ["total_accounts", "active_accounts", "tier_counts"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ Collections: total={data.get('total_accounts', 0)}, active={data.get('active_accounts', 0)}")


# ==================== Training API Tests ====================

class TestTrainingAPI:
    """Test Training modules endpoint"""

    def test_training_modules_returns_data(self, auth_headers):
        """GET /api/training/modules returns modules list"""
        response = requests.get(f"{BASE_URL}/api/training/modules", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "modules" in data, "Missing modules in response"
        print(f"✓ Training: {len(data['modules'])} modules available")


# ==================== Core Routes Tests ====================

class TestCoreRoutes:
    """Test core CMS routes"""

    def test_pages_route(self, auth_headers):
        """GET /api/pages returns pages list"""
        response = requests.get(f"{BASE_URL}/api/pages", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Pages: {len(data)} pages")

    def test_blog_posts_route(self, auth_headers):
        """GET /api/blog/posts returns blog posts"""
        response = requests.get(f"{BASE_URL}/api/blog/posts", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "posts" in data or isinstance(data, list)
        print(f"✓ Blog posts endpoint working")

    def test_authors_route(self, auth_headers):
        """GET /api/authors returns authors list"""
        response = requests.get(f"{BASE_URL}/api/authors", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Authors: {len(data)} authors")

    def test_clients_stats_route(self, auth_headers):
        """GET /api/admin/clients/stats returns client stats"""
        response = requests.get(f"{BASE_URL}/api/admin/clients/stats", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total" in data or isinstance(data, dict)
        print(f"✓ Client stats endpoint working")


# ==================== Commission Settings Tests ====================

class TestCommissionSettings:
    """Test Commission Settings endpoint"""

    def test_get_commission_settings(self, auth_headers):
        """GET /api/collections/settings returns settings"""
        response = requests.get(f"{BASE_URL}/api/collections/settings", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "settings" in data, "Missing settings in response"
        settings = data["settings"]
        
        # Check key settings sections
        expected_sections = ["commission", "fees", "late_fees", "tiers"]
        for section in expected_sections:
            assert section in settings, f"Missing settings section: {section}"
        
        print(f"✓ Commission Settings: {len(settings.keys())} sections configured")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
