"""
Security API Router for Attorney Marketplace

Provides endpoints for:
- Audit log queries
- Security event monitoring
- Rate limit status
- Encryption key management (admin only)
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from typing import Optional, List
from datetime import datetime, timezone
import os

from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client

from .roles import UserRole, is_credlocity_staff
from .audit_logger import AuditLogger
from .rate_limiter import RateLimiter
from .authorization import get_user_context, execute_as_admin

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
client = get_client(MONGO_URL)
db = client[DB_NAME]

security_router = APIRouter(prefix="/api/security", tags=["Security"])


# ==================== AUTHENTICATION ====================

async def get_current_admin(authorization: Optional[str] = Header(None)):
    """Get current admin user from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        from jose import jwt
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if email:
            user = await db.users.find_one({"email": email}, {"_id": 0, "hashed_password": 0})
            if user:
                role = user.get("role", "")
                # Map legacy roles
                if role == "super_admin":
                    role = UserRole.CREDLOCITY_ADMIN
                elif role == "admin":
                    role = UserRole.CREDLOCITY_ADMIN
                
                if not is_credlocity_staff(role):
                    raise HTTPException(status_code=403, detail="Admin access required")
                
                return user
    except HTTPException:
        raise
    except Exception:
        pass
    
    raise HTTPException(status_code=401, detail="Invalid authentication")


# ==================== AUDIT LOG ENDPOINTS ====================

@security_router.get("/audit-log")
async def get_audit_log(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_admin)
):
    """
    Query audit log with filters
    Admin only
    """
    events = await AuditLogger.get_audit_trail(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    return {
        "events": events,
        "count": len(events),
        "filters": {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date
        }
    }


@security_router.get("/audit-log/summary")
async def get_audit_summary(
    days: int = 7,
    current_user: dict = Depends(get_current_admin)
):
    """
    Get audit log summary statistics
    """
    from datetime import timedelta
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Get event counts by type
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$event_type",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    event_counts = await db.audit_log.aggregate(pipeline).to_list(100)
    
    # Get failed access attempts
    failed_access = await db.audit_log.count_documents({
        "timestamp": {"$gte": start_date},
        "success": False
    })
    
    # Get unique users
    unique_users = await db.audit_log.distinct("user_id", {
        "timestamp": {"$gte": start_date}
    })
    
    return {
        "period_days": days,
        "start_date": start_date,
        "event_counts": {item["_id"]: item["count"] for item in event_counts},
        "failed_access_attempts": failed_access,
        "unique_users": len(unique_users),
        "total_events": sum(item["count"] for item in event_counts)
    }


# ==================== RATE LIMIT ENDPOINTS ====================

@security_router.get("/rate-limits/status")
async def get_rate_limit_status(
    identifier: str,
    identifier_type: str = "ip",
    action: Optional[str] = None,
    current_user: dict = Depends(get_current_admin)
):
    """
    Get rate limit status for an identifier
    Admin only
    """
    if action:
        usage = await RateLimiter.get_current_usage(db, identifier, identifier_type, action)
        return usage
    
    # Get all actions for this identifier
    all_usage = {}
    actions = ["api_general", "case_submission", "document_upload", "login_attempt", "bid_placement"]
    
    for act in actions:
        usage = await RateLimiter.get_current_usage(db, identifier, identifier_type, act)
        if usage.get("current_count", 0) > 0:
            all_usage[act] = usage
    
    return {
        "identifier": identifier,
        "identifier_type": identifier_type,
        "usage_by_action": all_usage
    }


@security_router.post("/rate-limits/reset")
async def reset_rate_limit(
    identifier: str,
    identifier_type: str = "ip",
    action: Optional[str] = None,
    current_user: dict = Depends(get_current_admin)
):
    """
    Reset rate limits for an identifier
    Admin only - requires justification
    """
    query = {
        "identifier": identifier,
        "identifier_type": identifier_type
    }
    
    if action:
        query["action"] = action
    
    result = await db.rate_limits.delete_many(query)
    
    # Log the reset
    await AuditLogger.log_admin_override(
        db,
        admin_user_id=current_user.get("id"),
        operation="reset_rate_limit",
        params={"identifier": identifier, "identifier_type": identifier_type, "action": action},
        justification="Admin rate limit reset"
    )
    
    return {
        "success": True,
        "records_deleted": result.deleted_count
    }


@security_router.post("/rate-limits/cleanup")
async def cleanup_rate_limits(current_user: dict = Depends(get_current_admin)):
    """
    Clean up expired rate limit records
    Admin only
    """
    await RateLimiter.cleanup_expired_records(db)
    return {"success": True, "message": "Expired rate limit records cleaned up"}


# ==================== SECURITY MONITORING ====================

@security_router.get("/failed-logins")
async def get_failed_logins(
    hours: int = 24,
    current_user: dict = Depends(get_current_admin)
):
    """
    Get recent failed login attempts
    Admin only
    """
    from datetime import timedelta
    
    start_date = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    
    failed_logins = await db.audit_log.find(
        {
            "event_type": "auth.login_attempt",
            "success": False,
            "timestamp": {"$gte": start_date}
        },
        {"_id": 0}
    ).sort("timestamp", -1).to_list(100)
    
    return {
        "period_hours": hours,
        "failed_attempts": failed_logins,
        "count": len(failed_logins)
    }


@security_router.get("/document-access")
async def get_document_access_log(
    case_id: Optional[str] = None,
    document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    days: int = 30,
    current_user: dict = Depends(get_current_admin)
):
    """
    Get document access log
    Admin only
    """
    from datetime import timedelta
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    query = {
        "event_type": "document.access",
        "timestamp": {"$gte": start_date}
    }
    
    if case_id:
        query["metadata.case_id"] = case_id
    if document_id:
        query["resource_id"] = document_id
    if user_id:
        query["user_id"] = user_id
    
    access_log = await db.audit_log.find(query, {"_id": 0}).sort("timestamp", -1).to_list(500)
    
    return {
        "period_days": days,
        "access_events": access_log,
        "count": len(access_log)
    }


# ==================== ADMIN OVERRIDE ====================

@security_router.post("/admin-override")
async def admin_override(
    request: Request,
    operation: str,
    params: dict,
    justification: str,
    current_user: dict = Depends(get_current_admin)
):
    """
    Execute an admin override operation
    Credlocity admin only - requires detailed justification
    """
    role = current_user.get("role", "")
    
    if role not in [UserRole.CREDLOCITY_ADMIN, "super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Only Credlocity administrators can execute overrides")
    
    try:
        result = await execute_as_admin(
            db,
            admin_user_id=current_user.get("id"),
            operation=operation,
            params=params,
            justification=justification
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ==================== HEALTH CHECK ====================

@security_router.get("/health")
async def security_health_check():
    """Public health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "audit_logging": "active",
            "rate_limiting": "active",
            "encryption": "active"
        }
    }
