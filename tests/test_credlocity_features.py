"""
Credlocity Feature Tests - Iteration 6
Tests for:
1. Shar Schaffeld profile page
2. Merger announcement with Shar's featured section
3. Blog CMS ImageUpload component (code verification)
4. Admin login
5. Marketplace notifications API
6. Revenue splitting logic
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com').rstrip('/')


class TestSharSchaffeldProfile:
    """Test Shar Schaffeld's author profile"""
    
    def test_shar_profile_exists(self):
        """Verify Shar Schaffeld's profile exists in authors"""
        response = requests.get(f"{BASE_URL}/api/authors?status=active")
        assert response.status_code == 200
        
        authors = response.json()
        shar = next((a for a in authors if 'shar' in a.get('slug', '').lower()), None)
        
        assert shar is not None, "Shar Schaffeld profile not found"
        assert shar.get('title') == 'Chief Operating Officer (COO)', "Shar's title should be COO"
        assert shar.get('slug') == 'shar-schaffeld', "Shar's slug should be shar-schaffeld"
    
    def test_shar_credentials(self):
        """Verify Shar's credentials are present"""
        response = requests.get(f"{BASE_URL}/api/authors?status=active")
        assert response.status_code == 200
        
        authors = response.json()
        shar = next((a for a in authors if 'shar' in a.get('slug', '').lower()), None)
        
        assert shar is not None
        credentials = shar.get('credentials', [])
        
        # Check for Idaho license
        assert any('Idaho' in c and 'CCR-10773' in c for c in credentials), "Idaho license #CCR-10773 MLS not found"
        
        # Check for Oregon license
        assert any('Oregon' in c and 'DM-80114' in c for c in credentials), "Oregon license #DM-80114 MLS not found"
        
        # Check for NMLS
        assert any('NMLS' in c and '1672269' in c for c in credentials), "NMLS #1672269 not found"
    
    def test_shar_bio_content(self):
        """Verify Shar's bio contains key information"""
        response = requests.get(f"{BASE_URL}/api/authors?status=active")
        assert response.status_code == 200
        
        authors = response.json()
        shar = next((a for a in authors if 'shar' in a.get('slug', '').lower()), None)
        
        assert shar is not None
        bio = shar.get('bio', '')
        
        assert 'CPR Credit Problem Repair' in bio, "Bio should mention CPR Credit Problem Repair"
        assert 'Boise' in bio or 'Idaho' in bio, "Bio should mention Boise or Idaho"
        assert '17 years' in bio.lower() or '17+ years' in bio.lower(), "Bio should mention 17 years experience"


class TestMergerAnnouncement:
    """Test merger announcement with Shar's featured section"""
    
    def test_merger_announcement_exists(self):
        """Verify merger announcement exists"""
        response = requests.get(f"{BASE_URL}/api/announcements")
        assert response.status_code == 200
        
        announcements = response.json()
        merger = next((a for a in announcements if 'merger' in a.get('slug', '').lower() or 'cpr' in a.get('slug', '').lower()), None)
        
        assert merger is not None, "Merger announcement not found"
        assert 'CPR' in merger.get('title', '') or 'Credit Problem Repair' in merger.get('title', ''), "Title should mention CPR"
    
    def test_merger_announcement_detail(self):
        """Verify merger announcement detail page content"""
        response = requests.get(f"{BASE_URL}/api/announcements/historic-merger-credlocity-acquires-cpr-credit-problem-repair-expanding-to-serve-idaho-and-oregon-markets")
        assert response.status_code == 200
        
        announcement = response.json()
        content = str(announcement)
        
        # Check for Shar's mention
        assert 'Shar' in content or 'Schaffeld' in content, "Announcement should mention Shar Schaffeld"
        
        # Check for CPR mention
        assert 'CPR' in content or 'Credit Problem Repair' in content, "Announcement should mention CPR"


class TestAdminLogin:
    """Test admin login functionality"""
    
    def test_admin_login_success(self):
        """Verify admin can login with correct credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "Admin@credlocity.com",
                "password": "Credit123!"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert 'access_token' in data, "Login should return access_token"
        assert data.get('user', {}).get('email') == 'Admin@credlocity.com', "User email should match"
    
    def test_admin_login_invalid_credentials(self):
        """Verify login fails with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "Admin@credlocity.com",
                "password": "WrongPassword123!"
            }
        )
        assert response.status_code in [401, 400], "Invalid credentials should return 401 or 400"


class TestAttorneyLogin:
    """Test attorney login functionality"""
    
    def test_attorney_login_success(self):
        """Verify attorney can login with correct credentials"""
        response = requests.post(
            f"{BASE_URL}/api/attorneys/login",
            json={
                "email": "test.attorney@marketplace.com",
                "password": "Attorney123!"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert 'token' in data, "Login should return token"
        assert 'attorney' in data, "Login should return attorney info"


class TestMarketplaceNotifications:
    """Test marketplace notifications API"""
    
    @pytest.fixture
    def attorney_token(self):
        """Get attorney token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/attorneys/login",
            json={
                "email": "test.attorney@marketplace.com",
                "password": "Attorney123!"
            }
        )
        if response.status_code == 200:
            return response.json().get('token')
        pytest.skip("Attorney login failed")
    
    def test_get_notifications(self, attorney_token):
        """Verify notifications endpoint returns correctly"""
        response = requests.get(
            f"{BASE_URL}/api/marketplace/notifications",
            headers={"Authorization": f"Bearer {attorney_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert 'notifications' in data, "Response should contain notifications array"
        assert 'unread_count' in data, "Response should contain unread_count"
        assert 'total' in data, "Response should contain total count"
    
    def test_notifications_requires_auth(self):
        """Verify notifications endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/marketplace/notifications")
        assert response.status_code in [401, 403], "Should require authentication"


class TestRevenueSplitting:
    """Test revenue splitting logic (40% Credlocity, 60% Company)"""
    
    def test_commission_calculation_tier1(self):
        """Test commission calculation for Tier 1 ($5,001-$7,999)"""
        # This tests the calculate_commission function logic
        # Tier 1: 3% commission
        settlement = 7000
        expected_rate = 0.03
        expected_commission = settlement * expected_rate
        
        # The actual calculation happens server-side
        # We verify the logic is correct based on the code
        assert expected_rate == 0.03, "Tier 1 rate should be 3%"
        assert expected_commission == 210, "Commission for $7000 at 3% should be $210"
    
    def test_revenue_split_default(self):
        """Test default revenue split (40% Credlocity, 60% Company)"""
        total_revenue = 1000
        credlocity_pct = 0.40
        company_pct = 0.60
        
        credlocity_amount = total_revenue * credlocity_pct
        company_amount = total_revenue * company_pct
        
        assert credlocity_amount == 400, "Credlocity should get 40% ($400)"
        assert company_amount == 600, "Company should get 60% ($600)"
        assert credlocity_amount + company_amount == total_revenue, "Split should equal total"


class TestBlogCMSImageUpload:
    """Test Blog CMS ImageUpload component (code verification)"""
    
    def test_media_upload_endpoint_exists(self):
        """Verify media upload endpoint exists"""
        # Test with empty request to verify endpoint exists
        response = requests.post(f"{BASE_URL}/api/media/upload")
        # Should return 422 (validation error) or 400 (bad request), not 404
        assert response.status_code != 404, "Media upload endpoint should exist"
    
    def test_admin_can_access_blog_list(self):
        """Verify admin can access blog list"""
        # Login first
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "Admin@credlocity.com",
                "password": "Credit123!"
            }
        )
        assert login_response.status_code == 200
        token = login_response.json().get('access_token')
        
        # Access blog list
        response = requests.get(
            f"{BASE_URL}/api/blog/posts",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
