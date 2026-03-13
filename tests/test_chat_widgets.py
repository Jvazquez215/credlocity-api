"""
Credlocity Chat Widgets API Tests
Tests: Public Chat Widget endpoints, CMS Chat Bubble record search, excluded pages management
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


# ==================== PUBLIC WIDGET SETTINGS (No Auth Required) ====================

class TestPublicWidgetSettings:
    """Tests for public widget settings endpoint - no auth required"""

    def test_get_widget_settings_success(self, api_client):
        """GET /api/support-chat/widget/settings - returns widget config without auth"""
        response = api_client.get(f"{BASE_URL}/api/support-chat/widget/settings")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "widget_enabled" in data
        assert "greeting_message" in data
        assert "widget_appearance" in data
        assert "excluded_pages" in data
        
        # Verify types
        assert isinstance(data["widget_enabled"], bool)
        assert isinstance(data["greeting_message"], str)
        assert isinstance(data["widget_appearance"], dict)
        assert isinstance(data["excluded_pages"], list)
        
        # Verify widget_appearance structure
        appearance = data["widget_appearance"]
        assert "primary_color" in appearance
        assert "position" in appearance
        assert "title" in appearance

    def test_get_widget_settings_includes_excluded_pages(self, api_client):
        """Widget settings should include excluded_pages list"""
        response = api_client.get(f"{BASE_URL}/api/support-chat/widget/settings")
        
        assert response.status_code == 200
        data = response.json()
        
        # excluded_pages should be a list of strings
        assert isinstance(data["excluded_pages"], list)


# ==================== CHAT SESSIONS WITH LEAD CREATION ====================

class TestChatSessionsWithLeadCreation:
    """Tests for chat session creation with lead generation"""

    def test_start_session_with_lead_creation(self, api_client):
        """POST /api/support-chat/sessions/start with create_lead=true creates Lead record"""
        payload = {
            "name": "TEST_ChatWidget_Lead",
            "email": f"TEST_chat_{os.urandom(4).hex()}@example.com",
            "phone": "555-111-2222",
            "page_url": "https://test-site.com/page",
            "create_lead": True
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/support-chat/sessions/start",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify session created
        assert "id" in data
        assert data["visitor_name"] == payload["name"]
        assert data["visitor_email"] == payload["email"]
        assert data["visitor_phone"] == payload["phone"]
        assert data["page_url"] == payload["page_url"]
        assert data["status"] == "waiting"
        
        # Verify lead was created
        assert "lead_id" in data
        assert data["lead_id"] is not None
        assert isinstance(data["lead_id"], str)
        assert len(data["lead_id"]) > 0

    def test_start_session_without_lead_creation(self, api_client):
        """POST /api/support-chat/sessions/start without create_lead should not create lead"""
        payload = {
            "name": "TEST_NoLead_Visitor",
            "email": f"TEST_nolead_{os.urandom(4).hex()}@example.com",
            "phone": "555-333-4444",
            "page_url": "https://test-site.com/page2",
            "create_lead": False
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/support-chat/sessions/start",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Session created but no lead
        assert "id" in data
        assert data["lead_id"] is None

    def test_start_session_minimal_info(self, api_client):
        """Session can be started with minimal visitor info"""
        payload = {
            "name": "Minimal User"
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/support-chat/sessions/start",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["visitor_name"] == "Minimal User"


# ==================== EXCLUDED PAGES MANAGEMENT (Admin Only) ====================

class TestExcludedPagesManagement:
    """Tests for admin-only excluded pages CRUD operations"""

    def test_get_excluded_pages_requires_auth(self, api_client):
        """GET /api/support-chat/widget/excluded-pages requires admin auth"""
        response = api_client.get(f"{BASE_URL}/api/support-chat/widget/excluded-pages")
        assert response.status_code in [401, 403]

    def test_get_excluded_pages_success(self, authenticated_client):
        """Admin can GET excluded pages list"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "pages" in data
        assert isinstance(data["pages"], list)

    def test_add_excluded_page_requires_auth(self, api_client):
        """POST /api/support-chat/widget/excluded-pages requires admin auth"""
        response = api_client.post(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages",
            json={"page_path": "/test-path"}
        )
        assert response.status_code in [401, 403]

    def test_add_and_delete_excluded_page(self, authenticated_client):
        """Admin can add and delete page exclusions"""
        test_path = f"/TEST_path_{os.urandom(4).hex()}"
        
        # Add exclusion
        add_response = authenticated_client.post(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages",
            json={"page_path": test_path}
        )
        
        assert add_response.status_code == 200
        add_data = add_response.json()
        assert add_data["page_path"] == test_path
        assert "id" in add_data
        
        page_id = add_data["id"]
        
        # Verify it's in the list
        get_response = authenticated_client.get(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages"
        )
        assert get_response.status_code == 200
        pages = get_response.json()["pages"]
        assert any(p["id"] == page_id for p in pages)
        
        # Delete exclusion
        delete_response = authenticated_client.delete(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages/{page_id}"
        )
        assert delete_response.status_code == 200
        
        # Verify it's removed
        get_response2 = authenticated_client.get(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages"
        )
        pages2 = get_response2.json()["pages"]
        assert not any(p["id"] == page_id for p in pages2)

    def test_add_duplicate_excluded_page_fails(self, authenticated_client):
        """Adding duplicate page path returns 409 conflict"""
        test_path = f"/TEST_dup_{os.urandom(4).hex()}"
        
        # Add first time
        response1 = authenticated_client.post(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages",
            json={"page_path": test_path}
        )
        assert response1.status_code == 200
        page_id = response1.json()["id"]
        
        # Try to add again
        response2 = authenticated_client.post(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages",
            json={"page_path": test_path}
        )
        assert response2.status_code == 409
        
        # Cleanup
        authenticated_client.delete(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages/{page_id}"
        )

    def test_delete_nonexistent_excluded_page_returns_404(self, authenticated_client):
        """Deleting non-existent page exclusion returns 404"""
        response = authenticated_client.delete(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages/nonexistent-id-12345"
        )
        assert response.status_code == 404


# ==================== RECORD SEARCH (CMS Chat Bubble) ====================

class TestRecordSearch:
    """Tests for CMS chat bubble record search functionality"""

    def test_search_records_requires_auth(self, api_client):
        """GET /api/chat/search-records requires authentication"""
        response = api_client.get(
            f"{BASE_URL}/api/chat/search-records?type=lead&q=test"
        )
        assert response.status_code in [401, 403]

    def test_search_leads_success(self, authenticated_client):
        """Search leads returns results with normalized 'name' field"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/chat/search-records?type=lead&q=test"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert isinstance(data["records"], list)
        
        # If results exist, verify name field is present
        if len(data["records"]) > 0:
            first_record = data["records"][0]
            assert "name" in first_record, "Lead records should have 'name' field"
            assert "id" in first_record

    def test_search_clients_success(self, authenticated_client):
        """Search clients returns results"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/chat/search-records?type=client&q=test"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert isinstance(data["records"], list)

    def test_search_cases_success(self, authenticated_client):
        """Search cases returns results"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/chat/search-records?type=case&q=credit"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert isinstance(data["records"], list)

    def test_search_companies_success(self, authenticated_client):
        """Search companies returns results"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/chat/search-records?type=company&q=corp"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert isinstance(data["records"], list)

    def test_search_invalid_type_returns_empty(self, authenticated_client):
        """Invalid record type returns empty results"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/chat/search-records?type=invalid_type&q=test"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["records"] == []

    def test_search_short_query_returns_empty(self, authenticated_client):
        """Query less than 2 chars returns empty results"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/chat/search-records?type=lead&q=t"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["records"] == []


# ==================== INTERNAL CHAT MESSAGE WITH ATTACHED RECORDS ====================

class TestChatMessageWithRecords:
    """Tests for sending chat messages with attached records"""

    def test_send_message_with_attached_records(self, authenticated_client):
        """Messages can include attached_records array"""
        # First create or get a channel
        channels_response = authenticated_client.get(
            f"{BASE_URL}/api/chat/channels"
        )
        assert channels_response.status_code == 200
        channels = channels_response.json()["channels"]
        
        if not channels:
            # Create a test channel
            create_response = authenticated_client.post(
                f"{BASE_URL}/api/chat/channels",
                json={
                    "name": "TEST_Widget_Channel",
                    "type": "group",
                    "description": "Test channel for widget testing"
                }
            )
            assert create_response.status_code == 200
            channel_id = create_response.json()["id"]
        else:
            channel_id = channels[0]["id"]
        
        # Send message with attached records
        message_response = authenticated_client.post(
            f"{BASE_URL}/api/chat/channels/{channel_id}/messages",
            json={
                "content": "TEST message with attached record",
                "attached_records": [
                    {"type": "lead", "id": "test-lead-123", "name": "Test Lead"}
                ]
            }
        )
        
        assert message_response.status_code == 200
        message_data = message_response.json()
        assert "attached_records" in message_data
        assert len(message_data["attached_records"]) == 1
        assert message_data["attached_records"][0]["type"] == "lead"


# ==================== CLEANUP ====================

class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_data(self, authenticated_client):
        """Clean up TEST_ prefixed data"""
        # Clean up test channels
        channels_response = authenticated_client.get(
            f"{BASE_URL}/api/chat/channels"
        )
        if channels_response.status_code == 200:
            channels = channels_response.json()["channels"]
            for channel in channels:
                if channel["name"].startswith("TEST_"):
                    # Note: No delete endpoint exposed, this is just for documentation
                    pass
        
        # Clean up test excluded pages
        pages_response = authenticated_client.get(
            f"{BASE_URL}/api/support-chat/widget/excluded-pages"
        )
        if pages_response.status_code == 200:
            pages = pages_response.json()["pages"]
            for page in pages:
                if page["page_path"].startswith("/TEST_"):
                    authenticated_client.delete(
                        f"{BASE_URL}/api/support-chat/widget/excluded-pages/{page['id']}"
                    )
        
        assert True  # Cleanup completed
