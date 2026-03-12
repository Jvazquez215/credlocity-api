"""
Credlocity Customer Support Chat API
Features: Live chat with agents, AI chatbot settings, Knowledge base management
"""

from fastapi import APIRouter, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from typing import Optional, List, Dict
from datetime import datetime, timezone
from uuid import uuid4
import json

# Create router
support_chat_router = APIRouter(prefix="/api/support-chat")

# Database reference
db = None

def set_db(database):
    global db
    db = database


# WebSocket manager for customer support
class SupportConnectionManager:
    def __init__(self):
        # session_id -> WebSocket (visitors)
        self.visitor_connections: Dict[str, WebSocket] = {}
        # agent_id -> WebSocket (agents)
        self.agent_connections: Dict[str, WebSocket] = {}
        # session_id -> agent_id (active assignments)
        self.session_assignments: Dict[str, str] = {}
    
    async def connect_visitor(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.visitor_connections[session_id] = websocket
    
    async def connect_agent(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        self.agent_connections[agent_id] = websocket
    
    def disconnect_visitor(self, session_id: str):
        if session_id in self.visitor_connections:
            del self.visitor_connections[session_id]
        if session_id in self.session_assignments:
            del self.session_assignments[session_id]
    
    def disconnect_agent(self, agent_id: str):
        if agent_id in self.agent_connections:
            del self.agent_connections[agent_id]
    
    async def send_to_visitor(self, session_id: str, message: dict):
        if session_id in self.visitor_connections:
            try:
                await self.visitor_connections[session_id].send_json(message)
            except Exception:
                pass
    
    async def send_to_agent(self, agent_id: str, message: dict):
        if agent_id in self.agent_connections:
            try:
                await self.agent_connections[agent_id].send_json(message)
            except Exception:
                pass
    
    async def broadcast_to_agents(self, message: dict):
        for agent_id, ws in self.agent_connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                pass
    
    def assign_session(self, session_id: str, agent_id: str):
        self.session_assignments[session_id] = agent_id
    
    def get_assigned_agent(self, session_id: str) -> Optional[str]:
        return self.session_assignments.get(session_id)

support_manager = SupportConnectionManager()


# Auth helpers - uses JWT auth
from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        user = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user):
    if user.get("role") not in ["admin", "super_admin", "director", "support"]:
        raise HTTPException(status_code=403, detail="Admin access required")


# ==================== CHAT SESSIONS (Visitor Side) ====================

@support_chat_router.post("/sessions/start")
async def start_chat_session(data: dict):
    """Start a new support chat session (called by website visitor)"""
    visitor_name = data.get("name", "Visitor")
    visitor_email = data.get("email", "")
    page_url = data.get("page_url", "")
    
    session = {
        "id": str(uuid4()),
        "visitor_name": visitor_name,
        "visitor_email": visitor_email,
        "page_url": page_url,
        "status": "waiting",  # waiting, active, resolved, abandoned
        "assigned_agent_id": None,
        "assigned_agent_name": None,
        "department": data.get("department", "general"),
        "messages": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_activity": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "rating": None,
        "feedback": None,
        "tags": [],
        "notes": ""
    }
    
    await db.support_chat_sessions.insert_one(session)
    session.pop("_id", None)
    
    # Notify all agents about new chat
    await support_manager.broadcast_to_agents({
        "type": "new_session",
        "session": session
    })
    
    return session


@support_chat_router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get chat session details"""
    session = await db.support_chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@support_chat_router.post("/sessions/{session_id}/messages")
async def send_visitor_message(session_id: str, data: dict):
    """Send a message from the visitor"""
    session = await db.support_chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    message = {
        "id": str(uuid4()),
        "sender_type": "visitor",
        "sender_name": session.get("visitor_name", "Visitor"),
        "content": data.get("content", ""),
        "attachments": data.get("attachments", []),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.support_chat_sessions.update_one(
        {"id": session_id},
        {
            "$push": {"messages": message},
            "$set": {"last_activity": message["timestamp"]}
        }
    )
    
    # Send to assigned agent or broadcast to all
    assigned_agent = session.get("assigned_agent_id")
    if assigned_agent:
        await support_manager.send_to_agent(assigned_agent, {
            "type": "visitor_message",
            "session_id": session_id,
            "message": message
        })
    else:
        await support_manager.broadcast_to_agents({
            "type": "visitor_message",
            "session_id": session_id,
            "message": message
        })
    
    return message


@support_chat_router.post("/sessions/{session_id}/end")
async def end_session_visitor(session_id: str, data: dict = None):
    """End a chat session (visitor side)"""
    data = data or {}
    
    update = {
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat()
    }
    
    if data.get("rating"):
        update["rating"] = data["rating"]
    if data.get("feedback"):
        update["feedback"] = data["feedback"]
    
    await db.support_chat_sessions.update_one({"id": session_id}, {"$set": update})
    
    # Notify agent
    session = await db.support_chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if session and session.get("assigned_agent_id"):
        await support_manager.send_to_agent(session["assigned_agent_id"], {
            "type": "session_ended",
            "session_id": session_id
        })
    
    return {"message": "Session ended"}


# ==================== AGENT DASHBOARD ====================

@support_chat_router.get("/agent/sessions")
async def get_agent_sessions(
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get chat sessions for agent dashboard"""
    
    
    query = {}
    if status:
        if status == "mine":
            query["assigned_agent_id"] = user["id"]
        else:
            query["status"] = status
    
    sessions = await db.support_chat_sessions.find(
        query, {"_id": 0}
    ).sort("last_activity", -1).limit(100).to_list(length=100)
    
    # Get counts by status
    waiting_count = await db.support_chat_sessions.count_documents({"status": "waiting"})
    active_count = await db.support_chat_sessions.count_documents({"status": "active"})
    my_active = await db.support_chat_sessions.count_documents({
        "status": "active",
        "assigned_agent_id": user["id"]
    })
    
    return {
        "sessions": sessions,
        "counts": {
            "waiting": waiting_count,
            "active": active_count,
            "my_active": my_active
        }
    }


@support_chat_router.post("/agent/sessions/{session_id}/claim")
async def claim_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """Agent claims/joins a chat session"""
    
    
    session = await db.support_chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("assigned_agent_id") and session["assigned_agent_id"] != user["id"]:
        raise HTTPException(status_code=400, detail="Session already assigned to another agent")
    
    await db.support_chat_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "assigned_agent_id": user["id"],
            "assigned_agent_name": user.get("full_name", "Agent"),
            "status": "active",
            "last_activity": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    support_manager.assign_session(session_id, user["id"])
    
    # Notify visitor that agent has joined
    await support_manager.send_to_visitor(session_id, {
        "type": "agent_joined",
        "agent_name": user.get("full_name", "Agent")
    })
    
    # System message
    system_message = {
        "id": str(uuid4()),
        "sender_type": "system",
        "sender_name": "System",
        "content": f"{user.get('full_name', 'An agent')} has joined the chat.",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.support_chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": system_message}}
    )
    
    return {"message": "Session claimed", "session_id": session_id}


@support_chat_router.post("/agent/sessions/{session_id}/messages")
async def send_agent_message(
    session_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Send a message from the agent"""
    
    
    session = await db.support_chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    message = {
        "id": str(uuid4()),
        "sender_type": "agent",
        "sender_id": user["id"],
        "sender_name": user.get("full_name", "Agent"),
        "content": data.get("content", ""),
        "attachments": data.get("attachments", []),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.support_chat_sessions.update_one(
        {"id": session_id},
        {
            "$push": {"messages": message},
            "$set": {"last_activity": message["timestamp"]}
        }
    )
    
    # Send to visitor
    await support_manager.send_to_visitor(session_id, {
        "type": "agent_message",
        "message": message
    })
    
    return message


@support_chat_router.post("/agent/sessions/{session_id}/resolve")
async def resolve_session(
    session_id: str,
    data: dict = None,
    user: dict = Depends(get_current_user)
):
    """Agent resolves/closes a chat session"""
    
    data = data or {}
    
    update = {
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolved_by": user["id"]
    }
    
    if data.get("notes"):
        update["notes"] = data["notes"]
    if data.get("tags"):
        update["tags"] = data["tags"]
    
    await db.support_chat_sessions.update_one({"id": session_id}, {"$set": update})
    
    # Notify visitor
    await support_manager.send_to_visitor(session_id, {
        "type": "session_resolved",
        "message": data.get("resolution_message", "This chat has been resolved. Thank you for contacting us!")
    })
    
    return {"message": "Session resolved"}


@support_chat_router.post("/agent/sessions/{session_id}/transfer")
async def transfer_session(
    session_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Transfer session to another agent or department"""
    
    
    new_agent_id = data.get("agent_id")
    new_department = data.get("department")
    
    update = {
        "last_activity": datetime.now(timezone.utc).isoformat()
    }
    
    if new_agent_id:
        new_agent = await db.users.find_one({"id": new_agent_id}, {"_id": 0, "id": 1, "full_name": 1})
        if not new_agent:
            new_agent = await db.team_members.find_one({"id": new_agent_id}, {"_id": 0, "id": 1, "full_name": 1})
        
        if new_agent:
            update["assigned_agent_id"] = new_agent_id
            update["assigned_agent_name"] = new_agent.get("full_name", "Agent")
            support_manager.assign_session(session_id, new_agent_id)
    
    if new_department:
        update["department"] = new_department
        update["assigned_agent_id"] = None
        update["assigned_agent_name"] = None
        update["status"] = "waiting"
    
    await db.support_chat_sessions.update_one({"id": session_id}, {"$set": update})
    
    # Notify about transfer
    transfer_msg = {
        "id": str(uuid4()),
        "sender_type": "system",
        "sender_name": "System",
        "content": f"Chat transferred by {user.get('full_name', 'agent')}.",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.support_chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": transfer_msg}}
    )
    
    return {"message": "Session transferred"}


# ==================== CANNED RESPONSES ====================

@support_chat_router.get("/canned-responses")
async def get_canned_responses(user: dict = Depends(get_current_user)):
    """Get canned responses for quick replies"""
    responses = await db.canned_responses.find({}, {"_id": 0}).to_list(length=100)
    return {"responses": responses}


@support_chat_router.post("/canned-responses")
async def create_canned_response(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Create a new canned response"""
    
    require_admin(user)
    
    response = {
        "id": str(uuid4()),
        "title": data.get("title", ""),
        "content": data.get("content", ""),
        "category": data.get("category", "general"),
        "shortcut": data.get("shortcut", ""),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.canned_responses.insert_one(response)
    response.pop("_id", None)
    
    return response


@support_chat_router.delete("/canned-responses/{response_id}")
async def delete_canned_response(
    response_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete a canned response"""
    
    require_admin(user)
    
    await db.canned_responses.delete_one({"id": response_id})
    return {"message": "Deleted"}


# ==================== CHATBOT SETTINGS ====================

@support_chat_router.get("/chatbot/settings")
async def get_chatbot_settings(user: dict = Depends(get_current_user)):
    """Get chatbot configuration settings"""
    
    require_admin(user)
    
    settings = await db.chatbot_settings.find_one({"id": "main"}, {"_id": 0})
    
    if not settings:
        # Default settings
        settings = {
            "id": "main",
            "enabled": False,
            "model_provider": "openai",
            "model_name": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 500,
            "system_prompt": """You are a helpful customer support assistant for Credlocity, a credit repair company. 
Your role is to:
- Answer questions about credit repair services
- Explain how Credlocity can help improve credit scores
- Provide general information about credit bureaus and disputes
- Guide visitors to the right resources
- Collect contact information for follow-up if needed

Be professional, friendly, and helpful. If you don't know something, offer to connect them with a human agent.""",
            "greeting_message": "Hi! I'm the Credlocity assistant. How can I help you today?",
            "fallback_message": "I'm not sure I understand. Would you like me to connect you with a human agent?",
            "escalation_keywords": ["speak to human", "talk to agent", "real person", "supervisor"],
            "auto_escalate_after": 3,  # Number of failed responses before auto-escalation
            "working_hours": {
                "enabled": True,
                "timezone": "America/New_York",
                "schedule": {
                    "monday": {"start": "09:00", "end": "18:00"},
                    "tuesday": {"start": "09:00", "end": "18:00"},
                    "wednesday": {"start": "09:00", "end": "18:00"},
                    "thursday": {"start": "09:00", "end": "18:00"},
                    "friday": {"start": "09:00", "end": "17:00"},
                    "saturday": None,
                    "sunday": None
                }
            },
            "offline_message": "We're currently offline. Please leave your email and we'll get back to you!",
            "collect_email": True,
            "widget_appearance": {
                "primary_color": "#10B981",
                "position": "bottom-right",
                "title": "Credlocity Support",
                "subtitle": "We typically reply within minutes"
            },
            "knowledge_base_enabled": True,
            "knowledge_sources": [],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chatbot_settings.insert_one(settings)
        settings.pop("_id", None)
    
    return settings


@support_chat_router.put("/chatbot/settings")
async def update_chatbot_settings(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Update chatbot configuration settings"""
    
    require_admin(user)
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user["id"]
    
    await db.chatbot_settings.update_one(
        {"id": "main"},
        {"$set": data},
        upsert=True
    )
    
    return {"message": "Settings updated"}


# ==================== KNOWLEDGE BASE ====================

@support_chat_router.get("/knowledge-base")
async def get_knowledge_base(user: dict = Depends(get_current_user)):
    """Get knowledge base articles for chatbot training"""
    
    require_admin(user)
    
    articles = await db.knowledge_base.find({}, {"_id": 0}).sort("category", 1).to_list(length=500)
    
    # Get categories
    categories = await db.knowledge_base.distinct("category")
    
    return {"articles": articles, "categories": categories}


@support_chat_router.post("/knowledge-base")
async def create_knowledge_article(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Create a new knowledge base article"""
    
    require_admin(user)
    
    article = {
        "id": str(uuid4()),
        "title": data.get("title", ""),
        "content": data.get("content", ""),
        "category": data.get("category", "general"),
        "tags": data.get("tags", []),
        "questions": data.get("questions", []),  # Sample questions this article answers
        "is_active": data.get("is_active", True),
        "priority": data.get("priority", 0),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.knowledge_base.insert_one(article)
    article.pop("_id", None)
    
    return article


@support_chat_router.put("/knowledge-base/{article_id}")
async def update_knowledge_article(
    article_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Update a knowledge base article"""
    
    require_admin(user)
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user["id"]
    
    await db.knowledge_base.update_one({"id": article_id}, {"$set": data})
    
    return {"message": "Article updated"}


@support_chat_router.delete("/knowledge-base/{article_id}")
async def delete_knowledge_article(
    article_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete a knowledge base article"""
    
    require_admin(user)
    
    await db.knowledge_base.delete_one({"id": article_id})
    
    return {"message": "Article deleted"}


@support_chat_router.post("/knowledge-base/import")
async def import_from_content(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Import knowledge base articles from existing Credlocity content (FAQs, blog posts, etc.)"""
    
    require_admin(user)
    
    source = data.get("source", "faqs")  # faqs, blog, pages
    imported_count = 0
    
    if source == "faqs":
        faqs = await db.faqs.find({"is_published": True}, {"_id": 0}).to_list(length=None)
        for faq in faqs:
            article = {
                "id": str(uuid4()),
                "title": faq.get("question", ""),
                "content": faq.get("answer", ""),
                "category": faq.get("category", "FAQ"),
                "tags": ["faq", "imported"],
                "questions": [faq.get("question", "")],
                "is_active": True,
                "priority": faq.get("order", 0),
                "source": "faq",
                "source_id": faq.get("id"),
                "created_by": user["id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            await db.knowledge_base.insert_one(article)
            imported_count += 1
    
    elif source == "blog":
        posts = await db.blog_posts.find({"status": "published"}, {"_id": 0}).to_list(length=None)
        for post in posts:
            article = {
                "id": str(uuid4()),
                "title": post.get("title", ""),
                "content": post.get("content", "")[:5000],  # Limit content size
                "category": "Blog",
                "tags": post.get("tags", []) + ["blog", "imported"],
                "questions": [],
                "is_active": True,
                "priority": 0,
                "source": "blog",
                "source_id": post.get("id"),
                "created_by": user["id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            await db.knowledge_base.insert_one(article)
            imported_count += 1
    
    return {"message": f"Imported {imported_count} articles from {source}"}


# ==================== ANALYTICS ====================

@support_chat_router.get("/analytics")
async def get_chat_analytics(
    period: str = "week",
    user: dict = Depends(get_current_user)
):
    """Get chat support analytics"""
    
    require_admin(user)
    
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    
    if period == "day":
        start = now - timedelta(days=1)
    elif period == "week":
        start = now - timedelta(weeks=1)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(weeks=1)
    
    start_iso = start.isoformat()
    
    # Total sessions
    total_sessions = await db.support_chat_sessions.count_documents({
        "started_at": {"$gte": start_iso}
    })
    
    # Resolved sessions
    resolved_sessions = await db.support_chat_sessions.count_documents({
        "started_at": {"$gte": start_iso},
        "status": "resolved"
    })
    
    # Average rating
    sessions_with_rating = await db.support_chat_sessions.find(
        {"started_at": {"$gte": start_iso}, "rating": {"$exists": True, "$ne": None}},
        {"_id": 0, "rating": 1}
    ).to_list(length=None)
    
    avg_rating = 0
    if sessions_with_rating:
        avg_rating = sum(s["rating"] for s in sessions_with_rating) / len(sessions_with_rating)
    
    # Sessions by status
    by_status = {}
    for status in ["waiting", "active", "resolved", "abandoned"]:
        count = await db.support_chat_sessions.count_documents({
            "started_at": {"$gte": start_iso},
            "status": status
        })
        by_status[status] = count
    
    # Top agents
    pipeline = [
        {"$match": {"started_at": {"$gte": start_iso}, "assigned_agent_id": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$assigned_agent_id", "count": {"$sum": 1}, "agent_name": {"$first": "$assigned_agent_name"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    top_agents = await db.support_chat_sessions.aggregate(pipeline).to_list(length=10)
    
    return {
        "period": period,
        "total_sessions": total_sessions,
        "resolved_sessions": resolved_sessions,
        "resolution_rate": (resolved_sessions / total_sessions * 100) if total_sessions > 0 else 0,
        "average_rating": round(avg_rating, 2),
        "by_status": by_status,
        "top_agents": [{"agent_id": a["_id"], "agent_name": a.get("agent_name", "Unknown"), "sessions": a["count"]} for a in top_agents]
    }
