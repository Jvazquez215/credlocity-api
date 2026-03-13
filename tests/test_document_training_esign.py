"""
Tests for Document Center, CMS Mastery Training, and E-Signature APIs
Features:
1. Document Center - 11 seeded documentation sections
2. Training - CMS Mastery module with 6 steps and 20-question quiz
3. E-Signature - Send for signature, public signing page, PDF download
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication for test setup"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "Admin@credlocity.com",
            "password": "Credit123!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}


class TestDocumentCenterAPI(TestAuth):
    """Test Document Center API endpoints"""
    
    def test_list_sections_returns_11_sections(self, auth_headers):
        """GET /api/documentation/sections returns 11 seeded documentation sections"""
        response = requests.get(f"{BASE_URL}/api/documentation/sections", headers=auth_headers)
        assert response.status_code == 200, f"Failed to list sections: {response.text}"
        sections = response.json()
        assert isinstance(sections, list), "Response should be a list"
        assert len(sections) == 11, f"Expected 11 sections, got {len(sections)}"
        
        # Verify each section has required fields
        for section in sections:
            assert "id" in section
            assert "title" in section
            assert "slug" in section
            assert "category" in section
            assert "content_blocks" in section
    
    def test_get_section_by_id_returns_full_content(self, auth_headers):
        """GET /api/documentation/sections/{id} returns full section with content_blocks"""
        # First get list to find a section ID
        list_response = requests.get(f"{BASE_URL}/api/documentation/sections", headers=auth_headers)
        assert list_response.status_code == 200
        sections = list_response.json()
        assert len(sections) > 0, "No sections found"
        
        section_id = sections[0]["id"]
        
        # Get individual section
        response = requests.get(f"{BASE_URL}/api/documentation/sections/{section_id}", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get section: {response.text}"
        section = response.json()
        
        # Verify full content
        assert section["id"] == section_id
        assert "title" in section
        assert "description" in section
        assert "content_blocks" in section
        assert isinstance(section["content_blocks"], list)
        assert len(section["content_blocks"]) > 0, "Section should have content blocks"
    
    def test_section_categories_are_valid(self, auth_headers):
        """Verify documentation sections have valid categories"""
        response = requests.get(f"{BASE_URL}/api/documentation/sections", headers=auth_headers)
        assert response.status_code == 200
        sections = response.json()
        
        valid_categories = {'getting-started', 'operations', 'finance', 'hr', 'legal', 'marketing', 'admin'}
        for section in sections:
            assert section["category"] in valid_categories, f"Invalid category: {section['category']}"
    
    def test_get_categories(self, auth_headers):
        """GET /api/documentation/categories returns category list"""
        response = requests.get(f"{BASE_URL}/api/documentation/categories", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get categories: {response.text}"
        categories = response.json()
        assert isinstance(categories, list)
        assert len(categories) >= 7, f"Expected at least 7 categories, got {len(categories)}"


class TestTrainingAPI(TestAuth):
    """Test Training Center API endpoints"""
    
    def test_list_modules_returns_cms_mastery(self, auth_headers):
        """GET /api/training/modules returns CMS Mastery module with status 'published'"""
        response = requests.get(f"{BASE_URL}/api/training/modules", headers=auth_headers)
        assert response.status_code == 200, f"Failed to list modules: {response.text}"
        data = response.json()
        assert "modules" in data
        modules = data["modules"]
        
        # Find CMS Mastery module
        cms_mastery = None
        for module in modules:
            if "CMS Mastery" in module.get("title", ""):
                cms_mastery = module
                break
        
        assert cms_mastery is not None, "CMS Mastery module not found"
        assert cms_mastery.get("status") == "published", f"Module status should be 'published', got {cms_mastery.get('status')}"
        assert "steps" in cms_mastery
        assert len(cms_mastery["steps"]) == 6, f"Expected 6 steps, got {len(cms_mastery['steps'])}"
    
    def test_get_cms_mastery_quiz(self, auth_headers):
        """GET /api/training/modules/{id}/quiz returns quiz with 20 questions and 70% passing score"""
        # First get the CMS Mastery module ID
        response = requests.get(f"{BASE_URL}/api/training/modules", headers=auth_headers)
        assert response.status_code == 200
        modules = response.json()["modules"]
        
        cms_mastery_id = None
        for module in modules:
            if "CMS Mastery" in module.get("title", ""):
                cms_mastery_id = module["id"]
                break
        
        assert cms_mastery_id is not None, "CMS Mastery module not found"
        
        # Get quiz
        quiz_response = requests.get(f"{BASE_URL}/api/training/modules/{cms_mastery_id}/quiz", headers=auth_headers)
        assert quiz_response.status_code == 200, f"Failed to get quiz: {quiz_response.text}"
        data = quiz_response.json()
        
        assert "quiz" in data
        quiz = data["quiz"]
        assert quiz is not None, "Quiz should exist"
        assert "questions" in quiz
        assert len(quiz["questions"]) == 20, f"Expected 20 questions, got {len(quiz['questions'])}"
        assert quiz.get("passing_score") == 70, f"Expected 70% passing score, got {quiz.get('passing_score')}"
    
    def test_training_departments(self, auth_headers):
        """GET /api/training/departments returns list of departments"""
        response = requests.get(f"{BASE_URL}/api/training/departments", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get departments: {response.text}"
        data = response.json()
        assert "departments" in data
        assert len(data["departments"]) >= 5


class TestESignAPI(TestAuth):
    """Test E-Signature API endpoints"""
    
    @pytest.fixture(scope="class")
    def test_partner_id(self):
        """Partner ID for testing"""
        return "176200b3-5e59-4ecd-be5e-d58fa531afd5"
    
    @pytest.fixture(scope="class")
    def service_agreement_id(self, auth_headers, test_partner_id):
        """Get or create a service agreement for testing"""
        # Check for existing service agreements
        response = requests.get(
            f"{BASE_URL}/api/admin/outsource/partners/{test_partner_id}/service-agreements",
            headers=auth_headers
        )
        if response.status_code == 200 and len(response.json()) > 0:
            return response.json()[0]["id"]
        
        # Create a new one
        create_response = requests.post(
            f"{BASE_URL}/api/admin/outsource/partners/{test_partner_id}/agreement",
            headers=auth_headers,
            json={
                "rate_per_account": 30.00,
                "min_accounts": 35,
                "max_accounts": 50,
                "package_name": "Test E-Sign Package"
            }
        )
        assert create_response.status_code == 200, f"Failed to create agreement: {create_response.text}"
        return create_response.json()["id"]
    
    def test_send_for_esignature(self, auth_headers, service_agreement_id):
        """POST /api/esign/send/{agreement_id} creates e-sign request with token"""
        response = requests.post(
            f"{BASE_URL}/api/esign/send/{service_agreement_id}",
            headers=auth_headers,
            json={
                "signer_name": "Test Signer",
                "signer_email": "test@example.com"
            }
        )
        assert response.status_code == 200, f"Failed to send for e-signature: {response.text}"
        data = response.json()
        
        assert "sign_token" in data, "Response should contain sign_token"
        assert "sign_request_id" in data
        assert "expires_at" in data
        assert data["signer_email"] == "test@example.com"
        
        # Store token for next tests
        TestESignAPI.sign_token = data["sign_token"]
    
    def test_verify_sign_token_public(self, auth_headers):
        """GET /api/esign/public/verify/{sign_token} returns agreement info for pending signatures"""
        sign_token = getattr(TestESignAPI, 'sign_token', None)
        if not sign_token:
            pytest.skip("No sign token from previous test")
        
        # This is a PUBLIC endpoint - no auth needed
        response = requests.get(f"{BASE_URL}/api/esign/public/verify/{sign_token}")
        assert response.status_code == 200, f"Failed to verify token: {response.text}"
        data = response.json()
        
        assert data["status"] == "pending", f"Expected status 'pending', got {data['status']}"
        assert "signer_name" in data
        assert "agreement" in data
        assert "partner" in data
    
    def test_sign_agreement_public(self, auth_headers):
        """POST /api/esign/public/sign/{sign_token} accepts signature_data and marks as signed"""
        sign_token = getattr(TestESignAPI, 'sign_token', None)
        if not sign_token:
            pytest.skip("No sign token from previous test")
        
        # This is a PUBLIC endpoint - no auth needed
        # Sample base64 signature data (minimal PNG)
        signature_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        response = requests.post(
            f"{BASE_URL}/api/esign/public/sign/{sign_token}",
            json={"signature_data": signature_data}
        )
        assert response.status_code == 200, f"Failed to sign: {response.text}"
        data = response.json()
        
        assert "signed_at" in data
        assert data["message"] == "Agreement signed successfully"
    
    def test_download_signed_agreement_public(self, auth_headers):
        """GET /api/esign/public/download/{sign_token} returns PDF with signature"""
        sign_token = getattr(TestESignAPI, 'sign_token', None)
        if not sign_token:
            pytest.skip("No sign token from previous test")
        
        # This is a PUBLIC endpoint - no auth needed
        response = requests.get(f"{BASE_URL}/api/esign/public/download/{sign_token}")
        assert response.status_code == 200, f"Failed to download: {response.text}"
        
        # Check it's a PDF
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 0, "PDF should have content"
    
    def test_verify_already_signed(self, auth_headers):
        """GET /api/esign/public/verify/{sign_token} returns already_signed status"""
        sign_token = getattr(TestESignAPI, 'sign_token', None)
        if not sign_token:
            pytest.skip("No sign token from previous test")
        
        response = requests.get(f"{BASE_URL}/api/esign/public/verify/{sign_token}")
        assert response.status_code == 200
        data = response.json()
        
        # Should be already_signed or signed status
        assert data["status"] in ["signed", "already_signed"], f"Expected signed status, got {data['status']}"
    
    def test_esign_validation_errors(self, auth_headers, service_agreement_id):
        """Test e-sign validation - missing signer name/email"""
        # Missing signer_email
        response = requests.post(
            f"{BASE_URL}/api/esign/send/{service_agreement_id}",
            headers=auth_headers,
            json={"signer_name": "Test"}
        )
        assert response.status_code == 400, "Should return 400 for missing signer_email"
        
        # Missing signer_name
        response = requests.post(
            f"{BASE_URL}/api/esign/send/{service_agreement_id}",
            headers=auth_headers,
            json={"signer_email": "test@test.com"}
        )
        assert response.status_code == 400, "Should return 400 for missing signer_name"
    
    def test_invalid_sign_token(self):
        """GET /api/esign/public/verify/{invalid_token} returns 404"""
        response = requests.get(f"{BASE_URL}/api/esign/public/verify/invalid_token_12345")
        assert response.status_code == 404


class TestIntegrationScenarios(TestAuth):
    """Integration tests for the complete flow"""
    
    def test_document_center_full_flow(self, auth_headers):
        """Test full document center flow - list, get, verify content types"""
        # List all sections
        list_response = requests.get(f"{BASE_URL}/api/documentation/sections", headers=auth_headers)
        assert list_response.status_code == 200
        sections = list_response.json()
        
        # Verify we have sections from different categories
        categories_found = set()
        content_types_found = set()
        
        for section in sections:
            categories_found.add(section["category"])
            
            # Get full section
            detail_response = requests.get(
                f"{BASE_URL}/api/documentation/sections/{section['id']}",
                headers=auth_headers
            )
            assert detail_response.status_code == 200
            detail = detail_response.json()
            
            # Check content blocks
            for block in detail.get("content_blocks", []):
                content_types_found.add(block.get("type"))
        
        # Should have multiple categories
        assert len(categories_found) >= 5, f"Expected at least 5 categories, found {categories_found}"
        
        # Should have various content types
        expected_types = {"text", "list", "callout", "screenshot", "table"}
        assert content_types_found.intersection(expected_types), f"Expected some of {expected_types}, found {content_types_found}"
    
    def test_training_module_structure(self, auth_headers):
        """Test training module has complete structure"""
        # Get CMS Mastery module
        response = requests.get(f"{BASE_URL}/api/training/modules", headers=auth_headers)
        assert response.status_code == 200
        modules = response.json()["modules"]
        
        cms_mastery = next((m for m in modules if "CMS Mastery" in m.get("title", "")), None)
        assert cms_mastery is not None
        
        # Verify module structure
        assert cms_mastery.get("department") == "General"
        assert len(cms_mastery.get("steps", [])) == 6
        
        # Verify each step has content
        for i, step in enumerate(cms_mastery["steps"], 1):
            assert "title" in step, f"Step {i} missing title"
            assert "content" in step, f"Step {i} missing content"
            assert len(step["content"]) > 50, f"Step {i} content too short"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
