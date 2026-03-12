"""
Audit Logging for Attorney Marketplace

Logs all security-related events:
- Failed authorization attempts
- Document access (who accessed what, when)
- Role changes
- Permission grants/revokes
- Admin overrides
- Payment verifications
- Subscription status changes
- Case ownership transfers

Retention: Minimum 7 years for financial records
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from uuid import uuid4


class AuditLogger:
    """Centralized audit logging system"""
    
    @staticmethod
    async def log_event(
        db: AsyncIOMotorDatabase,
        event_type: str,
        user_id: Optional[str],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        success: bool = True,
        failure_reason: Optional[str] = None,
        metadata: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        Log a general audit event
        
        Returns:
            Event ID
        """
        event_id = str(uuid4())
        event = {
            "id": event_id,
            "event_type": event_type,
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "success": success,
            "failure_reason": failure_reason,
            "metadata": metadata or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "retention_years": 7  # Financial record retention
        }
        
        await db.audit_log.insert_one(event)
        return event_id
    
    @staticmethod
    async def log_security_event(
        db: AsyncIOMotorDatabase,
        event_type: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """Log a security-related event (failed access, etc.)"""
        return await AuditLogger.log_event(
            db,
            event_type=f"security.{event_type}",
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            success=False,
            failure_reason=reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    async def log_document_access(
        db: AsyncIOMotorDatabase,
        user_id: str,
        document_id: str,
        case_id: str,
        access_type: str = "view",
        ip_address: Optional[str] = None
    ) -> str:
        """Log document access for compliance"""
        return await AuditLogger.log_event(
            db,
            event_type="document.access",
            user_id=user_id,
            action=access_type,
            resource_type="document",
            resource_id=document_id,
            success=True,
            metadata={"case_id": case_id, "access_type": access_type},
            ip_address=ip_address
        )
    
    @staticmethod
    async def log_document_access_grant(
        db: AsyncIOMotorDatabase,
        attorney_id: str,
        case_id: str,
        granted_by: str
    ) -> str:
        """Log when document access is granted to attorney"""
        return await AuditLogger.log_event(
            db,
            event_type="document.access_granted",
            user_id=granted_by,
            action="grant_access",
            resource_type="case",
            resource_id=case_id,
            success=True,
            metadata={
                "attorney_id": attorney_id,
                "granted_by": granted_by
            }
        )
    
    @staticmethod
    async def log_payment_verification(
        db: AsyncIOMotorDatabase,
        attorney_id: str,
        case_id: str,
        verified: bool,
        reason: Optional[str] = None
    ) -> str:
        """Log payment verification events"""
        return await AuditLogger.log_event(
            db,
            event_type="payment.verification",
            user_id=attorney_id,
            action="verify_payment",
            resource_type="case",
            resource_id=case_id,
            success=verified,
            failure_reason=reason,
            metadata={"attorney_id": attorney_id}
        )
    
    @staticmethod
    async def log_role_change(
        db: AsyncIOMotorDatabase,
        user_id: str,
        changed_by: str,
        old_role: str,
        new_role: str
    ) -> str:
        """Log role changes"""
        return await AuditLogger.log_event(
            db,
            event_type="user.role_change",
            user_id=changed_by,
            action="change_role",
            resource_type="user",
            resource_id=user_id,
            success=True,
            metadata={
                "target_user_id": user_id,
                "old_role": old_role,
                "new_role": new_role
            }
        )
    
    @staticmethod
    async def log_admin_override(
        db: AsyncIOMotorDatabase,
        admin_user_id: str,
        operation: str,
        params: Dict[str, Any],
        justification: str
    ) -> str:
        """Log admin override actions"""
        return await AuditLogger.log_event(
            db,
            event_type="admin.override",
            user_id=admin_user_id,
            action=operation,
            resource_type="admin_override",
            resource_id=None,
            success=True,
            metadata={
                "operation": operation,
                "params": params,
                "justification": justification
            }
        )
    
    @staticmethod
    async def log_subscription_change(
        db: AsyncIOMotorDatabase,
        company_id: str,
        changed_by: str,
        old_status: str,
        new_status: str,
        change_type: str = "status_change"
    ) -> str:
        """Log subscription status changes"""
        return await AuditLogger.log_event(
            db,
            event_type=f"subscription.{change_type}",
            user_id=changed_by,
            action=change_type,
            resource_type="subscription",
            resource_id=company_id,
            success=True,
            metadata={
                "company_id": company_id,
                "old_status": old_status,
                "new_status": new_status
            }
        )
    
    @staticmethod
    async def log_case_ownership_transfer(
        db: AsyncIOMotorDatabase,
        case_id: str,
        from_company_id: str,
        to_company_id: str,
        transferred_by: str,
        reason: str
    ) -> str:
        """Log case ownership transfers"""
        return await AuditLogger.log_event(
            db,
            event_type="case.ownership_transfer",
            user_id=transferred_by,
            action="transfer_ownership",
            resource_type="case",
            resource_id=case_id,
            success=True,
            metadata={
                "from_company_id": from_company_id,
                "to_company_id": to_company_id,
                "reason": reason
            }
        )
    
    @staticmethod
    async def log_bid_action(
        db: AsyncIOMotorDatabase,
        bid_id: str,
        case_id: str,
        attorney_id: str,
        action: str,
        performed_by: str,
        bid_amount: Optional[float] = None
    ) -> str:
        """Log bid-related actions"""
        return await AuditLogger.log_event(
            db,
            event_type=f"bid.{action}",
            user_id=performed_by,
            action=action,
            resource_type="bid",
            resource_id=bid_id,
            success=True,
            metadata={
                "case_id": case_id,
                "attorney_id": attorney_id,
                "bid_amount": bid_amount
            }
        )
    
    @staticmethod
    async def log_login_attempt(
        db: AsyncIOMotorDatabase,
        email: str,
        success: bool,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """Log login attempts"""
        return await AuditLogger.log_event(
            db,
            event_type="auth.login_attempt",
            user_id=None,
            action="login",
            resource_type="auth",
            resource_id=None,
            success=success,
            failure_reason=reason,
            metadata={"email": email},
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    async def get_audit_trail(
        db: AsyncIOMotorDatabase,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ):
        """
        Query audit trail with filters
        
        Args:
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            user_id: Filter by user
            event_type: Filter by event type
            start_date: Filter from date
            end_date: Filter to date
            limit: Max results
        
        Returns:
            List of audit events
        """
        query = {}
        
        if resource_type:
            query["resource_type"] = resource_type
        if resource_id:
            query["resource_id"] = resource_id
        if user_id:
            query["user_id"] = user_id
        if event_type:
            query["event_type"] = {"$regex": f"^{event_type}"}
        if start_date:
            query.setdefault("timestamp", {})["$gte"] = start_date
        if end_date:
            query.setdefault("timestamp", {})["$lte"] = end_date
        
        events = await db.audit_log.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
        return events
