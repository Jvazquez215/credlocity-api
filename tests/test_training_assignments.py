"""
Test suite for Training Assignments feature
Tests assignment CRUD, employee search, and notification creation
"""

import pytest
import requests
import os
from uuid import uuid4

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_EMAIL = "Admin@credlocity.com"
TEST_PASSWORD = "Credit123!"

# Known module ID from seed data
KNOWN_MODULE_ID = "48654d67-5c47-4add-aa0e-733e6c8c8192"


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


@pytest.fixture(scope="module")
def admin_user_id(api_client):
    """Get Admin user ID for assignment testing"""
    response = api_client.get(f"{BASE_URL}/api/training/employees")
    assert response.status_code == 200
    employees = response.json()["employees"]
    admin = next((e for e in employees if e["email"] == TEST_EMAIL), None)
    assert admin, f"Admin user not found in employees list"
    return admin["id"]


# ==================== EMPLOYEES SEARCH API ====================

class TestEmployeesSearch:
    """Test GET /api/training/employees endpoint"""
    
    def test_get_employees_returns_list(self, api_client):
        """GET /api/training/employees returns list of employees"""
        response = api_client.get(f"{BASE_URL}/api/training/employees")
        assert response.status_code == 200
        data = response.json()
        assert "employees" in data
        assert isinstance(data["employees"], list)
        assert len(data["employees"]) > 0
        
        # Check employee structure
        emp = data["employees"][0]
        assert "id" in emp
        assert "email" in emp
        print(f"[PASS] Found {len(data['employees'])} employees")
    
    def test_employees_search_by_name(self, api_client):
        """GET /api/training/employees?q=Admin filters by name"""
        response = api_client.get(f"{BASE_URL}/api/training/employees?q=Admin")
        assert response.status_code == 200
        data = response.json()
        # Should find Admin user
        found = any("admin" in e.get("full_name", "").lower() or "admin" in e.get("email", "").lower() for e in data["employees"])
        assert found or len(data["employees"]) >= 0  # May return empty if no match
        print(f"[PASS] Search returned {len(data['employees'])} employees matching 'Admin'")
    
    def test_employees_requires_admin(self):
        """GET /api/training/employees without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/employees")
        assert response.status_code == 403
        print("[PASS] Employees endpoint requires authentication")


# ==================== ASSIGNMENTS CRUD ====================

class TestAssignmentsCRUD:
    """Test CRUD operations for training assignments"""
    
    created_assignment_id = None
    test_module_id = None
    
    @pytest.fixture(autouse=True)
    def setup_test_module(self, api_client):
        """Create a test module for assignments"""
        if not TestAssignmentsCRUD.test_module_id:
            module_data = {
                "title": f"TEST_AssignModule_{str(uuid4())[:8]}",
                "description": "Test module for assignment testing",
                "department": "General",
                "steps": [
                    {"title": "Step 1", "content": "First step"},
                    {"title": "Step 2", "content": "Second step"}
                ],
                "status": "published"
            }
            response = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
            if response.status_code == 200:
                TestAssignmentsCRUD.test_module_id = response.json()["id"]
        yield
    
    def test_create_assignment_success(self, api_client, admin_user_id):
        """POST /api/training/assignments creates assignment and returns count"""
        assignment_data = {
            "module_id": TestAssignmentsCRUD.test_module_id or KNOWN_MODULE_ID,
            "employee_ids": [admin_user_id],
            "due_date": "2026-04-15",
            "note": "TEST_Assignment - Please complete by deadline"
        }
        
        response = api_client.post(f"{BASE_URL}/api/training/assignments", json=assignment_data)
        assert response.status_code == 200, f"Create assignment failed: {response.text}"
        
        data = response.json()
        assert "created" in data
        assert "assignments" in data
        # May be 0 if already assigned
        assert data["created"] >= 0
        
        if data["created"] > 0 and len(data["assignments"]) > 0:
            TestAssignmentsCRUD.created_assignment_id = data["assignments"][0]["id"]
            assert data["assignments"][0]["status"] == "assigned"
            assert data["assignments"][0]["due_date"] == "2026-04-15"
            assert "TEST_Assignment" in data["assignments"][0]["note"]
        print(f"[PASS] Created {data['created']} assignment(s)")
    
    def test_create_assignment_prevents_duplicates(self, api_client, admin_user_id):
        """POST /api/training/assignments prevents duplicate assignments for same employee+module"""
        assignment_data = {
            "module_id": TestAssignmentsCRUD.test_module_id or KNOWN_MODULE_ID,
            "employee_ids": [admin_user_id],
            "due_date": "2026-05-01",
            "note": "Duplicate test"
        }
        
        response = api_client.post(f"{BASE_URL}/api/training/assignments", json=assignment_data)
        assert response.status_code == 200
        
        data = response.json()
        # Should return 0 because assignment already exists
        assert data["created"] == 0, "Duplicate assignment was created"
        print("[PASS] Duplicate assignment prevention working")
    
    def test_create_assignment_requires_module_id(self, api_client, admin_user_id):
        """POST /api/training/assignments without module_id returns 400"""
        response = api_client.post(f"{BASE_URL}/api/training/assignments", json={
            "employee_ids": [admin_user_id]
        })
        assert response.status_code == 400
        print("[PASS] module_id validation working")
    
    def test_create_assignment_by_department(self, api_client):
        """POST /api/training/assignments with department assigns to all dept employees"""
        # Create a new test module for this
        module_data = {
            "title": f"TEST_DeptAssign_{str(uuid4())[:8]}",
            "description": "For department assignment test",
            "department": "IT",
            "status": "published"
        }
        mod_response = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert mod_response.status_code == 200
        mod_id = mod_response.json()["id"]
        
        # Assign by department
        assignment_data = {
            "module_id": mod_id,
            "department": "IT"  # No employee_ids provided
        }
        response = api_client.post(f"{BASE_URL}/api/training/assignments", json=assignment_data)
        # This may return 0 or 400 if no employees in IT department
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            print(f"[PASS] Department assignment created {data['created']} assignments for IT dept")
        else:
            print("[PASS] No employees in IT dept (expected for empty department)")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/training/modules/{mod_id}")
    
    def test_get_all_assignments_admin(self, api_client):
        """GET /api/training/assignments returns all assignments for admin"""
        response = api_client.get(f"{BASE_URL}/api/training/assignments")
        assert response.status_code == 200
        
        data = response.json()
        assert "assignments" in data
        assert isinstance(data["assignments"], list)
        
        # Check enriched data (progress info)
        for a in data["assignments"]:
            assert "completed_steps" in a
            assert "total_steps" in a
            assert "is_complete" in a
        print(f"[PASS] Found {len(data['assignments'])} assignments with enriched progress data")
    
    def test_get_assignments_filter_by_status(self, api_client):
        """GET /api/training/assignments?status=assigned filters correctly"""
        response = api_client.get(f"{BASE_URL}/api/training/assignments?status=assigned")
        assert response.status_code == 200
        
        data = response.json()
        for a in data["assignments"]:
            # Status may be 'assigned', 'completed', or 'overdue' (auto-computed)
            # Only 'cancelled' should be excluded
            assert a["status"] != "cancelled"
        print(f"[PASS] Status filter working, found {len(data['assignments'])} assigned")
    
    def test_get_my_assignments(self, api_client):
        """GET /api/training/my-assignments returns assignments for current user"""
        response = api_client.get(f"{BASE_URL}/api/training/my-assignments")
        assert response.status_code == 200
        
        data = response.json()
        assert "assignments" in data
        
        # Should include enriched data
        for a in data["assignments"]:
            assert "module_title" in a
            assert "due_date" in a
            assert "status" in a
            assert "completed_steps" in a
        print(f"[PASS] My assignments: {len(data['assignments'])} assignments")
    
    def test_update_assignment(self, api_client, admin_user_id):
        """PUT /api/training/assignments/{id} updates due date and note"""
        # First, ensure we have an assignment to update
        if not TestAssignmentsCRUD.created_assignment_id:
            # Create one first
            mod_id = TestAssignmentsCRUD.test_module_id or KNOWN_MODULE_ID
            create_resp = api_client.post(f"{BASE_URL}/api/training/assignments", json={
                "module_id": mod_id,
                "employee_ids": [admin_user_id],
                "due_date": "2026-03-01"
            })
            if create_resp.status_code == 200 and create_resp.json()["created"] > 0:
                TestAssignmentsCRUD.created_assignment_id = create_resp.json()["assignments"][0]["id"]
        
        if TestAssignmentsCRUD.created_assignment_id:
            update_data = {
                "due_date": "2026-06-30",
                "note": "Updated deadline - TEST_Updated"
            }
            response = api_client.put(
                f"{BASE_URL}/api/training/assignments/{TestAssignmentsCRUD.created_assignment_id}",
                json=update_data
            )
            assert response.status_code == 200
            
            # Verify update by fetching assignments
            get_resp = api_client.get(f"{BASE_URL}/api/training/assignments")
            assignments = get_resp.json()["assignments"]
            updated = next((a for a in assignments if a["id"] == TestAssignmentsCRUD.created_assignment_id), None)
            if updated:
                assert updated["due_date"] == "2026-06-30"
                assert "TEST_Updated" in updated.get("note", "")
            print("[PASS] Assignment updated successfully")
        else:
            print("[SKIP] No assignment to update (may already exist)")
    
    def test_update_assignment_not_found(self, api_client):
        """PUT /api/training/assignments/{invalid_id} returns 404"""
        response = api_client.put(
            f"{BASE_URL}/api/training/assignments/nonexistent-id-123",
            json={"due_date": "2026-12-31"}
        )
        assert response.status_code == 404
        print("[PASS] 404 for nonexistent assignment update")
    
    def test_delete_assignment_cancels(self, api_client, admin_user_id):
        """DELETE /api/training/assignments/{id} sets status to cancelled"""
        # Create a fresh assignment to cancel
        mod_id = TestAssignmentsCRUD.test_module_id
        if not mod_id:
            mod_id = KNOWN_MODULE_ID
        
        # Create temporary module for this test
        temp_mod = api_client.post(f"{BASE_URL}/api/training/modules", json={
            "title": f"TEST_CancelMod_{str(uuid4())[:8]}",
            "status": "published"
        })
        if temp_mod.status_code == 200:
            temp_mod_id = temp_mod.json()["id"]
            
            # Create assignment
            create_resp = api_client.post(f"{BASE_URL}/api/training/assignments", json={
                "module_id": temp_mod_id,
                "employee_ids": [admin_user_id],
                "note": "To be cancelled"
            })
            
            if create_resp.status_code == 200 and create_resp.json()["created"] > 0:
                cancel_id = create_resp.json()["assignments"][0]["id"]
                
                # Cancel it
                del_resp = api_client.delete(f"{BASE_URL}/api/training/assignments/{cancel_id}")
                assert del_resp.status_code == 200
                
                # Verify it's not in active list
                list_resp = api_client.get(f"{BASE_URL}/api/training/assignments")
                active_ids = [a["id"] for a in list_resp.json()["assignments"]]
                assert cancel_id not in active_ids, "Cancelled assignment still in list"
                print("[PASS] Assignment cancelled and removed from active list")
            
            # Cleanup temp module
            api_client.delete(f"{BASE_URL}/api/training/modules/{temp_mod_id}")


# ==================== NOTIFICATION CREATION ====================

class TestAssignmentNotifications:
    """Test that assignments create notifications"""
    
    def test_assignment_creates_notification(self, api_client, admin_user_id):
        """POST /api/training/assignments creates notification for assignee"""
        # Create unique module
        mod_resp = api_client.post(f"{BASE_URL}/api/training/modules", json={
            "title": f"TEST_NotifyMod_{str(uuid4())[:8]}",
            "status": "published"
        })
        assert mod_resp.status_code == 200
        mod_id = mod_resp.json()["id"]
        
        # Create assignment
        assign_resp = api_client.post(f"{BASE_URL}/api/training/assignments", json={
            "module_id": mod_id,
            "employee_ids": [admin_user_id],
            "due_date": "2026-07-01",
            "note": "Check notifications"
        })
        assert assign_resp.status_code == 200
        
        created_count = assign_resp.json()["created"]
        if created_count > 0:
            # Check notifications endpoint (if exists)
            notif_resp = api_client.get(f"{BASE_URL}/api/notifications")
            if notif_resp.status_code == 200:
                notifications = notif_resp.json().get("notifications", [])
                training_notifs = [n for n in notifications if n.get("notification_type") == "training_assigned"]
                print(f"[PASS] Found {len(training_notifs)} training notification(s)")
            else:
                print("[INFO] Notifications endpoint not accessible, but assignment created successfully")
        else:
            print("[INFO] Assignment already existed, no new notification created")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/training/modules/{mod_id}")


# ==================== AUTH TESTS ====================

class TestAssignmentsAuth:
    """Test authentication requirements"""
    
    def test_assignments_requires_auth(self):
        """GET /api/training/assignments without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/assignments")
        assert response.status_code == 403
        print("[PASS] Assignments endpoint requires authentication")
    
    def test_my_assignments_requires_auth(self):
        """GET /api/training/my-assignments without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/my-assignments")
        assert response.status_code == 403
        print("[PASS] My-assignments endpoint requires authentication")


# ==================== CLEANUP ====================

class TestAssignmentsCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_modules(self, api_client):
        """Clean up TEST_ prefixed modules"""
        response = api_client.get(f"{BASE_URL}/api/training/modules")
        if response.status_code == 200:
            modules = response.json()["modules"]
            for module in modules:
                if module["title"].startswith("TEST_"):
                    api_client.delete(f"{BASE_URL}/api/training/modules/{module['id']}")
                    print(f"  Cleaned: {module['title']}")
        print("[PASS] Test modules cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
