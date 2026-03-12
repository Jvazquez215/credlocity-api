"""
Credlocity Unified Team & Partners Management API
Handles team members, roles, and permissions
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import os
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

team_router = APIRouter(prefix="/api/team", tags=["Team Management"])

# Database connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "app_db")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Role definitions with hierarchy
ROLE_HIERARCHY = {
    "admin": 100,
    "director": 90,
    "collections_manager": 80,
    "team_leader": 70,
    "collections_agent": 60,
    "contractor": 50,
    "affiliate": 40,
    "attorney": 30,
    "partner": 20,
    "viewer": 10
}

# Default permission templates
DEFAULT_PERMISSION_TEMPLATES = {
    "admin": {
        "name": "Administrator",
        "description": "Full system access",
        "permissions": {
            "users": ["create", "read", "update", "delete"],
            "team": ["create", "read", "update", "delete"],
            "collections": ["create", "read", "update", "delete", "archive", "approve"],
            "settlements": ["create", "read", "update", "delete", "approve_all"],
            "waivers": ["create", "read", "update", "delete", "approve_all"],
            "reports": ["read", "export"],
            "settings": ["read", "update"],
            "attorneys": ["create", "read", "update", "delete", "approve"],
            "revenue": ["read", "update"]
        }
    },
    "director": {
        "name": "Director",
        "description": "Department head access",
        "permissions": {
            "users": ["read", "update"],
            "team": ["create", "read", "update"],
            "collections": ["create", "read", "update", "delete", "archive", "approve"],
            "settlements": ["create", "read", "update", "approve_all"],
            "waivers": ["create", "read", "update", "approve_all"],
            "reports": ["read", "export"],
            "attorneys": ["read", "update", "approve"]
        }
    },
    "collections_manager": {
        "name": "Collections Manager",
        "description": "Manage collections team",
        "permissions": {
            "team": ["read", "update"],
            "collections": ["create", "read", "update", "archive", "approve"],
            "settlements": ["create", "read", "update", "approve_tier3"],
            "waivers": ["create", "read", "update", "approve_tier3"],
            "reports": ["read"]
        }
    },
    "team_leader": {
        "name": "Team Leader",
        "description": "Lead a collections team",
        "permissions": {
            "team": ["read"],
            "collections": ["create", "read", "update"],
            "settlements": ["create", "read", "update", "approve_tier2"],
            "waivers": ["create", "read", "update", "approve_tier2"],
            "reports": ["read"]
        }
    },
    "collections_agent": {
        "name": "Collections Agent",
        "description": "Standard collections representative",
        "permissions": {
            "collections": ["create", "read", "update"],
            "settlements": ["create", "read"],
            "waivers": ["create", "read"]
        }
    },
    "contractor": {
        "name": "Contractor",
        "description": "External contractor with limited access",
        "permissions": {
            "collections": ["read", "update"],
            "settlements": ["read"]
        }
    },
    "affiliate": {
        "name": "Affiliate Partner",
        "description": "Affiliate with referral access",
        "permissions": {
            "referrals": ["create", "read"],
            "commission": ["read"]
        }
    },
    "attorney": {
        "name": "Attorney Partner",
        "description": "Attorney affiliate network member",
        "permissions": {
            "cases": ["read", "update"],
            "clients": ["read"],
            "commission": ["read"]
        }
    }
}


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from authorization header using JWT"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    
    # Decode JWT token
    try:
        from jose import jwt, JWTError
        import os
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if not email:
            return None
    except JWTError:
        return None
    
    # Check in users collection (main CMS users)
    user = await db.users.find_one({"email": email}, {"_id": 0, "hashed_password": 0})
    if user:
        # Map super_admin to admin for permission checks
        if user.get("role") == "super_admin":
            user["role"] = "admin"
        return user
    
    # Check in team_members collection
    member = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if member:
        return member
    
    return None


def check_permission(user: dict, resource: str, action: str) -> bool:
    """Check if user has permission for resource/action"""
    if not user:
        return False
    
    role = user.get("role", "viewer")
    
    # Admins have all permissions
    if role == "admin":
        return True
    
    # Get permissions from user or template
    permissions = user.get("permissions") or DEFAULT_PERMISSION_TEMPLATES.get(role, {}).get("permissions", {})
    
    resource_perms = permissions.get(resource, [])
    return action in resource_perms


# ==================== TEAM MEMBERS CRUD ====================

@team_router.post("/members")
async def create_team_member(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new team member"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_permission(user, "team", "create"):
        raise HTTPException(status_code=403, detail="Not authorized to create team members")
    
    # Validate required fields
    if not data.get("email") or not data.get("full_name"):
        raise HTTPException(status_code=400, detail="Email and full name are required")
    
    # Check email uniqueness
    existing = await db.team_members.find_one({"email": data["email"].lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Hash password if provided
    password_hash = None
    if data.get("password"):
        password_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    
    role = data.get("role", "collections_agent")
    
    member = {
        "id": str(uuid4()),
        "email": data["email"].lower(),
        "full_name": data["full_name"],
        "password_hash": password_hash,
        "phone": data.get("phone"),
        "role": role,
        "role_name": DEFAULT_PERMISSION_TEMPLATES.get(role, {}).get("name", role),
        "member_type": data.get("member_type", "employee"),  # employee, contractor, affiliate, attorney
        "department": data.get("department", "collections"),
        "team_id": data.get("team_id"),
        "reports_to": data.get("reports_to"),
        "permissions": data.get("permissions") or DEFAULT_PERMISSION_TEMPLATES.get(role, {}).get("permissions", {}),
        "status": "active",
        "hire_date": data.get("hire_date"),
        "hourly_rate": data.get("hourly_rate"),
        "commission_rate": data.get("commission_rate"),
        "notes": data.get("notes"),
        "created_by_id": user["id"],
        "created_by_name": user.get("full_name") or user.get("name"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.team_members.insert_one(member)
    
    # Remove sensitive data before returning
    member.pop("password_hash", None)
    member.pop("_id", None)
    return member


@team_router.get("/members")
async def list_team_members(
    authorization: Optional[str] = Header(None),
    role: Optional[str] = None,
    member_type: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = "active",
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """List all team members with filters"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_permission(user, "team", "read"):
        raise HTTPException(status_code=403, detail="Not authorized to view team members")
    
    query = {}
    if role:
        query["role"] = role
    if member_type:
        query["member_type"] = member_type
    if department:
        query["department"] = department
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    
    members = await db.team_members.find(query, {"_id": 0, "password_hash": 0}).sort("full_name", 1).skip(skip).limit(limit).to_list(None)
    total = await db.team_members.count_documents(query)
    
    return {"members": members, "total": total, "skip": skip, "limit": limit}


@team_router.get("/members/{member_id}")
async def get_team_member(member_id: str, authorization: Optional[str] = Header(None)):
    """Get a specific team member"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_permission(user, "team", "read"):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    member = await db.team_members.find_one({"id": member_id}, {"_id": 0, "password_hash": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    return member


@team_router.put("/members/{member_id}")
async def update_team_member(member_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update a team member"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_permission(user, "team", "update"):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    existing = await db.team_members.find_one({"id": member_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Fields that can be updated
    update_fields = ["full_name", "phone", "role", "member_type", "department", 
                    "team_id", "reports_to", "permissions", "status", "hourly_rate",
                    "commission_rate", "notes"]
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in update_fields:
        if field in data:
            update_data[field] = data[field]
    
    # Update role name if role changed
    if "role" in data:
        update_data["role_name"] = DEFAULT_PERMISSION_TEMPLATES.get(data["role"], {}).get("name", data["role"])
        # Update permissions if not custom
        if "permissions" not in data:
            update_data["permissions"] = DEFAULT_PERMISSION_TEMPLATES.get(data["role"], {}).get("permissions", {})
    
    await db.team_members.update_one({"id": member_id}, {"$set": update_data})
    
    updated = await db.team_members.find_one({"id": member_id}, {"_id": 0, "password_hash": 0})
    return updated


@team_router.delete("/members/{member_id}")
async def delete_team_member(member_id: str, authorization: Optional[str] = Header(None)):
    """Delete a team member"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_permission(user, "team", "delete"):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    existing = await db.team_members.find_one({"id": member_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    await db.team_members.delete_one({"id": member_id})
    return {"message": "Team member deleted", "id": member_id}


# ==================== PERMISSION TEMPLATES ====================

@team_router.get("/permission-templates")
async def get_permission_templates(authorization: Optional[str] = Header(None)):
    """Get all permission templates"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Get custom templates from database
    custom_templates = await db.permission_templates.find({}, {"_id": 0}).to_list(None)
    
    # Merge with defaults
    templates = {**DEFAULT_PERMISSION_TEMPLATES}
    for template in custom_templates:
        templates[template["id"]] = template
    
    return {"templates": templates, "roles": list(ROLE_HIERARCHY.keys())}


@team_router.post("/permission-templates")
async def create_permission_template(data: dict, authorization: Optional[str] = Header(None)):
    """Create a custom permission template"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if user.get("role") not in ["admin", "director"]:
        raise HTTPException(status_code=403, detail="Only admins can create permission templates")
    
    template = {
        "id": data.get("id") or str(uuid4()),
        "name": data["name"],
        "description": data.get("description", ""),
        "permissions": data["permissions"],
        "is_custom": True,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.permission_templates.insert_one(template)
    template.pop("_id", None)
    return template


# ==================== TEAM STATS ====================

@team_router.get("/stats")
async def get_team_stats(authorization: Optional[str] = Header(None)):
    """Get team statistics"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    total_members = await db.team_members.count_documents({"status": "active"})
    
    # Count by role
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$role", "count": {"$sum": 1}}}
    ]
    by_role = await db.team_members.aggregate(pipeline).to_list(None)
    
    # Count by type
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$member_type", "count": {"$sum": 1}}}
    ]
    by_type = await db.team_members.aggregate(pipeline).to_list(None)
    
    # Count by department
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ]
    by_department = await db.team_members.aggregate(pipeline).to_list(None)
    
    return {
        "total_members": total_members,
        "by_role": {item["_id"]: item["count"] for item in by_role if item["_id"]},
        "by_type": {item["_id"]: item["count"] for item in by_type if item["_id"]},
        "by_department": {item["_id"]: item["count"] for item in by_department if item["_id"]}
    }
