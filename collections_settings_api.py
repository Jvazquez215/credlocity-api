"""
Collections Settings API
Manages configurable commission rates, fee schedules, late fee tiers, and waiver limits.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

collections_settings_router = APIRouter(prefix="/api/collections/settings", tags=["Collections Settings"])

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
    if user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Default settings used when no DB config exists
DEFAULT_SETTINGS = {
    "commission": {
        "base_rate": 20,
        "payment_plan_threshold": 70,
        "collection_fee_immediate": True,
    },
    "fees": {
        "collection_file_processing": {"amount": 150.00, "waivable": False},
        "collection_fee": {"amount": 350.00, "waivable": True, "max_waive_amount": 175.00, "min_collect": 175.00},
        "payment_processing": {"amount": 190.00, "waivable": True, "max_waive_amount": 90.00, "min_collect": 100.00},
    },
    "late_fees": [
        {"label": "1-10 days late", "min_days": 1, "max_days": 10, "amount": 10.50},
        {"label": "11-15 days late", "min_days": 11, "max_days": 15, "amount": 17.50},
        {"label": "16-30 days late", "min_days": 16, "max_days": 30, "amount": 30.00},
        {"label": "31-90 days late", "min_days": 31, "max_days": 90, "amount": 50.00},
    ],
    "tiers": {
        "1": {
            "name": "Payment in Full",
            "description": "Full payment within 5 business days",
            "min_down_percent": 100,
            "max_months": 0,
            "waiver_limits": {
                "collection_fee_max_waive": 125.00,
                "payment_processing_max_waive": 70.00,
                "late_fees_waivable": True,
                "late_fees_max_count": 99,
                "conditional_free_trial_waivable": True,
            },
        },
        "2": {
            "name": "Payment Plan (3-4 Months)",
            "description": "Min 25% down within 5 days, autopay required",
            "min_down_percent": 25,
            "max_months": 4,
            "waiver_limits": {
                "collection_fee_max_waive": 75.00,
                "payment_processing_max_waive": 40.00,
                "late_fees_waivable": True,
                "late_fees_max_count": 2,
                "conditional_free_trial_waivable": True,
                "conditional_free_trial_max_percent": 50,
            },
        },
        "3": {
            "name": "Extended Plan (5-6 Months)",
            "description": "Min 30% down within 5 days, autopay required, late payment penalties",
            "min_down_percent": 30,
            "max_months": 6,
            "waiver_limits": {
                "collection_fee_max_waive": 50.00,
                "payment_processing_max_waive": 25.00,
                "late_fees_waivable": True,
                "late_fees_max_count": 1,
                "late_fees_requires_down_percent": 40,
                "conditional_free_trial_waivable": False,
            },
        },
    },
    "bonuses": [
        {"name": "Quick Close Bonus", "type": "fixed", "amount": 50.00, "condition": "Payment in full within 48 hours"},
        {"name": "Full Collection Bonus", "type": "percentage", "percentage": 2.0, "condition": "No waivers used on any fees"},
    ],
}


@collections_settings_router.get("")
async def get_settings(user: dict = Depends(get_admin_user)):
    """Get current collections settings"""
    settings = await db.collections_settings.find_one({"key": "global"}, {"_id": 0})
    if not settings:
        return {"settings": DEFAULT_SETTINGS, "source": "defaults"}
    return {"settings": settings.get("data", DEFAULT_SETTINGS), "source": "database", "updated_at": settings.get("updated_at")}


@collections_settings_router.put("")
async def update_settings(data: dict, user: dict = Depends(get_admin_user)):
    """Update collections settings"""
    now = datetime.now(timezone.utc).isoformat()
    settings_data = data.get("settings", data)

    await db.collections_settings.update_one(
        {"key": "global"},
        {"$set": {
            "key": "global",
            "data": settings_data,
            "updated_by": user["id"],
            "updated_by_name": user.get("full_name", ""),
            "updated_at": now,
        }},
        upsert=True
    )
    return {"message": "Settings updated", "updated_at": now}


@collections_settings_router.get("/defaults")
async def get_defaults(user: dict = Depends(get_admin_user)):
    """Get default settings for reset"""
    return {"settings": DEFAULT_SETTINGS}


async def get_active_settings():
    """Helper: get active settings from DB or defaults. Used by other modules."""
    settings = await db.collections_settings.find_one({"key": "global"}, {"_id": 0})
    if settings and settings.get("data"):
        return settings["data"]
    return DEFAULT_SETTINGS
