"""
Data Access Policies for Attorney Marketplace

Implements access control for:
- credit_repair_companies
- cases
- case_documents
- company_subscriptions
- case_bids
- company_revenue_splits
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from .roles import (
    UserRole, Permission, has_permission, is_credlocity_staff,
    is_company_user, is_attorney_user
)


class AccessResult:
    """Result of an access check"""
    def __init__(self, allowed: bool, reason: Optional[str] = None, data: Optional[Dict] = None):
        self.allowed = allowed
        self.reason = reason
        self.data = data or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "data": self.data
        }


class CompanyAccessPolicy:
    """
    Access control for credit_repair_companies table
    
    Rules:
    - Company owners: Full access to their own company
    - Company staff: Read-only access to their company
    - Credlocity admins: Full access to all companies
    - Credlocity support: Read access to all companies
    - Everyone else: No access
    """
    
    @staticmethod
    def can_read(user: Dict, company_id: str) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        
        # Credlocity staff can read all
        if is_credlocity_staff(role):
            return AccessResult(True)
        
        # Company users can read their own
        if is_company_user(role) and user_company_id == company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: You can only view your own company")
    
    @staticmethod
    def can_write(user: Dict, company_id: str) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        
        # Credlocity admin has full access
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ADMIN]:
            return AccessResult(True)
        
        # Company owner can update their own
        if role == UserRole.COMPANY_OWNER and user_company_id == company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Only company owner can modify company data")
    
    @staticmethod
    def can_delete(user: Dict, company_id: str) -> AccessResult:
        role = user.get("role", "")
        
        # Only Credlocity admin can delete companies
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Only Credlocity administrators can delete companies")


class CaseAccessPolicy:
    """
    Access control for cases table
    
    Rules:
    - Company owner/staff: Full access to cases created by their company
    - Attorneys: Read access to published cases only
    - Assigned attorneys: Full access to cases assigned to them (after payment)
    - Credlocity admins: Full access to all cases
    - Everyone else: No access
    """
    
    @staticmethod
    def can_read(user: Dict, case: Dict) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        user_attorney_id = user.get("attorney_profile_id")
        case_company_id = case.get("company_id")
        case_status = case.get("status", "")
        assigned_attorney_id = case.get("assigned_attorney_id")
        payment_verified = case.get("payment_verified", False)
        
        # Credlocity staff can read all
        if is_credlocity_staff(role):
            return AccessResult(True)
        
        # Company users can read their own cases
        if is_company_user(role) and user_company_id == case_company_id:
            return AccessResult(True)
        
        # Attorneys can read published cases
        if is_attorney_user(role):
            if case_status == "published":
                return AccessResult(True, data={"preview_only": True})
            
            # Assigned attorney with payment verified gets full access
            if assigned_attorney_id == user_attorney_id and payment_verified:
                return AccessResult(True, data={"full_access": True})
        
        return AccessResult(False, "Access denied: Case not accessible")
    
    @staticmethod
    def can_write(user: Dict, case: Dict) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        user_attorney_id = user.get("attorney_profile_id")
        case_company_id = case.get("company_id")
        assigned_attorney_id = case.get("assigned_attorney_id")
        payment_verified = case.get("payment_verified", False)
        
        # Credlocity admin has full access
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ADMIN]:
            return AccessResult(True)
        
        # Company owner can update their cases
        if role == UserRole.COMPANY_OWNER and user_company_id == case_company_id:
            return AccessResult(True)
        
        # Assigned attorney with payment can update limited fields
        if role == UserRole.ATTORNEY and assigned_attorney_id == user_attorney_id and payment_verified:
            return AccessResult(True, data={"limited_fields": ["attorney_notes", "case_status_attorney"]})
        
        return AccessResult(False, "Access denied: Cannot modify this case")
    
    @staticmethod
    def can_delete(user: Dict, case: Dict) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        case_company_id = case.get("company_id")
        
        # Only Credlocity admin or company owner can delete
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
            return AccessResult(True)
        
        if role == UserRole.COMPANY_OWNER and user_company_id == case_company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Cannot delete this case")
    
    @staticmethod
    def can_publish(user: Dict, case: Dict) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        case_company_id = case.get("company_id")
        
        # Credlocity admin or company owner can publish
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
            return AccessResult(True)
        
        if role == UserRole.COMPANY_OWNER and user_company_id == case_company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Only company owner can publish cases")


class DocumentAccessPolicy:
    """
    Access control for case_documents table
    
    Rules:
    - Company: Full access to documents in their cases
    - Attorneys (before payment): Access only to documents marked visible_before_payment
    - Attorneys (after payment verified): Full access to all documents in assigned cases
    - Credlocity admins: Full access
    - Everyone else: No access
    """
    
    @staticmethod
    def can_access(user: Dict, document: Dict, case: Dict) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        user_attorney_id = user.get("attorney_profile_id")
        case_company_id = case.get("company_id")
        assigned_attorney_id = case.get("assigned_attorney_id")
        payment_verified = case.get("payment_verified", False)
        visible_before_payment = document.get("visible_before_payment", False)
        
        # Credlocity staff can access all
        if is_credlocity_staff(role):
            return AccessResult(True, data={"document_url": document.get("url")})
        
        # Company users can access their documents
        if is_company_user(role) and user_company_id == case_company_id:
            return AccessResult(True, data={"document_url": document.get("url")})
        
        # Attorneys
        if is_attorney_user(role):
            # Preview documents are accessible
            if visible_before_payment:
                return AccessResult(True, data={"document_url": document.get("preview_url", document.get("url"))})
            
            # Full access after payment
            if assigned_attorney_id == user_attorney_id and payment_verified:
                return AccessResult(True, data={"document_url": document.get("url")})
            
            return AccessResult(False, "Access denied: Full document access requires payment verification")
        
        return AccessResult(False, "Access denied: Document not accessible")


class SubscriptionAccessPolicy:
    """
    Access control for company_subscriptions table
    
    Rules:
    - Company owners: Read access to their subscription only
    - Credlocity admins: Full access
    - Direct modification blocked (changes only via webhooks or admin interface)
    - Everyone else: No access
    """
    
    @staticmethod
    def can_read(user: Dict, subscription_company_id: str) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        
        # Credlocity staff can read all
        if is_credlocity_staff(role):
            return AccessResult(True)
        
        # Company owner can read their own
        if role == UserRole.COMPANY_OWNER and user_company_id == subscription_company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Can only view your own subscription")
    
    @staticmethod
    def can_modify(user: Dict, subscription_company_id: str) -> AccessResult:
        role = user.get("role", "")
        
        # Only Credlocity admin can directly modify (or via webhooks)
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Subscription modifications are restricted")


class BidAccessPolicy:
    """
    Access control for case_bids table
    
    Rules:
    - Attorneys: Full access to their own bids
    - Companies: Read access to bids on their cases
    - Credlocity admins: Full access
    - Everyone else: No access
    """
    
    @staticmethod
    def can_read(user: Dict, bid: Dict, case: Dict) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        user_attorney_id = user.get("attorney_profile_id")
        bid_attorney_id = bid.get("attorney_id")
        case_company_id = case.get("company_id")
        
        # Credlocity staff can read all
        if is_credlocity_staff(role):
            return AccessResult(True)
        
        # Attorney can read their own bids
        if is_attorney_user(role) and user_attorney_id == bid_attorney_id:
            return AccessResult(True)
        
        # Company can read bids on their cases
        if is_company_user(role) and user_company_id == case_company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Bid not accessible")
    
    @staticmethod
    def can_create(user: Dict) -> AccessResult:
        role = user.get("role", "")
        
        if role == UserRole.ATTORNEY:
            return AccessResult(True)
        
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Only verified attorneys can place bids")
    
    @staticmethod
    def can_modify(user: Dict, bid: Dict) -> AccessResult:
        role = user.get("role", "")
        user_attorney_id = user.get("attorney_profile_id")
        bid_attorney_id = bid.get("attorney_id")
        bid_status = bid.get("status", "")
        
        # Credlocity admin can always modify
        if role in [UserRole.CREDLOCITY_ADMIN, UserRole.SUPER_ADMIN]:
            return AccessResult(True)
        
        # Attorney can modify their own pending bids
        if role == UserRole.ATTORNEY and user_attorney_id == bid_attorney_id:
            if bid_status in ["pending", "draft"]:
                return AccessResult(True)
            return AccessResult(False, "Access denied: Cannot modify accepted/rejected bids")
        
        return AccessResult(False, "Access denied: Cannot modify this bid")


class RevenueAccessPolicy:
    """
    Access control for company_revenue_splits table
    
    Rules:
    - Company owners: Read access to their revenue records only
    - Credlocity admins: Full access
    - Modification blocked (revenue records are immutable once created)
    - Everyone else: No access
    """
    
    @staticmethod
    def can_read(user: Dict, revenue_company_id: str) -> AccessResult:
        role = user.get("role", "")
        user_company_id = user.get("company_id")
        
        # Credlocity staff can read all
        if is_credlocity_staff(role):
            return AccessResult(True)
        
        # Company owner can read their own
        if role == UserRole.COMPANY_OWNER and user_company_id == revenue_company_id:
            return AccessResult(True)
        
        return AccessResult(False, "Access denied: Can only view your own revenue records")
    
    @staticmethod
    def can_modify(user: Dict) -> AccessResult:
        # Revenue records are immutable
        return AccessResult(False, "Access denied: Revenue records cannot be modified")
