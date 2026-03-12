"""
Employee Activity Tracking API
Tracks user sessions, activity events, and generates performance metrics
"""

from fastapi import APIRouter, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
import logging
import os

logger = logging.getLogger(__name__)

# Database connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
client = get_client(MONGO_URL)
db = client[DB_NAME]

router = APIRouter(prefix="/api/activity", tags=["Activity Tracking"])


# ==================== MODELS ====================

class ActivityEvent(BaseModel):
    """Individual activity event"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    session_id: str
    event_type: str  # page_view, click, form_submit, api_call, idle, active, logout
    event_data: Dict[str, Any] = {}
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    
class UserSession(BaseModel):
    """User session tracking"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    total_events: int = 0
    page_views: int = 0
    clicks: int = 0
    idle_time_seconds: int = 0
    active_time_seconds: int = 0


class DailyActivitySummary(BaseModel):
    """Daily summary of user activity"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    date: str  # YYYY-MM-DD
    total_sessions: int = 0
    total_time_seconds: int = 0
    active_time_seconds: int = 0
    idle_time_seconds: int = 0
    total_page_views: int = 0
    total_clicks: int = 0
    total_form_submissions: int = 0
    total_api_calls: int = 0
    pages_visited: List[str] = []
    first_login: Optional[str] = None
    last_logout: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActivityEventCreate(BaseModel):
    """Create activity event request"""
    session_id: str
    event_type: str
    event_data: Dict[str, Any] = {}
    page_url: Optional[str] = None
    page_title: Optional[str] = None


class SessionStartRequest(BaseModel):
    """Start session request"""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ActivityBatchRequest(BaseModel):
    """Batch of activity events"""
    session_id: str
    events: List[Dict[str, Any]]


# ==================== HELPER FUNCTIONS ====================

def remove_id(doc):
    """Remove _id field from MongoDB document"""
    if doc and '_id' in doc:
        doc.pop('_id')
    return doc


def remove_ids(docs):
    """Remove _id field from list of MongoDB documents"""
    return [remove_id(doc) for doc in docs if doc]


# ==================== API ENDPOINTS ====================

@router.post("/session/start")
async def start_session(request: Request, session_data: SessionStartRequest):
    """Start a new user session"""
    
    # Get user from token (simplified - in production use proper auth)
    user_id = request.headers.get("X-User-ID", "anonymous")
    user_email = request.headers.get("X-User-Email", "")
    user_name = request.headers.get("X-User-Name", "")
    user_role = request.headers.get("X-User-Role", "")
    
    session = UserSession(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        user_role=user_role,
        ip_address=session_data.ip_address or (request.client.host if request.client else None),
        user_agent=session_data.user_agent or request.headers.get("User-Agent", "")
    )
    
    await db.user_sessions.insert_one(session.model_dump())
    
    return {
        "session_id": session.id,
        "message": "Session started",
        "start_time": session.start_time.isoformat()
    }


@router.post("/session/{session_id}/end")
async def end_session(request: Request, session_id: str):
    """End a user session"""
    session = await db.user_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    end_time = datetime.now(timezone.utc)
    start_time = session.get("start_time", end_time)
    if isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except:
            start_time = end_time
    elif not isinstance(start_time, datetime):
        start_time = end_time
    
    # Ensure both datetimes have timezone info
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    
    # Calculate session duration
    duration_seconds = max(0, int((end_time - start_time).total_seconds()))
    
    await db.user_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "end_time": end_time,
            "is_active": False,
            "total_time_seconds": duration_seconds
        }}
    )
    
    # Update daily summary
    await update_daily_summary(db, session, end_time)
    
    return {"message": "Session ended", "duration_seconds": duration_seconds}


@router.post("/event")
async def log_activity_event(request: Request, event_data: ActivityEventCreate):
    """Log a single activity event"""
    user_id = request.headers.get("X-User-ID", "anonymous")
    user_email = request.headers.get("X-User-Email", "")
    user_name = request.headers.get("X-User-Name", "")
    
    event = ActivityEvent(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        session_id=event_data.session_id,
        event_type=event_data.event_type,
        event_data=event_data.event_data,
        page_url=event_data.page_url,
        page_title=event_data.page_title
    )
    
    await db.activity_events.insert_one(event.model_dump())
    
    # Update session stats
    inc_update = {"total_events": 1}
    if event_data.event_type == "page_view":
        inc_update["page_views"] = 1
    elif event_data.event_type == "click":
        inc_update["clicks"] = 1
    
    await db.user_sessions.update_one(
        {"id": event_data.session_id},
        {"$set": {"last_activity": event.timestamp}, "$inc": inc_update}
    )
    
    return {"event_id": event.id, "message": "Event logged"}


@router.post("/events/batch")
async def log_activity_batch(request: Request, batch: ActivityBatchRequest):
    """Log a batch of activity events (for efficiency)"""
    user_id = request.headers.get("X-User-ID", "anonymous")
    user_email = request.headers.get("X-User-Email", "")
    user_name = request.headers.get("X-User-Name", "")
    
    events_to_insert = []
    page_views = 0
    clicks = 0
    
    for event_data in batch.events:
        event = ActivityEvent(
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            session_id=batch.session_id,
            event_type=event_data.get("event_type", "unknown"),
            event_data=event_data.get("event_data", {}),
            page_url=event_data.get("page_url"),
            page_title=event_data.get("page_title"),
            timestamp=datetime.fromisoformat(event_data["timestamp"]) if "timestamp" in event_data else datetime.now(timezone.utc)
        )
        events_to_insert.append(event.model_dump())
        
        if event_data.get("event_type") == "page_view":
            page_views += 1
        elif event_data.get("event_type") == "click":
            clicks += 1
    
    if events_to_insert:
        await db.activity_events.insert_many(events_to_insert)
    
    # Update session stats
    await db.user_sessions.update_one(
        {"id": batch.session_id},
        {
            "$set": {"last_activity": datetime.now(timezone.utc)},
            "$inc": {
                "total_events": len(events_to_insert),
                "page_views": page_views,
                "clicks": clicks
            }
        }
    )
    
    return {"events_logged": len(events_to_insert), "message": "Batch logged"}


@router.post("/heartbeat/{session_id}")
async def session_heartbeat(request: Request, session_id: str, is_active: bool = True):
    """Update session heartbeat (sent periodically to track active/idle time)"""
    now = datetime.now(timezone.utc)
    
    session = await db.user_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    last_activity = session.get("last_activity", now)
    if isinstance(last_activity, str):
        last_activity = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
    
    time_since_last = int((now - last_activity).total_seconds())
    
    inc_field = "active_time_seconds" if is_active else "idle_time_seconds"
    
    await db.user_sessions.update_one(
        {"id": session_id},
        {
            "$set": {"last_activity": now},
            "$inc": {inc_field: min(time_since_last, 60)}
        }
    )
    
    return {"status": "ok", "timestamp": now.isoformat()}


async def update_daily_summary(db, session: dict, end_time: datetime):
    """Update or create daily activity summary"""
    user_id = session.get("user_id")
    date_str = end_time.strftime("%Y-%m-%d")
    
    existing = await db.daily_activity_summaries.find_one({
        "user_id": user_id,
        "date": date_str
    })
    
    start_time = session.get("start_time", end_time)
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    
    session_duration = int((end_time - start_time).total_seconds())
    
    if existing:
        await db.daily_activity_summaries.update_one(
            {"id": existing["id"]},
            {
                "$inc": {
                    "total_sessions": 1,
                    "total_time_seconds": session_duration,
                    "active_time_seconds": session.get("active_time_seconds", 0),
                    "idle_time_seconds": session.get("idle_time_seconds", 0),
                    "total_page_views": session.get("page_views", 0),
                    "total_clicks": session.get("clicks", 0),
                    "total_events": session.get("total_events", 0)
                },
                "$set": {
                    "last_logout": end_time.isoformat(),
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
    else:
        summary = DailyActivitySummary(
            user_id=user_id,
            user_email=session.get("user_email"),
            user_name=session.get("user_name"),
            user_role=session.get("user_role"),
            date=date_str,
            total_sessions=1,
            total_time_seconds=session_duration,
            active_time_seconds=session.get("active_time_seconds", 0),
            idle_time_seconds=session.get("idle_time_seconds", 0),
            total_page_views=session.get("page_views", 0),
            total_clicks=session.get("clicks", 0),
            first_login=start_time.isoformat(),
            last_logout=end_time.isoformat()
        )
        await db.daily_activity_summaries.insert_one(summary.model_dump())


# ==================== METRICS ENDPOINTS ====================

@router.get("/metrics/overview")
async def get_activity_overview(request: Request, days: int = 7):
    """Get activity overview for dashboard - includes both completed and active sessions"""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    
    # Get daily summaries (completed sessions)
    summaries = await db.daily_activity_summaries.find({
        "date": {"$gte": start_str}
    }).to_list(1000)
    summaries = remove_ids(summaries)
    
    # Get active sessions (current/ongoing)
    active_sessions_list = await db.user_sessions.find({
        "is_active": True
    }).to_list(1000)
    active_sessions_list = remove_ids(active_sessions_list)
    active_sessions = len(active_sessions_list)
    
    # Calculate totals from completed summaries
    total_time = sum(s.get("total_time_seconds", 0) for s in summaries)
    total_active_time = sum(s.get("active_time_seconds", 0) for s in summaries)
    total_page_views = sum(s.get("total_page_views", 0) for s in summaries)
    total_clicks = sum(s.get("total_clicks", 0) for s in summaries)
    total_sessions = sum(s.get("total_sessions", 0) for s in summaries)
    
    # Add active session stats (live data)
    for session in active_sessions_list:
        total_page_views += session.get("page_views", 0)
        total_clicks += session.get("clicks", 0)
        # Calculate current session time
        start_time = session.get("start_time")
        if start_time:
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except:
                    start_time = end_date
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            session_time = int((end_date - start_time).total_seconds())
            total_time += session_time
            total_active_time += session.get("active_time_seconds", 0)
    
    total_sessions += active_sessions  # Add active sessions to count
    
    # Get unique users
    unique_users = len(set(s.get("user_id") for s in summaries))
    unique_users += len(set(s.get("user_id") for s in active_sessions_list if s.get("user_id") not in [x.get("user_id") for x in summaries]))
    
    # Get today's stats
    today_str = end_date.strftime("%Y-%m-%d")
    today_summaries = [s for s in summaries if s.get("date") == today_str]
    today_active_users = len(today_summaries) + len(set(s.get("user_id") for s in active_sessions_list))
    today_time = sum(s.get("total_time_seconds", 0) for s in today_summaries)
    # Add active session time to today's time
    for session in active_sessions_list:
        start_time = session.get("start_time")
        if start_time:
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except:
                    continue
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if start_time.date() == end_date.date():
                today_time += int((end_date - start_time).total_seconds())
    
    return {
        "period_days": days,
        "active_sessions_now": active_sessions,
        "unique_users": unique_users,
        "total_sessions": total_sessions,
        "total_time_seconds": total_time,
        "total_time_hours": round(total_time / 3600, 1),
        "active_time_seconds": total_active_time,
        "active_time_hours": round(total_active_time / 3600, 1),
        "total_page_views": total_page_views,
        "total_clicks": total_clicks,
        "today": {
            "active_users": today_active_users,
            "total_time_seconds": today_time,
            "total_time_hours": round(today_time / 3600, 1)
        },
        "avg_session_minutes": round((total_time / max(total_sessions, 1)) / 60, 1),
        "avg_pages_per_session": round(total_page_views / max(total_sessions, 1), 1)
    }


@router.get("/metrics/users")
async def get_user_activity_metrics(request: Request, days: int = 7):
    """Get per-user activity metrics - includes active sessions"""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    
    # Aggregate completed sessions by user
    pipeline = [
        {"$match": {"date": {"$gte": start_str}}},
        {"$group": {
            "_id": "$user_id",
            "user_email": {"$first": "$user_email"},
            "user_name": {"$first": "$user_name"},
            "user_role": {"$first": "$user_role"},
            "total_sessions": {"$sum": "$total_sessions"},
            "total_time_seconds": {"$sum": "$total_time_seconds"},
            "active_time_seconds": {"$sum": "$active_time_seconds"},
            "total_page_views": {"$sum": "$total_page_views"},
            "total_clicks": {"$sum": "$total_clicks"},
            "days_active": {"$sum": 1}
        }},
        {"$sort": {"total_time_seconds": -1}}
    ]
    
    results = await db.daily_activity_summaries.aggregate(pipeline).to_list(100)
    
    # Create a map for easy lookup
    user_map = {}
    for r in results:
        user_map[r["_id"]] = {
            "user_id": r["_id"],
            "user_email": r.get("user_email", ""),
            "user_name": r.get("user_name", ""),
            "user_role": r.get("user_role", ""),
            "total_sessions": r.get("total_sessions", 0),
            "total_time_seconds": r.get("total_time_seconds", 0),
            "active_time_seconds": r.get("active_time_seconds", 0),
            "total_page_views": r.get("total_page_views", 0),
            "total_clicks": r.get("total_clicks", 0),
            "days_active": r.get("days_active", 0)
        }
    
    # Add active sessions data
    active_sessions = await db.user_sessions.find({"is_active": True}).to_list(1000)
    for session in active_sessions:
        user_id = session.get("user_id")
        if user_id not in user_map:
            user_map[user_id] = {
                "user_id": user_id,
                "user_email": session.get("user_email", ""),
                "user_name": session.get("user_name", ""),
                "user_role": session.get("user_role", ""),
                "total_sessions": 0,
                "total_time_seconds": 0,
                "active_time_seconds": 0,
                "total_page_views": 0,
                "total_clicks": 0,
                "days_active": 0
            }
        
        # Add current session stats
        user_map[user_id]["total_sessions"] += 1
        user_map[user_id]["total_page_views"] += session.get("page_views", 0)
        user_map[user_id]["total_clicks"] += session.get("clicks", 0)
        user_map[user_id]["active_time_seconds"] += session.get("active_time_seconds", 0)
        
        # Calculate current session time
        start_time = session.get("start_time")
        if start_time:
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except:
                    continue
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            session_time = int((end_date - start_time).total_seconds())
            user_map[user_id]["total_time_seconds"] += session_time
        
        # Mark as active today
        if user_map[user_id]["days_active"] == 0:
            user_map[user_id]["days_active"] = 1
    
    # Convert to list and calculate derived metrics
    users = []
    for user_data in user_map.values():
        total_time = user_data["total_time_seconds"]
        total_sessions = user_data["total_sessions"]
        users.append({
            "user_id": user_data["user_id"],
            "user_email": user_data["user_email"],
            "user_name": user_data["user_name"],
            "user_role": user_data["user_role"],
            "total_sessions": total_sessions,
            "total_time_hours": round(total_time / 3600, 1),
            "active_time_hours": round(user_data["active_time_seconds"] / 3600, 1),
            "total_page_views": user_data["total_page_views"],
            "total_clicks": user_data["total_clicks"],
            "days_active": user_data["days_active"],
            "avg_session_minutes": round((total_time / max(total_sessions, 1)) / 60, 1)
        })
    
    # Sort by total time
    users.sort(key=lambda x: x["total_time_hours"], reverse=True)
    
    return {"users": users, "period_days": days}


@router.get("/metrics/leaderboard")
async def get_activity_leaderboard(request: Request, metric: str = "time", days: int = 7, limit: int = 10):
    """Get activity leaderboard"""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    
    sort_field = {
        "time": "total_time_seconds",
        "page_views": "total_page_views",
        "clicks": "total_clicks",
        "sessions": "total_sessions"
    }.get(metric, "total_time_seconds")
    
    pipeline = [
        {"$match": {"date": {"$gte": start_str}}},
        {"$group": {
            "_id": "$user_id",
            "user_email": {"$first": "$user_email"},
            "user_name": {"$first": "$user_name"},
            "user_role": {"$first": "$user_role"},
            "total_sessions": {"$sum": "$total_sessions"},
            "total_time_seconds": {"$sum": "$total_time_seconds"},
            "total_page_views": {"$sum": "$total_page_views"},
            "total_clicks": {"$sum": "$total_clicks"}
        }},
        {"$sort": {sort_field: -1}},
        {"$limit": limit}
    ]
    
    results = await db.daily_activity_summaries.aggregate(pipeline).to_list(limit)
    
    leaderboard = []
    for i, r in enumerate(results):
        leaderboard.append({
            "rank": i + 1,
            "user_id": r["_id"],
            "user_name": r.get("user_name", "Unknown"),
            "user_role": r.get("user_role", ""),
            "total_time_hours": round(r.get("total_time_seconds", 0) / 3600, 1),
            "total_page_views": r.get("total_page_views", 0),
            "total_clicks": r.get("total_clicks", 0),
            "total_sessions": r.get("total_sessions", 0)
        })
    
    return {"leaderboard": leaderboard, "metric": metric, "period_days": days}


@router.get("/metrics/daily")
async def get_daily_activity(request: Request, days: int = 30):
    """Get daily activity trends"""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    
    pipeline = [
        {"$match": {"date": {"$gte": start_str}}},
        {"$group": {
            "_id": "$date",
            "unique_users": {"$sum": 1},
            "total_sessions": {"$sum": "$total_sessions"},
            "total_time_seconds": {"$sum": "$total_time_seconds"},
            "total_page_views": {"$sum": "$total_page_views"},
            "total_clicks": {"$sum": "$total_clicks"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db.daily_activity_summaries.aggregate(pipeline).to_list(days)
    
    daily_data = []
    for r in results:
        daily_data.append({
            "date": r["_id"],
            "unique_users": r.get("unique_users", 0),
            "total_sessions": r.get("total_sessions", 0),
            "total_time_hours": round(r.get("total_time_seconds", 0) / 3600, 1),
            "total_page_views": r.get("total_page_views", 0),
            "total_clicks": r.get("total_clicks", 0)
        })
    
    return {"daily_data": daily_data, "period_days": days}


@router.get("/user/{user_id}/activity")
async def get_user_activity(request: Request, user_id: str, days: int = 7):
    """Get detailed activity for a specific user"""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    
    # Get daily summaries
    summaries = await db.daily_activity_summaries.find({
        "user_id": user_id,
        "date": {"$gte": start_str}
    }).sort("date", -1).to_list(100)
    summaries = remove_ids(summaries)
    
    # Get recent sessions
    recent_sessions = await db.user_sessions.find({
        "user_id": user_id
    }).sort("start_time", -1).limit(10).to_list(10)
    recent_sessions = remove_ids(recent_sessions)
    
    # Calculate totals
    total_time = sum(s.get("total_time_seconds", 0) for s in summaries)
    total_sessions = sum(s.get("total_sessions", 0) for s in summaries)
    total_page_views = sum(s.get("total_page_views", 0) for s in summaries)
    
    return {
        "user_id": user_id,
        "period_days": days,
        "summary": {
            "total_time_hours": round(total_time / 3600, 1),
            "total_sessions": total_sessions,
            "total_page_views": total_page_views,
            "avg_session_minutes": round((total_time / max(total_sessions, 1)) / 60, 1)
        },
        "daily_activity": summaries,
        "recent_sessions": recent_sessions
    }
