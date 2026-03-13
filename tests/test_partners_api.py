"""
Test suite for Credlocity Partners API
Tests: Partner Types CRUD, Partners CRUD, Public endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"


class TestPublicPartnersAPI:
    """Public Partners API tests - no auth required"""
    
    def test_get_partner_types_public(self):
        """GET /api/partner-types - should return active partner types"""
        response = requests.get(f"{BASE_URL}/api/partner-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least Real Estate and Mortgage types
        assert len(data) >= 1
        # Verify structure
        if len(data) > 0:
            assert "id" in data[0]
            assert "name" in data[0]
            assert "slug" in data[0]
    
    def test_get_partners_public(self):
        """GET /api/partners - should return published partners"""
        response = requests.get(f"{BASE_URL}/api/partners")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least John Smith partner
        assert len(data) >= 1
        # Verify structure
        partner = data[0]
        assert "id" in partner
        assert "name" in partner
        assert "slug" in partner
        assert "company_name" in partner
        assert "partner_type" in partner
    
    def test_get_partner_by_slug(self):
        """GET /api/partners/:slug - should return partner details"""
        response = requests.get(f"{BASE_URL}/api/partners/john-smith-premier-realty-group")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "John Smith"
        assert data["company_name"] == "Premier Realty Group"
        assert data["slug"] == "john-smith-premier-realty-group"
        assert "partner_type" in data
        assert data["partner_type"]["name"] == "Real Estate"
    
    def test_get_partner_by_invalid_slug(self):
        """GET /api/partners/:slug - should return 404 for invalid slug"""
        response = requests.get(f"{BASE_URL}/api/partners/nonexistent-partner-slug")
        assert response.status_code == 404
    
    def test_get_partners_filtered_by_type(self):
        """GET /api/partners?partner_type=:id - should filter by type"""
        # First get a valid type ID
        types_response = requests.get(f"{BASE_URL}/api/partner-types")
        types = types_response.json()
        if len(types) > 0:
            type_id = types[0]["id"]
            response = requests.get(f"{BASE_URL}/api/partners?partner_type={type_id}")
            assert response.status_code == 200
            data = response.json()
            # All returned partners should have this type
            for partner in data:
                assert partner["partner_type_id"] == type_id
    
    def test_get_featured_partners(self):
        """GET /api/partners?featured=true - should return featured partners"""
        response = requests.get(f"{BASE_URL}/api/partners?featured=true")
        assert response.status_code == 200
        data = response.json()
        # All returned partners should be featured
        for partner in data:
            assert partner["is_featured"] == True


class TestAdminAuth:
    """Admin authentication tests"""
    
    def test_admin_login_success(self):
        """POST /api/auth/login - should return token for valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 0
    
    def test_admin_login_invalid_password(self):
        """POST /api/auth/login - should return 401 for invalid password"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401


class TestAdminPartnerTypesAPI:
    """Admin Partner Types API tests - requires auth"""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_admin_partner_types(self, auth_headers):
        """GET /api/admin/partner-types - should return all types"""
        response = requests.get(f"{BASE_URL}/api/admin/partner-types", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_partner_type(self, auth_headers):
        """POST /api/admin/partner-types - should create new type"""
        response = requests.post(f"{BASE_URL}/api/admin/partner-types", 
            headers=auth_headers,
            json={
                "name": "TEST_Funding Partners",
                "description": "Funding and investment partners"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Funding Partners"
        assert "id" in data
        assert "slug" in data
        
        # Cleanup - delete the test type
        type_id = data["id"]
        requests.delete(f"{BASE_URL}/api/admin/partner-types/{type_id}", headers=auth_headers)
    
    def test_update_partner_type(self, auth_headers):
        """PUT /api/admin/partner-types/:id - should update type"""
        # First create a type
        create_response = requests.post(f"{BASE_URL}/api/admin/partner-types",
            headers=auth_headers,
            json={
                "name": "TEST_Update Type",
                "description": "Original description"
            }
        )
        type_id = create_response.json()["id"]
        
        # Update it
        update_response = requests.put(f"{BASE_URL}/api/admin/partner-types/{type_id}",
            headers=auth_headers,
            json={
                "description": "Updated description"
            }
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["description"] == "Updated description"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/partner-types/{type_id}", headers=auth_headers)
    
    def test_delete_partner_type(self, auth_headers):
        """DELETE /api/admin/partner-types/:id - should delete type"""
        # First create a type
        create_response = requests.post(f"{BASE_URL}/api/admin/partner-types",
            headers=auth_headers,
            json={
                "name": "TEST_Delete Type",
                "description": "To be deleted"
            }
        )
        type_id = create_response.json()["id"]
        
        # Delete it
        delete_response = requests.delete(f"{BASE_URL}/api/admin/partner-types/{type_id}", headers=auth_headers)
        assert delete_response.status_code == 200
        
        # Verify it's gone from public API
        public_response = requests.get(f"{BASE_URL}/api/partner-types")
        types = public_response.json()
        type_ids = [t["id"] for t in types]
        assert type_id not in type_ids


class TestAdminPartnersAPI:
    """Admin Partners API tests - requires auth"""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    @pytest.fixture
    def partner_type_id(self, auth_headers):
        """Get a valid partner type ID"""
        response = requests.get(f"{BASE_URL}/api/admin/partner-types", headers=auth_headers)
        types = response.json()
        if len(types) > 0:
            return types[0]["id"]
        pytest.skip("No partner types available")
    
    def test_get_admin_partners(self, auth_headers):
        """GET /api/admin/partners - should return all partners"""
        response = requests.get(f"{BASE_URL}/api/admin/partners", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_admin_partner_by_id(self, auth_headers):
        """GET /api/admin/partners/:id - should return partner by ID"""
        # First get list to find an ID
        list_response = requests.get(f"{BASE_URL}/api/admin/partners", headers=auth_headers)
        partners = list_response.json()
        if len(partners) > 0:
            partner_id = partners[0]["id"]
            response = requests.get(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == partner_id
    
    def test_create_partner(self, auth_headers, partner_type_id):
        """POST /api/admin/partners - should create new partner"""
        response = requests.post(f"{BASE_URL}/api/admin/partners",
            headers=auth_headers,
            json={
                "name": "TEST_Jane Doe",
                "company_name": "TEST_Doe Consulting",
                "partner_type_id": partner_type_id,
                "short_bio": "Test partner for automated testing",
                "full_bio": "This is a test partner created by automated tests.",
                "email": "test@example.com",
                "is_published": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Jane Doe"
        assert data["company_name"] == "TEST_Doe Consulting"
        assert "id" in data
        assert "slug" in data
        
        # Verify it appears in public API
        public_response = requests.get(f"{BASE_URL}/api/partners")
        partners = public_response.json()
        partner_names = [p["name"] for p in partners]
        assert "TEST_Jane Doe" in partner_names
        
        # Cleanup
        partner_id = data["id"]
        requests.delete(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
    
    def test_update_partner(self, auth_headers, partner_type_id):
        """PUT /api/admin/partners/:id - should update partner"""
        # First create a partner
        create_response = requests.post(f"{BASE_URL}/api/admin/partners",
            headers=auth_headers,
            json={
                "name": "TEST_Update Partner",
                "company_name": "TEST_Original Company",
                "partner_type_id": partner_type_id,
                "short_bio": "Original bio",
                "full_bio": "Original full bio"
            }
        )
        partner_id = create_response.json()["id"]
        
        # Update it
        update_response = requests.put(f"{BASE_URL}/api/admin/partners/{partner_id}",
            headers=auth_headers,
            json={
                "short_bio": "Updated bio",
                "years_experience": 10
            }
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["short_bio"] == "Updated bio"
        assert data["years_experience"] == 10
        
        # Verify with GET
        get_response = requests.get(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
        assert get_response.json()["short_bio"] == "Updated bio"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
    
    def test_toggle_partner_published(self, auth_headers, partner_type_id):
        """PATCH /api/admin/partners/:id/toggle - should toggle published status"""
        # First create a partner
        create_response = requests.post(f"{BASE_URL}/api/admin/partners",
            headers=auth_headers,
            json={
                "name": "TEST_Toggle Partner",
                "company_name": "TEST_Toggle Company",
                "partner_type_id": partner_type_id,
                "short_bio": "Test toggle",
                "full_bio": "Test toggle full bio",
                "is_published": True
            }
        )
        partner_id = create_response.json()["id"]
        
        # Toggle it
        toggle_response = requests.patch(f"{BASE_URL}/api/admin/partners/{partner_id}/toggle", headers=auth_headers)
        assert toggle_response.status_code == 200
        
        # Verify it's now unpublished
        get_response = requests.get(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
        assert get_response.json()["is_published"] == False
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
    
    def test_delete_partner(self, auth_headers, partner_type_id):
        """DELETE /api/admin/partners/:id - should delete partner"""
        # First create a partner
        create_response = requests.post(f"{BASE_URL}/api/admin/partners",
            headers=auth_headers,
            json={
                "name": "TEST_Delete Partner",
                "company_name": "TEST_Delete Company",
                "partner_type_id": partner_type_id,
                "short_bio": "To be deleted",
                "full_bio": "To be deleted full bio"
            }
        )
        partner_id = create_response.json()["id"]
        
        # Delete it
        delete_response = requests.delete(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
        assert delete_response.status_code == 200
        
        # Verify it's gone
        get_response = requests.get(f"{BASE_URL}/api/admin/partners/{partner_id}", headers=auth_headers)
        assert get_response.status_code == 404


class TestAdminPartnersAPIUnauthorized:
    """Test that admin endpoints require authentication"""
    
    def test_get_admin_partners_unauthorized(self):
        """GET /api/admin/partners - should return 401/403 without auth"""
        response = requests.get(f"{BASE_URL}/api/admin/partners")
        assert response.status_code in [401, 403]  # Both indicate unauthorized
    
    def test_create_partner_unauthorized(self):
        """POST /api/admin/partners - should return 401/403 without auth"""
        response = requests.post(f"{BASE_URL}/api/admin/partners", json={
            "name": "Unauthorized Partner",
            "company_name": "Unauthorized Company"
        })
        assert response.status_code in [401, 403]  # Both indicate unauthorized
    
    def test_get_admin_partner_types_unauthorized(self):
        """GET /api/admin/partner-types - should return 401/403 without auth"""
        response = requests.get(f"{BASE_URL}/api/admin/partner-types")
        assert response.status_code in [401, 403]  # Both indicate unauthorized


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
