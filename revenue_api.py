"""
Credlocity Revenue Tracking API
Comprehensive revenue tracking across all business sources:
1. Attorney Network Revenue (referral fees, commissions, bid bonuses)
2. Collections Revenue (recovered balances, payment plans)
3. Credit Repair Clients (monthly fees, setup fees)
4. Outsourcing Clients (project fees, retainers)
5. Digital Products (future: ebooks, templates, courses)
"""

from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import os
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
client = get_client(MONGO_URL)
db = client[DB_NAME]

revenue_router = APIRouter(prefix="/api/revenue", tags=["Revenue"])


# ==================== AUTHENTICATION ====================

async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from authorization header using JWT"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    
    try:
        from jose import jwt, JWTError
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if not email:
            return None
    except:
        return None
    
    user = await db.users.find_one({"email": email}, {"_id": 0, "hashed_password": 0})
    if user:
        if user.get("role") == "super_admin":
            user["role"] = "admin"
        return user
    
    return None


def require_admin(user):
    """Check if user has admin access for revenue dashboard"""
    if not user or user.get("role") not in ["admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized to view revenue data")


# ==================== REVENUE RECORDS ====================

@revenue_router.post("/records")
async def create_revenue_record(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new revenue record"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    record = {
        "id": str(uuid4()),
        "source": data["source"],  # attorney_network, collections, credit_repair, outsourcing, digital_products
        "category": data.get("category"),  # Subcategory within source
        "amount": float(data["amount"]),
        "description": data.get("description"),
        "reference_id": data.get("reference_id"),  # Link to case, account, client, etc.
        "reference_type": data.get("reference_type"),  # case, collection_account, client, invoice
        "payment_status": data.get("payment_status", "pending"),  # pending, paid, overdue, cancelled
        "payment_method": data.get("payment_method"),
        "payment_date": data.get("payment_date"),
        "due_date": data.get("due_date"),
        "notes": data.get("notes"),
        "created_by_id": user["id"],
        "created_by_name": user.get("full_name") or user.get("name"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.revenue_records.insert_one(record)
    record.pop("_id", None)
    return record


@revenue_router.get("/records")
async def list_revenue_records(
    authorization: Optional[str] = Header(None),
    source: Optional[str] = None,
    payment_status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
):
    """List revenue records with filters"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if source:
        query["source"] = source
    if payment_status:
        query["payment_status"] = payment_status
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    records = await db.revenue_records.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.revenue_records.count_documents(query)
    
    return {"records": records, "total": total}


@revenue_router.put("/records/{record_id}")
async def update_revenue_record(record_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update a revenue record"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    record = await db.revenue_records.find_one({"id": record_id})
    if not record:
        raise HTTPException(status_code=404, detail="Revenue record not found")
    
    update_fields = ["amount", "description", "payment_status", "payment_method", "payment_date", "due_date", "notes"]
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    for field in update_fields:
        if field in data:
            update[field] = data[field]
    
    await db.revenue_records.update_one({"id": record_id}, {"$set": update})
    
    updated = await db.revenue_records.find_one({"id": record_id}, {"_id": 0})
    return updated


# ==================== DASHBOARD STATISTICS ====================

@revenue_router.get("/dashboard/summary")
async def get_revenue_summary(
    authorization: Optional[str] = Header(None),
    period: str = "month"  # day, week, month, quarter, year, all
):
    """Get revenue summary for dashboard"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Calculate date range
    now = datetime.now(timezone.utc)
    if period == "day":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        quarter_month = ((now.month - 1) // 3) * 3 + 1
        start_date = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = None
    
    date_filter = {"created_at": {"$gte": start_date.isoformat()}} if start_date else {}
    
    # Aggregate revenue by source
    pipeline = [
        {"$match": {**date_filter, "payment_status": "paid"}},
        {"$group": {
            "_id": "$source",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    
    by_source_result = await db.revenue_records.aggregate(pipeline).to_list(None)
    by_source = {item["_id"]: {"total": item["total"], "count": item["count"]} for item in by_source_result}
    
    # Calculate totals
    total_revenue = sum(item["total"] for item in by_source.values())
    total_transactions = sum(item["count"] for item in by_source.values())
    
    # Get pending revenue
    pending_pipeline = [
        {"$match": {"payment_status": "pending"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    pending_result = await db.revenue_records.aggregate(pending_pipeline).to_list(None)
    pending_revenue = pending_result[0]["total"] if pending_result else 0
    pending_count = pending_result[0]["count"] if pending_result else 0
    
    # Get overdue revenue
    overdue_pipeline = [
        {"$match": {"payment_status": "overdue"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    overdue_result = await db.revenue_records.aggregate(overdue_pipeline).to_list(None)
    overdue_revenue = overdue_result[0]["total"] if overdue_result else 0
    
    return {
        "period": period,
        "start_date": start_date.isoformat() if start_date else None,
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "pending_revenue": pending_revenue,
        "pending_count": pending_count,
        "overdue_revenue": overdue_revenue,
        "by_source": {
            "attorney_network": by_source.get("attorney_network", {"total": 0, "count": 0}),
            "collections": by_source.get("collections", {"total": 0, "count": 0}),
            "credit_repair": by_source.get("credit_repair", {"total": 0, "count": 0}),
            "outsourcing": by_source.get("outsourcing", {"total": 0, "count": 0}),
            "digital_products": by_source.get("digital_products", {"total": 0, "count": 0})
        }
    }


@revenue_router.get("/dashboard/trends")
async def get_revenue_trends(
    authorization: Optional[str] = Header(None),
    months: int = 12
):
    """Get revenue trends over time"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Calculate start date
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=months * 30)
    
    # Aggregate by month
    pipeline = [
        {"$match": {"created_at": {"$gte": start_date.isoformat()}, "payment_status": "paid"}},
        {"$addFields": {
            "month": {"$substr": ["$created_at", 0, 7]}  # Extract YYYY-MM
        }},
        {"$group": {
            "_id": {"month": "$month", "source": "$source"},
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.month": 1}}
    ]
    
    result = await db.revenue_records.aggregate(pipeline).to_list(None)
    
    # Organize by month
    monthly_data = {}
    for item in result:
        month = item["_id"]["month"]
        source = item["_id"]["source"]
        if month not in monthly_data:
            monthly_data[month] = {
                "month": month,
                "attorney_network": 0,
                "collections": 0,
                "credit_repair": 0,
                "outsourcing": 0,
                "digital_products": 0,
                "total": 0
            }
        monthly_data[month][source] = item["total"]
        monthly_data[month]["total"] += item["total"]
    
    # Sort by month
    trends = sorted(monthly_data.values(), key=lambda x: x["month"])
    
    return {"months": months, "trends": trends}


@revenue_router.get("/dashboard/projected")
async def get_projected_revenue(authorization: Optional[str] = Header(None)):
    """Get projected revenue based on pending and historical data"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Get pending revenue (expected to be paid)
    pending_pipeline = [
        {"$match": {"payment_status": "pending"}},
        {"$group": {"_id": "$source", "total": {"$sum": "$amount"}}}
    ]
    pending_result = await db.revenue_records.aggregate(pending_pipeline).to_list(None)
    pending_by_source = {item["_id"]: item["total"] for item in pending_result}
    
    # Get last 3 months average for projections
    now = datetime.now(timezone.utc)
    three_months_ago = now - timedelta(days=90)
    
    avg_pipeline = [
        {"$match": {"created_at": {"$gte": three_months_ago.isoformat()}, "payment_status": "paid"}},
        {"$group": {"_id": "$source", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    avg_result = await db.revenue_records.aggregate(avg_pipeline).to_list(None)
    
    projections = {}
    for item in avg_result:
        source = item["_id"]
        monthly_avg = item["total"] / 3
        projections[source] = {
            "monthly_average": round(monthly_avg, 2),
            "quarterly_projection": round(monthly_avg * 3, 2),
            "annual_projection": round(monthly_avg * 12, 2),
            "pending": pending_by_source.get(source, 0)
        }
    
    total_monthly_avg = sum(p["monthly_average"] for p in projections.values())
    total_pending = sum(pending_by_source.values())
    
    return {
        "projections": projections,
        "total_monthly_average": round(total_monthly_avg, 2),
        "total_quarterly_projection": round(total_monthly_avg * 3, 2),
        "total_annual_projection": round(total_monthly_avg * 12, 2),
        "total_pending": total_pending
    }


# ==================== SOURCE-SPECIFIC AGGREGATIONS ====================

@revenue_router.get("/attorney-network/summary")
async def get_attorney_network_revenue(authorization: Optional[str] = Header(None)):
    """Get detailed attorney network revenue breakdown"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Get from attorney_cases collection
    settled_cases = await db.attorney_cases.find({"status": "resolved"}, {"_id": 0}).to_list(None)
    
    total_initial_fees = 0
    total_commissions = 0
    total_bid_bonuses = 0
    cases_by_type = {}
    
    for case in settled_cases:
        total_initial_fees += 500  # Standard initial fee
        commission = case.get("commission_amount", 0)
        total_commissions += commission
        bid_bonus = case.get("bid_bonus_amount", 0)
        total_bid_bonuses += bid_bonus
        
        case_type = case.get("case_type", "other")
        if case_type not in cases_by_type:
            cases_by_type[case_type] = {"count": 0, "revenue": 0}
        cases_by_type[case_type]["count"] += 1
        cases_by_type[case_type]["revenue"] += 500 + commission + bid_bonus
    
    # Get pending cases for projected revenue
    pending_cases = await db.attorney_cases.count_documents({"status": {"$in": ["assigned", "in_progress"]}})
    
    return {
        "total_revenue": total_initial_fees + total_commissions + total_bid_bonuses,
        "breakdown": {
            "initial_fees": total_initial_fees,
            "commissions": total_commissions,
            "bid_bonuses": total_bid_bonuses
        },
        "cases_resolved": len(settled_cases),
        "cases_pending": pending_cases,
        "projected_pending_revenue": pending_cases * 500,  # Minimum expected
        "by_case_type": cases_by_type
    }


@revenue_router.get("/collections/summary")
async def get_collections_revenue(authorization: Optional[str] = Header(None)):
    """Get detailed collections revenue breakdown"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Get all collections accounts with payments
    pipeline = [
        {"$unwind": {"path": "$payments", "preserveNullAndEmptyArrays": False}},
        {"$group": {
            "_id": None,
            "total_collected": {"$sum": "$payments.amount"},
            "payment_count": {"$sum": 1}
        }}
    ]
    
    result = await db.collections_accounts.aggregate(pipeline).to_list(None)
    total_collected = result[0]["total_collected"] if result else 0
    payment_count = result[0]["payment_count"] if result else 0
    
    # Get by tier
    tier_pipeline = [
        {"$match": {"status": {"$in": ["settled", "payment_plan"]}}},
        {"$group": {
            "_id": "$tier",
            "count": {"$sum": 1},
            "total_balance": {"$sum": "$current_balance"}
        }}
    ]
    tier_result = await db.collections_accounts.aggregate(tier_pipeline).to_list(None)
    by_tier = {str(item["_id"]): {"count": item["count"], "balance": item["total_balance"]} for item in tier_result}
    
    # Get active vs settled counts
    active_count = await db.collections_accounts.count_documents({"status": "active"})
    settled_count = await db.collections_accounts.count_documents({"status": "settled"})
    payment_plan_count = await db.collections_accounts.count_documents({"status": "payment_plan"})
    
    # Get outstanding balance
    outstanding_pipeline = [
        {"$match": {"status": {"$in": ["active", "payment_plan"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$current_balance"}}}
    ]
    outstanding_result = await db.collections_accounts.aggregate(outstanding_pipeline).to_list(None)
    outstanding_balance = outstanding_result[0]["total"] if outstanding_result else 0
    
    return {
        "total_collected": total_collected,
        "payment_count": payment_count,
        "outstanding_balance": outstanding_balance,
        "accounts": {
            "active": active_count,
            "settled": settled_count,
            "payment_plan": payment_plan_count
        },
        "by_tier": by_tier
    }


@revenue_router.get("/credit-repair/summary")
async def get_credit_repair_revenue(authorization: Optional[str] = Header(None)):
    """Get credit repair client revenue"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Get active clients with their payment info
    active_clients = await db.clients.count_documents({"status": "active"})
    total_clients = await db.clients.count_documents({})
    
    # Calculate monthly recurring revenue (MRR)
    # Assuming average monthly fee from service plans
    avg_monthly_fee = 99  # Default average
    
    service_plans = await db.collections_service_plans.find({}, {"_id": 0}).to_list(None)
    if service_plans:
        total_fees = sum(plan.get("monthly_fee", 99) for plan in service_plans)
        avg_monthly_fee = total_fees / len(service_plans) if service_plans else 99
    
    mrr = active_clients * avg_monthly_fee
    arr = mrr * 12
    
    # Get setup fees collected (one-time)
    setup_pipeline = [
        {"$match": {"setup_fee_paid": True}},
        {"$count": "total"}
    ]
    setup_result = await db.clients.aggregate(setup_pipeline).to_list(None)
    setup_fees_collected = (setup_result[0]["total"] if setup_result else 0) * 199  # Avg setup fee
    
    return {
        "active_clients": active_clients,
        "total_clients": total_clients,
        "monthly_recurring_revenue": round(mrr, 2),
        "annual_recurring_revenue": round(arr, 2),
        "setup_fees_collected": setup_fees_collected,
        "average_monthly_fee": round(avg_monthly_fee, 2),
        "churn_rate": 0  # Would need historical data to calculate
    }


@revenue_router.get("/outsourcing/summary")
async def get_outsourcing_revenue(authorization: Optional[str] = Header(None)):
    """Get outsourcing partner revenue"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Get from outsource_invoices
    paid_pipeline = [
        {"$match": {"status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    paid_result = await db.outsource_invoices.aggregate(paid_pipeline).to_list(None)
    total_paid = paid_result[0]["total"] if paid_result else 0
    paid_count = paid_result[0]["count"] if paid_result else 0
    
    # Get pending invoices
    pending_pipeline = [
        {"$match": {"status": {"$in": ["pending", "sent"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    pending_result = await db.outsource_invoices.aggregate(pending_pipeline).to_list(None)
    total_pending = pending_result[0]["total"] if pending_result else 0
    pending_count = pending_result[0]["count"] if pending_result else 0
    
    # Get active partners
    active_partners = await db.outsource_partners.count_documents({"status": "active"})
    total_partners = await db.outsource_partners.count_documents({})
    
    return {
        "total_revenue": total_paid,
        "invoices_paid": paid_count,
        "pending_revenue": total_pending,
        "invoices_pending": pending_count,
        "active_partners": active_partners,
        "total_partners": total_partners
    }


# ==================== EXPORT ====================

@revenue_router.get("/export")
async def export_revenue_data(
    authorization: Optional[str] = Header(None),
    format: str = "json",  # json or csv
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Export revenue data"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    records = await db.revenue_records.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)
    
    if format == "csv":
        # Generate CSV string
        if not records:
            return {"csv": "No data found"}
        
        headers = list(records[0].keys())
        csv_lines = [",".join(headers)]
        for record in records:
            row = [str(record.get(h, "")) for h in headers]
            csv_lines.append(",".join(row))
        
        return {"csv": "\n".join(csv_lines), "filename": f"revenue_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    
    return {"records": records, "count": len(records)}
