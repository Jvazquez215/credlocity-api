"""
Credlocity Credit Repair Reviews & Complaint System API
Handles complaints about credit repair companies, company database, and reviews display
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional, List
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
import os
import re

# Get database connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = get_client(mongo_url)
db = client[os.environ.get('DB_NAME', 'credlocity')]

credit_repair_router = APIRouter()


# ============= MODELS =============

class CreditRepairCompany(BaseModel):
    id: str
    name: str
    slug: str
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    social_facebook: Optional[str] = None
    social_twitter: Optional[str] = None
    social_instagram: Optional[str] = None
    social_linkedin: Optional[str] = None
    social_youtube: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_verified: bool = False
    has_comparison_page: bool = False
    comparison_page_slug: Optional[str] = None
    complaint_count: int = 0
    avg_rating: float = 0
    created_at: str
    updated_at: str


class ComplaintSubmission(BaseModel):
    # Company info
    company_id: Optional[str] = None
    company_name: str
    is_new_company: bool = False
    new_company_website: Optional[str] = None
    new_company_socials: Optional[dict] = None
    
    # Complainant info
    complainant_name: str
    complainant_email: str
    complainant_phone: Optional[str] = None
    complainant_city: Optional[str] = None
    complainant_state: str
    
    # Complainant social media (for verification - optional)
    social_twitter: Optional[str] = None
    social_facebook: Optional[str] = None
    social_instagram: Optional[str] = None
    social_linkedin: Optional[str] = None
    social_threads: Optional[str] = None
    social_tiktok: Optional[str] = None
    social_bluesky: Optional[str] = None
    
    # Complaint details
    date_of_service: Optional[str] = None
    complaint_types: List[str] = []
    complaint_details: str
    person_spoke_to: Optional[str] = None
    amount_paid: Optional[float] = None
    resolution_sought: Optional[str] = None
    fair_resolution: Optional[str] = None  # What they consider fair resolution
    
    # Rating (1-5 stars)
    star_rating: Optional[int] = 1
    
    # Video review
    video_review_url: Optional[str] = None
    video_review_platform: Optional[str] = None  # youtube, vimeo, tiktok, etc.
    
    # Evidence
    screenshots: List[str] = []
    documents: List[str] = []
    audio_recordings: List[str] = []


class ComplaintSEO(BaseModel):
    """SEO fields for individual complaint/review pages"""
    url_slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    schema_type: str = "Review"
    canonical_url: Optional[str] = None
    keywords: List[str] = []


# ============= COMPANY ENDPOINTS =============

@credit_repair_router.get("/companies")
async def list_credit_repair_companies(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """List all credit repair companies"""
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"website": {"$regex": search, "$options": "i"}}
        ]
    
    companies = await db.credit_repair_companies.find(
        query,
        {"_id": 0}
    ).sort("name", 1).skip(skip).limit(limit).to_list(None)
    
    total = await db.credit_repair_companies.count_documents(query)
    
    return {"companies": companies, "total": total}


@credit_repair_router.get("/companies/admin/stats")
async def get_companies_stats():
    """Get company statistics for admin dashboard"""
    total = await db.credit_repair_companies.count_documents({})
    
    # Top companies by complaints
    pipeline = [
        {"$group": {"_id": "$company_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    top_by_complaints = await db.complaints.aggregate(pipeline).to_list(length=10)
    
    # Enrich with company names
    top_companies = []
    for t in top_by_complaints:
        company = await db.credit_repair_companies.find_one({"id": t["_id"]}, {"_id": 0, "name": 1})
        top_companies.append({
            "company_id": t["_id"],
            "name": company["name"] if company else "Unknown",
            "complaint_count": t["count"]
        })
    
    return {
        "total_companies": total,
        "top_companies_by_cases": top_companies
    }



@credit_repair_router.get("/companies/{company_id}")
async def get_credit_repair_company(company_id: str):
    """Get a single credit repair company with complaints"""
    company = await db.credit_repair_companies.find_one(
        {"$or": [{"id": company_id}, {"slug": company_id}]},
        {"_id": 0}
    )
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get published complaints for this company
    complaints = await db.complaints.find(
        {"company_id": company["id"], "status": "published"},
        {"_id": 0, "complainant_email": 0, "complainant_phone": 0}
    ).sort("created_at", -1).limit(20).to_list(None)
    
    return {"company": company, "complaints": complaints}


@credit_repair_router.post("/companies")
async def create_credit_repair_company(data: dict):
    """Create a new credit repair company"""
    # Generate slug from name
    slug = re.sub(r'[^a-z0-9]+', '-', data["name"].lower()).strip('-')
    
    # Check for existing
    existing = await db.credit_repair_companies.find_one({
        "$or": [
            {"slug": slug},
            {"name": {"$regex": f"^{data['name']}$", "$options": "i"}}
        ]
    })
    
    if existing:
        return {"exists": True, "company": existing}
    
    company = {
        "id": str(uuid4()),
        "name": data["name"],
        "slug": slug,
        "website": data.get("website"),
        "phone": data.get("phone"),
        "email": data.get("email"),
        "address": data.get("address"),
        "social_facebook": data.get("social_facebook"),
        "social_twitter": data.get("social_twitter"),
        "social_instagram": data.get("social_instagram"),
        "social_linkedin": data.get("social_linkedin"),
        "social_youtube": data.get("social_youtube"),
        "logo_url": data.get("logo_url"),
        "description": data.get("description"),
        "is_verified": False,
        "has_comparison_page": False,
        "comparison_page_slug": None,
        "complaint_count": 0,
        "avg_rating": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.credit_repair_companies.insert_one(company)
    
    return {"company": company, "exists": False}


# ============= COMPLAINT ENDPOINTS =============

@credit_repair_router.post("/complaints/submit")
async def submit_complaint(data: ComplaintSubmission):
    """Submit a new complaint about a credit repair company"""
    
    company_id = data.company_id
    company_name = data.company_name
    
    # Handle new company creation
    if data.is_new_company and not company_id:
        new_company = await create_credit_repair_company({
            "name": data.company_name,
            "website": data.new_company_website,
            "social_facebook": data.new_company_socials.get("facebook") if data.new_company_socials else None,
            "social_twitter": data.new_company_socials.get("twitter") if data.new_company_socials else None,
            "social_instagram": data.new_company_socials.get("instagram") if data.new_company_socials else None
        })
        company_id = new_company["company"]["id"]
        company_name = new_company["company"]["name"]
    
    # Generate URL slug for the review page
    first_name = data.complainant_name.split()[0] if data.complainant_name else "anonymous"
    url_slug = f"{re.sub(r'[^a-z0-9]+', '-', company_name.lower()).strip('-')}-review-{re.sub(r'[^a-z0-9]+', '-', first_name.lower())}-{str(uuid4())[:8]}"
    
    # Parse complainant name for display (First Name, Last Initial)
    name_parts = data.complainant_name.strip().split() if data.complainant_name else ["Anonymous"]
    display_first_name = name_parts[0]
    display_last_initial = name_parts[-1][0].upper() + "." if len(name_parts) > 1 else ""
    display_name = f"{display_first_name} {display_last_initial}".strip()
    
    # Create complaint record
    complaint = {
        "id": str(uuid4()),
        "company_id": company_id,
        "company_name": company_name,
        "complainant_name": data.complainant_name,
        "complainant_email": data.complainant_email,
        "complainant_phone": data.complainant_phone,
        "complainant_city": data.complainant_city,
        "complainant_state": data.complainant_state,
        "display_name": display_name,  # "John D." format
        
        # Social media links (for verification)
        "social_twitter": data.social_twitter,
        "social_facebook": data.social_facebook,
        "social_instagram": data.social_instagram,
        "social_linkedin": data.social_linkedin,
        "social_threads": data.social_threads,
        "social_tiktok": data.social_tiktok,
        "social_bluesky": data.social_bluesky,
        
        # Complaint details
        "date_of_service": data.date_of_service,
        "complaint_types": data.complaint_types,
        "complaint_details": data.complaint_details,
        "person_spoke_to": data.person_spoke_to,
        "amount_paid": data.amount_paid,
        "resolution_sought": data.resolution_sought,
        "fair_resolution": data.fair_resolution,
        
        # Rating
        "star_rating": data.star_rating or 1,
        
        # Video review
        "video_review_url": data.video_review_url,
        "video_review_platform": data.video_review_platform,
        
        # Evidence
        "screenshots": data.screenshots,
        "documents": data.documents,
        "audio_recordings": data.audio_recordings,
        
        # Status and admin fields
        "status": "pending_review",
        "admin_findings": None,
        "company_response": None,
        "company_contacted": False,
        "company_contacted_date": None,
        "published_at": None,
        "display_complainant_name": True,
        
        # SEO fields (admin can edit)
        "seo": {
            "url_slug": url_slug,
            "meta_title": f"{company_name} Review by {display_name} | Credlocity",
            "meta_description": f"Read {display_name}'s honest review and complaint about {company_name}. {data.complaint_details[:150]}...",
            "og_title": f"{company_name} Review - Consumer Complaint",
            "og_description": f"Real consumer experience with {company_name}",
            "keywords": [company_name.lower(), "credit repair review", "credit repair complaint", data.complainant_state],
            "schema_type": "Review"
        },
        
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.complaints.insert_one(complaint)
    
    # Update company complaint count
    if company_id:
        await db.credit_repair_companies.update_one(
            {"id": company_id},
            {
                "$inc": {"complaint_count": 1},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
    
    return {
        "message": "Your complaint has been submitted successfully. We will review it and may contact you for additional information.",
        "complaint_id": complaint["id"]
    }


@credit_repair_router.get("/complaints/public")
async def get_public_complaints(
    company_id: Optional[str] = None,
    company_slug: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
):
    """Get published complaints for public display"""
    query = {"status": "published"}
    
    if company_id:
        query["company_id"] = company_id
    elif company_slug:
        company = await db.credit_repair_companies.find_one({"slug": company_slug})
        if company:
            query["company_id"] = company["id"]
    
    complaints = await db.complaints.find(
        query,
        {
            "_id": 0,
            "complainant_email": 0,
            "complainant_phone": 0,
            "documents": 0,
            "audio_recordings": 0
        }
    ).sort("published_at", -1).skip(skip).limit(limit).to_list(None)
    
    total = await db.complaints.count_documents(query)
    
    return {"complaints": complaints, "total": total}


@credit_repair_router.get("/reviews/{review_slug}")
async def get_review_by_slug(review_slug: str):
    """Get a single published review/complaint by its URL slug for SEO-optimized individual page"""
    complaint = await db.complaints.find_one(
        {"seo.url_slug": review_slug, "status": "published"},
        {
            "_id": 0,
            "complainant_email": 0,
            "complainant_phone": 0,
            "documents": 0,
            "audio_recordings": 0
        }
    )
    
    if not complaint:
        # Also try by ID
        complaint = await db.complaints.find_one(
            {"id": review_slug, "status": "published"},
            {
                "_id": 0,
                "complainant_email": 0,
                "complainant_phone": 0,
                "documents": 0,
                "audio_recordings": 0
            }
        )
    
    if not complaint:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Get company info
    company = await db.credit_repair_companies.find_one(
        {"id": complaint.get("company_id")},
        {"_id": 0}
    )
    
    # Get related reviews from same company (max 5)
    related_reviews = await db.complaints.find(
        {
            "company_id": complaint.get("company_id"),
            "status": "published",
            "id": {"$ne": complaint["id"]}
        },
        {
            "_id": 0,
            "id": 1,
            "display_name": 1,
            "complainant_state": 1,
            "complainant_city": 1,
            "star_rating": 1,
            "complaint_details": 1,
            "seo.url_slug": 1,
            "published_at": 1
        }
    ).sort("published_at", -1).limit(5).to_list(None)
    
    return {
        "review": complaint,
        "company": company,
        "related_reviews": related_reviews,
        "credlocity_benefits": {
            "free_trial": "30-day free trial",
            "money_back_guarantee": "100% 180-day money back guarantee",
            "investigative_journalism": "Investigative journalism exposing fraud credit repair",
            "attorney_network": "Exclusive attorney network for legal support",
            "affiliate_network": "Trusted network of realtors, mortgage companies, and influencers"
        }
    }


@credit_repair_router.get("/reviews-page-data")
async def get_reviews_page_data():
    """Get all data needed for the reviews listing page, grouped by company"""
    # Get all companies with at least one published complaint
    companies = await db.credit_repair_companies.find(
        {},
        {"_id": 0}
    ).sort("complaint_count", -1).to_list(None)
    
    # Get published complaints grouped by company
    complaints_by_company = {}
    all_complaints = await db.complaints.find(
        {"status": "published"},
        {
            "_id": 0,
            "complainant_email": 0,
            "complainant_phone": 0,
            "documents": 0,
            "audio_recordings": 0
        }
    ).sort("published_at", -1).to_list(None)
    
    for complaint in all_complaints:
        company_id = complaint.get("company_id", "other")
        if company_id not in complaints_by_company:
            complaints_by_company[company_id] = []
        complaints_by_company[company_id].append(complaint)
    
    # Recent complaints (last 10)
    recent_complaints = all_complaints[:10] if all_complaints else []
    
    # Calculate stats
    total_complaints = len(all_complaints)
    total_companies = len([c for c in companies if c.get("complaint_count", 0) > 0])
    
    return {
        "companies": companies,
        "complaints_by_company": complaints_by_company,
        "recent_complaints": recent_complaints,
        "stats": {
            "total_complaints": total_complaints,
            "total_companies": len(companies),
            "companies_with_complaints": total_companies
        }
    }


# ============= ADMIN COMPLAINT MANAGEMENT =============

@credit_repair_router.get("/admin/complaints")
async def admin_list_complaints(
    status: Optional[str] = None,
    company_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Admin: List all complaints"""
    query = {}
    if status:
        query["status"] = status
    if company_id:
        query["company_id"] = company_id
    
    complaints = await db.complaints.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    
    total = await db.complaints.count_documents(query)
    
    # Get stats
    pending = await db.complaints.count_documents({"status": "pending_review"})
    investigating = await db.complaints.count_documents({"status": "under_investigation"})
    published = await db.complaints.count_documents({"status": "published"})
    
    return {
        "complaints": complaints,
        "total": total,
        "stats": {
            "pending": pending,
            "investigating": investigating,
            "published": published
        }
    }


@credit_repair_router.put("/admin/complaints/{complaint_id}")
async def admin_update_complaint(complaint_id: str, data: dict):
    """Admin: Update complaint with findings, status, SEO, etc."""
    update_data = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Update allowed fields
    allowed_fields = [
        "status", "admin_findings", "company_response", 
        "company_contacted", "company_contacted_date",
        "display_complainant_name"
    ]
    
    for field in allowed_fields:
        if field in data:
            update_data[field] = data[field]
    
    # Update SEO fields if provided
    if "seo" in data:
        seo_fields = ["url_slug", "meta_title", "meta_description", "og_title", "og_description", "keywords", "schema_type"]
        for seo_field in seo_fields:
            if seo_field in data["seo"]:
                update_data[f"seo.{seo_field}"] = data["seo"][seo_field]
    
    # If publishing, set published_at
    if data.get("status") == "published":
        update_data["published_at"] = datetime.now(timezone.utc).isoformat()
        
        # Update company's average rating
        complaint = await db.complaints.find_one({"id": complaint_id})
        if complaint and complaint.get("company_id"):
            all_ratings = await db.complaints.find(
                {"company_id": complaint["company_id"], "status": "published", "star_rating": {"$exists": True}},
                {"star_rating": 1}
            ).to_list(None)
            if all_ratings:
                avg_rating = sum(r.get("star_rating", 1) for r in all_ratings) / len(all_ratings)
                await db.credit_repair_companies.update_one(
                    {"id": complaint["company_id"]},
                    {"$set": {"avg_rating": round(avg_rating, 1)}}
                )
    
    result = await db.complaints.update_one(
        {"id": complaint_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    return {"message": "Complaint updated successfully"}


# ============= SEED COMMON CREDIT REPAIR COMPANIES =============

async def seed_credit_repair_companies():
    """Seed common credit repair companies"""
    existing = await db.credit_repair_companies.count_documents({})
    if existing > 0:
        return
    
    common_companies = [
        {
            "name": "Lexington Law",
            "website": "https://www.lexingtonlaw.com",
            "description": "One of the largest credit repair law firms in the United States"
        },
        {
            "name": "Credit Saint",
            "website": "https://www.creditsaint.com",
            "description": "Credit repair service with multiple service tiers"
        },
        {
            "name": "The Credit People",
            "website": "https://www.thecreditpeople.com",
            "description": "Credit repair company with flat monthly fee"
        },
        {
            "name": "Sky Blue Credit",
            "website": "https://www.skyblue.com",
            "description": "Simple, straightforward credit repair service"
        },
        {
            "name": "CreditRepair.com",
            "website": "https://www.creditrepair.com",
            "description": "Technology-driven credit repair service"
        },
        {
            "name": "Ovation Credit",
            "website": "https://www.ovationcredit.com",
            "description": "Credit repair with personalized service"
        },
        {
            "name": "Credit Firm",
            "website": "https://www.creditfirm.net",
            "description": "Law firm based credit repair"
        },
        {
            "name": "Pyramid Credit Repair",
            "website": "https://www.pyramidcreditrepair.com",
            "description": "Arizona-based credit repair company"
        }
    ]
    
    for company_data in common_companies:
        slug = re.sub(r'[^a-z0-9]+', '-', company_data["name"].lower()).strip('-')
        company = {
            "id": str(uuid4()),
            "name": company_data["name"],
            "slug": slug,
            "website": company_data.get("website"),
            "description": company_data.get("description"),
            "is_verified": True,
            "has_comparison_page": True,  # Assume we have comparison pages
            "comparison_page_slug": f"vs-{slug}",
            "complaint_count": 0,
            "avg_rating": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.credit_repair_companies.insert_one(company)
    
    print("✅ Seeded credit repair companies")
