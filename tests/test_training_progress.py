"""
Test suite for Credlocity Employee Training Progress Tracking API
Tests progress tracking endpoints: my-progress, modules/{id}/progress, progress-report, progress/dashboard
"""

import pytest
import requests
import os
from uuid import uuid4

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com').rstrip('/')

# Test credentials - Admin user
TEST_EMAIL = "Admin@credlocity.com"
TEST_PASSWORD = "Credit123!"

# Known module ID with existing progress
KNOWN_MODULE_ID = "48654d67-5c47-4add-aa0e-733e6c8c8192"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for Admin user"""
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


# ==================== MY-PROGRESS ENDPOINT ====================

class TestMyProgress:
    """Test GET /api/training/my-progress endpoint - returns user's progress map"""
    
    def test_get_my_progress_returns_map(self, api_client):
        """GET /api/training/my-progress returns progress map (module_id -> progress record)"""
        response = api_client.get(f"{BASE_URL}/api/training/my-progress")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "progress" in data, "Response missing 'progress' field"
        assert isinstance(data["progress"], dict), "Progress should be a dict (map)"
        
        print(f"[PASS] my-progress returns progress map with {len(data['progress'])} modules")
        
        # If existing progress exists, verify structure
        if data["progress"]:
            sample_module_id = list(data["progress"].keys())[0]
            progress_record = data["progress"][sample_module_id]
            
            # Verify progress record structure
            assert "module_id" in progress_record, "Missing module_id in progress record"
            assert "completed_steps" in progress_record, "Missing completed_steps array"
            assert "is_complete" in progress_record, "Missing is_complete flag"
            assert "total_steps" in progress_record, "Missing total_steps"
            
            print(f"  Sample progress record: module={progress_record['module_id']}, "
                  f"completed_steps={len(progress_record['completed_steps'])}, "
                  f"is_complete={progress_record['is_complete']}")
    
    def test_my_progress_requires_auth(self):
        """GET /api/training/my-progress without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/my-progress")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("[PASS] my-progress endpoint requires authentication")


# ==================== MODULE PROGRESS UPDATE ENDPOINT ====================

class TestModuleProgressUpdate:
    """Test POST /api/training/modules/{id}/progress endpoint"""
    
    test_module_id = None
    
    @pytest.fixture(autouse=True)
    def setup_test_module(self, api_client):
        """Create a test module for progress tests"""
        # Create test module with steps
        module_data = {
            "title": f"TEST_ProgressModule_{str(uuid4())[:8]}",
            "description": "Test module for progress tracking",
            "department": "IT",
            "content": "<p>Test content</p>",
            "steps": [
                {"title": "Step 1", "content": "First step", "image_url": ""},
                {"title": "Step 2", "content": "Second step", "image_url": ""},
                {"title": "Step 3", "content": "Third step", "image_url": ""}
            ],
            "status": "published",
            "order": 99
        }
        
        response = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        if response.status_code == 200:
            TestModuleProgressUpdate.test_module_id = response.json()["id"]
        
        yield
        
        # Cleanup: Delete test module
        if TestModuleProgressUpdate.test_module_id:
            api_client.delete(f"{BASE_URL}/api/training/modules/{TestModuleProgressUpdate.test_module_id}")
    
    def test_create_progress_with_completed_steps(self, api_client):
        """POST /api/training/modules/{id}/progress creates progress with completed_steps array"""
        module_id = TestModuleProgressUpdate.test_module_id
        if not module_id:
            pytest.skip("Test module not created")
        
        progress_data = {
            "completed_steps": [0, 1],  # Mark first two steps complete
            "is_complete": False
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/progress",
            json=progress_data
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["module_id"] == module_id
        assert data["completed_steps"] == [0, 1]
        assert data["is_complete"] == False
        assert data["total_steps"] == 3
        
        print(f"[PASS] Created progress: {len(data['completed_steps'])}/3 steps completed")
    
    def test_update_progress_adds_more_steps(self, api_client):
        """POST /api/training/modules/{id}/progress updates existing progress"""
        module_id = TestModuleProgressUpdate.test_module_id
        if not module_id:
            pytest.skip("Test module not created")
        
        # Update to include step 2 as well
        progress_data = {
            "completed_steps": [0, 1, 2],  # All three steps
            "is_complete": False
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/progress",
            json=progress_data
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["completed_steps"] == [0, 1, 2]
        
        print(f"[PASS] Updated progress: {len(data['completed_steps'])}/3 steps completed")
    
    def test_auto_complete_when_all_steps_done(self, api_client):
        """POST /api/training/modules/{id}/progress auto-sets is_complete=true when all steps are completed"""
        module_id = TestModuleProgressUpdate.test_module_id
        if not module_id:
            pytest.skip("Test module not created")
        
        # Complete all steps
        progress_data = {
            "completed_steps": [0, 1, 2],  # All 3 steps
            "is_complete": False  # Not explicitly set, should be auto-set to True
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/progress",
            json=progress_data
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # When all steps are completed, is_complete should be auto-set to True
        assert data["is_complete"] == True, f"Expected is_complete=True, got {data['is_complete']}"
        assert data["total_steps"] == 3
        assert len(data["completed_steps"]) == 3
        
        print("[PASS] Auto-complete working: is_complete=True when all steps done")
    
    def test_progress_for_nonexistent_module_returns_404(self, api_client):
        """POST /api/training/modules/{invalid_id}/progress returns 404"""
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/nonexistent-module-xyz/progress",
            json={"completed_steps": [0], "is_complete": False}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("[PASS] 404 returned for progress on nonexistent module")


# ==================== MODULE PROGRESS REPORT (Admin Only) ====================

class TestModuleProgressReport:
    """Test GET /api/training/modules/{id}/progress-report endpoint (admin only)"""
    
    def test_get_progress_report_returns_stats(self, api_client):
        """GET /api/training/modules/{id}/progress-report returns completion stats and employee list"""
        # Use known module with progress
        module_id = KNOWN_MODULE_ID
        
        response = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}/progress-report")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "module_id" in data, "Missing module_id"
        assert "module_title" in data, "Missing module_title"
        assert "total_assigned" in data, "Missing total_assigned"
        assert "completed" in data, "Missing completed count"
        assert "in_progress" in data, "Missing in_progress count"
        assert "employees" in data, "Missing employees list"
        
        print(f"[PASS] Progress report for module '{data['module_title']}':")
        print(f"  - Total started: {data['total_assigned']}")
        print(f"  - Completed: {data['completed']}")
        print(f"  - In progress: {data['in_progress']}")
        print(f"  - Employees: {len(data['employees'])}")
        
        # If there are employees, verify structure
        if data["employees"]:
            emp = data["employees"][0]
            assert "user_id" in emp, "Employee missing user_id"
            assert "completed_steps" in emp, "Employee missing completed_steps"
            assert "is_complete" in emp, "Employee missing is_complete"
    
    def test_progress_report_requires_auth(self):
        """GET /api/training/modules/{id}/progress-report without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/modules/{KNOWN_MODULE_ID}/progress-report")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("[PASS] progress-report endpoint requires authentication")
    
    def test_progress_report_nonexistent_module_returns_404(self, api_client):
        """GET /api/training/modules/{invalid_id}/progress-report returns 404"""
        response = api_client.get(f"{BASE_URL}/api/training/modules/nonexistent-module-xyz/progress-report")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("[PASS] 404 returned for progress-report on nonexistent module")


# ==================== PROGRESS DASHBOARD (Admin Only) ====================

class TestProgressDashboard:
    """Test GET /api/training/progress/dashboard endpoint (admin only)"""
    
    def test_get_dashboard_returns_total_stats(self, api_client):
        """GET /api/training/progress/dashboard returns total stats"""
        response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        
        # Verify total stats
        assert "total_modules" in data, "Missing total_modules"
        assert "total_completions" in data, "Missing total_completions"
        assert "total_in_progress" in data, "Missing total_in_progress"
        
        print(f"[PASS] Dashboard total stats:")
        print(f"  - Published modules: {data['total_modules']}")
        print(f"  - Total completions: {data['total_completions']}")
        print(f"  - In progress: {data['total_in_progress']}")
    
    def test_dashboard_returns_module_stats(self, api_client):
        """GET /api/training/progress/dashboard returns module_stats array"""
        response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        assert "module_stats" in data, "Missing module_stats"
        assert isinstance(data["module_stats"], list), "module_stats should be a list"
        
        # Verify module_stats structure if not empty
        if data["module_stats"]:
            ms = data["module_stats"][0]
            assert "module_id" in ms, "Module stat missing module_id"
            assert "title" in ms, "Module stat missing title"
            assert "department" in ms, "Module stat missing department"
            assert "total_steps" in ms, "Module stat missing total_steps"
            assert "employees_started" in ms, "Module stat missing employees_started"
            assert "employees_completed" in ms, "Module stat missing employees_completed"
            assert "completion_rate" in ms, "Module stat missing completion_rate"
            
            print(f"[PASS] Module stats sample: {ms['title']}")
            print(f"  - Completion rate: {ms['completion_rate']}%")
            print(f"  - Started: {ms['employees_started']}, Completed: {ms['employees_completed']}")
    
    def test_dashboard_returns_department_stats(self, api_client):
        """GET /api/training/progress/dashboard returns department_stats dict"""
        response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        assert "department_stats" in data, "Missing department_stats"
        assert isinstance(data["department_stats"], dict), "department_stats should be a dict"
        
        # Verify department stats structure if not empty
        if data["department_stats"]:
            dept = list(data["department_stats"].keys())[0]
            stats = data["department_stats"][dept]
            assert "total_modules" in stats, "Dept stat missing total_modules"
            assert "total_completions" in stats, "Dept stat missing total_completions"
            assert "total_started" in stats, "Dept stat missing total_started"
            
            print(f"[PASS] Department stats sample: {dept}")
            print(f"  - Modules: {stats['total_modules']}, Completions: {stats['total_completions']}")
    
    def test_dashboard_returns_top_performers(self, api_client):
        """GET /api/training/progress/dashboard returns top_performers array"""
        response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        assert "top_performers" in data, "Missing top_performers"
        assert isinstance(data["top_performers"], list), "top_performers should be a list"
        
        # Verify top_performers structure if not empty
        if data["top_performers"]:
            tp = data["top_performers"][0]
            assert "user_name" in tp, "Top performer missing user_name"
            assert "count" in tp, "Top performer missing count"
            
            print(f"[PASS] Top performers (first 3):")
            for i, p in enumerate(data["top_performers"][:3]):
                print(f"  {i+1}. {p['user_name']}: {p['count']} modules completed")
    
    def test_dashboard_requires_auth(self):
        """GET /api/training/progress/dashboard without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("[PASS] progress/dashboard endpoint requires authentication")


# ==================== INTEGRATION TEST ====================

class TestProgressIntegration:
    """End-to-end test: create module, mark progress, verify in dashboard"""
    
    test_module_id = None
    
    def test_full_progress_flow(self, api_client):
        """E2E: Create module -> Mark steps complete -> Verify in dashboard"""
        
        # 1. Create a test module with steps
        module_data = {
            "title": f"TEST_E2E_Progress_{str(uuid4())[:8]}",
            "description": "E2E progress test module",
            "department": "Sales",
            "content": "<p>E2E test</p>",
            "steps": [
                {"title": "E2E Step 1", "content": "Step 1 content", "image_url": ""},
                {"title": "E2E Step 2", "content": "Step 2 content", "image_url": ""}
            ],
            "status": "published",
            "order": 99
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert create_response.status_code == 200, f"Failed to create module: {create_response.text}"
        TestProgressIntegration.test_module_id = create_response.json()["id"]
        module_id = TestProgressIntegration.test_module_id
        print(f"[Step 1] Created module: {module_id}")
        
        # 2. Check initial progress (should be empty for this module)
        progress_response = api_client.get(f"{BASE_URL}/api/training/my-progress")
        assert progress_response.status_code == 200
        initial_progress = progress_response.json()["progress"]
        assert module_id not in initial_progress, "New module should not have progress yet"
        print("[Step 2] Initial progress verified (empty for new module)")
        
        # 3. Mark first step complete
        step1_response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/progress",
            json={"completed_steps": [0], "is_complete": False}
        )
        assert step1_response.status_code == 200
        step1_data = step1_response.json()
        assert step1_data["completed_steps"] == [0]
        assert step1_data["is_complete"] == False
        print("[Step 3] Marked step 1 complete")
        
        # 4. Verify progress shows up in my-progress
        progress_response2 = api_client.get(f"{BASE_URL}/api/training/my-progress")
        updated_progress = progress_response2.json()["progress"]
        assert module_id in updated_progress, "Progress should show for module"
        assert updated_progress[module_id]["completed_steps"] == [0]
        print("[Step 4] Progress verified in my-progress")
        
        # 5. Complete all steps (should auto-complete module)
        complete_response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/progress",
            json={"completed_steps": [0, 1], "is_complete": False}
        )
        assert complete_response.status_code == 200
        complete_data = complete_response.json()
        assert complete_data["is_complete"] == True, "Should auto-complete when all steps done"
        print("[Step 5] All steps completed, module auto-completed")
        
        # 6. Verify module progress report shows completion
        report_response = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}/progress-report")
        assert report_response.status_code == 200
        report_data = report_response.json()
        assert report_data["completed"] >= 1, "Should show at least 1 completion"
        print(f"[Step 6] Progress report shows {report_data['completed']} completion(s)")
        
        # 7. Check dashboard includes this module
        dashboard_response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert dashboard_response.status_code == 200
        dashboard_data = dashboard_response.json()
        
        # Find our module in module_stats
        our_module_stat = None
        for ms in dashboard_data["module_stats"]:
            if ms["module_id"] == module_id:
                our_module_stat = ms
                break
        
        assert our_module_stat is not None, "Our module should appear in dashboard module_stats"
        assert our_module_stat["employees_completed"] >= 1
        print(f"[Step 7] Module found in dashboard with {our_module_stat['employees_completed']} completion(s)")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/training/modules/{module_id}")
        print("[Cleanup] Test module deleted")
        print("[PASS] Full progress flow completed successfully!")


# ==================== CLEANUP ====================

class TestProgressCleanup:
    """Cleanup any test progress data"""
    
    def test_cleanup_test_modules(self, api_client):
        """Clean up any TEST_ prefixed modules created by progress tests"""
        response = api_client.get(f"{BASE_URL}/api/training/modules")
        if response.status_code == 200:
            modules = response.json()["modules"]
            cleaned = 0
            for module in modules:
                if module["title"].startswith("TEST_"):
                    api_client.delete(f"{BASE_URL}/api/training/modules/{module['id']}")
                    cleaned += 1
                    print(f"  Cleaned up module: {module['title']}")
            if cleaned == 0:
                print("  No test modules to clean up")
        print("[PASS] Test modules cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
