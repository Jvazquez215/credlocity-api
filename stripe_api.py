"""
Stripe Subscription API for Credlocity
Handles company subscriptions, signup fees, and payment processing
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

# Stripe integration (native)
import stripe

class StripeCheckout:
    def __init__(self, api_key):
        stripe.api_key = api_key
    
    async def create_session(self, **kwargs):
        return stripe.checkout.Session.create(**kwargs)
    
    async def get_session(self, session_id):
        return stripe.checkout.Session.retrieve(session_id)

class CheckoutSessionRequest:
    pass

class CheckoutSessionResponse:
    pass

class CheckoutStatusResponse:
    pass

# Database connection
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "credlocity")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

stripe_router = APIRouter(prefix="/api/stripe", tags=["Stripe Payments"])

# ==============================================================================
# FIXED PACKAGES - Never accept amounts from frontend
# ==============================================================================

SUBSCRIPTION_PACKAGES = {
    "company_signup": {
        "name": "Company Signup Fee",
        "amount": 500.00,
        "type": "one_time",
        "description": "One-time signup fee for credit repair companies"
    },
    "company_monthly": {
        "name": "Monthly Subscription",
        "amount": 199.99,
        "type": "recurring",
        "description": "Monthly subscription for credit repair companies"
    },
    "attorney_registration": {
        "name": "Attorney Registration",
        "amount": 0.00,  # Free
        "type": "one_time",
        "description": "Attorney registration (free)"
    }
}


# ==============================================================================
# PYDANTIC MODELS
# ==============================================================================

class CreateCheckoutRequest(BaseModel):
    """Request to create a checkout session"""
    package_id: str = Field(..., description="Package ID from SUBSCRIPTION_PACKAGES")
    company_id: Optional[str] = Field(None, description="Company ID for subscription")
    origin_url: str = Field(..., description="Frontend origin URL")
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict)


class CheckoutStatusRequest(BaseModel):
    """Request to check checkout status"""
    session_id: str


# ==============================================================================
# STRIPE CHECKOUT ENDPOINTS
# ==============================================================================

@stripe_router.post("/checkout/session")
async def create_checkout_session(request: Request, data: CreateCheckoutRequest):
    """
    Create a Stripe checkout session for subscription payment
    
    Security: Amount is determined by package_id, never from frontend
    """
    try:
        # Validate package
        package_id = data.package_id
        if package_id not in SUBSCRIPTION_PACKAGES:
            raise HTTPException(status_code=400, detail=f"Invalid package: {package_id}")
        
        package = SUBSCRIPTION_PACKAGES[package_id]
        amount = package["amount"]
        
        if amount <= 0:
            raise HTTPException(status_code=400, detail="This package is free, no payment required")
        
        # Build success/cancel URLs from frontend origin
        origin_url = data.origin_url.rstrip('/')
        success_url = f"{origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin_url}/payment/cancel"
        
        # Initialize Stripe
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/stripe/webhook"
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
        
        # Prepare metadata
        metadata = {
            "package_id": package_id,
            "package_name": package["name"],
            "company_id": data.company_id or "",
            "payment_type": package["type"],
            **data.metadata
        }
        
        # Create checkout session
        checkout_request = CheckoutSessionRequest(
            amount=float(amount),
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata
        )
        
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
        
        # Create payment transaction record BEFORE redirect
        transaction = {
            "id": str(uuid4()),
            "session_id": session.session_id,
            "company_id": data.company_id,
            "package_id": package_id,
            "package_name": package["name"],
            "amount": amount,
            "currency": "usd",
            "payment_type": package["type"],
            "payment_status": "initiated",
            "status": "pending",
            "metadata": metadata,
            "checkout_url": session.url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.payment_transactions.insert_one(transaction)
        
        return {
            "success": True,
            "url": session.url,
            "session_id": session.session_id,
            "amount": amount,
            "package": package["name"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[STRIPE CHECKOUT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@stripe_router.get("/checkout/status/{session_id}")
async def get_checkout_status(request: Request, session_id: str):
    """
    Check the status of a checkout session and update database
    """
    try:
        # Check if already processed
        transaction = await db.payment_transactions.find_one(
            {"session_id": session_id},
            {"_id": 0}
        )
        
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        # If already paid, don't process again
        if transaction.get("payment_status") == "paid":
            return {
                "status": "complete",
                "payment_status": "paid",
                "amount_total": transaction.get("amount", 0) * 100,
                "currency": "usd",
                "already_processed": True
            }
        
        # Initialize Stripe and check status
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/stripe/webhook"
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
        
        status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        
        # Update transaction based on status
        update_data = {
            "payment_status": status.payment_status,
            "status": status.status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # If payment is successful, process the subscription
        if status.payment_status == "paid" and transaction.get("payment_status") != "paid":
            update_data["paid_at"] = datetime.now(timezone.utc).isoformat()
            
            # Update company subscription status if applicable
            company_id = transaction.get("company_id")
            package_id = transaction.get("package_id")
            
            if company_id and package_id == "company_signup":
                # Update company signup fee status
                await db.credit_repair_companies.update_one(
                    {"id": company_id},
                    {
                        "$set": {
                            "signup_fee_paid": True,
                            "signup_fee_paid_at": datetime.now(timezone.utc).isoformat(),
                            "status": "active",
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
                
                # Create subscription record
                now = datetime.now(timezone.utc)
                subscription = {
                    "id": str(uuid4()),
                    "company_id": company_id,
                    "plan_type": "standard",
                    "status": "active",
                    "signup_fee": 500.00,
                    "monthly_fee": 199.99,
                    "signup_fee_paid": True,
                    "signup_fee_paid_at": now.isoformat(),
                    "current_period_start": now.isoformat(),
                    "current_period_end": (now + timedelta(days=30)).isoformat(),
                    "next_billing_date": (now + timedelta(days=30)).isoformat(),
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat()
                }
                
                await db.company_subscriptions.insert_one(subscription)
        
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": update_data}
        )
        
        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency,
            "metadata": status.metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[STRIPE STATUS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@stripe_router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events
    """
    try:
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/stripe/webhook"
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
        
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        # Process webhook event
        event_type = webhook_response.event_type
        session_id = webhook_response.session_id
        payment_status = webhook_response.payment_status
        
        print(f"[STRIPE WEBHOOK] Event: {event_type}, Session: {session_id}, Status: {payment_status}")
        
        # Update transaction
        if session_id:
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "payment_status": payment_status,
                        "webhook_event": event_type,
                        "webhook_received_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
        
        return {"received": True}
        
    except Exception as e:
        print(f"[STRIPE WEBHOOK ERROR] {e}")
        return {"received": True, "error": str(e)}


# ==============================================================================
# SUBSCRIPTION MANAGEMENT ENDPOINTS
# ==============================================================================

@stripe_router.get("/packages")
async def get_subscription_packages():
    """Get all available subscription packages"""
    return {
        "packages": [
            {
                "id": key,
                **value
            }
            for key, value in SUBSCRIPTION_PACKAGES.items()
        ]
    }


@stripe_router.get("/company/{company_id}/subscription")
async def get_company_subscription(company_id: str):
    """Get subscription details for a company"""
    subscription = await db.company_subscriptions.find_one(
        {"company_id": company_id},
        {"_id": 0}
    )
    
    if not subscription:
        return {"subscription": None, "active": False}
    
    return {
        "subscription": subscription,
        "active": subscription.get("status") == "active"
    }


@stripe_router.get("/company/{company_id}/transactions")
async def get_company_transactions(company_id: str, limit: int = 20):
    """Get payment transactions for a company"""
    transactions = await db.payment_transactions.find(
        {"company_id": company_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"transactions": transactions}


@stripe_router.post("/company/{company_id}/cancel-subscription")
async def cancel_company_subscription(
    company_id: str,
    authorization: str = Header(None)
):
    """Cancel a company's subscription"""
    # Verify authorization (company owner or admin)
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        subscription = await db.company_subscriptions.find_one({"company_id": company_id})
        
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        # Update subscription status
        await db.company_subscriptions.update_one(
            {"company_id": company_id},
            {
                "$set": {
                    "status": "cancelled",
                    "cancellation_date": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Update company status
        await db.credit_repair_companies.update_one(
            {"id": company_id},
            {
                "$set": {
                    "subscription_status": "cancelled",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        return {"success": True, "message": "Subscription cancelled"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CANCEL SUBSCRIPTION ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))
