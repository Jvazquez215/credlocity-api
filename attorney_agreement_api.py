"""
Credlocity Attorney Agreement API
Handles attorney onboarding agreement, terms acceptance, and policy acknowledgments
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional, List
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
import os

# Get database connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'credlocity')]

attorney_agreement_router = APIRouter()


# ============= MODELS =============

class AgreementAcceptance(BaseModel):
    terms_of_service: bool
    privacy_policy: bool
    diversity_inclusion_policy: bool
    affiliate_terms: bool
    right_to_update_acknowledgment: bool
    signature_name: str
    signature_date: str
    request_copy_email: Optional[bool] = False


# ============= AGREEMENT ENDPOINTS =============

@attorney_agreement_router.get("/status")
async def get_agreement_status(token: str):
    """Check if attorney has signed the onboarding agreement"""
    attorney = await db.attorneys.find_one({"token": token}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    return {
        "requires_agreement": attorney.get("requires_agreement", True),
        "agreement_signed": attorney.get("agreement_signed", False),
        "agreement_signed_at": attorney.get("agreement_signed_at"),
        "attorney_name": attorney.get("full_name"),
        "attorney_email": attorney.get("email")
    }


@attorney_agreement_router.get("/documents")
async def get_agreement_documents():
    """Get URLs to all agreement documents"""
    return {
        "terms_of_service": {
            "title": "Terms of Service",
            "url": "/terms-of-service",
            "description": "Our general terms and conditions governing use of Credlocity services"
        },
        "privacy_policy": {
            "title": "Privacy Policy",
            "url": "/privacy-policy",
            "description": "How we collect, use, and protect your personal information"
        },
        "diversity_inclusion_policy": {
            "title": "Diversity and Inclusion Policy",
            "url": "/diversity-inclusion-policy",
            "description": "Our commitment to diversity, equity, and inclusion in all business practices"
        },
        "affiliate_terms": {
            "title": "Affiliate Terms and Services",
            "url": "/affiliate-terms",
            "description": "Terms specific to our affiliate and attorney referral network program"
        },
        "attorney_network_agreement": {
            "title": "Attorney Network Participation Agreement",
            "url": "/attorney-network-agreement",
            "description": "Specific terms for participation in the attorney referral marketplace"
        }
    }


@attorney_agreement_router.post("/accept")
async def accept_agreement(acceptance: AgreementAcceptance, token: str):
    """Attorney accepts the onboarding agreement"""
    attorney = await db.attorneys.find_one({"token": token}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    # Validate all required acceptances
    required_fields = [
        ("terms_of_service", "Terms of Service"),
        ("privacy_policy", "Privacy Policy"),
        ("diversity_inclusion_policy", "Diversity and Inclusion Policy"),
        ("affiliate_terms", "Affiliate Terms and Services"),
        ("right_to_update_acknowledgment", "Right to Update Acknowledgment")
    ]
    
    for field, label in required_fields:
        if not getattr(acceptance, field):
            raise HTTPException(status_code=400, detail=f"You must accept the {label}")
    
    if not acceptance.signature_name.strip():
        raise HTTPException(status_code=400, detail="Signature name is required")
    
    # Create agreement record
    agreement_record = {
        "id": str(uuid4()),
        "attorney_id": attorney["id"],
        "attorney_name": attorney.get("full_name"),
        "attorney_email": attorney.get("email"),
        "terms_of_service_accepted": acceptance.terms_of_service,
        "privacy_policy_accepted": acceptance.privacy_policy,
        "diversity_inclusion_policy_accepted": acceptance.diversity_inclusion_policy,
        "affiliate_terms_accepted": acceptance.affiliate_terms,
        "right_to_update_acknowledged": acceptance.right_to_update_acknowledgment,
        "signature_name": acceptance.signature_name,
        "signature_date": acceptance.signature_date,
        "ip_address": None,  # Would capture from request in production
        "user_agent": None,
        "request_copy_email": acceptance.request_copy_email,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.attorney_agreement_records.insert_one(agreement_record)
    
    # Update attorney record
    await db.attorneys.update_one(
        {"id": attorney["id"]},
        {
            "$set": {
                "requires_agreement": False,
                "agreement_signed": True,
                "agreement_signed_at": datetime.now(timezone.utc).isoformat(),
                "agreement_record_id": agreement_record["id"],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # If requested, send copies (in production, this would trigger an email)
    if acceptance.request_copy_email:
        # Log the request for email sending
        await db.email_queue.insert_one({
            "id": str(uuid4()),
            "to": attorney.get("email"),
            "subject": "Credlocity Attorney Network Agreement - Your Copy",
            "template": "attorney_agreement_copy",
            "data": {
                "attorney_name": attorney.get("full_name"),
                "agreement_record": agreement_record
            },
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    return {
        "message": "Agreement accepted successfully",
        "agreement_id": agreement_record["id"],
        "signed_at": agreement_record["created_at"],
        "copy_requested": acceptance.request_copy_email
    }


@attorney_agreement_router.get("/record")
async def get_agreement_record(token: str):
    """Get attorney's agreement record"""
    attorney = await db.attorneys.find_one({"token": token}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    if not attorney.get("agreement_signed"):
        raise HTTPException(status_code=404, detail="No agreement record found")
    
    record = await db.attorney_agreement_records.find_one(
        {"attorney_id": attorney["id"]},
        {"_id": 0}
    )
    
    return record


@attorney_agreement_router.post("/request-copies")
async def request_agreement_copies(token: str):
    """Attorney requests copies of all agreement documents sent to their email"""
    attorney = await db.attorneys.find_one({"token": token}, {"_id": 0})
    if not attorney:
        raise HTTPException(status_code=401, detail="Invalid attorney session")
    
    # Queue email with all documents
    await db.email_queue.insert_one({
        "id": str(uuid4()),
        "to": attorney.get("email"),
        "subject": "Credlocity Agreement Documents - Your Copies",
        "template": "attorney_agreement_documents",
        "data": {
            "attorney_name": attorney.get("full_name"),
            "documents": [
                "Terms of Service",
                "Privacy Policy",
                "Diversity and Inclusion Policy",
                "Affiliate Terms and Services",
                "Attorney Network Participation Agreement"
            ]
        },
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "message": "Document copies have been requested and will be sent to your email",
        "email": attorney.get("email")
    }


# ============= AGREEMENT TEXT =============

ATTORNEY_NETWORK_AGREEMENT_TEXT = """
CREDLOCITY ATTORNEY NETWORK PARTICIPATION AGREEMENT

This Attorney Network Participation Agreement ("Agreement") is entered into between Credlocity Business Group LLC ("Credlocity," "we," "us," or "our") and you, the participating attorney ("Attorney," "you," or "your").

1. ACCEPTANCE OF TERMS
By clicking "Accept" or participating in the Credlocity Attorney Network, you agree to be bound by:
- These Attorney Network Terms
- Our Terms of Service (available at credlocity.com/terms-of-service)
- Our Privacy Policy (available at credlocity.com/privacy-policy)
- Our Diversity and Inclusion Policy (available at credlocity.com/diversity-inclusion-policy)
- Our Affiliate Terms and Services (available at credlocity.com/affiliate-terms)

2. CASE REFERRAL FEE STRUCTURE
a) Non-Negotiable Referral Fee: A flat $500 referral fee is due to Credlocity upon successful settlement or judgment of any referred case. This fee is non-negotiable.
b) Commission Structure: In addition to the referral fee, Credlocity is entitled to a percentage commission based on the settlement amount as outlined in our fee schedule.
c) Payment Terms: All fees are due within 30 days of settlement receipt or judgment collection.

3. CASE UPDATE REQUIREMENTS
a) 30-Day Updates: You must provide a status update on each assigned case every 30 days.
b) Update Options: Updates must indicate the current case status (e.g., Under Review, In Negotiations, Litigation Filed, Settlement Pending, etc.).
c) Penalty for Non-Compliance: Failure to provide required updates within 3 days after the 30-day deadline may result in:
   - Temporary suspension of marketplace access
   - Hold on account balance/reserve
   - Access will be restored upon providing the required updates

4. CLIENT PROTECTION
a) You agree to represent referred clients with the same standard of care as your other clients.
b) You will keep clients reasonably informed about case progress.
c) You will not charge clients any fees beyond your standard attorney-client fee agreement.

5. CONFIDENTIALITY
All client information and case details are confidential. You may not disclose such information except as required to represent the client or as required by law.

6. PROFESSIONAL STANDARDS
a) You must maintain an active bar license in good standing.
b) You must maintain professional liability insurance.
c) You must comply with all applicable rules of professional conduct.

7. RIGHT TO UPDATE TERMS
Credlocity reserves the right to modify these terms at any time. We will provide notice of material changes via email or through our platform. Continued participation after such notice constitutes acceptance of updated terms.

8. TERM AND TERMINATION
This Agreement is effective upon acceptance and continues until terminated by either party with 30 days written notice. Termination does not affect obligations regarding pending cases or fees owed.

9. GOVERNING LAW
This Agreement is governed by the laws of the Commonwealth of Pennsylvania.

10. DISPUTE RESOLUTION
Any disputes arising from this Agreement shall be resolved through binding arbitration in Philadelphia, Pennsylvania, in accordance with the rules of the American Arbitration Association.

By accepting this Agreement, you acknowledge that you have read, understood, and agree to be bound by all terms herein and all referenced policies.
"""


@attorney_agreement_router.get("/full-text")
async def get_full_agreement_text():
    """Get the full agreement text for display"""
    return {
        "agreement_text": ATTORNEY_NETWORK_AGREEMENT_TEXT,
        "version": "1.0",
        "effective_date": "2024-01-01",
        "last_updated": "2024-12-01"
    }
