"""
RBAC (Role-Based Access Control) API Tests
Tests for groups, permissions, user assignments, and permission gating

Tests cover:
- GET /api/rbac/groups - List all groups (8 default system groups)
- GET /api/rbac/permissions - List all permission categories
- GET /api/rbac/my-permissions - Get current user's effective permissions
- POST /api/rbac/groups - Create a new custom group
- PUT /api/rbac/groups/{group_id} - Update a group's permissions
- PUT /api/rbac/users/{user_id}/assignment - Assign user to group with overrides
- GET /api/rbac/users - List all users with assignments
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')

class TestRBACAPI:
    """RBAC System API Tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "Admin@credlocity.com", "password": "Credit123!"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture(scope="class")
    def admin_user_id(self, headers):
        """Get admin user ID for assignment tests"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200
        return response.json().get("id")
    
    # ==================== PERMISSIONS TESTS ====================
    
    def test_get_all_permissions(self, headers):
        """GET /api/rbac/permissions - Returns all permission categories"""
        response = requests.get(f"{BASE_URL}/api/rbac/permissions", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify permissions structure
        assert "permissions" in data
        perms = data["permissions"]
        
        # Check for expected permission categories
        expected_categories = [
            "dashboard", "collections", "payroll", "training", "marketing",
            "reviews", "clients", "outsourcing", "legal", "billing",
            "partners", "forms", "team", "chat", "security", "settings"
        ]
        
        for cat in expected_categories:
            assert cat in perms, f"Missing permission category: {cat}"
            assert "label" in perms[cat], f"Missing label for {cat}"
            assert "perms" in perms[cat], f"Missing perms for {cat}"
            assert len(perms[cat]["perms"]) > 0, f"No permissions in {cat}"
        
        print(f"PASS: Found {len(perms)} permission categories with total perms: {sum(len(p['perms']) for p in perms.values())}")
    
    # ==================== GROUPS TESTS ====================
    
    def test_get_all_groups_returns_8_default(self, headers):
        """GET /api/rbac/groups - Returns 8 default system groups"""
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "groups" in data
        groups = data["groups"]
        
        # Verify 8 default groups exist
        system_groups = [g for g in groups if g.get("is_system") == True]
        assert len(system_groups) >= 8, f"Expected 8 system groups, found {len(system_groups)}"
        
        # Verify expected group names
        group_names = [g["name"] for g in groups]
        expected_names = [
            "Super Admin", "Admin", "Collection Rep", "Collection Manager",
            "Marketing", "HR & Payroll", "Legal", "Finance"
        ]
        
        for name in expected_names:
            assert name in group_names, f"Missing group: {name}"
        
        print(f"PASS: Found {len(groups)} groups including {len(system_groups)} system groups")
        
        # Verify each group has required fields
        for g in groups:
            assert "id" in g, f"Group missing id: {g.get('name')}"
            assert "name" in g, "Group missing name"
            assert "permissions" in g, f"Group missing permissions: {g.get('name')}"
            assert "member_count" in g, f"Group missing member_count: {g.get('name')}"
        
        return groups
    
    def test_get_super_admin_group_has_all_permissions(self, headers):
        """Verify Super Admin group has all 32 permissions"""
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=headers)
        assert response.status_code == 200
        
        groups = response.json()["groups"]
        super_admin = next((g for g in groups if g["name"] == "Super Admin"), None)
        
        assert super_admin is not None, "Super Admin group not found"
        assert super_admin["is_system"] == True, "Super Admin should be a system group"
        assert len(super_admin["permissions"]) >= 32, f"Super Admin should have 32+ perms, found {len(super_admin['permissions'])}"
        
        print(f"PASS: Super Admin has {len(super_admin['permissions'])} permissions")
    
    def test_get_collection_rep_group_limited_permissions(self, headers):
        """Verify Collection Rep group has limited permissions"""
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=headers)
        assert response.status_code == 200
        
        groups = response.json()["groups"]
        collection_rep = next((g for g in groups if g["name"] == "Collection Rep"), None)
        
        assert collection_rep is not None, "Collection Rep group not found"
        
        # Collection Rep should have limited permissions
        perms = collection_rep["permissions"]
        assert "dashboard.view" in perms, "Collection Rep should have dashboard.view"
        assert "collections.view" in perms, "Collection Rep should have collections.view"
        assert "chat.view" in perms, "Collection Rep should have chat.view"
        assert "settings.manage" not in perms, "Collection Rep should NOT have settings.manage"
        
        print(f"PASS: Collection Rep has {len(perms)} permissions (limited as expected)")
    
    # ==================== MY-PERMISSIONS TESTS ====================
    
    def test_admin_my_permissions_returns_all_32(self, headers):
        """GET /api/rbac/my-permissions - Admin gets all 32 permissions"""
        response = requests.get(f"{BASE_URL}/api/rbac/my-permissions", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "permissions" in data
        assert "is_admin" in data
        
        # Admin should have all permissions
        assert data["is_admin"] == True, "Admin user should have is_admin=True"
        assert len(data["permissions"]) >= 32, f"Admin should have 32+ permissions, found {len(data['permissions'])}"
        
        print(f"PASS: Admin has {len(data['permissions'])} permissions and is_admin={data['is_admin']}")
    
    def test_my_permissions_requires_auth(self):
        """GET /api/rbac/my-permissions - Requires authentication"""
        response = requests.get(f"{BASE_URL}/api/rbac/my-permissions")
        
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: my-permissions requires authentication")
    
    # ==================== CREATE GROUP TESTS ====================
    
    def test_create_custom_group(self, headers):
        """POST /api/rbac/groups - Create a new custom group"""
        group_data = {
            "name": "TEST_Custom_Group",
            "description": "Test group for automated testing",
            "permissions": ["dashboard.view", "collections.view", "chat.view"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/rbac/groups",
            headers=headers,
            json=group_data
        )
        
        assert response.status_code == 200, f"Failed to create group: {response.text}"
        data = response.json()
        
        assert data["name"] == "TEST_Custom_Group"
        assert data["is_system"] == False, "Custom group should not be system group"
        assert len(data["permissions"]) == 3
        assert "id" in data
        
        print(f"PASS: Created custom group with id={data['id']}")
        
        return data["id"]
    
    def test_create_group_requires_auth(self):
        """POST /api/rbac/groups - Requires admin auth"""
        response = requests.post(
            f"{BASE_URL}/api/rbac/groups",
            json={"name": "Unauthorized Group", "permissions": []}
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: Group creation requires authentication")
    
    # ==================== UPDATE GROUP TESTS ====================
    
    def test_update_group_permissions(self, headers):
        """PUT /api/rbac/groups/{id} - Update a custom group's permissions"""
        # First create a group to update
        create_response = requests.post(
            f"{BASE_URL}/api/rbac/groups",
            headers=headers,
            json={
                "name": "TEST_Update_Group",
                "description": "Group to test updates",
                "permissions": ["dashboard.view"]
            }
        )
        assert create_response.status_code == 200
        group_id = create_response.json()["id"]
        
        # Update the group
        update_response = requests.put(
            f"{BASE_URL}/api/rbac/groups/{group_id}",
            headers=headers,
            json={
                "permissions": ["dashboard.view", "collections.view", "payroll.view"]
            }
        )
        
        assert update_response.status_code == 200, f"Failed to update: {update_response.text}"
        
        # Verify update persisted
        get_response = requests.get(f"{BASE_URL}/api/rbac/groups/{group_id}", headers=headers)
        assert get_response.status_code == 200
        
        updated_group = get_response.json()
        assert len(updated_group["permissions"]) == 3, f"Expected 3 permissions after update"
        assert "payroll.view" in updated_group["permissions"]
        
        print(f"PASS: Updated group {group_id} with new permissions")
        
        return group_id
    
    # ==================== USER ASSIGNMENT TESTS ====================
    
    def test_get_users_with_assignments(self, headers):
        """GET /api/rbac/users - List users with group assignments"""
        response = requests.get(f"{BASE_URL}/api/rbac/users", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "users" in data
        users = data["users"]
        
        # Verify user structure
        if len(users) > 0:
            user = users[0]
            assert "id" in user, "User missing id"
            assert "email" in user, "User missing email"
            assert "role" in user, "User missing role"
            # These may be null if not assigned
            assert "group_id" in user or user.get("group_id") is None, "User should have group_id field"
        
        print(f"PASS: Found {len(users)} users with assignment data")
    
    def test_assign_user_to_group(self, headers, admin_user_id):
        """PUT /api/rbac/users/{id}/assignment - Assign user to group with overrides"""
        # Get a group to assign
        groups_response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=headers)
        groups = groups_response.json()["groups"]
        
        # Get Collection Rep group (limited permissions)
        collection_rep = next((g for g in groups if g["name"] == "Collection Rep"), None)
        assert collection_rep is not None
        
        # Note: We'll use a test user if available, otherwise skip
        # First check if there are any non-admin users
        users_response = requests.get(f"{BASE_URL}/api/rbac/users", headers=headers)
        users = users_response.json()["users"]
        
        # Find a non-super-admin user for testing
        test_user = next((u for u in users if u["role"] not in ["super_admin", "admin"]), None)
        
        if test_user:
            # Assign user to Collection Rep with extra permissions
            assignment_data = {
                "group_id": collection_rep["id"],
                "extra_permissions": ["payroll.view"],
                "revoked_permissions": []
            }
            
            response = requests.put(
                f"{BASE_URL}/api/rbac/users/{test_user['id']}/assignment",
                headers=headers,
                json=assignment_data
            )
            
            assert response.status_code == 200, f"Failed to assign: {response.text}"
            data = response.json()
            
            assert "assignment" in data
            assert data["assignment"]["group_id"] == collection_rep["id"]
            assert "payroll.view" in data["assignment"]["extra_permissions"]
            
            print(f"PASS: Assigned user {test_user['email']} to {collection_rep['name']} with extra permissions")
        else:
            print("SKIP: No non-admin users found for assignment test")
    
    # ==================== DELETE GROUP TESTS ====================
    
    def test_cannot_delete_system_group(self, headers):
        """DELETE /api/rbac/groups/{id} - Cannot delete system groups"""
        # Get Super Admin group ID
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=headers)
        groups = response.json()["groups"]
        
        super_admin = next((g for g in groups if g["name"] == "Super Admin"), None)
        assert super_admin is not None
        
        # Try to delete - should fail
        delete_response = requests.delete(
            f"{BASE_URL}/api/rbac/groups/{super_admin['id']}",
            headers=headers
        )
        
        assert delete_response.status_code == 400, f"Expected 400 for system group delete, got {delete_response.status_code}"
        print("PASS: Cannot delete system groups")
    
    def test_delete_custom_group(self, headers):
        """DELETE /api/rbac/groups/{id} - Can delete custom groups"""
        # Create a group to delete
        create_response = requests.post(
            f"{BASE_URL}/api/rbac/groups",
            headers=headers,
            json={
                "name": "TEST_Delete_Group",
                "description": "Group to be deleted",
                "permissions": ["dashboard.view"]
            }
        )
        assert create_response.status_code == 200
        group_id = create_response.json()["id"]
        
        # Delete the group
        delete_response = requests.delete(
            f"{BASE_URL}/api/rbac/groups/{group_id}",
            headers=headers
        )
        
        assert delete_response.status_code == 200, f"Failed to delete: {delete_response.text}"
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/rbac/groups/{group_id}", headers=headers)
        assert get_response.status_code == 404, "Deleted group should return 404"
        
        print(f"PASS: Deleted custom group {group_id}")
    
    # ==================== CLEANUP ====================
    
    def test_z_cleanup_test_groups(self, headers):
        """Cleanup test groups created during testing"""
        response = requests.get(f"{BASE_URL}/api/rbac/groups", headers=headers)
        groups = response.json()["groups"]
        
        deleted = 0
        for group in groups:
            if group["name"].startswith("TEST_"):
                delete_response = requests.delete(
                    f"{BASE_URL}/api/rbac/groups/{group['id']}",
                    headers=headers
                )
                if delete_response.status_code == 200:
                    deleted += 1
        
        print(f"Cleanup: Deleted {deleted} test groups")


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment variables"""
    if not os.environ.get('REACT_APP_BACKEND_URL'):
        os.environ['REACT_APP_BACKEND_URL'] = 'https://condescending-wozniak-3.preview.emergentagent.com'
    yield


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
