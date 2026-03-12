# Security Module for Attorney Marketplace
# Comprehensive security policies and access control

from .roles import (
    UserRole, Permission, ROLE_HIERARCHY, ROLE_PERMISSIONS,
    get_role_level, has_permission, has_higher_or_equal_role,
    is_credlocity_staff, is_company_user, is_attorney_user,
    UserProfile
)

from .access_control import (
    AccessResult,
    CompanyAccessPolicy,
    CaseAccessPolicy,
    DocumentAccessPolicy,
    SubscriptionAccessPolicy,
    BidAccessPolicy,
    RevenueAccessPolicy
)

from .authorization import (
    get_user_context,
    check_case_access,
    check_document_access,
    check_subscription_access,
    verify_attorney_payment,
    grant_document_access,
    verify_attorney_credentials,
    execute_as_admin
)

from .rate_limiter import (
    RateLimitConfig,
    RateLimitResult,
    RateLimiter
)

from .audit_logger import AuditLogger

from .encryption import (
    EncryptionService,
    SENSITIVE_FIELDS,
    encrypt_sensitive_fields,
    decrypt_sensitive_fields
)

__all__ = [
    # Roles
    'UserRole', 'Permission', 'ROLE_HIERARCHY', 'ROLE_PERMISSIONS',
    'get_role_level', 'has_permission', 'has_higher_or_equal_role',
    'is_credlocity_staff', 'is_company_user', 'is_attorney_user',
    'UserProfile',
    # Access Control
    'AccessResult', 'CompanyAccessPolicy', 'CaseAccessPolicy',
    'DocumentAccessPolicy', 'SubscriptionAccessPolicy',
    'BidAccessPolicy', 'RevenueAccessPolicy',
    # Authorization
    'get_user_context', 'check_case_access', 'check_document_access',
    'check_subscription_access', 'verify_attorney_payment',
    'grant_document_access', 'verify_attorney_credentials',
    'execute_as_admin',
    # Rate Limiting
    'RateLimitConfig', 'RateLimitResult', 'RateLimiter',
    # Audit Logging
    'AuditLogger',
    # Encryption
    'EncryptionService', 'SENSITIVE_FIELDS',
    'encrypt_sensitive_fields', 'decrypt_sensitive_fields'
]
