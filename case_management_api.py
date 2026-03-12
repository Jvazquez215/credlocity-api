"""
Credlocity Case Management API
Comprehensive FCRA case management for the attorney marketplace:
- Case creation and management
- Violation tracking
- Dispute history
- Document management
- Compliance checks
- Case analysis and marketplace publishing
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import os
import json
from motor.motor_asyncio import AsyncIOMotorClient

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

case_management_router = APIRouter(prefix="/api/cases", tags=["Case Management"])


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


def require_auth(user):
    """Require authentication"""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")


def require_admin(user):
    """Require admin authentication"""
    if not user or user.get("role") not in ["admin", "super_admin", "director"]:
        raise HTTPException(status_code=403, detail="Admin authentication required")


def require_company_access(user, company_id):
    """Require user has access to specific company"""
    if user.get("role") in ["admin", "super_admin", "director"]:
        return True
    if user.get("is_company_user") and user.get("company_id") == company_id:
        return True
    raise HTTPException(status_code=403, detail="Access denied to this company")


# ==================== CASE STATUS & TIER CONSTANTS ====================

CASE_STATUSES = ["draft", "published", "under_review", "bid_accepted", "in_litigation", "settled", "closed"]
CASE_TIERS = ["tier_1", "tier_2", "tier_3", "tier_4"]
DOCUMENT_TYPES = ["dispute_letter", "response", "credit_report", "poa", "adverse_action", "mov_request", "mov_response", "other"]
DAMAGE_TYPES = ["credit_denial", "higher_interest", "emotional_distress", "time_investment", "other"]
RECIPIENT_TYPES = ["bureau", "furnisher"]


# ==================== CASE CRUD ====================

@case_management_router.post("/create")
async def create_case(data: dict, authorization: Optional[str] = Header(None)):
    """Create a new case"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    company_id = data.get("company_id")
    if company_id:
        require_company_access(user, company_id)
    
    # Generate case number
    count = await db.cases.count_documents({})
    case_number = f"CASE-{datetime.now().strftime('%Y%m%d')}-{str(count + 1).zfill(5)}"
    
    case = {
        "id": str(uuid4()),
        "case_number": case_number,
        
        # Client Information
        "client_name": data.get("client_name"),
        "client_first_name": data.get("client_first_name"),
        "client_last_name": data.get("client_last_name"),
        "client_email": data.get("client_email"),
        "client_phone": data.get("client_phone"),
        "client_state": data.get("client_state"),
        "client_city": data.get("client_city"),
        "client_address": data.get("client_address"),
        "client_zip": data.get("client_zip"),
        "client_dob": data.get("client_dob"),
        "client_ssn_last_4": data.get("client_ssn_last_4"),
        
        # Case Classification
        "case_tier": "tier_1",  # Will be auto-calculated
        "estimated_value_min": 0,
        "estimated_value_max": 0,
        "warner_compliant": False,
        "circuit": data.get("circuit"),
        "violation_count": 0,
        "documentation_quality_score": 0,
        
        # Status
        "status": "draft",
        
        # Company Information
        "created_by_company_id": company_id or user.get("company_id"),
        "created_by_company_name": data.get("company_name") or user.get("company_name"),
        "created_by_user_id": user.get("id"),
        "created_by_user_name": user.get("full_name", user.get("name", "Unknown")),
        
        # Attorney Assignment
        "assigned_attorney_id": None,
        "assigned_attorney_name": None,
        "assignment_date": None,
        
        # Publishing
        "published_at": None,
        "listing_id": None,
        
        # Counters
        "disputes_count": 0,
        "documents_count": 0,
        "damages_count": 0,
        
        # Notes
        "internal_notes": data.get("internal_notes"),
        "case_summary": data.get("case_summary"),
        
        # Timestamps
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.cases.insert_one(case)
    
    # Log audit
    await log_case_audit(case["id"], "created", user, None, case)
    
    case.pop("_id", None)
    return {"message": "Case created successfully", "case_id": case["id"], "case_number": case_number}


@case_management_router.get("")
async def list_cases(
    authorization: Optional[str] = Header(None),
    company_id: Optional[str] = None,
    status: Optional[str] = None,
    tier: Optional[str] = None,
    state: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """List cases with filters"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    query = {}
    
    # Company filter
    if user.get("is_company_user"):
        query["created_by_company_id"] = user.get("company_id")
    elif company_id:
        query["created_by_company_id"] = company_id
    
    # Other filters
    if status:
        query["status"] = status
    if tier:
        query["case_tier"] = tier
    if state:
        query["client_state"] = state
    if search:
        query["$or"] = [
            {"case_number": {"$regex": search, "$options": "i"}},
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_email": {"$regex": search, "$options": "i"}}
        ]
    
    # Hide sensitive info for non-admin/non-owner
    projection = {"_id": 0}
    if user.get("is_company_user"):
        # Company users see their own cases fully
        pass
    elif user.get("role") not in ["admin", "super_admin", "director"]:
        projection["client_ssn_last_4"] = 0
        projection["client_dob"] = 0
    
    cases = await db.cases.find(query, projection).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    total = await db.cases.count_documents(query)
    
    return {"cases": cases, "total": total, "skip": skip, "limit": limit}


@case_management_router.get("/{case_id}")
async def get_case(case_id: str, authorization: Optional[str] = Header(None)):
    """Get case details"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Check access
    if user.get("is_company_user") and case.get("created_by_company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get related data
    violations = await db.case_violations.find({"case_id": case_id}, {"_id": 0}).to_list(None)
    disputes = await db.case_disputes.find({"case_id": case_id}, {"_id": 0}).sort("letter_date", 1).to_list(None)
    documents = await db.case_documents.find({"case_id": case_id, "deleted": {"$ne": True}}, {"_id": 0}).to_list(None)
    damages = await db.case_damages.find({"case_id": case_id}, {"_id": 0}).to_list(None)
    interviews = await db.case_interviews.find({"case_id": case_id}, {"_id": 0}).to_list(None)
    compliance = await db.case_compliance_checks.find_one({"case_id": case_id}, {"_id": 0})
    
    return {
        "case": case,
        "violations": violations,
        "disputes": disputes,
        "documents": documents,
        "damages": damages,
        "interviews": interviews,
        "compliance": compliance
    }


@case_management_router.put("/{case_id}")
async def update_case(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update case details"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Check access
    if user.get("is_company_user") and case.get("created_by_company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Store old values for audit
    old_values = {k: case.get(k) for k in data.keys() if k in case}
    
    # Allowed fields
    allowed_fields = [
        "client_name", "client_first_name", "client_last_name", "client_email",
        "client_phone", "client_state", "client_city", "client_address", "client_zip",
        "circuit", "case_summary", "internal_notes", "status"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.cases.update_one({"id": case_id}, {"$set": update_data})
    
    # Log audit
    await log_case_audit(case_id, "updated", user, old_values, update_data)
    
    updated = await db.cases.find_one({"id": case_id}, {"_id": 0})
    return updated


# ==================== DISPUTES ====================

@case_management_router.post("/{case_id}/disputes/add")
async def add_dispute(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Add a dispute round to a case"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Check access
    if user.get("is_company_user") and case.get("created_by_company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    dispute = {
        "id": str(uuid4()),
        "case_id": case_id,
        "recipient_type": data.get("recipient_type"),  # bureau, furnisher
        "recipient_name": data.get("recipient_name"),  # Experian, Equifax, TransUnion, or furnisher name
        "letter_date": data.get("letter_date"),
        "mailing_method": data.get("mailing_method"),  # certified, regular, fax, online
        "tracking_number": data.get("tracking_number"),
        "response_received": data.get("response_received", False),
        "response_date": data.get("response_date"),
        "response_type": data.get("response_type"),  # verified, deleted, frivolous, no_response, investigation
        "days_to_respond": None,
        "dispute_reason": data.get("dispute_reason"),
        "items_disputed": data.get("items_disputed", []),  # List of items disputed
        "notes": data.get("notes"),
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Calculate days to respond if response received
    if dispute["response_received"] and dispute["letter_date"] and dispute["response_date"]:
        try:
            letter = datetime.fromisoformat(dispute["letter_date"].replace("Z", "+00:00"))
            response = datetime.fromisoformat(dispute["response_date"].replace("Z", "+00:00"))
            dispute["days_to_respond"] = (response - letter).days
        except (ValueError, TypeError):
            pass
    
    await db.case_disputes.insert_one(dispute)
    
    # Update case dispute count
    await db.cases.update_one(
        {"id": case_id},
        {
            "$inc": {"disputes_count": 1},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    # Log audit
    await log_case_audit(case_id, "dispute_added", user, None, {"dispute_id": dispute["id"]})
    
    dispute.pop("_id", None)
    return {"message": "Dispute added successfully", "dispute": dispute}


@case_management_router.put("/{case_id}/disputes/{dispute_id}")
async def update_dispute(case_id: str, dispute_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Update a dispute"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    dispute = await db.case_disputes.find_one({"id": dispute_id, "case_id": case_id})
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    
    allowed_fields = [
        "recipient_type", "recipient_name", "letter_date", "mailing_method",
        "tracking_number", "response_received", "response_date", "response_type",
        "dispute_reason", "items_disputed", "notes"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    # Recalculate days to respond
    letter_date = update_data.get("letter_date", dispute.get("letter_date"))
    response_date = update_data.get("response_date", dispute.get("response_date"))
    response_received = update_data.get("response_received", dispute.get("response_received"))
    
    if response_received and letter_date and response_date:
        try:
            letter = datetime.fromisoformat(letter_date.replace("Z", "+00:00"))
            response = datetime.fromisoformat(response_date.replace("Z", "+00:00"))
            update_data["days_to_respond"] = (response - letter).days
        except (ValueError, TypeError):
            pass
    
    await db.case_disputes.update_one({"id": dispute_id}, {"$set": update_data})
    
    updated = await db.case_disputes.find_one({"id": dispute_id}, {"_id": 0})
    return updated


@case_management_router.delete("/{case_id}/disputes/{dispute_id}")
async def delete_dispute(case_id: str, dispute_id: str, authorization: Optional[str] = Header(None)):
    """Delete a dispute"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    result = await db.case_disputes.delete_one({"id": dispute_id, "case_id": case_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dispute not found")
    
    # Update case count
    await db.cases.update_one(
        {"id": case_id},
        {
            "$inc": {"disputes_count": -1},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return {"message": "Dispute deleted successfully"}


# ==================== VIOLATIONS ====================

@case_management_router.post("/{case_id}/violations/add")
async def add_violation(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Add a violation to a case"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    violation = {
        "id": str(uuid4()),
        "case_id": case_id,
        "violation_type": data.get("violation_type"),  # FCRA section (e.g., 1681s-2(b), 1681e(b))
        "violation_description": data.get("violation_description"),
        "defendant": data.get("defendant"),  # CRA or furnisher name
        "defendant_type": data.get("defendant_type"),  # cra, furnisher, data_broker
        "evidence_summary": data.get("evidence_summary"),
        "statutory_basis": data.get("statutory_basis"),
        "potential_damages": data.get("potential_damages"),
        "willfulness_indicators": data.get("willfulness_indicators", []),
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_violations.insert_one(violation)
    
    # Update violation count on case
    violation_count = await db.case_violations.count_documents({"case_id": case_id})
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "violation_count": violation_count,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    violation.pop("_id", None)
    return {"message": "Violation added successfully", "violation": violation}


@case_management_router.delete("/{case_id}/violations/{violation_id}")
async def delete_violation(case_id: str, violation_id: str, authorization: Optional[str] = Header(None)):
    """Delete a violation"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    result = await db.case_violations.delete_one({"id": violation_id, "case_id": case_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Violation not found")
    
    # Update count
    violation_count = await db.case_violations.count_documents({"case_id": case_id})
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "violation_count": violation_count,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"message": "Violation deleted successfully"}


# ==================== DAMAGES ====================

@case_management_router.post("/{case_id}/damages/add")
async def add_damage(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Add damage entry to a case"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    damage = {
        "id": str(uuid4()),
        "case_id": case_id,
        "damage_type": data.get("damage_type"),  # credit_denial, higher_interest, emotional_distress, time_investment, other
        "amount": float(data.get("amount", 0)),
        "calculation_basis": data.get("calculation_basis"),
        "supporting_evidence": data.get("supporting_evidence"),
        "date_incurred": data.get("date_incurred"),
        "notes": data.get("notes"),
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_damages.insert_one(damage)
    
    # Update estimated value on case
    await update_case_value_estimate(case_id)
    
    damage.pop("_id", None)
    return {"message": "Damage added successfully", "damage": damage}


@case_management_router.delete("/{case_id}/damages/{damage_id}")
async def delete_damage(case_id: str, damage_id: str, authorization: Optional[str] = Header(None)):
    """Delete a damage entry"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    result = await db.case_damages.delete_one({"id": damage_id, "case_id": case_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Damage entry not found")
    
    # Update estimated value
    await update_case_value_estimate(case_id)
    
    return {"message": "Damage entry deleted successfully"}


async def update_case_value_estimate(case_id: str):
    """Update case estimated value based on damages"""
    damages = await db.case_damages.find({"case_id": case_id}).to_list(None)
    
    total_documented = sum(d.get("amount", 0) for d in damages)
    
    # Get violation count for statutory damages estimate
    violation_count = await db.case_violations.count_documents({"case_id": case_id})
    
    # Estimated statutory damages ($100 - $1000 per violation)
    statutory_min = violation_count * 100
    statutory_max = violation_count * 1000
    
    # Total estimate
    estimated_min = total_documented + statutory_min
    estimated_max = total_documented + statutory_max
    
    # Determine tier
    if estimated_max < 5000:
        tier = "tier_1"
    elif estimated_max < 15000:
        tier = "tier_2"
    elif estimated_max < 30000:
        tier = "tier_3"
    else:
        tier = "tier_4"
    
    damages_count = len(damages)
    
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "estimated_value_min": estimated_min,
                "estimated_value_max": estimated_max,
                "case_tier": tier,
                "damages_count": damages_count,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )


# ==================== DOCUMENTS ====================

@case_management_router.post("/{case_id}/documents/upload")
async def upload_document(
    case_id: str,
    document_type: str = Form(...),
    document_category: str = Form(None),
    visible_before_payment: bool = Form(True),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Upload a document to a case"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    company_id = case.get("created_by_company_id", "default")
    
    # Create upload directory
    upload_dir = f"./uploads/cases/{company_id}/{case_id}/{document_type}"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_filename = f"{str(uuid4())}{file_ext}"
    file_path = f"{upload_dir}/{unique_filename}"
    
    # Save file
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Determine visibility (some documents should be hidden until attorney pays)
    if document_type in ["poa", "credit_report"]:
        visible_before_payment = False
    
    document = {
        "id": str(uuid4()),
        "case_id": case_id,
        "document_type": document_type,
        "document_category": document_category,
        "file_path": file_path,
        "file_url": f"/api/cases/{case_id}/documents/{unique_filename}",
        "file_name": file.filename,
        "file_size": len(contents),
        "mime_type": file.content_type,
        "visible_before_payment": visible_before_payment,
        "deleted": False,
        "uploaded_by": user.get("id"),
        "uploaded_by_name": user.get("full_name", user.get("name", "Unknown")),
        "upload_date": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_documents.insert_one(document)
    
    # Update document count
    doc_count = await db.case_documents.count_documents({"case_id": case_id, "deleted": {"$ne": True}})
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "documents_count": doc_count,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Recalculate documentation quality score
    await calculate_documentation_quality(case_id)
    
    document.pop("_id", None)
    return {"message": "Document uploaded successfully", "document": document}


@case_management_router.delete("/{case_id}/documents/{document_id}")
async def delete_document(case_id: str, document_id: str, authorization: Optional[str] = Header(None)):
    """Soft delete a document"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    result = await db.case_documents.update_one(
        {"id": document_id, "case_id": case_id},
        {
            "$set": {
                "deleted": True,
                "deleted_by": user.get("id"),
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Update counts
    doc_count = await db.case_documents.count_documents({"case_id": case_id, "deleted": {"$ne": True}})
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "documents_count": doc_count,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    await calculate_documentation_quality(case_id)
    
    return {"message": "Document deleted successfully"}


async def calculate_documentation_quality(case_id: str):
    """Calculate documentation quality score (0-100)"""
    documents = await db.case_documents.find(
        {"case_id": case_id, "deleted": {"$ne": True}}
    ).to_list(None)
    
    # Scoring criteria
    score = 0
    max_score = 100
    
    doc_types = [d.get("document_type") for d in documents]
    
    # Required documents (40 points)
    if "credit_report" in doc_types:
        score += 15
    if "poa" in doc_types:
        score += 15
    if "dispute_letter" in doc_types:
        score += 10
    
    # Supporting documents (30 points)
    if "adverse_action" in doc_types:
        score += 15
    if "response" in doc_types:
        score += 10
    if "mov_request" in doc_types:
        score += 5
    
    # Volume bonus (20 points)
    doc_count = len(documents)
    if doc_count >= 10:
        score += 20
    elif doc_count >= 5:
        score += 10
    elif doc_count >= 3:
        score += 5
    
    # Dispute history bonus (10 points)
    disputes = await db.case_disputes.count_documents({"case_id": case_id})
    if disputes >= 3:
        score += 10
    elif disputes >= 2:
        score += 7
    elif disputes >= 1:
        score += 5
    
    # Cap at 100
    score = min(score, max_score)
    
    await db.cases.update_one(
        {"id": case_id},
        {"$set": {"documentation_quality_score": score}}
    )
    
    return score


# ==================== INTERVIEW ====================

@case_management_router.post("/{case_id}/interview/save")
async def save_interview(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Save client interview data"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    interview = {
        "id": str(uuid4()),
        "case_id": case_id,
        "completed_date": data.get("completed_date", datetime.now(timezone.utc).isoformat()),
        "interviewer": data.get("interviewer", user.get("full_name")),
        "interview_method": data.get("interview_method", "phone"),  # phone, video, in_person, written
        "duration_minutes": data.get("duration_minutes"),
        "responses": data.get("responses", {}),  # JSON object with Q&A
        "fact_form_data": data.get("fact_form_data", {}),  # Structured fact form
        "client_demeanor": data.get("client_demeanor"),
        "credibility_assessment": data.get("credibility_assessment"),
        "additional_notes": data.get("additional_notes"),
        "follow_up_needed": data.get("follow_up_needed", False),
        "follow_up_items": data.get("follow_up_items", []),
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_interviews.insert_one(interview)
    
    interview.pop("_id", None)
    return {"message": "Interview saved successfully", "interview": interview}


# ==================== COMPLIANCE CHECK ====================

@case_management_router.post("/{case_id}/compliance/check")
async def run_compliance_check(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Run or update compliance check for a case"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Calculate compliance
    issues = []
    
    # Check POA
    poa_present = await db.case_documents.count_documents({
        "case_id": case_id,
        "document_type": "poa",
        "deleted": {"$ne": True}
    }) > 0
    
    if not poa_present:
        issues.append({"type": "missing_poa", "severity": "high", "message": "Power of Attorney document required"})
    
    # Check client certification
    client_cert = data.get("client_cert_present", False)
    if not client_cert:
        issues.append({"type": "missing_client_cert", "severity": "high", "message": "Client certification required"})
    
    # Check company certification
    company_cert = data.get("company_cert_present", False)
    if not company_cert:
        issues.append({"type": "missing_company_cert", "severity": "high", "message": "Company certification required"})
    
    # Check disputes exist
    disputes = await db.case_disputes.count_documents({"case_id": case_id})
    if disputes == 0:
        issues.append({"type": "no_disputes", "severity": "medium", "message": "No dispute history recorded"})
    
    # Calculate score
    score = 100
    for issue in issues:
        if issue["severity"] == "high":
            score -= 25
        elif issue["severity"] == "medium":
            score -= 10
        else:
            score -= 5
    score = max(0, score)
    
    # Warner compliant if score >= 80 and no high severity issues
    high_issues = [i for i in issues if i["severity"] == "high"]
    warner_compliant = score >= 80 and len(high_issues) == 0
    
    compliance = {
        "id": str(uuid4()),
        "case_id": case_id,
        "client_cert_present": client_cert,
        "company_cert_present": company_cert,
        "esignature_verified": data.get("esignature_verified", False),
        "poa_notarized": data.get("poa_notarized", False),
        "poa_date": data.get("poa_date"),
        "compliance_score": score,
        "warner_compliant": warner_compliant,
        "issues": issues,
        "checked_by": user.get("id"),
        "checked_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Upsert compliance
    await db.case_compliance_checks.update_one(
        {"case_id": case_id},
        {"$set": compliance},
        upsert=True
    )
    
    # Update case Warner status
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "warner_compliant": warner_compliant,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    compliance.pop("_id", None)
    return {"message": "Compliance check completed", "compliance": compliance}


# ==================== CASE ANALYSIS ====================

@case_management_router.post("/{case_id}/analyze")
async def analyze_case(case_id: str, authorization: Optional[str] = Header(None)):
    """Run comprehensive case analysis"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Get all case data
    violations = await db.case_violations.find({"case_id": case_id}).to_list(None)
    disputes = await db.case_disputes.find({"case_id": case_id}).to_list(None)
    damages = await db.case_damages.find({"case_id": case_id}).to_list(None)
    documents = await db.case_documents.find({"case_id": case_id, "deleted": {"$ne": True}}).to_list(None)
    
    # Violation analysis
    violations_detected = []
    for dispute in disputes:
        if dispute.get("days_to_respond") and dispute["days_to_respond"] > 30:
            violations_detected.append({
                "type": "late_response",
                "description": f"{dispute.get('recipient_name')} responded in {dispute['days_to_respond']} days (>30 days)",
                "defendant": dispute.get("recipient_name"),
                "statutory_basis": "15 U.S.C. § 1681i(a)(1)"
            })
        if dispute.get("response_type") == "no_response":
            violations_detected.append({
                "type": "no_response",
                "description": f"{dispute.get('recipient_name')} failed to respond to dispute",
                "defendant": dispute.get("recipient_name"),
                "statutory_basis": "15 U.S.C. § 1681i(a)(1)"
            })
    
    # Documentation quality
    doc_quality = await calculate_documentation_quality(case_id)
    
    # Missing items
    missing_items = []
    doc_types = [d.get("document_type") for d in documents]
    if "credit_report" not in doc_types:
        missing_items.append("Credit report")
    if "poa" not in doc_types:
        missing_items.append("Power of Attorney")
    if "dispute_letter" not in doc_types:
        missing_items.append("Dispute letters")
    if len(disputes) == 0:
        missing_items.append("Dispute history")
    
    # Value estimate
    total_damages = sum(d.get("amount", 0) for d in damages)
    violation_count = len(violations) + len(violations_detected)
    
    estimated_min = total_damages + (violation_count * 100)
    estimated_max = total_damages + (violation_count * 1000)
    
    # Tier determination
    if estimated_max < 5000:
        tier = "tier_1"
    elif estimated_max < 15000:
        tier = "tier_2"
    elif estimated_max < 30000:
        tier = "tier_3"
    else:
        tier = "tier_4"
    
    # Warner compliance status
    compliance = await db.case_compliance_checks.find_one({"case_id": case_id})
    warner_status = compliance.get("warner_compliant", False) if compliance else False
    
    # Update case with analysis
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "estimated_value_min": estimated_min,
                "estimated_value_max": estimated_max,
                "case_tier": tier,
                "violation_count": violation_count,
                "documentation_quality_score": doc_quality,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "case_id": case_id,
        "compliance_status": {
            "warner_compliant": warner_status,
            "issues": compliance.get("issues", []) if compliance else []
        },
        "violations_detected": violations_detected,
        "existing_violations": len(violations),
        "total_violations": violation_count,
        "tier": tier,
        "tier_description": f"Tier {tier[-1]}: {tier.replace('tier_', '').upper()}",
        "estimated_value_range": {
            "min": estimated_min,
            "max": estimated_max
        },
        "quality_score": doc_quality,
        "missing_items": missing_items,
        "ready_for_marketplace": doc_quality >= 60 and warner_status and len(missing_items) <= 2
    }


@case_management_router.get("/{case_id}/readiness")
async def check_marketplace_readiness(case_id: str, authorization: Optional[str] = Header(None)):
    """Check if case is ready for marketplace"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    blocking_issues = []
    warnings = []
    
    # Check documentation quality
    quality_score = case.get("documentation_quality_score", 0)
    if quality_score < 40:
        blocking_issues.append(f"Documentation quality score too low ({quality_score}/100, minimum 40 required)")
    elif quality_score < 60:
        warnings.append(f"Documentation quality score is fair ({quality_score}/100, 60+ recommended)")
    
    # Check Warner compliance
    if not case.get("warner_compliant"):
        blocking_issues.append("Case is not Warner compliant")
    
    # Check violations
    if case.get("violation_count", 0) == 0:
        blocking_issues.append("No violations documented")
    
    # Check disputes
    disputes_count = case.get("disputes_count", 0)
    if disputes_count == 0:
        blocking_issues.append("No dispute history")
    elif disputes_count < 2:
        warnings.append("Limited dispute history (2+ rounds recommended)")
    
    # Check documents
    documents_count = case.get("documents_count", 0)
    if documents_count < 3:
        warnings.append("Limited documentation uploaded")
    
    # Check estimated value
    if case.get("estimated_value_max", 0) < 3000:
        warnings.append("Estimated case value is low")
    
    ready = len(blocking_issues) == 0
    
    return {
        "ready": ready,
        "quality_score": quality_score,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "case_tier": case.get("case_tier"),
        "estimated_value": {
            "min": case.get("estimated_value_min", 0),
            "max": case.get("estimated_value_max", 0)
        }
    }


# ==================== MARKETPLACE PUBLISHING ====================

@case_management_router.post("/{case_id}/publish")
async def publish_to_marketplace(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """Publish case to attorney marketplace"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Check readiness
    if case.get("status") == "published":
        raise HTTPException(status_code=400, detail="Case is already published")
    
    # Create marketplace listing
    listing = {
        "id": str(uuid4()),
        "case_id": case_id,
        "listing_type": data.get("listing_type", "pledge"),  # bidding, pledge
        "minimum_bid": data.get("minimum_bid"),
        "required_pledge_amount": data.get("required_pledge_amount"),
        "listing_expires_at": data.get("expires_at"),
        "view_count": 0,
        "watchlist_count": 0,
        "featured": data.get("featured", False),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_marketplace_listings.insert_one(listing)
    
    # Update case status
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "status": "published",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "listing_id": listing["id"],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Log audit
    await log_case_audit(case_id, "published", user, None, {"listing_id": listing["id"]})
    
    return {"message": "Case published to marketplace", "listing_id": listing["id"]}


@case_management_router.put("/{case_id}/unpublish")
async def unpublish_from_marketplace(case_id: str, authorization: Optional[str] = Header(None)):
    """Remove case from marketplace"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    if case.get("status") != "published":
        raise HTTPException(status_code=400, detail="Case is not published")
    
    # Check for accepted bids
    if case.get("assigned_attorney_id"):
        raise HTTPException(status_code=400, detail="Cannot unpublish case with assigned attorney")
    
    # Remove listing
    if case.get("listing_id"):
        await db.case_marketplace_listings.delete_one({"id": case.get("listing_id")})
    
    # Update case
    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "status": "draft",
                "published_at": None,
                "listing_id": None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Log audit
    await log_case_audit(case_id, "unpublished", user, None, None)
    
    return {"message": "Case removed from marketplace"}


# ==================== TIMELINE ====================

@case_management_router.get("/{case_id}/timeline")
async def get_case_timeline(case_id: str, authorization: Optional[str] = Header(None)):
    """Get chronological timeline of all case events"""
    user = await get_current_user(authorization)
    require_auth(user)
    
    timeline = []
    
    # Disputes
    disputes = await db.case_disputes.find({"case_id": case_id}, {"_id": 0}).to_list(None)
    for d in disputes:
        timeline.append({
            "type": "dispute_sent",
            "date": d.get("letter_date"),
            "title": f"Dispute sent to {d.get('recipient_name')}",
            "description": f"Method: {d.get('mailing_method')}",
            "data": {k: v for k, v in d.items() if k != "_id"}
        })
        if d.get("response_received"):
            timeline.append({
                "type": "response_received",
                "date": d.get("response_date"),
                "title": f"Response from {d.get('recipient_name')}",
                "description": f"Response type: {d.get('response_type')}, Days: {d.get('days_to_respond')}",
                "data": {k: v for k, v in d.items() if k != "_id"}
            })
    
    # Documents
    documents = await db.case_documents.find({"case_id": case_id, "deleted": {"$ne": True}}, {"_id": 0}).to_list(None)
    for doc in documents:
        timeline.append({
            "type": "document_uploaded",
            "date": doc.get("upload_date"),
            "title": f"Document uploaded: {doc.get('file_name')}",
            "description": f"Type: {doc.get('document_type')}",
            "data": {k: v for k, v in doc.items() if k != "_id"}
        })
    
    # Audit log - exclude _id and handle nested objects
    audit = await db.case_audit_log.find({"case_id": case_id}, {"_id": 0}).to_list(None)
    for a in audit:
        # Clean nested objects that might contain ObjectId
        clean_data = {}
        for k, v in a.items():
            if k == "_id":
                continue
            if isinstance(v, dict):
                clean_data[k] = {dk: dv for dk, dv in v.items() if dk != "_id"} if v else v
            else:
                clean_data[k] = v
        
        timeline.append({
            "type": "audit",
            "date": a.get("timestamp"),
            "title": f"Case {a.get('action_type')}",
            "description": f"By: {a.get('changed_by_name', 'System')}",
            "data": clean_data
        })
    
    # Sort by date
    timeline.sort(key=lambda x: x.get("date") or "", reverse=True)
    
    return {"timeline": timeline}


# ==================== AUDIT LOGGING ====================

async def log_case_audit(case_id: str, action_type: str, user: dict, old_values: dict, new_values: dict):
    """Log case audit entry"""
    audit = {
        "id": str(uuid4()),
        "case_id": case_id,
        "action_type": action_type,
        "changed_by_user_id": user.get("id") if user else None,
        "changed_by_name": user.get("full_name", user.get("name", "System")) if user else "System",
        "changed_by_company_id": user.get("company_id") if user else None,
        "old_values": old_values,
        "new_values": new_values,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.case_audit_log.insert_one(audit)
