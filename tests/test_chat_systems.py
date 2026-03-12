"""
Test suite for Credlocity Chat Systems:
1. Internal Employee Chat - DMs, Group Channels, Department Channels
2. Customer Support Chat - Live Agent Dashboard, Chatbot Settings, Knowledge Base
"""

import pytest
import requests
import os
from uuid import uuid4

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


# ==================== INTERNAL CHAT API TESTS ====================

class TestInternalChatChannels:
    """Tests for Internal Chat channel management"""
    
    def test_get_channels_success(self, admin_headers):
        """GET /api/chat/channels - should return channels list"""
        response = requests.get(f"{BASE_URL}/api/chat/channels", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "channels" in data
        assert isinstance(data["channels"], list)
        print(f"Found {len(data['channels'])} channels")
    
    def test_get_channels_unauthorized(self):
        """GET /api/chat/channels - should fail without auth"""
        response = requests.get(f"{BASE_URL}/api/chat/channels")
        assert response.status_code in [401, 403]
    
    def test_create_group_channel(self, admin_headers):
        """POST /api/chat/channels - create group channel"""
        channel_name = f"TEST_Group_{uuid4().hex[:8]}"
        response = requests.post(
            f"{BASE_URL}/api/chat/channels",
            headers=admin_headers,
            json={
                "type": "group",
                "name": channel_name,
                "description": "Test group channel",
                "members": [],
                "is_public": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == channel_name
        assert data["type"] == "group"
        assert "id" in data
        print(f"Created group channel: {data['id']}")
        return data["id"]
    
    def test_create_department_channel(self, admin_headers):
        """POST /api/chat/channels - create department channel"""
        channel_name = f"TEST_Dept_{uuid4().hex[:8]}"
        response = requests.post(
            f"{BASE_URL}/api/chat/channels",
            headers=admin_headers,
            json={
                "type": "department",
                "name": channel_name,
                "department": "sales",
                "members": []
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "department"
        print(f"Created department channel: {data['id']}")
    
    def test_get_departments(self, admin_headers):
        """GET /api/chat/departments - should return department list"""
        response = requests.get(f"{BASE_URL}/api/chat/departments", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "departments" in data
        assert len(data["departments"]) > 0
        print(f"Found {len(data['departments'])} departments")
    
    def test_search_users(self, admin_headers):
        """GET /api/chat/users/search - search for users"""
        response = requests.get(
            f"{BASE_URL}/api/chat/users/search?q=admin",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        print(f"Found {len(data['users'])} users matching 'admin'")


class TestInternalChatMessages:
    """Tests for Internal Chat messaging"""
    
    @pytest.fixture
    def test_channel(self, admin_headers):
        """Create a test channel for messaging tests"""
        response = requests.post(
            f"{BASE_URL}/api/chat/channels",
            headers=admin_headers,
            json={
                "type": "group",
                "name": f"TEST_MsgChannel_{uuid4().hex[:8]}",
                "is_public": True
            }
        )
        assert response.status_code == 200
        return response.json()["id"]
    
    def test_send_message(self, admin_headers, test_channel):
        """POST /api/chat/channels/{id}/messages - send message"""
        response = requests.post(
            f"{BASE_URL}/api/chat/channels/{test_channel}/messages",
            headers=admin_headers,
            json={"content": "Test message from pytest"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Test message from pytest"
        assert "id" in data
        print(f"Sent message: {data['id']}")
    
    def test_get_messages(self, admin_headers, test_channel):
        """GET /api/chat/channels/{id}/messages - get messages"""
        # First send a message
        requests.post(
            f"{BASE_URL}/api/chat/channels/{test_channel}/messages",
            headers=admin_headers,
            json={"content": "Test message for retrieval"}
        )
        
        # Then get messages
        response = requests.get(
            f"{BASE_URL}/api/chat/channels/{test_channel}/messages",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) > 0
        print(f"Retrieved {len(data['messages'])} messages")
    
    def test_get_unread_counts(self, admin_headers):
        """GET /api/chat/unread - get unread message counts"""
        response = requests.get(f"{BASE_URL}/api/chat/unread", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_unread" in data
        print(f"Total unread: {data['total_unread']}")


# ==================== CUSTOMER SUPPORT CHAT API TESTS ====================

class TestSupportChatSessions:
    """Tests for Customer Support Chat sessions"""
    
    def test_start_chat_session(self):
        """POST /api/support-chat/sessions/start - start visitor session"""
        response = requests.post(
            f"{BASE_URL}/api/support-chat/sessions/start",
            json={
                "name": "Test Visitor",
                "email": "test@example.com",
                "page_url": "https://credlocity.com/test"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["visitor_name"] == "Test Visitor"
        assert data["status"] == "waiting"
        assert "id" in data
        print(f"Started session: {data['id']}")
        return data["id"]
    
    def test_get_agent_sessions(self, admin_headers):
        """GET /api/support-chat/agent/sessions - get sessions for agent"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/agent/sessions",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "counts" in data
        assert "waiting" in data["counts"]
        assert "active" in data["counts"]
        print(f"Sessions - Waiting: {data['counts']['waiting']}, Active: {data['counts']['active']}")
    
    def test_get_agent_sessions_with_filter(self, admin_headers):
        """GET /api/support-chat/agent/sessions?status=waiting - filter by status"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/agent/sessions?status=waiting",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data


class TestChatbotSettings:
    """Tests for Chatbot Settings API"""
    
    def test_get_chatbot_settings(self, admin_headers):
        """GET /api/support-chat/chatbot/settings - get chatbot config"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/chatbot/settings",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "enabled" in data
        assert "model_provider" in data
        assert "model_name" in data
        assert "temperature" in data
        assert "max_tokens" in data
        assert "system_prompt" in data
        assert "greeting_message" in data
        assert "fallback_message" in data
        
        print(f"Chatbot enabled: {data['enabled']}, Model: {data['model_provider']}/{data['model_name']}")
    
    def test_update_chatbot_settings(self, admin_headers):
        """PUT /api/support-chat/chatbot/settings - update chatbot config"""
        response = requests.put(
            f"{BASE_URL}/api/support-chat/chatbot/settings",
            headers=admin_headers,
            json={
                "enabled": True,
                "model_provider": "openai",
                "model_name": "gpt-4o",
                "temperature": 0.7,
                "max_tokens": 500,
                "greeting_message": "Hi! How can I help you today?"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Settings updated"
        print("Chatbot settings updated successfully")
    
    def test_chatbot_settings_unauthorized(self):
        """GET /api/support-chat/chatbot/settings - should fail without auth"""
        response = requests.get(f"{BASE_URL}/api/support-chat/chatbot/settings")
        assert response.status_code in [401, 403]


class TestKnowledgeBase:
    """Tests for Knowledge Base API"""
    
    def test_get_knowledge_base(self, admin_headers):
        """GET /api/support-chat/knowledge-base - get articles"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/knowledge-base",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "articles" in data
        assert "categories" in data
        print(f"Found {len(data['articles'])} knowledge base articles")
    
    def test_create_knowledge_article(self, admin_headers):
        """POST /api/support-chat/knowledge-base - create article"""
        response = requests.post(
            f"{BASE_URL}/api/support-chat/knowledge-base",
            headers=admin_headers,
            json={
                "title": f"TEST_Article_{uuid4().hex[:8]}",
                "content": "This is a test knowledge base article for chatbot training.",
                "category": "FAQ",
                "tags": ["test", "pytest"],
                "questions": ["What is this test article about?"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["category"] == "FAQ"
        print(f"Created article: {data['id']}")
        return data["id"]
    
    def test_import_from_faqs(self, admin_headers):
        """POST /api/support-chat/knowledge-base/import - import from FAQs"""
        response = requests.post(
            f"{BASE_URL}/api/support-chat/knowledge-base/import",
            headers=admin_headers,
            json={"source": "faqs"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Import result: {data['message']}")
    
    def test_knowledge_base_unauthorized(self):
        """GET /api/support-chat/knowledge-base - should fail without auth"""
        response = requests.get(f"{BASE_URL}/api/support-chat/knowledge-base")
        assert response.status_code in [401, 403]


class TestSupportChatAnalytics:
    """Tests for Support Chat Analytics API"""
    
    def test_get_analytics_week(self, admin_headers):
        """GET /api/support-chat/analytics?period=week - get weekly analytics"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/analytics?period=week",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "total_sessions" in data
        assert "resolved_sessions" in data
        assert "resolution_rate" in data
        assert "average_rating" in data
        assert "by_status" in data
        
        print(f"Analytics - Total: {data['total_sessions']}, Resolved: {data['resolved_sessions']}, Rate: {data['resolution_rate']:.1f}%")
    
    def test_get_analytics_day(self, admin_headers):
        """GET /api/support-chat/analytics?period=day - get daily analytics"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/analytics?period=day",
            headers=admin_headers
        )
        assert response.status_code == 200
    
    def test_get_analytics_month(self, admin_headers):
        """GET /api/support-chat/analytics?period=month - get monthly analytics"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/analytics?period=month",
            headers=admin_headers
        )
        assert response.status_code == 200


class TestCannedResponses:
    """Tests for Canned Responses API"""
    
    def test_get_canned_responses(self, admin_headers):
        """GET /api/support-chat/canned-responses - get canned responses"""
        response = requests.get(
            f"{BASE_URL}/api/support-chat/canned-responses",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "responses" in data
        print(f"Found {len(data['responses'])} canned responses")
    
    def test_create_canned_response(self, admin_headers):
        """POST /api/support-chat/canned-responses - create canned response"""
        response = requests.post(
            f"{BASE_URL}/api/support-chat/canned-responses",
            headers=admin_headers,
            json={
                "title": f"TEST_Response_{uuid4().hex[:8]}",
                "content": "Thank you for contacting us. How can I help you today?",
                "category": "greeting",
                "shortcut": "/greet"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print(f"Created canned response: {data['id']}")


# ==================== CLEANUP ====================

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_channels(self, admin_headers):
        """Clean up TEST_ prefixed channels"""
        response = requests.get(f"{BASE_URL}/api/chat/channels", headers=admin_headers)
        if response.status_code == 200:
            channels = response.json().get("channels", [])
            test_channels = [c for c in channels if c.get("name", "").startswith("TEST_")]
            print(f"Found {len(test_channels)} test channels to clean up")
            # Note: Would need delete endpoint to clean up
