"""
Test suite for Credlocity Employee Training & Policies API
Tests CRUD operations for training modules and policies
"""

import pytest
import requests
import os
from uuid import uuid4

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_EMAIL = "Admin@credlocity.com"
TEST_PASSWORD = "Credit123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


# ==================== DEPARTMENTS & CATEGORIES ====================

class TestDepartmentsAndCategories:
    """Test department and policy category endpoints"""
    
    def test_get_departments(self, api_client):
        """GET /api/training/departments returns list of departments"""
        response = api_client.get(f"{BASE_URL}/api/training/departments")
        assert response.status_code == 200
        data = response.json()
        assert "departments" in data
        assert isinstance(data["departments"], list)
        assert len(data["departments"]) > 0
        # Verify expected departments
        expected_depts = ["General", "Collections", "Sales", "HR", "IT"]
        for dept in expected_depts:
            assert dept in data["departments"], f"Expected department '{dept}' not found"
        print(f"[PASS] Departments: {data['departments']}")
    
    def test_get_policy_categories(self, api_client):
        """GET /api/training/policy-categories returns list of categories"""
        response = api_client.get(f"{BASE_URL}/api/training/policy-categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert isinstance(data["categories"], list)
        assert len(data["categories"]) > 0
        # Verify expected default categories
        expected_cats = ["General", "HR", "Compliance", "Operations", "Safety", "IT Security"]
        for cat in expected_cats:
            assert cat in data["categories"], f"Expected category '{cat}' not found"
        print(f"[PASS] Policy Categories: {data['categories']}")


# ==================== TRAINING MODULES CRUD ====================

class TestTrainingModulesCRUD:
    """Test full CRUD operations for training modules"""
    
    created_module_id = None
    
    def test_get_modules_list(self, api_client):
        """GET /api/training/modules returns list of modules"""
        response = api_client.get(f"{BASE_URL}/api/training/modules")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert isinstance(data["modules"], list)
        print(f"[PASS] Found {len(data['modules'])} training modules")
    
    def test_get_modules_filtered_by_department(self, api_client):
        """GET /api/training/modules?department=HR filters correctly"""
        response = api_client.get(f"{BASE_URL}/api/training/modules?department=HR")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        for module in data["modules"]:
            assert module["department"] == "HR", f"Module {module['id']} has wrong department"
        print(f"[PASS] Department filter working, found {len(data['modules'])} HR modules")
    
    def test_create_module_success(self, api_client):
        """POST /api/training/modules creates a new module"""
        module_data = {
            "title": f"TEST_Module_{str(uuid4())[:8]}",
            "description": "Test module description",
            "department": "IT",
            "content": "<h2>Test Content</h2><p>This is test content.</p>",
            "steps": [
                {"title": "Step 1", "content": "First step instructions", "image_url": ""},
                {"title": "Step 2", "content": "Second step instructions", "image_url": ""}
            ],
            "status": "draft",
            "order": 99
        }
        
        response = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert response.status_code == 200, f"Failed to create module: {response.text}"
        
        created = response.json()
        assert "id" in created
        assert created["title"] == module_data["title"]
        assert created["department"] == "IT"
        assert created["status"] == "draft"
        assert len(created["steps"]) == 2
        
        TestTrainingModulesCRUD.created_module_id = created["id"]
        print(f"[PASS] Created module: {created['id']}")
    
    def test_get_single_module(self, api_client):
        """GET /api/training/modules/{id} returns single module"""
        module_id = TestTrainingModulesCRUD.created_module_id
        assert module_id, "No module ID from create test"
        
        response = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}")
        assert response.status_code == 200
        
        module = response.json()
        assert module["id"] == module_id
        assert "steps" in module
        print(f"[PASS] Retrieved module: {module['title']}")
    
    def test_update_module_success(self, api_client):
        """PUT /api/training/modules/{id} updates module"""
        module_id = TestTrainingModulesCRUD.created_module_id
        assert module_id, "No module ID from create test"
        
        update_data = {
            "title": f"TEST_Module_Updated_{str(uuid4())[:8]}",
            "status": "published",
            "steps": [
                {"title": "Updated Step 1", "content": "Updated content", "image_url": ""},
                {"title": "Updated Step 2", "content": "Updated content 2", "image_url": ""},
                {"title": "New Step 3", "content": "Added step", "image_url": ""}
            ]
        }
        
        response = api_client.put(f"{BASE_URL}/api/training/modules/{module_id}", json=update_data)
        assert response.status_code == 200
        
        # Verify update persisted
        get_response = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}")
        assert get_response.status_code == 200
        updated = get_response.json()
        assert updated["status"] == "published"
        assert len(updated["steps"]) == 3
        print(f"[PASS] Updated module to published status with 3 steps")
    
    def test_delete_module_success(self, api_client):
        """DELETE /api/training/modules/{id} deletes module"""
        module_id = TestTrainingModulesCRUD.created_module_id
        assert module_id, "No module ID from create test"
        
        response = api_client.delete(f"{BASE_URL}/api/training/modules/{module_id}")
        assert response.status_code == 200
        
        # Verify deletion
        get_response = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}")
        assert get_response.status_code == 404
        print(f"[PASS] Module deleted successfully")
    
    def test_get_nonexistent_module_returns_404(self, api_client):
        """GET /api/training/modules/{invalid_id} returns 404"""
        response = api_client.get(f"{BASE_URL}/api/training/modules/nonexistent-id-123")
        assert response.status_code == 404
        print("[PASS] 404 returned for nonexistent module")


# ==================== POLICIES CRUD ====================

class TestPoliciesCRUD:
    """Test full CRUD operations for policies"""
    
    created_policy_id = None
    
    def test_get_policies_list(self, api_client):
        """GET /api/training/policies returns list of policies"""
        response = api_client.get(f"{BASE_URL}/api/training/policies")
        assert response.status_code == 200
        data = response.json()
        assert "policies" in data
        assert isinstance(data["policies"], list)
        print(f"[PASS] Found {len(data['policies'])} policies")
    
    def test_get_policies_filtered_by_department(self, api_client):
        """GET /api/training/policies?department=Collections filters correctly"""
        response = api_client.get(f"{BASE_URL}/api/training/policies?department=Collections")
        assert response.status_code == 200
        data = response.json()
        assert "policies" in data
        for policy in data["policies"]:
            assert policy["department"] == "Collections"
        print(f"[PASS] Department filter working, found {len(data['policies'])} Collections policies")
    
    def test_create_policy_success(self, api_client):
        """POST /api/training/policies creates a new policy"""
        policy_data = {
            "title": f"TEST_Policy_{str(uuid4())[:8]}",
            "description": "Test policy description",
            "department": "Legal",
            "category": "Compliance",
            "content": "<h2>Policy Overview</h2><p>This is test policy content.</p>",
            "sections": [
                {"title": "Section 1: Introduction", "content": "<p>Introduction content</p>"},
                {"title": "Section 2: Procedures", "content": "<p>Procedure details</p>"}
            ],
            "status": "draft",
            "effective_date": "2026-01-01",
            "order": 99
        }
        
        response = api_client.post(f"{BASE_URL}/api/training/policies", json=policy_data)
        assert response.status_code == 200, f"Failed to create policy: {response.text}"
        
        created = response.json()
        assert "id" in created
        assert created["title"] == policy_data["title"]
        assert created["department"] == "Legal"
        assert created["category"] == "Compliance"
        assert created["status"] == "draft"
        assert len(created["sections"]) == 2
        
        TestPoliciesCRUD.created_policy_id = created["id"]
        print(f"[PASS] Created policy: {created['id']}")
    
    def test_get_single_policy(self, api_client):
        """GET /api/training/policies/{id} returns single policy"""
        policy_id = TestPoliciesCRUD.created_policy_id
        assert policy_id, "No policy ID from create test"
        
        response = api_client.get(f"{BASE_URL}/api/training/policies/{policy_id}")
        assert response.status_code == 200
        
        policy = response.json()
        assert policy["id"] == policy_id
        assert "sections" in policy
        print(f"[PASS] Retrieved policy: {policy['title']}")
    
    def test_update_policy_success(self, api_client):
        """PUT /api/training/policies/{id} updates policy"""
        policy_id = TestPoliciesCRUD.created_policy_id
        assert policy_id, "No policy ID from create test"
        
        update_data = {
            "title": f"TEST_Policy_Updated_{str(uuid4())[:8]}",
            "status": "published",
            "effective_date": "2026-06-01",
            "sections": [
                {"title": "Updated Section 1", "content": "<p>Updated content</p>"},
                {"title": "New Section 2", "content": "<p>Added section</p>"},
                {"title": "New Section 3", "content": "<p>Another section</p>"}
            ]
        }
        
        response = api_client.put(f"{BASE_URL}/api/training/policies/{policy_id}", json=update_data)
        assert response.status_code == 200
        
        # Verify update persisted
        get_response = api_client.get(f"{BASE_URL}/api/training/policies/{policy_id}")
        assert get_response.status_code == 200
        updated = get_response.json()
        assert updated["status"] == "published"
        assert len(updated["sections"]) == 3
        assert updated["effective_date"] == "2026-06-01"
        print(f"[PASS] Updated policy with 3 sections and new effective date")
    
    def test_delete_policy_success(self, api_client):
        """DELETE /api/training/policies/{id} deletes policy"""
        policy_id = TestPoliciesCRUD.created_policy_id
        assert policy_id, "No policy ID from create test"
        
        response = api_client.delete(f"{BASE_URL}/api/training/policies/{policy_id}")
        assert response.status_code == 200
        
        # Verify deletion
        get_response = api_client.get(f"{BASE_URL}/api/training/policies/{policy_id}")
        assert get_response.status_code == 404
        print(f"[PASS] Policy deleted successfully")
    
    def test_get_nonexistent_policy_returns_404(self, api_client):
        """GET /api/training/policies/{invalid_id} returns 404"""
        response = api_client.get(f"{BASE_URL}/api/training/policies/nonexistent-id-456")
        assert response.status_code == 404
        print("[PASS] 404 returned for nonexistent policy")


# ==================== AUTHENTICATION TESTS ====================

class TestTrainingAPIAuth:
    """Test authentication requirements for training API"""
    
    def test_modules_requires_auth(self):
        """GET /api/training/modules without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/modules")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("[PASS] Modules endpoint requires authentication")
    
    def test_policies_requires_auth(self):
        """GET /api/training/policies without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/policies")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("[PASS] Policies endpoint requires authentication")
    
    def test_departments_requires_auth(self):
        """GET /api/training/departments without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/departments")
        assert response.status_code == 403
        print("[PASS] Departments endpoint requires authentication")


# ==================== CHATBOT SETTINGS TESTS ====================

class TestChatbotSettings:
    """Test chatbot settings API including working hours"""
    
    def test_get_chatbot_settings(self, api_client):
        """GET /api/support-chat/chatbot/settings returns settings"""
        response = api_client.get(f"{BASE_URL}/api/support-chat/chatbot/settings")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "enabled" in data
        assert "greeting_message" in data
        assert "model_provider" in data
        print(f"[PASS] Chatbot settings retrieved, enabled: {data['enabled']}")
    
    def test_update_chatbot_settings(self, api_client):
        """PUT /api/support-chat/chatbot/settings updates settings"""
        # Get current settings first
        get_response = api_client.get(f"{BASE_URL}/api/support-chat/chatbot/settings")
        current = get_response.json()
        
        # Update with working hours
        update_data = {
            **current,
            "working_hours": {
                "enabled": True,
                "schedule": {
                    "monday": {"start": "09:00", "end": "17:00"},
                    "tuesday": {"start": "09:00", "end": "17:00"},
                    "wednesday": {"start": "09:00", "end": "17:00"},
                    "thursday": {"start": "09:00", "end": "17:00"},
                    "friday": {"start": "09:00", "end": "17:00"},
                    "saturday": None,
                    "sunday": None
                }
            }
        }
        
        response = api_client.put(f"{BASE_URL}/api/support-chat/chatbot/settings", json=update_data)
        assert response.status_code == 200
        print("[PASS] Chatbot settings with working hours updated")
    
    def test_get_widget_excluded_pages(self, api_client):
        """GET /api/support-chat/widget/excluded-pages returns pages list"""
        response = api_client.get(f"{BASE_URL}/api/support-chat/widget/excluded-pages")
        assert response.status_code == 200
        data = response.json()
        assert "pages" in data
        assert isinstance(data["pages"], list)
        print(f"[PASS] Found {len(data['pages'])} excluded pages")
    
    def test_add_and_remove_excluded_page(self, api_client):
        """POST and DELETE /api/support-chat/widget/excluded-pages works"""
        # Add excluded page
        add_response = api_client.post(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages",
            json={"page_path": "/test-excluded-path-xyz"}
        )
        assert add_response.status_code in [200, 201], f"Failed to add: {add_response.text}"
        added = add_response.json()
        page_id = added.get("id")
        assert page_id, "No ID returned from add"
        
        # Verify it's in the list
        list_response = api_client.get(f"{BASE_URL}/api/support-chat/widget/excluded-pages")
        pages = list_response.json()["pages"]
        found = any(p["page_path"] == "/test-excluded-path-xyz" for p in pages)
        assert found, "Added page not found in list"
        
        # Delete it
        delete_response = api_client.delete(f"{BASE_URL}/api/support-chat/widget/excluded-pages/{page_id}")
        assert delete_response.status_code == 200
        
        # Verify deletion
        list_response2 = api_client.get(f"{BASE_URL}/api/support-chat/widget/excluded-pages")
        pages2 = list_response2.json()["pages"]
        found2 = any(p["page_path"] == "/test-excluded-path-xyz" for p in pages2)
        assert not found2, "Page still exists after deletion"
        
        print("[PASS] Add and remove excluded page working")


# ==================== CLEANUP ====================

class TestCleanup:
    """Cleanup any test data created"""
    
    def test_cleanup_test_modules(self, api_client):
        """Clean up any TEST_ prefixed modules"""
        response = api_client.get(f"{BASE_URL}/api/training/modules")
        if response.status_code == 200:
            modules = response.json()["modules"]
            for module in modules:
                if module["title"].startswith("TEST_"):
                    api_client.delete(f"{BASE_URL}/api/training/modules/{module['id']}")
                    print(f"  Cleaned up module: {module['title']}")
        print("[PASS] Test modules cleanup complete")
    
    def test_cleanup_test_policies(self, api_client):
        """Clean up any TEST_ prefixed policies"""
        response = api_client.get(f"{BASE_URL}/api/training/policies")
        if response.status_code == 200:
            policies = response.json()["policies"]
            for policy in policies:
                if policy["title"].startswith("TEST_"):
                    api_client.delete(f"{BASE_URL}/api/training/policies/{policy['id']}")
                    print(f"  Cleaned up policy: {policy['title']}")
        print("[PASS] Test policies cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
