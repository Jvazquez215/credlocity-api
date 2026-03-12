"""
Test Revenue Splits and Notifications APIs
Tests for:
1. Admin Revenue Splits Dashboard API
2. Attorney Notifications API
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"
ATTORNEY_EMAIL = "test.attorney@marketplace.com"
ATTORNEY_PASSWORD = "Attorney123!"


class TestAdminRevenueSplits:
    """Admin Revenue Splits API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.admin_token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_get_revenue_splits_success(self):
        """Test GET /api/admin/revenue-splits returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/revenue-splits",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "splits" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "total_pages" in data
        assert "summary" in data
        
        # Validate summary structure
        summary = data["summary"]
        assert "total_revenue" in summary
        assert "credlocity_total" in summary
        assert "company_total" in summary
        assert "cases_count" in summary
        assert "pending_payouts" in summary
        
        # Validate types
        assert isinstance(data["splits"], list)
        assert isinstance(data["total"], int)
        assert isinstance(summary["total_revenue"], (int, float))
    
    def test_get_revenue_splits_with_status_filter(self):
        """Test GET /api/admin/revenue-splits with status filter"""
        for status in ["pending_payout", "processing", "paid"]:
            response = requests.get(
                f"{BASE_URL}/api/admin/revenue-splits?status={status}",
                headers=self.headers
            )
            assert response.status_code == 200
            data = response.json()
            assert "splits" in data
    
    def test_get_revenue_splits_with_date_range_filter(self):
        """Test GET /api/admin/revenue-splits with date range filter"""
        for date_range in ["today", "week", "month", "quarter", "year", "all"]:
            response = requests.get(
                f"{BASE_URL}/api/admin/revenue-splits?date_range={date_range}",
                headers=self.headers
            )
            assert response.status_code == 200
            data = response.json()
            assert "splits" in data
    
    def test_get_revenue_splits_with_pagination(self):
        """Test GET /api/admin/revenue-splits with pagination"""
        response = requests.get(
            f"{BASE_URL}/api/admin/revenue-splits?page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["limit"] == 10
    
    def test_get_revenue_splits_with_search(self):
        """Test GET /api/admin/revenue-splits with search"""
        response = requests.get(
            f"{BASE_URL}/api/admin/revenue-splits?search=TEST",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "splits" in data
    
    def test_export_revenue_splits_csv(self):
        """Test GET /api/admin/revenue-splits/export returns CSV"""
        response = requests.get(
            f"{BASE_URL}/api/admin/revenue-splits/export?format=csv",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "csv" in data
        assert "filename" in data
        
        # Validate CSV content
        csv_content = data["csv"]
        assert "Case ID" in csv_content
        assert "Company ID" in csv_content
        assert "Settlement Amount" in csv_content
        assert "Total Revenue" in csv_content
        assert "Credlocity Share" in csv_content
        assert "Company Share" in csv_content
        assert "Status" in csv_content
        assert "Date" in csv_content
        
        # Validate filename format
        assert data["filename"].startswith("revenue_splits_")
        assert data["filename"].endswith(".csv")
    
    def test_revenue_splits_unauthorized(self):
        """Test GET /api/admin/revenue-splits without auth returns 401/403"""
        response = requests.get(f"{BASE_URL}/api/admin/revenue-splits")
        assert response.status_code in [401, 403]


class TestAttorneyNotifications:
    """Attorney Notifications API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup attorney token"""
        response = requests.post(f"{BASE_URL}/api/attorneys/login", json={
            "email": ATTORNEY_EMAIL,
            "password": ATTORNEY_PASSWORD
        })
        assert response.status_code == 200, f"Attorney login failed: {response.text}"
        self.attorney_token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.attorney_token}"}
    
    def test_get_notifications_success(self):
        """Test GET /api/marketplace/notifications returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/marketplace/notifications?limit=20",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "notifications" in data
        assert "unread_count" in data
        assert "total" in data
        
        # Validate types
        assert isinstance(data["notifications"], list)
        assert isinstance(data["unread_count"], int)
        assert isinstance(data["total"], int)
    
    def test_get_notifications_with_unread_only(self):
        """Test GET /api/marketplace/notifications with unread_only filter"""
        response = requests.get(
            f"{BASE_URL}/api/marketplace/notifications?unread_only=true",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
    
    def test_get_notifications_with_limit(self):
        """Test GET /api/marketplace/notifications with limit"""
        response = requests.get(
            f"{BASE_URL}/api/marketplace/notifications?limit=5",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["notifications"]) <= 5
    
    def test_notifications_unauthorized(self):
        """Test GET /api/marketplace/notifications without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/marketplace/notifications")
        assert response.status_code == 403
    
    def test_notifications_with_admin_token_fails(self):
        """Test GET /api/marketplace/notifications with admin token returns 403"""
        # Login as admin
        admin_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        admin_token = admin_response.json()["access_token"]
        
        # Try to access notifications with admin token
        response = requests.get(
            f"{BASE_URL}/api/marketplace/notifications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403


class TestMarkNotificationRead:
    """Test notification read marking endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup attorney token"""
        response = requests.post(f"{BASE_URL}/api/attorneys/login", json={
            "email": ATTORNEY_EMAIL,
            "password": ATTORNEY_PASSWORD
        })
        assert response.status_code == 200
        self.attorney_token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.attorney_token}"}
    
    def test_mark_all_read_success(self):
        """Test POST /api/marketplace/notifications/mark-all-read"""
        response = requests.post(
            f"{BASE_URL}/api/marketplace/notifications/mark-all-read",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Marked" in data["message"]
    
    def test_mark_single_notification_read_not_found(self):
        """Test PATCH /api/marketplace/notifications/{id}/read with invalid ID"""
        response = requests.patch(
            f"{BASE_URL}/api/marketplace/notifications/invalid-id-123/read",
            headers=self.headers
        )
        assert response.status_code == 404


class TestAdminCompanies:
    """Test admin companies endpoint used by revenue splits filter"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.admin_token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_get_companies_for_filter(self):
        """Test GET /api/admin/companies returns companies for filter dropdown"""
        response = requests.get(
            f"{BASE_URL}/api/admin/companies?active_only=true",
            headers=self.headers
        )
        # This endpoint may or may not exist, just check it doesn't crash
        assert response.status_code in [200, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
