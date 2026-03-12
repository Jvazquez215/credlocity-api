"""
API Authorization Functions for Attorney Marketplace

Provides authorization check functions:
- checkCaseAccess
- checkDocumentAccess
- checkSubscriptionAccess
- verifyAttorneyPayment
- grantDocumentAccess
- verifyAttorneyCredentials
"""

from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import os

from .roles import UserRole, is_credlocity_staff, is_company_user, is_attorney_user
from .access_control import (
    AccessResult, CaseAccessPolicy, DocumentAccessPolicy,
    SubscriptionAccessPolicy, BidAccessPolicy
)
from .audit_logger import AuditLogger


async def get_user_context(db: AsyncIOMotorDatabase, user_id: str) -> Dict[str, Any]:
    """
    Get full user context including role and associations
    
    Returns:
        {
            "user_id": str,
            "role": str,
            "company_id": str | None,
            "attorney_profile_id": str | None,
            "permissions": list,
            "is_verified": bool
        }
    """
    # Try to find in users collection
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user:
        return None
    
    context = {
        "user_id": user_id,
        "role": user.get("role", "viewer"),
        "company_id": user.get("company_id"),
        "attorney_profile_id": user.get("attorney_profile_id"),
        "permissions": user.get("permissions", []),
        "is_verified": user.get("is_verified", False),
        "email": user.get("email"),
        "full_name": user.get("full_name")
    }
    
    # If company user, get company_id from company_users collection
    if not context["company_id"]:
        company_user = await db.company_users.find_one({"user_id": user_id}, {"_id": 0})
        if company_user:
            context["company_id"] = company_user.get("company_id")
            context["role"] = company_user.get("role", context["role"])
    
    # If attorney, get attorney_profile_id
    if not context["attorney_profile_id"]:
        attorney = await db.attorney_profiles.find_one({"user_id": user_id}, {"_id": 0})
        if attorney:
            context["attorney_profile_id"] = attorney.get("id")
            context["is_verified"] = attorney.get("verified", False)
    
    return context


async def check_case_access(
    db: AsyncIOMotorDatabase,
    user_id: str,
    case_id: str,
    required_permission: str = "read"
) -> AccessResult:
    """
    Check if user can access a case
    
    Args:
        db: Database connection
        user_id: User ID
        case_id: Case ID
        required_permission: "read", "write", "delete", "publish"
    
    Returns:
        AccessResult with allowed status and reason
    """
    # Get user context
    user = await get_user_context(db, user_id)
    if not user:
        return AccessResult(False, "User not found")
    
    # Get case
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        return AccessResult(False, "Case not found")
    
    # Check access based on permission type
    if required_permission == "read":
        result = CaseAccessPolicy.can_read(user, case)
    elif required_permission == "write":
        result = CaseAccessPolicy.can_write(user, case)
    elif required_permission == "delete":
        result = CaseAccessPolicy.can_delete(user, case)
    elif required_permission == "publish":
        result = CaseAccessPolicy.can_publish(user, case)
    else:
        result = AccessResult(False, f"Unknown permission: {required_permission}")
    
    # Log failed access attempts
    if not result.allowed:
        await AuditLogger.log_security_event(
            db,
            event_type="access_denied",
            user_id=user_id,
            resource_type="case",
            resource_id=case_id,
            action=required_permission,
            reason=result.reason
        )
    
    return result


async def check_document_access(
    db: AsyncIOMotorDatabase,
    user_id: str,
    document_id: str
) -> AccessResult:
    """
    Check if user can access a document
    
    Returns:
        AccessResult with allowed status and document_url if allowed
    """
    # Get user context
    user = await get_user_context(db, user_id)
    if not user:
        return AccessResult(False, "User not found")
    
    # Get document
    document = await db.case_documents.find_one({"id": document_id}, {"_id": 0})
    if not document:
        return AccessResult(False, "Document not found")
    
    # Get associated case
    case = await db.cases.find_one({"id": document.get("case_id")}, {"_id": 0})
    if not case:
        return AccessResult(False, "Associated case not found")
    
    result = DocumentAccessPolicy.can_access(user, document, case)
    
    # Log document access
    if result.allowed:
        await AuditLogger.log_document_access(
            db,
            user_id=user_id,
            document_id=document_id,
            case_id=case.get("id"),
            access_type="full" if result.data.get("document_url") == document.get("url") else "preview"
        )
    else:
        await AuditLogger.log_security_event(
            db,
            event_type="document_access_denied",
            user_id=user_id,
            resource_type="document",
            resource_id=document_id,
            action="read",
            reason=result.reason
        )
    
    return result


async def check_subscription_access(
    db: AsyncIOMotorDatabase,
    user_id: str,
    company_id: str
) -> AccessResult:
    """
    Check if user can access subscription data
    """
    user = await get_user_context(db, user_id)
    if not user:
        return AccessResult(False, "User not found")
    
    return SubscriptionAccessPolicy.can_read(user, company_id)


async def verify_attorney_payment(
    db: AsyncIOMotorDatabase,
    attorney_id: str,
    case_id: str
) -> Tuple[bool, Optional[str]]:
    """
    Verify if attorney has paid for case access
    
    Returns:
        (is_verified, reason)
    """
    # Check case_assignments table
    assignment = await db.case_assignments.find_one({
        "attorney_id": attorney_id,
        "case_id": case_id
    }, {"_id": 0})
    
    if not assignment:
        return False, "No assignment found for this attorney and case"
    
    # Verify payment
    if not assignment.get("payment_verified"):
        return False, "Payment not verified"
    
    # Check status
    if assignment.get("status") != "active":
        return False, f"Assignment status is {assignment.get('status')}, not active"
    
    # Log successful verification
    await AuditLogger.log_payment_verification(
        db,
        attorney_id=attorney_id,
        case_id=case_id,
        verified=True
    )
    
    return True, None


async def grant_document_access(
    db: AsyncIOMotorDatabase,
    attorney_id: str,
    case_id: str,
    granted_by: str
) -> Dict[str, Any]:
    """
    Grant full document access to attorney after bid/pledge accepted
    
    Called when bid is accepted:
    1. Create/update case_assignment record
    2. Set payment_verified = true
    3. Log event in audit_log
    
    Returns:
        Result dict with status
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Create or update assignment
    assignment = {
        "attorney_id": attorney_id,
        "case_id": case_id,
        "payment_verified": True,
        "status": "active",
        "granted_at": now,
        "granted_by": granted_by,
        "updated_at": now
    }
    
    await db.case_assignments.update_one(
        {"attorney_id": attorney_id, "case_id": case_id},
        {"$set": assignment},
        upsert=True
    )
    
    # Log the event
    await AuditLogger.log_document_access_grant(
        db,
        attorney_id=attorney_id,
        case_id=case_id,
        granted_by=granted_by
    )
    
    return {
        "success": True,
        "message": "Document access granted",
        "assignment": assignment
    }


async def verify_attorney_credentials(
    db: AsyncIOMotorDatabase,
    attorney_id: str
) -> Dict[str, Any]:
    """
    Verify attorney credentials before allowing them to bid
    
    Checks:
    1. Bar number verified
    2. Licensed in relevant states
    3. Malpractice insurance on file (if required)
    4. Background check completed (if required)
    5. Payment method on file
    6. Terms of service accepted
    
    Returns:
        {
            "verified": bool,
            "checks": {
                "bar_number": bool,
                "licensed_states": list,
                "malpractice_insurance": bool,
                "background_check": bool,
                "payment_method": bool,
                "terms_accepted": bool
            },
            "reason": str | None
        }
    """
    attorney = await db.attorney_profiles.find_one({"id": attorney_id}, {"_id": 0})
    
    if not attorney:
        return {
            "verified": False,
            "checks": {},
            "reason": "Attorney profile not found"
        }
    
    checks = {
        "bar_number": bool(attorney.get("bar_number_verified", False)),
        "licensed_states": attorney.get("licensed_states", []),
        "malpractice_insurance": bool(attorney.get("malpractice_insurance_on_file", False)),
        "background_check": bool(attorney.get("background_check_completed", False)),
        "payment_method": bool(attorney.get("payment_method_on_file", False)),
        "terms_accepted": bool(attorney.get("terms_accepted", False))
    }
    
    # Determine if all required checks pass
    required_checks = ["bar_number", "payment_method", "terms_accepted"]
    missing_checks = [c for c in required_checks if not checks.get(c)]
    
    verified = len(missing_checks) == 0
    reason = None if verified else f"Missing requirements: {', '.join(missing_checks)}"
    
    return {
        "verified": verified,
        "checks": checks,
        "reason": reason
    }


async def execute_as_admin(
    db: AsyncIOMotorDatabase,
    admin_user_id: str,
    operation: str,
    params: Dict[str, Any],
    justification: str
) -> Dict[str, Any]:
    """
    Execute an operation with admin override privileges
    
    Only callable by credlocity_admin role.
    Logs all admin override actions.
    
    Args:
        db: Database connection
        admin_user_id: Admin user ID
        operation: Operation name
        params: Operation parameters
        justification: Required justification for the override
    
    Returns:
        Operation result
    """
    # Verify admin role
    user = await get_user_context(db, admin_user_id)
    if not user or user.get("role") not in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
        raise PermissionError("Only Credlocity administrators can execute admin overrides")
    
    if not justification or len(justification.strip()) < 10:
        raise ValueError("A detailed justification is required for admin overrides")
    
    # Log the admin action
    await AuditLogger.log_admin_override(
        db,
        admin_user_id=admin_user_id,
        operation=operation,
        params=params,
        justification=justification
    )
    
    # Return success - actual operation would be performed by caller
    return {
        "success": True,
        "operation": operation,
        "executed_by": admin_user_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
