"""
Credlocity Credit Repair Company Management API
Multi-company subscription system for the attorney marketplace:
- Company registration and onboarding
- Subscription management
- Revenue tracking and splits
- Company users and permissions
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import os
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

company_router = APIRouter(prefix="/api/companies", tags=["Credit Repair Companies"])


# ==================== AUTHENTICATION ====================

async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    
    try:
        from jose import jwt
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if email:
            user = await db.users.find_one({"email": email}, {"_id": 0, "hashed_password": 0})
            if user:
                if user.get("role") == "super_admin":
                    user["role"] = "admin"
                return user
    except Exception:
        pass
    
    # Check for company user token
    company_user = await db.company_users.find_one({"token": token}, {"_id": 0, "password_hash": 0})
    if company_user:
        company_user["is_company_user"] = True
        return company_user
    
    return None


def require_admin(user):
    """Require admin authentication"""
    if not user or user.get("role") not in ["admin", "super_admin", "director"]:
        raise HTTPException(status_code=403, detail="Admin authentication required")


def require_company_user(user):
    """Require company user authentication"""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.get("is_company_user") and user.get("role") not in ["admin", "super_admin", "director"]:
        raise HTTPException(status_code=403, detail="Company user access required")


# ==================== PUBLIC COMPANY SIGNUP ====================

@company_router.post("/signup")
async def company_signup(data: dict):
    """Public endpoint for credit repair company signup"""
    # Validate required fields
    required = ["company_name", "owner_name", "email", "phone", "password"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
    
    email = data["email"].lower()
    
    # Check email uniqueness
    existing = await db.credit_repair_companies.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="A company with this email already exists")
    
    existing_user = await db.company_users.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    
    # Get default billing settings
    billing_settings = await db.billing_settings.find_one({"id": "billing_settings"})
    if not billing_settings:
        signup_fee = 500.00
        monthly_fee = 199.99
    else:
        signup_fee = billing_settings.get("company_signup_fee", 500.00)
        monthly_fee = billing_settings.get("company_monthly_fee", 199.99)
    
    # Create company
    company = {
        "id": str(uuid4()),
        "company_name": data["company_name"],
        "business_type": data.get("business_type", "credit_repair"),
        "owner_name": data["owner_name"],
        "email": email,
        "phone": data["phone"],
        "address": data.get("address"),
        "city": data.get("city"),
        "state": data.get("state"),
        "zip_code": data.get("zip_code"),
        "website": data.get("website"),
        
        # Business Details
        "years_in_business": data.get("years_in_business"),
        "clients_served": data.get("clients_served"),
        "certifications": data.get("certifications", []),
        
        # Subscription Status
        "subscription_status": "pending_payment",  # pending_payment, trial, active, past_due, cancelled, suspended
        "subscription_tier": "standard",
        
        # Fees (configurable from billing settings)
        "signup_fee_amount": signup_fee,
        "signup_fee_paid": False,
        "monthly_fee_amount": monthly_fee,
        
        # Stats
        "total_cases_submitted": 0,
        "total_cases_sold": 0,
        "total_revenue_earned": 0,
        
        # Metadata
        "signup_date": datetime.now(timezone.utc).isoformat(),
        "last_active": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.credit_repair_companies.insert_one(company)
    
    # Create owner user account
    password_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    
    owner_user = {
        "id": str(uuid4()),
        "company_id": company["id"],
        "email": email,
        "password_hash": password_hash,
        "full_name": data["owner_name"],
        "role": "owner",  # owner, admin, user
        "is_active": True,
        "token": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.company_users.insert_one(owner_user)
    
    company.pop("_id", None)
    
    return {
        "message": "Company registered successfully. Please complete payment to activate your account.",
        "company_id": company["id"],
        "signup_fee": signup_fee,
        "monthly_fee": monthly_fee,
        "next_step": "payment"
    }


@company_router.post("/login")
async def company_login(data: dict):
    """Company user login"""
    email = data.get("email", "").lower()
    password = data.get("password", "")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    user = await db.company_users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Password not set")
    
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account is deactivated")
    
    # Get company info
    company = await db.credit_repair_companies.find_one({"id": user["company_id"]}, {"_id": 0})
    
    # Check subscription status
    if company and company.get("subscription_status") == "suspended":
        raise HTTPException(status_code=403, detail="Company subscription is suspended")
    
    # Generate token
    token = str(uuid4())
    await db.company_users.update_one(
        {"id": user["id"]},
        {"$set": {"token": token, "last_login": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "company_id": user["company_id"]
        },
        "company": {
            "id": company["id"] if company else None,
            "name": company["company_name"] if company else None,
            "subscription_status": company["subscription_status"] if company else None
        }
    }


# ==================== COMPANY MANAGEMENT ====================

@company_router.get("/me")
async def get_my_company(authorization: Optional[str] = Header(None)):
    """Get current user's company details"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=404, detail="No company associated with user")
    
    company = await db.credit_repair_companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get subscription details
    subscription = await db.company_subscriptions.find_one(
        {"company_id": company_id, "status": {"$in": ["active", "trialing", "past_due"]}},
        {"_id": 0}
    )
    
    return {"company": company, "subscription": subscription}


@company_router.put("/me")
async def update_my_company(data: dict, authorization: Optional[str] = Header(None)):
    """Update current user's company details"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    # Only owner or admin can update company
    if user.get("role") not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only company owner or admin can update company details")
    
    company_id = user.get("company_id")
    
    allowed_fields = [
        "company_name", "phone", "address", "city", "state", "zip_code",
        "website", "years_in_business", "clients_served", "certifications"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.credit_repair_companies.update_one({"id": company_id}, {"$set": update_data})
    
    updated = await db.credit_repair_companies.find_one({"id": company_id}, {"_id": 0})
    return updated


# ==================== COMPANY USERS ====================

@company_router.get("/users")
async def list_company_users(authorization: Optional[str] = Header(None)):
    """List users in current company"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    company_id = user.get("company_id")
    
    users = await db.company_users.find(
        {"company_id": company_id},
        {"_id": 0, "password_hash": 0, "token": 0}
    ).to_list(None)
    
    return {"users": users}


@company_router.post("/users")
async def add_company_user(data: dict, authorization: Optional[str] = Header(None)):
    """Add a user to current company"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    # Only owner or admin can add users
    if user.get("role") not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only company owner or admin can add users")
    
    email = data.get("email", "").lower()
    
    # Check uniqueness
    existing = await db.company_users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Check company user limit
    company = await db.credit_repair_companies.find_one({"id": user.get("company_id")})
    subscription = await db.company_subscriptions.find_one({"company_id": user.get("company_id"), "status": "active"})
    
    if subscription:
        plan = await db.subscription_plans.find_one({"id": subscription.get("plan_id")})
        max_users = plan.get("max_users") if plan else 3
        if max_users:
            current_users = await db.company_users.count_documents({"company_id": user.get("company_id")})
            if current_users >= max_users:
                raise HTTPException(status_code=400, detail=f"User limit reached ({max_users} users). Upgrade your plan for more users.")
    
    # Create user
    password_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    
    new_user = {
        "id": str(uuid4()),
        "company_id": user.get("company_id"),
        "email": email,
        "password_hash": password_hash,
        "full_name": data.get("full_name"),
        "role": data.get("role", "user"),  # user, admin (owner cannot be assigned)
        "is_active": True,
        "token": None,
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.company_users.insert_one(new_user)
    
    new_user.pop("_id", None)
    new_user.pop("password_hash", None)
    
    return {"message": "User added successfully", "user": new_user}


@company_router.delete("/users/{user_id}")
async def remove_company_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Remove a user from company"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    # Only owner can remove users
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only company owner can remove users")
    
    # Cannot remove self
    if user_id == user.get("id"):
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    
    target_user = await db.company_users.find_one({"id": user_id, "company_id": user.get("company_id")})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot remove owner
    if target_user.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove company owner")
    
    await db.company_users.delete_one({"id": user_id})
    
    return {"message": "User removed successfully"}


# ==================== SUBSCRIPTION MANAGEMENT ====================

@company_router.get("/subscription")
async def get_subscription(authorization: Optional[str] = Header(None)):
    """Get current company subscription"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    company_id = user.get("company_id")
    
    subscription = await db.company_subscriptions.find_one(
        {"company_id": company_id},
        {"_id": 0}
    )
    
    if not subscription:
        # Get company for fee info
        company = await db.credit_repair_companies.find_one({"id": company_id}, {"_id": 0})
        return {
            "subscription": None,
            "signup_required": True,
            "signup_fee": company.get("signup_fee_amount", 500) if company else 500,
            "monthly_fee": company.get("monthly_fee_amount", 199.99) if company else 199.99
        }
    
    # Get plan details
    plan = await db.subscription_plans.find_one({"id": subscription.get("plan_id")}, {"_id": 0})
    
    return {"subscription": subscription, "plan": plan}


@company_router.post("/subscription/activate")
async def activate_subscription(data: dict, authorization: Optional[str] = Header(None)):
    """Activate company subscription (after payment)"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    company_id = user.get("company_id")
    plan_id = data.get("plan_id")
    
    # In production, this would verify payment first
    # For now, we'll create the subscription directly
    
    company = await db.credit_repair_companies.find_one({"id": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get plan
    plan = await db.subscription_plans.find_one({"id": plan_id}) if plan_id else None
    if not plan:
        # Use default plan
        plan = await db.subscription_plans.find_one({"code": "STANDARD"})
    
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    
    # Create subscription
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)
    
    subscription = {
        "id": str(uuid4()),
        "company_id": company_id,
        "plan_id": plan.get("id"),
        "plan_name": plan.get("name"),
        "monthly_rate": plan.get("monthly_fee"),
        "signup_fee_paid": True,
        "signup_fee_amount": plan.get("signup_fee"),
        "current_period_start": now.isoformat(),
        "current_period_end": period_end.isoformat(),
        "status": "active",
        "payment_processor_subscription_id": data.get("payment_subscription_id"),  # From Stripe, etc.
        "payment_processor_customer_id": data.get("payment_customer_id"),
        "company_revenue_percentage": plan.get("company_revenue_percentage", 60),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    await db.company_subscriptions.insert_one(subscription)
    
    # Update company status
    await db.credit_repair_companies.update_one(
        {"id": company_id},
        {
            "$set": {
                "subscription_status": "active",
                "subscription_tier": plan.get("code", "standard").lower(),
                "signup_fee_paid": True,
                "updated_at": now.isoformat()
            }
        }
    )
    
    subscription.pop("_id", None)
    
    return {"message": "Subscription activated successfully", "subscription": subscription}


@company_router.post("/subscription/cancel")
async def cancel_subscription(data: dict, authorization: Optional[str] = Header(None)):
    """Cancel company subscription"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    # Only owner can cancel
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only company owner can cancel subscription")
    
    company_id = user.get("company_id")
    cancel_immediately = data.get("cancel_immediately", False)
    
    subscription = await db.company_subscriptions.find_one({"company_id": company_id, "status": "active"})
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    if cancel_immediately:
        new_status = "cancelled"
        cancel_at = datetime.now(timezone.utc).isoformat()
    else:
        new_status = "cancelling"
        cancel_at = subscription.get("current_period_end")
    
    await db.company_subscriptions.update_one(
        {"id": subscription["id"]},
        {
            "$set": {
                "status": new_status,
                "cancel_at": cancel_at,
                "cancel_reason": data.get("reason"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Update company status
    company_status = "cancelled" if cancel_immediately else "cancelling"
    await db.credit_repair_companies.update_one(
        {"id": company_id},
        {"$set": {"subscription_status": company_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "message": "Subscription cancellation scheduled" if not cancel_immediately else "Subscription cancelled",
        "cancel_at": cancel_at
    }


# ==================== ANALYTICS ====================

@company_router.get("/analytics")
async def get_company_analytics(authorization: Optional[str] = Header(None)):
    """Get company performance analytics"""
    user = await get_current_user(authorization)
    require_company_user(user)
    
    company_id = user.get("company_id")
    
    # Get case stats
    total_cases = await db.cases.count_documents({"created_by_company_id": company_id})
    published_cases = await db.cases.count_documents({"created_by_company_id": company_id, "status": "published"})
    sold_cases = await db.cases.count_documents({"created_by_company_id": company_id, "status": {"$in": ["bid_accepted", "in_litigation", "settled"]}})
    
    # Get revenue
    revenue_pipeline = [
        {"$match": {"company_id": company_id}},
        {"$group": {
            "_id": None,
            "total_revenue": {"$sum": "$company_amount"},
            "total_cases": {"$sum": 1}
        }}
    ]
    revenue_result = await db.company_revenue_splits.aggregate(revenue_pipeline).to_list(None)
    revenue = revenue_result[0] if revenue_result else {"total_revenue": 0, "total_cases": 0}
    
    # Monthly breakdown
    monthly_pipeline = [
        {"$match": {"created_by_company_id": company_id}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 7]},
            "cases": {"$sum": 1}
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 12}
    ]
    monthly_cases = await db.cases.aggregate(monthly_pipeline).to_list(None)
    
    # Get subscription info
    subscription = await db.company_subscriptions.find_one(
        {"company_id": company_id, "status": {"$in": ["active", "trialing"]}},
        {"_id": 0}
    )
    
    return {
        "current_period": {
            "cases_submitted": total_cases,
            "cases_published": published_cases,
            "cases_sold": sold_cases,
            "revenue_earned": revenue.get("total_revenue", 0)
        },
        "all_time": {
            "total_cases": total_cases,
            "total_revenue": revenue.get("total_revenue", 0),
            "success_rate": (sold_cases / total_cases * 100) if total_cases > 0 else 0
        },
        "monthly_trend": monthly_cases,
        "subscription_info": {
            "status": subscription.get("status") if subscription else "inactive",
            "next_billing": subscription.get("current_period_end") if subscription else None
        }
    }


# ==================== ADMIN COMPANY MANAGEMENT ====================

@company_router.get("/admin/stats")
async def admin_company_stats(authorization: Optional[str] = Header(None)):
    """Admin: Get company network statistics"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    total_companies = await db.credit_repair_companies.count_documents({})
    active_companies = await db.credit_repair_companies.count_documents({"subscription_status": "active"})
    pending_companies = await db.credit_repair_companies.count_documents({"subscription_status": "pending_payment"})
    suspended_companies = await db.credit_repair_companies.count_documents({"subscription_status": "suspended"})
    
    # Cases by company
    case_pipeline = [
        {"$group": {
            "_id": "$created_by_company_id",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    top_companies_by_cases = await db.cases.aggregate(case_pipeline).to_list(None)
    
    # Enrich with company names
    for item in top_companies_by_cases:
        company = await db.credit_repair_companies.find_one({"id": item["_id"]}, {"company_name": 1})
        item["company_name"] = company.get("company_name", "Unknown") if company else "Unknown"
    
    return {
        "companies": {
            "total": total_companies,
            "active": active_companies,
            "pending": pending_companies,
            "suspended": suspended_companies
        },
        "top_companies_by_cases": top_companies_by_cases
    }


@company_router.get("/admin/list")
async def admin_list_companies(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Admin: List all credit repair companies"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if status:
        query["subscription_status"] = status
    if search:
        query["$or"] = [
            {"company_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"owner_name": {"$regex": search, "$options": "i"}}
        ]
    
    companies = await db.credit_repair_companies.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.credit_repair_companies.count_documents(query)
    
    return {"companies": companies, "total": total}


@company_router.get("/admin/{company_id}")
async def admin_get_company(company_id: str, authorization: Optional[str] = Header(None)):
    """Admin: Get company details"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    company = await db.credit_repair_companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get subscription
    subscription = await db.company_subscriptions.find_one({"company_id": company_id}, {"_id": 0})
    
    # Get users
    users = await db.company_users.find(
        {"company_id": company_id},
        {"_id": 0, "password_hash": 0, "token": 0}
    ).to_list(None)
    
    # Get cases
    cases = await db.cases.find(
        {"created_by_company_id": company_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(None)
    
    return {
        "company": company,
        "subscription": subscription,
        "users": users,
        "recent_cases": cases
    }


@company_router.put("/admin/{company_id}")
async def admin_update_company(company_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Update company"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    company = await db.credit_repair_companies.find_one({"id": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    allowed_fields = [
        "company_name", "phone", "address", "city", "state", "zip_code",
        "website", "subscription_status", "subscription_tier",
        "signup_fee_amount", "monthly_fee_amount"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.credit_repair_companies.update_one({"id": company_id}, {"$set": update_data})
    
    updated = await db.credit_repair_companies.find_one({"id": company_id}, {"_id": 0})
    return updated


@company_router.post("/admin/{company_id}/suspend")
async def admin_suspend_company(company_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Suspend a company"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    reason = data.get("reason", "Admin action")
    
    await db.credit_repair_companies.update_one(
        {"id": company_id},
        {
            "$set": {
                "subscription_status": "suspended",
                "suspension_reason": reason,
                "suspended_by": user.get("id"),
                "suspended_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Also suspend the subscription
    await db.company_subscriptions.update_one(
        {"company_id": company_id, "status": "active"},
        {"$set": {"status": "suspended", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Company suspended successfully"}


@company_router.post("/admin/{company_id}/reactivate")
async def admin_reactivate_company(company_id: str, authorization: Optional[str] = Header(None)):
    """Admin: Reactivate a suspended company"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    await db.credit_repair_companies.update_one(
        {"id": company_id},
        {
            "$set": {
                "subscription_status": "active",
                "suspension_reason": None,
                "reactivated_by": user.get("id"),
                "reactivated_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$unset": {"suspended_by": "", "suspended_at": ""}
        }
    )
    
    # Reactivate subscription
    await db.company_subscriptions.update_one(
        {"company_id": company_id, "status": "suspended"},
        {"$set": {"status": "active", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Company reactivated successfully"}
