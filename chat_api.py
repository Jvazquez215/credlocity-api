"""
Credlocity Internal Chat & Customer Support Chat API
Supports: WebSocket real-time messaging, DMs, Group Channels, Department Channels, File Sharing
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
import shutil
from pathlib import Path

# Create router
chat_router = APIRouter(prefix="/api/chat")

# Database reference (will be set from server.py)
db = None

def set_db(database):
    global db
    db = database

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        # user_id -> list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # channel_id -> list of user_ids subscribed
        self.channel_subscribers: Dict[str, List[str]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass
    
    async def send_to_channel(self, channel_id: str, message: dict, exclude_user: str = None):
        if channel_id in self.channel_subscribers:
            for user_id in self.channel_subscribers[channel_id]:
                if user_id != exclude_user:
                    await self.send_to_user(user_id, message)
    
    def subscribe_to_channel(self, channel_id: str, user_id: str):
        if channel_id not in self.channel_subscribers:
            self.channel_subscribers[channel_id] = []
        if user_id not in self.channel_subscribers[channel_id]:
            self.channel_subscribers[channel_id].append(user_id)
    
    def unsubscribe_from_channel(self, channel_id: str, user_id: str):
        if channel_id in self.channel_subscribers:
            if user_id in self.channel_subscribers[channel_id]:
                self.channel_subscribers[channel_id].remove(user_id)

manager = ConnectionManager()

# Auth helper - uses the same JWT auth as main server
from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Check regular users
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if user:
        return user
    
    # Check team members
    team_member = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if team_member:
        return team_member
    
    raise HTTPException(status_code=401, detail="User not found")


# ==================== CHANNELS ====================

@chat_router.get("/channels")
async def get_channels(
    channel_type: Optional[str] = None,
    user: dict = Depends(get_current_user_from_token)
):
    """Get all channels the user has access to"""
    
    user_id = user["id"]
    
    query = {
        "$or": [
            {"members": user_id},
            {"is_public": True},
            {"created_by": user_id}
        ]
    }
    
    if channel_type:
        query["type"] = channel_type
    
    channels = await db.chat_channels.find(query, {"_id": 0}).sort("updated_at", -1).to_list(length=100)
    
    # Add unread counts
    for channel in channels:
        unread = await db.chat_messages.count_documents({
            "channel_id": channel["id"],
            "read_by": {"$ne": user_id},
            "sender_id": {"$ne": user_id}
        })
        channel["unread_count"] = unread
    
    return {"channels": channels}


@chat_router.post("/channels")
async def create_channel(
    data: dict,
    user: dict = Depends(get_current_user_from_token)
):
    """Create a new channel (group, department, or DM)"""
    
    
    channel_type = data.get("type", "group")  # dm, group, department
    name = data.get("name", "")
    description = data.get("description", "")
    members = data.get("members", [])
    is_public = data.get("is_public", False)
    department = data.get("department")
    
    # For DMs, ensure exactly 2 members and check if DM already exists
    if channel_type == "dm":
        if len(members) != 1:
            raise HTTPException(status_code=400, detail="DM requires exactly one other member")
        
        other_user_id = members[0]
        members = [user["id"], other_user_id]
        
        # Check if DM already exists
        existing_dm = await db.chat_channels.find_one({
            "type": "dm",
            "members": {"$all": members, "$size": 2}
        }, {"_id": 0})
        
        if existing_dm:
            return existing_dm
        
        # Get other user's name for DM name
        other_user = await db.users.find_one({"id": other_user_id}, {"_id": 0, "full_name": 1})
        if not other_user:
            other_user = await db.team_members.find_one({"id": other_user_id}, {"_id": 0, "full_name": 1})
        name = other_user.get("full_name", "Direct Message") if other_user else "Direct Message"
    else:
        # Add creator to members if not already
        if user["id"] not in members:
            members.append(user["id"])
    
    channel = {
        "id": str(uuid4()),
        "type": channel_type,
        "name": name,
        "description": description,
        "members": members,
        "is_public": is_public,
        "department": department,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_message": None,
        "last_message_at": None
    }
    
    await db.chat_channels.insert_one(channel)
    channel.pop("_id", None)
    
    # Notify all members about new channel
    for member_id in members:
        await manager.send_to_user(member_id, {
            "type": "channel_created",
            "channel": channel
        })
    
    return channel


@chat_router.get("/channels/{channel_id}")
async def get_channel(
    channel_id: str,
    user: dict = Depends(get_current_user_from_token)
):
    """Get channel details"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Check access
    if not channel.get("is_public") and user["id"] not in channel.get("members", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get member details
    member_ids = channel.get("members", [])
    members = []
    for mid in member_ids:
        member = await db.users.find_one({"id": mid}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "photo_url": 1})
        if not member:
            member = await db.team_members.find_one({"id": mid}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "photo_url": 1})
        if member:
            members.append(member)
    
    channel["member_details"] = members
    
    return channel


@chat_router.patch("/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    data: dict,
    user: dict = Depends(get_current_user_from_token)
):
    """Update channel settings"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Only creator or admin can update
    if channel["created_by"] != user["id"] and user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Only channel creator can update")
    
    update_data = {}
    if "name" in data:
        update_data["name"] = data["name"]
    if "description" in data:
        update_data["description"] = data["description"]
    if "is_public" in data:
        update_data["is_public"] = data["is_public"]
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.chat_channels.update_one({"id": channel_id}, {"$set": update_data})
    
    return {"message": "Channel updated"}


@chat_router.post("/channels/{channel_id}/members")
async def add_channel_members(
    channel_id: str,
    data: dict,
    user: dict = Depends(get_current_user_from_token)
):
    """Add members to a channel"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if channel["type"] == "dm":
        raise HTTPException(status_code=400, detail="Cannot add members to DM")
    
    new_members = data.get("members", [])
    current_members = channel.get("members", [])
    
    for member_id in new_members:
        if member_id not in current_members:
            current_members.append(member_id)
            # Notify new member
            await manager.send_to_user(member_id, {
                "type": "added_to_channel",
                "channel": channel
            })
    
    await db.chat_channels.update_one(
        {"id": channel_id},
        {"$set": {"members": current_members, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Members added", "members": current_members}


@chat_router.delete("/channels/{channel_id}/members/{member_id}")
async def remove_channel_member(
    channel_id: str,
    member_id: str,
    user: dict = Depends(get_current_user_from_token)
):
    """Remove a member from a channel"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Only creator, admin, or self can remove
    if channel["created_by"] != user["id"] and user["id"] != member_id and user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    current_members = channel.get("members", [])
    if member_id in current_members:
        current_members.remove(member_id)
    
    await db.chat_channels.update_one(
        {"id": channel_id},
        {"$set": {"members": current_members, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Notify removed member
    await manager.send_to_user(member_id, {
        "type": "removed_from_channel",
        "channel_id": channel_id
    })
    
    return {"message": "Member removed"}


# ==================== MESSAGES ====================

@chat_router.get("/channels/{channel_id}/messages")
async def get_messages(
    channel_id: str,
    limit: int = 50,
    before: Optional[str] = None,
    user: dict = Depends(get_current_user_from_token)
):
    """Get messages from a channel"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Check access
    if not channel.get("is_public") and user["id"] not in channel.get("members", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = {"channel_id": channel_id}
    if before:
        query["created_at"] = {"$lt": before}
    
    messages = await db.chat_messages.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    messages.reverse()  # Oldest first
    
    # Enrich with sender info
    for msg in messages:
        sender = await db.users.find_one({"id": msg["sender_id"]}, {"_id": 0, "id": 1, "full_name": 1, "photo_url": 1})
        if not sender:
            sender = await db.team_members.find_one({"id": msg["sender_id"]}, {"_id": 0, "id": 1, "full_name": 1, "photo_url": 1})
        msg["sender"] = sender or {"id": msg["sender_id"], "full_name": "Unknown"}
    
    # Mark messages as read
    await db.chat_messages.update_many(
        {"channel_id": channel_id, "sender_id": {"$ne": user["id"]}},
        {"$addToSet": {"read_by": user["id"]}}
    )
    
    return {"messages": messages, "channel_id": channel_id}


@chat_router.post("/channels/{channel_id}/messages")
async def send_message(
    channel_id: str,
    data: dict,
    user: dict = Depends(get_current_user_from_token)
):
    """Send a message to a channel"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Check access
    if not channel.get("is_public") and user["id"] not in channel.get("members", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    content = data.get("content", "").strip()
    attachments = data.get("attachments", [])
    reply_to = data.get("reply_to")
    
    if not content and not attachments:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    message = {
        "id": str(uuid4()),
        "channel_id": channel_id,
        "sender_id": user["id"],
        "content": content,
        "attachments": attachments,
        "reply_to": reply_to,
        "read_by": [user["id"]],
        "reactions": [],
        "edited": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.chat_messages.insert_one(message)
    message.pop("_id", None)
    
    # Update channel last message
    await db.chat_channels.update_one(
        {"id": channel_id},
        {"$set": {
            "last_message": content[:100] if content else "[Attachment]",
            "last_message_at": message["created_at"],
            "updated_at": message["created_at"]
        }}
    )
    
    # Add sender info
    message["sender"] = {
        "id": user["id"],
        "full_name": user.get("full_name", "Unknown"),
        "photo_url": user.get("photo_url")
    }
    
    # Broadcast to channel members via WebSocket
    for member_id in channel.get("members", []):
        await manager.send_to_user(member_id, {
            "type": "new_message",
            "message": message
        })
    
    return message


@chat_router.patch("/messages/{message_id}")
async def edit_message(
    message_id: str,
    data: dict,
    user: dict = Depends(get_current_user_from_token)
):
    """Edit a message"""
    
    
    message = await db.chat_messages.find_one({"id": message_id}, {"_id": 0})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message["sender_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Can only edit your own messages")
    
    new_content = data.get("content", "").strip()
    if not new_content:
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    
    await db.chat_messages.update_one(
        {"id": message_id},
        {"$set": {
            "content": new_content,
            "edited": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Broadcast edit to channel
    channel = await db.chat_channels.find_one({"id": message["channel_id"]}, {"_id": 0})
    if channel:
        for member_id in channel.get("members", []):
            await manager.send_to_user(member_id, {
                "type": "message_edited",
                "message_id": message_id,
                "content": new_content,
                "channel_id": message["channel_id"]
            })
    
    return {"message": "Message edited"}


@chat_router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    user: dict = Depends(get_current_user_from_token)
):
    """Delete a message"""
    
    
    message = await db.chat_messages.find_one({"id": message_id}, {"_id": 0})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Only sender or admin can delete
    if message["sender_id"] != user["id"] and user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    await db.chat_messages.delete_one({"id": message_id})
    
    # Broadcast deletion to channel
    channel = await db.chat_channels.find_one({"id": message["channel_id"]}, {"_id": 0})
    if channel:
        for member_id in channel.get("members", []):
            await manager.send_to_user(member_id, {
                "type": "message_deleted",
                "message_id": message_id,
                "channel_id": message["channel_id"]
            })
    
    return {"message": "Message deleted"}


@chat_router.post("/messages/{message_id}/reactions")
async def add_reaction(
    message_id: str,
    data: dict,
    user: dict = Depends(get_current_user_from_token)
):
    """Add a reaction to a message"""
    
    
    emoji = data.get("emoji", "")
    if not emoji:
        raise HTTPException(status_code=400, detail="Emoji required")
    
    message = await db.chat_messages.find_one({"id": message_id}, {"_id": 0})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    reactions = message.get("reactions", [])
    
    # Check if user already reacted with this emoji
    existing = next((r for r in reactions if r["emoji"] == emoji), None)
    if existing:
        if user["id"] not in existing["users"]:
            existing["users"].append(user["id"])
    else:
        reactions.append({"emoji": emoji, "users": [user["id"]]})
    
    await db.chat_messages.update_one({"id": message_id}, {"$set": {"reactions": reactions}})
    
    return {"reactions": reactions}


# ==================== FILE UPLOAD ====================

UPLOAD_DIR = Path("/app/backend/uploads/chat")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@chat_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user_from_token)
):
    """Upload a file for chat"""
    
    
    # Validate file size (10MB max)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    
    # Generate unique filename
    ext = Path(file.filename).suffix
    file_id = str(uuid4())
    filename = f"{file_id}{ext}"
    filepath = UPLOAD_DIR / filename
    
    # Save file
    with open(filepath, "wb") as f:
        f.write(contents)
    
    # Determine file type
    content_type = file.content_type or "application/octet-stream"
    file_type = "file"
    if content_type.startswith("image/"):
        file_type = "image"
    elif content_type.startswith("video/"):
        file_type = "video"
    elif content_type.startswith("audio/"):
        file_type = "audio"
    
    attachment = {
        "id": file_id,
        "filename": file.filename,
        "url": f"/api/chat/files/{filename}",
        "type": file_type,
        "content_type": content_type,
        "size": len(contents),
        "uploaded_by": user["id"],
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    
    return attachment


@chat_router.get("/files/{filename}")
async def get_file(filename: str):
    """Get an uploaded file"""
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(filepath)


# ==================== DEPARTMENT CHANNELS ====================

DEPARTMENTS = [
    {"id": "collections", "name": "Collections", "icon": "briefcase"},
    {"id": "sales", "name": "Sales", "icon": "trending-up"},
    {"id": "support", "name": "Customer Support", "icon": "headphones"},
    {"id": "legal", "name": "Legal", "icon": "scale"},
    {"id": "operations", "name": "Operations", "icon": "settings"},
    {"id": "management", "name": "Management", "icon": "users"},
    {"id": "general", "name": "General", "icon": "message-circle"}
]

@chat_router.get("/departments")
async def get_departments(user: dict = Depends(get_current_user_from_token)):
    """Get list of departments for channel creation"""
    
    return {"departments": DEPARTMENTS}


@chat_router.get("/department-channels")
async def get_department_channels(user: dict = Depends(get_current_user_from_token)):
    """Get all department channels"""
    
    
    channels = await db.chat_channels.find(
        {"type": "department"},
        {"_id": 0}
    ).sort("department", 1).to_list(length=100)
    
    # Add unread counts
    for channel in channels:
        unread = await db.chat_messages.count_documents({
            "channel_id": channel["id"],
            "read_by": {"$ne": user["id"]},
            "sender_id": {"$ne": user["id"]}
        })
        channel["unread_count"] = unread
    
    return {"channels": channels}


# ==================== USER SEARCH ====================

@chat_router.get("/users/search")
async def search_users(
    q: str = "",
    user: dict = Depends(get_current_user_from_token)
):
    """Search for users to add to channels or start DMs"""
    
    
    if len(q) < 2:
        return {"users": []}
    
    # Search in users collection
    users = await db.users.find(
        {
            "$or": [
                {"full_name": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}}
            ],
            "id": {"$ne": user["id"]}
        },
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "photo_url": 1, "role": 1}
    ).limit(10).to_list(length=10)
    
    # Search in team_members collection
    team_members = await db.team_members.find(
        {
            "$or": [
                {"full_name": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}}
            ],
            "id": {"$ne": user["id"]}
        },
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "photo_url": 1, "role": 1, "department": 1}
    ).limit(10).to_list(length=10)
    
    all_users = users + team_members
    
    return {"users": all_users}


# ==================== ONLINE STATUS ====================

@chat_router.get("/online-users")
async def get_online_users(user: dict = Depends(get_current_user_from_token)):
    """Get list of currently online users"""
    
    
    online_user_ids = list(manager.active_connections.keys())
    
    # Get user details
    online_users = []
    for uid in online_user_ids:
        user = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1, "full_name": 1, "photo_url": 1})
        if not user:
            user = await db.team_members.find_one({"id": uid}, {"_id": 0, "id": 1, "full_name": 1, "photo_url": 1})
        if user:
            online_users.append(user)
    
    return {"online_users": online_users, "count": len(online_users)}


# ==================== TYPING INDICATOR ====================

@chat_router.post("/channels/{channel_id}/typing")
async def send_typing_indicator(
    channel_id: str,
    user: dict = Depends(get_current_user_from_token)
):
    """Send typing indicator to channel"""
    
    
    channel = await db.chat_channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Broadcast typing to other channel members
    for member_id in channel.get("members", []):
        if member_id != user["id"]:
            await manager.send_to_user(member_id, {
                "type": "typing",
                "channel_id": channel_id,
                "user_id": user["id"],
                "user_name": user.get("full_name", "Someone")
            })
    
    return {"status": "ok"}


# ==================== UNREAD COUNTS ====================

@chat_router.get("/unread")
async def get_unread_counts(user: dict = Depends(get_current_user_from_token)):
    """Get total unread message count for the user"""
    
    
    # Get all channels user is member of
    channels = await db.chat_channels.find(
        {"members": user["id"]},
        {"_id": 0, "id": 1}
    ).to_list(length=None)
    
    channel_ids = [c["id"] for c in channels]
    
    total_unread = await db.chat_messages.count_documents({
        "channel_id": {"$in": channel_ids},
        "read_by": {"$ne": user["id"]},
        "sender_id": {"$ne": user["id"]}
    })
    
    return {"total_unread": total_unread}
