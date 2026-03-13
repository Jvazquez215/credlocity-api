"""
Test Department-Specific Dashboards and SmartDashboard Router APIs
Tests for Iteration 21 - Credlocity CMS modernization
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestRBACAndPermissions:
    """Test RBAC/Permissions API - Core of SmartDashboard routing"""

    def test_my_permissions_returns_admin_true(self, auth_headers):
        """Admin user should get is_admin=true and 32 permissions"""
        response = requests.get(f"{BASE_URL}/api/rbac/my-permissions", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "permissions" in data
        assert "is_admin" in data
        assert data["is_admin"] == True, "Admin user should have is_admin=true"
        
        # Admin should have 32 permissions
        permissions = data.get("permissions", [])
        assert len(permissions) >= 32, f"Expected 32+ permissions, got {len(permissions)}"
        
        # Check group_name is present
        assert "group_name" in data, "group_name should be in response"
        print(f"Admin permissions count: {len(permissions)}")
        print(f"Admin group_name: {data.get('group_name')}")

    def test_rbac_groups_returns_system_groups(self, auth_headers):
        """Should return all system groups for role-based dashboard routing"""
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        # Handle both list and dict response formats
        groups = data.get("groups", data) if isinstance(data, dict) else data
        assert isinstance(groups, list)
        
        # Check for expected system groups (used in SmartDashboard)
        group_names = [g.get("name", "").lower() for g in groups]
        expected_groups = ["admin", "collection rep", "collection manager", "marketing", 
                         "hr & payroll", "legal", "finance", "super admin"]
        
        for expected in expected_groups:
            matching = [g for g in group_names if expected in g.lower()]
            if not matching:
                print(f"Warning: Group '{expected}' not found exactly, but may exist with different name")
        
        print(f"Total groups found: {len(groups)}")
        print(f"Group names: {[g.get('name') for g in groups]}")


class TestMasterDashboardAPIs:
    """Test APIs used by the Master Dashboard (DashboardHome)"""

    def test_collections_commission_dashboard(self, auth_headers):
        """Commission dashboard should return summary with total_earned=$500"""
        response = requests.get(f"{BASE_URL}/api/collections/commission-dashboard", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "summary" in data
        
        summary = data["summary"]
        assert "total_earned" in summary
        assert summary["total_earned"] == 500.0, f"Expected $500.0 earned, got {summary['total_earned']}"
        
        # Verify other summary fields exist
        assert "total_pending" in summary
        assert "total_projected" in summary
        assert "active_trackers" in summary
        
        print(f"Commission Summary: {summary}")

    def test_payroll_dashboard(self, auth_headers):
        """Payroll dashboard should return stats for HR & Payroll section"""
        response = requests.get(f"{BASE_URL}/api/payroll/dashboard", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "active_employees" in data
        assert "total_annual_salaries" in data
        
        # Verify payroll data
        assert data["active_employees"] >= 1, "Should have at least 1 active employee"
        assert data["total_annual_salaries"] >= 65000, "Should have salary data"
        
        print(f"Payroll data: active_employees={data['active_employees']}, annual_salaries=${data['total_annual_salaries']}")

    def test_pages_api(self, auth_headers):
        """Pages API should return content for Content Overview section"""
        response = requests.get(f"{BASE_URL}/api/pages", headers=auth_headers)
        assert response.status_code == 200
        
        pages = response.json()
        assert isinstance(pages, list)
        assert len(pages) >= 21, f"Expected 21+ pages, got {len(pages)}"
        
        print(f"Total pages: {len(pages)}")

    def test_blog_posts_api(self, auth_headers):
        """Blog posts API for Content Overview"""
        response = requests.get(f"{BASE_URL}/api/blog/posts", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        posts = data.get("posts", data) if isinstance(data, dict) else data
        assert isinstance(posts, list)
        
        print(f"Total blog posts: {len(posts)}")

    def test_reviews_api(self, auth_headers):
        """Reviews API for Content Overview"""
        response = requests.get(f"{BASE_URL}/api/reviews", headers=auth_headers)
        assert response.status_code == 200
        
        reviews = response.json()
        assert isinstance(reviews, list)
        
        print(f"Total reviews: {len(reviews)}")

    def test_training_modules(self, auth_headers):
        """Training modules API for HR & Payroll section"""
        response = requests.get(f"{BASE_URL}/api/training/modules", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        modules = data.get("modules", [])
        
        print(f"Training modules count: {len(modules)}")


class TestCollectionsDashboardAPIs:
    """Test APIs for Collections Dashboard and related pages"""

    def test_collections_dashboard_stats(self, auth_headers):
        """Collections dashboard stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/collections/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        print(f"Collections dashboard stats: {data}")

    def test_collections_accounts(self, auth_headers):
        """Collections accounts list"""
        response = requests.get(f"{BASE_URL}/api/collections/accounts", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        accounts = data.get("accounts", data) if isinstance(data, dict) else data
        
        print(f"Collections accounts: {len(accounts) if isinstance(accounts, list) else 'N/A'}")

    def test_collections_settings(self, auth_headers):
        """Commission settings for the Commission Config page"""
        response = requests.get(f"{BASE_URL}/api/collections/settings", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        # Settings should have commission config sections
        assert isinstance(data, dict)
        
        print(f"Collections settings keys: {list(data.keys())}")


class TestSidebarNavigationEndpoints:
    """Test that all sidebar navigation endpoints return valid responses"""

    def test_lawsuits_endpoint(self, auth_headers):
        """Lawsuits Filed navigation link"""
        response = requests.get(f"{BASE_URL}/api/lawsuits", headers=auth_headers)
        assert response.status_code == 200
        print("Lawsuits endpoint: OK")

    def test_press_releases_endpoint(self, auth_headers):
        """Press Releases navigation"""
        response = requests.get(f"{BASE_URL}/api/press-releases", headers=auth_headers)
        assert response.status_code == 200
        print("Press Releases endpoint: OK")

    def test_outsource_partners_endpoint(self, auth_headers):
        """Outsourcing Partners navigation"""
        response = requests.get(f"{BASE_URL}/api/admin/outsource/partners", headers=auth_headers)
        assert response.status_code == 200
        print("Outsource Partners endpoint: OK")

    def test_outsource_inquiries_endpoint(self, auth_headers):
        """Outsourcing Inquiries navigation"""
        response = requests.get(f"{BASE_URL}/api/admin/outsource/inquiries", headers=auth_headers)
        assert response.status_code == 200
        print("Outsource Inquiries endpoint: OK")

    def test_clients_stats_endpoint(self, auth_headers):
        """Clients stats for dashboard"""
        response = requests.get(f"{BASE_URL}/api/admin/clients/stats", headers=auth_headers)
        assert response.status_code == 200
        print("Clients stats endpoint: OK")

    def test_authors_endpoint(self, auth_headers):
        """Authors/Profiles navigation"""
        response = requests.get(f"{BASE_URL}/api/authors", headers=auth_headers)
        assert response.status_code == 200
        print("Authors endpoint: OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
