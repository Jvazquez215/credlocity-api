"""
Review Linking & Case Management API
Handles interlinking of client and attorney reviews, case settlements, and content attachments
"""

from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional, List, Dict
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import BaseModel
import re
import os

# Import database from server
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
client = get_client(MONGO_URL)
db = client[DB_NAME]

review_linking_router = APIRouter(prefix="/api/review-linking", tags=["Review Linking"])


# ==================== MODELS ====================

class SettlementDetails(BaseModel):
    amount: Optional[float] = None
    defendant_name: Optional[str] = None  # Who was sued (credit bureau, collector, etc.)
    defendant_type: Optional[str] = None  # credit_bureau, debt_collector, credit_repair_company
    case_type: Optional[str] = None  # fdcpa, fcra, tcpa, state_consumer_protection
    settlement_date: Optional[str] = None
    case_summary: Optional[str] = None
    is_public: bool = True  # Whether settlement details can be shown publicly


class AttachedContent(BaseModel):
    blog_ids: List[str] = []
    press_release_ids: List[str] = []
    lawsuit_doc_urls: List[str] = []
    related_page_slugs: List[str] = []  # Links to other pages for interlinking


class ReviewLinkRequest(BaseModel):
    source_review_id: str  # The review initiating the link
    target_review_id: str  # The review to link to
    link_type: str = "case_related"  # case_related, same_attorney, same_defendant


class ReviewSearchFilters(BaseModel):
    client_name: Optional[str] = None
    client_city: Optional[str] = None
    client_state: Optional[str] = None
    defendant_name: Optional[str] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    attorney_name: Optional[str] = None
    has_settlement: Optional[bool] = None


# ==================== HELPER FUNCTIONS ====================

def normalize_name(name: str) -> str:
    """Normalize name for matching - lowercase, remove special chars"""
    if not name:
        return ""
    return re.sub(r'[^a-z\s]', '', name.lower()).strip()


def calculate_match_score(review1: dict, review2: dict) -> float:
    """Calculate how likely two reviews are related (0-100)"""
    score = 0
    
    # Name similarity (up to 40 points)
    name1 = normalize_name(review1.get("client_name", ""))
    name2 = normalize_name(review2.get("linked_client_review_name", "") or review2.get("client_name", ""))
    if name1 and name2:
        # Simple word overlap
        words1 = set(name1.split())
        words2 = set(name2.split())
        if words1 & words2:
            overlap = len(words1 & words2) / max(len(words1), len(words2))
            score += overlap * 40
    
    # Location match (up to 30 points)
    loc1 = review1.get("location", "") or ""
    loc2 = review2.get("client_city", "") + ", " + review2.get("client_state", "") if review2.get("client_city") else review2.get("location", "")
    if loc1 and loc2:
        loc1_lower = loc1.lower()
        loc2_lower = loc2.lower()
        if loc1_lower == loc2_lower:
            score += 30
        elif any(part in loc2_lower for part in loc1_lower.split(",")):
            score += 15
    
    # Defendant/Company match (up to 30 points)
    def1 = review1.get("defendant_name", "") or review1.get("competitor_switched_from", "") or ""
    def2 = review2.get("settlement_details", {}).get("defendant_name", "") or review2.get("defendant_name", "") or ""
    if def1 and def2:
        if normalize_name(def1) == normalize_name(def2):
            score += 30
        elif normalize_name(def1) in normalize_name(def2) or normalize_name(def2) in normalize_name(def1):
            score += 15
    
    return min(score, 100)


# ==================== CLIENT REVIEW ENDPOINTS ====================

@review_linking_router.get("/client-reviews/search")
async def search_client_reviews(
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    defendant: Optional[str] = None,
    limit: int = 20,
    authorization: Optional[str] = Header(None)
):
    """
    Search for client reviews to link to.
    Used by attorneys when submitting reviews to find matching clients.
    """
    query = {"is_attorney_review": {"$ne": True}}
    
    if name:
        query["client_name"] = {"$regex": name, "$options": "i"}
    
    if city or state:
        location_pattern = ""
        if city:
            location_pattern += city
        if state:
            location_pattern += (".*" if city else "") + state
        if location_pattern:
            query["location"] = {"$regex": location_pattern, "$options": "i"}
    
    if defendant:
        query["$or"] = [
            {"defendant_name": {"$regex": defendant, "$options": "i"}},
            {"competitor_switched_from": {"$regex": defendant, "$options": "i"}},
            {"settlement_details.defendant_name": {"$regex": defendant, "$options": "i"}}
        ]
    
    reviews = await db.reviews.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    return {
        "reviews": reviews,
        "total": len(reviews),
        "filters_applied": {
            "name": name,
            "city": city,
            "state": state,
            "defendant": defendant
        }
    }


@review_linking_router.get("/attorney-reviews/search")
async def search_attorney_reviews(
    attorney_name: Optional[str] = None,
    client_name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    has_settlement: Optional[bool] = None,
    limit: int = 20,
    authorization: Optional[str] = Header(None)
):
    """
    Search for attorney reviews to link to.
    Used by clients when submitting reviews to find matching attorney cases.
    """
    query = {"is_attorney_review": True}
    
    if attorney_name:
        query["$or"] = [
            {"client_name": {"$regex": attorney_name, "$options": "i"}},
            {"attorney_name": {"$regex": attorney_name, "$options": "i"}}
        ]
    
    if client_name:
        query["linked_client_review_name"] = {"$regex": client_name, "$options": "i"}
    
    if city or state:
        location_pattern = ""
        if city:
            location_pattern += city
        if state:
            location_pattern += (".*" if city else "") + state
        if location_pattern:
            query["$or"] = query.get("$or", []) + [
                {"client_city": {"$regex": location_pattern, "$options": "i"}},
                {"location": {"$regex": location_pattern, "$options": "i"}}
            ]
    
    if has_settlement is True:
        query["$or"] = query.get("$or", []) + [
            {"attorney_settlement_amount": {"$gt": 0}},
            {"settlement_details.amount": {"$gt": 0}}
        ]
    
    reviews = await db.reviews.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    return {
        "reviews": reviews,
        "total": len(reviews)
    }


@review_linking_router.get("/smart-match/{review_id}")
async def get_smart_matches(review_id: str, authorization: Optional[str] = Header(None)):
    """
    Get smart matching suggestions for a review.
    Finds potential linked reviews based on name, location, and defendant.
    """
    # Get the source review
    source_review = await db.reviews.find_one({"id": review_id}, {"_id": 0})
    if not source_review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Determine what to search for based on review type
    is_attorney_review = source_review.get("is_attorney_review", False)
    
    if is_attorney_review:
        # Attorney review - search for matching client reviews
        query = {"is_attorney_review": {"$ne": True}, "id": {"$ne": review_id}}
    else:
        # Client review - search for matching attorney reviews
        query = {"is_attorney_review": True, "id": {"$ne": review_id}}
    
    # Get potential matches
    potential_matches = await db.reviews.find(query, {"_id": 0}).limit(50).to_list(50)
    
    # Calculate match scores
    matches = []
    for match in potential_matches:
        score = calculate_match_score(source_review, match)
        if score > 20:  # Only include matches with score > 20%
            matches.append({
                "review": match,
                "match_score": round(score, 1),
                "match_reasons": []
            })
            
            # Add match reasons
            if score >= 30:
                if normalize_name(source_review.get("client_name", "")) in normalize_name(match.get("linked_client_review_name", "") or match.get("client_name", "")):
                    matches[-1]["match_reasons"].append("Name match")
                if source_review.get("location") and source_review.get("location", "").lower() in (match.get("location", "") or "").lower():
                    matches[-1]["match_reasons"].append("Same location")
    
    # Sort by match score
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    return {
        "source_review": source_review,
        "matches": matches[:10],  # Top 10 matches
        "total_potential": len(matches)
    }


# ==================== LINKING ENDPOINTS ====================

@review_linking_router.post("/link")
async def link_reviews(data: ReviewLinkRequest, authorization: Optional[str] = Header(None)):
    """
    Link two reviews together (bi-directional).
    """
    source = await db.reviews.find_one({"id": data.source_review_id})
    target = await db.reviews.find_one({"id": data.target_review_id})
    
    if not source or not target:
        raise HTTPException(status_code=404, detail="One or both reviews not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Update source review
    await db.reviews.update_one(
        {"id": data.source_review_id},
        {"$set": {
            "linked_client_review_id": data.target_review_id if source.get("is_attorney_review") else None,
            "linked_attorney_review_id": data.target_review_id if not source.get("is_attorney_review") else None,
            "linked_client_review_name": target.get("client_name") if source.get("is_attorney_review") else None,
            "link_type": data.link_type,
            "linked_at": now,
            "updated_at": now
        }}
    )
    
    # Update target review (bi-directional)
    await db.reviews.update_one(
        {"id": data.target_review_id},
        {"$set": {
            "linked_client_review_id": data.source_review_id if target.get("is_attorney_review") else None,
            "linked_attorney_review_id": data.source_review_id if not target.get("is_attorney_review") else None,
            "linked_client_review_name": source.get("client_name") if target.get("is_attorney_review") else None,
            "link_type": data.link_type,
            "linked_at": now,
            "updated_at": now
        }}
    )
    
    return {
        "success": True,
        "message": "Reviews linked successfully",
        "link": {
            "source_id": data.source_review_id,
            "target_id": data.target_review_id,
            "link_type": data.link_type
        }
    }


@review_linking_router.delete("/link/{review_id}")
async def unlink_review(review_id: str, authorization: Optional[str] = Header(None)):
    """
    Remove link from a review (bi-directional).
    """
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Get linked review ID
    linked_id = review.get("linked_client_review_id") or review.get("linked_attorney_review_id")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Remove link from source
    await db.reviews.update_one(
        {"id": review_id},
        {"$set": {
            "linked_client_review_id": None,
            "linked_attorney_review_id": None,
            "linked_client_review_name": None,
            "link_type": None,
            "linked_at": None,
            "updated_at": now
        }}
    )
    
    # Remove link from target (if exists)
    if linked_id:
        await db.reviews.update_one(
            {"id": linked_id},
            {"$set": {
                "linked_client_review_id": None,
                "linked_attorney_review_id": None,
                "linked_client_review_name": None,
                "link_type": None,
                "linked_at": None,
                "updated_at": now
            }}
        )
    
    return {"success": True, "message": "Link removed"}


# ==================== SETTLEMENT & CASE DETAILS ====================

@review_linking_router.put("/review/{review_id}/settlement")
async def update_settlement_details(review_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """
    Update settlement/case details for a review.
    """
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    settlement_details = {
        "amount": data.get("amount"),
        "defendant_name": data.get("defendant_name"),
        "defendant_type": data.get("defendant_type"),
        "case_type": data.get("case_type"),
        "settlement_date": data.get("settlement_date"),
        "case_summary": data.get("case_summary"),
        "is_public": data.get("is_public", True)
    }
    
    await db.reviews.update_one(
        {"id": review_id},
        {"$set": {
            "settlement_details": settlement_details,
            "has_settlement": bool(settlement_details.get("amount")),
            "case_type": data.get("case_type") or "settlement",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Settlement details updated"}


@review_linking_router.put("/review/{review_id}/attachments")
async def update_review_attachments(review_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """
    Attach blogs, press releases, or lawsuit documents to a review.
    """
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    attached_content = {
        "blog_ids": data.get("blog_ids", []),
        "press_release_ids": data.get("press_release_ids", []),
        "lawsuit_doc_urls": data.get("lawsuit_doc_urls", []),
        "related_page_slugs": data.get("related_page_slugs", [])
    }
    
    await db.reviews.update_one(
        {"id": review_id},
        {"$set": {
            "attached_content": attached_content,
            "has_attachments": any([
                attached_content["blog_ids"],
                attached_content["press_release_ids"],
                attached_content["lawsuit_doc_urls"]
            ]),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Attachments updated"}


# ==================== REVIEW CATEGORIES ====================

@review_linking_router.get("/categories")
async def get_review_categories():
    """
    Get all review categories with counts.
    """
    # Count by category
    pipeline = [
        {"$match": {"show_on_success_stories": {"$ne": False}}},
        {"$group": {
            "_id": {
                "is_attorney": "$is_attorney_review",
                "has_settlement": {"$gt": ["$attorney_settlement_amount", 0]},
                "category": "$review_category"
            },
            "count": {"$sum": 1}
        }}
    ]
    
    results = await db.reviews.aggregate(pipeline).to_list(100)
    
    categories = {
        "cases_settled_won": {
            "name": "Cases Settled/Won",
            "description": "Attorney reviews with successful case outcomes",
            "count": 0,
            "slug": "cases-settled-won"
        },
        "attorney_testimonials": {
            "name": "Attorney Network Testimonials",
            "description": "Attorneys reviewing their partnership with Credlocity",
            "count": 0,
            "slug": "attorney-testimonials"
        },
        "client_success_stories": {
            "name": "Client Success Stories",
            "description": "Client reviews and credit improvement stories",
            "count": 0,
            "slug": "client-success-stories"
        },
        "lawsuit_victories": {
            "name": "Lawsuit Success Stories",
            "description": "Client reviews with lawsuit settlements",
            "count": 0,
            "slug": "lawsuit-victories"
        }
    }
    
    for r in results:
        is_attorney = r["_id"].get("is_attorney")
        has_settlement = r["_id"].get("has_settlement")
        
        if is_attorney and has_settlement:
            categories["cases_settled_won"]["count"] += r["count"]
        elif is_attorney:
            categories["attorney_testimonials"]["count"] += r["count"]
        elif has_settlement:
            categories["lawsuit_victories"]["count"] += r["count"]
        else:
            categories["client_success_stories"]["count"] += r["count"]
    
    return {"categories": list(categories.values())}


@review_linking_router.get("/by-category/{category_slug}")
async def get_reviews_by_category(category_slug: str, limit: int = 50):
    """
    Get reviews by category slug.
    """
    query = {"show_on_success_stories": {"$ne": False}}
    
    if category_slug == "cases-settled-won":
        query["is_attorney_review"] = True
        query["$or"] = [
            {"attorney_settlement_amount": {"$gt": 0}},
            {"settlement_details.amount": {"$gt": 0}}
        ]
    elif category_slug == "attorney-testimonials":
        query["is_attorney_review"] = True
        query["$and"] = [
            {"$or": [
                {"attorney_settlement_amount": {"$in": [None, 0]}},
                {"attorney_settlement_amount": {"$exists": False}}
            ]},
            {"$or": [
                {"settlement_details.amount": {"$in": [None, 0]}},
                {"settlement_details": {"$exists": False}}
            ]}
        ]
    elif category_slug == "lawsuit-victories":
        query["is_attorney_review"] = {"$ne": True}
        query["$or"] = [
            {"has_settlement": True},
            {"settlement_details.amount": {"$gt": 0}},
            {"worked_with_attorney": True}
        ]
    else:  # client-success-stories
        query["is_attorney_review"] = {"$ne": True}
        query["$and"] = [
            {"$or": [
                {"has_settlement": {"$ne": True}},
                {"has_settlement": {"$exists": False}}
            ]},
            {"$or": [
                {"worked_with_attorney": {"$ne": True}},
                {"worked_with_attorney": {"$exists": False}}
            ]}
        ]
    
    reviews = await db.reviews.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {
        "category": category_slug,
        "reviews": reviews,
        "total": len(reviews)
    }


# ==================== FULL REVIEW PAGE DATA ====================

@review_linking_router.get("/full-review/{review_id_or_slug}")
async def get_full_review_data(review_id_or_slug: str):
    """
    Get complete review data including linked reviews, attachments, and related content.
    This is used for individual review/success story pages.
    """
    # Find by ID or slug
    review = await db.reviews.find_one(
        {"$or": [{"id": review_id_or_slug}, {"story_slug": review_id_or_slug}]},
        {"_id": 0}
    )
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    result = {
        "review": review,
        "linked_review": None,
        "attached_blogs": [],
        "attached_press_releases": [],
        "related_reviews": []
    }
    
    # Get linked review
    linked_id = review.get("linked_client_review_id") or review.get("linked_attorney_review_id")
    if linked_id:
        linked = await db.reviews.find_one({"id": linked_id}, {"_id": 0})
        result["linked_review"] = linked
    
    # Get attached content
    attached = review.get("attached_content", {})
    
    if attached.get("blog_ids"):
        blogs = await db.blogs.find(
            {"id": {"$in": attached["blog_ids"]}},
            {"_id": 0, "id": 1, "title": 1, "slug": 1, "featured_image": 1, "excerpt": 1}
        ).to_list(10)
        result["attached_blogs"] = blogs
    
    if attached.get("press_release_ids"):
        prs = await db.press_releases.find(
            {"id": {"$in": attached["press_release_ids"]}},
            {"_id": 0, "id": 1, "title": 1, "slug": 1, "date": 1}
        ).to_list(10)
        result["attached_press_releases"] = prs
    
    # Get related reviews (same location or defendant)
    related_query = {
        "id": {"$ne": review["id"]},
        "show_on_success_stories": {"$ne": False}
    }
    
    if review.get("location"):
        related_query["location"] = {"$regex": review["location"].split(",")[0], "$options": "i"}
    
    related = await db.reviews.find(related_query, {"_id": 0}).limit(4).to_list(4)
    result["related_reviews"] = related
    
    # Generate schema.org data for SEO
    result["schema_data"] = {
        "@context": "https://schema.org",
        "@type": "Review",
        "itemReviewed": {
            "@type": "Organization",
            "name": "Credlocity"
        },
        "author": {
            "@type": "Person",
            "name": review.get("client_name")
        },
        "reviewBody": review.get("testimonial_text"),
        "reviewRating": {
            "@type": "Rating",
            "ratingValue": review.get("rating", 5),
            "bestRating": 5
        }
    }
    
    if review.get("settlement_details", {}).get("amount"):
        result["schema_data"]["about"] = {
            "@type": "LegalService",
            "name": "Consumer Protection Case",
            "result": f"${review['settlement_details']['amount']:,.0f} settlement"
        }
    
    return result


# ==================== STATISTICS ====================

@review_linking_router.get("/stats")
async def get_review_linking_stats():
    """
    Get statistics about review linking.
    """
    total_reviews = await db.reviews.count_documents({})
    linked_reviews = await db.reviews.count_documents({
        "$or": [
            {"linked_client_review_id": {"$ne": None}},
            {"linked_attorney_review_id": {"$ne": None}}
        ]
    })
    
    attorney_reviews = await db.reviews.count_documents({"is_attorney_review": True})
    client_reviews = await db.reviews.count_documents({"is_attorney_review": {"$ne": True}})
    
    with_settlement = await db.reviews.count_documents({
        "$or": [
            {"attorney_settlement_amount": {"$gt": 0}},
            {"settlement_details.amount": {"$gt": 0}},
            {"has_settlement": True}
        ]
    })
    
    with_attachments = await db.reviews.count_documents({"has_attachments": True})
    
    return {
        "total_reviews": total_reviews,
        "linked_reviews": linked_reviews,
        "link_rate": round((linked_reviews / total_reviews * 100) if total_reviews > 0 else 0, 1),
        "attorney_reviews": attorney_reviews,
        "client_reviews": client_reviews,
        "reviews_with_settlement": with_settlement,
        "reviews_with_attachments": with_attachments
    }
