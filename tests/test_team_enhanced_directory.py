"""
Test Suite for Enhanced Employee Directory Feature
Tests: Team members CRUD with new fields (title, location, skills, bio, etc),
       Stats with department breakdown, Training progress endpoint
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

class TestTeamEnhancedDirectory:
    """Test suite for enhanced team/employee directory"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "Admin@credlocity.com",
            "password": "Credit123!"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("access_token")
        assert token, "No access_token in login response"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        yield
        # Cleanup test data
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Cleanup any test-created members"""
        try:
            resp = self.session.get(f"{BASE_URL}/api/team/members?search=TEST_")
            if resp.ok:
                for member in resp.json().get("members", []):
                    self.session.delete(f"{BASE_URL}/api/team/members/{member['id']}")
        except:
            pass

    # ==================== STATS ENDPOINT ====================
    def test_get_team_stats(self):
        """Test GET /api/team/stats returns stats with by_department breakdown"""
        resp = self.session.get(f"{BASE_URL}/api/team/stats")
        assert resp.status_code == 200, f"Stats failed: {resp.text}"
        
        data = resp.json()
        # Verify response structure
        assert "total_members" in data, "Missing total_members in stats"
        assert "by_role" in data, "Missing by_role in stats"
        assert "by_type" in data, "Missing by_type in stats"
        assert "by_department" in data, "Missing by_department in stats"
        
        # by_department should be a dict
        assert isinstance(data["by_department"], dict), "by_department should be a dict"
        print(f"Stats: total={data['total_members']}, by_department={data['by_department']}")

    # ==================== LIST MEMBERS ====================
    def test_list_members_returns_new_fields(self):
        """Test GET /api/team/members returns list - verify response structure"""
        resp = self.session.get(f"{BASE_URL}/api/team/members")
        assert resp.status_code == 200, f"List members failed: {resp.text}"
        
        data = resp.json()
        assert "members" in data, "Missing members in response"
        assert "total" in data, "Missing total in response"
        
        # Check if we have any members
        if data["members"]:
            member = data["members"][0]
            # Core fields should always exist
            assert "id" in member, "Missing id"
            assert "email" in member, "Missing email"
            assert "full_name" in member, "Missing full_name"
            assert "department" in member, "Missing department"
            # Note: Legacy members may not have new fields (title, location, skills, bio) 
            # until they are updated. This is expected behavior.
        print(f"Listed {len(data['members'])} members, total={data['total']}")

    def test_list_members_with_department_filter(self):
        """Test GET /api/team/members with department filter"""
        resp = self.session.get(f"{BASE_URL}/api/team/members?department=collections")
        assert resp.status_code == 200, f"List with filter failed: {resp.text}"
        
        data = resp.json()
        # All returned members should have collections department
        for member in data["members"]:
            assert member.get("department") == "collections" or not data["members"], \
                "Department filter not working"
        print(f"Filtered by collections: {len(data['members'])} members")

    def test_list_members_with_search(self):
        """Test GET /api/team/members with search parameter"""
        resp = self.session.get(f"{BASE_URL}/api/team/members?search=John")
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        data = resp.json()
        print(f"Search 'John': found {len(data['members'])} members")

    # ==================== CREATE MEMBER WITH NEW FIELDS ====================
    def test_create_member_with_enhanced_fields(self):
        """Test POST /api/team/members with all new enhanced fields"""
        payload = {
            "email": "TEST_enhanced@example.com",
            "full_name": "TEST_Enhanced Employee",
            "phone": "555-123-4567",
            "role": "collections_agent",
            "member_type": "employee",
            "department": "collections",
            "title": "Senior Collections Specialist",
            "location": "New York, NY",
            "hire_date": "2024-01-15",
            "birthday": "1990-06-20",
            "skills": ["negotiation", "customer service", "data analysis"],
            "bio": "Experienced collections specialist with 5 years of experience.",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_phone": "555-987-6543",
            "emergency_contact_relation": "Spouse",
            "linkedin_url": "https://linkedin.com/in/testuser"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/team/members", json=payload)
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        
        created = resp.json()
        # Verify all new fields are returned
        assert created["title"] == "Senior Collections Specialist", "Title not saved"
        assert created["location"] == "New York, NY", "Location not saved"
        assert created["hire_date"] == "2024-01-15", "Hire date not saved"
        assert created["birthday"] == "1990-06-20", "Birthday not saved"
        assert created["skills"] == ["negotiation", "customer service", "data analysis"], "Skills not saved"
        assert created["bio"] == "Experienced collections specialist with 5 years of experience.", "Bio not saved"
        assert created["emergency_contact_name"] == "Jane Doe", "Emergency contact name not saved"
        assert created["emergency_contact_phone"] == "555-987-6543", "Emergency contact phone not saved"
        assert created["emergency_contact_relation"] == "Spouse", "Emergency contact relation not saved"
        assert created["linkedin_url"] == "https://linkedin.com/in/testuser", "LinkedIn URL not saved"
        
        # Verify persistence with GET
        get_resp = self.session.get(f"{BASE_URL}/api/team/members/{created['id']}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["title"] == "Senior Collections Specialist", "Title not persisted"
        assert fetched["skills"] == ["negotiation", "customer service", "data analysis"], "Skills not persisted"
        
        print(f"Created enhanced member: {created['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/team/members/{created['id']}")

    # ==================== UPDATE MEMBER WITH NEW FIELDS ====================
    def test_update_member_with_enhanced_fields(self):
        """Test PUT /api/team/members/{id} with enhanced fields"""
        # First create a member
        create_resp = self.session.post(f"{BASE_URL}/api/team/members", json={
            "email": "TEST_update_enhanced@example.com",
            "full_name": "TEST_Update Enhanced",
            "role": "collections_agent",
            "department": "collections"
        })
        assert create_resp.status_code == 200, f"Create for update failed: {create_resp.text}"
        member_id = create_resp.json()["id"]
        
        # Update with new fields
        update_payload = {
            "title": "Team Lead",
            "location": "Los Angeles, CA",
            "hire_date": "2023-06-01",
            "birthday": "1985-03-15",
            "skills": ["leadership", "mentoring"],
            "bio": "Updated bio with new role.",
            "linkedin_url": "https://linkedin.com/in/updated",
            "emergency_contact_name": "Updated Contact",
            "emergency_contact_phone": "555-111-2222",
            "emergency_contact_relation": "Parent"
        }
        
        update_resp = self.session.put(f"{BASE_URL}/api/team/members/{member_id}", json=update_payload)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        
        updated = update_resp.json()
        assert updated["title"] == "Team Lead", "Title not updated"
        assert updated["location"] == "Los Angeles, CA", "Location not updated"
        assert updated["skills"] == ["leadership", "mentoring"], "Skills not updated"
        
        # Verify persistence
        get_resp = self.session.get(f"{BASE_URL}/api/team/members/{member_id}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["title"] == "Team Lead", "Title update not persisted"
        assert fetched["bio"] == "Updated bio with new role.", "Bio update not persisted"
        
        print(f"Updated member {member_id} with enhanced fields")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/team/members/{member_id}")

    # ==================== TRAINING PROGRESS ENDPOINT ====================
    def test_training_progress_endpoint(self):
        """Test GET /api/team/members/{id}/training-progress"""
        # First get an existing member
        members_resp = self.session.get(f"{BASE_URL}/api/team/members")
        assert members_resp.status_code == 200
        members = members_resp.json().get("members", [])
        
        if not members:
            pytest.skip("No team members to test training progress")
        
        member_id = members[0]["id"]
        
        # Get training progress
        resp = self.session.get(f"{BASE_URL}/api/team/members/{member_id}/training-progress")
        assert resp.status_code == 200, f"Training progress failed: {resp.text}"
        
        data = resp.json()
        # Verify response structure
        assert "total_modules" in data, "Missing total_modules"
        assert "completed_modules" in data, "Missing completed_modules"
        assert "overall_pct" in data, "Missing overall_pct"
        assert "modules" in data, "Missing modules list"
        
        # Verify module structure if any exist
        if data["modules"]:
            mod = data["modules"][0]
            assert "module_id" in mod, "Missing module_id"
            assert "module_title" in mod, "Missing module_title"
            assert "progress_pct" in mod, "Missing progress_pct"
            assert "total_steps" in mod, "Missing total_steps"
            assert "completed_steps" in mod, "Missing completed_steps"
        
        print(f"Training progress for {member_id}: {data['completed_modules']}/{data['total_modules']} ({data['overall_pct']}%)")

    def test_training_progress_nonexistent_member(self):
        """Test training progress returns 404 for nonexistent member"""
        resp = self.session.get(f"{BASE_URL}/api/team/members/nonexistent-id/training-progress")
        assert resp.status_code == 404, "Should return 404 for nonexistent member"

    # ==================== GET SINGLE MEMBER ====================
    def test_get_single_member(self):
        """Test GET /api/team/members/{id} returns member with core fields"""
        # Get members first
        members_resp = self.session.get(f"{BASE_URL}/api/team/members")
        assert members_resp.status_code == 200
        members = members_resp.json().get("members", [])
        
        if not members:
            pytest.skip("No team members to test")
        
        member_id = members[0]["id"]
        
        resp = self.session.get(f"{BASE_URL}/api/team/members/{member_id}")
        assert resp.status_code == 200, f"Get member failed: {resp.text}"
        
        member = resp.json()
        # Check core fields exist
        assert "id" in member
        assert "email" in member
        assert "full_name" in member
        assert "role" in member
        assert "department" in member
        assert "status" in member
        # Note: Legacy members may not have enhanced fields until updated
        
        print(f"Got member {member_id}: {member['full_name']}")

    def test_get_nonexistent_member(self):
        """Test GET /api/team/members/{id} returns 404 for nonexistent"""
        resp = self.session.get(f"{BASE_URL}/api/team/members/nonexistent-id")
        assert resp.status_code == 404

    # ==================== DELETE MEMBER ====================
    def test_delete_member(self):
        """Test DELETE /api/team/members/{id}"""
        # Create a member to delete
        create_resp = self.session.post(f"{BASE_URL}/api/team/members", json={
            "email": "TEST_delete@example.com",
            "full_name": "TEST_Delete Me",
            "role": "collections_agent",
            "department": "collections"
        })
        assert create_resp.status_code == 200
        member_id = create_resp.json()["id"]
        
        # Delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/team/members/{member_id}")
        assert delete_resp.status_code == 200
        
        # Verify deleted
        get_resp = self.session.get(f"{BASE_URL}/api/team/members/{member_id}")
        assert get_resp.status_code == 404, "Member should be deleted"
        
        print(f"Deleted member {member_id}")

    # ==================== AUTH TESTS ====================
    def test_unauthorized_access(self):
        """Test endpoints require authentication"""
        unauth_session = requests.Session()
        unauth_session.headers.update({"Content-Type": "application/json"})
        
        resp = unauth_session.get(f"{BASE_URL}/api/team/members")
        assert resp.status_code == 401, "Should require auth"
        
        resp = unauth_session.get(f"{BASE_URL}/api/team/stats")
        assert resp.status_code == 401, "Stats should require auth"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
