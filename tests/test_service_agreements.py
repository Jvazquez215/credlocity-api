"""
Test Suite for Outsourcing Service Agreement System
- POST /api/admin/outsource/partners/{partner_id}/agreement (generate agreement)
- GET /api/admin/outsource/partners/{partner_id}/service-agreements (list agreements)
- GET /api/admin/outsource/agreements/{agreement_id}/download (download PDF)
- PATCH /api/admin/outsource/agreements/{agreement_id}/status (update status)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
PARTNER_ID = "176200b3-5e59-4ecd-be5e-d58fa531afd5"


class TestServiceAgreements:
    """Outsourcing Service Agreement System tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - authenticate once per test class"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get auth token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "Admin@credlocity.com",
            "password": "Credit123!"
        })
        
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed - skipping tests")
        
        yield
    
    def test_01_auth_login(self):
        """Test authentication works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "Admin@credlocity.com",
            "password": "Credit123!"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        print(f"PASS: Login successful, token received")
    
    def test_02_partner_exists(self):
        """Test that test partner exists"""
        response = self.session.get(f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == PARTNER_ID
        print(f"PASS: Partner found - {data.get('company_name', 'Unknown')}")
    
    def test_03_generate_service_agreement(self):
        """Test generating a new service agreement with custom pricing"""
        pricing_data = {
            "rate_per_account": 35.00,
            "min_accounts": 40,
            "max_accounts": 60,
            "package_name": "Full Service - High Volume",
            "additional_terms": "Test agreement generated via automated testing",
            "provider_name": "Credlocity LLC",
            "provider_address": "123 Test Street"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/agreement",
            json=pricing_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify agreement structure
        assert "id" in data
        assert data.get("partner_id") == PARTNER_ID
        assert data.get("rate_per_account") == 35.00
        assert data.get("min_accounts") == 40
        assert data.get("max_accounts") == 60
        assert data.get("package_name") == "Full Service - High Volume"
        assert data.get("status") == "draft"
        
        # Store agreement ID for later tests
        self.__class__.created_agreement_id = data["id"]
        print(f"PASS: Service agreement generated - ID: {data['id']}")
    
    def test_04_get_service_agreements_list(self):
        """Test fetching list of service agreements for partner"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/service-agreements"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least the one we just created
        
        # Verify agreement structure in list
        if len(data) > 0:
            agreement = data[0]
            assert "id" in agreement
            assert "partner_id" in agreement
            assert "rate_per_account" in agreement
            assert "min_accounts" in agreement
            assert "max_accounts" in agreement
            assert "status" in agreement
        
        print(f"PASS: Retrieved {len(data)} service agreements for partner")
    
    def test_05_update_agreement_status_sent(self):
        """Test updating agreement status to 'sent'"""
        agreement_id = getattr(self.__class__, 'created_agreement_id', None)
        if not agreement_id:
            # Try to get one from list
            list_response = self.session.get(
                f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/service-agreements"
            )
            if list_response.status_code == 200 and len(list_response.json()) > 0:
                agreement_id = list_response.json()[0]["id"]
            else:
                pytest.skip("No agreement available for status update test")
        
        response = self.session.patch(
            f"{BASE_URL}/api/admin/outsource/agreements/{agreement_id}/status",
            json={"status": "sent"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("message") == "Agreement status updated"
        print(f"PASS: Agreement status updated to 'sent'")
    
    def test_06_update_agreement_status_signed(self):
        """Test updating agreement status to 'signed'"""
        agreement_id = getattr(self.__class__, 'created_agreement_id', None)
        if not agreement_id:
            list_response = self.session.get(
                f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/service-agreements"
            )
            if list_response.status_code == 200 and len(list_response.json()) > 0:
                agreement_id = list_response.json()[0]["id"]
            else:
                pytest.skip("No agreement available for status update test")
        
        response = self.session.patch(
            f"{BASE_URL}/api/admin/outsource/agreements/{agreement_id}/status",
            json={"status": "signed"}
        )
        
        assert response.status_code == 200
        print(f"PASS: Agreement status updated to 'signed'")
    
    def test_07_update_agreement_status_active(self):
        """Test updating agreement status to 'active'"""
        agreement_id = getattr(self.__class__, 'created_agreement_id', None)
        if not agreement_id:
            list_response = self.session.get(
                f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/service-agreements"
            )
            if list_response.status_code == 200 and len(list_response.json()) > 0:
                agreement_id = list_response.json()[0]["id"]
            else:
                pytest.skip("No agreement available for status update test")
        
        response = self.session.patch(
            f"{BASE_URL}/api/admin/outsource/agreements/{agreement_id}/status",
            json={"status": "active"}
        )
        
        assert response.status_code == 200
        print(f"PASS: Agreement status updated to 'active'")
    
    def test_08_download_agreement_pdf(self):
        """Test downloading agreement as PDF"""
        agreement_id = getattr(self.__class__, 'created_agreement_id', None)
        if not agreement_id:
            list_response = self.session.get(
                f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/service-agreements"
            )
            if list_response.status_code == 200 and len(list_response.json()) > 0:
                agreement_id = list_response.json()[0]["id"]
            else:
                pytest.skip("No agreement available for download test")
        
        response = self.session.get(
            f"{BASE_URL}/api/admin/outsource/agreements/{agreement_id}/download"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf" or "pdf" in response.headers.get("content-type", "").lower()
        assert len(response.content) > 0  # PDF should have content
        
        # Verify it starts with PDF header
        assert response.content[:4] == b'%PDF', "Response does not appear to be a valid PDF"
        
        print(f"PASS: Downloaded PDF agreement ({len(response.content)} bytes)")
    
    def test_09_update_agreement_status_terminated(self):
        """Test updating agreement status to 'terminated'"""
        agreement_id = getattr(self.__class__, 'created_agreement_id', None)
        if not agreement_id:
            list_response = self.session.get(
                f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/service-agreements"
            )
            if list_response.status_code == 200 and len(list_response.json()) > 0:
                agreement_id = list_response.json()[0]["id"]
            else:
                pytest.skip("No agreement available for status update test")
        
        response = self.session.patch(
            f"{BASE_URL}/api/admin/outsource/agreements/{agreement_id}/status",
            json={"status": "terminated"}
        )
        
        assert response.status_code == 200
        print(f"PASS: Agreement status updated to 'terminated'")
    
    def test_10_generate_agreement_with_defaults(self):
        """Test generating agreement with minimal/default values"""
        response = self.session.post(
            f"{BASE_URL}/api/admin/outsource/partners/{PARTNER_ID}/agreement",
            json={}  # Empty - should use defaults
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check defaults are applied
        assert data.get("rate_per_account") == 30.00  # default
        assert data.get("min_accounts") == 35  # default
        assert data.get("max_accounts") == 50  # default
        assert "id" in data
        
        print(f"PASS: Agreement generated with default values")
    
    def test_11_invalid_partner_agreement(self):
        """Test generating agreement for non-existent partner returns 404"""
        fake_partner_id = "00000000-0000-0000-0000-000000000000"
        response = self.session.post(
            f"{BASE_URL}/api/admin/outsource/partners/{fake_partner_id}/agreement",
            json={"rate_per_account": 30.00}
        )
        
        assert response.status_code == 404
        print(f"PASS: 404 returned for invalid partner")
    
    def test_12_invalid_agreement_download(self):
        """Test downloading non-existent agreement returns 404"""
        fake_agreement_id = "00000000-0000-0000-0000-000000000000"
        response = self.session.get(
            f"{BASE_URL}/api/admin/outsource/agreements/{fake_agreement_id}/download"
        )
        
        assert response.status_code == 404
        print(f"PASS: 404 returned for invalid agreement download")
    
    def test_13_invalid_agreement_status_update(self):
        """Test updating status for non-existent agreement returns 404"""
        fake_agreement_id = "00000000-0000-0000-0000-000000000000"
        response = self.session.patch(
            f"{BASE_URL}/api/admin/outsource/agreements/{fake_agreement_id}/status",
            json={"status": "active"}
        )
        
        assert response.status_code == 404
        print(f"PASS: 404 returned for invalid agreement status update")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
