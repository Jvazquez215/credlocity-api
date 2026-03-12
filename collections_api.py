"""
Collections Management System API Routes
Handles accounts, contacts, compliance, payment plans, commissions, and disputes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import uuid4
import bcrypt
import os

collections_router = APIRouter(prefix="/collections", tags=["Collections"])

# Will be set by server.py
db = None

def set_db(database):
    global db
    db = database


# ==================== HELPER FUNCTIONS ====================

def calculate_days_past_due(first_failed_date: str) -> int:
    """Calculate days between first failed payment and today"""
    try:
        failed_date = datetime.strptime(first_failed_date, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        return (today - failed_date).days
    except:
        return 0

def get_tier_from_days(days: int) -> int:
    """Determine tier based on days past due"""
    if days <= 45:
        return 1
    elif days <= 60:
        return 2
    elif days <= 90:
        return 3
    else:
        return 4

def get_tier_info(tier: int) -> dict:
    """Get tier-specific rules and rates"""
    tiers = {
        1: {
            "name": "Tier 1",
            "days_range": "1-45 days",
            "full_discount": 0,
            "plan_discount": 0,
            "min_down_percent": 50,
            "max_months": 2,
            "commission_full": 5,
            "commission_plan": 5,
            "bonus_48hr": 1,
            "approval_required": None
        },
        2: {
            "name": "Tier 2",
            "days_range": "46-60 days",
            "full_discount": 15,
            "plan_discount": 0,
            "min_down_percent": 33,
            "max_months": 3,
            "commission_full": 12,
            "commission_plan": 6,
            "bonus_48hr": 0,
            "approval_required": "team_leader"
        },
        3: {
            "name": "Tier 3",
            "days_range": "61-90 days",
            "full_discount": 25,
            "plan_discount": 10,
            "min_down_percent": 40,
            "max_months": 6,
            "commission_full": 20,
            "commission_plan": 10,
            "bonus_48hr": 0,
            "approval_required": "collections_manager"
        },
        4: {
            "name": "Tier 4",
            "days_range": "91+ days",
            "full_discount": 35,
            "plan_discount": 20,
            "min_down_percent": 50,
            "max_months": 13,
            "commission_full": 30,
            "commission_plan": 15,
            "bonus_48hr": 0,
            "approval_required": "director"
        }
    }
    return tiers.get(tier, tiers[1])

async def get_collections_user(token: str = None, authorization: str = None):
    """Validate collections user token and return user.
    Works with both collections employees and main admin users.
    Accepts token as query param or Authorization header.
    """
    from server import decode_token
    
    # Extract token from Authorization header if provided
    actual_token = token
    if not actual_token and authorization:
        if authorization.startswith("Bearer "):
            actual_token = authorization[7:]
        else:
            actual_token = authorization
    
    if not actual_token:
        return None
    
    payload = decode_token(actual_token)
    if not payload:
        return None
    email = payload.get("sub")
    
    # First try collections employees
    user = await db.collections_employees.find_one({"email": email, "is_active": True}, {"_id": 0})
    if user:
        return user
    
    # Fall back to main admin users (for CMS admin access to collections)
    admin_user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if admin_user:
        # Map admin user to collections user format
        return {
            "id": admin_user.get("id", str(uuid4())),
            "email": admin_user.get("email"),
            "full_name": admin_user.get("full_name", admin_user.get("name", "Admin")),
            "role": "admin",  # Admin users have full access
            "is_active": True
        }
    
    return None

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


# ==================== COLLECTIONS AUTH ====================

@collections_router.post("/auth/login")
async def collections_login(data: dict):
    """Login for collections employees"""
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    user = await db.collections_employees.find_one({"email": email.lower()}, {"_id": 0})
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate token
    from server import create_access_token
    token = create_access_token(data={"sub": email, "type": "collections"})
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }

@collections_router.get("/auth/me")
async def get_current_collections_user(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get current collections user info"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    user.pop("password_hash", None)
    return user


# ==================== EMPLOYEES MANAGEMENT ====================

@collections_router.get("/employees")
async def get_employees(token: Optional[str] = None, role: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get all collections employees"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query = {"is_active": True}
    if role:
        query["role"] = role
    
    employees = await db.collections_employees.find(query, {"_id": 0, "password_hash": 0}).to_list(None)
    return employees

@collections_router.post("/employees")
async def create_employee(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Create a new collections employee"""
    user = await get_collections_user(token, authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check email uniqueness
    existing = await db.collections_employees.find_one({"email": data.get("email", "").lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    employee = {
        "id": str(uuid4()),
        "email": data.get("email", "").lower(),
        "password_hash": hash_password(data.get("password", "Password123!")),
        "full_name": data.get("full_name", ""),
        "role": data.get("role", "collections_agent"),
        "reports_to_id": data.get("reports_to_id"),
        "base_salary": data.get("base_salary", 500.00),
        "is_active": True,
        "phone": data.get("phone"),
        "hire_date": data.get("hire_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.collections_employees.insert_one(employee)
    employee.pop("_id", None)
    employee.pop("password_hash", None)
    return employee

@collections_router.put("/employees/{employee_id}")
async def update_employee(employee_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Update a collections employee"""
    user = await get_collections_user(token, authorization)
    if not user or user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    update_data = {k: v for k, v in data.items() if k not in ["id", "password_hash", "created_at"]}
    if "password" in data and data["password"]:
        update_data["password_hash"] = hash_password(data["password"])
        del update_data["password"]
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.collections_employees.update_one({"id": employee_id}, {"$set": update_data})
    updated = await db.collections_employees.find_one({"id": employee_id}, {"_id": 0, "password_hash": 0})
    return updated

@collections_router.get("/employees/hierarchy")
async def get_employee_hierarchy(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get employee hierarchy tree"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    employees = await db.collections_employees.find({"is_active": True}, {"_id": 0, "password_hash": 0}).to_list(None)
    
    # Build hierarchy
    hierarchy = []
    emp_map = {e["id"]: e for e in employees}
    
    for emp in employees:
        if not emp.get("reports_to_id"):
            emp["direct_reports"] = [e for e in employees if e.get("reports_to_id") == emp["id"]]
            hierarchy.append(emp)
    
    return hierarchy


# ==================== COLLECTIONS ACCOUNTS ====================

@collections_router.get("/accounts")
async def get_accounts(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    tier: Optional[int] = None,
    assigned_rep_id: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get collections accounts with filters"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query = {}
    
    # Role-based filtering
    if user["role"] == "collections_agent":
        query["assigned_rep_id"] = user["id"]
    elif user["role"] == "team_leader":
        # Get team members
        team = await db.collections_employees.find({"reports_to_id": user["id"]}, {"id": 1}).to_list(None)
        team_ids = [user["id"]] + [t["id"] for t in team]
        query["assigned_rep_id"] = {"$in": team_ids}
    # managers and above see all
    
    if status:
        query["account_status"] = status
    if tier:
        query["current_tier"] = tier
    if assigned_rep_id and user["role"] in ["collections_manager", "director", "admin"]:
        query["assigned_rep_id"] = assigned_rep_id
    if search:
        query["client_name"] = {"$regex": search, "$options": "i"}
    
    # Get accounts with updated tier info
    accounts = await db.collections_accounts.find(query, {"_id": 0}).sort("days_past_due", -1).skip(skip).limit(limit).to_list(None)
    
    # Update days_past_due and tier for each account
    for acc in accounts:
        acc["days_past_due"] = calculate_days_past_due(acc.get("first_failed_payment_date", ""))
        acc["current_tier"] = get_tier_from_days(acc["days_past_due"])
    
    total = await db.collections_accounts.count_documents(query)
    
    # Get today's compliance for each account
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for acc in accounts:
        compliance = await db.collections_daily_compliance.find_one(
            {"account_id": acc["id"], "date": today}, {"_id": 0}
        )
        acc["today_compliance"] = compliance or {"calls_completed": 0, "texts_completed": 0, "emails_completed": 0}
    
    return {"accounts": accounts, "total": total, "skip": skip, "limit": limit}

@collections_router.get("/accounts/{account_id}")
async def get_account(account_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get single account detail"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    account = await db.collections_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Update computed fields
    account["days_past_due"] = calculate_days_past_due(account.get("first_failed_payment_date", ""))
    account["current_tier"] = get_tier_from_days(account["days_past_due"])
    account["tier_info"] = get_tier_info(account["current_tier"])
    
    # Get today's compliance
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    compliance = await db.collections_daily_compliance.find_one(
        {"account_id": account_id, "date": today}, {"_id": 0}
    )
    account["today_compliance"] = compliance or {"calls_completed": 0, "texts_completed": 0, "emails_completed": 0, "compliance_met": False}
    
    # Get recent notes
    notes = await db.collections_notes.find({"account_id": account_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(None)
    account["notes"] = notes
    
    # Get contact history (last 30 days)
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    contact_history = await db.collections_daily_compliance.find(
        {"account_id": account_id, "date": {"$gte": thirty_days_ago}},
        {"_id": 0}
    ).sort("date", -1).to_list(None)
    account["contact_history"] = contact_history
    
    # Get active payment agreement if exists
    agreement = await db.payment_agreements.find_one(
        {"account_id": account_id, "status": "active"}, {"_id": 0}
    )
    account["active_agreement"] = agreement
    
    return account

@collections_router.post("/accounts")
async def create_account(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Create a new collections account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate first_failed_payment_date
    first_failed = data.get("first_failed_payment_date")
    if not first_failed:
        raise HTTPException(status_code=400, detail="First failed payment date is required")
    
    days_past_due = calculate_days_past_due(first_failed)
    current_tier = get_tier_from_days(days_past_due)
    
    # Calculate initial balance
    monthly_rate = 279.95 if data.get("package_type") == "couple" else 179.95
    months_past_due = max(1, days_past_due // 30)
    past_due_balance = monthly_rate * months_past_due
    
    account = {
        "id": str(uuid4()),
        "client_id": data.get("client_id"),
        "client_name": data.get("client_name", ""),
        "client_email": data.get("client_email"),
        "client_phone": data.get("client_phone"),
        "package_type": data.get("package_type", "individual"),
        "monthly_rate": monthly_rate,
        "first_failed_payment_date": first_failed,
        "days_past_due": days_past_due,
        "current_tier": current_tier,
        "past_due_balance": data.get("past_due_balance", past_due_balance),
        "account_status": "active",
        "assigned_rep_id": data.get("assigned_rep_id", user["id"]),
        "assigned_rep_name": data.get("assigned_rep_name", user["full_name"]),
        "notes_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.collections_accounts.insert_one(account)
    
    # Create system note
    note = {
        "id": str(uuid4()),
        "account_id": account["id"],
        "note_type": "system",
        "note_text": f"Account created. Tier {current_tier} ({days_past_due} days past due). Balance: ${past_due_balance:.2f}",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    account.pop("_id", None)
    return account

@collections_router.put("/accounts/{account_id}")
async def update_account(account_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Update a collections account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    existing = await db.collections_accounts.find_one({"id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check if first_failed_payment_date is being changed
    if "first_failed_payment_date" in data and data["first_failed_payment_date"] != existing.get("first_failed_payment_date"):
        if user["role"] not in ["collections_manager", "director", "admin"]:
            raise HTTPException(status_code=403, detail="Only managers can change first failed payment date")
        
        # Log the change
        note = {
            "id": str(uuid4()),
            "account_id": account_id,
            "note_type": "system",
            "note_text": f"First failed payment date changed from {existing.get('first_failed_payment_date')} to {data['first_failed_payment_date']} by {user['full_name']}. Reason: {data.get('change_reason', 'Not specified')}",
            "created_by_id": user["id"],
            "created_by_name": user["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.collections_notes.insert_one(note)
    
    update_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "change_reason"]}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.collections_accounts.update_one({"id": account_id}, {"$set": update_data})
    updated = await db.collections_accounts.find_one({"id": account_id}, {"_id": 0})
    return updated


@collections_router.put("/accounts/{account_id}/archive")
async def archive_account(account_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Archive a collections account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    existing = await db.collections_accounts.find_one({"id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Update status to archived
    await db.collections_accounts.update_one(
        {"id": account_id}, 
        {"$set": {
            "account_status": "archived",
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by_id": user["id"],
            "archived_by_name": user["full_name"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Create archive note
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "note_type": "system",
        "note_text": f"Account archived by {user['full_name']}",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    return {"message": "Account archived successfully", "account_id": account_id}


@collections_router.put("/accounts/{account_id}/restore")
async def restore_account(account_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Restore an archived collections account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    existing = await db.collections_accounts.find_one({"id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    
    if existing.get("account_status") != "archived":
        raise HTTPException(status_code=400, detail="Account is not archived")
    
    # Restore to active
    await db.collections_accounts.update_one(
        {"id": account_id}, 
        {"$set": {
            "account_status": "active",
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "restored_by_id": user["id"],
            "restored_by_name": user["full_name"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        "$unset": {"archived_at": "", "archived_by_id": "", "archived_by_name": ""}}
    )
    
    # Create restore note
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "note_type": "system",
        "note_text": f"Account restored from archive by {user['full_name']}",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    return {"message": "Account restored successfully", "account_id": account_id}


@collections_router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Permanently delete a collections account (managers only)"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Only managers and above can delete
    if user["role"] not in ["collections_manager", "director", "admin"]:
        raise HTTPException(status_code=403, detail="Only managers can delete accounts")
    
    existing = await db.collections_accounts.find_one({"id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Delete the account
    await db.collections_accounts.delete_one({"id": account_id})
    
    # Also delete related notes
    await db.collections_notes.delete_many({"account_id": account_id})
    
    # Delete related contacts
    await db.collections_contacts.delete_many({"account_id": account_id})
    
    return {"message": "Account deleted permanently", "account_id": account_id}


# ==================== CONTACT LOGGING ====================

@collections_router.post("/accounts/{account_id}/contacts")
async def log_contact(account_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Log a contact (call, text, or email)"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    contact_type = data.get("contact_type")  # call, text, email
    if contact_type not in ["call", "text", "email"]:
        raise HTTPException(status_code=400, detail="Invalid contact type")
    
    outcome = data.get("outcome", "")
    if len(outcome) < 10:
        raise HTTPException(status_code=400, detail="Outcome must be at least 10 characters")
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Get or create daily compliance record
    compliance = await db.collections_daily_compliance.find_one({"account_id": account_id, "date": today})
    if not compliance:
        compliance = {
            "id": str(uuid4()),
            "account_id": account_id,
            "date": today,
            "calls_completed": 0,
            "texts_completed": 0,
            "emails_completed": 0,
            "compliance_met": False,
            "auto_note_generated": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.collections_daily_compliance.insert_one(compliance)
    
    # Check if max contacts reached for this type
    type_field = f"{contact_type}s_completed"
    current_count = compliance.get(type_field, 0)
    if current_count >= 3:
        raise HTTPException(status_code=400, detail=f"Maximum 3 {contact_type}s already logged today")
    
    # Create contact record
    contact = {
        "id": str(uuid4()),
        "account_id": account_id,
        "contact_date": today,
        "contact_type": contact_type,
        "contact_number": current_count + 1,
        "contact_time": data.get("contact_time", datetime.now(timezone.utc).isoformat()),
        "outcome": outcome,
        "template_used": data.get("template_used"),
        "completed_by_rep_id": user["id"],
        "completed_by_rep_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_contacts.insert_one(contact)
    
    # Update compliance
    new_count = current_count + 1
    update = {"$set": {type_field: new_count}}
    
    # Check if all 9 contacts done
    calls = compliance.get("calls_completed", 0) + (1 if contact_type == "call" else 0)
    texts = compliance.get("texts_completed", 0) + (1 if contact_type == "text" else 0)
    emails = compliance.get("emails_completed", 0) + (1 if contact_type == "email" else 0)
    
    if calls >= 3 and texts >= 3 and emails >= 3:
        update["$set"]["compliance_met"] = True
        
        # Generate auto-note if not already done
        if not compliance.get("auto_note_generated"):
            auto_note = {
                "id": str(uuid4()),
                "account_id": account_id,
                "note_type": "auto_compliance",
                "note_text": f"[Auto-Generated Entry - {datetime.now(timezone.utc).strftime('%m/%d/%Y %I:%M %p')}]\nMinimum contact made per Credlocity Collection Policies.\nCalls: 3/3 | Texts: 3/3 | Emails: 3/3\nStatus: Compliance Met",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.collections_notes.insert_one(auto_note)
            await db.collections_accounts.update_one({"id": account_id}, {"$inc": {"notes_count": 1}})
            update["$set"]["auto_note_generated"] = True
    
    await db.collections_daily_compliance.update_one({"id": compliance["id"]}, update)
    
    # Update account last contact date
    await db.collections_accounts.update_one(
        {"id": account_id},
        {"$set": {"last_contact_date": datetime.now(timezone.utc).isoformat()}}
    )
    
    contact.pop("_id", None)
    return {"contact": contact, "compliance": {"calls": calls, "texts": texts, "emails": emails}}

@collections_router.get("/accounts/{account_id}/compliance")
async def get_account_compliance(account_id: str, token: Optional[str] = None, days: int = 30, authorization: Optional[str] = Header(None)):
    """Get compliance history for an account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    
    compliance = await db.collections_daily_compliance.find(
        {"account_id": account_id, "date": {"$gte": start_date}},
        {"_id": 0}
    ).sort("date", -1).to_list(None)
    
    return compliance


# ==================== NOTES ====================

@collections_router.post("/accounts/{account_id}/notes")
async def add_note(account_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Add a note to an account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "ticket_id": data.get("ticket_id"),
        "note_type": data.get("note_type", "manual"),
        "note_text": data.get("note_text", ""),
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.collections_notes.insert_one(note)
    await db.collections_accounts.update_one({"id": account_id}, {"$inc": {"notes_count": 1}})
    
    note.pop("_id", None)
    return note

@collections_router.get("/accounts/{account_id}/notes")
async def get_notes(account_id: str, token: Optional[str] = None, note_type: Optional[str] = None, limit: int = 50, authorization: Optional[str] = Header(None)):
    """Get notes for an account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query = {"account_id": account_id}
    if note_type:
        query["note_type"] = note_type
    
    notes = await db.collections_notes.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(None)
    return notes


# ==================== DISPUTE TICKETS ====================

@collections_router.post("/accounts/{account_id}/dispute")
async def create_dispute_ticket(account_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Mark account as disputed and create ticket"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    account = await db.collections_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Generate ticket number
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    count = await db.collections_tickets.count_documents({"ticket_number": {"$regex": f"^CT-{today}"}})
    ticket_number = f"CT-{today}-{str(count + 1).zfill(3)}"
    
    ticket = {
        "id": str(uuid4()),
        "ticket_number": ticket_number,
        "account_id": account_id,
        "client_name": account["client_name"],
        "account_balance": account["past_due_balance"],
        "dispute_date": datetime.now(timezone.utc).isoformat(),
        "assigned_rep_id": user["id"],
        "assigned_rep_name": user["full_name"],
        "status": "open",
        "priority": "high",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.collections_tickets.insert_one(ticket)
    
    # Update account status
    await db.collections_accounts.update_one(
        {"id": account_id},
        {"$set": {"account_status": "disputed", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Add system note
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "ticket_id": ticket["id"],
        "note_type": "system",
        "note_text": f"Account marked as disputed by {user['full_name']}. Ticket #{ticket_number} created.",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    ticket.pop("_id", None)
    return ticket

@collections_router.get("/tickets")
async def get_tickets(
    token: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    authorization: Optional[str] = Header(None)
):
    """Get dispute tickets"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query = {}
    
    # Role-based filtering
    if user["role"] == "collections_agent":
        query["assigned_rep_id"] = user["id"]
    
    if status:
        query["status"] = status
    if priority:
        query["priority"] = priority
    
    tickets = await db.collections_tickets.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.collections_tickets.count_documents(query)
    
    return {"tickets": tickets, "total": total}

@collections_router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get ticket detail"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    ticket = await db.collections_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    # Get investigation notes
    notes = await db.collections_notes.find(
        {"ticket_id": ticket_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(None)
    ticket["investigation_notes_list"] = notes
    
    return ticket

@collections_router.put("/tickets/{ticket_id}")
async def update_ticket(ticket_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Update a dispute ticket"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Only managers+ can update tickets
    if user["role"] not in ["collections_manager", "director", "admin"]:
        raise HTTPException(status_code=403, detail="Only managers can update tickets")
    
    update_data = {k: v for k, v in data.items() if k not in ["id", "ticket_number", "created_at"]}
    
    if "status" in data and data["status"].startswith("resolved"):
        update_data["resolved_by_id"] = user["id"]
        update_data["resolved_by_name"] = user["full_name"]
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.collections_tickets.update_one({"id": ticket_id}, {"$set": update_data})
    
    # Add investigation note if provided
    if data.get("investigation_note"):
        note = {
            "id": str(uuid4()),
            "account_id": (await db.collections_tickets.find_one({"id": ticket_id}))["account_id"],
            "ticket_id": ticket_id,
            "note_type": "investigation",
            "note_text": data["investigation_note"],
            "created_by_id": user["id"],
            "created_by_name": user["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.collections_notes.insert_one(note)
    
    updated = await db.collections_tickets.find_one({"id": ticket_id}, {"_id": 0})
    return updated


# ==================== PAYMENT AGREEMENTS ====================

@collections_router.post("/accounts/{account_id}/payment-plan")
async def create_payment_plan(account_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Create a payment agreement/plan"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    account = await db.collections_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    tier = data.get("tier_accepted", account.get("current_tier", 3))
    tier_info = get_tier_info(tier)
    
    # Check authorization
    approval_role = tier_info.get("approval_required")
    if approval_role:
        role_hierarchy = ["collections_agent", "team_leader", "collections_manager", "director", "admin"]
        user_level = role_hierarchy.index(user["role"]) if user["role"] in role_hierarchy else -1
        required_level = role_hierarchy.index(approval_role)
        if user_level < required_level:
            raise HTTPException(status_code=403, detail=f"Tier {tier} requires {approval_role} approval")
    
    # Calculate totals
    non_waivable_total = data.get("credit_reports_charge", 199.80) + data.get("services_rendered_charge", 0)
    
    adjusted_fees_total = (
        data.get("late_fees_adjusted", 0) +
        data.get("collection_fee_adjusted", 0) +
        data.get("file_processing_fee_adjusted", 0) +
        data.get("payment_processing_fee_adjusted", 0) +
        (data.get("conditional_charge_adjusted") or 0)
    )
    
    waived_amount_total = (
        (data.get("late_fees_original", 0) - data.get("late_fees_adjusted", 0)) +
        (data.get("collection_fee_original", 0) - data.get("collection_fee_adjusted", 0)) +
        (data.get("file_processing_fee_original", 0) - data.get("file_processing_fee_adjusted", 0)) +
        (data.get("payment_processing_fee_original", 0) - data.get("payment_processing_fee_adjusted", 0)) +
        ((data.get("conditional_charge_original") or 0) - (data.get("conditional_charge_adjusted") or 0))
    )
    
    adjusted_balance = non_waivable_total + adjusted_fees_total
    remaining_balance = adjusted_balance - data.get("down_payment_amount", 0)
    
    agreement = {
        "id": str(uuid4()),
        "account_id": account_id,
        "client_name": account["client_name"],
        "tier_accepted": tier,
        "tier_name": data.get("tier_name", f"Tier {tier}"),
        "original_balance": data.get("original_balance", account["past_due_balance"]),
        "discount_percentage": data.get("discount_percentage", tier_info["plan_discount"]),
        "discount_amount": data.get("discount_amount", 0),
        "adjusted_balance": adjusted_balance,
        "down_payment_amount": data.get("down_payment_amount", 0),
        "down_payment_date": data.get("down_payment_date"),
        "remaining_balance": remaining_balance,
        "payment_frequency": data.get("payment_frequency", "monthly"),
        "number_of_payments": data.get("number_of_payments", 1),
        "payment_amount": data.get("payment_amount", remaining_balance),
        "total_plan_amount": data.get("down_payment_amount", 0) + (data.get("payment_amount", 0) * data.get("number_of_payments", 1)),
        "credit_reports_charge": data.get("credit_reports_charge", 199.80),
        "services_rendered_charge": data.get("services_rendered_charge", 0),
        "non_waivable_total": non_waivable_total,
        "late_fees_original": data.get("late_fees_original", 0),
        "late_fees_adjusted": data.get("late_fees_adjusted", 0),
        "collection_fee_original": data.get("collection_fee_original", 0),
        "collection_fee_adjusted": data.get("collection_fee_adjusted", 0),
        "file_processing_fee_original": data.get("file_processing_fee_original", 0),
        "file_processing_fee_adjusted": data.get("file_processing_fee_adjusted", 0),
        "payment_processing_fee_original": data.get("payment_processing_fee_original", 0),
        "payment_processing_fee_adjusted": data.get("payment_processing_fee_adjusted", 0),
        "conditional_charge_original": data.get("conditional_charge_original"),
        "conditional_charge_adjusted": data.get("conditional_charge_adjusted"),
        "conditional_charge_description": data.get("conditional_charge_description"),
        "adjusted_fees_total": adjusted_fees_total,
        "waived_amount_total": waived_amount_total,
        "status": "active",
        "created_by_rep_id": user["id"],
        "created_by_rep_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.payment_agreements.insert_one(agreement)
    
    # Create payment schedule
    schedule = []
    
    # Down payment
    down_payment = {
        "id": str(uuid4()),
        "agreement_id": agreement["id"],
        "payment_number": 0,
        "payment_date": data.get("down_payment_date"),
        "payment_amount": data.get("down_payment_amount", 0),
        "status": "scheduled",
        "rep_commission_amount": data.get("down_payment_amount", 0) * 0.05,  # 5% default
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    schedule.append(down_payment)
    
    # Installments
    frequency_days = {"weekly": 7, "bi_weekly": 14, "monthly": 30}
    days_between = frequency_days.get(data.get("payment_frequency", "monthly"), 30)
    
    start_date = datetime.strptime(data.get("down_payment_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")), "%Y-%m-%d")
    
    for i in range(1, data.get("number_of_payments", 1) + 1):
        payment_date = start_date + timedelta(days=days_between * i)
        installment = {
            "id": str(uuid4()),
            "agreement_id": agreement["id"],
            "payment_number": i,
            "payment_date": payment_date.strftime("%Y-%m-%d"),
            "payment_amount": data.get("payment_amount", 0),
            "status": "scheduled",
            "rep_commission_amount": data.get("payment_amount", 0) * 0.03,  # 3% default
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        schedule.append(installment)
    
    if schedule:
        await db.payment_schedule.insert_many(schedule)
    
    # Update account status
    await db.collections_accounts.update_one(
        {"id": account_id},
        {"$set": {"account_status": "payment_plan", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Add system note
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "note_type": "system",
        "note_text": f"Payment plan created by {user['full_name']}. {agreement['tier_name']}. Down payment: ${agreement['down_payment_amount']:.2f}. {agreement['number_of_payments']} payments of ${agreement['payment_amount']:.2f}.",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    agreement.pop("_id", None)
    agreement["schedule"] = schedule
    return agreement

@collections_router.get("/accounts/{account_id}/payment-plans")
async def get_payment_plans(account_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get payment plans for an account"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    agreements = await db.payment_agreements.find({"account_id": account_id}, {"_id": 0}).to_list(None)
    
    for agreement in agreements:
        schedule = await db.payment_schedule.find({"agreement_id": agreement["id"]}, {"_id": 0}).sort("payment_number", 1).to_list(None)
        agreement["schedule"] = schedule
    
    return agreements


# ==================== COMMISSION PREVIEW ====================

@collections_router.post("/commission/preview")
async def preview_commission(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Preview commission for a potential collection"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    amount = data.get("amount", 0)
    tier = data.get("tier", 3)
    payment_type = data.get("payment_type", "full")  # full or plan
    
    tier_info = get_tier_info(tier)
    
    # Check for employee overrides
    override = await db.employee_commission_overrides.find_one(
        {"employee_id": user["id"], "effective_date": {"$lte": datetime.now(timezone.utc).strftime("%Y-%m-%d")}},
        {"_id": 0}
    )
    
    if payment_type == "full":
        rate = tier_info["commission_full"]
        if override and override.get(f"tier_{tier}_full_rate"):
            rate = override[f"tier_{tier}_full_rate"]
        
        commission = amount * (rate / 100)
        
        # 48hr bonus for tier 1
        bonus_48hr = 0
        if tier == 1:
            bonus_rate = tier_info["bonus_48hr"]
            if override and override.get("tier_1_bonus_48hr"):
                bonus_rate = override["tier_1_bonus_48hr"]
            bonus_48hr = amount * (bonus_rate / 100)
        
        return {
            "payment_type": "full",
            "amount": amount,
            "tier": tier,
            "commission_rate": rate,
            "base_commission": commission,
            "bonus_48hr": bonus_48hr,
            "total_commission": commission + bonus_48hr
        }
    else:
        # Payment plan
        down_payment = data.get("down_payment", 0)
        installment_amount = data.get("installment_amount", 0)
        num_payments = data.get("num_payments", 1)
        
        down_rate = 5.0
        if override and override.get("down_payment_rate"):
            down_rate = override["down_payment_rate"]
        
        installment_rate = 3.0
        if override and override.get("monthly_payment_rate"):
            installment_rate = override["monthly_payment_rate"]
        
        completion_rate = 2.0
        if override and override.get("completion_bonus_rate"):
            completion_rate = override["completion_bonus_rate"]
        
        down_commission = down_payment * (down_rate / 100)
        installment_commission = installment_amount * num_payments * (installment_rate / 100)
        completion_bonus = amount * (completion_rate / 100)
        
        return {
            "payment_type": "plan",
            "total_amount": amount,
            "tier": tier,
            "down_payment": down_payment,
            "down_payment_rate": down_rate,
            "down_payment_commission": down_commission,
            "installment_amount": installment_amount,
            "num_payments": num_payments,
            "installment_rate": installment_rate,
            "installment_commission": installment_commission,
            "completion_rate": completion_rate,
            "completion_bonus": completion_bonus,
            "total_commission": down_commission + installment_commission + completion_bonus
        }


# ==================== DASHBOARD STATS ====================

@collections_router.get("/dashboard/stats")
async def get_dashboard_stats(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get dashboard statistics"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Build query based on role
    query = {}
    if user["role"] == "collections_agent":
        query["assigned_rep_id"] = user["id"]
    elif user["role"] == "team_leader":
        team = await db.collections_employees.find({"reports_to_id": user["id"]}, {"id": 1}).to_list(None)
        team_ids = [user["id"]] + [t["id"] for t in team]
        query["assigned_rep_id"] = {"$in": team_ids}
    
    # Count by status
    total_accounts = await db.collections_accounts.count_documents(query)
    active_accounts = await db.collections_accounts.count_documents({**query, "account_status": "active"})
    disputed_accounts = await db.collections_accounts.count_documents({**query, "account_status": "disputed"})
    payment_plan_accounts = await db.collections_accounts.count_documents({**query, "account_status": "payment_plan"})
    
    # Count by tier
    tier_counts = {}
    for tier in [1, 2, 3, 4]:
        tier_counts[f"tier_{tier}"] = await db.collections_accounts.count_documents({**query, "current_tier": tier})
    
    # Today's compliance
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    compliance_query = {"date": today}
    if query:
        account_ids = [a["id"] for a in await db.collections_accounts.find(query, {"id": 1}).to_list(None)]
        compliance_query["account_id"] = {"$in": account_ids}
    
    compliant_today = await db.collections_daily_compliance.count_documents({**compliance_query, "compliance_met": True})
    
    # Open tickets
    ticket_query = {"status": "open"}
    if user["role"] == "collections_agent":
        ticket_query["assigned_rep_id"] = user["id"]
    open_tickets = await db.collections_tickets.count_documents(ticket_query)
    
    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "disputed_accounts": disputed_accounts,
        "payment_plan_accounts": payment_plan_accounts,
        "tier_counts": tier_counts,
        "compliant_today": compliant_today,
        "open_tickets": open_tickets
    }


# ==================== SEED DATA ====================

@collections_router.post("/seed")
async def seed_collections_data():
    """Seed the collections database with test data"""
    import random
    
    # Check if already seeded
    existing_employees = await db.collections_employees.count_documents({})
    if existing_employees > 0:
        return {"message": "Data already seeded", "employees": existing_employees}
    
    # Create employees hierarchy
    employees = []
    
    # Director
    director = {
        "id": str(uuid4()),
        "email": "joeziel@credlocity.com",
        "password_hash": hash_password("Collections2024!"),
        "full_name": "Joeziel Rosado",
        "role": "director",
        "reports_to_id": None,
        "base_salary": 2500.00,
        "phone": "(215) 555-0100",
        "is_active": True,
        "hire_date": "2023-01-01",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    employees.append(director)
    
    # Collections Manager
    manager = {
        "id": str(uuid4()),
        "email": "sarah.williams@credlocity.com",
        "password_hash": hash_password("Collections2024!"),
        "full_name": "Sarah Williams",
        "role": "collections_manager",
        "reports_to_id": director["id"],
        "base_salary": 1500.00,
        "phone": "(215) 555-0101",
        "is_active": True,
        "hire_date": "2023-03-15",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    employees.append(manager)
    
    # Team Leader
    team_leader = {
        "id": str(uuid4()),
        "email": "mark.johnson@credlocity.com",
        "password_hash": hash_password("Collections2024!"),
        "full_name": "Mark Johnson",
        "role": "team_leader",
        "reports_to_id": manager["id"],
        "base_salary": 1000.00,
        "phone": "(215) 555-0102",
        "is_active": True,
        "hire_date": "2023-06-01",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    employees.append(team_leader)
    
    # Collections Agents
    agents_data = [
        {"name": "Jane Doe", "email": "jane.doe@credlocity.com", "phone": "(215) 555-0103"},
        {"name": "Mike Davis", "email": "mike.davis@credlocity.com", "phone": "(215) 555-0104"},
        {"name": "Lisa Chen", "email": "lisa.chen@credlocity.com", "phone": "(215) 555-0105"}
    ]
    
    agent_ids = []
    for agent_data in agents_data:
        agent = {
            "id": str(uuid4()),
            "email": agent_data["email"],
            "password_hash": hash_password("Collections2024!"),
            "full_name": agent_data["name"],
            "role": "collections_agent",
            "reports_to_id": team_leader["id"],
            "base_salary": 500.00,
            "phone": agent_data["phone"],
            "is_active": True,
            "hire_date": "2024-01-15",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        employees.append(agent)
        agent_ids.append(agent["id"])
    
    await db.collections_employees.insert_many(employees)
    
    # Create test clients and accounts
    client_names = [
        "John Smith", "Maria Garcia", "David Johnson", "Jennifer Wilson", "Michael Brown",
        "Sarah Davis", "Christopher Martinez", "Amanda Anderson", "Daniel Taylor", "Jessica Thomas",
        "Matthew Jackson", "Ashley White", "Andrew Harris", "Emily Martin", "Joshua Thompson",
        "Samantha Robinson", "James Clark", "Lauren Lewis", "Ryan Lee", "Nicole Walker"
    ]
    
    addresses = [
        ("123 Main St", "Philadelphia", "PA", "19102"),
        ("456 Oak Ave", "Philadelphia", "PA", "19103"),
        ("789 Pine Rd", "Philadelphia", "PA", "19104"),
        ("321 Elm Blvd", "Philadelphia", "PA", "19106"),
        ("654 Maple Dr", "Philadelphia", "PA", "19107"),
        ("987 Cedar Ln", "Philadelphia", "PA", "19108"),
        ("147 Birch Way", "Philadelphia", "PA", "19109"),
        ("258 Spruce Ct", "Philadelphia", "PA", "19110"),
        ("369 Walnut Pl", "Philadelphia", "PA", "19111"),
        ("741 Cherry St", "Philadelphia", "PA", "19112"),
    ]
    
    accounts = []
    
    # Define account distribution by tier/days
    tier_configs = [
        # Tier 1 (1-45 days) - 5 accounts
        {"days": 15, "count": 2}, {"days": 30, "count": 2}, {"days": 42, "count": 1},
        # Tier 2 (46-60 days) - 4 accounts
        {"days": 50, "count": 2}, {"days": 58, "count": 2},
        # Tier 3 (61-90 days) - 6 accounts
        {"days": 65, "count": 2}, {"days": 77, "count": 2}, {"days": 88, "count": 2},
        # Tier 4 (90+ days) - 5 accounts
        {"days": 95, "count": 2}, {"days": 120, "count": 2}, {"days": 180, "count": 1}
    ]
    
    account_statuses = ["active", "active", "active", "disputed", "payment_plan"]
    client_index = 0
    
    for config in tier_configs:
        for _ in range(config["count"]):
            if client_index >= len(client_names):
                break
                
            name = client_names[client_index]
            address = addresses[client_index % len(addresses)]
            package_type = "couple" if client_index % 3 == 0 else "individual"
            monthly_rate = 279.95 if package_type == "couple" else 179.95
            
            days_past_due = config["days"]
            first_failed_date = (datetime.now(timezone.utc) - timedelta(days=days_past_due)).strftime("%Y-%m-%d")
            months_past_due = max(1, days_past_due // 30)
            past_due_balance = monthly_rate * months_past_due
            
            tier = get_tier_from_days(days_past_due)
            assigned_agent_id = agent_ids[client_index % len(agent_ids)]
            assigned_agent = next(e for e in employees if e["id"] == assigned_agent_id)
            
            account = {
                "id": str(uuid4()),
                "client_id": str(uuid4()),
                "client_name": name,
                "client_email": f"{name.lower().replace(' ', '.')}@example.com",
                "client_phone": f"(555) {100 + client_index:03d}-{1000 + client_index:04d}",
                "client_address": address[0],
                "client_city": address[1],
                "client_state": address[2],
                "client_zip": address[3],
                "package_type": package_type,
                "monthly_rate": monthly_rate,
                "first_failed_payment_date": first_failed_date,
                "days_past_due": days_past_due,
                "current_tier": tier,
                "past_due_balance": round(past_due_balance, 2),
                "account_status": random.choice(account_statuses),
                "assigned_rep_id": assigned_agent_id,
                "assigned_rep_name": assigned_agent["full_name"],
                "notes_count": 0,
                "last_contact_date": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            accounts.append(account)
            client_index += 1
    
    await db.collections_accounts.insert_many(accounts)
    
    # Create sample contact logs for some accounts
    contact_outcomes = [
        "Left voicemail message requesting callback",
        "Spoke with client, promised to pay next week",
        "No answer, will try again tomorrow",
        "Client requested email with account details",
        "Payment reminder sent via text",
        "Client confirmed receipt of email statement",
        "Discussed payment plan options with client",
        "Client out of town, will call back in 3 days"
    ]
    
    compliance_records = []
    contact_records = []
    
    for account in accounts[:10]:  # First 10 accounts get contact logs
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Random compliance (some full, some partial)
        calls = random.randint(0, 3)
        texts = random.randint(0, 3)
        emails = random.randint(0, 3)
        
        compliance = {
            "id": str(uuid4()),
            "account_id": account["id"],
            "date": today,
            "calls_completed": calls,
            "texts_completed": texts,
            "emails_completed": emails,
            "compliance_met": calls >= 3 and texts >= 3 and emails >= 3,
            "auto_note_generated": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        compliance_records.append(compliance)
        
        # Create contact records
        for i in range(calls):
            contact = {
                "id": str(uuid4()),
                "account_id": account["id"],
                "contact_date": today,
                "contact_type": "call",
                "contact_number": i + 1,
                "contact_time": datetime.now(timezone.utc).isoformat(),
                "outcome": random.choice(contact_outcomes),
                "completed_by_rep_id": account["assigned_rep_id"],
                "completed_by_rep_name": account["assigned_rep_name"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            contact_records.append(contact)
    
    if compliance_records:
        await db.collections_daily_compliance.insert_many(compliance_records)
    if contact_records:
        await db.collections_contacts.insert_many(contact_records)
    
    # Create indexes
    await db.collections_employees.create_index("email", unique=True)
    await db.collections_employees.create_index("role")
    await db.collections_accounts.create_index("assigned_rep_id")
    await db.collections_accounts.create_index("current_tier")
    await db.collections_accounts.create_index("account_status")
    await db.collections_daily_compliance.create_index([("account_id", 1), ("date", 1)])
    
    return {
        "message": "Collections data seeded successfully!",
        "employees_created": len(employees),
        "accounts_created": len(accounts),
        "compliance_records": len(compliance_records),
        "contact_logs": len(contact_records),
        "test_credentials": {
            "note": "All employees have password: Collections2024!",
            "director": "joeziel@credlocity.com",
            "manager": "sarah.williams@credlocity.com",
            "team_leader": "mark.johnson@credlocity.com",
            "agents": ["jane.doe@credlocity.com", "mike.davis@credlocity.com", "lisa.chen@credlocity.com"]
        }
    }



# ==================== GOOGLE VOICE INTEGRATION ====================
# Per-rep Google Voice credentials - each rep authenticates with their own GV account
# 
# NOTE: The pygooglevoice library uses an unofficial API and may have authentication 
# issues with Google's modern security (App Passwords may be required for 2FA accounts).
# If you encounter HTTP 404 errors, you may need to:
# 1. Enable "Less secure app access" (if available) OR
# 2. Generate an App Password from Google Account settings
# 3. Use the App Password instead of your regular Google password

# Fallback to environment credentials (legacy support)
GOOGLE_VOICE_EMAIL_FALLBACK = os.environ.get("GOOGLE_VOICE_EMAIL", "")
GOOGLE_VOICE_PASSWORD_FALLBACK = os.environ.get("GOOGLE_VOICE_PASSWORD", "")

# Simple encryption for storing passwords (in production, use proper key management)
import base64
import logging

# Configure logging for Google Voice
gv_logger = logging.getLogger("google_voice")
gv_logger.setLevel(logging.INFO)

def simple_encrypt(text: str) -> str:
    """Simple base64 encoding for password storage - in production use proper encryption"""
    if not text:
        return ""
    return base64.b64encode(text.encode()).decode()

def simple_decrypt(encoded: str) -> str:
    """Simple base64 decoding for password retrieval"""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return encoded  # Return as-is if not encoded


class CredlocityDialer:
    """
    Google Voice Dialer for Credlocity CRM
    Handles calls, SMS, and communication logging
    """
    
    def __init__(self, email: str, password: str):
        """Initialize Google Voice connection"""
        self.email = email
        self.password = password
        self.voice = None
        self.is_connected = False
        self.connection_error = None
        
    async def connect(self):
        """Attempt to connect to Google Voice"""
        try:
            from googlevoice import Voice
            self.voice = Voice()
            self.voice.login(self.email, self.password)
            self.is_connected = True
            self.connection_error = None
            gv_logger.info(f"Google Voice login successful for {self.email}")
            return True, "Connected successfully"
        except ImportError:
            self.connection_error = "pygooglevoice library not installed"
            gv_logger.error(self.connection_error)
            return False, self.connection_error
        except Exception as e:
            error_msg = str(e)
            self.connection_error = error_msg
            self.is_connected = False
            
            # Provide helpful error messages
            if "404" in error_msg:
                self.connection_error = "Authentication failed (HTTP 404). This usually means: 1) Invalid credentials, 2) Need to use an App Password for 2FA accounts, or 3) Google has updated their API. Try generating an App Password from your Google Account security settings."
            elif "Unauthorized" in error_msg or "401" in error_msg:
                self.connection_error = "Invalid email or password. If you have 2-Step Verification enabled, you need to use an App Password instead of your regular password."
            
            gv_logger.error(f"Google Voice login failed: {self.connection_error}")
            return False, self.connection_error
    
    def make_call(self, outgoing_number: str, forwarding_number: str = None):
        """
        Initiate a call via Google Voice
        
        Args:
            outgoing_number: The number to call
            forwarding_number: Your phone that will ring first (optional)
        """
        if not self.is_connected or not self.voice:
            return {"success": False, "error": "Not connected to Google Voice"}
        
        try:
            if forwarding_number:
                self.voice.call(outgoing_number, forwarding_number)
            else:
                self.voice.call(outgoing_number)
            
            gv_logger.info(f"Call initiated to {outgoing_number}")
            return {"success": True, "message": "Call initiated - your phone will ring"}
        except Exception as e:
            gv_logger.error(f"Call failed: {e}")
            return {"success": False, "error": str(e)}
    
    def send_sms(self, phone_number: str, message: str):
        """
        Send SMS via Google Voice
        
        Args:
            phone_number: Recipient's phone number
            message: Text message content
        """
        if not self.is_connected or not self.voice:
            return {"success": False, "error": "Not connected to Google Voice"}
        
        try:
            self.voice.send_sms(phone_number, message)
            gv_logger.info(f"SMS sent to {phone_number}")
            return {"success": True, "message": "SMS sent successfully"}
        except Exception as e:
            gv_logger.error(f"SMS failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_sms_history(self):
        """Retrieve SMS messages from Google Voice"""
        if not self.is_connected or not self.voice:
            return []
        
        try:
            self.voice.sms()
            messages = []
            for msg in self.voice.sms.messages:
                messages.append({
                    "id": msg.id,
                    "phone_number": getattr(msg, 'phoneNumber', ''),
                    "display_number": getattr(msg, 'displayNumber', ''),
                    "text": getattr(msg, 'messageText', ''),
                    "time": getattr(msg, 'displayStartDateTime', ''),
                    "is_read": getattr(msg, 'isRead', False)
                })
            return messages
        except Exception as e:
            gv_logger.error(f"Failed to get SMS history: {e}")
            return []
    
    def get_call_history(self, call_type: str = "all"):
        """
        Retrieve call history from Google Voice
        
        Args:
            call_type: "placed", "received", "missed", or "all"
        """
        if not self.is_connected or not self.voice:
            return []
        
        try:
            calls = []
            
            if call_type in ["placed", "all"]:
                self.voice.placed()
                for msg in self.voice.placed.messages:
                    calls.append({
                        "id": msg.id,
                        "type": "placed",
                        "phone_number": getattr(msg, 'phoneNumber', ''),
                        "display_number": getattr(msg, 'displayNumber', ''),
                        "time": getattr(msg, 'displayStartDateTime', ''),
                        "duration": getattr(msg, 'duration', 0)
                    })
            
            if call_type in ["received", "all"]:
                self.voice.received()
                for msg in self.voice.received.messages:
                    calls.append({
                        "id": msg.id,
                        "type": "received",
                        "phone_number": getattr(msg, 'phoneNumber', ''),
                        "display_number": getattr(msg, 'displayNumber', ''),
                        "time": getattr(msg, 'displayStartDateTime', ''),
                        "duration": getattr(msg, 'duration', 0)
                    })
            
            if call_type in ["missed", "all"]:
                self.voice.missed()
                for msg in self.voice.missed.messages:
                    calls.append({
                        "id": msg.id,
                        "type": "missed",
                        "phone_number": getattr(msg, 'phoneNumber', ''),
                        "display_number": getattr(msg, 'displayNumber', ''),
                        "time": getattr(msg, 'displayStartDateTime', '')
                    })
            
            return calls
        except Exception as e:
            gv_logger.error(f"Failed to get call history: {e}")
            return []


# Cache for dialer instances (per user)
_dialer_cache = {}

async def get_user_dialer(user_id: str) -> tuple:
    """
    Get or create a CredlocityDialer instance for the user
    Returns: (dialer, gv_settings, error_message)
    """
    global _dialer_cache
    
    # Get user's Google Voice settings
    gv_settings = await db.google_voice_settings.find_one({"user_id": user_id}, {"_id": 0})
    
    if not gv_settings:
        return None, None, "Google Voice not configured. Please set up your credentials in Settings."
    
    if not gv_settings.get("is_enabled"):
        return None, gv_settings, "Google Voice is disabled in your settings."
    
    email = gv_settings.get("gv_email", "")
    password = simple_decrypt(gv_settings.get("gv_password_encrypted", ""))
    
    if not email or not password:
        return None, gv_settings, "Google Voice credentials incomplete. Please update your settings."
    
    # Check cache
    cache_key = f"{user_id}:{email}"
    if cache_key in _dialer_cache:
        dialer = _dialer_cache[cache_key]
        if dialer.is_connected:
            return dialer, gv_settings, None
    
    # Create new dialer
    dialer = CredlocityDialer(email, password)
    success, error = await dialer.connect()
    
    if success:
        _dialer_cache[cache_key] = dialer
        # Update successful login time
        await db.google_voice_settings.update_one(
            {"user_id": user_id},
            {"$set": {
                "last_successful_login": datetime.now(timezone.utc).isoformat(),
                "login_error": None
            }}
        )
        return dialer, gv_settings, None
    else:
        # Update error
        await db.google_voice_settings.update_one(
            {"user_id": user_id},
            {"$set": {
                "login_error": error,
                "last_login_attempt": datetime.now(timezone.utc).isoformat()
            }}
        )
        return None, gv_settings, error


async def get_user_google_voice_client(user_id: str):
    """Legacy function - Initialize Google Voice client using the user's stored credentials"""
    dialer, gv_settings, error = await get_user_dialer(user_id)
    
    if dialer and dialer.is_connected:
        forwarding = gv_settings.get("forwarding_number", "") if gv_settings else ""
        return dialer.voice, forwarding
    
    # Fallback to environment credentials
    if GOOGLE_VOICE_EMAIL_FALLBACK and GOOGLE_VOICE_PASSWORD_FALLBACK:
        try:
            from googlevoice import Voice
            voice = Voice()
            voice.login(GOOGLE_VOICE_EMAIL_FALLBACK, GOOGLE_VOICE_PASSWORD_FALLBACK)
            return voice, os.environ.get("GOOGLE_VOICE_FORWARDING_NUMBER", "")
        except Exception as e:
            gv_logger.error(f"Fallback login failed: {e}")
    
    return None, ""


# ==================== GOOGLE VOICE SETTINGS ENDPOINTS ====================

@collections_router.get("/google-voice/settings")
async def get_google_voice_settings(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get the current user's Google Voice settings"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    settings = await db.google_voice_settings.find_one({"user_id": user["id"]}, {"_id": 0})
    
    if not settings:
        return {
            "is_configured": False,
            "is_enabled": False,
            "gv_email": None,
            "gv_number": None,
            "forwarding_number": None,
            "last_successful_login": None,
            "login_error": None
        }
    
    # Don't return the encrypted password
    return {
        "is_configured": True,
        "is_enabled": settings.get("is_enabled", False),
        "gv_email": settings.get("gv_email"),
        "gv_number": settings.get("gv_number"),
        "forwarding_number": settings.get("forwarding_number"),
        "last_successful_login": settings.get("last_successful_login"),
        "login_error": settings.get("login_error"),
        "updated_at": settings.get("updated_at")
    }


@collections_router.post("/google-voice/settings")
async def save_google_voice_settings(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Save Google Voice settings for the current user"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    gv_email = data.get("gv_email", "").strip()
    gv_password = data.get("gv_password", "").strip()
    gv_number = data.get("gv_number", "").strip()
    forwarding_number = data.get("forwarding_number", "").strip()
    is_enabled = data.get("is_enabled", True)
    
    if not gv_email:
        raise HTTPException(status_code=400, detail="Google Voice email is required")
    
    # Encrypt password for storage
    encrypted_password = simple_encrypt(gv_password) if gv_password else None
    
    settings = {
        "user_id": user["id"],
        "gv_email": gv_email,
        "gv_number": gv_number,
        "forwarding_number": forwarding_number,
        "is_enabled": is_enabled,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Only update password if provided
    if encrypted_password:
        settings["gv_password_encrypted"] = encrypted_password
    
    # Check if settings already exist
    existing = await db.google_voice_settings.find_one({"user_id": user["id"]})
    
    if existing:
        await db.google_voice_settings.update_one(
            {"user_id": user["id"]},
            {"$set": settings}
        )
    else:
        settings["id"] = str(uuid4())
        settings["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.google_voice_settings.insert_one(settings)
    
    return {
        "success": True,
        "message": "Google Voice settings saved successfully"
    }


@collections_router.post("/google-voice/test-connection")
async def test_google_voice_connection(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Test Google Voice credentials without saving"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    gv_email = data.get("gv_email", "").strip()
    gv_password = data.get("gv_password", "").strip()
    
    if not gv_email or not gv_password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    
    # Use CredlocityDialer for better error handling
    dialer = CredlocityDialer(gv_email, gv_password)
    success, error_or_msg = await dialer.connect()
    
    if success:
        return {
            "success": True,
            "message": "Successfully connected to Google Voice!",
            "authenticated": True,
            "help": None
        }
    else:
        # Provide helpful troubleshooting info
        help_text = None
        if "404" in str(error_or_msg):
            help_text = "The HTTP 404 error typically indicates an authentication problem. Google Voice uses an unofficial API that may require special setup:\n\n1. If you have 2-Step Verification enabled, you MUST use an App Password\n2. Go to myaccount.google.com → Security → App passwords\n3. Generate a new App Password for 'Mail' or 'Other'\n4. Use that 16-character password instead of your regular password\n\nNote: Google may have also updated their login flow which can break third-party access."
        elif "401" in str(error_or_msg) or "Unauthorized" in str(error_or_msg):
            help_text = "Invalid credentials. If you have 2-Step Verification, use an App Password instead of your regular password."
        
        return {
            "success": False,
            "message": str(error_or_msg),
            "authenticated": False,
            "error": str(error_or_msg),
            "help": help_text
        }


@collections_router.delete("/google-voice/settings")
async def delete_google_voice_settings(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Delete the current user's Google Voice settings"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    result = await db.google_voice_settings.delete_one({"user_id": user["id"]})
    
    if result.deleted_count > 0:
        return {"success": True, "message": "Google Voice settings deleted"}
    else:
        return {"success": True, "message": "No settings to delete"}


# ==================== ADMIN GOOGLE VOICE MANAGEMENT ====================

@collections_router.get("/admin/google-voice/all-settings")
async def get_all_google_voice_settings(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Admin: Get Google Voice settings status for all employees"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if user.get("role") not in ["admin", "director", "collections_manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get all employees
    employees = await db.collections_employees.find({"is_active": True}, {"_id": 0, "password_hash": 0}).to_list(None)
    
    # Get all GV settings
    gv_settings = await db.google_voice_settings.find({}, {"_id": 0, "gv_password_encrypted": 0}).to_list(None)
    gv_settings_map = {s["user_id"]: s for s in gv_settings}
    
    result = []
    for emp in employees:
        gv = gv_settings_map.get(emp["id"], {})
        result.append({
            "employee_id": emp["id"],
            "employee_name": emp.get("full_name"),
            "employee_email": emp.get("email"),
            "employee_role": emp.get("role"),
            "gv_configured": bool(gv),
            "gv_enabled": gv.get("is_enabled", False),
            "gv_email": gv.get("gv_email"),
            "gv_number": gv.get("gv_number"),
            "last_successful_login": gv.get("last_successful_login"),
            "login_error": gv.get("login_error")
        })
    
    return {
        "employees": result,
        "total": len(result),
        "configured_count": sum(1 for r in result if r["gv_configured"]),
        "enabled_count": sum(1 for r in result if r["gv_enabled"])
    }


# ==================== DIALPAD & DIALER ENDPOINTS ====================

@collections_router.get("/dialer/status")
async def get_dialer_status(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get the current user's Google Voice dialer status"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    dialer, gv_settings, error = await get_user_dialer(user["id"])
    
    return {
        "is_configured": gv_settings is not None,
        "is_connected": dialer is not None and dialer.is_connected,
        "is_enabled": gv_settings.get("is_enabled", False) if gv_settings else False,
        "gv_email": gv_settings.get("gv_email") if gv_settings else None,
        "gv_number": gv_settings.get("gv_number") if gv_settings else None,
        "forwarding_number": gv_settings.get("forwarding_number") if gv_settings else None,
        "error": error,
        "last_successful_login": gv_settings.get("last_successful_login") if gv_settings else None
    }


@collections_router.post("/dialer/call")
async def dialer_make_call(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """
    Initiate a call via the dialpad
    Uses the CredlocityDialer class for better handling
    """
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    phone_number = data.get("phone_number", "").strip()
    account_id = data.get("account_id")  # Optional - for CRM logging
    
    if not phone_number:
        raise HTTPException(status_code=400, detail="Phone number is required")
    
    # Clean and format phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) == 10:
        clean_phone = "1" + clean_phone
    elif len(clean_phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    
    formatted_phone = f"+{clean_phone}"
    
    # Get user's dialer
    dialer, gv_settings, error = await get_user_dialer(user["id"])
    
    if not dialer:
        return {
            "success": False,
            "call_initiated": False,
            "message": error or "Google Voice not configured",
            "needs_setup": gv_settings is None,
            "phone_number": formatted_phone
        }
    
    # Get forwarding number
    forwarding = gv_settings.get("forwarding_number", "") if gv_settings else ""
    
    # Make the call
    result = dialer.make_call(formatted_phone, forwarding if forwarding else None)
    
    # Log to database
    call_log = {
        "id": str(uuid4()),
        "user_id": user["id"],
        "user_name": user.get("full_name"),
        "account_id": account_id,
        "phone_number": formatted_phone,
        "direction": "outbound",
        "type": "call",
        "status": "initiated" if result["success"] else "failed",
        "gv_status": "success" if result["success"] else result.get("error", "failed"),
        "error_message": result.get("error") if not result["success"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_call_logs.insert_one(call_log)
    
    # Update daily compliance if account_id provided
    if account_id and result["success"]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.collections_daily_compliance.update_one(
            {"account_id": account_id, "date": today},
            {
                "$inc": {"calls_completed": 1},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                "$setOnInsert": {
                    "id": str(uuid4()),
                    "texts_completed": 0,
                    "emails_completed": 0,
                    "compliance_met": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
    
    return {
        "success": result["success"],
        "call_initiated": result["success"],
        "message": result.get("message") or result.get("error"),
        "phone_number": formatted_phone,
        "call_log_id": call_log["id"]
    }


@collections_router.post("/dialer/sms")
async def dialer_send_sms(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """
    Send SMS via the dialpad
    Uses the CredlocityDialer class for better handling
    """
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    phone_number = data.get("phone_number", "").strip()
    message = data.get("message", "").strip()
    account_id = data.get("account_id")  # Optional - for CRM logging
    
    if not phone_number:
        raise HTTPException(status_code=400, detail="Phone number is required")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if len(message) < 10:
        raise HTTPException(status_code=400, detail="Message must be at least 10 characters")
    
    # Clean and format phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) == 10:
        clean_phone = "1" + clean_phone
    
    formatted_phone = f"+{clean_phone}"
    
    # Get user's dialer
    dialer, gv_settings, error = await get_user_dialer(user["id"])
    
    if not dialer:
        return {
            "success": False,
            "sms_sent": False,
            "message": error or "Google Voice not configured",
            "needs_setup": gv_settings is None,
            "phone_number": formatted_phone
        }
    
    # Send SMS
    result = dialer.send_sms(formatted_phone, message)
    
    # Log to database
    sms_log = {
        "id": str(uuid4()),
        "user_id": user["id"],
        "user_name": user.get("full_name"),
        "account_id": account_id,
        "phone_number": formatted_phone,
        "direction": "outbound",
        "type": "sms",
        "message": message,
        "message_length": len(message),
        "segments": (len(message) // 160) + 1,
        "status": "sent" if result["success"] else "failed",
        "gv_status": "success" if result["success"] else result.get("error", "failed"),
        "error_message": result.get("error") if not result["success"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_sms_logs.insert_one(sms_log)
    
    # Update daily compliance if account_id provided
    if account_id and result["success"]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.collections_daily_compliance.update_one(
            {"account_id": account_id, "date": today},
            {
                "$inc": {"texts_completed": 1},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                "$setOnInsert": {
                    "id": str(uuid4()),
                    "calls_completed": 0,
                    "emails_completed": 0,
                    "compliance_met": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
    
    return {
        "success": result["success"],
        "sms_sent": result["success"],
        "message": result.get("message") or result.get("error"),
        "phone_number": formatted_phone,
        "sms_log_id": sms_log["id"]
    }


@collections_router.get("/dialer/history")
async def get_dialer_history(
    limit: int = 50,
    type: str = "all",
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """Get call and SMS history for the current user"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    history = []
    
    # Get call logs
    if type in ["all", "call"]:
        calls = await db.collections_call_logs.find(
            {"user_id": user["id"]},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        history.extend(calls)
    
    # Get SMS logs
    if type in ["all", "sms"]:
        sms = await db.collections_sms_logs.find(
            {"user_id": user["id"]},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        history.extend(sms)
    
    # Sort by timestamp
    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    return {
        "history": history[:limit],
        "total": len(history)
    }


@collections_router.get("/dialer/sync-gv-history")
async def sync_google_voice_history(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """
    Sync call and SMS history from Google Voice
    Fetches recent calls and messages from GV and stores them
    """
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    dialer, gv_settings, error = await get_user_dialer(user["id"])
    
    if not dialer:
        return {
            "success": False,
            "message": error or "Google Voice not configured",
            "synced": {"calls": 0, "sms": 0}
        }
    
    synced_calls = 0
    synced_sms = 0
    
    try:
        # Sync calls
        calls = dialer.get_call_history("all")
        for call in calls:
            # Check if already synced
            existing = await db.collections_call_logs.find_one({
                "gv_id": call.get("id"),
                "user_id": user["id"]
            })
            if not existing and call.get("id"):
                await db.collections_call_logs.insert_one({
                    "id": str(uuid4()),
                    "gv_id": call.get("id"),
                    "user_id": user["id"],
                    "user_name": user.get("full_name"),
                    "phone_number": call.get("phone_number") or call.get("display_number"),
                    "direction": "outbound" if call.get("type") == "placed" else "inbound",
                    "type": "call",
                    "call_type": call.get("type"),
                    "duration": call.get("duration", 0),
                    "status": "completed",
                    "gv_status": "synced",
                    "timestamp": call.get("time") or datetime.now(timezone.utc).isoformat(),
                    "synced_from_gv": True,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                synced_calls += 1
        
        # Sync SMS
        messages = dialer.get_sms_history()
        for msg in messages:
            existing = await db.collections_sms_logs.find_one({
                "gv_id": msg.get("id"),
                "user_id": user["id"]
            })
            if not existing and msg.get("id"):
                await db.collections_sms_logs.insert_one({
                    "id": str(uuid4()),
                    "gv_id": msg.get("id"),
                    "user_id": user["id"],
                    "user_name": user.get("full_name"),
                    "phone_number": msg.get("phone_number") or msg.get("display_number"),
                    "direction": "inbound",  # SMS history from GV is typically received
                    "type": "sms",
                    "message": msg.get("text", ""),
                    "is_read": msg.get("is_read", False),
                    "status": "received",
                    "gv_status": "synced",
                    "timestamp": msg.get("time") or datetime.now(timezone.utc).isoformat(),
                    "synced_from_gv": True,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                synced_sms += 1
        
        return {
            "success": True,
            "message": f"Synced {synced_calls} calls and {synced_sms} SMS messages",
            "synced": {"calls": synced_calls, "sms": synced_sms}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "synced": {"calls": synced_calls, "sms": synced_sms}
        }


# ==================== CALL & SMS ENDPOINTS (Updated for Per-User Auth) ====================

@collections_router.post("/call")
async def make_call(data: dict, token: str = None, authorization: Optional[str] = Header(None)):
    """Initiate a call via Google Voice using the rep's own credentials"""
    
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    account_id = data.get("account_id")
    phone_number = data.get("phone_number")
    
    if not phone_number:
        raise HTTPException(status_code=400, detail="Phone number required")
    
    # Clean phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) == 10:
        clean_phone = "1" + clean_phone
    clean_phone = "+" + clean_phone
    
    # Get the user's Google Voice client
    voice, forwarding_number = await get_user_google_voice_client(user["id"])
    call_initiated = False
    gv_status = "not_configured"
    
    if voice:
        try:
            if forwarding_number:
                voice.call(clean_phone, forwarding_number)
            else:
                # If no forwarding number, still try to initiate
                voice.call(clean_phone)
            call_initiated = True
            gv_status = "success"
        except Exception as e:
            print(f"Call failed: {e}")
            gv_status = f"error: {str(e)}"
    
    # Log the call attempt
    if account_id:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Get current compliance count
        compliance = await db.collections_daily_compliance.find_one({
            "account_id": account_id,
            "date": today
        })
        
        call_number = (compliance.get("calls_completed", 0) if compliance else 0) + 1
        
        if call_number <= 3:
            # Create contact record
            contact = {
                "id": str(uuid4()),
                "account_id": account_id,
                "contact_date": today,
                "contact_type": "call",
                "contact_number": call_number,
                "contact_time": datetime.now(timezone.utc).isoformat(),
                "outcome": "Call initiated via Google Voice" if call_initiated else "Call logged (manual dial required)",
                "gv_status": gv_status,
                "completed_by_rep_id": user.get("id"),
                "completed_by_rep_name": user.get("full_name"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.collections_contacts.insert_one(contact)
            
            # Update compliance
            await db.collections_daily_compliance.update_one(
                {"account_id": account_id, "date": today},
                {
                    "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                    "$inc": {"calls_completed": 1},
                    "$setOnInsert": {
                        "id": str(uuid4()),
                        "texts_completed": 0,
                        "emails_completed": 0,
                        "compliance_met": False,
                        "auto_note_generated": False,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
    
    return {
        "success": True,
        "call_initiated": call_initiated,
        "gv_status": gv_status,
        "message": "Call initiated! Your phone will ring." if call_initiated else "Call logged. Please configure Google Voice settings or dial manually."
    }


@collections_router.post("/sms")
async def send_sms(data: dict, token: str = None, authorization: Optional[str] = Header(None)):
    """Send SMS via Google Voice using the rep's own credentials"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    account_id = data.get("account_id")
    phone_number = data.get("phone_number")
    message = data.get("message", "")
    
    if not phone_number or not message:
        raise HTTPException(status_code=400, detail="Phone number and message required")
    
    if len(message) < 10:
        raise HTTPException(status_code=400, detail="Message must be at least 10 characters")
    
    # Clean phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) == 10:
        clean_phone = "1" + clean_phone
    clean_phone = "+" + clean_phone
    
    # Get the user's Google Voice client
    voice, _ = await get_user_google_voice_client(user["id"])
    sms_sent = False
    gv_status = "not_configured"
    
    if voice:
        try:
            voice.send_sms(clean_phone, message)
            sms_sent = True
            gv_status = "success"
        except Exception as e:
            print(f"SMS failed: {e}")
            gv_status = f"error: {str(e)}"
    
    # Log the SMS
    if account_id:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Get current compliance count
        compliance = await db.collections_daily_compliance.find_one({
            "account_id": account_id,
            "date": today
        })
        
        text_number = (compliance.get("texts_completed", 0) if compliance else 0) + 1
        
        if text_number <= 3:
            # Create contact record
            contact = {
                "id": str(uuid4()),
                "account_id": account_id,
                "contact_date": today,
                "contact_type": "text",
                "contact_number": text_number,
                "contact_time": datetime.now(timezone.utc).isoformat(),
                "outcome": f"SMS sent: {message[:100]}..." if len(message) > 100 else f"SMS sent: {message}",
                "gv_status": gv_status,
                "completed_by_rep_id": user.get("id"),
                "completed_by_rep_name": user.get("full_name"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.collections_contacts.insert_one(contact)
            
            # Update compliance
            new_texts = text_number
            compliance_data = await db.collections_daily_compliance.find_one({"account_id": account_id, "date": today})
            calls = compliance_data.get("calls_completed", 0) if compliance_data else 0
            emails = compliance_data.get("emails_completed", 0) if compliance_data else 0
            compliance_met = calls >= 3 and new_texts >= 3 and emails >= 3
            
            await db.collections_daily_compliance.update_one(
                {"account_id": account_id, "date": today},
                {
                    "$set": {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "compliance_met": compliance_met
                    },
                    "$inc": {"texts_completed": 1},
                    "$setOnInsert": {
                        "id": str(uuid4()),
                        "calls_completed": 0,
                        "emails_completed": 0,
                        "auto_note_generated": False,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
            
            # Check for auto-compliance note
            if compliance_met:
                await check_and_generate_compliance_note(account_id, today, user)
    
    return {
        "success": True,
        "sms_sent": sms_sent,
        "message": "SMS sent successfully!" if sms_sent else "SMS logged. Manual send may be required."
    }

async def check_and_generate_compliance_note(account_id: str, date: str, user: dict):
    """Generate auto-compliance note when 3/3/3 is reached"""
    compliance = await db.collections_daily_compliance.find_one({
        "account_id": account_id,
        "date": date
    })
    
    if compliance and compliance.get("compliance_met") and not compliance.get("auto_note_generated"):
        note = {
            "id": str(uuid4()),
            "account_id": account_id,
            "note_type": "auto_compliance",
            "note_text": f"""[Auto-Generated Entry - {datetime.now(timezone.utc).strftime('%m/%d/%Y %I:%M %p')}]
Minimum contact made per Credlocity Collection Policies.
Calls: 3/3 | Texts: 3/3 | Emails: 3/3
Status: Compliance Met ✓""",
            "created_by_rep_id": user.get("id"),
            "created_by_rep_name": user.get("full_name"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.notes.insert_one(note)
        
        await db.collections_daily_compliance.update_one(
            {"account_id": account_id, "date": date},
            {"$set": {"auto_note_generated": True}}
        )



# ==================== SERVICE PLANS (Available for Invoice-Style Account Creation) ====================

@collections_router.get("/service-plans")
async def get_service_plans(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get available service plans for account creation"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Default plans - can be extended via database
    default_plans = [
        {"id": "individual", "name": "Individual Plan", "default_price": 179.95, "type": "credit_repair"},
        {"id": "couple", "name": "Couple/Family Plan", "default_price": 279.95, "type": "credit_repair"},
        {"id": "legacy_individual", "name": "Legacy Individual", "default_price": 119.95, "type": "credit_repair"},
        {"id": "credit_monitoring_3b", "name": "Credit Monitoring (3B Reports)", "default_price": 29.95, "type": "credit_monitoring"},
        {"id": "credit_monitoring_partner", "name": "Credit Monitoring (Partner)", "default_price": 19.95, "type": "credit_monitoring"},
        {"id": "custom", "name": "Custom Plan", "default_price": 0, "type": "custom"}
    ]
    
    # Get any custom plans from database
    db_plans = await db.collections_service_plans.find({"is_active": True}, {"_id": 0}).to_list(None)
    
    return {"plans": default_plans + db_plans}


# ==================== INVOICE-STYLE ACCOUNT CREATION ====================

@collections_router.post("/accounts/invoice")
async def create_account_invoice_style(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Create a collections account with invoice-style line items"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate required fields
    if not data.get("client_name"):
        raise HTTPException(status_code=400, detail="Client name is required")
    if not data.get("first_failed_payment_date"):
        raise HTTPException(status_code=400, detail="First failed payment date is required")
    
    first_failed = data.get("first_failed_payment_date")
    days_past_due = calculate_days_past_due(first_failed)
    current_tier = get_tier_from_days(days_past_due)
    
    # Line items from invoice
    line_items = data.get("line_items", [])
    
    # Calculate totals from line items
    total_balance = 0
    line_item_records = []
    
    for item in line_items:
        item_total = float(item.get("amount", 0)) * int(item.get("quantity", 1))
        total_balance += item_total
        line_item_records.append({
            "id": str(uuid4()),
            "item_type": item.get("item_type"),  # plan, late_fee, collection_fee, payment_processing, file_processing
            "description": item.get("description", ""),
            "amount": float(item.get("amount", 0)),
            "quantity": int(item.get("quantity", 1)),
            "total": item_total,
            "is_waivable": item.get("is_waivable", False),
            "processing_source": item.get("processing_source"),  # collection_department, collection_agency
        })
    
    account = {
        "id": str(uuid4()),
        "client_id": data.get("client_id"),
        "client_name": data.get("client_name", ""),
        "client_email": data.get("client_email"),
        "client_phone": data.get("client_phone"),
        "client_address": data.get("client_address"),
        "client_city": data.get("client_city"),
        "client_state": data.get("client_state"),
        "client_zip": data.get("client_zip"),
        "ssn_last_4": data.get("ssn_last_4"),
        # Plan info
        "plan_id": data.get("plan_id"),
        "plan_name": data.get("plan_name"),
        "plan_type": data.get("plan_type"),  # credit_repair, credit_monitoring, custom
        "monthly_rate": float(data.get("monthly_rate", 0)),
        # Dates
        "first_failed_payment_date": first_failed,
        "days_past_due": days_past_due,
        "current_tier": current_tier,
        # Financials
        "past_due_balance": total_balance,
        "original_balance": total_balance,
        "line_items": line_item_records,
        # Status
        "account_status": "active",
        "assigned_rep_id": data.get("assigned_rep_id", user["id"]),
        "assigned_rep_name": data.get("assigned_rep_name", user["full_name"]),
        "notes_count": 0,
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.collections_accounts.insert_one(account)
    
    # Build line items summary for note
    items_summary = ", ".join([f"{item['description']}: ${item['total']:.2f}" for item in line_item_records])
    
    note = {
        "id": str(uuid4()),
        "account_id": account["id"],
        "note_type": "system",
        "note_text": f"Account created (Invoice Style). Tier {current_tier} ({days_past_due} days past due). Balance: ${total_balance:.2f}. Line items: {items_summary}",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    account.pop("_id", None)
    return account


# ==================== APPROVAL QUEUE SYSTEM ====================

@collections_router.post("/approval-requests")
async def create_approval_request(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Create an approval request for settlement/waiver"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    account_id = data.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="Account ID is required")
    
    account = await db.collections_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    request_type = data.get("request_type")  # tier_approval, waiver_approval, discount_approval
    
    # Determine required approval level
    tier = data.get("tier_requested", account.get("current_tier", 1))
    tier_info = get_tier_info(tier)
    required_role = tier_info.get("approval_required") or "team_leader"
    
    approval_request = {
        "id": str(uuid4()),
        "account_id": account_id,
        "client_name": account.get("client_name"),
        "request_type": request_type,
        "tier_requested": tier,
        "tier_name": tier_info.get("name"),
        # Financial details
        "original_balance": data.get("original_balance", account.get("past_due_balance", 0)),
        "proposed_settlement_amount": data.get("proposed_settlement_amount", 0),
        "discount_amount": data.get("discount_amount", 0),
        "discount_percentage": data.get("discount_percentage", 0),
        # Waiver details
        "waiver_type": data.get("waiver_type"),  # collection_fee, late_fees, file_processing, multiple
        "waiver_amount": data.get("waiver_amount", 0),
        "waiver_details": data.get("waiver_details", []),  # List of {type, original, waived, remaining}
        # Metadata
        "reason": data.get("reason", ""),
        "required_role": required_role,
        "status": "pending",
        "requested_by_id": user["id"],
        "requested_by_name": user["full_name"],
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "approved_by_id": None,
        "approved_by_name": None,
        "approved_at": None,
        "rejection_reason": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.approval_requests.insert_one(approval_request)
    
    # Add note to account
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "note_type": "approval_request",
        "note_text": f"Approval request submitted by {user['full_name']}. Type: {request_type}. Tier: {tier_info.get('name')}. Amount: ${data.get('waiver_amount', 0):.2f}",
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    approval_request.pop("_id", None)
    return approval_request


@collections_router.get("/approval-queue")
async def get_approval_queue(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    status: Optional[str] = "pending",
    request_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get approval queue - All managers see all pending approvals"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Only team_leader and above can view approval queue
    if user["role"] not in ["team_leader", "collections_manager", "director", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to view approval queue")
    
    query = {}
    if status:
        query["status"] = status
    if request_type:
        query["request_type"] = request_type
    
    requests = await db.approval_requests.find(query, {"_id": 0}).sort("requested_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.approval_requests.count_documents(query)
    
    # Add requester info and account details
    for req in requests:
        account = await db.collections_accounts.find_one({"id": req["account_id"]}, {"_id": 0, "client_name": 1, "past_due_balance": 1, "days_past_due": 1})
        req["account_info"] = account
    
    return {"requests": requests, "total": total, "skip": skip, "limit": limit}


@collections_router.put("/approval-requests/{request_id}")
async def process_approval_request(request_id: str, data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Approve or reject an approval request"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    approval_request = await db.approval_requests.find_one({"id": request_id})
    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    if approval_request["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request has already been processed")
    
    # Check user has required role
    required_role = approval_request.get("required_role", "team_leader")
    role_hierarchy = ["collections_agent", "team_leader", "collections_manager", "director", "admin"]
    user_level = role_hierarchy.index(user["role"]) if user["role"] in role_hierarchy else -1
    required_level = role_hierarchy.index(required_role) if required_role in role_hierarchy else 1
    
    if user_level < required_level:
        raise HTTPException(status_code=403, detail=f"Requires {required_role} or higher to process this request")
    
    action = data.get("action")  # approve, reject
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    update_data = {
        "status": "approved" if action == "approve" else "rejected",
        "approved_by_id": user["id"],
        "approved_by_name": user["full_name"],
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if action == "reject":
        update_data["rejection_reason"] = data.get("rejection_reason", "")
    
    await db.approval_requests.update_one({"id": request_id}, {"$set": update_data})
    
    # If approved, track waivers
    if action == "approve" and approval_request.get("waiver_details"):
        for waiver in approval_request.get("waiver_details", []):
            waiver_record = {
                "id": str(uuid4()),
                "account_id": approval_request["account_id"],
                "approval_request_id": request_id,
                "waiver_type": waiver.get("type"),
                "original_amount": waiver.get("original", 0),
                "waived_amount": waiver.get("waived", 0),
                "remaining_amount": waiver.get("remaining", 0),
                "requested_by_id": approval_request["requested_by_id"],
                "requested_by_name": approval_request["requested_by_name"],
                "requested_at": approval_request["requested_at"],
                "approved_by_id": user["id"],
                "approved_by_name": user["full_name"],
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.waiver_history.insert_one(waiver_record)
    
    # Add note to account
    account_id = approval_request["account_id"]
    note = {
        "id": str(uuid4()),
        "account_id": account_id,
        "note_type": "approval_response",
        "note_text": f"Approval request {action}d by {user['full_name']}. Type: {approval_request['request_type']}. " + 
                    (f"Rejection reason: {data.get('rejection_reason', 'N/A')}" if action == "reject" else f"Waiver amount approved: ${approval_request.get('waiver_amount', 0):.2f}"),
        "created_by_id": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.collections_notes.insert_one(note)
    
    updated = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    return updated


@collections_router.get("/approval-requests/{request_id}")
async def get_approval_request(request_id: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get a specific approval request"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    request = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    # Get account info
    account = await db.collections_accounts.find_one({"id": request["account_id"]}, {"_id": 0})
    request["account"] = account
    
    return request


# ==================== WAIVER TRACKING & KPIs ====================

@collections_router.get("/waiver-history")
async def get_waiver_history(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    rep_id: Optional[str] = None,
    account_id: Optional[str] = None,
    waiver_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
):
    """Get waiver history with filters"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query = {}
    if rep_id:
        query["requested_by_id"] = rep_id
    if account_id:
        query["account_id"] = account_id
    if waiver_type:
        query["waiver_type"] = waiver_type
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    waivers = await db.waiver_history.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.waiver_history.count_documents(query)
    
    return {"waivers": waivers, "total": total}


@collections_router.get("/waiver-kpis")
async def get_waiver_kpis(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    rep_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get waiver KPI metrics"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Only managers can see all KPIs, agents see only their own
    if user["role"] not in ["team_leader", "collections_manager", "director", "admin"] and not rep_id:
        rep_id = user["id"]
    
    # Build query
    waiver_query = {}
    request_query = {}
    
    if rep_id:
        waiver_query["requested_by_id"] = rep_id
        request_query["requested_by_id"] = rep_id
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date
        waiver_query["created_at"] = date_filter
        request_query["requested_at"] = date_filter
    
    # Get waiver stats
    waivers = await db.waiver_history.find(waiver_query, {"_id": 0}).to_list(None)
    
    total_waivers_requested = len(waivers)
    total_amount_waived = sum(w.get("waived_amount", 0) for w in waivers)
    
    # Breakdown by type
    by_type = {}
    for w in waivers:
        wtype = w.get("waiver_type", "unknown")
        if wtype not in by_type:
            by_type[wtype] = {"count": 0, "total_waived": 0}
        by_type[wtype]["count"] += 1
        by_type[wtype]["total_waived"] += w.get("waived_amount", 0)
    
    # Get approval request stats
    approved_count = await db.approval_requests.count_documents({**request_query, "status": "approved"})
    rejected_count = await db.approval_requests.count_documents({**request_query, "status": "rejected"})
    pending_count = await db.approval_requests.count_documents({**request_query, "status": "pending"})
    
    total_requests = approved_count + rejected_count + pending_count
    approval_rate = (approved_count / total_requests * 100) if total_requests > 0 else 0
    
    # Get rep leaderboard (if no specific rep)
    leaderboard = []
    if not rep_id:
        pipeline = [
            {"$match": waiver_query} if waiver_query else {"$match": {}},
            {"$group": {
                "_id": "$requested_by_id",
                "rep_name": {"$first": "$requested_by_name"},
                "total_waivers": {"$sum": 1},
                "total_amount_waived": {"$sum": "$waived_amount"}
            }},
            {"$sort": {"total_amount_waived": -1}},
            {"$limit": 10}
        ]
        leaderboard = await db.waiver_history.aggregate(pipeline).to_list(None)
    
    return {
        "summary": {
            "total_waivers_requested": total_waivers_requested,
            "total_amount_waived": total_amount_waived,
            "approval_requests": {
                "approved": approved_count,
                "rejected": rejected_count,
                "pending": pending_count,
                "approval_rate": round(approval_rate, 2)
            }
        },
        "by_type": by_type,
        "leaderboard": leaderboard
    }


# ==================== COMMISSION CALCULATION (Updated per Handbook) ====================

@collections_router.post("/commission/calculate")
async def calculate_commission_preview(data: dict, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Calculate commission preview for a settlement - Collection Fee 100% to rep + handbook %"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    tier = data.get("tier", 3)
    tier_info = get_tier_info(tier)
    payment_type = data.get("payment_type", "plan")  # full or plan
    
    # Amounts
    collected_amount = data.get("collected_amount", 0)
    collection_fee_kept = data.get("collection_fee_kept", 350.00)  # Rep keeps 100% of what they don't waive
    down_payment = data.get("down_payment_amount", 0)
    remaining_balance = data.get("remaining_balance", 0)
    
    commission = {
        "tier": tier,
        "tier_name": tier_info["name"],
        "payment_type": payment_type,
        "collection_fee_kept": collection_fee_kept,
        "collection_fee_note": "100% yours to keep (minus any waived amount)"
    }
    
    if payment_type == "full":
        # Full payment: Collection Fee + X% of collected
        base_commission = collected_amount * (tier_info["commission_full"] / 100)
        bonus_48hr = collected_amount * (tier_info.get("bonus_48hr", 0) / 100)
        
        commission["base_commission"] = round(base_commission, 2)
        commission["base_commission_rate"] = tier_info["commission_full"]
        commission["bonus_48hr"] = round(bonus_48hr, 2)
        commission["bonus_48hr_note"] = "If paid within 48 hours" if bonus_48hr > 0 else None
        commission["total_commission"] = round(collection_fee_kept + base_commission, 2)
        commission["total_with_bonus"] = round(collection_fee_kept + base_commission + bonus_48hr, 2)
        
    else:
        # Payment plan: Collection Fee + 5% down + 3% monthly + 2% completion
        down_commission = down_payment * 0.05  # 5% of down payment
        monthly_commission = remaining_balance * 0.03  # 3% of monthly payments
        completion_bonus = collected_amount * 0.02  # 2% completion bonus
        
        commission["down_payment_commission"] = round(down_commission, 2)
        commission["down_payment_rate"] = 5
        commission["monthly_commission"] = round(monthly_commission, 2)
        commission["monthly_rate"] = 3
        commission["completion_bonus"] = round(completion_bonus, 2)
        commission["completion_rate"] = 2
        commission["completion_note"] = "Earned when plan is fully paid"
        
        # Immediate earnings (on down payment)
        commission["immediate_earnings"] = round(collection_fee_kept + down_commission, 2)
        # Total potential
        commission["total_potential"] = round(collection_fee_kept + down_commission + monthly_commission + completion_bonus, 2)
    
    return commission


# ==================== REP PERFORMANCE METRICS ====================

@collections_router.get("/rep-performance/{rep_id}")
async def get_rep_performance(
    rep_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get detailed performance metrics for a rep"""
    user = await get_collections_user(token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Only managers or the rep themselves can view
    if user["role"] not in ["team_leader", "collections_manager", "director", "admin"] and user["id"] != rep_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Build date filter
    date_filter = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date
    
    # Get rep info
    rep = await db.collections_employees.find_one({"id": rep_id}, {"_id": 0, "password_hash": 0})
    if not rep:
        rep = await db.users.find_one({"id": rep_id}, {"_id": 0, "password_hash": 0})
    
    # Collections stats
    account_query = {"assigned_rep_id": rep_id}
    if date_filter:
        account_query["created_at"] = date_filter
    
    total_accounts = await db.collections_accounts.count_documents(account_query)
    
    # Payment agreements created
    agreement_query = {"created_by_rep_id": rep_id}
    if date_filter:
        agreement_query["created_at"] = date_filter
    
    agreements = await db.payment_agreements.find(agreement_query, {"_id": 0}).to_list(None)
    total_agreements = len(agreements)
    total_collected = sum(a.get("down_payment_amount", 0) for a in agreements)
    
    # Waiver stats
    waiver_query = {"requested_by_id": rep_id}
    if date_filter:
        waiver_query["created_at"] = date_filter
    
    waivers = await db.waiver_history.find(waiver_query, {"_id": 0}).to_list(None)
    total_waived = sum(w.get("waived_amount", 0) for w in waivers)
    
    # Approval requests
    request_query = {"requested_by_id": rep_id}
    if date_filter:
        request_query["requested_at"] = date_filter
    
    approved = await db.approval_requests.count_documents({**request_query, "status": "approved"})
    rejected = await db.approval_requests.count_documents({**request_query, "status": "rejected"})
    pending = await db.approval_requests.count_documents({**request_query, "status": "pending"})
    
    # Commission earned
    collection_fees_earned = sum(
        a.get("collection_fee_adjusted", 0) for a in agreements
    )
    
    return {
        "rep": rep,
        "period": {"start_date": start_date, "end_date": end_date},
        "accounts": {
            "total_assigned": total_accounts
        },
        "collections": {
            "total_agreements": total_agreements,
            "total_collected": round(total_collected, 2),
            "collection_fees_earned": round(collection_fees_earned, 2)
        },
        "waivers": {
            "total_waivers": len(waivers),
            "total_amount_waived": round(total_waived, 2)
        },
        "approvals": {
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "approval_rate": round(approved / (approved + rejected) * 100, 2) if (approved + rejected) > 0 else 0
        }
    }

