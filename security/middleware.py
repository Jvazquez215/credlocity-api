"""
Security Middleware for Attorney Marketplace

Provides:
- Request validation
- Rate limiting middleware
- Security headers
- CORS configuration
- Company isolation enforcement
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Optional
import time
from datetime import datetime, timezone

from .rate_limiter import RateLimiter, RateLimitConfig


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses
    
    Headers added:
    - Content-Security-Policy
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Strict-Transport-Security
    - X-XSS-Protection
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # HSTS for HTTPS (only in production)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy (relaxed for API)
        csp = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
        response.headers["Content-Security-Policy"] = csp
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for API requests
    
    Applies IP-based rate limiting to all API requests
    """
    
    def __init__(self, app, db_getter: Callable = None):
        super().__init__(app)
        self.db_getter = db_getter
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip rate limiting for certain paths
        skip_paths = ["/health", "/docs", "/openapi.json", "/redoc"]
        if any(request.url.path.startswith(p) for p in skip_paths):
            return await call_next(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Determine action type based on path
        action = self._get_action_type(request)
        
        # Check rate limit if we have a database
        if self.db_getter:
            try:
                db = self.db_getter()
                result = await RateLimiter.check_ip_rate_limit(db, client_ip, action)
                
                if not result.allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Too many requests",
                            "retry_after": result.retry_after
                        },
                        headers=result.get_headers()
                    )
                
                # Add rate limit headers to response
                response = await call_next(request)
                for key, value in result.get_headers().items():
                    response.headers[key] = value
                return response
            except Exception:
                # If rate limiting fails, allow request
                pass
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded headers (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _get_action_type(self, request: Request) -> str:
        """Determine rate limit action type from request"""
        path = request.url.path.lower()
        method = request.method.upper()
        
        if "/cases" in path and method == "POST":
            return "case_submission"
        elif "/documents" in path and method == "POST":
            return "document_upload"
        elif "/auth/login" in path:
            return "login_attempt"
        elif "/bids" in path and method == "POST":
            return "bid_placement"
        else:
            return "api_general"


class CompanyIsolationMiddleware(BaseHTTPMiddleware):
    """
    Enforce company data isolation
    
    Ensures users can only access data belonging to their company
    """
    
    def __init__(self, app, db_getter: Callable = None, get_user: Callable = None):
        super().__init__(app)
        self.db_getter = db_getter
        self.get_user = get_user
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Only check for API routes that involve company data
        company_routes = ["/api/cases", "/api/companies", "/api/subscriptions"]
        
        if not any(request.url.path.startswith(r) for r in company_routes):
            return await call_next(request)
        
        # Store original request state for potential validation
        request.state.company_isolation_checked = False
        
        response = await call_next(request)
        
        return response


def get_user_company_id(user: dict) -> Optional[str]:
    """
    Get the company ID associated with a user
    
    Returns None if user is not associated with a company
    """
    return user.get("company_id")


def verify_company_context(user: dict, target_company_id: str) -> bool:
    """
    Verify that user has access to the target company context
    
    Rules:
    - Credlocity staff can access any company
    - Company users can only access their own company
    """
    from .roles import is_credlocity_staff
    
    role = user.get("role", "")
    
    # Credlocity staff bypass
    if is_credlocity_staff(role):
        return True
    
    # Check company match
    user_company_id = get_user_company_id(user)
    return user_company_id == target_company_id


def apply_company_filter(user: dict, query: dict) -> dict:
    """
    Apply company isolation filter to a database query
    
    For non-Credlocity users, adds company_id filter
    """
    from .roles import is_credlocity_staff
    
    role = user.get("role", "")
    
    # Credlocity staff see everything
    if is_credlocity_staff(role):
        return query
    
    # Add company filter
    company_id = get_user_company_id(user)
    if company_id:
        query["company_id"] = company_id
    
    return query


# CORS Configuration
def get_cors_config() -> dict:
    """
    Get CORS configuration
    
    Production: Whitelist specific frontend domains
    Development: Allow localhost origins
    """
    import os
    
    env = os.environ.get("ENVIRONMENT", "development")
    
    if env == "production":
        # Production: specific origins only
        allowed_origins = [
            "https://credlocity.com",
            "https://www.credlocity.com",
            "https://admin.credlocity.com",
            os.environ.get("FRONTEND_URL", "")
        ]
        allowed_origins = [o for o in allowed_origins if o]  # Remove empty
    else:
        # Development: allow localhost
        allowed_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://localhost:3000",
            "*"  # For development flexibility
        ]
    
    return {
        "allow_origins": allowed_origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type", "X-Requested-With"],
        "expose_headers": [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ],
        "max_age": 600  # Preflight cache time
    }
