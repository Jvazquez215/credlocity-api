"""
Credlocity Case Update System API
Handles 30-day case update requirements, notifications, and attorney penalties
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from typing import Optional, List
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
import os
from auth import decode_token

# Get database connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = get_client(mongo_url)
db = client[os.environ.get('DB_NAME', 'credlocity')]

case_update_router = APIRouter()
security = HTTPBearer()


async def get_current_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user


# ============= MODELS =============

class CaseUpdateStatusOption(BaseModel):
    id: str
    name: str
    description: str
    is_active: bool = True
    display_order: int = 0
    created_at: str
    updated_at: str


class CaseUpdate(BaseModel):
    id: str
    case_id: str
    attorney_id: str
    status: str  # e.g., "under_review", "in_negotiations", "litigation_filed"
    notes: str
    created_at: str


class CaseUpdateSubmit(BaseModel):
    status: str
    notes: str


class PenaltyRequest(BaseModel):
    attorney_id: str
    reason: str
    case_ids: List[str]


# ============= CASE UPDATE STATUS OPTIONS (ADMIN) =============

@case_update_router.get("/status-options")
async def get_case_update_status_options():
    """Get all available case update status options"""
    options = await db.case_update_status_options.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(100)
    return options


@case_update_router.post("/status-options")
async def create_case_update_status_option(data: dict, user: dict = Depends(get_current_user_from_token)):
    """Admin: Create a new case update status option"""
    if not user or user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    option = {
        "id": str(uuid4()),
        "name": data["name"],
        "description": data.get("description", ""),
        "is_active": data.get("is_active", True),
        "display_order": data.get("display_order", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_update_status_options.insert_one(option)
    return {"message": "Status option created", "option": option}


@case_update_router.put("/status-options/{option_id}")
async def update_case_update_status_option(option_id: str, data: dict, user: dict = Depends(get_current_user_from_token)):
    """Admin: Update a case update status option"""
    if not user or user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    update_data = {
        "name": data.get("name"),
        "description": data.get("description"),
        "is_active": data.get("is_active"),
        "display_order": data.get("display_order"),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    update_data = {k: v for k, v in update_data.items() if v is not None}
    
    result = await db.case_update_status_options.update_one(
        {"id": option_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Status option not found")
    
    return {"message": "Status option updated"}


@case_update_router.delete("/status-options/{option_id}")
async def delete_case_update_status_option(option_id: str, user: dict = Depends(get_current_user_from_token)):
    """Admin: Delete a case update status option"""
    if not user or user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Soft delete by setting is_active to False
    result = await db.case_update_status_options.update_one(
        {"id": option_id},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Status option not found")
    
    return {"message": "Status option deleted"}


# ============= ATTORNEY CASE UPDATES =============

@case_update_router.get("/attorney/cases-needing-update")
async def get_attorney_cases_needing_update(token: str):
    """Get all cases that need updates for the logged-in attorney"""
    # Verify attorney token
    attorney = await db.attorneys.find_one({"token": token, "status": "approved"}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    attorney_id = attorney["id"]
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    
    # Get all pledged cases for this attorney (check both field patterns)
    cases = await db.marketplace_cases.find({
        "$or": [
            {"assignment.pledged_to_attorney_id": attorney_id},
            {"assigned_attorney_id": attorney_id}
        ],
        "status": {"$in": ["pledged", "in_progress"]}
    }, {"_id": 0}).to_list(100)
    
    cases_needing_update = []
    
    for case in cases:
        # Get the most recent update for this case
        last_update = await db.case_updates.find_one(
            {"case_id": case["case_id"], "attorney_id": attorney_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        
        # Determine if update is needed (no update in 30 days)
        last_update_date = None
        if last_update:
            last_update_date = datetime.fromisoformat(last_update["created_at"].replace("Z", "+00:00"))
        else:
            # If no update ever, use pledge date
            last_update_date = datetime.fromisoformat(case.get("pledged_at", case["created_at"]).replace("Z", "+00:00"))
        
        days_since_update = (now - last_update_date).days
        
        if days_since_update >= 30:
            # Calculate days overdue
            days_overdue = days_since_update - 30
            case["days_since_update"] = days_since_update
            case["days_overdue"] = days_overdue
            case["last_update_date"] = last_update_date.isoformat()
            case["needs_update"] = True
            case["is_urgent"] = days_overdue >= 3  # 3+ days overdue triggers penalty risk
            cases_needing_update.append(case)
    
    # Check if attorney is penalized
    is_penalized = attorney.get("marketplace_locked", False)
    penalty_info = None
    if is_penalized:
        penalty_info = {
            "locked": True,
            "reason": attorney.get("marketplace_lock_reason"),
            "locked_at": attorney.get("marketplace_locked_at"),
            "held_balance": attorney.get("held_balance", 0),
            "case_ids": attorney.get("penalty_case_ids", [])
        }
    
    return {
        "cases_needing_update": cases_needing_update,
        "total_overdue": len(cases_needing_update),
        "urgent_count": len([c for c in cases_needing_update if c.get("is_urgent")]),
        "penalty_status": penalty_info
    }


@case_update_router.post("/attorney/cases/{case_id}/update")
async def submit_case_update(case_id: str, update_data: CaseUpdateSubmit, token: str):
    """Attorney submits a case update"""
    # Verify attorney token
    attorney = await db.attorneys.find_one({"token": token, "status": "approved"}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    # Check if attorney is locked from marketplace
    if attorney.get("marketplace_locked"):
        raise HTTPException(status_code=403, detail="Your marketplace access is locked. Please contact support.")
    
    attorney_id = attorney["id"]
    
    # Verify case belongs to this attorney (check both field patterns)
    case = await db.marketplace_cases.find_one({
        "case_id": case_id,
        "$or": [
            {"assignment.pledged_to_attorney_id": attorney_id},
            {"assigned_attorney_id": attorney_id}
        ]
    })
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    # Create the update record
    case_update = {
        "id": str(uuid4()),
        "case_id": case_id,
        "attorney_id": attorney_id,
        "status": update_data.status,
        "notes": update_data.notes,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_updates.insert_one(case_update)
    
    # Update case's last_update field
    await db.marketplace_cases.update_one(
        {"case_id": case_id},
        {
            "$set": {
                "last_update_at": datetime.now(timezone.utc).isoformat(),
                "last_update_status": update_data.status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Reset overdue count if this was a required update
    await db.attorneys.update_one(
        {"id": attorney_id},
        {
            "$set": {
                "update_overdue_count": 0,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"message": "Case update submitted successfully", "update_id": case_update["id"]}


@case_update_router.get("/attorney/cases/{case_id}/history")
async def get_case_update_history(case_id: str, token: str):
    """Get update history for a specific case"""
    # Verify attorney token
    attorney = await db.attorneys.find_one({"token": token, "status": "approved"}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    attorney_id = attorney["id"]
    
    # Verify case belongs to this attorney (check both field patterns)
    case = await db.marketplace_cases.find_one({
        "case_id": case_id,
        "$or": [
            {"assignment.pledged_to_attorney_id": attorney_id},
            {"assigned_attorney_id": attorney_id}
        ]
    }, {"_id": 0})
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    # Get all updates for this case
    updates = await db.case_updates.find(
        {"case_id": case_id, "attorney_id": attorney_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return {"case": case, "updates": updates}


# ============= ADMIN PENALTY MANAGEMENT =============

@case_update_router.get("/admin/overdue-cases")
async def get_all_overdue_cases(user: dict = Depends(get_current_user_from_token)):
    """Admin: Get all cases that are overdue for updates across all attorneys"""
    if not user or user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    
    # Get all pledged/in_progress cases
    cases = await db.marketplace_cases.find({
        "status": {"$in": ["pledged", "in_progress"]},
        "assigned_attorney_id": {"$exists": True, "$ne": None}
    }, {"_id": 0}).to_list(500)
    
    overdue_cases = []
    
    for case in cases:
        attorney_id = case["assigned_attorney_id"]
        
        # Get the most recent update for this case
        last_update = await db.case_updates.find_one(
            {"case_id": case["case_id"], "attorney_id": attorney_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        
        # Determine last update date
        if last_update:
            last_update_date = datetime.fromisoformat(last_update["created_at"].replace("Z", "+00:00"))
        else:
            last_update_date = datetime.fromisoformat(case.get("pledged_at", case["created_at"]).replace("Z", "+00:00"))
        
        days_since_update = (now - last_update_date).days
        
        if days_since_update >= 30:
            days_overdue = days_since_update - 30
            
            # Get attorney info
            attorney = await db.attorneys.find_one({"id": attorney_id}, {"_id": 0, "full_name": 1, "email": 1, "marketplace_locked": 1})
            
            overdue_cases.append({
                "case_id": case["case_id"],
                "case_title": case["title"],
                "attorney_id": attorney_id,
                "attorney_name": attorney.get("full_name") if attorney else "Unknown",
                "attorney_email": attorney.get("email") if attorney else "Unknown",
                "attorney_locked": attorney.get("marketplace_locked", False) if attorney else False,
                "days_since_update": days_since_update,
                "days_overdue": days_overdue,
                "last_update_date": last_update_date.isoformat(),
                "requires_penalty": days_overdue >= 3
            })
    
    # Sort by days overdue (most overdue first)
    overdue_cases.sort(key=lambda x: x["days_overdue"], reverse=True)
    
    return {
        "overdue_cases": overdue_cases,
        "total_overdue": len(overdue_cases),
        "penalty_required_count": len([c for c in overdue_cases if c["requires_penalty"]])
    }


@case_update_router.post("/admin/apply-penalty")
async def apply_penalty_to_attorney(penalty: PenaltyRequest, user: dict = Depends(get_current_user_from_token)):
    """Admin: Apply penalty to an attorney (lock marketplace access and hold balance)"""
    if not user or user.get("role") not in ["admin", "super_admin", "director"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    attorney = await db.attorneys.find_one({"id": penalty.attorney_id})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney not found")
    
    # Lock marketplace and hold balance
    held_balance = attorney.get("account_balance", 0)
    
    await db.attorneys.update_one(
        {"id": penalty.attorney_id},
        {
            "$set": {
                "marketplace_locked": True,
                "marketplace_lock_reason": penalty.reason,
                "marketplace_locked_at": datetime.now(timezone.utc).isoformat(),
                "marketplace_locked_by": user.get("email"),
                "held_balance": held_balance,
                "account_balance": 0,
                "penalty_case_ids": penalty.case_ids,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Log the penalty action
    penalty_log = {
        "id": str(uuid4()),
        "attorney_id": penalty.attorney_id,
        "action": "penalty_applied",
        "reason": penalty.reason,
        "case_ids": penalty.case_ids,
        "held_balance": held_balance,
        "applied_by": user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.attorney_penalty_logs.insert_one(penalty_log)
    
    return {
        "message": "Penalty applied successfully",
        "attorney_id": penalty.attorney_id,
        "marketplace_locked": True,
        "held_balance": held_balance
    }


@case_update_router.post("/admin/remove-penalty/{attorney_id}")
async def remove_penalty_from_attorney(attorney_id: str, user: dict = Depends(get_current_user_from_token)):
    """Admin: Remove penalty from an attorney (restore marketplace access and balance)"""
    if not user or user.get("role") not in ["admin", "super_admin", "director"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    attorney = await db.attorneys.find_one({"id": attorney_id})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney not found")
    
    if not attorney.get("marketplace_locked"):
        raise HTTPException(status_code=400, detail="Attorney is not currently penalized")
    
    # Restore balance and access
    held_balance = attorney.get("held_balance", 0)
    
    await db.attorneys.update_one(
        {"id": attorney_id},
        {
            "$set": {
                "marketplace_locked": False,
                "marketplace_lock_reason": None,
                "marketplace_locked_at": None,
                "marketplace_locked_by": None,
                "account_balance": held_balance,
                "held_balance": 0,
                "penalty_case_ids": [],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Log the penalty removal
    penalty_log = {
        "id": str(uuid4()),
        "attorney_id": attorney_id,
        "action": "penalty_removed",
        "restored_balance": held_balance,
        "removed_by": user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.attorney_penalty_logs.insert_one(penalty_log)
    
    return {
        "message": "Penalty removed successfully",
        "attorney_id": attorney_id,
        "marketplace_locked": False,
        "restored_balance": held_balance
    }


@case_update_router.get("/admin/penalty-logs/{attorney_id}")
async def get_attorney_penalty_logs(attorney_id: str, user: dict = Depends(get_current_user_from_token)):
    """Admin: Get penalty history for an attorney"""
    if not user or user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    logs = await db.attorney_penalty_logs.find(
        {"attorney_id": attorney_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return logs


# ============= SEED DEFAULT STATUS OPTIONS =============

async def seed_case_update_status_options():
    """Seed default case update status options"""
    existing = await db.case_update_status_options.count_documents({})
    if existing > 0:
        return
    
    default_options = [
        {"name": "Under Review", "description": "Case is being reviewed and evaluated", "display_order": 1},
        {"name": "In Negotiations", "description": "Settlement negotiations are in progress", "display_order": 2},
        {"name": "Litigation Filed", "description": "Lawsuit has been filed in court", "display_order": 3},
        {"name": "Discovery Phase", "description": "Case is in the discovery phase", "display_order": 4},
        {"name": "Settlement Pending", "description": "Settlement terms agreed, awaiting finalization", "display_order": 5},
        {"name": "Case Won", "description": "Case resolved favorably for client", "display_order": 6},
        {"name": "Case Lost", "description": "Case resolved unfavorably", "display_order": 7},
        {"name": "Case Dismissed", "description": "Case was dismissed", "display_order": 8},
        {"name": "Client Unresponsive", "description": "Waiting for client response", "display_order": 9},
        {"name": "Awaiting Court Date", "description": "Waiting for scheduled court date", "display_order": 10}
    ]
    
    for opt in default_options:
        option = {
            "id": str(uuid4()),
            "name": opt["name"],
            "description": opt["description"],
            "is_active": True,
            "display_order": opt["display_order"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.case_update_status_options.insert_one(option)
    
    print("✅ Seeded default case update status options")
