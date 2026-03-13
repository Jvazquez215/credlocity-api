"""
Credlocity Payroll System API
Handles: Employee payroll profiles, pay periods, payroll runs,
commission tracking, bonus management, pay stub generation
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import io

payroll_router = APIRouter(prefix="/api/payroll")

db = None

def set_db(database):
    global db
    db = database


# Auth
from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        user = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user):
    if user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin access required")


PAY_TYPES = ["salary", "hourly", "salary_plus_commission", "hourly_plus_commission", "commission_only"]
PAY_SCHEDULES = ["weekly", "biweekly", "monthly"]


# ==================== PAYROLL PROFILES ====================

@payroll_router.get("/profiles")
async def list_profiles(department: Optional[str] = None, user: dict = Depends(get_current_user)):
    """List all employee payroll profiles"""
    require_admin(user)
    query = {}
    if department:
        query["department"] = department
    profiles = await db.payroll_profiles.find(query, {"_id": 0}).sort("employee_name", 1).to_list(length=500)
    return {"profiles": profiles}


@payroll_router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str, user: dict = Depends(get_current_user)):
    """Get a single payroll profile"""
    profile = await db.payroll_profiles.find_one({"id": profile_id}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    # Only admin or the employee themselves
    if user.get("role") not in ["admin", "super_admin", "director", "manager"] and profile["employee_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return profile


@payroll_router.post("/profiles")
async def create_profile(data: dict, user: dict = Depends(get_current_user)):
    """Create payroll profile for an employee"""
    require_admin(user)
    employee_id = data.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id required")

    # Check duplicate
    existing = await db.payroll_profiles.find_one({"employee_id": employee_id})
    if existing:
        raise HTTPException(status_code=409, detail="Profile already exists for this employee")

    now = datetime.now(timezone.utc).isoformat()
    profile = {
        "id": str(uuid4()),
        "employee_id": employee_id,
        "employee_name": data.get("employee_name", ""),
        "employee_email": data.get("employee_email", ""),
        "department": data.get("department", "General"),
        "pay_type": data.get("pay_type", "salary"),
        "base_salary": data.get("base_salary", 0),
        "hourly_rate": data.get("hourly_rate", 0),
        "commission_rate": data.get("commission_rate", 0),
        "pay_schedule": data.get("pay_schedule", "biweekly"),
        "tax_rate": data.get("tax_rate", 22),
        "deductions": data.get("deductions", []),
        "status": "active",
        "start_date": data.get("start_date", now[:10]),
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now
    }
    await db.payroll_profiles.insert_one(profile)
    profile.pop("_id", None)
    return profile


@payroll_router.put("/profiles/{profile_id}")
async def update_profile(profile_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update payroll profile"""
    require_admin(user)
    data.pop("id", None)
    data.pop("_id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.payroll_profiles.update_one({"id": profile_id}, {"$set": data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"message": "Profile updated"}


@payroll_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, user: dict = Depends(get_current_user)):
    """Deactivate payroll profile"""
    require_admin(user)
    result = await db.payroll_profiles.update_one(
        {"id": profile_id},
        {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"message": "Profile deactivated"}


# ==================== COMMISSIONS ====================

@payroll_router.post("/commissions")
async def log_commission(data: dict, user: dict = Depends(get_current_user)):
    """Log a commission entry for a collections employee"""
    require_admin(user)
    now = datetime.now(timezone.utc).isoformat()
    commission = {
        "id": str(uuid4()),
        "employee_id": data.get("employee_id"),
        "employee_name": data.get("employee_name", ""),
        "account_id": data.get("account_id", ""),
        "account_name": data.get("account_name", ""),
        "amount_collected": data.get("amount_collected", 0),
        "commission_rate": data.get("commission_rate", 0),
        "commission_amount": data.get("commission_amount", 0),
        "description": data.get("description", ""),
        "date": data.get("date", now[:10]),
        "status": "pending",
        "pay_period_id": data.get("pay_period_id"),
        "created_by": user["id"],
        "created_at": now
    }
    # Auto-calculate commission if not provided
    if not commission["commission_amount"] and commission["amount_collected"] and commission["commission_rate"]:
        commission["commission_amount"] = round(commission["amount_collected"] * commission["commission_rate"] / 100, 2)

    await db.payroll_commissions.insert_one(commission)
    commission.pop("_id", None)
    return commission


@payroll_router.get("/commissions")
async def list_commissions(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List commissions with filters"""
    require_admin(user)
    query = {}
    if employee_id:
        query["employee_id"] = employee_id
    if status:
        query["status"] = status
    if start_date or end_date:
        date_q = {}
        if start_date:
            date_q["$gte"] = start_date
        if end_date:
            date_q["$lte"] = end_date
        if date_q:
            query["date"] = date_q

    commissions = await db.payroll_commissions.find(query, {"_id": 0}).sort("date", -1).to_list(length=500)
    total = sum(c.get("commission_amount", 0) for c in commissions)
    return {"commissions": commissions, "total_commission": round(total, 2)}


@payroll_router.put("/commissions/{commission_id}")
async def update_commission(commission_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update commission status (approve, reject)"""
    require_admin(user)
    allowed = {"status", "commission_amount", "description"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.payroll_commissions.update_one({"id": commission_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commission not found")
    return {"message": "Updated"}


# ==================== BONUSES ====================

BONUS_TYPES = ["performance", "signup", "collections_target", "custom", "holiday", "referral"]

@payroll_router.post("/bonuses")
async def create_bonus(data: dict, user: dict = Depends(get_current_user)):
    """Create a bonus entry"""
    require_admin(user)
    now = datetime.now(timezone.utc).isoformat()
    bonus = {
        "id": str(uuid4()),
        "employee_id": data.get("employee_id"),
        "employee_name": data.get("employee_name", ""),
        "bonus_type": data.get("bonus_type", "custom"),
        "amount": data.get("amount", 0),
        "description": data.get("description", ""),
        "metric_name": data.get("metric_name", ""),
        "metric_value": data.get("metric_value", 0),
        "metric_target": data.get("metric_target", 0),
        "date": data.get("date", now[:10]),
        "status": "pending",
        "pay_period_id": data.get("pay_period_id"),
        "created_by": user["id"],
        "created_at": now
    }
    await db.payroll_bonuses.insert_one(bonus)
    bonus.pop("_id", None)
    return bonus


@payroll_router.get("/bonuses")
async def list_bonuses(
    employee_id: Optional[str] = None,
    bonus_type: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List bonuses"""
    require_admin(user)
    query = {}
    if employee_id:
        query["employee_id"] = employee_id
    if bonus_type:
        query["bonus_type"] = bonus_type
    if status:
        query["status"] = status
    bonuses = await db.payroll_bonuses.find(query, {"_id": 0}).sort("date", -1).to_list(length=500)
    total = sum(b.get("amount", 0) for b in bonuses)
    return {"bonuses": bonuses, "total_bonuses": round(total, 2)}


@payroll_router.put("/bonuses/{bonus_id}")
async def update_bonus(bonus_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update bonus"""
    require_admin(user)
    allowed = {"status", "amount", "description"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.payroll_bonuses.update_one({"id": bonus_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bonus not found")
    return {"message": "Updated"}


@payroll_router.delete("/bonuses/{bonus_id}")
async def delete_bonus(bonus_id: str, user: dict = Depends(get_current_user)):
    """Delete a bonus"""
    require_admin(user)
    result = await db.payroll_bonuses.delete_one({"id": bonus_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bonus not found")
    return {"message": "Deleted"}


# ==================== PAY PERIODS ====================

@payroll_router.get("/pay-periods")
async def list_pay_periods(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    """List pay periods"""
    require_admin(user)
    query = {}
    if status:
        query["status"] = status
    periods = await db.pay_periods.find(query, {"_id": 0}).sort("start_date", -1).to_list(length=100)
    return {"pay_periods": periods}


@payroll_router.post("/pay-periods")
async def create_pay_period(data: dict, user: dict = Depends(get_current_user)):
    """Create a new pay period"""
    require_admin(user)
    now = datetime.now(timezone.utc).isoformat()
    period = {
        "id": str(uuid4()),
        "name": data.get("name", ""),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "pay_date": data.get("pay_date"),
        "schedule_type": data.get("schedule_type", "biweekly"),
        "status": "open",
        "total_gross": 0,
        "total_deductions": 0,
        "total_net": 0,
        "total_commissions": 0,
        "total_bonuses": 0,
        "employee_count": 0,
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now
    }
    await db.pay_periods.insert_one(period)
    period.pop("_id", None)
    return period


@payroll_router.put("/pay-periods/{period_id}")
async def update_pay_period(period_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update pay period"""
    require_admin(user)
    allowed = {"name", "start_date", "end_date", "pay_date", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.pay_periods.update_one({"id": period_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Period not found")
    return {"message": "Updated"}


# ==================== PAYROLL RUNS ====================

@payroll_router.post("/pay-periods/{period_id}/run")
async def run_payroll(period_id: str, user: dict = Depends(get_current_user)):
    """Process payroll for a pay period — calculates pay for all active employees"""
    require_admin(user)
    period = await db.pay_periods.find_one({"id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")
    if period["status"] == "closed":
        raise HTTPException(status_code=400, detail="Pay period already closed")

    profiles = await db.payroll_profiles.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    now = datetime.now(timezone.utc).isoformat()
    stubs = []

    for profile in profiles:
        eid = profile["employee_id"]
        pay_type = profile.get("pay_type", "salary")

        # Calculate base pay
        base_pay = 0
        if pay_type in ["salary", "salary_plus_commission"]:
            annual = profile.get("base_salary", 0)
            schedule = profile.get("pay_schedule", "biweekly")
            if schedule == "weekly":
                base_pay = round(annual / 52, 2)
            elif schedule == "biweekly":
                base_pay = round(annual / 26, 2)
            else:
                base_pay = round(annual / 12, 2)
        elif pay_type in ["hourly", "hourly_plus_commission"]:
            hours = profile.get("default_hours", 80)
            base_pay = round(profile.get("hourly_rate", 0) * hours, 2)

        # Get commissions for this period
        commission_query = {
            "employee_id": eid,
            "date": {"$gte": period["start_date"], "$lte": period["end_date"]}
        }
        commissions = await db.payroll_commissions.find(commission_query, {"_id": 0}).to_list(length=200)
        total_commission = round(sum(c.get("commission_amount", 0) for c in commissions), 2)

        # Get bonuses for this period
        bonus_query = {
            "employee_id": eid,
            "date": {"$gte": period["start_date"], "$lte": period["end_date"]}
        }
        bonuses = await db.payroll_bonuses.find(bonus_query, {"_id": 0}).to_list(length=200)
        total_bonus = round(sum(b.get("amount", 0) for b in bonuses), 2)

        # Deductions
        deductions = profile.get("deductions", [])
        total_deductions = round(sum(d.get("amount", 0) for d in deductions), 2)

        # Tax
        gross = round(base_pay + total_commission + total_bonus, 2)
        tax_rate = profile.get("tax_rate", 22) / 100
        tax = round(gross * tax_rate, 2)
        net = round(gross - tax - total_deductions, 2)

        stub = {
            "id": str(uuid4()),
            "pay_period_id": period_id,
            "employee_id": eid,
            "employee_name": profile.get("employee_name", ""),
            "employee_email": profile.get("employee_email", ""),
            "department": profile.get("department", ""),
            "pay_type": pay_type,
            "base_pay": base_pay,
            "total_commission": total_commission,
            "commission_entries": len(commissions),
            "total_bonus": total_bonus,
            "bonus_entries": len(bonuses),
            "gross_pay": gross,
            "tax_rate": profile.get("tax_rate", 22),
            "tax_amount": tax,
            "deductions": deductions,
            "total_deductions": total_deductions,
            "net_pay": net,
            "status": "processed",
            "created_at": now
        }
        await db.pay_stubs.insert_one(stub)
        stub.pop("_id", None)
        stubs.append(stub)

        # Mark commissions as paid
        await db.payroll_commissions.update_many(commission_query, {"$set": {"status": "paid", "pay_period_id": period_id}})
        await db.payroll_bonuses.update_many(bonus_query, {"$set": {"status": "paid", "pay_period_id": period_id}})

    # Update period totals
    total_gross = round(sum(s["gross_pay"] for s in stubs), 2)
    total_deductions = round(sum(s["total_deductions"] + s["tax_amount"] for s in stubs), 2)
    total_net = round(sum(s["net_pay"] for s in stubs), 2)
    total_commissions = round(sum(s["total_commission"] for s in stubs), 2)
    total_bonuses = round(sum(s["total_bonus"] for s in stubs), 2)

    await db.pay_periods.update_one({"id": period_id}, {"$set": {
        "status": "processed",
        "total_gross": total_gross,
        "total_deductions": total_deductions,
        "total_net": total_net,
        "total_commissions": total_commissions,
        "total_bonuses": total_bonuses,
        "employee_count": len(stubs),
        "processed_at": now,
        "updated_at": now
    }})

    return {
        "pay_period_id": period_id,
        "employees_processed": len(stubs),
        "total_gross": total_gross,
        "total_net": total_net,
        "total_commissions": total_commissions,
        "total_bonuses": total_bonuses,
        "stubs": stubs
    }


# ==================== PAY STUBS ====================

@payroll_router.get("/pay-stubs")
async def list_pay_stubs(
    pay_period_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List pay stubs"""
    query = {}
    if pay_period_id:
        query["pay_period_id"] = pay_period_id
    # Non-admin can only see their own
    if user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        query["employee_id"] = user["id"]
    elif employee_id:
        query["employee_id"] = employee_id
    stubs = await db.pay_stubs.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=200)
    return {"stubs": stubs}


@payroll_router.get("/pay-stubs/{stub_id}/download")
async def download_pay_stub(stub_id: str, user: dict = Depends(get_current_user)):
    """Download pay stub as PDF"""
    stub = await db.pay_stubs.find_one({"id": stub_id}, {"_id": 0})
    if not stub:
        raise HTTPException(status_code=404, detail="Pay stub not found")
    if user.get("role") not in ["admin", "super_admin", "director", "manager"] and stub["employee_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    period = await db.pay_periods.find_one({"id": stub["pay_period_id"]}, {"_id": 0})
    pdf_bytes = generate_pay_stub_pdf(stub, period)
    filename = f"PayStub_{stub.get('employee_name', 'Employee').replace(' ', '_')}_{stub.get('pay_period_id', '')[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def generate_pay_stub_pdf(stub: dict, period: dict) -> bytes:
    """Generate a pay stub PDF"""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    w, h = letter
    c = canvas.Canvas(buf, pagesize=letter)

    # Header
    c.setFillColor(HexColor("#10B981"))
    c.rect(0, h - 80, w, 80, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 24)
    c.drawString(40, h - 50, "CREDLOCITY")
    c.setFont("Helvetica", 12)
    c.drawString(40, h - 70, "Pay Statement")
    c.drawRightString(w - 40, h - 50, f"Pay Stub ID: {stub['id'][:8]}")

    y = h - 110
    c.setFillColor(HexColor("#1F2937"))

    # Employee info
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, stub.get("employee_name", ""))
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Department: {stub.get('department', '')}")
    c.drawString(300, y, f"Pay Type: {stub.get('pay_type', '').replace('_', ' ').title()}")
    y -= 16
    if period:
        c.drawString(40, y, f"Pay Period: {period.get('start_date', '')} to {period.get('end_date', '')}")
        c.drawString(300, y, f"Pay Date: {period.get('pay_date', '')}")
    y -= 30

    # Earnings table
    c.setFillColor(HexColor("#F3F4F6"))
    c.rect(40, y - 5, w - 80, 22, fill=1, stroke=0)
    c.setFillColor(HexColor("#1F2937"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "EARNINGS")
    c.drawRightString(w - 50, y, "AMOUNT")
    y -= 25

    c.setFont("Helvetica", 10)
    items = [
        ("Base Pay", stub.get("base_pay", 0)),
        (f"Commissions ({stub.get('commission_entries', 0)} entries)", stub.get("total_commission", 0)),
        (f"Bonuses ({stub.get('bonus_entries', 0)} entries)", stub.get("total_bonus", 0)),
    ]
    for label, amount in items:
        c.drawString(50, y, label)
        c.drawRightString(w - 50, y, f"${amount:,.2f}")
        y -= 18

    # Gross
    c.setStrokeColor(HexColor("#D1D5DB"))
    c.line(40, y + 5, w - 40, y + 5)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y - 5, "GROSS PAY")
    c.drawRightString(w - 50, y - 5, f"${stub.get('gross_pay', 0):,.2f}")
    y -= 35

    # Deductions
    c.setFillColor(HexColor("#FEF2F2"))
    c.rect(40, y - 5, w - 80, 22, fill=1, stroke=0)
    c.setFillColor(HexColor("#1F2937"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "DEDUCTIONS")
    c.drawRightString(w - 50, y, "AMOUNT")
    y -= 25

    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Federal Tax ({stub.get('tax_rate', 0)}%)")
    c.drawRightString(w - 50, y, f"-${stub.get('tax_amount', 0):,.2f}")
    y -= 18

    for d in stub.get("deductions", []):
        c.drawString(50, y, d.get("name", "Deduction"))
        c.drawRightString(w - 50, y, f"-${d.get('amount', 0):,.2f}")
        y -= 18

    c.setStrokeColor(HexColor("#D1D5DB"))
    c.line(40, y + 5, w - 40, y + 5)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y - 5, "TOTAL DEDUCTIONS")
    c.drawRightString(w - 50, y - 5, f"-${stub.get('total_deductions', 0) + stub.get('tax_amount', 0):,.2f}")
    y -= 40

    # Net pay
    c.setFillColor(HexColor("#10B981"))
    c.rect(40, y - 10, w - 80, 35, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "NET PAY")
    c.drawRightString(w - 50, y, f"${stub.get('net_pay', 0):,.2f}")

    # Footer
    c.setFillColor(HexColor("#9CA3AF"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, 30, f"This is a system-generated pay stub. Stub ID: {stub['id']}")

    c.save()
    buf.seek(0)
    return buf.getvalue()


# ==================== DASHBOARD STATS ====================

@payroll_router.get("/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    """Get payroll dashboard stats"""
    require_admin(user)

    profiles = await db.payroll_profiles.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    total_annual = sum(p.get("base_salary", 0) for p in profiles if p.get("pay_type", "").startswith("salary"))

    # Current month commissions
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    commissions = await db.payroll_commissions.find(
        {"date": {"$gte": month_start}}, {"_id": 0}
    ).to_list(length=1000)
    month_commissions = round(sum(c.get("commission_amount", 0) for c in commissions), 2)

    # Current month bonuses
    bonuses = await db.payroll_bonuses.find(
        {"date": {"$gte": month_start}}, {"_id": 0}
    ).to_list(length=1000)
    month_bonuses = round(sum(b.get("amount", 0) for b in bonuses), 2)

    # Last pay period
    last_period = await db.pay_periods.find_one(
        {"status": {"$in": ["processed", "closed"]}},
        {"_id": 0}, sort=[("end_date", -1)]
    )

    # Commission leaderboard
    pipeline = [
        {"$match": {"date": {"$gte": month_start}}},
        {"$group": {"_id": "$employee_id", "name": {"$first": "$employee_name"}, "total": {"$sum": "$commission_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$limit": 10}
    ]
    leaderboard = await db.payroll_commissions.aggregate(pipeline).to_list(length=10)

    return {
        "active_employees": len(profiles),
        "total_annual_salaries": total_annual,
        "month_commissions": month_commissions,
        "month_bonuses": month_bonuses,
        "last_pay_period": last_period,
        "commission_leaderboard": [{"employee_id": l["_id"], "employee_name": l["name"], "total": round(l["total"], 2), "count": l["count"]} for l in leaderboard],
        "profiles_by_type": {
            pt: len([p for p in profiles if p.get("pay_type") == pt])
            for pt in PAY_TYPES if any(p.get("pay_type") == pt for p in profiles)
        }
    }
