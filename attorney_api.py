"""
Credlocity Attorney Affiliate Network API
Handles attorney signup, portal, and case management
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4
import os
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

attorney_router = APIRouter(prefix="/api/attorneys", tags=["Attorney Network"])

# Database connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "app_db")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Attorney status options
ATTORNEY_STATUSES = ["pending", "approved", "active", "suspended", "inactive"]

# Case status options
CASE_STATUSES = ["pending_assignment", "assigned", "in_progress", "pending_review", "resolved", "closed"]


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from authorization header using JWT"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    
    # First, try to decode as JWT token (main CMS users)
    try:
        from jose import jwt, JWTError
        import os
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if email:
            # Check in users collection (main CMS admin users)
            user = await db.users.find_one({"email": email}, {"_id": 0, "hashed_password": 0})
            if user:
                # Map super_admin to admin for permission checks
                if user.get("role") == "super_admin":
                    user["role"] = "admin"
                return user
    except:
        pass
    
    # Fallback: Check for attorney portal token (database-stored token)
    attorney = await db.attorneys.find_one({"token": token}, {"_id": 0, "password_hash": 0})
    if attorney:
        return {**attorney, "is_attorney": True}
    
    return None


# ==================== PUBLIC ATTORNEY SIGNUP ====================

@attorney_router.post("/signup")
async def attorney_signup(data: dict):
    """Public endpoint for attorney affiliate signup"""
    # Validate required fields
    required = ["email", "full_name", "bar_number", "state", "firm_name"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
    
    # Check email uniqueness
    existing = await db.attorneys.find_one({"email": data["email"].lower()})
    if existing:
        raise HTTPException(status_code=400, detail="An attorney with this email already exists")
    
    # Check bar number uniqueness
    existing_bar = await db.attorneys.find_one({"bar_number": data["bar_number"], "state": data["state"]})
    if existing_bar:
        raise HTTPException(status_code=400, detail="An attorney with this bar number already exists")
    
    # Hash password if provided
    password_hash = None
    if data.get("password"):
        password_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    
    attorney = {
        "id": str(uuid4()),
        "email": data["email"].lower(),
        "full_name": data["full_name"],
        "password_hash": password_hash,
        "phone": data.get("phone"),
        "bar_number": data["bar_number"],
        "state": data["state"],
        "firm_name": data["firm_name"],
        "firm_address": data.get("firm_address"),
        "firm_city": data.get("firm_city"),
        "firm_state": data.get("firm_state"),
        "firm_zip": data.get("firm_zip"),
        "practice_areas": data.get("practice_areas", []),
        "years_experience": data.get("years_experience"),
        "website": data.get("website"),
        "bio": data.get("bio"),
        "status": "pending",  # Requires admin approval
        "commission_rate": 0.15,  # Default 15% commission
        "referral_code": f"ATT-{str(uuid4())[:8].upper()}",
        "cases_assigned": 0,
        "cases_resolved": 0,
        "total_earnings": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.attorneys.insert_one(attorney)
    
    # Remove sensitive data
    attorney.pop("password_hash", None)
    attorney.pop("_id", None)
    
    return {
        "message": "Application submitted successfully. You will be notified once approved.",
        "attorney_id": attorney["id"],
        "referral_code": attorney["referral_code"]
    }


@attorney_router.post("/public/apply")
async def attorney_public_apply(data: dict):
    """Public endpoint for detailed attorney application from landing page"""
    # Validate required fields
    required = ["first_name", "last_name", "firm_name", "email", "phone", "bar_number", "bar_state", 
                "has_insurance", "ever_suspended", "main_practice_area"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
    
    email = data["email"].lower()
    
    # Check email uniqueness
    existing = await db.attorneys.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="An attorney with this email already exists")
    
    # Check bar number uniqueness
    existing_bar = await db.attorneys.find_one({
        "bar_number": data["bar_number"], 
        "bar_state": data["bar_state"]
    })
    if existing_bar:
        raise HTTPException(status_code=400, detail="An attorney with this bar number already exists in this state")
    
    # Generate temporary password
    temp_password = str(uuid4())[:12]
    password_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()
    
    # Build practice areas list
    practice_areas = [data["main_practice_area"]]
    if data.get("additional_practice_areas"):
        practice_areas.extend(data["additional_practice_areas"])
    
    attorney = {
        "id": str(uuid4()),
        "email": email,
        "full_name": f"{data['first_name']} {data['last_name']}",
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "password_hash": password_hash,
        "temp_password": temp_password,  # Store temporarily for admin to share
        "phone": data["phone"],
        "bar_number": data["bar_number"],
        "bar_state": data["bar_state"],
        "state": data["bar_state"],  # Alias for compatibility
        "firm_name": data["firm_name"],
        "linkedin_handle": data.get("linkedin_handle"),
        "website": data.get("website"),
        "has_insurance": data.get("has_insurance") == "yes",
        "ever_suspended": data.get("ever_suspended") == "yes",
        "suspension_details": data.get("suspension_details") if data.get("ever_suspended") == "yes" else None,
        "main_practice_area": data["main_practice_area"],
        "practice_areas": practice_areas,
        "how_heard_about_us": data.get("how_heard_about_us"),
        "status": "pending",  # Requires admin approval
        "requires_agreement": True,  # Must sign agreement on first login
        "agreement_signed": False,
        "agreement_signed_at": None,
        "commission_rate": 0.15,  # Default 15% commission
        "referral_code": f"ATT-{str(uuid4())[:8].upper()}",
        "account_balance": 0,  # For bidding system
        "reserved_balance": 0,
        "cases_assigned": 0,
        "cases_resolved": 0,
        "total_earnings": 0,
        "marketplace_access": True,
        "marketplace_locked": False,
        "marketplace_lock_reason": None,
        "update_overdue_count": 0,
        "application_source": "landing_page",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.attorneys.insert_one(attorney)
    
    return {
        "message": "Application submitted successfully. We will review your application and contact you within 24-48 hours.",
        "attorney_id": attorney["id"]
    }


@attorney_router.post("/login")
async def attorney_login(data: dict):
    """Attorney portal login"""
    email = data.get("email", "").lower()
    password = data.get("password", "")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    attorney = await db.attorneys.find_one({"email": email})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not attorney.get("password_hash"):
        raise HTTPException(status_code=401, detail="Password not set. Please contact support.")
    
    if not bcrypt.checkpw(password.encode(), attorney["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if attorney["status"] not in ["approved", "active"]:
        raise HTTPException(status_code=403, detail=f"Account is {attorney['status']}. Please contact support.")
    
    # Generate token
    token = str(uuid4())
    await db.attorneys.update_one({"id": attorney["id"]}, {"$set": {"token": token, "last_login": datetime.now(timezone.utc).isoformat()}})
    
    return {
        "token": token,
        "attorney": {
            "id": attorney["id"],
            "email": attorney["email"],
            "full_name": attorney["full_name"],
            "firm_name": attorney["firm_name"],
            "status": attorney["status"],
            "referral_code": attorney["referral_code"]
        }
    }


# ==================== ATTORNEY PORTAL ====================

@attorney_router.get("/me")
async def get_attorney_profile(authorization: Optional[str] = Header(None)):
    """Get current attorney's profile"""
    user = await get_current_user(authorization)
    if not user or not user.get("is_attorney"):
        raise HTTPException(status_code=401, detail="Not authenticated as attorney")
    
    attorney = await db.attorneys.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0, "token": 0})
    return attorney


@attorney_router.get("/my-cases")
async def get_attorney_cases(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get cases assigned to current attorney"""
    user = await get_current_user(authorization)
    if not user or not user.get("is_attorney"):
        raise HTTPException(status_code=401, detail="Not authenticated as attorney")
    
    query = {"assigned_attorney_id": user["id"]}
    if status:
        query["status"] = status
    
    cases = await db.attorney_cases.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.attorney_cases.count_documents(query)
    
    return {"cases": cases, "total": total}


@attorney_router.put("/cases/{case_id}/status")
async def update_case_status(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update case status (attorney portal)"""
    user = await get_current_user(authorization)
    if not user or not user.get("is_attorney"):
        raise HTTPException(status_code=401, detail="Not authenticated as attorney")
    
    case = await db.attorney_cases.find_one({"id": case_id, "assigned_attorney_id": user["id"]})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    new_status = data.get("status")
    if new_status not in CASE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {CASE_STATUSES}")
    
    update = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if data.get("notes"):
        update["attorney_notes"] = data["notes"]
    
    await db.attorney_cases.update_one({"id": case_id}, {"$set": update})
    
    # Log status change
    log = {
        "id": str(uuid4()),
        "case_id": case_id,
        "action": "status_change",
        "old_status": case["status"],
        "new_status": new_status,
        "notes": data.get("notes"),
        "by_id": user["id"],
        "by_name": user["full_name"],
        "by_type": "attorney",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.attorney_case_logs.insert_one(log)
    
    updated = await db.attorney_cases.find_one({"id": case_id}, {"_id": 0})
    return updated


@attorney_router.get("/my-earnings")
async def get_attorney_earnings(authorization: Optional[str] = Header(None)):
    """Get attorney earnings summary"""
    user = await get_current_user(authorization)
    if not user or not user.get("is_attorney"):
        raise HTTPException(status_code=401, detail="Not authenticated as attorney")
    
    attorney = await db.attorneys.find_one({"id": user["id"]})
    
    # Get earnings by month
    pipeline = [
        {"$match": {"attorney_id": user["id"]}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 7]},
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 12}
    ]
    monthly = await db.attorney_earnings.aggregate(pipeline).to_list(None)
    
    return {
        "total_earnings": attorney.get("total_earnings", 0),
        "cases_resolved": attorney.get("cases_resolved", 0),
        "commission_rate": attorney.get("commission_rate", 0.15),
        "monthly_breakdown": monthly
    }


# ==================== ADMIN ATTORNEY MANAGEMENT ====================

@attorney_router.get("/admin/list")
async def admin_list_attorneys(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Admin: List all attorneys"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    query = {}
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"firm_name": {"$regex": search, "$options": "i"}},
            {"bar_number": {"$regex": search, "$options": "i"}}
        ]
    
    attorneys = await db.attorneys.find(query, {"_id": 0, "password_hash": 0, "token": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.attorneys.count_documents(query)
    
    return {"attorneys": attorneys, "total": total}


@attorney_router.get("/admin/stats")
async def get_attorney_network_stats(authorization: Optional[str] = Header(None)):
    """Admin: Get attorney network statistics"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    total_attorneys = await db.attorneys.count_documents({})
    active_attorneys = await db.attorneys.count_documents({"status": {"$in": ["approved", "active"]}})
    pending_attorneys = await db.attorneys.count_documents({"status": "pending"})
    
    total_cases = await db.attorney_cases.count_documents({})
    pending_cases = await db.attorney_cases.count_documents({"status": "pending_assignment"})
    in_progress_cases = await db.attorney_cases.count_documents({"status": {"$in": ["assigned", "in_progress"]}})
    resolved_cases = await db.attorney_cases.count_documents({"status": "resolved"})
    
    # Top attorneys by cases resolved
    pipeline = [
        {"$match": {"status": {"$in": ["approved", "active"]}}},
        {"$sort": {"cases_resolved": -1}},
        {"$limit": 5},
        {"$project": {"_id": 0, "id": 1, "full_name": 1, "firm_name": 1, "cases_resolved": 1, "total_earnings": 1}}
    ]
    top_attorneys = await db.attorneys.aggregate(pipeline).to_list(None)
    
    return {
        "attorneys": {
            "total": total_attorneys,
            "active": active_attorneys,
            "pending_approval": pending_attorneys
        },
        "cases": {
            "total": total_cases,
            "pending_assignment": pending_cases,
            "in_progress": in_progress_cases,
            "resolved": resolved_cases
        },
        "top_attorneys": top_attorneys
    }


# ==================== CASE MANAGEMENT ====================
# NOTE: These routes MUST be defined before /admin/{attorney_id} to prevent route conflicts

@attorney_router.post("/admin/cases")
async def create_case(data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Create a new case for attorney assignment"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    case = {
        "id": str(uuid4()),
        "case_number": f"CASE-{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:4].upper()}",
        "client_name": data["client_name"],
        "client_email": data.get("client_email"),
        "client_phone": data.get("client_phone"),
        "case_type": data.get("case_type", "collections"),
        "description": data.get("description"),
        "amount_at_stake": data.get("amount_at_stake", 0),
        "debtor_name": data.get("debtor_name"),
        "debtor_contact": data.get("debtor_contact"),
        "status": "pending_assignment",
        "priority": data.get("priority", "medium"),
        "assigned_attorney_id": data.get("assigned_attorney_id"),
        "assigned_attorney_name": None,
        "documents": data.get("documents", []),
        "notes": data.get("notes"),
        "created_by_id": user["id"],
        "created_by_name": user.get("full_name") or user.get("name"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # If attorney assigned, get their name
    if case["assigned_attorney_id"]:
        attorney = await db.attorneys.find_one({"id": case["assigned_attorney_id"]})
        if attorney:
            case["assigned_attorney_name"] = attorney["full_name"]
            case["status"] = "assigned"
            # Update attorney stats
            await db.attorneys.update_one({"id": attorney["id"]}, {"$inc": {"cases_assigned": 1}})
    
    await db.attorney_cases.insert_one(case)
    case.pop("_id", None)
    return case


@attorney_router.get("/admin/cases")
async def admin_list_cases(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    attorney_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Admin: List all cases"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    query = {}
    if status:
        query["status"] = status
    if attorney_id:
        query["assigned_attorney_id"] = attorney_id
    
    cases = await db.attorney_cases.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.attorney_cases.count_documents(query)
    
    return {"cases": cases, "total": total}


@attorney_router.put("/admin/cases/{case_id}/assign")
async def assign_case_to_attorney(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Assign case to attorney"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    case = await db.attorney_cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    attorney_id = data.get("attorney_id")
    attorney = await db.attorneys.find_one({"id": attorney_id})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney not found")
    
    if attorney["status"] not in ["approved", "active"]:
        raise HTTPException(status_code=400, detail="Attorney is not active")
    
    # Update case
    await db.attorney_cases.update_one({"id": case_id}, {"$set": {
        "assigned_attorney_id": attorney_id,
        "assigned_attorney_name": attorney["full_name"],
        "status": "assigned",
        "assigned_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }})
    
    # Update attorney stats
    await db.attorneys.update_one({"id": attorney_id}, {"$inc": {"cases_assigned": 1}})
    
    return {"message": "Case assigned successfully", "case_id": case_id, "attorney_id": attorney_id}


# ==================== ATTORNEY DETAIL ROUTES ====================

@attorney_router.get("/admin/{attorney_id}")
async def admin_get_attorney(attorney_id: str, authorization: Optional[str] = Header(None)):
    """Admin: Get attorney details"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    attorney = await db.attorneys.find_one({"id": attorney_id}, {"_id": 0, "password_hash": 0, "token": 0})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney not found")
    
    # Get their cases
    cases = await db.attorney_cases.find({"assigned_attorney_id": attorney_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(None)
    attorney["recent_cases"] = cases
    
    return attorney


@attorney_router.put("/admin/{attorney_id}/approve")
async def admin_approve_attorney(attorney_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Approve or reject attorney application"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    attorney = await db.attorneys.find_one({"id": attorney_id})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney not found")
    
    action = data.get("action")  # approve, reject
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    update = {
        "status": "approved" if action == "approve" else "inactive",
        "approved_by_id": user["id"],
        "approved_by_name": user.get("full_name") or user.get("name"),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approval_notes": data.get("notes"),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if action == "approve" and data.get("commission_rate"):
        update["commission_rate"] = data["commission_rate"]
    
    await db.attorneys.update_one({"id": attorney_id}, {"$set": update})
    
    return {"message": f"Attorney {action}d successfully", "attorney_id": attorney_id}


@attorney_router.put("/admin/{attorney_id}")
async def admin_update_attorney(attorney_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Update attorney details"""
    user = await get_current_user(authorization)
    if not user or user.get("role") not in ["admin", "director"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    attorney = await db.attorneys.find_one({"id": attorney_id})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney not found")
    
    update_fields = ["status", "commission_rate", "notes", "practice_areas"]
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    for field in update_fields:
        if field in data:
            update[field] = data[field]
    
    await db.attorneys.update_one({"id": attorney_id}, {"$set": update})
    
    updated = await db.attorneys.find_one({"id": attorney_id}, {"_id": 0, "password_hash": 0, "token": 0})
    return updated

# End of attorney_api.py
