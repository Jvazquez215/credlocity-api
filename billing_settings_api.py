"""
Credlocity Billing & Settings API
Centralized billing management for all business aspects:
- Subscription pricing (credit repair companies)
- Fee structures (initial fees, revenue splits)
- Commission rates (attorney, marketplace)
- Coupon code management
- Invoice/billing configuration
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import os
from motor.motor_asyncio import AsyncIOMotorClient

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

billing_router = APIRouter(prefix="/api/billing", tags=["Billing & Settings"])


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
    
    return None


def require_admin(user):
    """Require admin authentication"""
    if not user or user.get("role") not in ["admin", "super_admin", "director"]:
        raise HTTPException(status_code=403, detail="Admin authentication required")


# ==================== BILLING SETTINGS ====================

@billing_router.get("/settings")
async def get_billing_settings(authorization: Optional[str] = Header(None)):
    """Get all billing settings"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    settings = await db.billing_settings.find_one({"id": "billing_settings"}, {"_id": 0})
    
    if not settings:
        # Initialize with default settings
        settings = await initialize_billing_settings()
    
    return settings


@billing_router.put("/settings")
async def update_billing_settings(data: dict, authorization: Optional[str] = Header(None)):
    """Update billing settings"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Only allow updating specific fields
    allowed_fields = [
        # Credit Repair Company Subscription
        "company_signup_fee",
        "company_monthly_fee",
        "company_trial_days",
        "company_grace_period_days",
        
        # Revenue Split
        "company_revenue_split_percentage",
        "credlocity_revenue_split_percentage",
        
        # Attorney Marketplace Fees
        "attorney_initial_fee",
        "attorney_commission_tiers",
        "attorney_bonus_commission_cap",
        "attorney_upfront_bonus_cap",
        
        # Client Bonus Settings
        "client_bonus_percentage_cap",
        
        # Bidding Settings
        "bid_reserve_percentage",
        "bid_expiry_days",
        
        # General Settings
        "tax_rate",
        "late_payment_fee",
        "currency",
        "payment_terms_days"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("id")
    
    await db.billing_settings.update_one(
        {"id": "billing_settings"},
        {"$set": update_data},
        upsert=True
    )
    
    # Log the change
    await db.billing_audit_log.insert_one({
        "id": str(uuid4()),
        "action": "update_billing_settings",
        "changed_by_user_id": user.get("id"),
        "changed_by_name": user.get("full_name", "Admin"),
        "changes": update_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    updated = await db.billing_settings.find_one({"id": "billing_settings"}, {"_id": 0})
    return updated


async def initialize_billing_settings():
    """Initialize default billing settings"""
    settings = {
        "id": "billing_settings",
        
        # Credit Repair Company Subscription
        "company_signup_fee": 500.00,
        "company_monthly_fee": 199.99,
        "company_trial_days": 0,
        "company_grace_period_days": 7,
        
        # Revenue Split (when cases sell)
        "company_revenue_split_percentage": 60.0,
        "credlocity_revenue_split_percentage": 40.0,
        
        # Attorney Marketplace Fees
        "attorney_initial_fee": 500.00,
        "attorney_commission_tiers": [
            {"min": 0, "max": 5000, "rate": 0.00, "description": "Below minimum - Initial fee only"},
            {"min": 5001, "max": 7999, "rate": 0.03, "description": "Tier 1: $5,001-$7,999 at 3%"},
            {"min": 8000, "max": 10999, "rate": 0.04, "description": "Tier 2: $8,000-$10,999 at 4%"},
            {"min": 11000, "max": 14999, "rate": 0.05, "description": "Tier 3: $11,000-$14,999 at 5%"},
            {"min": 15000, "max": 19999, "rate": 0.10, "description": "Tier 4: $15,000-$19,999 at 10%"},
            {"min": 20000, "max": None, "rate": 0.10, "description": "Tier 5: $20,000+ at 10% (progressive)"}
        ],
        "attorney_bonus_commission_cap": 0.15,  # 15% max bonus commission
        "attorney_upfront_bonus_cap": 2500.00,  # $2,500 max upfront bonus
        
        # Client Bonus Settings (for bidding)
        "client_bonus_percentage_cap": 0.20,  # 20% max client bonus
        
        # Bidding Settings
        "bid_reserve_percentage": 100,  # 100% of bid reserved
        "bid_expiry_days": 7,
        
        # General Settings
        "tax_rate": 0.0,  # Can be configured per state
        "late_payment_fee": 25.00,
        "currency": "USD",
        "payment_terms_days": 30,
        
        # Metadata
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.billing_settings.insert_one(settings)
    settings.pop("_id", None)
    return settings


@billing_router.get("/settings/commission-calculator")
async def calculate_commission_preview(
    settlement_amount: float,
    bonus_rate: float = 0,
    authorization: Optional[str] = Header(None)
):
    """Calculate commission preview based on current settings"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    settings = await db.billing_settings.find_one({"id": "billing_settings"}, {"_id": 0})
    if not settings:
        settings = await initialize_billing_settings()
    
    tiers = settings.get("attorney_commission_tiers", [])
    initial_fee = settings.get("attorney_initial_fee", 500)
    
    # Find applicable tier
    applicable_tier = None
    for tier in tiers:
        min_val = tier.get("min", 0)
        max_val = tier.get("max")
        if settlement_amount >= min_val and (max_val is None or settlement_amount <= max_val):
            applicable_tier = tier
            break
    
    if not applicable_tier:
        applicable_tier = {"rate": 0, "description": "Unknown tier"}
    
    standard_rate = applicable_tier.get("rate", 0)
    total_rate = standard_rate + bonus_rate
    commission = settlement_amount * total_rate
    
    return {
        "settlement_amount": settlement_amount,
        "tier_description": applicable_tier.get("description", ""),
        "standard_rate": standard_rate,
        "bonus_rate": bonus_rate,
        "total_rate": total_rate,
        "initial_fee": initial_fee,
        "commission_amount": round(commission, 2),
        "total_due": round(initial_fee + commission, 2)
    }


# ==================== COUPON MANAGEMENT ====================
# (Universal coupons - applicable to any billing context)

@billing_router.get("/coupons")
async def get_all_coupons(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    coupon_type: Optional[str] = None
):
    """Get all coupons with optional filters"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if status:
        query["status"] = status
    if coupon_type:
        query["coupon_type"] = coupon_type
    
    coupons = await db.billing_coupons.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)
    return coupons


@billing_router.post("/coupons")
async def create_coupon(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new coupon"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Check for duplicate code
    existing = await db.billing_coupons.find_one({"code": data.get("code", "").upper()})
    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists")
    
    coupon = {
        "id": str(uuid4()),
        "code": data.get("code", "").upper(),
        "name": data.get("name"),
        "description": data.get("description", ""),
        
        # Coupon Type determines where it can be applied
        "coupon_type": data.get("coupon_type", "universal"),  # universal, company_subscription, attorney_fee, outsourcing
        
        # Discount Configuration
        "discount_type": data.get("discount_type", "percentage"),  # percentage, fixed_amount, free_months, per_file
        "discount_value": float(data.get("discount_value", 0)),
        
        # Applicability
        "applies_to": data.get("applies_to", "all"),  # all, specific_companies, specific_partners
        "specific_entity_ids": data.get("specific_entity_ids", []),
        
        # Limits
        "max_uses": data.get("max_uses"),  # None = unlimited
        "max_uses_per_entity": data.get("max_uses_per_entity", 1),
        "times_used": 0,
        "duration_months": data.get("duration_months"),  # How long discount applies
        "min_purchase_amount": data.get("min_purchase_amount"),
        
        # Validity
        "valid_from": data.get("valid_from", datetime.now(timezone.utc).isoformat()),
        "valid_until": data.get("valid_until"),
        "status": "active",
        
        # Metadata
        "created_by": user.get("id"),
        "created_by_name": user.get("full_name", "Admin"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.billing_coupons.insert_one(coupon)
    coupon.pop("_id", None)
    
    return {"message": "Coupon created successfully", "coupon": coupon}


@billing_router.get("/coupons/{coupon_id}")
async def get_coupon(coupon_id: str, authorization: Optional[str] = Header(None)):
    """Get a specific coupon"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    coupon = await db.billing_coupons.find_one({"id": coupon_id}, {"_id": 0})
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    
    return coupon


@billing_router.put("/coupons/{coupon_id}")
async def update_coupon(coupon_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update a coupon"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    coupon = await db.billing_coupons.find_one({"id": coupon_id})
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    
    # Check for code uniqueness if changing code
    if data.get("code") and data["code"].upper() != coupon.get("code"):
        existing = await db.billing_coupons.find_one({"code": data["code"].upper()})
        if existing:
            raise HTTPException(status_code=400, detail="Coupon code already exists")
    
    allowed_fields = [
        "code", "name", "description", "coupon_type", "discount_type", "discount_value",
        "applies_to", "specific_entity_ids", "max_uses", "max_uses_per_entity",
        "duration_months", "min_purchase_amount", "valid_from", "valid_until", "status"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    if "code" in update_data:
        update_data["code"] = update_data["code"].upper()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.billing_coupons.update_one({"id": coupon_id}, {"$set": update_data})
    
    updated = await db.billing_coupons.find_one({"id": coupon_id}, {"_id": 0})
    return updated


@billing_router.delete("/coupons/{coupon_id}")
async def delete_coupon(coupon_id: str, authorization: Optional[str] = Header(None)):
    """Delete a coupon"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    result = await db.billing_coupons.delete_one({"id": coupon_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Coupon not found")
    
    return {"message": "Coupon deleted successfully"}


@billing_router.post("/coupons/validate")
async def validate_coupon(data: dict, authorization: Optional[str] = Header(None)):
    """Validate a coupon code for a specific context"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    code = data.get("code", "").upper()
    coupon_type = data.get("coupon_type", "universal")
    entity_id = data.get("entity_id")  # Company ID or Partner ID
    purchase_amount = float(data.get("purchase_amount", 0))
    
    coupon = await db.billing_coupons.find_one({
        "code": code,
        "status": "active"
    })
    
    if not coupon:
        return {"valid": False, "reason": "Coupon not found or inactive"}
    
    # Check coupon type
    if coupon.get("coupon_type") not in ["universal", coupon_type]:
        return {"valid": False, "reason": f"Coupon not valid for {coupon_type}"}
    
    # Check validity dates
    now = datetime.now(timezone.utc)
    valid_from = coupon.get("valid_from")
    valid_until = coupon.get("valid_until")
    
    if valid_from:
        from_date = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
        if now < from_date:
            return {"valid": False, "reason": "Coupon not yet valid"}
    
    if valid_until:
        until_date = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        if now > until_date:
            return {"valid": False, "reason": "Coupon has expired"}
    
    # Check max uses
    if coupon.get("max_uses") and coupon.get("times_used", 0) >= coupon.get("max_uses"):
        return {"valid": False, "reason": "Coupon usage limit reached"}
    
    # Check entity-specific limits
    if entity_id and coupon.get("max_uses_per_entity"):
        usage_count = await db.coupon_usage_log.count_documents({
            "coupon_id": coupon.get("id"),
            "entity_id": entity_id
        })
        if usage_count >= coupon.get("max_uses_per_entity"):
            return {"valid": False, "reason": "Usage limit reached for this account"}
    
    # Check applicability
    applies_to = coupon.get("applies_to", "all")
    if applies_to != "all" and entity_id:
        specific_ids = coupon.get("specific_entity_ids", [])
        if entity_id not in specific_ids:
            return {"valid": False, "reason": "Coupon not valid for this account"}
    
    # Check minimum purchase
    min_purchase = coupon.get("min_purchase_amount")
    if min_purchase and purchase_amount < min_purchase:
        return {"valid": False, "reason": f"Minimum purchase amount is ${min_purchase}"}
    
    # Calculate discount
    discount_type = coupon.get("discount_type")
    discount_value = coupon.get("discount_value", 0)
    discount_amount = 0
    
    if discount_type == "percentage":
        discount_amount = purchase_amount * (discount_value / 100)
    elif discount_type == "fixed_amount":
        discount_amount = min(discount_value, purchase_amount)
    elif discount_type == "free_months":
        # Special handling for subscription coupons
        discount_amount = discount_value  # Represents months, not dollars
    
    return {
        "valid": True,
        "coupon": {
            "id": coupon.get("id"),
            "code": coupon.get("code"),
            "name": coupon.get("name"),
            "discount_type": discount_type,
            "discount_value": discount_value,
            "duration_months": coupon.get("duration_months")
        },
        "discount_amount": round(discount_amount, 2)
    }


# ==================== COUPON USAGE TRACKING ====================

@billing_router.get("/coupons/{coupon_id}/usage")
async def get_coupon_usage(coupon_id: str, authorization: Optional[str] = Header(None)):
    """Get usage history for a coupon"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    usage = await db.coupon_usage_log.find(
        {"coupon_id": coupon_id}, 
        {"_id": 0}
    ).sort("used_at", -1).to_list(100)
    
    return {"coupon_id": coupon_id, "usage": usage, "total_uses": len(usage)}


# ==================== INVOICE MANAGEMENT ====================

@billing_router.get("/invoices")
async def get_invoices(
    authorization: Optional[str] = Header(None),
    invoice_type: Optional[str] = None,  # company_subscription, attorney_fee, outsourcing, case_settlement
    status: Optional[str] = None,
    entity_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get all invoices with filters"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if invoice_type:
        query["invoice_type"] = invoice_type
    if status:
        query["status"] = status
    if entity_id:
        query["entity_id"] = entity_id
    
    invoices = await db.billing_invoices.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.billing_invoices.count_documents(query)
    
    return {"invoices": invoices, "total": total}


@billing_router.post("/invoices")
async def create_invoice(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new invoice"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Generate invoice number
    count = await db.billing_invoices.count_documents({})
    invoice_number = f"INV-{datetime.now().strftime('%Y%m')}-{str(count + 1).zfill(5)}"
    
    invoice = {
        "id": str(uuid4()),
        "invoice_number": invoice_number,
        "invoice_type": data.get("invoice_type", "general"),  # company_subscription, attorney_fee, outsourcing, case_settlement
        
        # Entity Information
        "entity_id": data.get("entity_id"),
        "entity_type": data.get("entity_type"),  # credit_repair_company, attorney, outsource_partner
        "entity_name": data.get("entity_name"),
        "entity_email": data.get("entity_email"),
        
        # Line Items
        "line_items": data.get("line_items", []),  # [{description, quantity, unit_price, amount}]
        
        # Amounts
        "subtotal": float(data.get("subtotal", 0)),
        "discount_amount": float(data.get("discount_amount", 0)),
        "tax_amount": float(data.get("tax_amount", 0)),
        "total_amount": float(data.get("total_amount", 0)),
        
        # Coupon
        "coupon_code": data.get("coupon_code"),
        "coupon_id": data.get("coupon_id"),
        
        # Related Entity
        "related_case_id": data.get("related_case_id"),
        "related_subscription_id": data.get("related_subscription_id"),
        
        # Status & Dates
        "status": "pending",  # pending, paid, partial, overdue, cancelled, refunded
        "due_date": data.get("due_date"),
        "paid_date": None,
        "paid_amount": 0,
        
        # Payment Information
        "payment_method": None,
        "payment_reference": None,
        
        # Notes
        "notes": data.get("notes"),
        "internal_notes": data.get("internal_notes"),
        
        # Metadata
        "created_by": user.get("id"),
        "created_by_name": user.get("full_name", "Admin"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.billing_invoices.insert_one(invoice)
    invoice.pop("_id", None)
    
    return {"message": "Invoice created successfully", "invoice": invoice}


@billing_router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update an invoice"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    invoice = await db.billing_invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    allowed_fields = [
        "line_items", "subtotal", "discount_amount", "tax_amount", "total_amount",
        "coupon_code", "coupon_id", "status", "due_date", "notes", "internal_notes"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.billing_invoices.update_one({"id": invoice_id}, {"$set": update_data})
    
    updated = await db.billing_invoices.find_one({"id": invoice_id}, {"_id": 0})
    return updated


@billing_router.post("/invoices/{invoice_id}/record-payment")
async def record_payment(invoice_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Record a payment for an invoice"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    invoice = await db.billing_invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    payment_amount = float(data.get("amount", 0))
    current_paid = float(invoice.get("paid_amount", 0))
    total_paid = current_paid + payment_amount
    total_amount = float(invoice.get("total_amount", 0))
    
    # Determine new status
    if total_paid >= total_amount:
        new_status = "paid"
    elif total_paid > 0:
        new_status = "partial"
    else:
        new_status = invoice.get("status")
    
    # Record payment
    payment = {
        "id": str(uuid4()),
        "invoice_id": invoice_id,
        "amount": payment_amount,
        "payment_method": data.get("payment_method"),
        "payment_reference": data.get("payment_reference"),
        "notes": data.get("notes"),
        "recorded_by": user.get("id"),
        "recorded_by_name": user.get("full_name", "Admin"),
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.billing_payments.insert_one(payment)
    
    # Update invoice
    update_data = {
        "paid_amount": total_paid,
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if new_status == "paid":
        update_data["paid_date"] = datetime.now(timezone.utc).isoformat()
        update_data["payment_method"] = data.get("payment_method")
        update_data["payment_reference"] = data.get("payment_reference")
    
    await db.billing_invoices.update_one({"id": invoice_id}, {"$set": update_data})
    
    return {
        "message": "Payment recorded successfully",
        "payment_id": payment["id"],
        "total_paid": total_paid,
        "remaining": max(0, total_amount - total_paid),
        "status": new_status
    }


# ==================== BILLING STATISTICS ====================

@billing_router.get("/stats/overview")
async def get_billing_overview(authorization: Optional[str] = Header(None)):
    """Get billing statistics overview"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Invoice stats
    total_invoices = await db.billing_invoices.count_documents({})
    pending_invoices = await db.billing_invoices.count_documents({"status": "pending"})
    paid_invoices = await db.billing_invoices.count_documents({"status": "paid"})
    overdue_invoices = await db.billing_invoices.count_documents({"status": "overdue"})
    
    # Revenue pipeline
    pipeline = [
        {"$group": {
            "_id": "$status",
            "total": {"$sum": "$total_amount"},
            "paid": {"$sum": "$paid_amount"},
            "count": {"$sum": 1}
        }}
    ]
    revenue_by_status = await db.billing_invoices.aggregate(pipeline).to_list(None)
    
    # Monthly revenue
    monthly_pipeline = [
        {"$match": {"status": "paid"}},
        {"$group": {
            "_id": {"$substr": ["$paid_date", 0, 7]},
            "total": {"$sum": "$paid_amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 12}
    ]
    monthly_revenue = await db.billing_invoices.aggregate(monthly_pipeline).to_list(None)
    
    # Coupon stats
    active_coupons = await db.billing_coupons.count_documents({"status": "active"})
    total_coupon_usage = await db.coupon_usage_log.count_documents({})
    
    return {
        "invoices": {
            "total": total_invoices,
            "pending": pending_invoices,
            "paid": paid_invoices,
            "overdue": overdue_invoices
        },
        "revenue_by_status": {item["_id"]: {"total": item["total"], "paid": item["paid"], "count": item["count"]} for item in revenue_by_status},
        "monthly_revenue": monthly_revenue,
        "coupons": {
            "active": active_coupons,
            "total_usage": total_coupon_usage
        }
    }


# ==================== SUBSCRIPTION PLANS ====================

@billing_router.get("/subscription-plans")
async def get_subscription_plans(authorization: Optional[str] = Header(None)):
    """Get all subscription plans for credit repair companies"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    plans = await db.subscription_plans.find({}, {"_id": 0}).sort("display_order", 1).to_list(None)
    
    if not plans:
        # Initialize default plans
        plans = await initialize_subscription_plans()
    
    return plans


@billing_router.post("/subscription-plans")
async def create_subscription_plan(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new subscription plan"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    plan = {
        "id": str(uuid4()),
        "name": data.get("name"),
        "code": data.get("code", "").upper().replace(" ", "_"),
        "description": data.get("description"),
        
        # Pricing
        "signup_fee": float(data.get("signup_fee", 500)),
        "monthly_fee": float(data.get("monthly_fee", 199.99)),
        "annual_fee": data.get("annual_fee"),  # Optional annual pricing
        
        # Features
        "features": data.get("features", []),
        "max_cases_per_month": data.get("max_cases_per_month"),  # None = unlimited
        "max_users": data.get("max_users", 1),
        
        # Revenue Split
        "company_revenue_percentage": float(data.get("company_revenue_percentage", 60)),
        
        # Display
        "display_order": data.get("display_order", 0),
        "is_featured": data.get("is_featured", False),
        "status": "active",
        
        # Metadata
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.subscription_plans.insert_one(plan)
    plan.pop("_id", None)
    
    return {"message": "Subscription plan created", "plan": plan}


@billing_router.put("/subscription-plans/{plan_id}")
async def update_subscription_plan(plan_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update a subscription plan"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    plan = await db.subscription_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    allowed_fields = [
        "name", "code", "description", "signup_fee", "monthly_fee", "annual_fee",
        "features", "max_cases_per_month", "max_users", "company_revenue_percentage",
        "display_order", "is_featured", "status",
        # Website pricing page settings
        "show_on_website", "website_settings"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.subscription_plans.update_one({"id": plan_id}, {"$set": update_data})
    
    updated = await db.subscription_plans.find_one({"id": plan_id}, {"_id": 0})
    return updated


@billing_router.delete("/subscription-plans/{plan_id}")
async def delete_subscription_plan(plan_id: str, authorization: Optional[str] = Header(None)):
    """Delete a subscription plan (soft delete - sets status to inactive)"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Check if any active subscriptions use this plan
    active_subs = await db.company_subscriptions.count_documents({
        "plan_id": plan_id,
        "status": {"$in": ["active", "trialing"]}
    })
    
    if active_subs > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete plan with {active_subs} active subscriptions. Deactivate instead."
        )
    
    await db.subscription_plans.update_one(
        {"id": plan_id},
        {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Subscription plan deactivated"}


# ==================== PRICING PRODUCTS (One-time services, Pay-per-delete) ====================

@billing_router.get("/pricing-products")
async def get_pricing_products(
    authorization: Optional[str] = Header(None),
    category: Optional[str] = None
):
    """Get all pricing products (admin only)"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if category:
        query["category"] = category
    
    products = await db.pricing_products.find(query, {"_id": 0}).sort("display_order", 1).to_list(None)
    
    if not products:
        # Initialize default products
        products = await initialize_pricing_products()
    
    return products


@billing_router.post("/pricing-products")
async def create_pricing_product(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new pricing product"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    product = {
        "id": str(uuid4()),
        "name": data.get("name"),
        "code": data.get("code", "").upper().replace(" ", "_"),
        "description": data.get("description"),
        "category": data.get("category", "one_time"),  # one_time, setup_service, pay_per_delete
        "price": float(data.get("price", 0)),
        "price_display": data.get("price_display"),
        "price_note": data.get("price_note"),  # e.g., "Per successful deletion" or "One-time Required Service"
        "icon": data.get("icon"),  # Icon name for display
        "features": data.get("features", []),
        "cta_text": data.get("cta_text", "Get Started"),
        "cta_url": data.get("cta_url"),
        "show_on_website": data.get("show_on_website", False),
        "display_order": data.get("display_order", 0),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.pricing_products.insert_one(product)
    product.pop("_id", None)
    
    return {"message": "Pricing product created", "product": product}


@billing_router.put("/pricing-products/{product_id}")
async def update_pricing_product(product_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update a pricing product"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    product = await db.pricing_products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    allowed_fields = [
        "name", "code", "description", "category", "price", "price_display",
        "price_note", "icon", "features", "cta_text", "cta_url",
        "show_on_website", "display_order", "status"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.pricing_products.update_one({"id": product_id}, {"$set": update_data})
    
    updated = await db.pricing_products.find_one({"id": product_id}, {"_id": 0})
    return updated


@billing_router.delete("/pricing-products/{product_id}")
async def delete_pricing_product(product_id: str, authorization: Optional[str] = Header(None)):
    """Delete a pricing product"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    await db.pricing_products.update_one(
        {"id": product_id},
        {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Pricing product deactivated"}


@billing_router.get("/public/pricing-products")
async def get_public_pricing_products(category: Optional[str] = None):
    """
    Public endpoint - no auth required
    Returns pricing products enabled for the public website
    """
    query = {"status": "active", "show_on_website": True}
    if category:
        query["category"] = category
    
    products = await db.pricing_products.find(query, {"_id": 0}).sort("display_order", 1).to_list(None)
    return products


async def initialize_pricing_products():
    """Initialize default pricing products"""
    products = [
        # Essential Setup Services
        {
            "id": str(uuid4()),
            "name": "Credit Report Analysis",
            "code": "CREDIT_REPORT",
            "description": "Comprehensive three-bureau credit report for detailed analysis. Essential for identifying errors, outdated information, and opportunities for score improvement. Required for legal compliance with FCRA regulations.",
            "category": "setup_service",
            "price": 49.95,
            "price_display": "$49.95",
            "price_note": "One-time Required Service",
            "icon": "chart",
            "features": [],
            "cta_text": "Order Credit Report",
            "cta_url": "https://credlocity.scorexer.com/portal-signUp/signup.jsp",
            "show_on_website": True,
            "display_order": 1,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "name": "Power of Attorney (E-Notary)",
            "code": "POA_ENOTARY",
            "description": "Secure electronic notarization for immediate processing. Required for legal representation with creditors and bureaus. E-Notary ensures document validity and prevents processing delays from paper submissions.",
            "category": "setup_service",
            "price": 39.95,
            "price_display": "$39.95",
            "price_note": "Individual • $29.95 each for Couples/Family",
            "icon": "scale",
            "features": [],
            "cta_text": "Schedule E-Notary",
            "cta_url": "https://credlocity.scorexer.com/portal-signUp/signup.jsp",
            "show_on_website": True,
            "display_order": 2,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        # Pay-Per-Delete Options
        {
            "id": str(uuid4()),
            "name": "Collections & Charge-offs",
            "code": "PPD_COLLECTIONS",
            "description": "Pay only when we successfully remove collection accounts, charge-off accounts, or settled accounts from your credit report.",
            "category": "pay_per_delete",
            "price": 150,
            "price_display": "$150",
            "price_note": "Per successful deletion",
            "icon": "file-minus",
            "features": ["Collection accounts", "Charge-off accounts", "Settled accounts"],
            "cta_text": "Get Started",
            "cta_url": "https://credlocity.scorexer.com/portal-signUp/signup.jsp",
            "show_on_website": True,
            "display_order": 1,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "name": "Late Payments & Inquiries",
            "code": "PPD_LATE_PAYMENTS",
            "description": "Pay only when we successfully remove late payment history, hard inquiries, or account remarks from your credit report.",
            "category": "pay_per_delete",
            "price": 75,
            "price_display": "$75",
            "price_note": "Per successful deletion",
            "icon": "clock",
            "features": ["Late payment history", "Hard inquiries", "Account remarks"],
            "cta_text": "Get Started",
            "cta_url": "https://credlocity.scorexer.com/portal-signUp/signup.jsp",
            "show_on_website": True,
            "display_order": 2,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "name": "Public Records",
            "code": "PPD_PUBLIC_RECORDS",
            "description": "Pay only when we successfully remove bankruptcies, tax liens, or judgments from your credit report.",
            "category": "pay_per_delete",
            "price": 250,
            "price_display": "$250",
            "price_note": "Per successful deletion",
            "icon": "building",
            "features": ["Bankruptcies", "Tax liens", "Judgments"],
            "cta_text": "Get Started",
            "cta_url": "https://credlocity.scorexer.com/portal-signUp/signup.jsp",
            "show_on_website": True,
            "display_order": 3,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    for product in products:
        await db.pricing_products.insert_one(product)
        product.pop("_id", None)
    
    return products


# ==================== PUBLIC WEBSITE PRICING API ====================

@billing_router.get("/public/pricing-plans")
async def get_public_pricing_plans():
    """
    Public endpoint - no auth required
    Returns pricing plans enabled for the public website
    """
    plans = await db.subscription_plans.find(
        {"status": "active", "show_on_website": True},
        {"_id": 0}
    ).sort("display_order", 1).to_list(None)
    
    # Transform for website display
    website_plans = []
    for plan in plans:
        ws = plan.get("website_settings", {})
        website_plans.append({
            "id": plan.get("id"),
            "name": ws.get("display_name") or plan.get("name"),
            "code": plan.get("code"),
            "tagline": ws.get("tagline") or plan.get("description"),
            "price": ws.get("price_display") or f"${plan.get('monthly_fee', 0)}",
            "price_value": plan.get("monthly_fee", 0),
            "price_period": ws.get("price_period", "/month"),
            "trial_text": ws.get("trial_text", ""),
            "cta_text": ws.get("cta_text", "Get Started"),
            "cta_url": ws.get("cta_url", "/signup"),
            "banner": ws.get("banner"),  # {"text": "Most Popular", "color": "green", "position": "top"}
            "features": ws.get("features_included") or plan.get("features", []),
            "not_included": ws.get("features_not_included", []),
            "is_featured": plan.get("is_featured", False),
            "highlight_color": ws.get("highlight_color"),
            "display_order": plan.get("display_order", 0)
        })
    
    return website_plans


@billing_router.get("/public/pricing-config")
async def get_public_pricing_config():
    """
    Public endpoint - no auth required
    Returns pricing page configuration (hero text, FAQs, comparison table, etc.)
    """
    config = await db.pricing_page_config.find_one({"id": "pricing_page"}, {"_id": 0})
    
    if not config:
        # Return default configuration
        config = {
            "id": "pricing_page",
            "hero": {
                "title": "Monthly Service Plans",
                "subtitle": "Professional credit repair with comprehensive dispute services and ongoing support",
                "highlights": ["$0 First Work Fee", "180-Day Money Back Guarantee", "Cancel Anytime"]
            },
            "sections": {
                "monthly_plans": {
                    "enabled": True,
                    "title": "Monthly Service Plans",
                    "subtitle": "Professional credit repair with comprehensive dispute services and ongoing support"
                },
                "setup_services": {
                    "enabled": True,
                    "title": "Essential Setup Services",
                    "subtitle": "Required one-time services to begin your credit repair journey professionally and legally",
                    "info_box": {
                        "title": "Why These Services Are Required",
                        "points": [
                            "Credit reports provide the legal foundation for dispute strategies",
                            "Power of Attorney enables us to negotiate directly with creditors",
                            "E-Notary prevents delays and ensures immediate case activation"
                        ],
                        "note": "These aren't additional fees - they're essential legal requirements for professional credit repair"
                    }
                },
                "pay_per_delete": {
                    "enabled": True,
                    "title": "Pay-Per-Delete Options",
                    "subtitle": "Only pay when we successfully remove negative items from your credit report",
                    "benefits": [
                        "No monthly fees - only pay for results",
                        "Performance-based pricing model",
                        "Same credit report and power of attorney requirements",
                        "Perfect for targeted credit repair needs"
                    ]
                },
                "guarantee": {
                    "enabled": True,
                    "title": "180-Day Money-Back Guarantee",
                    "description": "We're so confident in our service that we offer a complete money-back guarantee. If you don't see meaningful progress in your credit score within 180 days, we'll refund your money - no questions asked.",
                    "icon": "shield"
                }
            },
            "comparison_table": {
                "enabled": True,
                "title": "How We Compare to Competitors",
                "competitors": ["Lexington Law", "Creditrepair.com"],
                "features": [
                    {"name": "First Work Fee", "credlocity": "$0", "competitor_values": ["Varies", "$119.95"]},
                    {"name": "Free Trial", "credlocity": "30 Days", "competitor_values": ["None", "None"]},
                    {"name": "BBB Complaints (3 yrs)", "credlocity": "0", "competitor_values": ["Multiple", "Multiple"]}
                ]
            },
            "faqs": [
                {"question": "Do you charge a first work fee?", "answer": "No! Unlike many competitors who charge $100-$150 upfront, we charge $0 in first work fees."},
                {"question": "How long is the free trial?", "answer": "Our plans include up to 30-day free trial - the longest in the credit repair industry."},
                {"question": "Can I cancel anytime?", "answer": "Yes, absolutely. You can cancel your subscription at any time with no cancellation fees or penalties."}
            ],
            "cta_section": {
                "title": "Ready to Get Started?",
                "subtitle": "Start your free trial today. No credit card required. No first work fee.",
                "primary_button": {"text": "Start Your Free Trial", "url": "https://credlocity.scorexer.com/portal-signUp/signup.jsp"},
                "secondary_button": {"text": "Schedule Consultation", "url": "https://calendly.com/credlocity/oneonone"}
            },
            "compliance_notice": "In accordance with federal regulations, all credit repair services must be initiated through our secure online platform."
        }
    
    return config


@billing_router.put("/pricing-page-config")
async def update_pricing_page_config(data: dict, authorization: Optional[str] = Header(None)):
    """Update pricing page configuration (admin only)"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    data["id"] = "pricing_page"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user.get("id")
    
    await db.pricing_page_config.update_one(
        {"id": "pricing_page"},
        {"$set": data},
        upsert=True
    )
    
    return {"message": "Pricing page configuration updated"}


@billing_router.get("/pricing-page-config")
async def get_pricing_page_config(authorization: Optional[str] = Header(None)):
    """Get pricing page configuration (admin only)"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    config = await db.pricing_page_config.find_one({"id": "pricing_page"}, {"_id": 0})
    return config or {}


async def initialize_subscription_plans():
    """Initialize default subscription plans"""
    plans = [
        {
            "id": str(uuid4()),
            "name": "Standard",
            "code": "STANDARD",
            "description": "Perfect for small credit repair companies",
            "signup_fee": 500.00,
            "monthly_fee": 199.99,
            "annual_fee": 1999.99,
            "features": [
                "Unlimited case submissions",
                "Access to attorney marketplace",
                "60% revenue share on case sales",
                "Basic analytics dashboard",
                "Email support"
            ],
            "max_cases_per_month": None,
            "max_users": 3,
            "company_revenue_percentage": 60.0,
            "display_order": 1,
            "is_featured": False,
            "status": "active",
            # Website pricing page settings
            "show_on_website": False,
            "website_settings": {
                "display_name": "Standard",
                "tagline": "Perfect for getting started",
                "price_display": "$199.99",
                "price_period": "/month",
                "trial_text": "14-Day Free Trial",
                "cta_text": "Get Started",
                "cta_url": "/signup?plan=standard",
                "banner": None,  # e.g., {"text": "Best Value", "color": "gold", "position": "top"}
                "features_included": [],
                "features_not_included": [],
                "highlight_color": None
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "name": "Professional",
            "code": "PROFESSIONAL",
            "description": "For growing credit repair businesses",
            "signup_fee": 500.00,
            "monthly_fee": 349.99,
            "annual_fee": 3499.99,
            "features": [
                "Everything in Standard",
                "65% revenue share on case sales",
                "Priority case listing",
                "Advanced analytics",
                "Phone & email support",
                "Dedicated account manager"
            ],
            "max_cases_per_month": None,
            "max_users": 10,
            "company_revenue_percentage": 65.0,
            "display_order": 2,
            "is_featured": True,
            "status": "active",
            # Website pricing page settings
            "show_on_website": False,
            "website_settings": {
                "display_name": "Professional",
                "tagline": "Most popular choice",
                "price_display": "$349.99",
                "price_period": "/month",
                "trial_text": "30-Day Free Trial",
                "cta_text": "Start Free Trial",
                "cta_url": "/signup?plan=professional",
                "banner": {"text": "Most Popular", "color": "green", "position": "top"},
                "features_included": [],
                "features_not_included": [],
                "highlight_color": "green"
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "name": "Enterprise",
            "code": "ENTERPRISE",
            "description": "For large operations with custom needs",
            "signup_fee": 0,
            "monthly_fee": 0,  # Custom pricing
            "annual_fee": None,
            "features": [
                "Everything in Professional",
                "Custom revenue share",
                "White-label options",
                "API access",
                "Custom integrations",
                "24/7 priority support"
            ],
            "max_cases_per_month": None,
            "max_users": None,
            "company_revenue_percentage": 70.0,
            "display_order": 3,
            "is_featured": False,
            "status": "active",
            # Website pricing page settings
            "show_on_website": False,
            "website_settings": {
                "display_name": "Enterprise",
                "tagline": "Custom solutions for large teams",
                "price_display": "Custom",
                "price_period": "",
                "trial_text": "Contact Us",
                "cta_text": "Contact Sales",
                "cta_url": "/contact?inquiry=enterprise",
                "banner": None,
                "features_included": [],
                "features_not_included": [],
                "highlight_color": None
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    for plan in plans:
        await db.subscription_plans.insert_one(plan)
        plan.pop("_id", None)
    
    return plans
