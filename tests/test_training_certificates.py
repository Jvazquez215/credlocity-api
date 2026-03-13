"""
Training Certificates API Tests
Tests for:
- POST /api/training/modules/{id}/certificate - Generate certificate (requires quiz passed or module complete)
- POST /api/training/modules/{id}/certificate - Returns existing cert if already generated (no duplicates)
- POST /api/training/modules/{id}/certificate - Rejects if quiz not passed
- GET /api/training/certificates - List user's certificates
- GET /api/training/certificates/{id}/download - Download PDF with valid content-type
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Known test data from context - Admin user has passed quiz on this module
EXISTING_MODULE_ID = "48654d67-5c47-4add-aa0e-733e6c8c8192"
EXISTING_CERT_ID = "584bfe42-5d94-4406-8edb-3c28deacfcc1"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for Admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "Admin@credlocity.com", "password": "Credit123!"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token")


@pytest.fixture
def api_client(auth_token):
    """Authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestGenerateCertificate:
    """Tests for POST /api/training/modules/{id}/certificate"""

    def test_generate_certificate_returns_existing_cert(self, api_client):
        """When cert already exists, should return existing cert (no duplicates)"""
        response = api_client.post(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/certificate")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return existing certificate
        assert data.get("id") == EXISTING_CERT_ID
        assert data.get("module_id") == EXISTING_MODULE_ID
        assert "user_id" in data
        assert "user_name" in data
        assert "module_title" in data
        assert "department" in data
        assert "quiz_score" in data
        assert "completed_date" in data
        assert "issued_at" in data
        
    def test_generate_certificate_requires_quiz_pass(self, api_client, auth_token):
        """Should reject if quiz exists but not passed"""
        # First create a new module with a quiz
        module_data = {
            "title": "TEST_CertTest_QuizRequired",
            "department": "General",
            "description": "Module for testing cert quiz requirement",
            "status": "published"
        }
        mod_res = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert mod_res.status_code == 200
        module_id = mod_res.json()["id"]
        
        # Add a quiz to this module
        quiz_data = {
            "questions": [
                {"question": "Test Q1?", "options": ["A", "B"], "correct_answer": 0}
            ],
            "passing_score": 80
        }
        quiz_res = api_client.post(f"{BASE_URL}/api/training/modules/{module_id}/quiz", json=quiz_data)
        assert quiz_res.status_code == 200
        
        # Try to generate cert without passing quiz - should fail
        cert_res = api_client.post(f"{BASE_URL}/api/training/modules/{module_id}/certificate")
        assert cert_res.status_code == 400
        assert "must pass the quiz" in cert_res.json().get("detail", "").lower()
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/training/modules/{module_id}")

    def test_generate_certificate_requires_module_complete_if_no_quiz(self, api_client):
        """Should reject if no quiz but module not completed"""
        # Create module without quiz
        module_data = {
            "title": "TEST_CertTest_NoQuiz",
            "department": "General",
            "description": "Module without quiz",
            "status": "published",
            "steps": [{"title": "Step 1", "content": "Do something"}]
        }
        mod_res = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert mod_res.status_code == 200
        module_id = mod_res.json()["id"]
        
        # Try to generate cert without completing module - should fail
        cert_res = api_client.post(f"{BASE_URL}/api/training/modules/{module_id}/certificate")
        assert cert_res.status_code == 400
        assert "must complete the module" in cert_res.json().get("detail", "").lower()
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/training/modules/{module_id}")

    def test_generate_certificate_for_nonexistent_module(self, api_client):
        """Should return 404 for nonexistent module"""
        response = api_client.post(f"{BASE_URL}/api/training/modules/nonexistent-id/certificate")
        assert response.status_code == 404

    def test_generate_certificate_requires_auth(self):
        """Should require authentication"""
        response = requests.post(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/certificate")
        assert response.status_code in [401, 403]


class TestListCertificates:
    """Tests for GET /api/training/certificates"""

    def test_list_certificates_returns_user_certs(self, api_client):
        """Should return all certificates for current user"""
        response = api_client.get(f"{BASE_URL}/api/training/certificates")
        
        assert response.status_code == 200
        data = response.json()
        assert "certificates" in data
        
        # Should contain at least the known cert
        certs = data["certificates"]
        assert isinstance(certs, list)
        assert len(certs) >= 1
        
        # Check structure of first cert
        cert = certs[0]
        assert "id" in cert
        assert "module_id" in cert
        assert "module_title" in cert
        assert "department" in cert
        assert "user_id" in cert
        assert "user_name" in cert

    def test_list_certificates_includes_required_fields(self, api_client):
        """Each certificate should have all required fields for UI display"""
        response = api_client.get(f"{BASE_URL}/api/training/certificates")
        assert response.status_code == 200
        
        certs = response.json().get("certificates", [])
        for cert in certs:
            # Fields required for certificate card display
            assert "id" in cert, "Missing certificate ID"
            assert "module_title" in cert, "Missing module title"
            assert "department" in cert, "Missing department"
            assert "completed_date" in cert, "Missing completed date"
            # quiz_score can be null if no quiz

    def test_list_certificates_requires_auth(self):
        """Should require authentication"""
        response = requests.get(f"{BASE_URL}/api/training/certificates")
        assert response.status_code in [401, 403]


class TestDownloadCertificate:
    """Tests for GET /api/training/certificates/{id}/download"""

    def test_download_certificate_returns_pdf(self, api_client):
        """Should return valid PDF file with correct content-type"""
        response = api_client.get(f"{BASE_URL}/api/training/certificates/{EXISTING_CERT_ID}/download")
        
        assert response.status_code == 200
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected application/pdf, got {content_type}"
        
        # Check Content-Disposition header
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert ".pdf" in content_disp

    def test_download_certificate_pdf_is_valid(self, api_client):
        """PDF should start with %PDF- header"""
        response = api_client.get(f"{BASE_URL}/api/training/certificates/{EXISTING_CERT_ID}/download")
        
        assert response.status_code == 200
        
        # Check PDF header
        pdf_content = response.content
        assert pdf_content.startswith(b"%PDF-"), "PDF file should start with %PDF- header"
        
        # PDF should have reasonable size (at least 1KB for a real PDF)
        assert len(pdf_content) > 1000, f"PDF seems too small: {len(pdf_content)} bytes"

    def test_download_certificate_not_found(self, api_client):
        """Should return 404 for nonexistent certificate"""
        response = api_client.get(f"{BASE_URL}/api/training/certificates/nonexistent-cert-id/download")
        assert response.status_code == 404

    def test_download_certificate_requires_auth(self):
        """Should require authentication"""
        response = requests.get(f"{BASE_URL}/api/training/certificates/{EXISTING_CERT_ID}/download")
        assert response.status_code in [401, 403]


class TestCertificateDataIntegrity:
    """Verify certificate data is correct"""

    def test_existing_certificate_has_correct_data(self, api_client):
        """Existing certificate should have correct module and user info"""
        response = api_client.get(f"{BASE_URL}/api/training/certificates")
        assert response.status_code == 200
        
        certs = response.json().get("certificates", [])
        
        # Find the known certificate
        cert = next((c for c in certs if c.get("id") == EXISTING_CERT_ID), None)
        assert cert is not None, f"Expected certificate {EXISTING_CERT_ID} not found"
        
        # Verify data
        assert cert["module_id"] == EXISTING_MODULE_ID
        assert cert["quiz_score"] == 100, "Admin passed quiz with 100%"

    def test_certificate_id_format(self, api_client):
        """Certificate IDs should be valid UUIDs"""
        import re
        uuid_pattern = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
        
        response = api_client.get(f"{BASE_URL}/api/training/certificates")
        assert response.status_code == 200
        
        certs = response.json().get("certificates", [])
        for cert in certs:
            cert_id = cert.get("id", "")
            assert uuid_pattern.match(cert_id), f"Certificate ID {cert_id} is not a valid UUID"


class TestGenerateCertificateOnQuizPass:
    """Test certificate generation flow for passed quiz"""

    def test_full_flow_pass_quiz_then_get_cert(self, api_client):
        """Complete flow: create module with quiz, pass quiz, get certificate"""
        # Create module
        module_data = {
            "title": "TEST_CertFlow_Module",
            "department": "Collections",
            "description": "Full flow test module",
            "status": "published"
        }
        mod_res = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert mod_res.status_code == 200
        module_id = mod_res.json()["id"]
        
        try:
            # Add quiz
            quiz_data = {
                "questions": [
                    {"question": "What is 2+2?", "options": ["3", "4", "5"], "correct_answer": 1, "explanation": "Basic math"}
                ],
                "passing_score": 80
            }
            quiz_res = api_client.post(f"{BASE_URL}/api/training/modules/{module_id}/quiz", json=quiz_data)
            assert quiz_res.status_code == 200
            
            # Submit quiz with correct answers
            submit_res = api_client.post(
                f"{BASE_URL}/api/training/modules/{module_id}/quiz/submit",
                json={"answers": {"0": 1}}  # Correct answer
            )
            assert submit_res.status_code == 200
            submit_data = submit_res.json()
            assert submit_data["passed"] == True
            assert submit_data["score"] == 100
            
            # Now generate certificate - should succeed
            cert_res = api_client.post(f"{BASE_URL}/api/training/modules/{module_id}/certificate")
            assert cert_res.status_code == 200
            cert = cert_res.json()
            
            # Verify certificate data
            assert cert["module_id"] == module_id
            assert cert["module_title"] == "TEST_CertFlow_Module"
            assert cert["department"] == "Collections"
            assert cert["quiz_score"] == 100
            assert "id" in cert
            assert "completed_date" in cert
            assert "issued_at" in cert
            
            # Download the PDF
            download_res = api_client.get(f"{BASE_URL}/api/training/certificates/{cert['id']}/download")
            assert download_res.status_code == 200
            assert "application/pdf" in download_res.headers.get("Content-Type", "")
            assert download_res.content.startswith(b"%PDF-")
            
        finally:
            # Cleanup
            api_client.delete(f"{BASE_URL}/api/training/modules/{module_id}")
