"""
User Roles & Permissions for Attorney Marketplace

Role Hierarchy:
- credlocity_admin: Full access to everything
- credlocity_support: Can view cases, assist companies
- company_owner: Owns a credit repair company
- company_staff: Works for a company, limited access
- attorney: Can browse marketplace, bid on cases
- attorney_staff: Works for attorney, can view assigned cases
"""

from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel

class UserRole(str, Enum):
    CREDLOCITY_ADMIN = "credlocity_admin"
    CREDLOCITY_SUPPORT = "credlocity_support"
    COMPANY_OWNER = "company_owner"
    COMPANY_STAFF = "company_staff"
    ATTORNEY = "attorney"
    ATTORNEY_STAFF = "attorney_staff"
    # Legacy roles mapping
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"
    AUTHOR = "author"
    VIEWER = "viewer"

# Role hierarchy for permission checks (higher number = more privileges)
ROLE_HIERARCHY: Dict[str, int] = {
    UserRole.CREDLOCITY_ADMIN: 100,
    UserRole.SUPER_ADMIN: 100,  # Legacy mapping
    UserRole.ADMIN: 90,  # Legacy mapping
    UserRole.CREDLOCITY_SUPPORT: 80,
    UserRole.COMPANY_OWNER: 60,
    UserRole.ATTORNEY: 50,
    UserRole.COMPANY_STAFF: 40,
    UserRole.ATTORNEY_STAFF: 30,
    UserRole.EDITOR: 70,  # Legacy
    UserRole.AUTHOR: 50,  # Legacy
    UserRole.VIEWER: 10,
}

# Permission definitions
class Permission(str, Enum):
    # Case permissions
    CASE_CREATE = "case:create"
    CASE_READ = "case:read"
    CASE_READ_OWN = "case:read_own"
    CASE_READ_PUBLISHED = "case:read_published"
    CASE_READ_ASSIGNED = "case:read_assigned"
    CASE_UPDATE = "case:update"
    CASE_UPDATE_OWN = "case:update_own"
    CASE_DELETE = "case:delete"
    CASE_PUBLISH = "case:publish"
    
    # Document permissions
    DOC_UPLOAD = "document:upload"
    DOC_READ = "document:read"
    DOC_READ_PREVIEW = "document:read_preview"
    DOC_READ_FULL = "document:read_full"
    DOC_DELETE = "document:delete"
    
    # Company permissions
    COMPANY_CREATE = "company:create"
    COMPANY_READ = "company:read"
    COMPANY_READ_OWN = "company:read_own"
    COMPANY_UPDATE = "company:update"
    COMPANY_UPDATE_OWN = "company:update_own"
    COMPANY_DELETE = "company:delete"
    COMPANY_SUSPEND = "company:suspend"
    
    # Subscription permissions
    SUBSCRIPTION_READ = "subscription:read"
    SUBSCRIPTION_READ_OWN = "subscription:read_own"
    SUBSCRIPTION_CREATE = "subscription:create"
    SUBSCRIPTION_UPDATE = "subscription:update"
    SUBSCRIPTION_CANCEL = "subscription:cancel"
    
    # Bid permissions
    BID_CREATE = "bid:create"
    BID_READ = "bid:read"
    BID_READ_OWN = "bid:read_own"
    BID_READ_ON_OWN_CASES = "bid:read_on_own_cases"
    BID_UPDATE = "bid:update"
    BID_ACCEPT = "bid:accept"
    BID_REJECT = "bid:reject"
    
    # Revenue permissions
    REVENUE_READ = "revenue:read"
    REVENUE_READ_OWN = "revenue:read_own"
    
    # Admin permissions
    ADMIN_OVERRIDE = "admin:override"
    ADMIN_AUDIT = "admin:audit"
    USER_MANAGE = "user:manage"
    SETTINGS_MANAGE = "settings:manage"
    
    # Attorney permissions
    ATTORNEY_VERIFY = "attorney:verify"
    ATTORNEY_MANAGE = "attorney:manage"

# Role to permissions mapping
ROLE_PERMISSIONS: Dict[str, List[Permission]] = {
    UserRole.CREDLOCITY_ADMIN: [
        # Full access to everything
        Permission.CASE_CREATE, Permission.CASE_READ, Permission.CASE_UPDATE,
        Permission.CASE_DELETE, Permission.CASE_PUBLISH,
        Permission.DOC_UPLOAD, Permission.DOC_READ, Permission.DOC_READ_FULL, Permission.DOC_DELETE,
        Permission.COMPANY_CREATE, Permission.COMPANY_READ, Permission.COMPANY_UPDATE,
        Permission.COMPANY_DELETE, Permission.COMPANY_SUSPEND,
        Permission.SUBSCRIPTION_READ, Permission.SUBSCRIPTION_CREATE,
        Permission.SUBSCRIPTION_UPDATE, Permission.SUBSCRIPTION_CANCEL,
        Permission.BID_READ, Permission.BID_UPDATE, Permission.BID_ACCEPT, Permission.BID_REJECT,
        Permission.REVENUE_READ,
        Permission.ADMIN_OVERRIDE, Permission.ADMIN_AUDIT, Permission.USER_MANAGE, Permission.SETTINGS_MANAGE,
        Permission.ATTORNEY_VERIFY, Permission.ATTORNEY_MANAGE,
    ],
    UserRole.CREDLOCITY_SUPPORT: [
        # Can view cases, assist companies
        Permission.CASE_READ, Permission.DOC_READ, Permission.DOC_READ_FULL,
        Permission.COMPANY_READ, Permission.SUBSCRIPTION_READ,
        Permission.BID_READ, Permission.REVENUE_READ,
        Permission.ADMIN_AUDIT,
    ],
    UserRole.COMPANY_OWNER: [
        # Full access to own company
        Permission.CASE_CREATE, Permission.CASE_READ_OWN, Permission.CASE_UPDATE_OWN,
        Permission.CASE_PUBLISH,
        Permission.DOC_UPLOAD, Permission.DOC_READ, Permission.DOC_DELETE,
        Permission.COMPANY_READ_OWN, Permission.COMPANY_UPDATE_OWN,
        Permission.SUBSCRIPTION_READ_OWN, Permission.SUBSCRIPTION_CANCEL,
        Permission.BID_READ_ON_OWN_CASES, Permission.BID_ACCEPT, Permission.BID_REJECT,
        Permission.REVENUE_READ_OWN,
        Permission.USER_MANAGE,  # Manage company staff
    ],
    UserRole.COMPANY_STAFF: [
        # Limited access to own company
        Permission.CASE_READ_OWN,
        Permission.DOC_READ,
        Permission.COMPANY_READ_OWN,
        Permission.SUBSCRIPTION_READ_OWN,
        Permission.BID_READ_ON_OWN_CASES,
    ],
    UserRole.ATTORNEY: [
        # Can browse marketplace, bid on cases
        Permission.CASE_READ_PUBLISHED, Permission.CASE_READ_ASSIGNED,
        Permission.DOC_READ_PREVIEW, Permission.DOC_READ_FULL,  # Full only after payment
        Permission.BID_CREATE, Permission.BID_READ_OWN, Permission.BID_UPDATE,
    ],
    UserRole.ATTORNEY_STAFF: [
        # Can view assigned cases
        Permission.CASE_READ_ASSIGNED,
        Permission.DOC_READ_PREVIEW,
    ],
}

# Legacy role mappings
ROLE_PERMISSIONS[UserRole.SUPER_ADMIN] = ROLE_PERMISSIONS[UserRole.CREDLOCITY_ADMIN]
ROLE_PERMISSIONS[UserRole.ADMIN] = ROLE_PERMISSIONS[UserRole.CREDLOCITY_ADMIN]


class UserProfile(BaseModel):
    """Extended user profile with marketplace associations"""
    user_id: str
    role: UserRole
    company_id: Optional[str] = None  # For company users
    attorney_profile_id: Optional[str] = None  # For attorneys
    permissions: List[str] = []  # Additional custom permissions
    is_verified: bool = False
    created_at: str
    updated_at: str


def get_role_level(role: str) -> int:
    """Get the hierarchy level for a role"""
    return ROLE_HIERARCHY.get(role, 0)


def has_permission(user_role: str, permission: Permission) -> bool:
    """Check if a role has a specific permission"""
    role_perms = ROLE_PERMISSIONS.get(user_role, [])
    return permission in role_perms


def has_higher_or_equal_role(user_role: str, required_role: str) -> bool:
    """Check if user role is higher or equal to required role"""
    return get_role_level(user_role) >= get_role_level(required_role)


def is_credlocity_staff(role: str) -> bool:
    """Check if user is Credlocity staff (admin or support)"""
    return role in [
        UserRole.CREDLOCITY_ADMIN,
        UserRole.CREDLOCITY_SUPPORT,
        UserRole.SUPER_ADMIN,
        UserRole.ADMIN
    ]


def is_company_user(role: str) -> bool:
    """Check if user is associated with a credit repair company"""
    return role in [UserRole.COMPANY_OWNER, UserRole.COMPANY_STAFF]


def is_attorney_user(role: str) -> bool:
    """Check if user is an attorney or attorney staff"""
    return role in [UserRole.ATTORNEY, UserRole.ATTORNEY_STAFF]
