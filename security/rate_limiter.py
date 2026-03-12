"""
Rate Limiting for Attorney Marketplace

Implements rate limits:
- Per IP address
- Per user
- Per company

Response when exceeded:
- HTTP 429 Too Many Requests
- Headers: X-RateLimit-Remaining, X-RateLimit-Reset
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncio


class RateLimitConfig:
    """Rate limit configurations"""
    
    # Per IP address limits
    IP_LIMITS = {
        "case_submission": {"requests": 10, "window_hours": 1},
        "document_upload": {"requests": 50, "window_hours": 1},
        "api_general": {"requests": 1000, "window_hours": 1},
        "login_attempt": {"requests": 5, "window_minutes": 15},
    }
    
    # Per user limits
    USER_LIMITS = {
        "bid_placement": {"requests": 20, "window_hours": 24},
        "case_creation": {"requests": 50, "window_hours": 24},
        "document_download": {"requests": 100, "window_hours": 1},
    }
    
    # Per company limits
    COMPANY_LIMITS = {
        "total_api_calls": {"requests": 10000, "window_hours": 24},
        "case_submissions": {"requests": 200, "window_hours": 24},
    }


class RateLimitResult:
    """Result of a rate limit check"""
    
    def __init__(
        self,
        allowed: bool,
        remaining: int,
        reset_time: datetime,
        limit: int,
        retry_after: Optional[int] = None
    ):
        self.allowed = allowed
        self.remaining = remaining
        self.reset_time = reset_time
        self.limit = limit
        self.retry_after = retry_after
    
    def get_headers(self) -> Dict[str, str]:
        """Get rate limit headers for response"""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_time.timestamp())),
        }
        if self.retry_after:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class RateLimiter:
    """Rate limiting implementation using MongoDB"""
    
    @staticmethod
    def _get_window_key(window_hours: int = None, window_minutes: int = None) -> str:
        """Generate a time window key"""
        now = datetime.now(timezone.utc)
        
        if window_hours:
            # Round to hour window
            window_start = now.replace(minute=0, second=0, microsecond=0)
            if window_hours > 1:
                hour = (now.hour // window_hours) * window_hours
                window_start = window_start.replace(hour=hour)
        elif window_minutes:
            # Round to minute window
            minute = (now.minute // window_minutes) * window_minutes
            window_start = now.replace(minute=minute, second=0, microsecond=0)
        else:
            window_start = now.replace(second=0, microsecond=0)
        
        return window_start.isoformat()
    
    @staticmethod
    async def check_rate_limit(
        db: AsyncIOMotorDatabase,
        identifier: str,
        identifier_type: str,  # "ip", "user", "company"
        action: str,
        config: Optional[Dict] = None
    ) -> RateLimitResult:
        """
        Check and update rate limit for an action
        
        Args:
            db: Database connection
            identifier: IP address, user ID, or company ID
            identifier_type: Type of identifier
            action: Action being rate limited
            config: Custom config (overrides default)
        
        Returns:
            RateLimitResult with allowed status and headers
        """
        # Get config
        if config is None:
            if identifier_type == "ip":
                config = RateLimitConfig.IP_LIMITS.get(action, RateLimitConfig.IP_LIMITS["api_general"])
            elif identifier_type == "user":
                config = RateLimitConfig.USER_LIMITS.get(action, {"requests": 100, "window_hours": 1})
            elif identifier_type == "company":
                config = RateLimitConfig.COMPANY_LIMITS.get(action, {"requests": 1000, "window_hours": 24})
            else:
                config = {"requests": 100, "window_hours": 1}
        
        max_requests = config["requests"]
        window_hours = config.get("window_hours")
        window_minutes = config.get("window_minutes")
        
        # Generate window key
        window_key = RateLimiter._get_window_key(window_hours, window_minutes)
        
        # Build document key
        doc_key = f"{identifier_type}:{identifier}:{action}:{window_key}"
        
        # Get or create rate limit record
        record = await db.rate_limits.find_one({"key": doc_key})
        
        now = datetime.now(timezone.utc)
        
        # Calculate reset time
        if window_hours:
            reset_time = now + timedelta(hours=window_hours - (now.hour % window_hours if window_hours > 1 else 0))
            reset_time = reset_time.replace(minute=0, second=0, microsecond=0)
        else:
            reset_time = now + timedelta(minutes=window_minutes - (now.minute % window_minutes))
            reset_time = reset_time.replace(second=0, microsecond=0)
        
        if record:
            current_count = record.get("count", 0)
        else:
            current_count = 0
        
        # Check if limit exceeded
        remaining = max_requests - current_count - 1
        
        if current_count >= max_requests:
            # Rate limited
            retry_after = int((reset_time - now).total_seconds())
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                limit=max_requests,
                retry_after=retry_after
            )
        
        # Increment counter
        await db.rate_limits.update_one(
            {"key": doc_key},
            {
                "$inc": {"count": 1},
                "$set": {
                    "identifier": identifier,
                    "identifier_type": identifier_type,
                    "action": action,
                    "window_key": window_key,
                    "last_request": now.isoformat(),
                    "expires_at": reset_time.isoformat()
                }
            },
            upsert=True
        )
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_time=reset_time,
            limit=max_requests
        )
    
    @staticmethod
    async def check_ip_rate_limit(
        db: AsyncIOMotorDatabase,
        ip_address: str,
        action: str
    ) -> RateLimitResult:
        """Convenience method for IP-based rate limiting"""
        return await RateLimiter.check_rate_limit(db, ip_address, "ip", action)
    
    @staticmethod
    async def check_user_rate_limit(
        db: AsyncIOMotorDatabase,
        user_id: str,
        action: str
    ) -> RateLimitResult:
        """Convenience method for user-based rate limiting"""
        return await RateLimiter.check_rate_limit(db, user_id, "user", action)
    
    @staticmethod
    async def check_company_rate_limit(
        db: AsyncIOMotorDatabase,
        company_id: str,
        action: str
    ) -> RateLimitResult:
        """Convenience method for company-based rate limiting"""
        return await RateLimiter.check_rate_limit(db, company_id, "company", action)
    
    @staticmethod
    async def cleanup_expired_records(db: AsyncIOMotorDatabase):
        """Remove expired rate limit records"""
        now = datetime.now(timezone.utc).isoformat()
        await db.rate_limits.delete_many({"expires_at": {"$lt": now}})
    
    @staticmethod
    async def get_current_usage(
        db: AsyncIOMotorDatabase,
        identifier: str,
        identifier_type: str,
        action: str
    ) -> Dict:
        """Get current rate limit usage for an identifier"""
        # Find all records for this identifier and action
        cursor = db.rate_limits.find({
            "identifier": identifier,
            "identifier_type": identifier_type,
            "action": action
        }, {"_id": 0})
        
        records = await cursor.to_list(100)
        
        total_count = sum(r.get("count", 0) for r in records)
        
        return {
            "identifier": identifier,
            "identifier_type": identifier_type,
            "action": action,
            "current_count": total_count,
            "records": records
        }
