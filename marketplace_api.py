"""
Credlocity Attorney Marketplace API
Comprehensive case marketplace with bidding engine, agreement generation,
and attorney portal functionality.
"""

from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from decimal import Decimal
import os
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
client = get_client(MONGO_URL)
db = client[DB_NAME]

marketplace_router = APIRouter(prefix="/api/marketplace", tags=["Attorney Marketplace"])


# ==================== AUTHENTICATION ====================

async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from JWT token or database token"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    
    # First, try JWT decode (for admin users)
    try:
        from jose import jwt, JWTError
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if email:
            # Check main users (admins)
            user = await db.users.find_one({"email": email}, {"_id": 0, "hashed_password": 0})
            if user:
                if user.get("role") == "super_admin":
                    user["role"] = "admin"
                return user
    except:
        pass
    
    # Fallback: Check for attorney portal token (database-stored)
    attorney = await db.attorneys.find_one({"token": token}, {"_id": 0, "password_hash": 0})
    if attorney:
        attorney["is_attorney"] = True
        return attorney
    
    return None


async def get_attorney_from_token(authorization: Optional[str] = Header(None)):
    """Get attorney user only"""
    user = await get_current_user(authorization)
    if not user or not user.get("is_attorney"):
        return None
    return user


def require_attorney(user):
    """Require attorney authentication"""
    if not user or not user.get("is_attorney"):
        raise HTTPException(status_code=403, detail="Attorney authentication required")


def require_admin(user):
    """Require admin authentication"""
    if not user or user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin authentication required")


# ==================== NOTIFICATION SYSTEM ====================

async def create_notification(
    recipient_id: str,
    recipient_type: str,  # 'attorney', 'company', 'admin'
    notification_type: str,
    title: str,
    message: str,
    related_case_id: str = None,
    related_bid_id: str = None,
    priority: str = "normal",  # 'low', 'normal', 'high', 'urgent'
    action_url: str = None
):
    """Create a notification for a user"""
    notification = {
        "id": str(uuid4()),
        "recipient_id": recipient_id,
        "recipient_type": recipient_type,
        "notification_type": notification_type,
        "title": title,
        "message": message,
        "related_case_id": related_case_id,
        "related_bid_id": related_bid_id,
        "priority": priority,
        "action_url": action_url,
        "is_read": False,
        "is_email_sent": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.notifications.insert_one(notification)
    return notification


async def notify_outbid_attorneys(case_id: str, new_highest_bid: float, new_bidder_id: str, case_title: str):
    """Notify all attorneys who have been outbid on a case"""
    case = await db.marketplace_cases.find_one({"case_id": case_id})
    if not case:
        return
    
    bids = case.get("bids", [])
    
    for bid in bids:
        # Skip the new highest bidder and non-active bids
        if bid.get("attorney_id") == new_bidder_id or bid.get("status") != "active":
            continue
        
        attorney_id = bid.get("attorney_id")
        bid_amount = bid.get("total_bid_value", 0)
        
        # Only notify if they were previously winning or close to winning
        if bid_amount > 0:
            await create_notification(
                recipient_id=attorney_id,
                recipient_type="attorney",
                notification_type="outbid",
                title="You've Been Outbid!",
                message=f"Another attorney has placed a higher bid of ${new_highest_bid:,.2f} on case \"{case_title}\". Your current bid is ${bid_amount:,.2f}. Increase your bid to stay competitive.",
                related_case_id=case_id,
                related_bid_id=bid.get("bid_id"),
                priority="high",
                action_url=f"/attorney/marketplace/{case_id}"
            )


async def notify_bid_accepted(attorney_id: str, case_id: str, case_title: str, bid_amount: float):
    """Notify attorney when their bid is accepted"""
    await create_notification(
        recipient_id=attorney_id,
        recipient_type="attorney",
        notification_type="bid_accepted",
        title="Congratulations! Your Bid Was Accepted",
        message=f"Your bid of ${bid_amount:,.2f} on case \"{case_title}\" has been accepted. Please review the case details and sign the attorney agreement to proceed.",
        related_case_id=case_id,
        priority="urgent",
        action_url=f"/attorney/cases/{case_id}"
    )


async def notify_bidding_deadline(case_id: str, hours_remaining: int):
    """Notify all active bidders about approaching deadline"""
    case = await db.marketplace_cases.find_one({"case_id": case_id})
    if not case:
        return
    
    bids = case.get("bids", [])
    case_title = case.get("title", "Case")
    
    for bid in bids:
        if bid.get("status") != "active":
            continue
        
        await create_notification(
            recipient_id=bid.get("attorney_id"),
            recipient_type="attorney",
            notification_type="bidding_deadline",
            title=f"Bidding Deadline in {hours_remaining} Hours",
            message=f"The bidding period for \"{case_title}\" ends in {hours_remaining} hours. Review your bid and make any final adjustments.",
            related_case_id=case_id,
            priority="high" if hours_remaining <= 6 else "normal",
            action_url=f"/attorney/marketplace/{case_id}"
        )


# ==================== COMMISSION CALCULATION ====================

# Revenue split configuration (can be overridden per-company or per-case)
DEFAULT_REVENUE_SPLIT = {
    "credlocity_percentage": 40,  # Credlocity takes 40%
    "company_percentage": 60,     # Referring company gets 60%
}


def calculate_commission(settlement_amount: float, bonus_commission_rate: float = 0) -> dict:
    """Calculate commission based on tier system"""
    settlement_amount = float(settlement_amount)
    
    if settlement_amount <= 5000:
        return {
            "tier": 0,
            "tier_description": "Below minimum for commission",
            "standard_rate": 0,
            "bonus_rate": bonus_commission_rate,
            "total_rate": bonus_commission_rate,
            "commission_amount": settlement_amount * bonus_commission_rate,
            "initial_fee": 500,
            "total_due": 500 + (settlement_amount * bonus_commission_rate)
        }
    
    if settlement_amount <= 7999:
        rate = 0.03
        tier = 1
        desc = "Tier 1: $5,001-$7,999 at 3%"
    elif settlement_amount <= 10999:
        rate = 0.04
        tier = 2
        desc = "Tier 2: $8,000-$10,999 at 4%"
    elif settlement_amount <= 14999:
        rate = 0.05
        tier = 3
        desc = "Tier 3: $11,000-$14,999 at 5%"
    elif settlement_amount < 20000:
        rate = 0.10
        tier = 4
        desc = "Tier 4: $15,000-$19,999 at 10%"
    else:
        # $20,000+ with progressive tiers
        over_20k = settlement_amount - 20000
        additional_tiers = int(over_20k / 5000)
        rate = 0.10 + (additional_tiers * 0.05)
        rate = min(rate, 0.30)  # Cap at 30%
        tier = 4 + additional_tiers
        desc = f"Tier {tier}: $20,000+ at {int(rate * 100)}%"
    
    total_rate = rate + bonus_commission_rate
    commission = settlement_amount * total_rate
    
    return {
        "tier": tier,
        "tier_description": desc,
        "standard_rate": rate,
        "bonus_rate": bonus_commission_rate,
        "total_rate": total_rate,
        "commission_amount": round(commission, 2),
        "initial_fee": 500,
        "total_due": round(500 + commission, 2)
    }


def calculate_revenue_split(
    total_revenue: float,
    company_id: str = None,
    custom_split: dict = None
) -> dict:
    """
    Calculate revenue split between Credlocity and the referring company.
    
    Default split is 40% Credlocity, 60% Company.
    Can be customized per-company or per-case.
    
    Args:
        total_revenue: The total revenue from the case (initial fee + commission)
        company_id: Optional company ID to look up custom split rates
        custom_split: Optional custom split percentages
    
    Returns:
        Dictionary with split details
    """
    # Use custom split if provided, otherwise use default
    split = custom_split or DEFAULT_REVENUE_SPLIT
    
    credlocity_pct = split.get("credlocity_percentage", 40) / 100
    company_pct = split.get("company_percentage", 60) / 100
    
    # Calculate amounts
    credlocity_amount = round(total_revenue * credlocity_pct, 2)
    company_amount = round(total_revenue * company_pct, 2)
    
    return {
        "total_revenue": total_revenue,
        "credlocity_percentage": split.get("credlocity_percentage", 40),
        "company_percentage": split.get("company_percentage", 60),
        "credlocity_amount": credlocity_amount,
        "company_amount": company_amount,
        "split_timestamp": datetime.now(timezone.utc).isoformat()
    }


async def process_case_settlement_revenue(
    case_id: str,
    settlement_amount: float,
    commission_amount: float,
    initial_fee: float = 500
) -> dict:
    """
    Process revenue for a settled case, including:
    - Recording the total revenue
    - Calculating the Credlocity/Company split
    - Creating transaction records
    - Updating company payouts
    
    Returns revenue split details
    """
    total_revenue = initial_fee + commission_amount
    
    # Get case to find the referring company
    case = await db.marketplace_cases.find_one({"case_id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    company_id = case.get("company_id") or case.get("referring_company_id")
    
    # Look up custom split for this company if exists
    custom_split = None
    if company_id:
        company = await db.companies.find_one({"id": company_id})
        if company and company.get("revenue_split"):
            custom_split = company.get("revenue_split")
    
    # Calculate the split
    split = calculate_revenue_split(total_revenue, company_id, custom_split)
    
    # Record the revenue split transaction
    revenue_record = {
        "id": str(uuid4()),
        "case_id": case_id,
        "company_id": company_id,
        "settlement_amount": settlement_amount,
        "initial_fee": initial_fee,
        "commission_amount": commission_amount,
        "total_revenue": total_revenue,
        "split_details": split,
        "status": "pending_payout",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.revenue_splits.insert_one(revenue_record)
    
    # Update case with revenue split info
    await db.marketplace_cases.update_one(
        {"case_id": case_id},
        {"$set": {"revenue_split": split}}
    )
    
    # Update company's pending payout balance if applicable
    if company_id:
        await db.companies.update_one(
            {"id": company_id},
            {
                "$inc": {"pending_payout": split["company_amount"]},
                "$push": {
                    "payout_transactions": {
                        "id": str(uuid4()),
                        "case_id": case_id,
                        "amount": split["company_amount"],
                        "status": "pending",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            }
        )
    
    # Update Credlocity revenue tracking
    await db.platform_revenue.update_one(
        {"period": datetime.now(timezone.utc).strftime("%Y-%m")},
        {
            "$inc": {
                "total_revenue": split["credlocity_amount"],
                "case_count": 1
            },
            "$push": {
                "revenue_entries": {
                    "case_id": case_id,
                    "amount": split["credlocity_amount"],
                    "date": datetime.now(timezone.utc).isoformat()
                }
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {
        "revenue_record_id": revenue_record["id"],
        "split_details": split,
        "company_payout_pending": split["company_amount"] if company_id else 0,
        "credlocity_revenue": split["credlocity_amount"]
    }


def anonymize_client(client_info: dict) -> dict:
    """Anonymize client information for marketplace display"""
    first_name = client_info.get("first_name", "")
    last_name = client_info.get("last_name", "")
    city = client_info.get("city", "")
    state = client_info.get("state", "")
    
    return {
        "display_name": f"{first_name} {last_name[0]}." if first_name and last_name else "Anonymous",
        "location": f"{city}, {state}" if city and state else "Location Unavailable"
    }


# ==================== CASE MARKETPLACE ====================

@marketplace_router.get("/cases")
async def list_marketplace_cases(
    authorization: Optional[str] = Header(None),
    category: Optional[str] = None,  # standard, bidding, class_action
    practice_area: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    status: str = "available",
    sort_by: str = "newest",
    skip: int = 0,
    limit: int = 20
):
    """List available cases in marketplace"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    query = {"availability_status": "open"}
    
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    if practice_area:
        query["practice_areas"] = practice_area
    if jurisdiction:
        query["jurisdiction"] = {"$regex": jurisdiction, "$options": "i"}
    if min_value:
        query["estimated_value"] = {"$gte": min_value}
    if max_value:
        if "estimated_value" in query:
            query["estimated_value"]["$lte"] = max_value
        else:
            query["estimated_value"] = {"$lte": max_value}
    
    # Sort options
    sort_field = "created_at"
    sort_dir = -1
    if sort_by == "value_high":
        sort_field = "estimated_value"
        sort_dir = -1
    elif sort_by == "value_low":
        sort_field = "estimated_value"
        sort_dir = 1
    elif sort_by == "deadline":
        sort_field = "deadline"
        sort_dir = 1
    
    # Projection - hide sensitive client info
    projection = {
        "_id": 0,
        "client_full_info": 0,
        "admin_settings.internal_notes": 0
    }
    
    cases = await db.marketplace_cases.find(query, projection).sort(sort_field, sort_dir).skip(skip).limit(limit).to_list(None)
    total = await db.marketplace_cases.count_documents(query)
    
    # Get active attorney count for marketplace display
    active_attorneys = await db.attorneys.count_documents({"status": {"$in": ["approved", "active"]}})
    
    # Anonymize client info for each case
    for case in cases:
        if "client_first_name" in case:
            case["client_display"] = {
                "name": f"{case.get('client_first_name', '')} {case.get('client_last_initial', '')}.",
                "location": case.get("client_location_display", "")
            }
    
    return {
        "cases": cases,
        "total": total,
        "skip": skip,
        "limit": limit,
        "network_stats": {
            "active_attorneys": active_attorneys
        }
    }


@marketplace_router.get("/cases/{case_id}")
async def get_case_details(case_id: str, authorization: Optional[str] = Header(None)):
    """Get detailed case information"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Base projection - hide sensitive info initially
    projection = {"_id": 0}
    
    case = await db.marketplace_cases.find_one({"case_id": case_id}, projection)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Check if attorney has access to full client info
    is_assigned_attorney = False
    if user.get("is_attorney"):
        assignment = case.get("assignment")
        if assignment and assignment.get("pledged_to_attorney_id") == user.get("id"):
            is_assigned_attorney = True
    
    # If not assigned or not admin, hide full client info
    if not is_assigned_attorney and user.get("role") not in ["admin", "director"]:
        case.pop("client_full_info", None)
        case["client_display"] = {
            "name": f"{case.get('client_first_name', '')} {case.get('client_last_initial', '')}.",
            "location": case.get("client_location_display", "")
        }
    
    # Calculate potential fee breakdown
    estimated_value = case.get("estimated_value", 0)
    case["fee_breakdown"] = calculate_commission(estimated_value)
    
    # Track view
    if user.get("is_attorney"):
        await db.marketplace_cases.update_one(
            {"case_id": case_id},
            {
                "$inc": {"views_count": 1},
                "$addToSet": {"unique_attorney_views": user.get("id")}
            }
        )
    
    return case


@marketplace_router.get("/cases/{case_id}/bids")
async def get_case_bids(case_id: str, authorization: Optional[str] = Header(None)):
    """Get current bids for a bidding case"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    case = await db.marketplace_cases.find_one({"case_id": case_id}, {"_id": 0, "bids": 1, "bidding_info": 1, "category": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    if case.get("category") not in ["bidding", "class_action"]:
        raise HTTPException(status_code=400, detail="This case does not accept bids")
    
    bids = case.get("bids", [])
    
    # For attorneys, hide other attorneys' detailed bid info
    if user.get("is_attorney"):
        sanitized_bids = []
        for bid in bids:
            if bid.get("attorney_id") == user.get("id"):
                # Show full details for own bid
                sanitized_bids.append(bid)
            else:
                # Show limited info for others
                sanitized_bids.append({
                    "attorney_name": bid.get("attorney_name", "Anonymous"),
                    "firm_name": bid.get("firm_name", ""),
                    "total_bid_value": bid.get("total_bid_value", 0),
                    "status": bid.get("status"),
                    "submitted_at": bid.get("submitted_at")
                })
        bids = sanitized_bids
    
    return {
        "case_id": case_id,
        "bidding_info": case.get("bidding_info", {}),
        "bids": bids,
        "bid_count": len(bids)
    }


# ==================== BIDDING ENGINE ====================

@marketplace_router.post("/cases/{case_id}/bid")
async def place_bid(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Place a bid on a bidding case"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    case = await db.marketplace_cases.find_one({"case_id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    if case.get("category") not in ["bidding", "class_action"]:
        raise HTTPException(status_code=400, detail="This case does not accept bids")
    
    if case.get("availability_status") != "open":
        raise HTTPException(status_code=400, detail="Bidding is closed for this case")
    
    bidding_info = case.get("bidding_info", {})
    if bidding_info.get("bidding_deadline"):
        deadline = datetime.fromisoformat(bidding_info["bidding_deadline"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > deadline:
            raise HTTPException(status_code=400, detail="Bidding deadline has passed")
    
    # Get attorney's current balance
    attorney = await db.attorneys.find_one({"id": user["id"]})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney profile not found")
    
    account_balance = attorney.get("account_balance", 0)
    
    # Calculate bid components
    upfront_bonus = float(data.get("upfront_bonus", 0))
    commission_bonus_percentage = float(data.get("commission_bonus_percentage", 0))
    client_bonus_percentage = float(data.get("client_bonus_percentage", 0))
    
    # Validate ranges
    if upfront_bonus < 0 or upfront_bonus > 2500:
        raise HTTPException(status_code=400, detail="Upfront bonus must be between $0 and $2,500")
    if commission_bonus_percentage < 0 or commission_bonus_percentage > 0.15:
        raise HTTPException(status_code=400, detail="Commission bonus must be between 0% and 15%")
    if client_bonus_percentage < 0 or client_bonus_percentage > 0.20:
        raise HTTPException(status_code=400, detail="Client bonus must be between 0% and 20%")
    
    # Calculate total bid
    estimated_value = case.get("estimated_value", 0)
    standard_initial_fee = 500
    standard_commission = calculate_commission(estimated_value)["standard_rate"]
    
    total_initial = standard_initial_fee + upfront_bonus
    total_commission_rate = standard_commission + commission_bonus_percentage
    estimated_commission = estimated_value * total_commission_rate
    total_bid_value = total_initial + estimated_commission
    
    # Check sufficient balance
    if account_balance < total_bid_value:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient balance. Required: ${total_bid_value:.2f}, Available: ${account_balance:.2f}"
        )
    
    # Check for existing bid from this attorney
    existing_bid = next((b for b in case.get("bids", []) if b.get("attorney_id") == user["id"]), None)
    if existing_bid and existing_bid.get("status") == "active":
        # Release old reserve and update bid
        old_reserve = existing_bid.get("reserved_amount", 0)
        account_balance += old_reserve
    
    # Create bid record
    bid = {
        "bid_id": str(uuid4()),
        "attorney_id": user["id"],
        "attorney_name": user.get("full_name", ""),
        "firm_name": user.get("firm_name", ""),
        "bid_components": {
            "standard_initial_fee": standard_initial_fee,
            "upfront_bonus": upfront_bonus,
            "commission_bonus_percentage": commission_bonus_percentage,
            "client_bonus_percentage": client_bonus_percentage
        },
        "estimated_commission_amount": round(estimated_commission, 2),
        "total_bid_value": round(total_bid_value, 2),
        "status": "active",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "reserved_amount": round(total_bid_value, 2),
        "reserve_released": False,
        "attorney_notes": data.get("notes", "")
    }
    
    # Determine if this is the new highest bid
    current_highest = bidding_info.get("highest_bid_amount", 0)
    is_highest = total_bid_value > current_highest
    
    # Update case with new bid
    if existing_bid:
        # Update existing bid
        await db.marketplace_cases.update_one(
            {"case_id": case_id, "bids.attorney_id": user["id"]},
            {
                "$set": {"bids.$": bid},
                "$inc": {"bidding_info.current_bid_count": 0}
            }
        )
    else:
        # Add new bid
        await db.marketplace_cases.update_one(
            {"case_id": case_id},
            {
                "$push": {"bids": bid},
                "$inc": {"bidding_info.current_bid_count": 1}
            }
        )
    
    # Update highest bid if applicable
    if is_highest:
        await db.marketplace_cases.update_one(
            {"case_id": case_id},
            {"$set": {"bidding_info.highest_bid_amount": total_bid_value}}
        )
    
    # Reserve funds from attorney account
    new_balance = account_balance - total_bid_value
    await db.attorneys.update_one(
        {"id": user["id"]},
        {
            "$set": {"account_balance": new_balance},
            "$push": {
                "account_transactions": {
                    "transaction_id": str(uuid4()),
                    "type": "bid_reserve",
                    "amount": -total_bid_value,
                    "description": f"Bid reserve for {case_id}",
                    "related_case_id": case_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "balance_after": new_balance
                }
            }
        }
    )
    
    # Notify outbid attorneys if this is the new highest bid
    if is_highest:
        case_title = case.get("title", "Case")
        await notify_outbid_attorneys(case_id, total_bid_value, user["id"], case_title)
    
    return {
        "message": "Bid placed successfully",
        "bid_id": bid["bid_id"],
        "total_bid_value": total_bid_value,
        "is_highest_bid": is_highest,
        "new_account_balance": new_balance
    }


@marketplace_router.delete("/cases/{case_id}/bid")
async def withdraw_bid(case_id: str, authorization: Optional[str] = Header(None)):
    """Withdraw a bid"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    case = await db.marketplace_cases.find_one({"case_id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Find attorney's bid
    bid = next((b for b in case.get("bids", []) if b.get("attorney_id") == user["id"] and b.get("status") == "active"), None)
    if not bid:
        raise HTTPException(status_code=404, detail="No active bid found")
    
    # Release reserved funds
    reserved_amount = bid.get("reserved_amount", 0)
    
    # Update bid status
    await db.marketplace_cases.update_one(
        {"case_id": case_id, "bids.attorney_id": user["id"]},
        {
            "$set": {
                "bids.$.status": "withdrawn",
                "bids.$.reserve_released": True
            },
            "$inc": {"bidding_info.current_bid_count": -1}
        }
    )
    
    # Return reserved funds
    await db.attorneys.update_one(
        {"id": user["id"]},
        {
            "$inc": {"account_balance": reserved_amount},
            "$push": {
                "account_transactions": {
                    "transaction_id": str(uuid4()),
                    "type": "bid_release",
                    "amount": reserved_amount,
                    "description": f"Bid withdrawal refund for {case_id}",
                    "related_case_id": case_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        }
    )
    
    return {"message": "Bid withdrawn successfully", "refunded_amount": reserved_amount}


# ==================== CASE PLEDGING (Standard Cases) ====================

@marketplace_router.post("/cases/{case_id}/pledge")
async def pledge_case(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Pledge to take a standard case"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    case = await db.marketplace_cases.find_one({"case_id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    if case.get("category") != "standard":
        raise HTTPException(status_code=400, detail="This case requires bidding, not pledging")
    
    if case.get("status") != "available":
        raise HTTPException(status_code=400, detail="Case is no longer available")
    
    # Verify agreement acceptance
    if not data.get("agreement_accepted"):
        raise HTTPException(status_code=400, detail="You must accept the referral agreement")
    
    # Generate agreement
    agreement_id = f"AGR-{case_id}-{user['id'][:8]}-{datetime.now().strftime('%Y%m%d')}"
    
    assignment = {
        "pledged_to_attorney_id": user["id"],
        "pledged_to_attorney_name": user.get("full_name", ""),
        "pledged_date": datetime.now(timezone.utc).isoformat(),
        "pledge_type": "standard",
        "agreement_generated": True,
        "agreement_generated_date": datetime.now(timezone.utc).isoformat(),
        "agreement_id": agreement_id,
        "agreement_accepted": True,
        "agreement_accepted_date": datetime.now(timezone.utc).isoformat(),
        "agreement_acceptance_ip": data.get("ip_address", ""),
        "initial_fee_amount": 500,
        "initial_fee_paid": False,
        "retainer_download_enabled": False
    }
    
    # Update case
    await db.marketplace_cases.update_one(
        {"case_id": case_id},
        {
            "$set": {
                "status": "pledged",
                "availability_status": "assigned",
                "assignment": assignment,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Add to attorney's active cases
    await db.attorneys.update_one(
        {"id": user["id"]},
        {
            "$push": {
                "active_cases": {
                    "case_id": case_id,
                    "case_title": case.get("title", ""),
                    "status": "pledged",
                    "assigned_date": datetime.now(timezone.utc).isoformat(),
                    "days_active": 0
                }
            },
            "$inc": {"active_cases_count": 1, "performance.cases_pledged": 1}
        }
    )
    
    return {
        "message": "Case pledged successfully",
        "case_id": case_id,
        "agreement_id": agreement_id,
        "next_step": "Await client approval, then pay initial fee to download retainer"
    }


# ==================== ATTORNEY PORTAL ====================

@marketplace_router.get("/attorney/dashboard")
async def get_attorney_dashboard(authorization: Optional[str] = Header(None)):
    """Get attorney portal dashboard data"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    attorney = await db.attorneys.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0, "token": 0})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney profile not found")
    
    # Get case counts
    active_cases = await db.marketplace_cases.count_documents({
        "assignment.pledged_to_attorney_id": user["id"],
        "status": {"$in": ["pledged", "in_progress"]}
    })
    
    available_cases = await db.marketplace_cases.count_documents({
        "status": "available",
        "availability_status": "open"
    })
    
    # Get pending actions
    pending_payments = await db.marketplace_cases.count_documents({
        "assignment.pledged_to_attorney_id": user["id"],
        "assignment.initial_fee_paid": False,
        "status": "pledged"
    })
    
    overdue_updates = await db.marketplace_cases.count_documents({
        "assignment.pledged_to_attorney_id": user["id"],
        "case_progress.status_update_overdue": True
    })
    
    # Recent activity
    recent_cases = await db.marketplace_cases.find(
        {"assignment.pledged_to_attorney_id": user["id"]},
        {"_id": 0, "case_id": 1, "title": 1, "status": 1, "assignment": 1, "settlement": 1}
    ).sort("updated_at", -1).limit(5).to_list(None)
    
    # Calculate earnings
    total_earnings = attorney.get("total_earnings", 0)
    account_balance = attorney.get("account_balance", 0)
    
    return {
        "attorney": {
            "id": attorney.get("id"),
            "name": attorney.get("full_name"),
            "firm": attorney.get("firm_name"),
            "email": attorney.get("email")
        },
        "stats": {
            "active_cases": active_cases,
            "available_cases": available_cases,
            "account_balance": account_balance,
            "total_earnings": total_earnings
        },
        "alerts": {
            "pending_payments": pending_payments,
            "overdue_updates": overdue_updates
        },
        "recent_cases": recent_cases,
        "performance": attorney.get("performance", {})
    }


@marketplace_router.get("/attorney/my-cases")
async def get_attorney_cases(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
):
    """Get attorney's cases"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    # Match on either field (legacy and new structure)
    query = {
        "$or": [
            {"assignment.pledged_to_attorney_id": user["id"]},
            {"assigned_attorney_id": user["id"]}
        ]
    }
    if status:
        query["status"] = status
    
    cases = await db.marketplace_cases.find(
        query,
        {"_id": 0, "admin_settings.internal_notes": 0}
    ).sort("updated_at", -1).skip(skip).limit(limit).to_list(None)
    
    total = await db.marketplace_cases.count_documents(query)
    
    return {"cases": cases, "total": total}


@marketplace_router.get("/attorney/case/{case_id}")
async def get_attorney_case_detail(
    case_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get detailed case information for attorney"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    # Find the case assigned to this attorney
    case = await db.marketplace_cases.find_one(
        {
            "case_id": case_id,
            "$or": [
                {"assignment.pledged_to_attorney_id": user["id"]},
                {"assigned_attorney_id": user["id"]}
            ]
        },
        {"_id": 0, "admin_settings.internal_notes": 0}
    )
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    # Get case update history
    updates = await db.case_updates.find(
        {"case_id": case_id, "attorney_id": user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return {"case": case, "updates": updates}


@marketplace_router.post("/attorney/cases/{case_id}/status-update")
async def submit_status_update(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Submit case status update"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    case = await db.marketplace_cases.find_one({
        "case_id": case_id,
        "assignment.pledged_to_attorney_id": user["id"]
    })
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    update = {
        "update_id": str(uuid4()),
        "attorney_id": user["id"],
        "status": data.get("status"),
        "description": data.get("description"),
        "next_action": data.get("next_action"),
        "next_deadline": data.get("next_deadline"),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.marketplace_cases.update_one(
        {"case_id": case_id},
        {
            "$push": {"case_progress.status_updates": update},
            "$set": {
                "case_progress.last_status_update": datetime.now(timezone.utc).isoformat(),
                "case_progress.status_update_required": False,
                "case_progress.status_update_overdue": False,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"message": "Status update submitted", "update_id": update["update_id"]}


@marketplace_router.post("/attorney/cases/{case_id}/report-settlement")
async def report_settlement(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Report case settlement"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    case = await db.marketplace_cases.find_one({
        "case_id": case_id,
        "assignment.pledged_to_attorney_id": user["id"]
    })
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    settlement_amount = float(data.get("settlement_amount", 0))
    if settlement_amount <= 0:
        raise HTTPException(status_code=400, detail="Settlement amount must be positive")
    
    # Get bonus commission from bid if applicable
    bonus_commission = 0
    assignment = case.get("assignment", {})
    if assignment.get("pledge_type") == "bid_winner":
        # Find winning bid
        bids = case.get("bids", [])
        winning_bid = next((b for b in bids if b.get("attorney_id") == user["id"] and b.get("status") == "winning"), None)
        if winning_bid:
            bonus_commission = winning_bid.get("bid_components", {}).get("commission_bonus_percentage", 0)
    
    # Calculate commission
    commission_calc = calculate_commission(settlement_amount, bonus_commission)
    
    settlement = {
        "settlement_reported": True,
        "settlement_amount": settlement_amount,
        "settlement_date": data.get("settlement_date", datetime.now(timezone.utc).isoformat()),
        "settlement_type": data.get("settlement_type", "full_payment"),
        "standard_commission_rate": commission_calc["standard_rate"],
        "bonus_commission_rate": commission_calc["bonus_rate"],
        "total_commission_rate": commission_calc["total_rate"],
        "commission_amount": commission_calc["commission_amount"],
        "initial_fee": commission_calc["initial_fee"],
        "total_due_credlocity": commission_calc["total_due"],
        "commission_invoice_sent": False,
        "commission_paid": False,
        "settlement_notes": data.get("notes", ""),
        "client_approved_settlement": data.get("client_approved", False)
    }
    
    await db.marketplace_cases.update_one(
        {"case_id": case_id},
        {
            "$set": {
                "status": "settled",
                "settlement": settlement,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Update attorney performance
    await db.attorneys.update_one(
        {"id": user["id"]},
        {
            "$inc": {
                "performance.cases_settled": 1,
                "performance.total_settlements_value": settlement_amount,
                "total_fees_paid": commission_calc["total_due"]
            }
        }
    )
    
    # Process revenue split between Credlocity and referring company
    revenue_split_result = await process_case_settlement_revenue(
        case_id=case_id,
        settlement_amount=settlement_amount,
        commission_amount=commission_calc["commission_amount"],
        initial_fee=commission_calc["initial_fee"]
    )
    
    # Notify relevant parties
    case_title = case.get("title", "Case")
    await create_notification(
        recipient_id=user["id"],
        recipient_type="attorney",
        notification_type="settlement_confirmed",
        title="Settlement Confirmed",
        message=f"Your settlement of ${settlement_amount:,.2f} for \"{case_title}\" has been recorded. Commission due: ${commission_calc['total_due']:,.2f}",
        related_case_id=case_id,
        priority="normal",
        action_url=f"/attorney/cases/{case_id}"
    )
    
    return {
        "message": "Settlement reported successfully",
        "settlement_amount": settlement_amount,
        "commission_breakdown": commission_calc,
        "revenue_split": revenue_split_result["split_details"],
        "next_step": "Invoice will be generated and sent to your email"
    }


@marketplace_router.post("/attorney/cases/{case_id}/pay-initial-fee")
async def pay_initial_fee(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Pay initial fee to download retainer"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    case = await db.marketplace_cases.find_one({
        "case_id": case_id,
        "assignment.pledged_to_attorney_id": user["id"]
    })
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not assigned to you")
    
    assignment = case.get("assignment", {})
    if assignment.get("initial_fee_paid"):
        raise HTTPException(status_code=400, detail="Initial fee already paid")
    
    fee_amount = assignment.get("initial_fee_amount", 500)
    
    # In production, this would integrate with payment processor
    # For now, deduct from attorney's account balance
    attorney = await db.attorneys.find_one({"id": user["id"]})
    account_balance = attorney.get("account_balance", 0)
    
    if account_balance < fee_amount:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient balance. Required: ${fee_amount}, Available: ${account_balance}"
        )
    
    # Deduct fee
    new_balance = account_balance - fee_amount
    
    await db.attorneys.update_one(
        {"id": user["id"]},
        {
            "$set": {"account_balance": new_balance},
            "$push": {
                "account_transactions": {
                    "transaction_id": str(uuid4()),
                    "type": "fee_payment",
                    "amount": -fee_amount,
                    "description": f"Initial fee for {case_id}",
                    "related_case_id": case_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "balance_after": new_balance
                }
            },
            "$inc": {"total_fees_paid": fee_amount}
        }
    )
    
    # Update case
    await db.marketplace_cases.update_one(
        {"case_id": case_id},
        {
            "$set": {
                "assignment.initial_fee_paid": True,
                "assignment.initial_fee_paid_date": datetime.now(timezone.utc).isoformat(),
                "assignment.retainer_download_enabled": True,
                "status": "in_progress",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "message": "Initial fee paid successfully",
        "amount_paid": fee_amount,
        "new_balance": new_balance,
        "case_id": case_id
    }


# ==================== ATTORNEY REVIEWS ====================

@marketplace_router.get("/attorney/my-reviews")
async def get_attorney_reviews(authorization: Optional[str] = Header(None)):
    """Get reviews submitted by the current attorney"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    reviews = await db.reviews.find(
        {
            "is_attorney_review": True,
            "attorney_id": user["id"]
        },
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return {"reviews": reviews, "total": len(reviews)}


@marketplace_router.post("/attorney/submit-review")
async def submit_attorney_review(data: dict, authorization: Optional[str] = Header(None)):
    """Submit a review/testimonial from an attorney"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    # Validate required fields
    if not data.get("testimonial_text"):
        raise HTTPException(status_code=400, detail="Testimonial text is required")
    
    # Generate slug for the review
    slug = f"attorney-{user.get('name', 'attorney').lower().replace(' ', '-').replace(',', '').replace('.', '')}-{str(uuid4())[:8]}"
    
    review = {
        "id": str(uuid4()),
        "attorney_id": user["id"],
        "attorney_name": user.get("name", ""),
        "attorney_email": user.get("email", ""),
        "attorney_firm_name": user.get("firm_name", ""),
        
        # Review content
        "client_name": user.get("name", "Attorney"),  # Use attorney name for display
        "testimonial_text": data.get("testimonial_text"),
        "full_story": data.get("full_story", data.get("testimonial_text", "")),
        "detailed_narrative": data.get("detailed_narrative", ""),
        "story_title": data.get("story_title", f"Attorney {user.get('name', '')} Review"),
        "story_slug": slug,
        
        # Video review
        "video_url": data.get("video_url", ""),
        "attorney_profile_video_url": data.get("video_url", ""),
        "video_platform": data.get("video_platform", ""),
        
        # Metrics
        "attorney_settlement_amount": data.get("settlement_amount"),
        "credlocity_points_gained": data.get("credlocity_points_gained"),
        "attorney_points_gained": data.get("attorney_points_gained"),
        "linked_client_review_id": data.get("linked_client_review_id"),
        "linked_client_review_name": data.get("linked_client_review_name"),
        
        # Star rating
        "rating": data.get("rating", 5),
        "before_score": data.get("before_score", 0),
        "after_score": data.get("after_score", 0),
        
        # Photos
        "client_photo_url": user.get("profile_photo", ""),
        "gallery_photos": data.get("gallery_photos", []),
        
        # Categories and flags
        "is_attorney_review": True,
        "review_category": "attorney_testimonials",
        "category": "attorney_network",
        "featured_on_homepage": False,
        "show_on_success_stories": True,
        "display_on_lawsuits_page": False,
        "location": f"{user.get('city', '')}, {user.get('state', '')}".strip(", "),
        
        # Status
        "status": "pending_approval",  # Admin needs to approve before publishing
        "published": False,
        
        # SEO
        "seo_meta_title": data.get("seo_meta_title", f"Attorney Review - {user.get('name', '')} | Credlocity"),
        "seo_meta_description": data.get("seo_meta_description", data.get("testimonial_text", "")[:160]),
        "seo_keywords": data.get("seo_keywords", "attorney review, credlocity attorney network, legal partnership"),
        
        # Timestamps
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.reviews.insert_one(review)
    review.pop("_id", None)
    
    return {
        "message": "Review submitted successfully! It will be published after admin approval.",
        "review_id": review["id"],
        "review": review
    }


@marketplace_router.put("/attorney/reviews/{review_id}")
async def update_attorney_review(review_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update an attorney's review"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    # Verify ownership
    review = await db.reviews.find_one({"id": review_id, "attorney_id": user["id"]})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or you don't have permission to edit it")
    
    # Don't allow editing published reviews (would need admin approval again)
    if review.get("published"):
        raise HTTPException(status_code=400, detail="Cannot edit a published review. Contact admin for changes.")
    
    update_data = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Allowed fields to update
    allowed_fields = [
        "testimonial_text", "full_story", "detailed_narrative", "story_title",
        "video_url", "attorney_profile_video_url", "video_platform",
        "settlement_amount", "credlocity_points_gained", "attorney_points_gained",
        "linked_client_review_id", "linked_client_review_name",
        "rating", "gallery_photos"
    ]
    
    for field in allowed_fields:
        if field in data:
            update_data[field] = data[field]
    
    await db.reviews.update_one(
        {"id": review_id},
        {"$set": update_data}
    )
    
    return {"message": "Review updated successfully"}


@marketplace_router.delete("/attorney/reviews/{review_id}")
async def delete_attorney_review(review_id: str, authorization: Optional[str] = Header(None)):
    """Delete an attorney's unpublished review"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    review = await db.reviews.find_one({"id": review_id, "attorney_id": user["id"]})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or you don't have permission to delete it")
    
    if review.get("published"):
        raise HTTPException(status_code=400, detail="Cannot delete a published review. Contact admin.")
    
    await db.reviews.delete_one({"id": review_id})
    
    return {"message": "Review deleted successfully"}


# ==================== ATTORNEY ACCOUNT ====================

@marketplace_router.get("/attorney/account")
async def get_attorney_account(authorization: Optional[str] = Header(None)):
    """Get attorney account details and transactions"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    attorney = await db.attorneys.find_one(
        {"id": user["id"]},
        {"_id": 0, "password_hash": 0, "token": 0, "client_full_info": 0}
    )
    
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney profile not found")
    
    return {
        "balance": attorney.get("account_balance", 0),
        "total_earnings": attorney.get("total_earnings", 0),
        "total_fees_paid": attorney.get("total_fees_paid", 0),
        "transactions": attorney.get("account_transactions", [])[-20:],  # Last 20
        "performance": attorney.get("performance", {})
    }


@marketplace_router.post("/attorney/account/deposit")
async def deposit_funds(data: dict, authorization: Optional[str] = Header(None)):
    """Add funds to attorney account (for bidding)"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    amount = float(data.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    # In production, this would integrate with payment processor
    attorney = await db.attorneys.find_one({"id": user["id"]})
    current_balance = attorney.get("account_balance", 0)
    new_balance = current_balance + amount
    
    await db.attorneys.update_one(
        {"id": user["id"]},
        {
            "$set": {"account_balance": new_balance},
            "$push": {
                "account_transactions": {
                    "transaction_id": str(uuid4()),
                    "type": "deposit",
                    "amount": amount,
                    "description": f"Account deposit",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "balance_after": new_balance
                }
            }
        }
    )
    
    return {
        "message": "Deposit successful",
        "amount": amount,
        "new_balance": new_balance
    }


@marketplace_router.get("/attorney/payment-summary")
async def get_payment_summary(authorization: Optional[str] = Header(None)):
    """Get attorney payment summary"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    attorney = await db.attorneys.find_one({"id": user["id"]}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney profile not found")
    
    # Get pending initial fees
    pending_fee_cases = await db.marketplace_cases.find(
        {
            "assigned_attorney_id": user["id"],
            "status": "pledged",
            "initial_fee_paid": {"$ne": True}
        },
        {"_id": 0, "case_id": 1, "title": 1}
    ).to_list(None)
    
    pending_fees = len(pending_fee_cases) * 500  # $500 per case
    
    return {
        "account_balance": attorney.get("account_balance", 0),
        "total_earnings": attorney.get("total_earnings", 0),
        "total_fees_paid": attorney.get("total_fees_paid", 0),
        "pending_fees": pending_fees,
        "pending_initial_fees": [
            {"case_id": c["case_id"], "case_title": c["title"]}
            for c in pending_fee_cases
        ],
        "held_balance": attorney.get("held_balance", 0),
        "marketplace_locked": attorney.get("marketplace_locked", False)
    }


@marketplace_router.get("/attorney/transactions")
async def get_attorney_transactions(
    authorization: Optional[str] = Header(None),
    skip: int = 0,
    limit: int = 50
):
    """Get attorney transaction history"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    attorney = await db.attorneys.find_one({"id": user["id"]}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=404, detail="Attorney profile not found")
    
    transactions = attorney.get("account_transactions", [])
    
    # Format transactions for display
    formatted = []
    for tx in transactions:
        formatted.append({
            "id": tx.get("transaction_id"),
            "type": "credit" if tx.get("amount", 0) > 0 else "debit",
            "amount": abs(tx.get("amount", 0)),
            "description": tx.get("description"),
            "reference": tx.get("related_case_id", ""),
            "created_at": tx.get("timestamp"),
            "balance_after": tx.get("balance_after")
        })
    
    # Sort by date descending and paginate
    formatted.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    paginated = formatted[skip:skip+limit]
    
    return {
        "transactions": paginated,
        "total": len(formatted)
    }


# ==================== ADMIN CASE MANAGEMENT ====================

@marketplace_router.post("/admin/cases")
async def create_marketplace_case(data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Create a new marketplace case"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Generate case ID
    case_count = await db.marketplace_cases.count_documents({})
    case_id = f"CASE-{str(case_count + 1).zfill(3)}"
    
    # Process client info
    client_first_name = data.get("client_first_name", "")
    client_last_name = data.get("client_last_name", "")
    client_city = data.get("client_city", "")
    client_state = data.get("client_state", "")
    
    case = {
        "case_id": case_id,
        "title": data.get("title"),
        "type": data.get("type"),
        "category": data.get("category", "standard"),  # standard, bidding, class_action
        "description": data.get("description"),
        
        # Anonymized client info
        "client_first_name": client_first_name,
        "client_last_initial": client_last_name[0] if client_last_name else "",
        "client_name_display": f"{client_first_name} {client_last_name[0]}." if client_first_name and client_last_name else "Anonymous",
        "client_city": client_city,
        "client_state": client_state,
        "client_location_display": f"{client_city}, {client_state}" if client_city and client_state else "",
        
        # Full client info (hidden from attorneys until assignment)
        "client_full_info": {
            "full_name": f"{client_first_name} {client_last_name}",
            "email": data.get("client_email"),
            "phone": data.get("client_phone"),
            "full_address": data.get("client_address"),
            "ssn_last_4": data.get("client_ssn_last_4"),
            "date_of_birth": data.get("client_dob")
        },
        
        # Case value and jurisdiction
        "estimated_value": float(data.get("estimated_value", 0)),
        "estimated_value_display": f"${data.get('estimated_value', 0):,.0f}",
        "jurisdiction": data.get("jurisdiction"),
        "venue_preference": data.get("venue_preference"),
        
        # Practice areas
        "practice_areas": data.get("practice_areas", []),
        
        # Status
        "status": "available",
        "availability_status": "open",
        
        # Evidence
        "evidence_summary": data.get("evidence_summary", []),
        "evidence_strength_score": data.get("evidence_strength_score", 5),
        
        # Violations
        "violations": data.get("violations", []),
        
        # Client background
        "client_background": data.get("client_background"),
        "client_impact": data.get("client_impact"),
        "client_credibility": data.get("client_credibility", "moderate"),
        
        # Settlement requirements
        "settlement_requirements": data.get("settlement_requirements", []),
        
        # Class action details
        "class_action_details": data.get("class_action_details") if data.get("category") == "class_action" else None,
        
        # Deadlines
        "deadline": data.get("deadline"),
        "statute_of_limitations": data.get("statute_of_limitations"),
        
        # Bidding info
        "bidding_info": {
            "bidding_enabled": data.get("category") in ["bidding", "class_action"],
            "bidding_deadline": data.get("bidding_deadline"),
            "bidding_start_date": datetime.now(timezone.utc).isoformat(),
            "min_bid_requirements": data.get("min_bid_requirements", {}),
            "current_bid_count": 0,
            "highest_bid_amount": 0,
            "winning_bid_id": None
        } if data.get("category") in ["bidding", "class_action"] else None,
        
        "bids": [],
        "assignment": None,
        "case_progress": {
            "status_updates": [],
            "last_status_update": None,
            "status_update_required": False,
            "status_update_overdue": False
        },
        "settlement": None,
        
        # Admin settings
        "admin_settings": {
            "featured": data.get("featured", False),
            "priority_level": data.get("priority_level", 3),
            "internal_notes": data.get("internal_notes"),
            "risk_assessment": data.get("risk_assessment", "medium"),
            "approval_status": "approved",
            "created_by": user.get("id")
        },
        
        # Metadata
        "views_count": 0,
        "unique_attorney_views": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.marketplace_cases.insert_one(case)
    case.pop("_id", None)
    
    return {"message": "Case created successfully", "case_id": case_id, "case": case}


@marketplace_router.get("/admin/cases")
async def admin_list_cases(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Admin: List all marketplace cases"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    query = {}
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    
    cases = await db.marketplace_cases.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.marketplace_cases.count_documents(query)
    
    return {"cases": cases, "total": total}


@marketplace_router.get("/admin/stats")
async def get_marketplace_stats(authorization: Optional[str] = Header(None)):
    """Admin: Get marketplace statistics"""
    user = await get_current_user(authorization)
    require_admin(user)
    
    # Case stats
    total_cases = await db.marketplace_cases.count_documents({})
    available_cases = await db.marketplace_cases.count_documents({"status": "available"})
    pledged_cases = await db.marketplace_cases.count_documents({"status": "pledged"})
    in_progress_cases = await db.marketplace_cases.count_documents({"status": "in_progress"})
    settled_cases = await db.marketplace_cases.count_documents({"status": "settled"})
    
    # Value pipeline
    pipeline = [
        {"$group": {
            "_id": "$status",
            "total_value": {"$sum": "$estimated_value"},
            "count": {"$sum": 1}
        }}
    ]
    value_by_status = await db.marketplace_cases.aggregate(pipeline).to_list(None)
    
    # Attorney stats
    total_attorneys = await db.attorneys.count_documents({})
    active_attorneys = await db.attorneys.count_documents({"status": "active"})
    
    # Revenue stats
    revenue_pipeline = [
        {"$match": {"settlement.commission_paid": True}},
        {"$group": {
            "_id": None,
            "total_initial_fees": {"$sum": "$settlement.initial_fee"},
            "total_commissions": {"$sum": "$settlement.commission_amount"},
            "count": {"$sum": 1}
        }}
    ]
    revenue_result = await db.marketplace_cases.aggregate(revenue_pipeline).to_list(None)
    revenue = revenue_result[0] if revenue_result else {"total_initial_fees": 0, "total_commissions": 0, "count": 0}
    
    return {
        "cases": {
            "total": total_cases,
            "available": available_cases,
            "pledged": pledged_cases,
            "in_progress": in_progress_cases,
            "settled": settled_cases
        },
        "value_by_status": {item["_id"]: {"value": item["total_value"], "count": item["count"]} for item in value_by_status},
        "attorneys": {
            "total": total_attorneys,
            "active": active_attorneys
        },
        "revenue": {
            "total_initial_fees": revenue.get("total_initial_fees", 0),
            "total_commissions": revenue.get("total_commissions", 0),
            "total": revenue.get("total_initial_fees", 0) + revenue.get("total_commissions", 0),
            "cases_settled": revenue.get("count", 0)
        }
    }


# ==================== NOTIFICATION ENDPOINTS ====================

@marketplace_router.get("/notifications")
async def get_attorney_notifications(
    unread_only: bool = False,
    limit: int = 50,
    authorization: Optional[str] = Header(None)
):
    """Get notifications for the current attorney"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    query = {"recipient_id": user["id"], "recipient_type": "attorney"}
    if unread_only:
        query["is_read"] = False
    
    notifications = await db.notifications.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    
    # Get unread count
    unread_count = await db.notifications.count_documents({
        "recipient_id": user["id"],
        "recipient_type": "attorney",
        "is_read": False
    })
    
    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total": len(notifications)
    }


@marketplace_router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    authorization: Optional[str] = Header(None)
):
    """Mark a notification as read"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    result = await db.notifications.update_one(
        {"id": notification_id, "recipient_id": user["id"]},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"message": "Notification marked as read"}


@marketplace_router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(authorization: Optional[str] = Header(None)):
    """Mark all notifications as read"""
    user = await get_attorney_from_token(authorization)
    require_attorney(user)
    
    result = await db.notifications.update_many(
        {"recipient_id": user["id"], "is_read": False},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": f"Marked {result.modified_count} notifications as read"}

