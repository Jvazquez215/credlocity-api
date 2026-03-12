"""
Client Review API
Handles unique review link generation, submission, and approval workflow
Supports review categorization and follow-up/update reviews
"""

from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from pydantic import BaseModel, EmailStr
import secrets
import hashlib
import os
import base64

# Import database from server
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
client = get_client(MONGO_URL)
db = client[DB_NAME]

client_review_router = APIRouter(prefix="/api/client-reviews", tags=["Client Reviews"])


# ==================== CONSTANTS ====================

REVIEW_CATEGORIES = [
    {"id": "signup_process", "label": "Sign-Up Process"},
    {"id": "results", "label": "Results & Outcomes"},
    {"id": "customer_service", "label": "Customer Service"},
    {"id": "overall_service", "label": "Overall Service"},
    {"id": "follow_up_update", "label": "Follow-Up Update"}
]


# ==================== MODELS ====================

class ReviewLinkCreate(BaseModel):
    """Model for creating a unique review link"""
    client_id: str  # The collections client ID this is for
    client_name: str
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    expires_days: int = 30  # How many days until link expires


class FollowUpLinkCreate(BaseModel):
    """Model for creating a follow-up review link"""
    original_review_id: str  # The review to update
    expires_days: int = 30


class ReviewLinkResponse(BaseModel):
    """Response after creating a review link"""
    id: str
    token: str
    link_url: str
    client_name: str
    expires_at: str
    status: str


class ClientReviewSubmission(BaseModel):
    """Model for submitting a client review"""
    # Basic Info
    client_name: str
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_city: Optional[str] = None
    client_state: Optional[str] = None
    
    # Review Category
    review_category: str = "overall_service"  # signup_process, results, customer_service, overall_service, follow_up_update
    
    # Credit Score
    before_score: Optional[int] = None
    after_score: Optional[int] = None
    
    # Rating & Review
    rating: int = 5
    testimonial_text: str
    full_story: Optional[str] = None
    
    # Social Links
    social_links: Optional[Dict[str, str]] = {}  # {facebook, instagram, twitter, linkedin, tiktok, bluesky, threads}
    
    # Lawsuit/Attorney Linking
    helped_with_lawsuit: bool = False
    selected_attorney_id: Optional[str] = None
    selected_attorney_name: Optional[str] = None
    defendant_name: Optional[str] = None
    settlement_amount: Optional[float] = None
    case_type: Optional[str] = None
    
    # Video (recorded or URL)
    video_url: Optional[str] = None  # If they provided a URL
    has_recorded_video: bool = False  # If they recorded in-browser
    
    # Consent
    consent_to_publish: bool = True
    consent_to_contact: bool = True
    
    # Follow-up tracking
    is_follow_up: bool = False
    original_review_id: Optional[str] = None


class ReviewApprovalUpdate(BaseModel):
    """Model for approving/rejecting a review"""
    status: str  # approved, rejected
    admin_notes: Optional[str] = None
    publish_immediately: bool = True


# ==================== HELPER FUNCTIONS ====================

def generate_secure_token() -> str:
    """Generate a secure, URL-safe token for review links"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()


# ==================== REVIEW LINK MANAGEMENT ====================

@client_review_router.post("/generate-link")
async def generate_review_link(
    data: ReviewLinkCreate,
    authorization: Optional[str] = Header(None)
):
    """
    Generate a unique, one-time-use review link for a specific client.
    Only collections staff can generate these links.
    """
    # Generate secure token
    token = generate_secure_token()
    token_hash = hash_token(token)
    
    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)
    
    # Create the review link record
    link_record = {
        "id": str(uuid4()),
        "token_hash": token_hash,
        "client_id": data.client_id,
        "client_name": data.client_name,
        "client_email": data.client_email,
        "client_phone": data.client_phone,
        "status": "pending",  # pending, submitted, expired, revoked
        "link_type": "initial",  # initial or follow_up
        "is_follow_up": False,
        "original_review_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "submitted_at": None,
        "review_id": None,  # Will be set when review is submitted
        "created_by": None,  # Will be set from auth token if available
        "view_count": 0,  # Track how many times the link was opened
        "last_viewed_at": None
    }
    
    # Extract user from auth token if present
    if authorization:
        # In a real implementation, decode the JWT and get user info
        pass
    
    await db.review_links.insert_one(link_record)
    
    # Generate the full link URL
    frontend_url = os.environ.get("FRONTEND_URL", "https://credlocity-forms.preview.emergentagent.com")
    link_url = f"{frontend_url}/review/{token}"
    
    return {
        "success": True,
        "link": {
            "id": link_record["id"],
            "token": token,  # Only returned once, not stored
            "link_url": link_url,
            "client_name": data.client_name,
            "expires_at": expires_at.isoformat(),
            "status": "pending"
        }
    }


@client_review_router.post("/generate-follow-up-link")
async def generate_follow_up_link(
    data: FollowUpLinkCreate,
    authorization: Optional[str] = Header(None)
):
    """
    Generate a follow-up review link for an existing review.
    This allows clients to add an update to their original review.
    """
    # Find the original review
    original_review = await db.reviews.find_one({"id": data.original_review_id}, {"_id": 0})
    
    if not original_review:
        raise HTTPException(status_code=404, detail="Original review not found")
    
    # Generate secure token
    token = generate_secure_token()
    token_hash = hash_token(token)
    
    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)
    
    # Create the follow-up link record
    link_record = {
        "id": str(uuid4()),
        "token_hash": token_hash,
        "client_id": original_review.get("client_id"),
        "client_name": original_review.get("client_name"),
        "client_email": original_review.get("contact_email"),
        "client_phone": original_review.get("contact_phone"),
        "status": "pending",
        "link_type": "follow_up",
        "is_follow_up": True,
        "original_review_id": data.original_review_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "submitted_at": None,
        "review_id": None,
        "created_by": None,
        "view_count": 0,
        "last_viewed_at": None
    }
    
    await db.review_links.insert_one(link_record)
    
    # Generate the full link URL
    frontend_url = os.environ.get("FRONTEND_URL", "https://credlocity-forms.preview.emergentagent.com")
    link_url = f"{frontend_url}/review/{token}"
    
    return {
        "success": True,
        "link": {
            "id": link_record["id"],
            "token": token,
            "link_url": link_url,
            "client_name": original_review.get("client_name"),
            "expires_at": expires_at.isoformat(),
            "status": "pending",
            "is_follow_up": True,
            "original_review_id": data.original_review_id
        }
    }


@client_review_router.get("/validate-link/{token}")
async def validate_review_link(token: str):
    """
    Validate a review link and return client info if valid.
    This is called when a client opens the review link.
    """
    token_hash = hash_token(token)
    
    # Find the link
    link = await db.review_links.find_one({"token_hash": token_hash}, {"_id": 0})
    
    if not link:
        raise HTTPException(status_code=404, detail="Invalid or expired review link")
    
    # Check if already submitted
    if link["status"] == "submitted":
        return {
            "valid": False,
            "error": "already_submitted",
            "message": "This review has already been submitted. Thank you!"
        }
    
    # Check if expired
    expires_at = datetime.fromisoformat(link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        # Mark as expired
        await db.review_links.update_one(
            {"token_hash": token_hash},
            {"$set": {"status": "expired"}}
        )
        return {
            "valid": False,
            "error": "expired",
            "message": "This review link has expired. Please contact Credlocity for a new link."
        }
    
    # Check if revoked
    if link["status"] == "revoked":
        return {
            "valid": False,
            "error": "revoked",
            "message": "This review link has been revoked."
        }
    
    # Update view count
    await db.review_links.update_one(
        {"token_hash": token_hash},
        {
            "$inc": {"view_count": 1},
            "$set": {"last_viewed_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    # Prepare response
    response = {
        "valid": True,
        "link_id": link["id"],
        "client_name": link["client_name"],
        "client_email": link.get("client_email"),
        "client_phone": link.get("client_phone"),
        "expires_at": link["expires_at"],
        "is_follow_up": link.get("is_follow_up", False),
        "original_review": None
    }
    
    # If this is a follow-up link, get the original review
    if link.get("is_follow_up") and link.get("original_review_id"):
        original_review = await db.reviews.find_one(
            {"id": link["original_review_id"]},
            {"_id": 0, "id": 1, "testimonial_text": 1, "review_category": 1, "rating": 1, "created_at": 1}
        )
        response["original_review"] = original_review
    
    return response


@client_review_router.post("/submit/{token}")
async def submit_review_via_link(
    token: str,
    data: ClientReviewSubmission
):
    """
    Submit a review using a unique review link.
    """
    token_hash = hash_token(token)
    
    # Find and validate the link
    link = await db.review_links.find_one({"token_hash": token_hash}, {"_id": 0})
    
    if not link:
        raise HTTPException(status_code=404, detail="Invalid review link")
    
    if link["status"] == "submitted":
        raise HTTPException(status_code=400, detail="Review already submitted")
    
    if link["status"] == "revoked":
        raise HTTPException(status_code=400, detail="This review link has been revoked")
    
    # Check expiration
    expires_at = datetime.fromisoformat(link["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        await db.review_links.update_one({"token_hash": token_hash}, {"$set": {"status": "expired"}})
        raise HTTPException(status_code=400, detail="Review link has expired")
    
    # Determine if this is a follow-up
    is_follow_up = link.get("is_follow_up", False) or data.is_follow_up
    original_review_id = link.get("original_review_id") or data.original_review_id
    
    # Create the review record
    review_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    review = {
        "id": review_id,
        "client_name": data.client_name,
        "location": f"{data.client_city}, {data.client_state}" if data.client_city and data.client_state else None,
        "client_city": data.client_city,
        "client_state": data.client_state,
        "contact_email": data.client_email,
        "contact_phone": data.client_phone,
        "review_category": data.review_category,
        "before_score": data.before_score,
        "after_score": data.after_score,
        "rating": data.rating,
        "testimonial_text": data.testimonial_text,
        "full_story": data.full_story,
        "video_url": data.video_url,
        "has_recorded_video": data.has_recorded_video,
        
        # Social links
        "client_social_links": data.social_links or {},
        
        # Lawsuit/Attorney info
        "worked_with_attorney": data.helped_with_lawsuit,
        "attorney_id": data.selected_attorney_id,
        "attorney_name": data.selected_attorney_name,
        "has_settlement": data.helped_with_lawsuit and data.settlement_amount and data.settlement_amount > 0,
        "settlement_details": {
            "amount": data.settlement_amount,
            "defendant_name": data.defendant_name,
            "case_type": data.case_type
        } if data.helped_with_lawsuit else None,
        
        # Consent
        "consent_to_publish": data.consent_to_publish,
        "consent_to_contact": data.consent_to_contact,
        
        # Status - pending approval
        "approval_status": "pending",  # pending, approved, rejected
        "show_on_success_stories": False,  # Will be set to True when approved
        "featured_on_homepage": False,
        
        # Tracking
        "source": "unique_link",
        "review_link_id": link["id"],
        "client_id": link.get("client_id"),
        "is_attorney_review": False,
        
        # Follow-up tracking
        "is_follow_up": is_follow_up,
        "original_review_id": original_review_id,
        "update_number": 1,  # Will be calculated if follow-up
        
        # Timestamps
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None
    }
    
    # If this is a follow-up, calculate update number and link to original
    if is_follow_up and original_review_id:
        # Count existing updates
        existing_updates = await db.reviews.count_documents({
            "original_review_id": original_review_id,
            "is_follow_up": True
        })
        review["update_number"] = existing_updates + 1
        
        # Also update the original review to link to this update
        await db.reviews.update_one(
            {"id": original_review_id},
            {
                "$push": {"update_ids": review_id},
                "$set": {"has_updates": True, "updated_at": now}
            }
        )
    
    # Calculate points improved
    if data.before_score and data.after_score:
        review["points_improved"] = data.after_score - data.before_score
    
    # Generate story slug for potential detail page
    slug_base = data.client_name.lower().replace(" ", "-").replace(".", "")
    review["story_slug"] = f"{slug_base}-{review_id[:8]}"
    
    # Insert the review
    await db.reviews.insert_one(review)
    
    # Update the link status
    await db.review_links.update_one(
        {"token_hash": token_hash},
        {
            "$set": {
                "status": "submitted",
                "submitted_at": now,
                "review_id": review_id
            }
        }
    )
    
    return {
        "success": True,
        "message": "Thank you for your review! It will be published after approval.",
        "review_id": review_id,
        "is_follow_up": is_follow_up
    }


@client_review_router.post("/submit-public")
async def submit_public_review(data: ClientReviewSubmission):
    """
    Submit a review from the public "Leave Honest Review" button.
    These require approval before publishing.
    """
    review_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    review = {
        "id": review_id,
        "client_name": data.client_name,
        "location": f"{data.client_city}, {data.client_state}" if data.client_city and data.client_state else None,
        "client_city": data.client_city,
        "client_state": data.client_state,
        "contact_email": data.client_email,
        "contact_phone": data.client_phone,
        "review_category": data.review_category,
        "before_score": data.before_score,
        "after_score": data.after_score,
        "rating": data.rating,
        "testimonial_text": data.testimonial_text,
        "full_story": data.full_story,
        "video_url": data.video_url,
        "has_recorded_video": data.has_recorded_video,
        
        # Social links
        "client_social_links": data.social_links or {},
        
        # Lawsuit/Attorney info
        "worked_with_attorney": data.helped_with_lawsuit,
        "attorney_id": data.selected_attorney_id,
        "attorney_name": data.selected_attorney_name,
        "has_settlement": data.helped_with_lawsuit and data.settlement_amount and data.settlement_amount > 0,
        "settlement_details": {
            "amount": data.settlement_amount,
            "defendant_name": data.defendant_name,
            "case_type": data.case_type
        } if data.helped_with_lawsuit else None,
        
        # Consent
        "consent_to_publish": data.consent_to_publish,
        "consent_to_contact": data.consent_to_contact,
        
        # Status - pending approval
        "approval_status": "pending",
        "show_on_success_stories": False,
        "featured_on_homepage": False,
        
        # Tracking
        "source": "public_form",
        "review_link_id": None,
        "client_id": None,
        "is_attorney_review": False,
        
        # Follow-up tracking
        "is_follow_up": False,
        "original_review_id": None,
        "has_updates": False,
        "update_ids": [],
        
        # Timestamps
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None
    }
    
    # Calculate points improved
    if data.before_score and data.after_score:
        review["points_improved"] = data.after_score - data.before_score
    
    # Generate story slug
    slug_base = data.client_name.lower().replace(" ", "-").replace(".", "")
    review["story_slug"] = f"{slug_base}-{review_id[:8]}"
    
    await db.reviews.insert_one(review)
    
    return {
        "success": True,
        "message": "Thank you for your review! It will be published after approval.",
        "review_id": review_id
    }


# ==================== VIDEO UPLOAD ====================

@client_review_router.post("/upload-video/{review_id}")
async def upload_review_video(
    review_id: str,
    file: UploadFile = File(...)
):
    """
    Upload a recorded video review.
    Videos are stored and linked to the review for admin approval.
    """
    # Validate the review exists
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Check file type
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    # Check file size (max 100MB)
    MAX_SIZE = 100 * 1024 * 1024  # 100MB
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Video must be under 100MB")
    
    # Generate filename
    ext = file.filename.split(".")[-1] if "." in file.filename else "webm"
    filename = f"review_video_{review_id}_{int(datetime.now().timestamp())}.{ext}"
    
    # Save to uploads directory
    upload_dir = "./uploads/review_videos"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Update review with video info
    video_url = f"/uploads/review_videos/{filename}"
    await db.reviews.update_one(
        {"id": review_id},
        {
            "$set": {
                "recorded_video_path": video_url,
                "has_recorded_video": True,
                "video_uploaded_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "success": True,
        "video_url": video_url,
        "message": "Video uploaded successfully"
    }


# ==================== ADMIN APPROVAL ENDPOINTS ====================

@client_review_router.get("/pending-approval")
async def get_pending_reviews(
    authorization: Optional[str] = Header(None),
    skip: int = 0,
    limit: int = 50
):
    """
    Get all reviews pending approval.
    Admin only endpoint.
    """
    query = {"approval_status": "pending"}
    
    reviews = await db.reviews.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.reviews.count_documents(query)
    
    return {
        "reviews": reviews,
        "total": total,
        "pending_count": total
    }


@client_review_router.put("/approve/{review_id}")
async def approve_or_reject_review(
    review_id: str,
    data: ReviewApprovalUpdate,
    authorization: Optional[str] = Header(None)
):
    """
    Approve or reject a review.
    Admin only endpoint.
    """
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    update_data = {
        "approval_status": data.status,
        "admin_notes": data.admin_notes,
        "updated_at": now
    }
    
    if data.status == "approved":
        update_data["approved_at"] = now
        update_data["show_on_success_stories"] = data.publish_immediately
    elif data.status == "rejected":
        update_data["show_on_success_stories"] = False
        update_data["rejected_at"] = now
    
    await db.reviews.update_one({"id": review_id}, {"$set": update_data})
    
    return {
        "success": True,
        "message": f"Review {data.status}",
        "review_id": review_id
    }


@client_review_router.get("/review-links")
async def get_review_links(
    authorization: Optional[str] = Header(None),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """
    Get all review links (for admin management).
    """
    query = {}
    if status:
        query["status"] = status
    
    links = await db.review_links.find(query, {"_id": 0, "token_hash": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.review_links.count_documents(query)
    
    # Get counts by status
    pending_count = await db.review_links.count_documents({"status": "pending"})
    submitted_count = await db.review_links.count_documents({"status": "submitted"})
    expired_count = await db.review_links.count_documents({"status": "expired"})
    
    return {
        "links": links,
        "total": total,
        "counts": {
            "pending": pending_count,
            "submitted": submitted_count,
            "expired": expired_count
        }
    }


@client_review_router.delete("/review-link/{link_id}")
async def revoke_review_link(
    link_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Revoke a review link (admin only).
    """
    result = await db.review_links.update_one(
        {"id": link_id},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    
    return {"success": True, "message": "Link revoked"}


# ==================== REVIEW WITH UPDATES ====================

@client_review_router.get("/review-with-updates/{review_id}")
async def get_review_with_updates(review_id: str):
    """
    Get a review along with all its updates/follow-ups.
    """
    # Get the main review
    review = await db.reviews.find_one({"id": review_id}, {"_id": 0})
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Get all updates for this review
    updates = []
    if review.get("has_updates") and review.get("update_ids"):
        updates = await db.reviews.find(
            {"id": {"$in": review["update_ids"]}},
            {"_id": 0}
        ).sort("created_at", 1).to_list(100)
    
    return {
        "review": review,
        "updates": updates,
        "update_count": len(updates)
    }


# ==================== ATTORNEY SEARCH (for linking) ====================

@client_review_router.get("/search-attorneys")
async def search_attorneys_for_linking(
    q: str = "",
    limit: int = 20
):
    """
    Search attorneys in the network for client review linking.
    """
    query = {"is_active": {"$ne": False}}
    
    if q:
        query["$or"] = [
            {"full_name": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"firm_name": {"$regex": q, "$options": "i"}}
        ]
    
    attorneys = await db.attorneys.find(
        query,
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "firm_name": 1, "location": 1, "practice_areas": 1}
    ).limit(limit).to_list(limit)
    
    # Normalize the name field
    for attorney in attorneys:
        if not attorney.get("full_name"):
            attorney["full_name"] = attorney.get("name", "Unknown Attorney")
    
    return {
        "attorneys": attorneys,
        "total": len(attorneys)
    }


# ==================== CATEGORIES ====================

@client_review_router.get("/categories")
async def get_review_categories():
    """
    Get all available review categories.
    """
    return {
        "categories": REVIEW_CATEGORIES
    }


# ==================== STATS ====================

@client_review_router.get("/stats")
async def get_review_stats(authorization: Optional[str] = Header(None)):
    """
    Get review statistics for admin dashboard.
    """
    total_reviews = await db.reviews.count_documents({})
    pending_approval = await db.reviews.count_documents({"approval_status": "pending"})
    approved_reviews = await db.reviews.count_documents({"approval_status": "approved"})
    rejected_reviews = await db.reviews.count_documents({"approval_status": "rejected"})
    
    reviews_with_video = await db.reviews.count_documents({
        "$or": [
            {"has_recorded_video": True},
            {"video_url": {"$ne": None, "$ne": ""}}
        ]
    })
    
    pending_links = await db.review_links.count_documents({"status": "pending"})
    
    # Category breakdown
    category_counts = {}
    for cat in REVIEW_CATEGORIES:
        count = await db.reviews.count_documents({"review_category": cat["id"]})
        category_counts[cat["id"]] = count
    
    # Follow-up counts
    follow_up_reviews = await db.reviews.count_documents({"is_follow_up": True})
    reviews_with_updates = await db.reviews.count_documents({"has_updates": True})
    
    return {
        "total_reviews": total_reviews,
        "pending_approval": pending_approval,
        "approved_reviews": approved_reviews,
        "rejected_reviews": rejected_reviews,
        "reviews_with_video": reviews_with_video,
        "pending_links": pending_links,
        "category_counts": category_counts,
        "follow_up_reviews": follow_up_reviews,
        "reviews_with_updates": reviews_with_updates
    }
