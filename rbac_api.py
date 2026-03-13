"""
Role-Based Access Control (RBAC) API
Manages permissions, groups, and user access assignments.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from datetime import datetime, timezone
from uuid import uuid4

rbac_router = APIRouter(prefix="/api/rbac", tags=["RBAC"])

db = None

def set_db(database):
    global db
    db = database

from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        user = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def get_any_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        user = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# All available permissions in the system
ALL_PERMISSIONS = {
    "dashboard": {"label": "Master Dashboard", "perms": ["dashboard.view"]},
    "collections": {"label": "Collections", "perms": ["collections.view", "collections.manage", "collections.settings"]},
    "payroll": {"label": "Payroll", "perms": ["payroll.view", "payroll.manage"]},
    "training": {"label": "Training & Policies", "perms": ["training.view", "training.manage"]},
    "marketing": {"label": "Marketing & Website", "perms": ["marketing.view", "marketing.manage"]},
    "reviews": {"label": "Reviews & Social Proof", "perms": ["reviews.view", "reviews.manage"]},
    "clients": {"label": "Clients", "perms": ["clients.view", "clients.manage"]},
    "outsourcing": {"label": "Outsourcing", "perms": ["outsourcing.view", "outsourcing.manage"]},
    "legal": {"label": "Legal & Attorney", "perms": ["legal.view", "legal.manage"]},
    "billing": {"label": "Billing & Finance", "perms": ["billing.view", "billing.manage"]},
    "partners": {"label": "Partners & Affiliates", "perms": ["partners.view", "partners.manage"]},
    "forms": {"label": "Form Builder", "perms": ["forms.view", "forms.manage"]},
    "team": {"label": "Team Management", "perms": ["team.view", "team.manage"]},
    "chat": {"label": "Chat & Support", "perms": ["chat.view", "chat.manage"]},
    "security": {"label": "Security", "perms": ["security.view", "security.manage"]},
    "settings": {"label": "Settings", "perms": ["settings.view", "settings.manage"]},
}

# Default groups with permissions
DEFAULT_GROUPS = [
    {
        "id": "group_super_admin",
        "name": "Super Admin",
        "description": "Full access to everything",
        "is_system": True,
        "permissions": [p for cat in ALL_PERMISSIONS.values() for p in cat["perms"]],
    },
    {
        "id": "group_admin",
        "name": "Admin",
        "description": "Full access to everything",
        "is_system": True,
        "permissions": [p for cat in ALL_PERMISSIONS.values() for p in cat["perms"]],
    },
    {
        "id": "group_collection_rep",
        "name": "Collection Rep",
        "description": "Access to collections, commission dashboard, training, and chat",
        "is_system": True,
        "permissions": [
            "dashboard.view", "collections.view", "collections.manage",
            "training.view", "chat.view", "chat.manage",
        ],
    },
    {
        "id": "group_collection_manager",
        "name": "Collection Manager",
        "description": "Collections management with team oversight and payroll view",
        "is_system": True,
        "permissions": [
            "dashboard.view", "collections.view", "collections.manage", "collections.settings",
            "payroll.view", "team.view", "training.view", "training.manage",
            "chat.view", "chat.manage",
        ],
    },
    {
        "id": "group_marketing",
        "name": "Marketing",
        "description": "Website content, blog, reviews, social proof, and media",
        "is_system": True,
        "permissions": [
            "dashboard.view", "marketing.view", "marketing.manage",
            "reviews.view", "reviews.manage",
        ],
    },
    {
        "id": "group_hr_payroll",
        "name": "HR & Payroll",
        "description": "Team management, payroll, training, and security",
        "is_system": True,
        "permissions": [
            "dashboard.view", "team.view", "team.manage",
            "payroll.view", "payroll.manage",
            "training.view", "training.manage",
            "security.view", "security.manage",
        ],
    },
    {
        "id": "group_legal",
        "name": "Legal",
        "description": "Attorney marketplace, cases, lawsuits",
        "is_system": True,
        "permissions": [
            "dashboard.view", "legal.view", "legal.manage",
            "clients.view",
        ],
    },
    {
        "id": "group_finance",
        "name": "Finance",
        "description": "Billing, commissions, and revenue overview",
        "is_system": True,
        "permissions": [
            "dashboard.view", "billing.view", "billing.manage",
            "payroll.view", "collections.view",
        ],
    },
    {
        "id": "group_partner",
        "name": "Partner",
        "description": "Company partner with full administrative access",
        "is_system": True,
        "permissions": [p for cat in ALL_PERMISSIONS.values() for p in cat["perms"]],
    },
]


async def seed_default_groups():
    """Seed default groups if they don't exist."""
    for group in DEFAULT_GROUPS:
        exists = await db.rbac_groups.find_one({"id": group["id"]})
        if not exists:
            await db.rbac_groups.insert_one({
                **group,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })


# ==================== PERMISSIONS ====================

@rbac_router.get("/permissions")
async def list_permissions(user: dict = Depends(get_any_user)):
    """List all available permissions in the system."""
    return {"permissions": ALL_PERMISSIONS}


# ==================== GROUPS ====================

@rbac_router.get("/groups")
async def list_groups(user: dict = Depends(get_any_user)):
    """List all permission groups."""
    groups = await db.rbac_groups.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    for g in groups:
        count = await db.rbac_user_assignments.count_documents({"group_id": g["id"]})
        g["member_count"] = count
    return {"groups": groups}


@rbac_router.get("/groups/{group_id}")
async def get_group(group_id: str, user: dict = Depends(get_any_user)):
    """Get a single group with its members."""
    group = await db.rbac_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    members = await db.rbac_user_assignments.find({"group_id": group_id}, {"_id": 0}).to_list(200)
    group["members"] = members
    return group


@rbac_router.post("/groups")
async def create_group(data: dict, user: dict = Depends(get_admin_user)):
    """Create a new permission group."""
    group = {
        "id": str(uuid4()),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "permissions": data.get("permissions", []),
        "is_system": False,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.rbac_groups.insert_one(group)
    group.pop("_id", None)
    return group


@rbac_router.put("/groups/{group_id}")
async def update_group(group_id: str, data: dict, user: dict = Depends(get_admin_user)):
    """Update a group's permissions or details."""
    group = await db.rbac_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "name" in data:
        update["name"] = data["name"]
    if "description" in data:
        update["description"] = data["description"]
    if "permissions" in data:
        update["permissions"] = data["permissions"]

    await db.rbac_groups.update_one({"id": group_id}, {"$set": update})
    return {"message": "Group updated"}


@rbac_router.delete("/groups/{group_id}")
async def delete_group(group_id: str, user: dict = Depends(get_admin_user)):
    """Delete a custom group (system groups can't be deleted)."""
    group = await db.rbac_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.get("is_system"):
        raise HTTPException(status_code=400, detail="Cannot delete system groups")
    await db.rbac_groups.delete_one({"id": group_id})
    await db.rbac_user_assignments.delete_many({"group_id": group_id})
    return {"message": "Group deleted"}


# ==================== USER ASSIGNMENTS ====================

@rbac_router.get("/users")
async def list_user_assignments(user: dict = Depends(get_admin_user)):
    """List all users with their group assignments and permission overrides."""
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    team = await db.team_members.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    all_users = users + team

    assignments = await db.rbac_user_assignments.find({}, {"_id": 0}).to_list(1000)
    assign_map = {}
    for a in assignments:
        assign_map[a["user_id"]] = a

    result = []
    for u in all_users:
        uid = u.get("id", "")
        assignment = assign_map.get(uid, {})
        result.append({
            "id": uid,
            "full_name": u.get("full_name", ""),
            "email": u.get("email", ""),
            "role": u.get("role", ""),
            "department": u.get("department", ""),
            "group_id": assignment.get("group_id"),
            "group_name": assignment.get("group_name"),
            "extra_permissions": assignment.get("extra_permissions", []),
            "revoked_permissions": assignment.get("revoked_permissions", []),
        })
    return {"users": sorted(result, key=lambda x: x.get("full_name", ""))}


@rbac_router.put("/users/{user_id}/assignment")
async def assign_user(user_id: str, data: dict, user: dict = Depends(get_admin_user)):
    """Assign a user to a group with optional permission overrides."""
    group_id = data.get("group_id")
    group_name = ""
    if group_id:
        group = await db.rbac_groups.find_one({"id": group_id}, {"_id": 0})
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        group_name = group.get("name", "")

    now = datetime.now(timezone.utc).isoformat()
    assignment = {
        "user_id": user_id,
        "group_id": group_id,
        "group_name": group_name,
        "extra_permissions": data.get("extra_permissions", []),
        "revoked_permissions": data.get("revoked_permissions", []),
        "assigned_by": user["id"],
        "updated_at": now,
    }

    await db.rbac_user_assignments.update_one(
        {"user_id": user_id},
        {"$set": assignment, "$setOnInsert": {"created_at": now}},
        upsert=True
    )
    return {"message": "User assignment updated", "assignment": assignment}


@rbac_router.delete("/users/{user_id}/assignment")
async def remove_user_assignment(user_id: str, user: dict = Depends(get_admin_user)):
    """Remove a user's group assignment."""
    await db.rbac_user_assignments.delete_one({"user_id": user_id})
    return {"message": "User assignment removed"}


# ==================== EFFECTIVE PERMISSIONS ====================

@rbac_router.get("/my-permissions")
async def get_my_permissions(user: dict = Depends(get_any_user)):
    """Get the effective permissions for the current user."""
    return await _get_effective_permissions(user)


async def _get_effective_permissions(user: dict):
    """Calculate effective permissions: group perms + extras - revoked."""
    uid = user.get("id", "")
    role = user.get("role", "")

    # Super admins, admins, and partners get everything
    if role in ["super_admin", "admin"]:
        all_perms = [p for cat in ALL_PERMISSIONS.values() for p in cat["perms"]]
        return {"permissions": all_perms, "group_name": role.replace("_", " ").title(), "is_admin": True}
    
    # Check if user is a partner
    user_doc = await db.users.find_one({"id": uid}, {"_id": 0, "is_partner": 1})
    if user_doc and user_doc.get("is_partner"):
        all_perms = [p for cat in ALL_PERMISSIONS.values() for p in cat["perms"]]
        return {"permissions": all_perms, "group_name": "Partner", "is_admin": True}

    assignment = await db.rbac_user_assignments.find_one({"user_id": uid}, {"_id": 0})
    if not assignment or not assignment.get("group_id"):
        return {"permissions": ["dashboard.view"], "group_name": "No Group", "is_admin": False}

    group = await db.rbac_groups.find_one({"id": assignment["group_id"]}, {"_id": 0})
    if not group:
        return {"permissions": ["dashboard.view"], "group_name": "No Group", "is_admin": False}

    base_perms = set(group.get("permissions", []))
    extras = set(assignment.get("extra_permissions", []))
    revoked = set(assignment.get("revoked_permissions", []))
    effective = list((base_perms | extras) - revoked)

    return {
        "permissions": sorted(effective),
        "group_id": group["id"],
        "group_name": group.get("name", ""),
        "is_admin": False,
    }
