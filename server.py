from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, Response, Header
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import os
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import shutil
import uuid
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL not available, image processing disabled")
import io
import base64
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    print("Warning: reportlab not available, PDF generation disabled")
from creditsage_bot import CreditSageBot


# Helper function to remove MongoDB _id field
def remove_id(doc):
    """Remove _id field from MongoDB document"""
    if doc and '_id' in doc:
        doc.pop('_id')
    return doc


def remove_ids(docs):
    """Remove _id field from list of MongoDB documents"""
    return [remove_id(doc) for doc in docs if doc]


from models import (
    User, UserCreate, UserUpdate, UserLogin, Token,
    Page, PageCreate, PageUpdate,
    Author, AuthorCreate, AuthorUpdate,
    BlogPost, BlogPostCreate, BlogPostUpdate,
    Category, CategoryCreate, CategoryUpdate,
    Tag, TagCreate, TagUpdate,
    Banner, BannerCreate, Settings,
    Complaint, ComplaintCreate,
    Review, ReviewCreate, ReviewUpdate,
    MediaEnhanced, MediaCreate, MediaUpdate,
    ReviewEnhanced, ReviewEnhancedCreate, ReviewEnhancedUpdate,
    FAQ, FAQCreate, FAQUpdate,
    FAQCategory, FAQCategoryCreate, FAQCategoryUpdate,
    SiteSettings, SiteSettingsUpdate,
    EducationVideo, EducationVideoCreate, EducationVideoUpdate,
    Affiliate, AffiliateCreate, AffiliateUpdate,
    PartnerLead, PartnerLeadCreate,
    PageBuilderLayout, PageBuilderLayoutUpdate,
    BannerPopup,
    Lawsuit, LawsuitCreate, LawsuitUpdate,
    PressRelease, PressReleaseCreate, PressReleaseUpdate,
    LegalPage, LegalPageCreate, LegalPageUpdate,
    ReviewCategory, ReviewCategoryCreate, ReviewCategoryUpdate
)
from auth import (
    verify_password, get_password_hash, create_access_token,
    decode_token, security
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Media upload directory
MEDIA_DIR = ROOT_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)

# Mount static files for media access
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# ============ AUTH HELPER ============
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    
    return user

def check_permissions(required_role: str):
    role_hierarchy = {
        "super_admin": 5,
        "admin": 4,
        "editor": 3,
        "author": 2,
        "viewer": 1
    }
    
    async def permission_checker(user: dict = Depends(get_current_user)):
        user_role = user.get("role", "viewer")
        if role_hierarchy.get(user_role, 0) < role_hierarchy.get(required_role, 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    
    return permission_checker


# ============ AUTH ROUTES ============
@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    
    if not user or not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    
    # Update last login
    await db.users.update_one(
        {"email": credentials.email},
        {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
    )
    
    access_token = create_access_token(data={"sub": user["email"]})
    
    # Remove password from response
    user_response = {k: v for k, v in user.items() if k != "hashed_password"}
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response
    }


@api_router.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    user_response = {k: v for k, v in current_user.items() if k != "hashed_password"}
    return user_response


# ============ USER ROUTES ============
@api_router.post("/users", response_model=User, dependencies=[Depends(check_permissions("admin"))])
async def create_user(user: UserCreate, current_user: dict = Depends(get_current_user)):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    user_dict = user.model_dump()
    user_dict["hashed_password"] = get_password_hash(user_dict.pop("password"))
    user_obj = User(**user_dict)
    
    doc = user_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.users.insert_one(doc)
    return user_obj


@api_router.get("/users", response_model=List[User], dependencies=[Depends(check_permissions("admin"))])
async def get_users():
    users = await db.users.find({}, {"_id": 0}).to_list(1000)
    for user in users:
        if isinstance(user.get('created_at'), str):
            user['created_at'] = datetime.fromisoformat(user['created_at'])
        if user.get('last_login') and isinstance(user['last_login'], str):
            user['last_login'] = datetime.fromisoformat(user['last_login'])
    return users


@api_router.get("/users/{user_id}", response_model=User, dependencies=[Depends(check_permissions("admin"))])
async def get_user(user_id: str):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if isinstance(user.get('created_at'), str):
        user['created_at'] = datetime.fromisoformat(user['created_at'])
    if user.get('last_login') and isinstance(user['last_login'], str):
        user['last_login'] = datetime.fromisoformat(user['last_login'])
    
    return user


@api_router.put("/users/{user_id}", response_model=User, dependencies=[Depends(check_permissions("admin"))])
async def update_user(user_id: str, user_update: UserUpdate):
    update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    
    if isinstance(updated_user.get('created_at'), str):
        updated_user['created_at'] = datetime.fromisoformat(updated_user['created_at'])
    if updated_user.get('last_login') and isinstance(updated_user['last_login'], str):
        updated_user['last_login'] = datetime.fromisoformat(updated_user['last_login'])
    
    return updated_user


@api_router.delete("/users/{user_id}", dependencies=[Depends(check_permissions("super_admin"))])
async def delete_user(user_id: str):
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}


# ============ PAGE ROUTES ============
@api_router.post("/pages", response_model=Page, dependencies=[Depends(check_permissions("editor"))])
async def create_page(page: PageCreate, current_user: dict = Depends(get_current_user)):
    # Check if slug already exists
    existing = await db.pages.find_one({"slug": page.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Page with this slug already exists")
    
    page_dict = page.model_dump()
    page_dict["created_by"] = current_user["id"]
    page_obj = Page(**page_dict)
    
    doc = page_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    
    await db.pages.insert_one(doc)
    return page_obj


@api_router.get("/pages", response_model=List[Page])
async def get_pages(status: Optional[str] = None, placement: Optional[str] = None):
    query = {}
    if status:
        query["status"] = status
    if placement:
        query["placement"] = placement
    
    pages = await db.pages.find(query, {"_id": 0}).to_list(1000)
    
    for page in pages:
        if isinstance(page.get('created_at'), str):
            page['created_at'] = datetime.fromisoformat(page['created_at'])
        if isinstance(page.get('updated_at'), str):
            page['updated_at'] = datetime.fromisoformat(page['updated_at'])
    
    return pages


@api_router.get("/pages/{page_id}", response_model=Page)
async def get_page(page_id: str):
    page = await db.pages.find_one({"id": page_id}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    if isinstance(page.get('created_at'), str):
        page['created_at'] = datetime.fromisoformat(page['created_at'])
    if isinstance(page.get('updated_at'), str):
        page['updated_at'] = datetime.fromisoformat(page['updated_at'])
    
    return page


@api_router.get("/pages/by-slug/{slug}", response_model=Page)
async def get_page_by_slug(slug: str):
    page = await db.pages.find_one({"slug": slug}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    if isinstance(page.get('created_at'), str):
        page['created_at'] = datetime.fromisoformat(page['created_at'])
    if isinstance(page.get('updated_at'), str):
        page['updated_at'] = datetime.fromisoformat(page['updated_at'])
    
    return page


@api_router.put("/pages/{page_id}", response_model=Page, dependencies=[Depends(check_permissions("editor"))])
async def update_page(page_id: str, page_update: PageUpdate):
    update_data = {k: v for k, v in page_update.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.pages.update_one({"id": page_id}, {"$set": update_data})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Page not found")
    
    updated_page = await db.pages.find_one({"id": page_id}, {"_id": 0})
    
    if isinstance(updated_page.get('created_at'), str):
        updated_page['created_at'] = datetime.fromisoformat(updated_page['created_at'])
    if isinstance(updated_page.get('updated_at'), str):
        updated_page['updated_at'] = datetime.fromisoformat(updated_page['updated_at'])
    
    return updated_page


@api_router.delete("/pages/{page_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_page(page_id: str):
    result = await db.pages.delete_one({"id": page_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"message": "Page deleted successfully"}


# ============ MEDIA ROUTES ============
@api_router.post("/media/upload", response_model=MediaEnhanced, dependencies=[Depends(check_permissions("author"))])
async def upload_media(
    file: UploadFile = File(...),
    alt_text: str = Form(""),
    caption: str = Form(""),
    folder: str = Form("/"),
    current_user: dict = Depends(get_current_user)
):
    """Enhanced media upload with image dimension detection"""
    try:
        # Generate unique filename
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = MEDIA_DIR / unique_filename
        
        # Read file content
        content = await file.read()
        
        # Save file
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # Determine file type and get dimensions for images
        mime_type = file.content_type or "application/octet-stream"
        if mime_type.startswith('image'):
            file_type = 'image'
            try:
                img = Image.open(io.BytesIO(content))
                width, height = img.size
            except Exception:
                width, height = None, None
        elif mime_type.startswith('video'):
            file_type = 'video'
            width, height = None, None
        else:
            file_type = 'document'
            width, height = None, None
        
        # Create enhanced media record
        media_obj = MediaEnhanced(
            filename=unique_filename,
            original_filename=file.filename,
            file_type=file_type,
            mime_type=mime_type,
            file_size=len(content),
            url=f"/media/{unique_filename}",
            alt_text=alt_text,
            caption=caption,
            folder=folder,
            width=width,
            height=height,
            uploaded_by=current_user["id"],
            used_in=[]
        )
        
        doc = media_obj.model_dump()
        doc['uploaded_at'] = doc['uploaded_at'].isoformat()
        
        await db.media.insert_one(doc)
        return media_obj
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@api_router.get("/media", response_model=List[MediaEnhanced], dependencies=[Depends(check_permissions("author"))])
async def get_media_files(
    folder: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 100
):
    """Get media files with optional filters"""
    query = {}
    if folder:
        query["folder"] = folder
    if file_type:
        query["file_type"] = file_type
    
    media_files = await db.media.find(query, {"_id": 0}).sort("uploaded_at", -1).limit(limit).to_list(limit)
    
    for media in media_files:
        if isinstance(media.get('uploaded_at'), str):
            media['uploaded_at'] = datetime.fromisoformat(media['uploaded_at'])
    
    return media_files


@api_router.put("/media/{media_id}", response_model=MediaEnhanced, dependencies=[Depends(check_permissions("author"))])
async def update_media(
    media_id: str,
    updates: MediaUpdate
):
    """Update media metadata (alt text, caption, folder)"""
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    result = await db.media.update_one(
        {"id": media_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Fetch and return updated media
    updated_media = await db.media.find_one({"id": media_id}, {"_id": 0})
    if isinstance(updated_media.get('uploaded_at'), str):
        updated_media['uploaded_at'] = datetime.fromisoformat(updated_media['uploaded_at'])
    
    return MediaEnhanced(**updated_media)


@api_router.delete("/media/{media_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_media(media_id: str):
    """Delete media file and database record"""
    # Get media record
    media = await db.media.find_one({"id": media_id}, {"_id": 0})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Check if used in any content
    if len(media.get("used_in", [])) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete. Media is used in {len(media['used_in'])} pages/posts"
        )
    
    # Delete file from disk
    file_path = MEDIA_DIR / media["filename"]
    if file_path.exists():
        file_path.unlink()
    
    # Delete from database
    await db.media.delete_one({"id": media_id})
    
    return {"message": "Media deleted successfully", "id": media_id}


# ============ BANNER ROUTES ============
@api_router.post("/banners", response_model=Banner, dependencies=[Depends(check_permissions("editor"))])
async def create_banner(banner: BannerCreate):
    banner_obj = Banner(**banner.model_dump())
    
    doc = banner_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('start_date'):
        doc['start_date'] = doc['start_date'].isoformat()
    if doc.get('end_date'):
        doc['end_date'] = doc['end_date'].isoformat()
    
    await db.banners.insert_one(doc)
    return banner_obj


@api_router.get("/banners", response_model=List[Banner])
async def get_banners(active_only: bool = False):
    query = {}
    if active_only:
        query["is_active"] = True
    
    banners = await db.banners.find(query, {"_id": 0}).to_list(100)
    for banner in banners:
        if isinstance(banner.get('created_at'), str):
            banner['created_at'] = datetime.fromisoformat(banner['created_at'])
        if banner.get('start_date') and isinstance(banner['start_date'], str):
            banner['start_date'] = datetime.fromisoformat(banner['start_date'])
        if banner.get('end_date') and isinstance(banner['end_date'], str):
            banner['end_date'] = datetime.fromisoformat(banner['end_date'])
    
    return banners


# ============ SETTINGS ROUTES ============
@api_router.get("/settings", response_model=Settings)
async def get_settings():
    settings = await db.settings.find_one({"id": "site_settings"}, {"_id": 0})
    if not settings:
        # Create default settings
        default_settings = Settings()
        doc = default_settings.model_dump()
        doc['updated_at'] = doc['updated_at'].isoformat()
        await db.settings.insert_one(doc)
        return default_settings
    
    if isinstance(settings.get('updated_at'), str):
        settings['updated_at'] = datetime.fromisoformat(settings['updated_at'])
    
    return settings


@api_router.put("/settings", response_model=Settings, dependencies=[Depends(check_permissions("admin"))])
async def update_settings(settings_update: dict):
    settings_update["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.settings.update_one(
        {"id": "site_settings"},
        {"$set": settings_update},
        upsert=True
    )
    
    updated_settings = await db.settings.find_one({"id": "site_settings"}, {"_id": 0})
    
    if isinstance(updated_settings.get('updated_at'), str):
        updated_settings['updated_at'] = datetime.fromisoformat(updated_settings['updated_at'])
    
    return updated_settings


# ============ INITIALIZATION ROUTE ============
@api_router.post("/init")
async def initialize_system():
    """Create master admin account if no users exist"""
    user_count = await db.users.count_documents({})
    
    if user_count == 0:
        master_admin = User(
            email="Admin@credlocity.com",
            hashed_password=get_password_hash("Credit123!"),
            full_name="Master Administrator",
            role="super_admin",
            is_active=True
        )
        
        doc = master_admin.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.users.insert_one(doc)
        
        return {"message": "Master admin account created successfully", "email": "Admin@credlocity.com"}
    
    return {"message": "System already initialized"}


# ============ COMPLAINT ROUTES ============
@api_router.post("/complaints", response_model=Complaint)
async def create_complaint(complaint: ComplaintCreate):
    """Submit a complaint about another credit repair company"""
    complaint_obj = Complaint(**complaint.model_dump())
    
    doc = complaint_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.complaints.insert_one(doc)
    return complaint_obj


@api_router.get("/complaints", response_model=List[Complaint], dependencies=[Depends(check_permissions("editor"))])
async def get_complaints(status: Optional[str] = None):
    """Get all complaints (admin only)"""
    query = {}
    if status:
        query["status"] = status
    
    complaints = await db.complaints.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    for complaint in complaints:
        if isinstance(complaint.get('created_at'), str):
            complaint['created_at'] = datetime.fromisoformat(complaint['created_at'])
    
    return complaints


@api_router.get("/complaints/{complaint_id}", response_model=Complaint, dependencies=[Depends(check_permissions("editor"))])
async def get_complaint(complaint_id: str):
    """Get a specific complaint"""
    complaint = await db.complaints.find_one({"id": complaint_id}, {"_id": 0})
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    if isinstance(complaint.get('created_at'), str):
        complaint['created_at'] = datetime.fromisoformat(complaint['created_at'])
    
    return complaint


@api_router.put("/complaints/{complaint_id}/status", dependencies=[Depends(check_permissions("editor"))])
async def update_complaint_status(complaint_id: str, status: str):
    """Update complaint status"""
    result = await db.complaints.update_one(
        {"id": complaint_id},
        {"$set": {"status": status}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    return {"message": "Status updated successfully"}


# ============ REVIEW/TESTIMONIAL ROUTES ============
@api_router.post("/reviews", response_model=ReviewEnhanced, dependencies=[Depends(check_permissions("editor"))])
async def create_review(review: ReviewEnhancedCreate):
    """Create a new review/testimonial with auto-calculated points improved"""
    # Auto-calculate points improved
    points_improved = review.after_score - review.before_score
    
    review_obj = ReviewEnhanced(
        **review.model_dump(),
        points_improved=points_improved
    )
    
    doc = review_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    
    await db.reviews.insert_one(doc)
    return review_obj


@api_router.get("/reviews", response_model=List[ReviewEnhanced])
async def get_reviews(
    featured_on_homepage: Optional[bool] = None,
    show_on_success_stories: Optional[bool] = None,
    review_category: Optional[str] = None
):
    """Get all reviews with optional filters"""
    query = {}
    if featured_on_homepage is not None:
        query["featured_on_homepage"] = featured_on_homepage
    if show_on_success_stories is not None:
        query["show_on_success_stories"] = show_on_success_stories
    if review_category is not None:
        query["review_category"] = review_category
    
    reviews = await db.reviews.find(query, {"_id": 0}).sort("display_order", 1).to_list(1000)
    
    # Ensure all required fields have defaults
    for review in reviews:
        if isinstance(review.get('created_at'), str):
            review['created_at'] = datetime.fromisoformat(review['created_at'])
        if isinstance(review.get('updated_at'), str):
            review['updated_at'] = datetime.fromisoformat(review['updated_at'])
        
        # Set defaults for required fields that might be missing or None
        if review.get('before_score') is None:
            review['before_score'] = 0
        if review.get('after_score') is None:
            review['after_score'] = 0
        review['points_improved'] = review.get('after_score', 0) - review.get('before_score', 0)
        
        # Fix string fields that might be None
        if review.get('full_story') is None:
            review['full_story'] = review.get('testimonial_text', '') or ''
        if review.get('testimonial_text') is None:
            review['testimonial_text'] = ''
        if review.get('client_name') is None:
            review['client_name'] = 'Anonymous'
        
        # Fix numeric fields that might have empty strings
        for numeric_field in ['attorney_settlement_amount']:
            if review.get(numeric_field) == '' or review.get(numeric_field) == 'null':
                review[numeric_field] = None
            elif review.get(numeric_field) is not None:
                try:
                    review[numeric_field] = float(review[numeric_field])
                except (ValueError, TypeError):
                    review[numeric_field] = None
        
        for int_field in ['credlocity_points_gained', 'attorney_points_gained']:
            if review.get(int_field) == '' or review.get(int_field) == 'null':
                review[int_field] = None
            elif review.get(int_field) is not None:
                try:
                    review[int_field] = int(review[int_field])
                except (ValueError, TypeError):
                    review[int_field] = None
    
    return reviews


@api_router.get("/reviews/{review_id}", response_model=ReviewEnhanced)
async def get_review(review_id: str):
    """Get a specific review"""
    review = await db.reviews.find_one({"id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if isinstance(review.get('created_at'), str):
        review['created_at'] = datetime.fromisoformat(review['created_at'])
    if isinstance(review.get('updated_at'), str):
        review['updated_at'] = datetime.fromisoformat(review['updated_at'])
    
    # Fix None values for required string fields
    if review.get('full_story') is None:
        review['full_story'] = review.get('testimonial_text', '') or ''
    if review.get('testimonial_text') is None:
        review['testimonial_text'] = ''
    if review.get('client_name') is None:
        review['client_name'] = 'Anonymous'
    if review.get('before_score') is None:
        review['before_score'] = 0
    if review.get('after_score') is None:
        review['after_score'] = 0
    
    return review


@api_router.get("/reviews/story/{slug}", response_model=ReviewEnhanced)
async def get_review_by_slug(slug: str):
    """Get a specific review by story slug for individual story pages"""
    review = await db.reviews.find_one({"story_slug": slug}, {"_id": 0})
    if not review:
        raise HTTPException(status_code=404, detail="Story not found")
    
    if isinstance(review.get('created_at'), str):
        review['created_at'] = datetime.fromisoformat(review['created_at'])
    if isinstance(review.get('updated_at'), str):
        review['updated_at'] = datetime.fromisoformat(review['updated_at'])
    
    # Fix None values for required string fields
    if review.get('full_story') is None:
        review['full_story'] = review.get('testimonial_text', '') or ''
    if review.get('testimonial_text') is None:
        review['testimonial_text'] = ''
    if review.get('client_name') is None:
        review['client_name'] = 'Anonymous'
    
    return review


@api_router.put("/reviews/{review_id}", response_model=ReviewEnhanced, dependencies=[Depends(check_permissions("editor"))])
async def update_review(review_id: str, review_update: ReviewEnhancedUpdate):
    """Update a review with auto-recalculation of points improved"""
    update_data = {k: v for k, v in review_update.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # If scores changed, recalculate points improved
    if 'before_score' in update_data or 'after_score' in update_data:
        current_review = await db.reviews.find_one({"id": review_id}, {"_id": 0})
        if not current_review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        before = update_data.get('before_score', current_review.get('before_score'))
        after = update_data.get('after_score', current_review.get('after_score'))
        update_data['points_improved'] = after - before
    
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.reviews.update_one({"id": review_id}, {"$set": update_data})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    
    updated_review = await db.reviews.find_one({"id": review_id}, {"_id": 0})
    
    if isinstance(updated_review.get('created_at'), str):
        updated_review['created_at'] = datetime.fromisoformat(updated_review['created_at'])
    if isinstance(updated_review.get('updated_at'), str):
        updated_review['updated_at'] = datetime.fromisoformat(updated_review['updated_at'])
    
    return updated_review


@api_router.delete("/reviews/{review_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_review(review_id: str):
    """Delete a review"""
    result = await db.reviews.delete_one({"id": review_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return {"message": "Review deleted successfully", "id": review_id}



# ============================================
# BLOG POST ENDPOINTS
# ============================================

@api_router.get("/blog/posts")
async def get_blog_posts(
    status: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    featured: Optional[bool] = None,
    author_id: Optional[str] = None,
    related_page: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """
    Get all blog posts with optional filters
    Public endpoint but returns only published posts unless authenticated
    """
    query = {}
    
    # Filter by status
    if status:
        query["status"] = status
    else:
        # Default: only show published posts for public access
        query["status"] = "published"
    
    # Filter by category
    if category:
        query["categories"] = category
    
    # Filter by tag
    if tag:
        query["tags"] = tag
    
    # Filter by featured
    if featured is not None:
        query["featured_post"] = featured
    
    # Filter by author
    if author_id:
        query["author_id"] = author_id
    
    # Filter by related page (for credit issue pages, etc.)
    if related_page:
        query["related_pages"] = related_page
    
    posts = await db.blog_posts.find(query, {"_id": 0}).sort("publish_date", -1).skip(skip).limit(limit).to_list(length=limit)
    return remove_ids(posts)


@api_router.get("/blog/posts/all")
async def get_all_blog_posts_admin(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all blog posts for admin (including drafts)
    Requires authentication
    """
    query = {}
    
    if status:
        query["status"] = status
    
    if category:
        query["categories"] = category
    
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"content": {"$regex": search, "$options": "i"}},
            {"excerpt": {"$regex": search, "$options": "i"}}
        ]
    
    posts = await db.blog_posts.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    posts = remove_ids(posts)
    
    total = await db.blog_posts.count_documents(query)
    
    return {
        "posts": posts,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@api_router.post("/blog/posts", dependencies=[Depends(check_permissions("author"))])
async def create_blog_post(post: BlogPostCreate, current_user: dict = Depends(get_current_user)):
    """
    Create a new blog post
    Requires author permission or higher
    """
    # Check if slug already exists
    existing = await db.blog_posts.find_one({"slug": post.slug})
    if existing:
        raise HTTPException(status_code=400, detail=f"Slug '{post.slug}' already exists")
    
    # Convert Pydantic model to dict
    post_dict = post.dict()
    post_dict["id"] = str(uuid.uuid4())
    post_dict["created_at"] = datetime.now(timezone.utc)
    post_dict["updated_at"] = datetime.now(timezone.utc)
    post_dict["created_by"] = current_user.get("id")
    post_dict["last_edited_by"] = current_user.get("id")
    post_dict["view_count"] = 0
    
    # Fetch and populate author data if author_id is provided
    if post_dict.get("author_id"):
        author = await db.authors.find_one({"id": post_dict["author_id"]})
        if author:
            post_dict["author_name"] = author.get("full_name", "")
            post_dict["author_slug"] = author.get("slug", "")
            post_dict["author_photo_url"] = author.get("photo_url", "")
            post_dict["author_title"] = author.get("title", "")
            post_dict["author_credentials"] = author.get("credentials", [])
            post_dict["author_experience"] = author.get("years_experience", 0)
            post_dict["author_education"] = author.get("education", [])
            post_dict["author_publications"] = author.get("publications", [])
            post_dict["author_bio"] = author.get("bio", "")
    
    # If status is published and no publish_date, set it now
    if post_dict["status"] == "published" and not post_dict.get("publish_date"):
        post_dict["publish_date"] = datetime.now(timezone.utc)
    
    # Prepare for MongoDB (convert datetime to ISO string)
    if isinstance(post_dict.get('created_at'), datetime):
        post_dict['created_at'] = post_dict['created_at'].isoformat()
    if isinstance(post_dict.get('updated_at'), datetime):
        post_dict['updated_at'] = post_dict['updated_at'].isoformat()
    if isinstance(post_dict.get('publish_date'), datetime):
        post_dict['publish_date'] = post_dict['publish_date'].isoformat()
    if isinstance(post_dict.get('scheduled_publish'), datetime):
        post_dict['scheduled_publish'] = post_dict['scheduled_publish'].isoformat()
    
    await db.blog_posts.insert_one(post_dict)
    
    # Update category post counts
    for cat_id in post_dict.get("categories", []):
        await db.categories.update_one(
            {"id": cat_id},
            {"$inc": {"post_count": 1}}
        )
    
    # Update tag post counts
    for tag_name in post_dict.get("tags", []):
        await db.tags.update_one(
            {"slug": tag_name.lower().replace(" ", "-")},
            {"$inc": {"post_count": 1}},
            upsert=True
        )
    
    return remove_id(post_dict)


@api_router.get("/blog/posts/{post_id}")
async def get_blog_post(post_id: str):
    """
    Get a single blog post by ID
    Returns published posts for public, all posts for authenticated users
    """
    post = await db.blog_posts.find_one({"id": post_id})
    
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Increment view count
    await db.blog_posts.update_one(
        {"id": post_id},
        {"$inc": {"view_count": 1}}
    )
    
    return remove_id(post)


@api_router.get("/blog/posts/slug/{slug}")
async def get_blog_post_by_slug(slug: str):
    """
    Get a published blog post by slug (for public pages)
    """
    post = await db.blog_posts.find_one({"slug": slug, "status": "published"})
    
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Increment view count
    await db.blog_posts.update_one(
        {"slug": slug},
        {"$inc": {"view_count": 1}}
    )
    
    return remove_id(post)


@api_router.get("/blog/posts/{post_id}/schema")
async def get_blog_post_schema(post_id: str, include_faq: bool = False):
    """
    Generate Schema.org JSON-LD for a blog post (with site settings)
    """
    try:
        from schema_generator import generate_all_schemas
        
        post = await db.blog_posts.find_one({"id": post_id})
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")
        
        # Convert ObjectId to string
        if "_id" in post:
            del post["_id"]
        
        # Get site settings for organization schema
        site_settings = await db.site_settings.find_one({"id": "site_settings"})
        if site_settings and "_id" in site_settings:
            del site_settings["_id"]
        
        # Get FAQs if requested
        faqs = None
        if include_faq:
            faqs = await db.faqs.find({"status": "published"}).limit(10).to_list(None)
        
        schema_json = generate_all_schemas(post, site_settings, include_faq, faqs)
        
        return {"schema": schema_json, "schemas_array": schema_json}
    except Exception as e:
        print(f"[SCHEMA GENERATION ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/pricing/schema")
async def get_pricing_schema():
    """
    Generate Schema.org JSON-LD for pricing page
    Returns Service + AggregateOffer schema for all pricing plans
    """
    try:
        from schema_generator import generate_pricing_schema
        
        # Get site settings for organization schema
        site_settings = await db.site_settings.find_one({"id": "site_settings"})
        if site_settings and "_id" in site_settings:
            del site_settings["_id"]
        
        # Define pricing plans (matches frontend Pricing.js)
        pricing_data = [
            {
                "name": "Fraud Plan",
                "price": "$99.95",
                "trial": "15-Day Free Trial",
                "trial_days": 15,
                "features": [
                    "Identity theft & fraud removal",
                    "FCRA 605B credit block",
                    "All 3 credit bureaus",
                    "Monthly credit monitoring",
                    "Email support"
                ]
            },
            {
                "name": "Aggressive Plan",
                "price": "$179.95",
                "trial": "30-Day Free Trial",
                "trial_days": 30,
                "features": [
                    "Everything in Fraud Plan",
                    "Advanced dispute strategies",
                    "Collection account removal",
                    "Late payment removal",
                    "Monthly one-on-one reviews"
                ]
            },
            {
                "name": "Family Plan",
                "price": "$279.95",
                "trial": "30-Day Free Trial",
                "trial_days": 30,
                "features": [
                    "Everything in Aggressive Plan",
                    "Up to 4 family members",
                    "Individual credit repair for each",
                    "Family financial planning",
                    "Dedicated family account manager"
                ]
            }
        ]
        
        schema_json = generate_pricing_schema(pricing_data, site_settings)
        
        return {"schema": schema_json}
    except Exception as e:
        print(f"[PRICING SCHEMA GENERATION ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/blog/posts/{post_id}", dependencies=[Depends(check_permissions("author"))])
async def update_blog_post(post_id: str, post: BlogPostUpdate, current_user: dict = Depends(get_current_user)):
    """
    Update a blog post
    Requires author permission or higher
    """
    existing_post = await db.blog_posts.find_one({"id": post_id})
    
    if not existing_post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Check slug uniqueness if slug is being changed
    if post.slug and post.slug != existing_post.get("slug"):
        slug_exists = await db.blog_posts.find_one({"slug": post.slug, "id": {"$ne": post_id}})
        if slug_exists:
            raise HTTPException(status_code=400, detail=f"Slug '{post.slug}' already exists")
    
    # Update dict
    update_data = {k: v for k, v in post.dict(exclude_unset=True).items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    update_data["last_edited_by"] = current_user.get("id")
    
    # Fetch and populate author data if author_id is being updated or already exists
    author_id_to_fetch = update_data.get("author_id") or existing_post.get("author_id")
    if author_id_to_fetch:
        author = await db.authors.find_one({"id": author_id_to_fetch})
        if author:
            update_data["author_name"] = author.get("full_name", "")
            update_data["author_slug"] = author.get("slug", "")
            update_data["author_photo_url"] = author.get("photo_url", "")
            update_data["author_title"] = author.get("title", "")
            update_data["author_credentials"] = author.get("credentials", [])
            update_data["author_experience"] = author.get("years_experience", 0)
            update_data["author_education"] = author.get("education", [])
            update_data["author_publications"] = author.get("publications", [])
            update_data["author_bio"] = author.get("bio", "")
    
    # If changing status to published and no publish_date, set it now
    if update_data.get("status") == "published" and not existing_post.get("publish_date"):
        update_data["publish_date"] = datetime.now(timezone.utc)
    
    # Prepare datetime fields for MongoDB
    if isinstance(update_data.get('updated_at'), datetime):
        update_data['updated_at'] = update_data['updated_at'].isoformat()
    if isinstance(update_data.get('publish_date'), datetime):
        update_data['publish_date'] = update_data['publish_date'].isoformat()
    if isinstance(update_data.get('scheduled_publish'), datetime):
        update_data['scheduled_publish'] = update_data['scheduled_publish'].isoformat()
    
    await db.blog_posts.update_one(
        {"id": post_id},
        {"$set": update_data}
    )
    
    updated_post = await db.blog_posts.find_one({"id": post_id})
    return remove_id(updated_post)


@api_router.delete("/blog/posts/{post_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_blog_post(post_id: str):
    """
    Delete a blog post
    Requires editor permission or higher
    """
    post = await db.blog_posts.find_one({"id": post_id})
    
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Update category post counts
    for cat_id in post.get("categories", []):
        await db.categories.update_one(
            {"id": cat_id},
            {"$inc": {"post_count": -1}}
        )
    
    # Update tag post counts
    for tag_name in post.get("tags", []):
        await db.tags.update_one(
            {"slug": tag_name.lower().replace(" ", "-")},
            {"$inc": {"post_count": -1}}
        )
    
    result = await db.blog_posts.delete_one({"id": post_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    return {"message": "Blog post deleted successfully", "id": post_id}


# ============================================
# BLOG POST UPDATES/CORRECTIONS ENDPOINTS
# ============================================

@api_router.post("/blog/posts/{post_id}/updates", dependencies=[Depends(check_permissions("author"))])
async def add_blog_update(post_id: str, update_data: dict, current_user: dict = Depends(get_current_user)):
    """
    Add an update or correction to a blog post
    Requires author permission or higher
    """
    post = await db.blog_posts.find_one({"id": post_id})
    
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Create update object
    update = {
        "id": str(uuid.uuid4()),
        "type": update_data.get("type", "update"),  # "update" or "critical_update"
        "explanation": update_data.get("explanation", ""),
        "content": update_data.get("content", ""),
        "date": update_data.get("date", datetime.now(timezone.utc).isoformat()),
        "author": current_user.get("full_name", "Admin"),
        "highlight_enabled": update_data.get("highlight_enabled", False),
        "highlight_color": update_data.get("highlight_color", "#fef08a"),  # Default yellow
        "highlight_style": update_data.get("highlight_style", "background")  # "background" or "border"
    }
    
    # Convert date if it's a datetime object
    if isinstance(update["date"], datetime):
        update["date"] = update["date"].isoformat()
    
    # Add update to blog post
    await db.blog_posts.update_one(
        {"id": post_id},
        {
            "$push": {"updates": update},
            "$set": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_edited_by": current_user.get("id")
            }
        }
    )
    
    return {"message": "Update added successfully", "update": update}


@api_router.put("/blog/posts/{post_id}/updates/{update_id}", dependencies=[Depends(check_permissions("author"))])
async def edit_blog_update(post_id: str, update_id: str, update_data: dict, current_user: dict = Depends(get_current_user)):
    """
    Edit an existing update on a blog post
    Requires author permission or higher
    """
    post = await db.blog_posts.find_one({"id": post_id})
    
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Find the update in the updates array
    updates = post.get("updates", [])
    update_index = next((i for i, u in enumerate(updates) if u.get("id") == update_id), None)
    
    if update_index is None:
        raise HTTPException(status_code=404, detail="Update not found")
    
    # Update the specific fields
    update_path_prefix = f"updates.{update_index}"
    update_fields = {}
    
    if "type" in update_data:
        update_fields[f"{update_path_prefix}.type"] = update_data["type"]
    if "explanation" in update_data:
        update_fields[f"{update_path_prefix}.explanation"] = update_data["explanation"]
    if "content" in update_data:
        update_fields[f"{update_path_prefix}.content"] = update_data["content"]
    if "date" in update_data:
        date_value = update_data["date"]
        if isinstance(date_value, datetime):
            date_value = date_value.isoformat()
        update_fields[f"{update_path_prefix}.date"] = date_value
    if "highlight_enabled" in update_data:
        update_fields[f"{update_path_prefix}.highlight_enabled"] = update_data["highlight_enabled"]
    if "highlight_color" in update_data:
        update_fields[f"{update_path_prefix}.highlight_color"] = update_data["highlight_color"]
    if "highlight_style" in update_data:
        update_fields[f"{update_path_prefix}.highlight_style"] = update_data["highlight_style"]
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_fields["last_edited_by"] = current_user.get("id")
    
    await db.blog_posts.update_one(
        {"id": post_id},
        {"$set": update_fields}
    )
    
    # Get updated post
    updated_post = await db.blog_posts.find_one({"id": post_id})
    updated_update = next((u for u in updated_post.get("updates", []) if u.get("id") == update_id), None)
    
    return {"message": "Update edited successfully", "update": updated_update}


@api_router.delete("/blog/posts/{post_id}/updates/{update_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_blog_update(post_id: str, update_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete an update from a blog post
    Requires author permission or higher
    """
    post = await db.blog_posts.find_one({"id": post_id})
    
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Remove the update from the array
    result = await db.blog_posts.update_one(
        {"id": post_id},
        {
            "$pull": {"updates": {"id": update_id}},
            "$set": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_edited_by": current_user.get("id")
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Update not found")
    
    return {"message": "Update deleted successfully"}


# ============================================
# CATEGORY ENDPOINTS
# ============================================

@api_router.get("/blog/categories")
async def get_categories():
    """
    Get all categories with post counts
    """
    categories = await db.categories.find().sort("name", 1).to_list(length=100)
    return remove_ids(categories)


@api_router.post("/blog/categories", dependencies=[Depends(check_permissions("editor"))])
async def create_category(category: CategoryCreate, current_user: dict = Depends(get_current_user)):
    """
    Create a new category
    Requires editor permission or higher
    """
    # Check if slug already exists
    existing = await db.categories.find_one({"slug": category.slug})
    if existing:
        raise HTTPException(status_code=400, detail=f"Category slug '{category.slug}' already exists")
    
    category_dict = category.dict()
    category_dict["id"] = str(uuid.uuid4())
    category_dict["post_count"] = 0
    category_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.categories.insert_one(category_dict)
    return remove_id(category_dict)


@api_router.put("/blog/categories/{category_id}", dependencies=[Depends(check_permissions("editor"))])
async def update_category(category_id: str, category: CategoryUpdate):
    """
    Update a category
    Requires editor permission or higher
    """
    existing = await db.categories.find_one({"id": category_id})
    
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Check slug uniqueness if being changed
    if category.slug and category.slug != existing.get("slug"):
        slug_exists = await db.categories.find_one({"slug": category.slug, "id": {"$ne": category_id}})
        if slug_exists:
            raise HTTPException(status_code=400, detail=f"Category slug '{category.slug}' already exists")
    
    update_data = {k: v for k, v in category.dict(exclude_unset=True).items() if v is not None}
    
    await db.categories.update_one(
        {"id": category_id},
        {"$set": update_data}
    )
    
    updated_category = await db.categories.find_one({"id": category_id})
    return remove_id(updated_category)


@api_router.delete("/blog/categories/{category_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_category(category_id: str):
    """
    Delete a category
    Requires editor permission or higher
    """
    result = await db.categories.delete_one({"id": category_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return {"message": "Category deleted successfully", "id": category_id}


# ============================================
# TAG ENDPOINTS
# ============================================

@api_router.get("/blog/tags")
async def get_tags():
    """
    Get all tags with post counts
    """
    tags = await db.tags.find().sort("name", 1).to_list(length=200)
    return remove_ids(tags)


@api_router.post("/blog/tags", dependencies=[Depends(check_permissions("editor"))])
async def create_tag(tag: TagCreate, current_user: dict = Depends(get_current_user)):
    """
    Create a new tag
    Requires editor permission or higher
    """
    # Check if slug already exists
    existing = await db.tags.find_one({"slug": tag.slug})
    if existing:
        raise HTTPException(status_code=400, detail=f"Tag slug '{tag.slug}' already exists")
    
    tag_dict = tag.dict()
    tag_dict["id"] = str(uuid.uuid4())
    tag_dict["post_count"] = 0
    tag_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.tags.insert_one(tag_dict)
    return remove_id(tag_dict)


@api_router.delete("/blog/tags/{tag_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_tag(tag_id: str):
    """
    Delete a tag
    Requires editor permission or higher
    """
    result = await db.tags.delete_one({"id": tag_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    return {"message": "Tag deleted successfully", "id": tag_id}



# ==========================================
# AUTHOR / TEAM MEMBER ENDPOINTS
# ==========================================

@api_router.get("/authors")
async def get_authors(
    status: Optional[str] = None,
    featured: Optional[bool] = None,
    show_on_team_page: Optional[bool] = None
):
    """
    Get all authors with optional filters
    Public endpoint - no authentication required
    """
    try:
        query = {}
        
        if status:
            query["status"] = status
        if featured is not None:
            query["featured"] = featured
        if show_on_team_page is not None:
            query["show_on_team_page"] = show_on_team_page
        
        print(f"[AUTHORS API] Fetching authors with query: {query}")
        authors = await db.authors.find(query).sort("display_order", 1).to_list(100)
        print(f"[AUTHORS API] Found {len(authors)} authors")
        
        # Remove MongoDB _id field (keep existing UUID id field)
        for author in authors:
            if "_id" in author:
                author.pop("_id")
        
        return authors
    except Exception as e:
        print(f"[AUTHORS API ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/authors", dependencies=[Depends(get_current_user)])
async def create_author(author: AuthorCreate):
    """
    Create a new author
    Requires authentication
    """
    try:
        # Check slug uniqueness
        existing = await db.authors.find_one({"slug": author.slug})
        if existing:
            raise HTTPException(status_code=400, detail="Slug already exists")
        
        # Create author dict
        author_dict = author.model_dump()
        author_dict["id"] = str(uuid.uuid4())
        author_dict["post_count"] = 0
        author_dict["created_at"] = datetime.now(timezone.utc)
        author_dict["updated_at"] = datetime.now(timezone.utc)
        
        # Insert into database
        await db.authors.insert_one(author_dict)
        
        # Return without _id
        author_dict.pop("_id", None)
        return author_dict
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/authors/{author_id}")
async def get_author(author_id: str):
    """
    Get a single author by ID (UUID)
    Public endpoint
    """
    try:
        # Query by UUID 'id' field
        author = await db.authors.find_one({"id": author_id})
        
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")
        
        # Convert _id ObjectId to string and remove it
        if "_id" in author:
            author.pop("_id")
        
        return author
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[AUTHORS API ERROR] get_author: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/authors/slug/{slug}")
async def get_author_by_slug(slug: str):
    """
    Get a single author by slug
    Public endpoint for author profile pages
    """
    try:
        author = await db.authors.find_one({"slug": slug, "status": "active"})
        
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")
        
        if "_id" in author:
            author["id"] = str(author.pop("_id"))
        
        # Get post count for this author
        post_count = await db.blog_posts.count_documents({"author_id": author["id"], "status": "published"})
        author["post_count"] = post_count
        
        return author
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/authors/{author_id}", dependencies=[Depends(get_current_user)])
async def update_author(author_id: str, author_update: AuthorUpdate):
    """
    Update an author
    Requires authentication
    """
    try:
        # Check if author exists
        existing = await db.authors.find_one({"id": author_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Author not found")
        
        # If slug is being updated, check uniqueness
        update_data = author_update.model_dump(exclude_unset=True)
        if "slug" in update_data and update_data["slug"] != existing.get("slug"):
            slug_exists = await db.authors.find_one({"slug": update_data["slug"]})
            if slug_exists:
                raise HTTPException(status_code=400, detail="Slug already exists")
        
        # Update timestamp
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        # Update in database
        await db.authors.update_one(
            {"id": author_id},
            {"$set": update_data}
        )
        
        # Fetch and return updated author
        updated_author = await db.authors.find_one({"id": author_id})
        if "_id" in updated_author:
            updated_author.pop("_id")
        
        return updated_author
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/authors/{author_id}", dependencies=[Depends(get_current_user)])
async def delete_author(author_id: str):
    """
    Delete an author by ID (UUID)
    Requires authentication
    Checks if author has blog posts before deleting
    """
    try:
        # Check if author exists by UUID 'id' field
        author = await db.authors.find_one({"id": author_id})
        
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")
        
        # Check if author has blog posts
        post_count = await db.blog_posts.count_documents({"author_id": author_id})
        if post_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete author with {post_count} blog post(s). Please reassign posts first."
            )
        
        # Delete by UUID 'id' field
        result = await db.authors.delete_one({"id": author_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Author not found")
        
        return {"message": "Author deleted successfully", "id": author_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[AUTHORS API ERROR] delete_author: {e}")
        raise HTTPException(status_code=500, detail=str(e))




# ===================================
# FAQ MANAGEMENT ENDPOINTS (Phase 3C)
# ===================================

# GET /api/faqs - List all FAQs with filters
@api_router.get("/faqs")
async def get_faqs(
    category: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Get all FAQs with optional filters
    Query params: ?category=equifax-faqs&status=published
    """
    try:
        query = {}
        
        if category:
            query["category_slug"] = category
        
        if status:
            query["status"] = status
        
        faqs = await db.faqs.find(query).sort("order", 1).to_list(length=None)
        
        # Convert MongoDB _id to string id
        for faq in faqs:
            faq["id"] = str(faq.pop("_id"))
        
        return faqs
    except Exception as e:
        print(f"[FAQ API ERROR] get_faqs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /api/faqs - Create new FAQ
@api_router.post("/faqs")
async def create_faq(
    faq: FAQCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new FAQ (requires authentication)"""
    try:
        faq_dict = faq.model_dump()
        faq_dict["created_at"] = datetime.now(timezone.utc)
        faq_dict["updated_at"] = datetime.now(timezone.utc)
        
        result = await db.faqs.insert_one(faq_dict)
        
        # Update category FAQ count
        await db.faq_categories.update_one(
            {"slug": faq.category_slug},
            {"$inc": {"faq_count": 1}}
        )
        
        faq_dict["id"] = str(result.inserted_id)
        faq_dict.pop("_id", None)
        
        return faq_dict
    except Exception as e:
        print(f"[FAQ API ERROR] create_faq: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/faqs/{faq_id} - Get single FAQ by ID
@api_router.get("/faqs/{faq_id}")
async def get_faq(faq_id: str):
    """Get a single FAQ by ID"""
    try:
        faq = await db.faqs.find_one({"id": faq_id})
        
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        faq["id"] = str(faq.pop("_id"))
        return faq
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[FAQ API ERROR] get_faq: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/faqs/slug/{slug} - Get FAQ by slug (public)
@api_router.get("/faqs/slug/{slug}")
async def get_faq_by_slug(slug: str):
    """Get a single FAQ by slug for public access"""
    try:
        faq = await db.faqs.find_one({"slug": slug})
        
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        # Increment view count
        await db.faqs.update_one(
            {"slug": slug},
            {"$inc": {"views": 1}}
        )
        
        faq["id"] = str(faq.pop("_id"))
        return faq
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[FAQ API ERROR] get_faq_by_slug: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /api/faqs/{faq_id} - Update FAQ
@api_router.put("/faqs/{faq_id}")
async def update_faq(
    faq_id: str,
    faq: FAQUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a FAQ (requires authentication)"""
    try:
        # Check if FAQ exists
        existing_faq = await db.faqs.find_one({"id": faq_id})
        if not existing_faq:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        update_data = {k: v for k, v in faq.model_dump(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        # If category changed, update FAQ counts
        if "category_slug" in update_data and update_data["category_slug"] != existing_faq["category_slug"]:
            # Decrease count in old category
            await db.faq_categories.update_one(
                {"slug": existing_faq["category_slug"]},
                {"$inc": {"faq_count": -1}}
            )
            # Increase count in new category
            await db.faq_categories.update_one(
                {"slug": update_data["category_slug"]},
                {"$inc": {"faq_count": 1}}
            )
        
        result = await db.faqs.update_one(
            {"id": faq_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        # Get updated FAQ
        updated_faq = await db.faqs.find_one({"id": faq_id})
        updated_faq["id"] = str(updated_faq.pop("_id"))
        
        return updated_faq
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[FAQ API ERROR] update_faq: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /api/faqs/{faq_id} - Delete FAQ
@api_router.delete("/faqs/{faq_id}")
async def delete_faq(
    faq_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a FAQ (requires authentication)"""
    try:
        # Get FAQ to find category for count update
        faq = await db.faqs.find_one({"id": faq_id})
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        # Delete FAQ
        result = await db.faqs.delete_one({"id": faq_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        # Update category FAQ count
        await db.faq_categories.update_one(
            {"slug": faq["category_slug"]},
            {"$inc": {"faq_count": -1}}
        )
        
        return {"message": "FAQ deleted successfully", "id": faq_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[FAQ API ERROR] delete_faq: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /api/faqs/{faq_id}/increment-views - Increment view counter
@api_router.post("/faqs/{faq_id}/increment-views")
async def increment_faq_views(faq_id: str):
    """Increment FAQ view counter (public endpoint)"""
    try:
        result = await db.faqs.update_one(
            {"id": faq_id},
            {"$inc": {"views": 1}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        return {"message": "View count incremented"}
    except Exception as e:
        print(f"[FAQ API ERROR] increment_faq_views: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/faqs/search - Search FAQs
@api_router.get("/faqs/search")
async def search_faqs(q: str):
    """Search FAQs by question/answer text"""
    try:
        # Case-insensitive search in question and answer
        faqs = await db.faqs.find({
            "$or": [
                {"question": {"$regex": q, "$options": "i"}},
                {"answer": {"$regex": q, "$options": "i"}}
            ],
            "status": "published"
        }).to_list(length=None)
        
        # Convert MongoDB _id to string id
        for faq in faqs:
            faq["id"] = str(faq.pop("_id"))
        
        return faqs
    except Exception as e:
        print(f"[FAQ API ERROR] search_faqs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# FAQ CATEGORY ENDPOINTS
# ===================================

# GET /api/faq-categories - List all categories
@api_router.get("/faq-categories")
async def get_faq_categories():
    """Get all FAQ categories"""
    try:
        categories = await db.faq_categories.find().sort("order", 1).to_list(length=None)
        
        # Convert MongoDB _id to string id
        for category in categories:
            category["id"] = str(category.pop("_id"))
        
        return categories
    except Exception as e:
        print(f"[FAQ CATEGORY API ERROR] get_faq_categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /api/faq-categories - Create category
@api_router.post("/faq-categories")
async def create_faq_category(
    category: FAQCategoryCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new FAQ category (requires authentication)"""
    try:
        category_dict = category.model_dump()
        category_dict["created_at"] = datetime.now(timezone.utc)
        category_dict["faq_count"] = 0
        
        result = await db.faq_categories.insert_one(category_dict)
        
        category_dict["id"] = str(result.inserted_id)
        category_dict.pop("_id", None)
        
        return category_dict
    except Exception as e:
        print(f"[FAQ CATEGORY API ERROR] create_faq_category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /api/faq-categories/{cat_id} - Update category
@api_router.put("/faq-categories/{cat_id}")
async def update_faq_category(
    cat_id: str,
    category: FAQCategoryUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a FAQ category (requires authentication)"""
    try:
        update_data = {k: v for k, v in category.model_dump(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        result = await db.faq_categories.update_one(
            {"id": cat_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="FAQ category not found")
        
        # Get updated category
        updated_category = await db.faq_categories.find_one({"id": cat_id})
        updated_category["id"] = str(updated_category.pop("_id"))
        
        return updated_category
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[FAQ CATEGORY API ERROR] update_faq_category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /api/faq-categories/{cat_id} - Delete category
@api_router.delete("/faq-categories/{cat_id}")
async def delete_faq_category(
    cat_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a FAQ category (requires authentication)"""
    try:
        # Check if category has FAQs
        category = await db.faq_categories.find_one({"id": cat_id})
        if not category:
            raise HTTPException(status_code=404, detail="FAQ category not found")
        
        if category.get("faq_count", 0) > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete category with existing FAQs. Please reassign or delete FAQs first."
            )
        
        result = await db.faq_categories.delete_one({"id": cat_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="FAQ category not found")
        
        return {"message": "FAQ category deleted successfully", "id": cat_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[FAQ CATEGORY API ERROR] delete_faq_category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# SITE SETTINGS ENDPOINTS (Phase 4)
# ===================================

# GET /api/site-settings - Get site settings (public)
@api_router.get("/site-settings")
async def get_site_settings():
    """Get site settings (public endpoint for logo, colors, etc.)"""
    try:
        settings = await db.site_settings.find_one({"id": "site_settings"})
        
        if not settings:
            # Return default settings if not found
            default_settings = SiteSettings().model_dump()
            return default_settings
        
        settings["id"] = str(settings.pop("_id", "site_settings"))
        return settings
    except Exception as e:
        print(f"[SITE SETTINGS API ERROR] get_site_settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /api/site-settings - Update site settings (super_admin only)
@api_router.put("/site-settings")
async def update_site_settings(
    settings: SiteSettingsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update site settings (requires super_admin authentication)"""
    try:
        # Check if user is super_admin
        if current_user.get("role") != "super_admin":
            raise HTTPException(
                status_code=403,
                detail="Only super administrators can modify site settings"
            )
        
        update_data = {k: v for k, v in settings.model_dump(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        # Upsert (update or insert if doesn't exist)
        result = await db.site_settings.update_one(
            {"id": "site_settings"},
            {"$set": update_data},
            upsert=True
        )
        
        # Get updated settings
        updated_settings = await db.site_settings.find_one({"id": "site_settings"})
        if updated_settings:
            updated_settings["id"] = str(updated_settings.pop("_id", "site_settings"))
        
        return updated_settings
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SITE SETTINGS API ERROR] update_site_settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# SEO TOOLS ENDPOINTS (Phase 4)
# ===================================

# GET /sitemap.xml - Auto-generated sitemap
@app.get("/sitemap.xml")
async def generate_sitemap():
    """Generate dynamic XML sitemap from all published content"""
    try:
        # Check if sitemap is enabled
        settings = await db.site_settings.find_one({"id": "site_settings"})
        if settings and not settings.get("sitemap_enabled", True):
            raise HTTPException(status_code=404, detail="Sitemap is disabled")
        
        # Fetch all published content
        pages = await db.pages.find({"status": "published"}).to_list(None)
        posts = await db.blog_posts.find({"status": "published"}).to_list(None)
        authors = await db.authors.find({"status": "active"}).to_list(None)
        press_releases = await db.press_releases.find({"is_published": True}).to_list(None)
        lawsuits = await db.lawsuits.find({"is_active": True}).to_list(None)
        
        # Start XML sitemap
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        
        # Add homepage
        sitemap += '  <url>\n'
        sitemap += '    <loc>https://credlocity.com/</loc>\n'
        sitemap += '    <priority>1.0</priority>\n'
        sitemap += '    <changefreq>weekly</changefreq>\n'
        sitemap += '  </url>\n'
        
        # Add static pages
        for page in pages:
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/{page["slug"]}</loc>\n'
            if "updated_at" in page and page["updated_at"]:
                lastmod = page["updated_at"]
                if isinstance(lastmod, datetime):
                    sitemap += f'    <lastmod>{lastmod.isoformat()}</lastmod>\n'
            sitemap += '    <priority>0.8</priority>\n'
            sitemap += '    <changefreq>monthly</changefreq>\n'
            sitemap += '  </url>\n'
        
        # Add blog posts (higher priority)
        sitemap += '  <url>\n'
        sitemap += '    <loc>https://credlocity.com/blog</loc>\n'
        sitemap += '    <priority>0.9</priority>\n'
        sitemap += '    <changefreq>weekly</changefreq>\n'
        sitemap += '  </url>\n'
        
        for post in posts:
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/blog/{post["slug"]}</loc>\n'
            if "updated_at" in post and post["updated_at"]:
                lastmod = post["updated_at"]
                if isinstance(lastmod, datetime):
                    sitemap += f'    <lastmod>{lastmod.isoformat()}</lastmod>\n'
            sitemap += '    <priority>0.9</priority>\n'
            sitemap += '    <changefreq>monthly</changefreq>\n'
            sitemap += '  </url>\n'
        
        # Add team directory page
        sitemap += '  <url>\n'
        sitemap += '    <loc>https://credlocity.com/team</loc>\n'
        sitemap += '    <priority>0.8</priority>\n'
        sitemap += '    <changefreq>monthly</changefreq>\n'
        sitemap += '  </url>\n'
        
        # Add author profiles
        for author in authors:
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/team/{author["slug"]}</loc>\n'
            if "updated_at" in author and author["updated_at"]:
                lastmod = author["updated_at"]
                if isinstance(lastmod, datetime):
                    sitemap += f'    <lastmod>{lastmod.isoformat()}</lastmod>\n'
            sitemap += '    <priority>0.7</priority>\n'
            sitemap += '    <changefreq>monthly</changefreq>\n'
            sitemap += '  </url>\n'
        
        # Add FAQ page
        sitemap += '  <url>\n'
        sitemap += '    <loc>https://credlocity.com/faqs</loc>\n'
        sitemap += '    <priority>0.8</priority>\n'
        sitemap += '    <changefreq>weekly</changefreq>\n'
        sitemap += '  </url>\n'
        
        # Add Press Releases hub page
        sitemap += '  <url>\n'
        sitemap += '    <loc>https://credlocity.com/press-releases</loc>\n'
        sitemap += '    <priority>0.9</priority>\n'
        sitemap += '    <changefreq>weekly</changefreq>\n'
        sitemap += '  </url>\n'
        
        # Add individual press releases
        for release in press_releases:
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/press-releases/{release["slug"]}</loc>\n'
            if "updated_at" in release and release["updated_at"]:
                lastmod = release["updated_at"]
                if isinstance(lastmod, datetime):
                    sitemap += f'    <lastmod>{lastmod.isoformat()}</lastmod>\n'
            sitemap += '    <priority>0.9</priority>\n'
            sitemap += '    <changefreq>monthly</changefreq>\n'
            sitemap += '  </url>\n'
        
        # Add Lawsuits hub page
        sitemap += '  <url>\n'
        sitemap += '    <loc>https://credlocity.com/lawsuits</loc>\n'
        sitemap += '    <priority>0.9</priority>\n'
        sitemap += '    <changefreq>weekly</changefreq>\n'
        sitemap += '  </url>\n'
        
        # Add individual lawsuits
        for lawsuit in lawsuits:
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/lawsuits/{lawsuit["slug"]}</loc>\n'
            if "updated_at" in lawsuit and lawsuit["updated_at"]:
                lastmod = lawsuit["updated_at"]
                if isinstance(lastmod, datetime):
                    sitemap += f'    <lastmod>{lastmod.isoformat()}</lastmod>\n'
            sitemap += '    <priority>0.8</priority>\n'
            sitemap += '    <changefreq>monthly</changefreq>\n'
            sitemap += '  </url>\n'
        
        sitemap += '</urlset>'
        
        return Response(content=sitemap, media_type="application/xml")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SITEMAP ERROR] generate_sitemap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /robots.txt - Auto-generated or custom robots.txt
@app.get("/robots.txt")
async def generate_robots():
    """Generate robots.txt (custom or default)"""
    try:
        # Check if custom robots.txt exists
        settings = await db.site_settings.find_one({"id": "site_settings"})
        
        if settings and settings.get("robots_txt_custom"):
            # Return custom robots.txt
            return Response(content=settings["robots_txt_custom"], media_type="text/plain")
        
        # Default robots.txt
        robots = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/

Sitemap: https://credlocity.com/sitemap.xml
"""
        
        return Response(content=robots, media_type="text/plain")
    except Exception as e:
        print(f"[ROBOTS.TXT ERROR] generate_robots: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# Router will be included at the end after all endpoints are defined

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ===================================
# EDUCATION HUB ENDPOINTS (Phase 5)
# ===================================

# GET /api/education-hub - Get Education Hub content (public)
@api_router.get("/education-hub")
async def get_education_hub():
    """Get Education Hub pillar page content"""
    try:
        hub = await db.education_hub.find_one({"id": "education_hub"})
        
        if not hub:
            # Create default hub if doesn't exist
            from models import EducationHub
            default_hub = EducationHub().model_dump()
            await db.education_hub.insert_one(default_hub)
            hub = default_hub
        
        if hub and "_id" in hub:
            hub["id"] = str(hub.pop("_id"))
        
        return hub
    except Exception as e:
        print(f"[EDUCATION HUB API ERROR] get_education_hub: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# PUT /api/education-hub - Update Education Hub (admin only)
@api_router.put("/education-hub")
async def update_education_hub(
    hub_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update Education Hub content"""
    try:
        hub_data["updated_at"] = datetime.now(timezone.utc)
        hub_data["last_edited_by"] = current_user.get("email", "")
        
        # Upsert
        result = await db.education_hub.update_one(
            {"id": "education_hub"},
            {"$set": hub_data},
            upsert=True
        )
        
        # Get updated hub
        updated_hub = await db.education_hub.find_one({"id": "education_hub"})
        if updated_hub and "_id" in updated_hub:
            updated_hub["id"] = str(updated_hub.pop("_id"))
        
        return updated_hub
    except Exception as e:
        print(f"[EDUCATION HUB API ERROR] update_education_hub: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# POST /api/education-hub/increment-views - Track page views
@api_router.post("/education-hub/increment-views")
async def increment_education_hub_views():
    """Increment Education Hub view count"""
    try:
        await db.education_hub.update_one(
            {"id": "education_hub"},
            {"$inc": {"views": 1}}
        )
        return {"message": "View count incremented"}
    except Exception as e:
        print(f"[EDUCATION HUB API ERROR] increment_views: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Duplicate video endpoints removed - using complete set at end of file


# ===================================
# SAMPLE LETTERS ENDPOINTS
# ===================================

# GET /api/sample-letters - List all letters
@api_router.get("/sample-letters")
async def get_sample_letters(
    letter_type: Optional[str] = None,
    target_recipient: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None
):
    """Get all sample letters with optional filters"""
    try:
        query = {}
        if letter_type:
            query["letter_type"] = letter_type
        if target_recipient:
            query["target_recipient"] = target_recipient
        if category:
            query["category"] = category
        if status:
            query["status"] = status
        
        letters = await db.sample_letters.find(query).sort("order", 1).to_list(None)
        for letter in letters:
            if "_id" in letter:
                letter["id"] = str(letter.pop("_id"))
        
        return letters
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] get_sample_letters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# POST /api/sample-letters - Create new letter
@api_router.post("/sample-letters")
async def create_sample_letter(
    letter: dict,
    current_user: dict = Depends(get_current_user)
):
    """Create new sample letter"""
    try:
        from models import SampleLetter
        letter_obj = SampleLetter(**letter)
        letter_dict = letter_obj.model_dump()
        
        result = await db.sample_letters.insert_one(letter_dict)
        return {"message": "Letter created successfully", "id": letter_obj.id}
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] create_sample_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# GET /api/sample-letters/{letter_id} - Get single letter
@api_router.get("/sample-letters/{letter_id}")
async def get_sample_letter(letter_id: str):
    """Get single sample letter by ID"""
    try:
        letter = await db.sample_letters.find_one({"id": letter_id})
        if not letter:
            raise HTTPException(status_code=404, detail="Letter not found")
        
        if "_id" in letter:
            letter["id"] = str(letter.pop("_id"))
        
        return letter
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] get_sample_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# PUT /api/sample-letters/{letter_id} - Update letter
@api_router.put("/sample-letters/{letter_id}")
async def update_sample_letter(
    letter_id: str,
    letter_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update sample letter"""
    try:
        letter_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await db.sample_letters.update_one(
            {"id": letter_id},
            {"$set": letter_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Letter not found")
        
        return {"message": "Letter updated successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] update_sample_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# DELETE /api/sample-letters/{letter_id} - Delete letter
@api_router.delete("/sample-letters/{letter_id}")
async def delete_sample_letter(
    letter_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete sample letter"""
    try:
        result = await db.sample_letters.delete_one({"id": letter_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Letter not found")
        
        return {"message": "Letter deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] delete_sample_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# POST /api/sample-letters/{letter_id}/increment-downloads - Track downloads
@api_router.post("/sample-letters/{letter_id}/increment-downloads")
async def increment_letter_downloads(letter_id: str):
    """Increment letter download count"""
    try:
        await db.sample_letters.update_one(
            {"id": letter_id},
            {"$inc": {"downloads": 1}}
        )
        return {"message": "Download count incremented"}
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] increment_letter_downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# POST /api/sample-letters/{letter_id}/generate - Generate filled letter
@api_router.post("/sample-letters/{letter_id}/generate")
async def generate_filled_letter(
    letter_id: str,
    filled_data: dict
):
    """Generate filled letter from template with user data"""
    try:
        # Get letter template
        letter = await db.sample_letters.find_one({"id": letter_id})
        if not letter:
            raise HTTPException(status_code=404, detail="Letter not found")
        
        # Replace placeholders with user data
        filled_letter = letter["letter_body"]
        for field_id, value in filled_data.items():
            placeholder = "{{" + field_id + "}}"
            filled_letter = filled_letter.replace(placeholder, str(value))
        
        # Increment download counter
        await db.sample_letters.update_one(
            {"id": letter_id},
            {"$inc": {"downloads": 1}}
        )
        
        return {
            "title": letter["title"],
            "filled_letter": filled_letter,
            "disclaimer": letter.get("legal_disclaimer", "")
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SAMPLE LETTERS API ERROR] generate_filled_letter: {e}")



# ===================================
# URL REDIRECT MANAGEMENT
# ===================================

@api_router.get("/url-redirects")
async def get_redirects(active: Optional[bool] = None, current_user: dict = Depends(get_current_user)):
    """Get all URL redirects"""
    try:
        query = {}
        if active is not None:
            query["active"] = active
        
        redirects = await db.url_redirects.find(query).to_list(None)
        for redirect in redirects:
            if "_id" in redirect:
                redirect["id"] = str(redirect.pop("_id"))
        
        return redirects
    except Exception as e:
        print(f"[REDIRECT API ERROR] get_redirects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/url-redirects")
async def create_redirect(redirect_data: dict, current_user: dict = Depends(get_current_user)):
    """Create URL redirect"""
    try:
        from models import URLRedirect
        redirect = URLRedirect(**redirect_data)
        await db.url_redirects.insert_one(redirect.model_dump())
        return {"message": "Redirect created", "id": redirect.id}
    except Exception as e:
        print(f"[REDIRECT API ERROR] create_redirect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/url-redirects/{redirect_id}")
async def delete_redirect(redirect_id: str, current_user: dict = Depends(get_current_user)):
    """Delete redirect"""
    try:
        result = await db.url_redirects.delete_one({"id": redirect_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Redirect not found")
        return {"message": "Redirect deleted"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[REDIRECT API ERROR] delete_redirect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/check-redirect")
async def check_redirect(url: str):
    """Check if URL has redirect (public endpoint)"""
    try:
        redirect = await db.url_redirects.find_one({"old_url": url, "active": True})
        if redirect:
            await db.url_redirects.update_one({"id": redirect["id"]}, {"$inc": {"hit_count": 1}})
            return {"redirect": True, "new_url": redirect["new_url"], "type": redirect.get("redirect_type", 301)}
        return {"redirect": False}
    except Exception as e:
        return {"redirect": False}


# ===================================
# RSS & NEWS SITEMAP
# ===================================

@api_router.get("/rss")
async def generate_rss_feed():
    """RSS feed for news blogs"""
    try:
        from xml.etree.ElementTree import Element, SubElement, tostring
        
        news_posts = await db.blog_posts.find({"status": "published", "is_news": True}).sort("publish_date", -1).limit(50).to_list(None)
        
        rss = Element('rss', version='2.0')
        channel = SubElement(rss, 'channel')
        SubElement(channel, 'title').text = 'Credlocity News'
        SubElement(channel, 'link').text = 'https://credlocity.com/blog'
        SubElement(channel, 'description').text = 'Latest credit repair news from Credlocity'
        
        for post in news_posts:
            item = SubElement(channel, 'item')
            SubElement(item, 'title').text = post.get('title', '')
            SubElement(item, 'link').text = f"https://credlocity.com/blog/{post.get('slug', '')}"
            SubElement(item, 'description').text = post.get('excerpt', '')
            SubElement(item, 'pubDate').text = post.get('publish_date', datetime.now(timezone.utc)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        rss_xml = tostring(rss, encoding='unicode')
        return Response(content=f'<?xml version="1.0" encoding="UTF-8"?>\n{rss_xml}', media_type="application/rss+xml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/rss.xml")
async def generate_rss_feed():
    """Generate RSS feed for news articles (Google News compatible)"""
    try:
        # Get all published news posts (not just last 2 days like sitemap)
        news_posts = await db.blog_posts.find({
            "status": "published", 
            "is_news": True
        }).sort("publish_date", -1).limit(50).to_list(None)
        
        # Build RSS 2.0 feed
        rss = '<?xml version="1.0" encoding="UTF-8"?>\n'
        rss += '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/">\n'
        rss += '  <channel>\n'
        rss += '    <title>Credlocity News</title>\n'
        rss += '    <link>https://credlocity.com/blog</link>\n'
        rss += '    <description>Latest news and updates from Credlocity - Credit Repair and Financial Education</description>\n'
        rss += '    <language>en-us</language>\n'
        rss += f'    <lastBuildDate>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>\n'
        rss += '    <atom:link href="https://credlocity.com/rss.xml" rel="self" type="application/rss+xml" />\n'
        rss += '    <generator>Credlocity CMS</generator>\n'
        rss += '    <image>\n'
        rss += '      <url>https://credlocity.com/logo.png</url>\n'
        rss += '      <title>Credlocity</title>\n'
        rss += '      <link>https://credlocity.com</link>\n'
        rss += '    </image>\n\n'
        
        for post in news_posts:
            # Get publish date
            pub_date = post.get("publish_date")
            if isinstance(pub_date, str):
                pub_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            elif not pub_date:
                pub_date = datetime.now(timezone.utc)
            
            # Format date for RSS (RFC 822)
            pub_date_str = pub_date.strftime("%a, %d %b %Y %H:%M:%S GMT")
            
            # Get content and strip HTML for description
            content = post.get("content", "")
            excerpt = post.get("excerpt", "")
            if not excerpt and content:
                # Create excerpt from content (strip HTML)
                import re
                excerpt = re.sub('<[^<]+?>', '', content)[:300] + '...'
            
            rss += '    <item>\n'
            rss += f'      <title><![CDATA[{post.get("title", "")}]]></title>\n'
            rss += f'      <link>https://credlocity.com/blog/{post.get("slug", "")}</link>\n'
            rss += f'      <guid isPermaLink="true">https://credlocity.com/blog/{post.get("slug", "")}</guid>\n'
            rss += f'      <pubDate>{pub_date_str}</pubDate>\n'
            rss += f'      <dc:creator><![CDATA[{post.get("author_name", "Credlocity Team")}]]></dc:creator>\n'
            rss += f'      <description><![CDATA[{excerpt}]]></description>\n'
            rss += f'      <content:encoded><![CDATA[{content}]]></content:encoded>\n'
            
            # Add categories
            categories = post.get("categories", [])
            for cat_id in categories:
                cat = await db.categories.find_one({"id": cat_id})
                if cat:
                    rss += f'      <category><![CDATA[{cat.get("name", "")}]]></category>\n'
            
            # Add featured image if available
            if post.get("featured_image_url"):
                rss += f'      <enclosure url="{post.get("featured_image_url")}" type="image/jpeg" />\n'
            
            rss += '    </item>\n\n'
        
        rss += '  </channel>\n'
        rss += '</rss>'
        
        return Response(content=rss, media_type="application/rss+xml")
    except Exception as e:
        print(f"[RSS XML GENERATION ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/rss-all")
async def generate_combined_rss_feed():
    """Combined RSS feed for blogs, press releases, and lawsuits"""
    try:
        from xml.etree.ElementTree import Element, SubElement, tostring
        
        # Fetch all content types
        blogs = await db.blog_posts.find({"status": "published"}).sort("publish_date", -1).limit(30).to_list(None)
        press_releases = await db.press_releases.find({"is_published": True}).sort("publish_date", -1).limit(30).to_list(None)
        lawsuits = await db.lawsuits.find({"is_active": True}).sort("created_at", -1).limit(30).to_list(None)
        
        # Combine and sort all items by date
        all_items = []
        
        for blog in blogs:
            all_items.append({
                'type': 'blog',
                'title': blog.get('title', ''),
                'link': f"https://credlocity.com/blog/{blog.get('slug', '')}",
                'description': blog.get('excerpt', ''),
                'date': blog.get('publish_date', blog.get('created_at', datetime.now(timezone.utc)))
            })
        
        for pr in press_releases:
            all_items.append({
                'type': 'press_release',
                'title': pr.get('title', ''),
                'link': f"https://credlocity.com/press-releases/{pr.get('slug', '')}",
                'description': pr.get('summary', ''),
                'date': pr.get('publish_date', pr.get('created_at', datetime.now(timezone.utc)))
            })
        
        for lawsuit in lawsuits:
            all_items.append({
                'type': 'lawsuit',
                'title': lawsuit.get('title', ''),
                'link': f"https://credlocity.com/lawsuits/{lawsuit.get('slug', '')}",
                'description': lawsuit.get('description', ''),
                'date': lawsuit.get('created_at', datetime.now(timezone.utc))
            })
        
        # Sort by date (most recent first)
        all_items.sort(key=lambda x: x['date'] if isinstance(x['date'], datetime) else datetime.fromisoformat(str(x['date']).replace('Z', '+00:00')), reverse=True)
        
        # Build RSS feed
        rss = Element('rss', version='2.0', attrib={'xmlns:atom': 'http://www.w3.org/2005/Atom'})
        channel = SubElement(rss, 'channel')
        SubElement(channel, 'title').text = 'Credlocity - All Updates'
        SubElement(channel, 'link').text = 'https://credlocity.com'
        SubElement(channel, 'description').text = 'Latest blogs, press releases, and lawsuits from Credlocity'
        SubElement(channel, 'language').text = 'en-us'
        SubElement(channel, 'lastBuildDate').text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Add atom:link for self-reference
        atom_link = SubElement(channel, '{http://www.w3.org/2005/Atom}link')
        atom_link.set('href', 'https://credlocity.com/rss-all')
        atom_link.set('rel', 'self')
        atom_link.set('type', 'application/rss+xml')
        
        for item_data in all_items[:50]:  # Limit to 50 most recent items
            item = SubElement(channel, 'item')
            SubElement(item, 'title').text = f"[{item_data['type'].replace('_', ' ').title()}] {item_data['title']}"
            SubElement(item, 'link').text = item_data['link']
            SubElement(item, 'description').text = item_data['description']
            
            # Format date
            date = item_data['date']
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            elif not isinstance(date, datetime):
                date = datetime.now(timezone.utc)
            
            SubElement(item, 'pubDate').text = date.strftime('%a, %d %b %Y %H:%M:%S GMT')
            SubElement(item, 'category').text = item_data['type'].replace('_', ' ').title()
        
        rss_xml = tostring(rss, encoding='unicode')
        return Response(content=f'<?xml version="1.0" encoding="UTF-8"?>\n{rss_xml}', media_type="application/rss+xml")
    except Exception as e:
        print(f"[RSS COMBINED ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

        return Response(content=rss, media_type="application/xml")
    except Exception as e:
        print(f"[RSS FEED ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/news-sitemap.xml")
async def generate_news_sitemap():
    """Google News sitemap (last 2 days of news only)"""
    try:
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        news_posts = await db.blog_posts.find({"status": "published", "is_news": True, "publish_date": {"$gte": two_days_ago}}).sort("publish_date", -1).to_list(None)
        
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
        
        for post in news_posts:
            # Get publish date
            pub_date = post.get("publish_date")
            if isinstance(pub_date, str):
                pub_date_str = pub_date
            elif pub_date:
                pub_date_str = pub_date.isoformat()
            else:
                pub_date_str = datetime.now(timezone.utc).isoformat()
            
            # Get keywords from SEO
            keywords = ""
            if post.get("seo") and post["seo"].get("keywords"):
                keywords = post["seo"]["keywords"]
            
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/blog/{post.get("slug", "")}</loc>\n'
            sitemap += '    <news:news>\n'
            sitemap += '      <news:publication>\n'
            sitemap += '        <news:name>Credlocity</news:name>\n'
            sitemap += '        <news:language>en</news:language>\n'
            sitemap += '      </news:publication>\n'
            sitemap += f'      <news:publication_date>{pub_date_str}</news:publication_date>\n'
            sitemap += f'      <news:title><![CDATA[{post.get("title", "")}]]></news:title>\n'
            if keywords:
                sitemap += f'      <news:keywords><![CDATA[{keywords}]]></news:keywords>\n'
            sitemap += '    </news:news>\n'
            sitemap += '  </url>\n'
        
        sitemap += '</urlset>'
        return Response(content=sitemap, media_type="application/xml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# BLOG UPDATES
# ===================================

@api_router.get("/blog-updates/{post_id}")
async def get_blog_updates(post_id: str):
    """Get updates for blog post"""
    try:
        updates = await db.blog_updates.find({"blog_post_id": post_id}).sort("update_date", -1).to_list(None)
        for update in updates:
            if "_id" in update:
                update["id"] = str(update.pop("_id"))
        return updates
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/blog-updates")
async def create_blog_update(update_data: dict, current_user: dict = Depends(get_current_user)):
    """Create blog update"""
    try:
        from models import BlogUpdate
        update = BlogUpdate(**update_data)
        update.created_by = current_user.get("email", "")
        await db.blog_updates.insert_one(update.model_dump())
        await db.blog_posts.update_one({"id": update.blog_post_id}, {"$set": {"updated_at": datetime.now(timezone.utc)}})
        return {"message": "Update created", "id": update.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# AFFILIATE PAGES
# ===================================

@api_router.get("/affiliates")
async def get_affiliates(status: Optional[str] = None, featured: Optional[bool] = None):
    """
    Get all affiliate pages with optional filters
    """
    try:
        query = {}
        if status:
            query["status"] = status
        if featured is not None:
            query["featured"] = featured
            
        affiliates = await db.affiliates.find(query).sort("order", 1).to_list(None)
        return remove_ids(affiliates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/affiliates/{affiliate_id}")
async def get_affiliate(affiliate_id: str):
    """Get single affiliate page by ID"""
    try:
        affiliate = await db.affiliates.find_one({"id": affiliate_id})
        if not affiliate:
            raise HTTPException(status_code=404, detail="Affiliate page not found")
        return remove_id(affiliate)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/affiliates/slug/{slug}")
async def get_affiliate_by_slug(slug: str):
    """Get affiliate page by slug (for public pages)"""
    try:
        affiliate = await db.affiliates.find_one({"slug": slug, "status": "published"})
        if not affiliate:
            raise HTTPException(status_code=404, detail="Affiliate page not found")
        return remove_id(affiliate)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/affiliates", dependencies=[Depends(check_permissions("author"))])
async def create_affiliate(affiliate: AffiliateCreate, current_user: dict = Depends(get_current_user)):
    """
    Create a new affiliate page
    Requires author permission or higher
    """
    try:
        # Check slug uniqueness
        existing = await db.affiliates.find_one({"slug": affiliate.slug})
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug '{affiliate.slug}' already exists")
        
        # Create affiliate object
        affiliate_dict = affiliate.model_dump()
        affiliate_dict["id"] = str(uuid.uuid4())
        affiliate_dict["created_at"] = datetime.now(timezone.utc)
        affiliate_dict["updated_at"] = datetime.now(timezone.utc)
        affiliate_dict["created_by"] = current_user.get("id")
        
        # Set published_at if status is published
        if affiliate_dict.get("status") == "published":
            affiliate_dict["published_at"] = datetime.now(timezone.utc)
        
        await db.affiliates.insert_one(affiliate_dict)
        
        return {"message": "Affiliate page created successfully", "id": affiliate_dict["id"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[AFFILIATE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/affiliates/{affiliate_id}", dependencies=[Depends(check_permissions("author"))])
async def update_affiliate(affiliate_id: str, affiliate: AffiliateUpdate, current_user: dict = Depends(get_current_user)):
    """
    Update an affiliate page
    Requires author permission or higher
    """
    try:
        existing = await db.affiliates.find_one({"id": affiliate_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Affiliate page not found")
        
        # Check slug uniqueness if slug is being changed
        if affiliate.slug and affiliate.slug != existing.get("slug"):
            slug_exists = await db.affiliates.find_one({"slug": affiliate.slug, "id": {"$ne": affiliate_id}})
            if slug_exists:
                raise HTTPException(status_code=400, detail=f"Slug '{affiliate.slug}' already exists")
        
        # Update data
        update_data = {k: v for k, v in affiliate.model_dump(exclude_unset=True).items() if v is not None}
        update_data["updated_at"] = datetime.now(timezone.utc)
        update_data["last_edited_by"] = current_user.get("id")
        
        # Set published_at if changing to published
        if update_data.get("status") == "published" and existing.get("status") != "published":
            update_data["published_at"] = datetime.now(timezone.utc)
        
        await db.affiliates.update_one(
            {"id": affiliate_id},
            {"$set": update_data}
        )
        
        return {"message": "Affiliate page updated successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[AFFILIATE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/affiliates/{affiliate_id}", dependencies=[Depends(check_permissions("admin"))])
async def delete_affiliate(affiliate_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete an affiliate page
    Requires admin permission or higher
    """
    try:
        result = await db.affiliates.delete_one({"id": affiliate_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Affiliate page not found")
        
        return {"message": "Affiliate page deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[AFFILIATE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================
# PARTNER LEADS API
# =====================================

@api_router.post("/partner-leads")
async def create_partner_lead(lead: PartnerLeadCreate, request: Request):
    """
    Create a new partner lead from partner signup form
    Public endpoint - no authentication required
    Stores lead in database for CMS tracking
    """
    try:
        # Create lead object
        lead_dict = lead.model_dump()
        lead_dict["id"] = str(uuid.uuid4())
        lead_dict["created_at"] = datetime.now(timezone.utc)
        lead_dict["updated_at"] = datetime.now(timezone.utc)
        lead_dict["status"] = "new"
        lead_dict["crm_synced"] = False
        
        # Add metadata
        lead_dict["ip_address"] = request.client.host
        lead_dict["user_agent"] = request.headers.get("user-agent", "")
        
        # Insert into database
        await db.partner_leads.insert_one(lead_dict)
        
        return {
            "success": True,
            "message": "Thank you for your interest! We'll reach out within 24-48 hours.",
            "id": lead_dict["id"]
        }
    except Exception as e:
        print(f"[PARTNER LEAD CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/partner-leads", dependencies=[Depends(check_permissions("author"))])
async def get_partner_leads(
    partner_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all partner leads (admin only)
    Filter by partner_type and/or status
    """
    try:
        query = {}
        if partner_type:
            query["partner_type"] = partner_type
        if status:
            query["status"] = status
            
        leads = await db.partner_leads.find(query).sort("created_at", -1).to_list(None)
        return remove_ids(leads)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/partner-leads/{lead_id}", dependencies=[Depends(check_permissions("author"))])
async def get_partner_lead(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Get single partner lead by ID (admin only)"""
    try:
        lead = await db.partner_leads.find_one({"id": lead_id})
        if not lead:
            raise HTTPException(status_code=404, detail="Partner lead not found")
        return remove_id(lead)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================
# PAGE BUILDER API
# =====================================

@api_router.get("/page-builder/layout/{page_id}", dependencies=[Depends(check_permissions("author"))])
async def get_page_builder_layout(page_id: str, current_user: dict = Depends(get_current_user)):
    """Get page builder layout for a specific page"""
    try:
        layout = await db.page_builder_layouts.find_one({"page_id": page_id})
        if layout:
            return remove_id(layout)
        # Return empty layout if none exists
        return {
            "page_id": page_id,
            "layout_data": {"components": [], "settings": {}},
            "version": 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/page-builder/layout", dependencies=[Depends(check_permissions("author"))])
async def save_page_builder_layout(
    page_id: str,
    layout_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Save or update page builder layout"""
    try:
        existing = await db.page_builder_layouts.find_one({"page_id": page_id})
        
        if existing:
            # Update existing layout
            update_data = {
                "layout_data": layout_data,
                "updated_at": datetime.now(timezone.utc),
                "last_edited_by": current_user.get("id"),
                "version": existing.get("version", 1) + 1
            }
            await db.page_builder_layouts.update_one(
                {"page_id": page_id},
                {"$set": update_data}
            )
            return {"message": "Layout updated successfully", "page_id": page_id}
        else:
            # Create new layout
            layout = {
                "id": str(uuid.uuid4()),
                "page_id": page_id,
                "layout_data": layout_data,
                "version": 1,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_by": current_user.get("id")
            }
            await db.page_builder_layouts.insert_one(layout)
            return {"message": "Layout created successfully", "page_id": page_id}
    except Exception as e:
        print(f"[PAGE BUILDER SAVE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/page-builder/render/{page_slug}")
async def get_page_layout_by_slug(page_slug: str):
    """
    Public endpoint: Get page builder layout by page slug for rendering
    Used by frontend to render visually-built pages
    """
    try:
        # First find the page by slug
        page = await db.pages.find_one({"slug": page_slug})
        if not page:
            return {"has_layout": False, "layout_data": None}
        
        # Then find the layout for that page
        layout = await db.page_builder_layouts.find_one({"page_id": page.get("id")})
        
        if layout:
            return {
                "has_layout": True,
                "layout_data": layout.get("layout_data", {"components": [], "settings": {}}),
                "page": remove_id(page)
            }
        
        return {"has_layout": False, "layout_data": None, "page": remove_id(page)}
    except Exception as e:
        print(f"[PAGE BUILDER RENDER ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/page-builder/save-changes", dependencies=[Depends(check_permissions("author"))])
async def save_page_changes(
    page_id: str,
    changes: list,
    current_user: dict = Depends(get_current_user)
):
    """
    Save visual editor changes (element modifications)
    Stores changes as structured data that can be applied on page load
    """
    try:
        existing = await db.page_builder_layouts.find_one({"page_id": page_id})
        
        if existing:
            # Update existing layout with changes
            update_data = {
                "changes": changes,
                "updated_at": datetime.now(timezone.utc),
                "last_edited_by": current_user.get("id"),
                "version": existing.get("version", 1) + 1
            }
            await db.page_builder_layouts.update_one(
                {"page_id": page_id},
                {"$set": update_data}
            )
            return {
                "message": "Changes saved successfully",
                "page_id": page_id,
                "changes_count": len(changes),
                "version": update_data["version"]
            }
        else:
            # Create new layout with changes
            layout = {
                "id": str(uuid.uuid4()),
                "page_id": page_id,
                "changes": changes,
                "layout_data": {"components": [], "settings": {}},
                "version": 1,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_by": current_user.get("id")
            }
            await db.page_builder_layouts.insert_one(layout)
            return {
                "message": "Changes saved successfully",
                "page_id": page_id,
                "changes_count": len(changes),
                "version": 1
            }
    except Exception as e:
        print(f"[PAGE BUILDER SAVE CHANGES ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================
# Video Management API (Education Hub)
# =====================================

@api_router.get("/test-video-endpoint")
async def test_video_endpoint():
    """Test endpoint to verify video routes are working"""
    return {"message": "Video endpoints are working", "status": "success"}

@api_router.get("/education-videos")
async def get_education_videos(
    category: Optional[str] = None,
    status: Optional[str] = None,
    featured: Optional[bool] = None
):
    """Get all education videos with optional filters"""
    try:
        query = {}
        if category:
            query["category"] = category
        if status:
            query["status"] = status
        if featured is not None:
            query["featured"] = featured
        
        videos = await db.education_videos.find(query).sort("order", 1).to_list(None)
        for video in videos:
            if "_id" in video:
                video["id"] = str(video.pop("_id"))
        
        return videos
    except Exception as e:
        print(f"[EDUCATION VIDEOS API ERROR] get_education_videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/education-videos/{video_id}")
async def get_education_video(video_id: str):
    """Get single education video by ID"""
    try:
        video = await db.education_videos.find_one({"id": video_id})
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        if "_id" in video:
            video["id"] = str(video.pop("_id"))
        return video
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/education-videos/slug/{slug}")
async def get_education_video_by_slug(slug: str):
    """Get education video by slug (for public pages) and increment views"""
    try:
        video = await db.education_videos.find_one({"url_slug": slug, "status": "published"})
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Get the video ID before popping _id
        video_id = video.get("id")
        if "_id" in video:
            video.pop("_id")
        
        # Increment view count in database
        await db.education_videos.update_one({"id": video_id}, {"$inc": {"views": 1}})
        
        # Fetch updated video with new view count
        updated_video = await db.education_videos.find_one({"id": video_id})
        if updated_video and "_id" in updated_video:
            updated_video.pop("_id")
        
        return updated_video if updated_video else video
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/education-videos")
async def create_education_video(video_data: dict, current_user: dict = Depends(get_current_user)):
    """Create new education video (admin only)"""
    try:
        video = EducationVideo(**video_data)
        video_dict = video.model_dump()
        
        # Ensure dates are ISO strings for MongoDB
        video_dict["created_at"] = video_dict["created_at"].isoformat() if isinstance(video_dict.get("created_at"), datetime) else datetime.now(timezone.utc).isoformat()
        video_dict["updated_at"] = video_dict["updated_at"].isoformat() if isinstance(video_dict.get("updated_at"), datetime) else datetime.now(timezone.utc).isoformat()
        video_dict["upload_date"] = video_dict["upload_date"].isoformat() if isinstance(video_dict.get("upload_date"), datetime) else datetime.now(timezone.utc).isoformat()
        
        await db.education_videos.insert_one(video_dict)
        return {"message": "Video created successfully", "id": video.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/education-videos/{video_id}")
async def update_education_video(video_id: str, video_data: dict, current_user: dict = Depends(get_current_user)):
    """Update education video (admin only)"""
    try:
        video_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        result = await db.education_videos.update_one({"id": video_id}, {"$set": video_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Fetch and return updated video
        updated_video = await db.education_videos.find_one({"id": video_id})
        if not updated_video:
            raise HTTPException(status_code=404, detail="Video not found after update")
        
        if "_id" in updated_video:
            updated_video.pop("_id")
        
        return {"message": "Video updated successfully", "video": updated_video}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/education-videos/{video_id}")
async def delete_education_video(video_id: str, current_user: dict = Depends(get_current_user)):
    """Delete education video (admin only)"""
    try:
        result = await db.education_videos.delete_one({"id": video_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {"message": "Video deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/education-videos/{video_id}/placements")
async def update_video_placements(video_id: str, placements: dict, current_user: dict = Depends(get_current_user)):
    """Update video placement data (for drag-and-drop positioning)"""
    try:
        result = await db.education_videos.update_one(
            {"id": video_id}, 
            {"$set": {"placements": placements.get("placements", []), "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {"message": "Video placements updated successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/debug-test")
async def debug_test():
    """Debug test endpoint"""
    return {"message": "Debug endpoint working"}


# ===== CREDITSAGE AI CHATBOT ENDPOINTS =====

# Initialize CreditSage bot
creditsage = CreditSageBot(db)

@api_router.post("/creditsage/index")
async def index_creditsage_content(current_user: dict = Depends(get_current_user)):
    """
    Index all website content for CreditSage bot
    Admin only - rebuilds the knowledge base
    """
    try:
        count = await creditsage.index_website_content()
        return {
            "message": "CreditSage knowledge base indexed successfully",
            "items_indexed": count
        }
    except Exception as e:
        print(f"[CREDITSAGE INDEX ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/creditsage/chat")
async def chat_with_creditsage(
    message: str,
    conversation_id: Optional[str] = None
):
    """
    Public endpoint - Chat with CreditSage AI assistant
    No authentication required
    """
    try:
        # Ensure knowledge base is loaded
        if not creditsage.knowledge_base:
            await creditsage.index_website_content()
        
        response = await creditsage.chat(message, conversation_id)
        return response
    except Exception as e:
        print(f"[CREDITSAGE CHAT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/creditsage/stats", dependencies=[Depends(check_permissions("admin"))])
async def get_creditsage_stats():
    """
    Get CreditSage statistics - Admin only
    """
    try:
        total_conversations = await db.creditsage_conversations.count_documents({})
        knowledge_items = len(creditsage.knowledge_base)
        
        return {
            "total_conversations": total_conversations,
            "knowledge_items": knowledge_items
        }
    except Exception as e:
        print(f"[CREDITSAGE STATS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== BANNERS & POPUPS ENDPOINTS =====

@api_router.get("/banners-popups")
async def get_all_banners_popups():
    """
    Public endpoint - Get all active banners and popups
    Returns only active items within their date range
    """
    try:
        current_time = datetime.now(timezone.utc)
        
        # Find active items within date range
        items = await db.banners_popups.find({
            "is_active": True,
            "$or": [
                {"start_date": None, "end_date": None},
                {"start_date": {"$lte": current_time}, "end_date": None},
                {"start_date": None, "end_date": {"$gte": current_time}},
                {"start_date": {"$lte": current_time}, "end_date": {"$gte": current_time}}
            ]
        }).to_list(length=None)
        
        return [remove_id(item) for item in items]
    except Exception as e:
        print(f"[BANNERS/POPUPS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/banners-popups", dependencies=[Depends(check_permissions("author"))])
async def get_all_banners_popups_admin():
    """Admin endpoint - Get all banners and popups"""
    try:
        items = await db.banners_popups.find({}).to_list(length=None)
        return [remove_id(item) for item in items]
    except Exception as e:
        print(f"[ADMIN BANNERS/POPUPS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/banners-popups/{item_id}", dependencies=[Depends(check_permissions("author"))])
async def get_banner_popup(item_id: str):
    """Get a single banner/popup by ID"""
    try:
        item = await db.banners_popups.find_one({"id": item_id})
        if not item:
            raise HTTPException(status_code=404, detail="Banner/Popup not found")
        return remove_id(item)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BANNER/POPUP GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/banners-popups", dependencies=[Depends(check_permissions("author"))])
async def create_banner_popup(
    item: BannerPopup,
    current_user: dict = Depends(get_current_user)
):
    """Create a new banner or popup"""
    try:
        item_dict = item.dict()
        item_dict["id"] = str(uuid.uuid4())
        item_dict["created_at"] = datetime.now(timezone.utc)
        item_dict["updated_at"] = datetime.now(timezone.utc)
        item_dict["created_by"] = current_user.get("id")
        
        await db.banners_popups.insert_one(item_dict)
        return remove_id(item_dict)
    except Exception as e:
        print(f"[BANNER/POPUP CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/banners-popups/{item_id}", dependencies=[Depends(check_permissions("author"))])
async def update_banner_popup(
    item_id: str,
    item: BannerPopup,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing banner or popup"""
    try:
        existing = await db.banners_popups.find_one({"id": item_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Banner/Popup not found")
        
        item_dict = item.dict(exclude_unset=True)
        item_dict["updated_at"] = datetime.now(timezone.utc)
        
        await db.banners_popups.update_one(
            {"id": item_id},
            {"$set": item_dict}
        )
        
        updated = await db.banners_popups.find_one({"id": item_id})
        return remove_id(updated)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BANNER/POPUP UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/banners-popups/{item_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_banner_popup(item_id: str):
    """Delete a banner or popup"""
    try:
        result = await db.banners_popups.delete_one({"id": item_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Banner/Popup not found")
        return {"message": "Banner/Popup deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BANNER/POPUP DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/banners-popups/{item_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_banner_popup(item_id: str):
    """Toggle active status of a banner or popup"""
    try:
        item = await db.banners_popups.find_one({"id": item_id})
        if not item:
            raise HTTPException(status_code=404, detail="Banner/Popup not found")
        
        new_status = not item.get("is_active", False)
        await db.banners_popups.update_one(
            {"id": item_id},
            {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        
        return {"message": f"Banner/Popup {'activated' if new_status else 'deactivated'}", "is_active": new_status}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BANNER/POPUP TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# LAWSUIT CONFIGURATION ENDPOINTS
# ==============================================================

@api_router.get("/admin/lawsuit-violations", dependencies=[Depends(check_permissions("author"))])
async def get_lawsuit_violations():
    """Get all lawsuit violations"""
    try:
        violations = await db.lawsuit_violations.find({"is_active": True}, {"_id": 0}).sort("name", 1).to_list(length=None)
        return violations
    except Exception as e:
        print(f"[LAWSUIT VIOLATIONS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/lawsuit-violations", dependencies=[Depends(check_permissions("author"))])
async def create_lawsuit_violation(violation: dict):
    """Create a new lawsuit violation"""
    try:
        violation_data = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            **violation
        }
        await db.lawsuit_violations.insert_one(violation_data)
        return {k: v for k, v in violation_data.items() if k != '_id'}
    except Exception as e:
        print(f"[LAWSUIT VIOLATION CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/lawsuit-violations/{violation_id}", dependencies=[Depends(check_permissions("author"))])
async def update_lawsuit_violation(violation_id: str, violation: dict):
    """Update a lawsuit violation"""
    try:
        update_data = {k: v for k, v in violation.items() if k not in ['id', 'created_at']}
        result = await db.lawsuit_violations.update_one(
            {"id": violation_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Violation not found")
        return {"message": "Violation updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT VIOLATION UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/lawsuit-violations/{violation_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_lawsuit_violation(violation_id: str):
    """Delete a lawsuit violation"""
    try:
        result = await db.lawsuit_violations.delete_one({"id": violation_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Violation not found")
        return {"message": "Violation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT VIOLATION DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/admin/lawsuit-violations/{violation_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_lawsuit_violation(violation_id: str):
    """Toggle lawsuit violation active status"""
    try:
        violation = await db.lawsuit_violations.find_one({"id": violation_id})
        if not violation:
            raise HTTPException(status_code=404, detail="Violation not found")
        new_status = not violation.get("is_active", True)
        await db.lawsuit_violations.update_one(
            {"id": violation_id},
            {"$set": {"is_active": new_status}}
        )
        return {"message": f"Violation {'activated' if new_status else 'deactivated'} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT VIOLATION TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/lawsuit-outcome-stages", dependencies=[Depends(check_permissions("author"))])
async def get_lawsuit_outcome_stages():
    """Get all lawsuit outcome stages"""
    try:
        stages = await db.lawsuit_outcome_stages.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return stages
    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/lawsuit-outcome-stages", dependencies=[Depends(check_permissions("author"))])
async def create_lawsuit_outcome_stage(stage: dict):
    """Create a new lawsuit outcome stage"""
    try:
        stage_data = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            **stage
        }
        await db.lawsuit_outcome_stages.insert_one(stage_data)
        return {k: v for k, v in stage_data.items() if k != '_id'}
    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/lawsuit-outcome-stages/{stage_id}", dependencies=[Depends(check_permissions("author"))])
async def update_lawsuit_outcome_stage(stage_id: str, stage: dict):
    """Update a lawsuit outcome stage"""
    try:
        update_data = {k: v for k, v in stage.items() if k not in ['id', 'created_at']}
        result = await db.lawsuit_outcome_stages.update_one(
            {"id": stage_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Stage not found")
        return {"message": "Stage updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/lawsuit-outcome-stages/{stage_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_lawsuit_outcome_stage(stage_id: str):
    """Delete a lawsuit outcome stage"""
    try:
        result = await db.lawsuit_outcome_stages.delete_one({"id": stage_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Stage not found")
        return {"message": "Stage deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/admin/lawsuit-outcome-stages/{stage_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_lawsuit_outcome_stage(stage_id: str):
    """Toggle lawsuit outcome stage active status"""
    try:
        stage = await db.lawsuit_outcome_stages.find_one({"id": stage_id})
        if not stage:
            raise HTTPException(status_code=404, detail="Stage not found")
        new_status = not stage.get("is_active", True)
        await db.lawsuit_outcome_stages.update_one(
            {"id": stage_id},
            {"$set": {"is_active": new_status}}
        )
        return {"message": f"Stage {'activated' if new_status else 'deactivated'} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGE TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/lawsuit-categories", dependencies=[Depends(check_permissions("author"))])
async def get_lawsuit_categories():
    """Get all lawsuit categories"""
    try:
        categories = await db.lawsuit_category_options.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return categories
    except Exception as e:
        print(f"[LAWSUIT CATEGORIES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/lawsuit-categories", dependencies=[Depends(check_permissions("author"))])
async def create_lawsuit_category(category: dict):
    """Create a new lawsuit category"""
    try:
        category_data = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            **category
        }
        await db.lawsuit_category_options.insert_one(category_data)
        return {k: v for k, v in category_data.items() if k != '_id'}
    except Exception as e:
        print(f"[LAWSUIT CATEGORY CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/lawsuit-categories/{category_id}", dependencies=[Depends(check_permissions("author"))])
async def update_lawsuit_category(category_id: str, category: dict):
    """Update a lawsuit category"""
    try:
        update_data = {k: v for k, v in category.items() if k not in ['id', 'created_at']}
        result = await db.lawsuit_category_options.update_one(
            {"id": category_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Category not found")
        return {"message": "Category updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT CATEGORY UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/lawsuit-categories/{category_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_lawsuit_category(category_id: str):
    """Delete a lawsuit category"""
    try:
        result = await db.lawsuit_category_options.delete_one({"id": category_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Category not found")
        return {"message": "Category deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT CATEGORY DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/admin/lawsuit-categories/{category_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_lawsuit_category(category_id: str):
    """Toggle lawsuit category active status"""
    try:
        category = await db.lawsuit_category_options.find_one({"id": category_id})
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        new_status = not category.get("is_active", True)
        await db.lawsuit_category_options.update_one(
            {"id": category_id},
            {"$set": {"is_active": new_status}}
        )
        return {"message": f"Category {'activated' if new_status else 'deactivated'} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT CATEGORY TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/lawsuit-types", dependencies=[Depends(check_permissions("author"))])
async def get_lawsuit_types():
    """Get all lawsuit types"""
    try:
        types = await db.lawsuit_type_options.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return types
    except Exception as e:
        print(f"[LAWSUIT TYPES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/lawsuit-types", dependencies=[Depends(check_permissions("author"))])
async def create_lawsuit_type(lawsuit_type: dict):
    """Create a new lawsuit type"""
    try:
        type_data = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            **lawsuit_type
        }
        await db.lawsuit_type_options.insert_one(type_data)
        return {k: v for k, v in type_data.items() if k != '_id'}
    except Exception as e:
        print(f"[LAWSUIT TYPE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/lawsuit-types/{type_id}", dependencies=[Depends(check_permissions("author"))])
async def update_lawsuit_type(type_id: str, lawsuit_type: dict):
    """Update a lawsuit type"""
    try:
        update_data = {k: v for k, v in lawsuit_type.items() if k not in ['id', 'created_at']}
        result = await db.lawsuit_type_options.update_one(
            {"id": type_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Type not found")
        return {"message": "Type updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT TYPE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/lawsuit-types/{type_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_lawsuit_type(type_id: str):
    """Delete a lawsuit type"""
    try:
        result = await db.lawsuit_type_options.delete_one({"id": type_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Type not found")
        return {"message": "Type deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT TYPE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/admin/lawsuit-types/{type_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_lawsuit_type(type_id: str):
    """Toggle lawsuit type active status"""
    try:
        lawsuit_type = await db.lawsuit_type_options.find_one({"id": type_id})
        if not lawsuit_type:
            raise HTTPException(status_code=404, detail="Type not found")
        new_status = not lawsuit_type.get("is_active", True)
        await db.lawsuit_type_options.update_one(
            {"id": type_id},
            {"$set": {"is_active": new_status}}
        )
        return {"message": f"Type {'activated' if new_status else 'deactivated'} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT TYPE TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/party-roles", dependencies=[Depends(check_permissions("author"))])
async def get_party_roles():
    """Get all party roles"""
    try:
        roles = await db.party_roles.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return roles
    except Exception as e:
        print(f"[PARTY ROLES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/party-roles", dependencies=[Depends(check_permissions("author"))])
async def create_party_role(role: dict):
    """Create a new party role"""
    try:
        role_data = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            **role
        }
        await db.party_roles.insert_one(role_data)
        # Return clean data without MongoDB ObjectId
        return {k: v for k, v in role_data.items() if k != '_id'}
    except Exception as e:
        print(f"[PARTY ROLE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/party-roles/{role_id}", dependencies=[Depends(check_permissions("author"))])
async def update_party_role(role_id: str, role: dict):
    """Update a party role"""
    try:
        update_data = {k: v for k, v in role.items() if k not in ['id', 'created_at']}
        result = await db.party_roles.update_one(
            {"id": role_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Party role not found")
        return {"message": "Party role updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTY ROLE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/party-roles/{role_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_party_role(role_id: str):
    """Delete a party role"""
    try:
        result = await db.party_roles.delete_one({"id": role_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Party role not found")
        return {"message": "Party role deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTY ROLE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/admin/party-roles/{role_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_party_role(role_id: str):
    """Toggle party role active status"""
    try:
        role = await db.party_roles.find_one({"id": role_id})
        if not role:
            raise HTTPException(status_code=404, detail="Party role not found")
        new_status = not role.get("is_active", True)
        await db.party_roles.update_one(
            {"id": role_id},
            {"$set": {"is_active": new_status}}
        )
        return {"message": f"Party role {'activated' if new_status else 'deactivated'} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTY ROLE TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ==============================================================
# LAWSUIT MANAGEMENT  
# ==============================================================

def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title"""
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


@api_router.get("/lawsuits/reviews")
async def get_lawsuit_reviews():
    """Public endpoint - Get reviews for lawsuits page"""
    try:
        reviews = await db.reviews.find({"display_on_lawsuits_page": True}, {"_id": 0}).limit(5).to_list(length=5)
        return reviews
    except Exception as e:
        print(f"[LAWSUIT REVIEWS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/lawsuits")
async def get_lawsuits_public():
    """Public endpoint - Get all active lawsuits"""
    try:
        lawsuits = await db.lawsuits.find({"is_active": True}, {"_id": 0}).sort("date_filed", -1).to_list(length=None)
        return lawsuits
    except Exception as e:
        print(f"[LAWSUITS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/lawsuits/{slug}")
async def get_lawsuit_by_slug(slug: str):
    """Public endpoint - Get lawsuit by slug"""
    try:
        lawsuit = await db.lawsuits.find_one({"slug": slug, "is_active": True}, {"_id": 0})
        if not lawsuit:
            raise HTTPException(status_code=404, detail="Lawsuit not found")
        return lawsuit
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PUBLIC LAWSUIT METADATA ENDPOINTS ====================
@api_router.get("/lawsuit-metadata/party-roles")
async def get_party_roles_public():
    """Public endpoint - Get all party roles for display"""
    try:
        roles = await db.party_roles.find({"is_active": True}, {"_id": 0}).sort("name", 1).to_list(length=None)
        return roles
    except Exception as e:
        print(f"[PARTY ROLES PUBLIC GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/lawsuit-metadata/categories")
async def get_lawsuit_categories_public():
    """Public endpoint - Get all lawsuit categories for display"""
    try:
        categories = await db.lawsuit_category_options.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return categories
    except Exception as e:
        print(f"[LAWSUIT CATEGORIES PUBLIC GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/lawsuit-metadata/types")
async def get_lawsuit_types_public():
    """Public endpoint - Get all lawsuit types for display"""
    try:
        types = await db.lawsuit_type_options.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return types
    except Exception as e:
        print(f"[LAWSUIT TYPES PUBLIC GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/lawsuit-metadata/violations")
async def get_lawsuit_violations_public():
    """Public endpoint - Get all lawsuit violations for display"""
    try:
        violations = await db.lawsuit_violations.find({"is_active": True}, {"_id": 0}).sort("name", 1).to_list(length=None)
        return violations
    except Exception as e:
        print(f"[LAWSUIT VIOLATIONS PUBLIC GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/lawsuit-metadata/outcome-stages")
async def get_lawsuit_outcome_stages_public():
    """Public endpoint - Get all outcome stages for display"""
    try:
        stages = await db.lawsuit_outcome_stages.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return stages
    except Exception as e:
        print(f"[LAWSUIT OUTCOME STAGES PUBLIC GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))



@api_router.get("/admin/lawsuits", dependencies=[Depends(check_permissions("author"))])
async def get_all_lawsuits_admin():
    """Admin endpoint - Get all lawsuits"""
    try:
        lawsuits = await db.lawsuits.find({}, {"_id": 0}).sort("date_filed", -1).to_list(length=None)
        return lawsuits
    except Exception as e:
        print(f"[LAWSUITS ADMIN GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/lawsuits/{lawsuit_id}", dependencies=[Depends(check_permissions("author"))])
async def get_lawsuit_by_id(lawsuit_id: str):
    """Admin endpoint - Get lawsuit by ID"""
    try:
        lawsuit = await db.lawsuits.find_one({"id": lawsuit_id}, {"_id": 0})
        if not lawsuit:
            raise HTTPException(status_code=404, detail="Lawsuit not found")
        return lawsuit
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/lawsuits", dependencies=[Depends(check_permissions("author"))])
async def create_lawsuit(
    lawsuit: LawsuitCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new lawsuit"""
    try:
        lawsuit_dict = lawsuit.dict()
        lawsuit_dict["id"] = str(uuid.uuid4())
        lawsuit_dict["slug"] = generate_slug(lawsuit.title)
        lawsuit_dict["created_at"] = datetime.now(timezone.utc)
        lawsuit_dict["updated_at"] = datetime.now(timezone.utc)
        lawsuit_dict["created_by"] = current_user.get("id")
        
        await db.lawsuits.insert_one(lawsuit_dict)
        return remove_id(lawsuit_dict)
    except Exception as e:
        print(f"[LAWSUIT CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/lawsuits/{lawsuit_id}", dependencies=[Depends(check_permissions("author"))])
async def update_lawsuit(
    lawsuit_id: str,
    lawsuit: LawsuitUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing lawsuit"""
    try:
        existing = await db.lawsuits.find_one({"id": lawsuit_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Lawsuit not found")
        
        lawsuit_dict = lawsuit.dict(exclude_unset=True)
        if lawsuit.title:
            lawsuit_dict["slug"] = generate_slug(lawsuit.title)
        lawsuit_dict["updated_at"] = datetime.now(timezone.utc)
        
        await db.lawsuits.update_one(
            {"id": lawsuit_id},
            {"$set": lawsuit_dict}
        )
        
        updated = await db.lawsuits.find_one({"id": lawsuit_id})
        return remove_id(updated)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/lawsuits/{lawsuit_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_lawsuit(lawsuit_id: str):
    """Delete a lawsuit"""
    try:
        result = await db.lawsuits.delete_one({"id": lawsuit_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Lawsuit not found")
        return {"message": "Lawsuit deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/lawsuits/{lawsuit_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_lawsuit_active(lawsuit_id: str):
    """Toggle lawsuit active status"""
    try:
        lawsuit = await db.lawsuits.find_one({"id": lawsuit_id})
        if not lawsuit:
            raise HTTPException(status_code=404, detail="Lawsuit not found")
        
        new_status = not lawsuit.get("is_active", False)
        await db.lawsuits.update_one(
            {"id": lawsuit_id},
            {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        
        return {"message": f"Lawsuit {'activated' if new_status else 'deactivated'}", "is_active": new_status}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LAWSUIT TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# PRESS RELEASE MANAGEMENT
# ==============================================================

@api_router.get("/press-releases")
async def get_press_releases_public():
    """Public endpoint - Get all published press releases"""
    try:
        press_releases = await db.press_releases.find({"is_published": True}, {"_id": 0}).sort("publish_date", -1).to_list(length=None)
        return press_releases
    except Exception as e:
        print(f"[PRESS RELEASES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/press-releases/rss")
async def get_press_releases_rss():
    """Public RSS feed for press releases (for Google News)"""
    try:
        press_releases = await db.press_releases.find(
            {"is_published": True}, 
            {"_id": 0}
        ).sort("publish_date", -1).limit(50).to_list(length=50)
        
        # Build RSS feed
        rss_items = []
        for pr in press_releases:
            pub_date = pr.get('publish_date', datetime.now(timezone.utc))
            if isinstance(pub_date, str):
                pub_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            
            # Format date for RSS (RFC 822)
            pub_date_rfc = pub_date.strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Clean description (strip HTML tags for RSS)
            import re
            description = pr.get('excerpt', '')
            if not description:
                description = re.sub('<.*?>', '', pr.get('content', ''))[:300] + '...'
            
            item = f"""
            <item>
                <title>{pr.get('title', '')}</title>
                <link>https://credlocity.com/press-releases/{pr.get('slug', pr.get('id'))}</link>
                <guid isPermaLink="true">https://credlocity.com/press-releases/{pr.get('slug', pr.get('id'))}</guid>
                <description><![CDATA[{description}]]></description>
                <pubDate>{pub_date_rfc}</pubDate>
                <author>press@credlocity.com (Credlocity)</author>
            </item>
            """
            rss_items.append(item)
        
        rss_feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>Credlocity Press Releases</title>
        <link>https://credlocity.com/press-releases</link>
        <description>Latest press releases from Credlocity - credit repair industry news, lawsuits, and company updates</description>
        <language>en-us</language>
        <copyright>Copyright {datetime.now().year} Credlocity Business Group LLC</copyright>
        <atom:link href="https://credlocity.com/api/press-releases/rss" rel="self" type="application/rss+xml" />
        {''.join(rss_items)}
    </channel>
</rss>"""
        
        return Response(content=rss_feed, media_type="application/rss+xml")
    except Exception as e:
        print(f"[RSS FEED ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/press-releases/{slug}")
async def get_press_release_by_slug(slug: str):
    """Public endpoint - Get press release by slug"""
    try:
        press_release = await db.press_releases.find_one({"slug": slug, "is_published": True}, {"_id": 0})
        if not press_release:
            raise HTTPException(status_code=404, detail="Press release not found")
        return press_release
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PRESS RELEASE GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/press-releases", dependencies=[Depends(check_permissions("author"))])
async def get_all_press_releases_admin():
    """Admin endpoint - Get all press releases"""
    try:
        press_releases = await db.press_releases.find({}, {"_id": 0}).sort("publish_date", -1).to_list(length=None)
        return press_releases
    except Exception as e:
        print(f"[PRESS RELEASES ADMIN GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/press-releases/{release_id}", dependencies=[Depends(check_permissions("author"))])
async def get_press_release_by_id(release_id: str):
    """Admin endpoint - Get press release by ID"""
    try:
        press_release = await db.press_releases.find_one({"id": release_id}, {"_id": 0})
        if not press_release:
            raise HTTPException(status_code=404, detail="Press release not found")
        return press_release
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PRESS RELEASE GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# OUTSOURCING MANAGEMENT ENDPOINTS
# ==============================================================

# ==================== CRM PLATFORMS ====================
@api_router.get("/admin/outsource/crm-platforms", dependencies=[Depends(check_permissions("author"))])
async def get_crm_platforms():
    """Get all CRM platforms"""
    try:
        platforms = await db.crm_platforms.find({}, {"_id": 0}).sort("name", 1).to_list(None)
        return platforms
    except Exception as e:
        print(f"[CRM PLATFORMS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/outsource/crm-platforms", dependencies=[Depends(check_permissions("author"))])
async def create_crm_platform(platform: dict):
    """Create a new CRM platform"""
    try:
        platform_data = {
            "id": str(uuid.uuid4()),
            "name": platform.get("name"),
            "description": platform.get("description"),
            "website": platform.get("website"),
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        }
        await db.crm_platforms.insert_one(platform_data)
        return {k: v for k, v in platform_data.items() if k != '_id'}
    except Exception as e:
        print(f"[CRM PLATFORM CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== OUTSOURCE INQUIRIES ====================
@api_router.post("/api/outsource/inquiries")
async def submit_outsource_inquiry(inquiry: dict):
    """Public endpoint - Submit outsource partner inquiry"""
    try:
        inquiry_data = {
            "id": str(uuid.uuid4()),
            "company_name": inquiry.get("company_name"),
            "contact_first_name": inquiry.get("contact_first_name"),
            "contact_last_name": inquiry.get("contact_last_name"),
            "contact_email": inquiry.get("contact_email"),
            "contact_phone": inquiry.get("contact_phone"),
            "position": inquiry.get("position"),
            "current_platform": inquiry.get("current_platform"),
            "status": "pending",
            "notes": inquiry.get("notes", ""),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        await db.outsource_partner_inquiries.insert_one(inquiry_data)
        return {"message": "Inquiry submitted successfully", "id": inquiry_data["id"]}
    except Exception as e:
        print(f"[OUTSOURCE INQUIRY CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/outsource/inquiries", dependencies=[Depends(check_permissions("author"))])
async def get_outsource_inquiries():
    """Get all outsource partner inquiries"""
    try:
        inquiries = await db.outsource_partner_inquiries.find({}, {"_id": 0}).sort("created_at", -1).to_list(None)
        return inquiries
    except Exception as e:
        print(f"[OUTSOURCE INQUIRIES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/admin/outsource/inquiries/{inquiry_id}/status", dependencies=[Depends(check_permissions("author"))])
async def update_inquiry_status(inquiry_id: str, status_data: dict, current_user: dict = Depends(get_current_user)):
    """Update inquiry status (pending, approved, disapproved, pending_review)"""
    try:
        status = status_data.get("status")
        notes = status_data.get("notes", "")
        
        result = await db.outsource_partner_inquiries.update_one(
            {"id": inquiry_id},
            {"$set": {
                "status": status,
                "notes": notes,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Inquiry not found")
        
        # If approved, optionally create partner record
        if status == "approved" and status_data.get("create_partner", False):
            inquiry = await db.outsource_partner_inquiries.find_one({"id": inquiry_id}, {"_id": 0})
            if inquiry:
                partner_data = {
                    "id": str(uuid.uuid4()),
                    "inquiry_id": inquiry_id,
                    "company_name": inquiry["company_name"],
                    "contact_first_name": inquiry["contact_first_name"],
                    "contact_last_name": inquiry["contact_last_name"],
                    "contact_email": inquiry["contact_email"],
                    "contact_phone": inquiry["contact_phone"],
                    "position": inquiry["position"],
                    "status": "approved",
                    "is_active": True,
                    "approved_at": datetime.now(timezone.utc),
                    "approved_by": current_user["id"],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                await db.outsource_partners.insert_one(partner_data)
                return {"message": "Inquiry approved and partner created", "partner_id": partner_data["id"]}
        
        return {"message": "Inquiry status updated"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INQUIRY STATUS UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== OUTSOURCE PARTNERS ====================
@api_router.get("/admin/outsource/partners", dependencies=[Depends(check_permissions("author"))])
async def get_outsource_partners():
    """Get all outsource partners"""
    try:
        partners = await db.outsource_partners.find({}, {"_id": 0}).sort("company_name", 1).to_list(None)
        return partners
    except Exception as e:
        print(f"[OUTSOURCE PARTNERS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/outsource/partners/{partner_id}", dependencies=[Depends(check_permissions("author"))])
async def get_outsource_partner(partner_id: str):
    """Get a specific outsource partner"""
    try:
        partner = await db.outsource_partners.find_one({"id": partner_id}, {"_id": 0})
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        return partner
    except HTTPException:
        raise
    except Exception as e:
        print(f"[OUTSOURCE PARTNER GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/outsource/partners", dependencies=[Depends(check_permissions("author"))])
async def create_outsource_partner(partner: dict, current_user: dict = Depends(get_current_user)):
    """Create a new outsource partner"""
    try:
        partner_data = {
            "id": str(uuid.uuid4()),
            "inquiry_id": partner.get("inquiry_id"),
            "company_name": partner.get("company_name"),
            "contact_first_name": partner.get("contact_first_name"),
            "contact_last_name": partner.get("contact_last_name"),
            "contact_email": partner.get("contact_email"),
            "contact_phone": partner.get("contact_phone"),
            "position": partner.get("position"),
            "crm_platform_id": partner.get("crm_platform_id"),
            "crm_username": partner.get("crm_username"),
            "crm_password": partner.get("crm_password"),
            "status": "approved",
            "billing_email": partner.get("billing_email", partner.get("contact_email")),
            "payment_terms": partner.get("payment_terms", "Net 30"),
            "is_active": True,
            "approved_at": datetime.now(timezone.utc),
            "approved_by": current_user["id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        await db.outsource_partners.insert_one(partner_data)
        return {k: v for k, v in partner_data.items() if k != '_id'}
    except Exception as e:
        print(f"[OUTSOURCE PARTNER CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/outsource/partners/{partner_id}", dependencies=[Depends(check_permissions("author"))])
async def update_outsource_partner(
    partner_id: str, 
    partner_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update an outsource partner with pricing history tracking"""
    try:
        # Get current partner data first
        existing_partner = await db.outsource_partners.find_one({"id": partner_id}, {"_id": 0})
        if not existing_partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        update_data = {k: v for k, v in partner_data.items() if k not in ['id', 'created_at', 'approved_by', 'approved_at', 'pricing_history']}
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        # Check if pricing or client count changed - add to history
        old_cost = existing_partner.get("cost_per_consumer", 0)
        old_count = existing_partner.get("active_client_count", 0)
        new_cost = partner_data.get("cost_per_consumer", old_cost)
        new_count = partner_data.get("active_client_count", old_count)
        
        if (new_cost != old_cost or new_count != old_count) and (old_cost > 0 or old_count > 0):
            # Add current pricing to history before updating
            history_entry = {
                "date": datetime.now(timezone.utc).isoformat(),
                "cost_per_consumer": old_cost,
                "active_client_count": old_count,
                "changed_by": current_user.get("id"),
                "notes": partner_data.get("pricing_change_notes", f"Changed from ${old_cost}/consumer, {old_count} clients")
            }
            
            # Append to pricing history
            await db.outsource_partners.update_one(
                {"id": partner_id},
                {"$push": {"pricing_history": history_entry}}
            )
        
        result = await db.outsource_partners.update_one(
            {"id": partner_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        # Return updated partner
        updated_partner = await db.outsource_partners.find_one({"id": partner_id}, {"_id": 0})
        return updated_partner
    except HTTPException:
        raise
    except Exception as e:
        print(f"[OUTSOURCE PARTNER UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get partner billing info for invoice auto-population
@api_router.get("/admin/outsource/partners/{partner_id}/billing-info", dependencies=[Depends(check_permissions("author"))])
async def get_partner_billing_info(partner_id: str):
    """Get partner's current billing info for auto-populating invoices, including active credits/discounts"""
    try:
        partner = await db.outsource_partners.find_one({"id": partner_id}, {"_id": 0})
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        base_amount = partner.get("cost_per_consumer", 0) * partner.get("active_client_count", 0)
        
        # Get active credits count
        active_credits = await db.outsource_partner_credits.count_documents({
            "partner_id": partner_id,
            "status": "active"
        })
        
        # Get active discounts count
        active_discounts = await db.outsource_partner_discounts.count_documents({
            "partner_id": partner_id,
            "status": "active"
        })
        
        # Get summary of active credits
        credits_summary = []
        credits = await db.outsource_partner_credits.find({
            "partner_id": partner_id,
            "status": "active"
        }, {"_id": 0}).to_list(None)
        for c in credits:
            credits_summary.append({
                "type": c.get("credit_type"),
                "description": c.get("description"),
                "dollar_amount": c.get("dollar_amount"),
                "months": c.get("months")
            })
        
        # Get summary of active discounts
        discounts_summary = []
        discounts = await db.outsource_partner_discounts.find({
            "partner_id": partner_id,
            "status": "active"
        }, {"_id": 0}).to_list(None)
        for d in discounts:
            discounts_summary.append({
                "type": d.get("discount_type"),
                "description": d.get("description"),
                "percentage": d.get("percentage"),
                "dollar_amount": d.get("dollar_amount"),
                "per_file_amount": d.get("per_file_amount")
            })
        
        return {
            "partner_id": partner_id,
            "company_name": partner.get("company_name", ""),
            "cost_per_consumer": partner.get("cost_per_consumer", 0),
            "active_client_count": partner.get("active_client_count", 0),
            "billing_cycle": partner.get("billing_cycle", "monthly"),
            "billing_email": partner.get("billing_email", partner.get("contact_email", "")),
            "base_amount": base_amount,
            "total_amount": base_amount,  # Frontend will calculate final after adjustments
            "active_credits_count": active_credits,
            "active_discounts_count": active_discounts,
            "credits_summary": credits_summary,
            "discounts_summary": discounts_summary,
            "has_billing_adjustments": active_credits > 0 or active_discounts > 0
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER BILLING INFO ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WORK LOGS ====================
@api_router.get("/admin/outsource/work-logs", dependencies=[Depends(check_permissions("author"))])
async def get_work_logs(partner_id: Optional[str] = None):
    """Get work logs, optionally filtered by partner"""
    try:
        query = {"partner_id": partner_id} if partner_id else {}
        logs = await db.outsource_work_logs.find(query, {"_id": 0}).sort("work_date", -1).to_list(None)
        return logs
    except Exception as e:
        print(f"[WORK LOGS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/outsource/work-logs", dependencies=[Depends(check_permissions("author"))])
async def create_work_log(log: dict, current_user: dict = Depends(get_current_user)):
    """Create a new work log"""
    try:
        log_data = {
            "id": str(uuid.uuid4()),
            "partner_id": log.get("partner_id"),
            "work_date": log.get("work_date", datetime.now(timezone.utc).isoformat()),
            "description": log.get("description", ""),
            "disputes_processed": log.get("disputes_processed", 0),
            "letters_sent": log.get("letters_sent", 0),
            "hours_worked": log.get("hours_worked", 0),
            "notes": log.get("notes", ""),
            "performed_by": current_user["id"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_work_logs.insert_one(log_data)
        return {k: v for k, v in log_data.items() if k != '_id'}
    except Exception as e:
        print(f"[WORK LOG CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== INVOICES ====================
@api_router.get("/admin/outsource/invoices", dependencies=[Depends(check_permissions("author"))])
async def get_outsource_invoices(partner_id: Optional[str] = None):
    """Get invoices, optionally filtered by partner"""
    try:
        query = {"partner_id": partner_id} if partner_id else {}
        invoices = await db.outsource_invoices.find(query, {"_id": 0}).sort("invoice_date", -1).to_list(None)
        return invoices
    except Exception as e:
        print(f"[INVOICES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/outsource/invoices", dependencies=[Depends(check_permissions("author"))])
async def create_outsource_invoice(invoice: dict, current_user: dict = Depends(get_current_user)):
    """Create a new invoice with credits, discounts, and coupons applied"""
    try:
        partner_id = invoice.get("partner_id")
        
        # Get items from either 'items' or 'line_items' (frontend sends 'items')
        items = invoice.get("items", invoice.get("line_items", []))
        
        # Calculate subtotal from items (quantity * unit_price per item)
        subtotal = sum((item.get("quantity", 0) * item.get("unit_price", 0)) for item in items)
        
        # If subtotal was passed directly, use that as a fallback
        if subtotal == 0 and invoice.get("total_amount"):
            subtotal = invoice.get("total_amount", 0)
        
        # Initialize billing adjustments tracking
        adjustments = []
        total_discount = 0
        total_credit_applied = 0
        
        # ============ FETCH & APPLY PARTNER DISCOUNTS ============
        if partner_id:
            now = datetime.now(timezone.utc)
            
            # Get active discounts for this partner
            active_discounts = await db.outsource_partner_discounts.find({
                "partner_id": partner_id,
                "status": "active"
            }, {"_id": 0}).to_list(None)
            
            for discount in active_discounts:
                # Check if discount is within valid date range
                start_date = discount.get("start_date")
                end_date = discount.get("end_date")
                
                if start_date:
                    if isinstance(start_date, str):
                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    if now < start_date:
                        continue
                
                if end_date:
                    if isinstance(end_date, str):
                        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if now > end_date:
                        continue
                
                discount_type = discount.get("discount_type")
                discount_amount = 0
                
                if discount_type == "percentage" and discount.get("percentage"):
                    discount_amount = subtotal * (discount.get("percentage") / 100)
                elif discount_type == "dollar_amount" and discount.get("dollar_amount"):
                    discount_amount = discount.get("dollar_amount")
                elif discount_type == "per_file" and discount.get("per_file_amount"):
                    # Calculate based on total files/items processed
                    total_quantity = sum(item.get("quantity", 0) for item in items)
                    discount_amount = total_quantity * discount.get("per_file_amount")
                
                if discount_amount > 0:
                    total_discount += discount_amount
                    adjustments.append({
                        "type": "discount",
                        "id": discount.get("id"),
                        "description": discount.get("description", f"{discount_type} discount"),
                        "amount": -discount_amount
                    })
            
            # ============ FETCH & APPLY PARTNER CREDITS ============
            active_credits = await db.outsource_partner_credits.find({
                "partner_id": partner_id,
                "status": "active"
            }, {"_id": 0}).to_list(None)
            
            for credit in active_credits:
                # Check if credit is within valid date range
                valid_from = credit.get("valid_from")
                valid_until = credit.get("valid_until")
                
                if valid_from:
                    if isinstance(valid_from, str):
                        valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                    if now < valid_from:
                        continue
                
                if valid_until:
                    if isinstance(valid_until, str):
                        valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                    if now > valid_until:
                        continue
                
                credit_type = credit.get("credit_type")
                credit_amount = 0
                
                if credit_type == "dollar_credit" and credit.get("dollar_amount"):
                    credit_amount = credit.get("dollar_amount")
                elif credit_type == "month_credit":
                    # Month credit means this invoice is free
                    credit_amount = subtotal - total_discount
                elif credit_type == "freemium":
                    # Freemium also covers the full amount
                    credit_amount = subtotal - total_discount
                
                if credit_amount > 0:
                    total_credit_applied += credit_amount
                    adjustments.append({
                        "type": "credit",
                        "id": credit.get("id"),
                        "description": credit.get("description", f"{credit_type}"),
                        "amount": -credit_amount
                    })
                    
                    # Mark one-time credits as used
                    if credit_type in ["dollar_credit", "month_credit"]:
                        await db.outsource_partner_credits.update_one(
                            {"id": credit.get("id")},
                            {"$set": {
                                "status": "used",
                                "applied_to_invoice_id": str(uuid.uuid4()),  # Will update with actual invoice ID
                                "applied_at": now.isoformat()
                            }}
                        )
            
            # ============ APPLY COUPON IF PROVIDED ============
            coupon_code = invoice.get("coupon_code")
            if coupon_code:
                coupon = await db.outsource_coupons.find_one({
                    "code": coupon_code.upper(),
                    "status": "active"
                }, {"_id": 0})
                
                if coupon:
                    # Check if coupon is valid for this partner
                    applies_to = coupon.get("applies_to", "all")
                    specific_partners = coupon.get("specific_partner_ids", [])
                    
                    coupon_valid = (applies_to == "all") or (partner_id in specific_partners)
                    
                    # Check date validity
                    valid_from = coupon.get("valid_from")
                    valid_until = coupon.get("valid_until")
                    
                    if valid_from:
                        if isinstance(valid_from, str):
                            valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                        if now < valid_from:
                            coupon_valid = False
                    
                    if valid_until:
                        if isinstance(valid_until, str):
                            valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                        if now > valid_until:
                            coupon_valid = False
                    
                    # Check max uses
                    if coupon.get("max_uses") and coupon.get("times_used", 0) >= coupon.get("max_uses"):
                        coupon_valid = False
                    
                    if coupon_valid:
                        coupon_discount = 0
                        discount_type = coupon.get("discount_type")
                        discount_value = coupon.get("discount_value", 0)
                        
                        remaining_total = subtotal - total_discount - total_credit_applied
                        
                        if discount_type == "percentage":
                            coupon_discount = remaining_total * (discount_value / 100)
                        elif discount_type in ["dollar_amount", "dollar"]:
                            coupon_discount = min(discount_value, remaining_total)
                        elif discount_type == "per_file":
                            total_quantity = sum(item.get("quantity", 0) for item in items)
                            coupon_discount = min(total_quantity * discount_value, remaining_total)
                        elif discount_type == "free_months":
                            coupon_discount = remaining_total  # Full discount
                        
                        if coupon_discount > 0:
                            adjustments.append({
                                "type": "coupon",
                                "id": coupon.get("id"),
                                "code": coupon_code.upper(),
                                "description": coupon.get("name", f"Coupon: {coupon_code.upper()}"),
                                "amount": -coupon_discount
                            })
                            total_discount += coupon_discount
                            
                            # Increment coupon usage
                            await db.outsource_coupons.update_one(
                                {"id": coupon.get("id")},
                                {"$inc": {"times_used": 1}}
                            )
        
        # Calculate final total (ensure it doesn't go negative)
        final_total = max(0, subtotal - total_discount - total_credit_applied)
        
        # Use provided invoice number or generate one
        invoice_number = invoice.get("invoice_number")
        if not invoice_number:
            count = await db.outsource_invoices.count_documents({})
            invoice_number = f"INV-{datetime.now().year}-{str(count + 1).zfill(4)}"
        
        invoice_id = str(uuid.uuid4())
        
        invoice_data = {
            "id": invoice_id,
            "partner_id": partner_id,
            "invoice_number": invoice_number,
            "invoice_date": invoice.get("invoice_date", datetime.now(timezone.utc).isoformat()),
            "due_date": invoice.get("due_date"),
            "billing_period_start": invoice.get("billing_period_start"),
            "billing_period_end": invoice.get("billing_period_end"),
            "items": items,
            "subtotal": subtotal,
            "adjustments": adjustments,
            "total_discount": total_discount + total_credit_applied,
            "total_amount": final_total,
            "coupon_code": invoice.get("coupon_code"),
            "status": invoice.get("status", "draft"),
            "notes": invoice.get("notes"),
            "created_by": current_user["id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.outsource_invoices.insert_one(invoice_data)
        
        # Update credit records with actual invoice ID
        for adj in adjustments:
            if adj["type"] == "credit":
                await db.outsource_partner_credits.update_one(
                    {"id": adj["id"], "status": "used"},
                    {"$set": {"applied_to_invoice_id": invoice_id}}
                )
        
        return {k: v for k, v in invoice_data.items() if k != '_id'}
    except Exception as e:
        print(f"[INVOICE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/outsource/invoices/{invoice_id}", dependencies=[Depends(check_permissions("author"))])
async def get_outsource_invoice(invoice_id: str):
    """Get a single invoice by ID"""
    try:
        invoice = await db.outsource_invoices.find_one({"id": invoice_id}, {"_id": 0})
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return invoice
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INVOICE GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/outsource/invoices/{invoice_id}", dependencies=[Depends(check_permissions("author"))])
async def update_outsource_invoice(invoice_id: str, invoice: dict, current_user: dict = Depends(get_current_user)):
    """Update an invoice - recalculates billing adjustments if recalculate flag is set"""
    try:
        partner_id = invoice.get("partner_id")
        recalculate = invoice.get("recalculate_adjustments", False)
        
        # Get items and calculate subtotal
        items = invoice.get("items", invoice.get("line_items", []))
        subtotal = sum((item.get("quantity", 0) * item.get("unit_price", 0)) for item in items)
        
        if subtotal == 0 and invoice.get("total_amount"):
            subtotal = invoice.get("total_amount", 0)
        
        # Start with base update data
        update_data = {
            "partner_id": partner_id,
            "invoice_number": invoice.get("invoice_number"),
            "invoice_date": invoice.get("invoice_date"),
            "due_date": invoice.get("due_date"),
            "billing_period_start": invoice.get("billing_period_start"),
            "billing_period_end": invoice.get("billing_period_end"),
            "items": items,
            "subtotal": subtotal,
            "status": invoice.get("status"),
            "notes": invoice.get("notes"),
            "coupon_code": invoice.get("coupon_code"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # If recalculating adjustments or items changed significantly
        if recalculate and partner_id:
            adjustments = []
            total_discount = 0
            total_credit_applied = 0
            now = datetime.now(timezone.utc)
            
            # Get active discounts for this partner
            active_discounts = await db.outsource_partner_discounts.find({
                "partner_id": partner_id,
                "status": "active"
            }, {"_id": 0}).to_list(None)
            
            for discount in active_discounts:
                start_date = discount.get("start_date")
                end_date = discount.get("end_date")
                
                if start_date:
                    if isinstance(start_date, str):
                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    if now < start_date:
                        continue
                
                if end_date:
                    if isinstance(end_date, str):
                        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if now > end_date:
                        continue
                
                discount_type = discount.get("discount_type")
                discount_amount = 0
                
                if discount_type == "percentage" and discount.get("percentage"):
                    discount_amount = subtotal * (discount.get("percentage") / 100)
                elif discount_type == "dollar_amount" and discount.get("dollar_amount"):
                    discount_amount = discount.get("dollar_amount")
                elif discount_type == "per_file" and discount.get("per_file_amount"):
                    total_quantity = sum(item.get("quantity", 0) for item in items)
                    discount_amount = total_quantity * discount.get("per_file_amount")
                
                if discount_amount > 0:
                    total_discount += discount_amount
                    adjustments.append({
                        "type": "discount",
                        "id": discount.get("id"),
                        "description": discount.get("description", f"{discount_type} discount"),
                        "amount": -discount_amount
                    })
            
            # Get active credits for this partner (only unused ones for recalc)
            active_credits = await db.outsource_partner_credits.find({
                "partner_id": partner_id,
                "status": "active"
            }, {"_id": 0}).to_list(None)
            
            for credit in active_credits:
                valid_from = credit.get("valid_from")
                valid_until = credit.get("valid_until")
                
                if valid_from:
                    if isinstance(valid_from, str):
                        valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                    if now < valid_from:
                        continue
                
                if valid_until:
                    if isinstance(valid_until, str):
                        valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                    if now > valid_until:
                        continue
                
                credit_type = credit.get("credit_type")
                credit_amount = 0
                
                if credit_type == "dollar_credit" and credit.get("dollar_amount"):
                    credit_amount = credit.get("dollar_amount")
                elif credit_type == "month_credit":
                    credit_amount = subtotal - total_discount
                elif credit_type == "freemium":
                    credit_amount = subtotal - total_discount
                
                if credit_amount > 0:
                    total_credit_applied += credit_amount
                    adjustments.append({
                        "type": "credit",
                        "id": credit.get("id"),
                        "description": credit.get("description", f"{credit_type}"),
                        "amount": -credit_amount
                    })
            
            # Apply coupon if provided
            coupon_code = invoice.get("coupon_code")
            if coupon_code:
                coupon = await db.outsource_coupons.find_one({
                    "code": coupon_code.upper(),
                    "status": "active"
                }, {"_id": 0})
                
                if coupon:
                    applies_to = coupon.get("applies_to", "all")
                    specific_partners = coupon.get("specific_partner_ids", [])
                    coupon_valid = (applies_to == "all") or (partner_id in specific_partners)
                    
                    valid_from = coupon.get("valid_from")
                    valid_until = coupon.get("valid_until")
                    
                    if valid_from:
                        if isinstance(valid_from, str):
                            valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                        if now < valid_from:
                            coupon_valid = False
                    
                    if valid_until:
                        if isinstance(valid_until, str):
                            valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                        if now > valid_until:
                            coupon_valid = False
                    
                    if coupon_valid:
                        coupon_discount = 0
                        discount_type = coupon.get("discount_type")
                        discount_value = coupon.get("discount_value", 0)
                        remaining_total = subtotal - total_discount - total_credit_applied
                        
                        if discount_type == "percentage":
                            coupon_discount = remaining_total * (discount_value / 100)
                        elif discount_type == "dollar_amount":
                            coupon_discount = min(discount_value, remaining_total)
                        elif discount_type == "per_file":
                            total_quantity = sum(item.get("quantity", 0) for item in items)
                            coupon_discount = min(total_quantity * discount_value, remaining_total)
                        elif discount_type == "free_months":
                            coupon_discount = remaining_total
                        
                        if coupon_discount > 0:
                            adjustments.append({
                                "type": "coupon",
                                "id": coupon.get("id"),
                                "code": coupon_code.upper(),
                                "description": coupon.get("name", f"Coupon: {coupon_code.upper()}"),
                                "amount": -coupon_discount
                            })
                            total_discount += coupon_discount
            
            final_total = max(0, subtotal - total_discount - total_credit_applied)
            
            update_data["adjustments"] = adjustments
            update_data["total_discount"] = total_discount + total_credit_applied
            update_data["total_amount"] = final_total
        else:
            # Keep existing adjustments, just update total_amount based on new subtotal
            existing_invoice = await db.outsource_invoices.find_one({"id": invoice_id}, {"_id": 0})
            if existing_invoice:
                existing_discount = existing_invoice.get("total_discount", 0)
                update_data["total_amount"] = max(0, subtotal - existing_discount)
            else:
                update_data["total_amount"] = subtotal
        
        # Remove None values
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        result = await db.outsource_invoices.update_one(
            {"id": invoice_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        updated = await db.outsource_invoices.find_one({"id": invoice_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INVOICE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/outsource/invoices/{invoice_id}/status", dependencies=[Depends(check_permissions("author"))])
async def update_invoice_status(invoice_id: str, status_data: dict):
    """Update invoice status"""
    try:
        update_data = {
            "status": status_data.get("status"),
            "updated_at": datetime.now(timezone.utc)
        }
        
        if status_data.get("status") == "paid":
            update_data["paid_date"] = datetime.now(timezone.utc)
            update_data["payment_method"] = status_data.get("payment_method")
            update_data["payment_reference"] = status_data.get("payment_reference")
        
        result = await db.outsource_invoices.update_one(
            {"id": invoice_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        return {"message": "Invoice status updated"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INVOICE STATUS UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/invoices/{invoice_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_outsource_invoice(invoice_id: str):
    """Delete an invoice"""
    try:
        result = await db.outsource_invoices.delete_one({"id": invoice_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return {"message": "Invoice deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INVOICE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OUTSOURCE ESCALATION TICKET CATEGORIES ====================

@api_router.get("/admin/outsource/ticket-categories", dependencies=[Depends(check_permissions("author"))])
async def get_ticket_categories():
    """Get all ticket categories"""
    try:
        categories = await db.outsource_ticket_categories.find(
            {"is_active": True}, {"_id": 0}
        ).sort("display_order", 1).to_list(None)
        
        # Return default categories if none exist
        if not categories:
            default_categories = [
                {"id": str(uuid.uuid4()), "name": "Billing Issue", "default_urgency": "high", "display_order": 1, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "Technical Issue", "default_urgency": "high", "display_order": 2, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "Service Complaint", "default_urgency": "medium", "display_order": 3, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "Contract Question", "default_urgency": "medium", "display_order": 4, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "General Inquiry", "default_urgency": "low", "display_order": 5, "is_active": True},
            ]
            # Insert default categories
            for cat in default_categories:
                cat["created_at"] = datetime.now(timezone.utc).isoformat()
                await db.outsource_ticket_categories.insert_one(cat)
            return default_categories
        return categories
    except Exception as e:
        print(f"[TICKET CATEGORIES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/ticket-categories", dependencies=[Depends(check_permissions("editor"))])
async def create_ticket_category(category: dict, current_user: dict = Depends(get_current_user)):
    """Create a new ticket category"""
    try:
        category_data = {
            "id": str(uuid.uuid4()),
            "name": category.get("name"),
            "description": category.get("description", ""),
            "default_urgency": category.get("default_urgency", "medium"),
            "display_order": category.get("display_order", 0),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_ticket_categories.insert_one(category_data)
        category_data.pop("_id", None)
        return category_data
    except Exception as e:
        print(f"[TICKET CATEGORY CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/outsource/ticket-categories/{category_id}", dependencies=[Depends(check_permissions("editor"))])
async def update_ticket_category(category_id: str, category: dict):
    """Update a ticket category"""
    try:
        update_data = {k: v for k, v in category.items() if v is not None}
        result = await db.outsource_ticket_categories.update_one(
            {"id": category_id}, {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Category not found")
        updated = await db.outsource_ticket_categories.find_one({"id": category_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TICKET CATEGORY UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/ticket-categories/{category_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_ticket_category(category_id: str):
    """Soft delete a ticket category"""
    try:
        result = await db.outsource_ticket_categories.update_one(
            {"id": category_id}, {"$set": {"is_active": False}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Category not found")
        return {"message": "Category deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TICKET CATEGORY DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OUTSOURCE ESCALATION TICKETS ====================

def calculate_urgency_and_response(category_urgency: str, communication_method: str) -> tuple:
    """Calculate urgency and response time based on category and communication method"""
    # Base urgency from category
    urgency_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    comm_boost = {"phone": 1, "text": 0.5, "email": 0}
    
    base_level = urgency_levels.get(category_urgency, 2)
    boost = comm_boost.get(communication_method, 0)
    final_level = min(base_level + boost, 4)
    
    # Map back to urgency string
    urgency_map = {1: "low", 2: "medium", 3: "high", 4: "critical"}
    final_urgency = urgency_map.get(int(final_level), "medium")
    
    # Response time based on final urgency
    response_times = {"low": 48, "medium": 24, "high": 8, "critical": 4}
    response_hours = response_times.get(final_urgency, 24)
    
    return final_urgency, response_hours


@api_router.get("/admin/outsource/tickets", dependencies=[Depends(check_permissions("author"))])
async def get_escalation_tickets(
    partner_id: Optional[str] = None,
    status: Optional[str] = None,
    urgency: Optional[str] = None
):
    """Get all escalation tickets with optional filters"""
    try:
        query = {}
        if partner_id:
            query["partner_id"] = partner_id
        if status:
            query["status"] = status
        if urgency:
            query["urgency"] = urgency
        
        tickets = await db.outsource_tickets.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)
        return tickets
    except Exception as e:
        print(f"[TICKETS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/outsource/tickets/{ticket_id}", dependencies=[Depends(check_permissions("author"))])
async def get_escalation_ticket(ticket_id: str):
    """Get a specific escalation ticket"""
    try:
        ticket = await db.outsource_tickets.find_one({"id": ticket_id}, {"_id": 0})
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TICKET GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/tickets", dependencies=[Depends(check_permissions("author"))])
async def create_escalation_ticket(ticket: dict, current_user: dict = Depends(get_current_user)):
    """Create a new escalation ticket"""
    try:
        # Get category for urgency calculation
        category = await db.outsource_ticket_categories.find_one(
            {"id": ticket.get("category_id")}, {"_id": 0}
        )
        category_urgency = category.get("default_urgency", "medium") if category else "medium"
        
        # Calculate urgency and response time
        urgency, response_hours = calculate_urgency_and_response(
            category_urgency, ticket.get("communication_method", "email")
        )
        
        # Generate ticket number
        count = await db.outsource_tickets.count_documents({})
        year = datetime.now().year
        ticket_number = f"ESC-{year}-{str(count + 1).zfill(4)}"
        
        # Calculate due date
        due_by = datetime.now(timezone.utc) + timedelta(hours=response_hours)
        
        ticket_data = {
            "id": str(uuid.uuid4()),
            "ticket_number": ticket_number,
            "partner_id": ticket.get("partner_id"),
            "category_id": ticket.get("category_id"),
            "subject": ticket.get("subject"),
            "notes": ticket.get("notes"),
            "contact_name": ticket.get("contact_name"),
            "communication_method": ticket.get("communication_method"),
            "submitted_by_id": current_user.get("id"),
            "submitted_by_name": current_user.get("full_name", current_user.get("email")),
            "urgency": urgency,
            "response_time_hours": response_hours,
            "status": "open",
            "due_by": due_by.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.outsource_tickets.insert_one(ticket_data)
        # Remove _id if MongoDB added it (to avoid serialization issues)
        ticket_data.pop("_id", None)
        return ticket_data
    except Exception as e:
        print(f"[TICKET CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/outsource/tickets/{ticket_id}", dependencies=[Depends(check_permissions("author"))])
async def update_escalation_ticket(ticket_id: str, ticket: dict, current_user: dict = Depends(get_current_user)):
    """Update an escalation ticket"""
    try:
        existing = await db.outsource_tickets.find_one({"id": ticket_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        update_data = {k: v for k, v in ticket.items() if v is not None}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # If status changed to resolved/closed, track resolution
        if ticket.get("status") in ["resolved", "closed"] and existing.get("status") not in ["resolved", "closed"]:
            update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
            update_data["resolved_by_id"] = current_user.get("id")
            update_data["resolved_by_name"] = current_user.get("full_name", current_user.get("email"))
        
        await db.outsource_tickets.update_one({"id": ticket_id}, {"$set": update_data})
        updated = await db.outsource_tickets.find_one({"id": ticket_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TICKET UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/tickets/{ticket_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_escalation_ticket(ticket_id: str):
    """Delete an escalation ticket"""
    try:
        result = await db.outsource_tickets.delete_one({"id": ticket_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {"message": "Ticket deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TICKET DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ENHANCED WORK LOGS ====================

@api_router.put("/admin/outsource/work-logs/{log_id}", dependencies=[Depends(check_permissions("author"))])
async def update_work_log(log_id: str, log_data: dict, current_user: dict = Depends(get_current_user)):
    """Update a work log entry"""
    try:
        existing = await db.outsource_work_logs.find_one({"id": log_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Work log not found")
        
        update_data = {k: v for k, v in log_data.items() if v is not None}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.outsource_work_logs.update_one({"id": log_id}, {"$set": update_data})
        updated = await db.outsource_work_logs.find_one({"id": log_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORK LOG UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/outsource/work-logs/{log_id}/archive", dependencies=[Depends(check_permissions("author"))])
async def archive_work_log(log_id: str, current_user: dict = Depends(get_current_user)):
    """Archive a work log entry"""
    try:
        existing = await db.outsource_work_logs.find_one({"id": log_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Work log not found")
        
        is_archived = not existing.get("is_archived", False)
        update_data = {
            "is_archived": is_archived,
            "archived_at": datetime.now(timezone.utc).isoformat() if is_archived else None,
            "archived_by": current_user.get("id") if is_archived else None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.outsource_work_logs.update_one({"id": log_id}, {"$set": update_data})
        return {"message": f"Work log {'archived' if is_archived else 'unarchived'} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORK LOG ARCHIVE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/outsource/partners/{partner_id}/work-logs", dependencies=[Depends(check_permissions("author"))])
async def get_partner_work_logs(partner_id: str, include_archived: bool = False):
    """Get work logs for a specific partner"""
    try:
        query = {"partner_id": partner_id}
        if not include_archived:
            query["$or"] = [{"is_archived": False}, {"is_archived": {"$exists": False}}]
        
        logs = await db.outsource_work_logs.find(query, {"_id": 0}).sort("work_date", -1).to_list(None)
        return logs
    except Exception as e:
        print(f"[PARTNER WORK LOGS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/outsource/partners/{partner_id}/tickets", dependencies=[Depends(check_permissions("author"))])
async def get_partner_tickets(partner_id: str):
    """Get escalation tickets for a specific partner"""
    try:
        tickets = await db.outsource_tickets.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(None)
        return tickets
    except Exception as e:
        print(f"[PARTNER TICKETS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/outsource/partners/{partner_id}/invoices", dependencies=[Depends(check_permissions("author"))])
async def get_partner_invoices(partner_id: str):
    """Get invoices for a specific partner"""
    try:
        invoices = await db.outsource_invoices.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("invoice_date", -1).to_list(None)
        return invoices
    except Exception as e:
        print(f"[PARTNER INVOICES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/work-logs/{log_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_work_log(log_id: str):
    """Delete a work log entry"""
    try:
        result = await db.outsource_work_logs.delete_one({"id": log_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Work log not found")
        return {"message": "Work log deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORK LOG DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PARTNER NOTES ====================

@api_router.get("/admin/outsource/partners/{partner_id}/notes", dependencies=[Depends(check_permissions("author"))])
async def get_partner_notes(partner_id: str):
    """Get notes for a specific partner"""
    try:
        notes = await db.outsource_partner_notes.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(None)
        return notes
    except Exception as e:
        print(f"[PARTNER NOTES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/partners/{partner_id}/notes", dependencies=[Depends(check_permissions("author"))])
async def create_partner_note(partner_id: str, note: dict, current_user: dict = Depends(get_current_user)):
    """Create a note for a partner"""
    try:
        note_data = {
            "id": str(uuid.uuid4()),
            "partner_id": partner_id,
            "title": note.get("title"),
            "content": note.get("content"),
            "category": note.get("category"),
            "source_type": note.get("source_type"),
            "contact_email": note.get("contact_email"),
            "contact_phone": note.get("contact_phone"),
            "contact_name": note.get("contact_name"),
            "attachments": note.get("attachments", []),
            "created_by_id": current_user.get("id"),
            "created_by_name": current_user.get("full_name", current_user.get("email")),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_partner_notes.insert_one(note_data)
        note_data.pop("_id", None)
        return note_data
    except Exception as e:
        print(f"[PARTNER NOTE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/outsource/notes/{note_id}", dependencies=[Depends(check_permissions("author"))])
async def update_partner_note(note_id: str, note: dict):
    """Update a partner note"""
    try:
        update_data = {k: v for k, v in note.items() if v is not None}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.outsource_partner_notes.update_one({"id": note_id}, {"$set": update_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Note not found")
        updated = await db.outsource_partner_notes.find_one({"id": note_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER NOTE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/notes/{note_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_partner_note(note_id: str):
    """Delete a partner note"""
    try:
        result = await db.outsource_partner_notes.delete_one({"id": note_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"message": "Note deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER NOTE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PARTNER AGREEMENTS ====================

@api_router.get("/admin/outsource/partners/{partner_id}/agreements", dependencies=[Depends(check_permissions("author"))])
async def get_partner_agreements(partner_id: str):
    """Get agreements for a specific partner"""
    try:
        agreements = await db.outsource_partner_agreements.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(None)
        return agreements
    except Exception as e:
        print(f"[PARTNER AGREEMENTS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/partners/{partner_id}/agreements", dependencies=[Depends(check_permissions("author"))])
async def create_partner_agreement(partner_id: str, agreement: dict, current_user: dict = Depends(get_current_user)):
    """Create an agreement for a partner"""
    try:
        agreement_data = {
            "id": str(uuid.uuid4()),
            "partner_id": partner_id,
            "title": agreement.get("title"),
            "description": agreement.get("description"),
            "agreement_type": agreement.get("agreement_type"),
            "file_name": agreement.get("file_name"),
            "file_url": agreement.get("file_url"),
            "file_size": agreement.get("file_size"),
            "effective_date": agreement.get("effective_date"),
            "expiration_date": agreement.get("expiration_date"),
            "status": agreement.get("status", "active"),
            "uploaded_by_id": current_user.get("id"),
            "uploaded_by_name": current_user.get("full_name", current_user.get("email")),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_partner_agreements.insert_one(agreement_data)
        agreement_data.pop("_id", None)
        return agreement_data
    except Exception as e:
        print(f"[PARTNER AGREEMENT CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/agreements/{agreement_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_partner_agreement(agreement_id: str):
    """Delete a partner agreement"""
    try:
        result = await db.outsource_partner_agreements.delete_one({"id": agreement_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Agreement not found")
        return {"message": "Agreement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER AGREEMENT DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PARTNER CREDITS ====================

@api_router.get("/admin/outsource/partners/{partner_id}/credits", dependencies=[Depends(check_permissions("author"))])
async def get_partner_credits(partner_id: str):
    """Get credits for a specific partner"""
    try:
        credits = await db.outsource_partner_credits.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(None)
        return credits
    except Exception as e:
        print(f"[PARTNER CREDITS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/partners/{partner_id}/credits", dependencies=[Depends(check_permissions("author"))])
async def create_partner_credit(partner_id: str, credit: dict, current_user: dict = Depends(get_current_user)):
    """Create a credit for a partner"""
    try:
        credit_data = {
            "id": str(uuid.uuid4()),
            "partner_id": partner_id,
            "credit_type": credit.get("credit_type"),
            "description": credit.get("description"),
            "months": credit.get("months"),
            "dollar_amount": credit.get("dollar_amount"),
            "valid_from": credit.get("valid_from", datetime.now(timezone.utc).isoformat()),
            "valid_until": credit.get("valid_until"),
            "status": "active",
            "created_by_id": current_user.get("id"),
            "created_by_name": current_user.get("full_name", current_user.get("email")),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_partner_credits.insert_one(credit_data)
        credit_data.pop("_id", None)
        return credit_data
    except Exception as e:
        print(f"[PARTNER CREDIT CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/outsource/credits/{credit_id}/status", dependencies=[Depends(check_permissions("author"))])
async def update_credit_status(credit_id: str, data: dict):
    """Update credit status"""
    try:
        update_data = {"status": data.get("status")}
        if data.get("applied_to_invoice_id"):
            update_data["applied_to_invoice_id"] = data.get("applied_to_invoice_id")
            update_data["applied_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.outsource_partner_credits.update_one({"id": credit_id}, {"$set": update_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Credit not found")
        return {"message": "Credit updated"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CREDIT STATUS UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PARTNER DISCOUNTS ====================

@api_router.get("/admin/outsource/partners/{partner_id}/discounts", dependencies=[Depends(check_permissions("author"))])
async def get_partner_discounts(partner_id: str):
    """Get discounts for a specific partner"""
    try:
        discounts = await db.outsource_partner_discounts.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(None)
        return discounts
    except Exception as e:
        print(f"[PARTNER DISCOUNTS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/partners/{partner_id}/discounts", dependencies=[Depends(check_permissions("author"))])
async def create_partner_discount(partner_id: str, discount: dict, current_user: dict = Depends(get_current_user)):
    """Create a discount for a partner"""
    try:
        # Calculate end date if duration specified
        end_date = None
        if discount.get("duration_months"):
            start = datetime.now(timezone.utc)
            end_date = (start + timedelta(days=discount.get("duration_months") * 30)).isoformat()
        
        discount_data = {
            "id": str(uuid.uuid4()),
            "partner_id": partner_id,
            "discount_type": discount.get("discount_type"),
            "description": discount.get("description"),
            "percentage": discount.get("percentage"),
            "dollar_amount": discount.get("dollar_amount"),
            "per_file_amount": discount.get("per_file_amount"),
            "duration_months": discount.get("duration_months"),
            "start_date": datetime.now(timezone.utc).isoformat(),
            "end_date": end_date,
            "status": "active",
            "created_by_id": current_user.get("id"),
            "created_by_name": current_user.get("full_name", current_user.get("email")),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_partner_discounts.insert_one(discount_data)
        discount_data.pop("_id", None)
        return discount_data
    except Exception as e:
        print(f"[PARTNER DISCOUNT CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/discounts/{discount_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_partner_discount(discount_id: str):
    """Delete a partner discount"""
    try:
        result = await db.outsource_partner_discounts.delete_one({"id": discount_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Discount not found")
        return {"message": "Discount deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DISCOUNT DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== COUPONS ====================

@api_router.get("/admin/outsource/coupons", dependencies=[Depends(check_permissions("author"))])
async def get_coupons():
    """Get all coupons"""
    try:
        coupons = await db.outsource_coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(None)
        return coupons
    except Exception as e:
        print(f"[COUPONS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/coupons", dependencies=[Depends(check_permissions("editor"))])
async def create_coupon(coupon: dict, current_user: dict = Depends(get_current_user)):
    """Create a new coupon"""
    try:
        # Check if code already exists
        existing = await db.outsource_coupons.find_one({"code": coupon.get("code").upper()})
        if existing:
            raise HTTPException(status_code=400, detail="Coupon code already exists")
        
        coupon_data = {
            "id": str(uuid.uuid4()),
            "code": coupon.get("code").upper(),
            "name": coupon.get("name"),
            "description": coupon.get("description"),
            "discount_type": coupon.get("discount_type"),
            "discount_value": coupon.get("discount_value"),
            "applies_to": coupon.get("applies_to", "all"),
            "specific_partner_ids": coupon.get("specific_partner_ids", []),
            "duration_months": coupon.get("duration_months"),
            "max_uses": coupon.get("max_uses"),
            "times_used": 0,
            "valid_from": coupon.get("valid_from", datetime.now(timezone.utc).isoformat()),
            "valid_until": coupon.get("valid_until"),
            "status": "active",
            "created_by_id": current_user.get("id"),
            "created_by_name": current_user.get("full_name", current_user.get("email")),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.outsource_coupons.insert_one(coupon_data)
        coupon_data.pop("_id", None)
        return coupon_data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[COUPON CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/outsource/coupons/{coupon_id}", dependencies=[Depends(check_permissions("editor"))])
async def update_coupon(coupon_id: str, coupon: dict):
    """Update a coupon"""
    try:
        update_data = {k: v for k, v in coupon.items() if v is not None}
        result = await db.outsource_coupons.update_one({"id": coupon_id}, {"$set": update_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Coupon not found")
        updated = await db.outsource_coupons.find_one({"id": coupon_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[COUPON UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/coupons/{coupon_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_coupon(coupon_id: str):
    """Delete a coupon"""
    try:
        result = await db.outsource_coupons.delete_one({"id": coupon_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Coupon not found")
        return {"message": "Coupon deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[COUPON DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== APPLY COUPON TO PARTNER ====================

@api_router.get("/admin/outsource/partners/{partner_id}/coupons", dependencies=[Depends(check_permissions("author"))])
async def get_partner_applied_coupons(partner_id: str):
    """Get applied coupons for a partner"""
    try:
        applied = await db.outsource_applied_coupons.find(
            {"partner_id": partner_id}, {"_id": 0}
        ).sort("applied_at", -1).to_list(None)
        return applied
    except Exception as e:
        print(f"[PARTNER COUPONS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/partners/{partner_id}/apply-coupon", dependencies=[Depends(check_permissions("author"))])
async def apply_coupon_to_partner(partner_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Apply a coupon to a partner"""
    try:
        coupon_code = data.get("coupon_code", "").upper()
        
        # Find coupon
        coupon = await db.outsource_coupons.find_one({"code": coupon_code, "status": "active"}, {"_id": 0})
        if not coupon:
            raise HTTPException(status_code=404, detail="Coupon not found or inactive")
        
        # Check if coupon can be applied
        if coupon.get("max_uses") and coupon.get("times_used", 0) >= coupon.get("max_uses"):
            raise HTTPException(status_code=400, detail="Coupon has reached maximum uses")
        
        # Check if already applied to this partner
        existing = await db.outsource_applied_coupons.find_one({
            "coupon_id": coupon["id"],
            "partner_id": partner_id,
            "status": "active"
        })
        if existing:
            raise HTTPException(status_code=400, detail="Coupon already applied to this partner")
        
        # Calculate expiry
        expires_at = None
        if coupon.get("duration_months"):
            expires_at = (datetime.now(timezone.utc) + timedelta(days=coupon.get("duration_months") * 30)).isoformat()
        
        applied_data = {
            "id": str(uuid.uuid4()),
            "coupon_id": coupon["id"],
            "coupon_code": coupon["code"],
            "partner_id": partner_id,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "applied_by_id": current_user.get("id"),
            "applied_by_name": current_user.get("full_name", current_user.get("email")),
            "months_remaining": coupon.get("duration_months"),
            "expires_at": expires_at,
            "status": "active"
        }
        
        await db.outsource_applied_coupons.insert_one(applied_data)
        
        # Increment coupon usage
        await db.outsource_coupons.update_one(
            {"id": coupon["id"]},
            {"$inc": {"times_used": 1}}
        )
        
        applied_data.pop("_id", None)
        return applied_data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[APPLY COUPON ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/applied-coupons/{applied_id}", dependencies=[Depends(check_permissions("author"))])
async def remove_applied_coupon(applied_id: str):
    """Remove an applied coupon from a partner"""
    try:
        applied = await db.outsource_applied_coupons.find_one({"id": applied_id}, {"_id": 0})
        if not applied:
            raise HTTPException(status_code=404, detail="Applied coupon not found")
        
        # Decrement coupon usage
        await db.outsource_coupons.update_one(
            {"id": applied["coupon_id"]},
            {"$inc": {"times_used": -1}}
        )
        
        await db.outsource_applied_coupons.delete_one({"id": applied_id})
        return {"message": "Coupon removed from partner"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REMOVE COUPON ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== NOTE CATEGORIES ====================

@api_router.get("/admin/outsource/note-categories", dependencies=[Depends(check_permissions("author"))])
async def get_note_categories():
    """Get all note categories"""
    try:
        categories = await db.outsource_note_categories.find({"is_active": True}, {"_id": 0}).to_list(None)
        if not categories:
            # Create default categories
            default_categories = [
                {"id": str(uuid.uuid4()), "name": "Billing", "display_order": 1, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "Customer Care", "display_order": 2, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "Technical", "display_order": 3, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "Contract", "display_order": 4, "is_active": True},
                {"id": str(uuid.uuid4()), "name": "General", "display_order": 5, "is_active": True},
            ]
            for cat in default_categories:
                await db.outsource_note_categories.insert_one(cat)
                cat.pop("_id", None)
            return default_categories
        return categories
    except Exception as e:
        print(f"[NOTE CATEGORIES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/note-categories", dependencies=[Depends(check_permissions("editor"))])
async def create_note_category(category: dict):
    """Create a new note category"""
    try:
        cat_data = {
            "id": str(uuid.uuid4()),
            "name": category.get("name"),
            "display_order": category.get("display_order", 0),
            "is_active": True
        }
        await db.outsource_note_categories.insert_one(cat_data)
        cat_data.pop("_id", None)
        return cat_data
    except Exception as e:
        print(f"[NOTE CATEGORY CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/press-releases", dependencies=[Depends(check_permissions("author"))])
async def create_press_release(
    press_release: PressReleaseCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new press release"""
    try:
        pr_dict = press_release.dict()
        pr_dict["id"] = str(uuid.uuid4())
        pr_dict["slug"] = generate_slug(press_release.title)
        pr_dict["created_at"] = datetime.now(timezone.utc)
        pr_dict["updated_at"] = datetime.now(timezone.utc)
        pr_dict["created_by"] = current_user.get("id")
        
        await db.press_releases.insert_one(pr_dict)
        return remove_id(pr_dict)
    except Exception as e:
        print(f"[PRESS RELEASE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/press-releases/{release_id}", dependencies=[Depends(check_permissions("author"))])
async def update_press_release(
    release_id: str,
    press_release: PressReleaseUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing press release"""
    try:
        existing = await db.press_releases.find_one({"id": release_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Press release not found")
        
        pr_dict = press_release.dict(exclude_unset=True)
        if press_release.title:
            pr_dict["slug"] = generate_slug(press_release.title)
        pr_dict["updated_at"] = datetime.now(timezone.utc)
        
        await db.press_releases.update_one(
            {"id": release_id},
            {"$set": pr_dict}
        )
        
        updated = await db.press_releases.find_one({"id": release_id})
        return remove_id(updated)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PRESS RELEASE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/press-releases/{release_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_press_release(release_id: str):
    """Delete a press release"""
    try:
        result = await db.press_releases.delete_one({"id": release_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Press release not found")
        return {"message": "Press release deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PRESS RELEASE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/press-releases/{release_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_press_release_published(release_id: str):
    """Toggle press release published status"""
    try:
        press_release = await db.press_releases.find_one({"id": release_id})
        if not press_release:
            raise HTTPException(status_code=404, detail="Press release not found")
        
        new_status = not press_release.get("is_published", False)
        await db.press_releases.update_one(
            {"id": release_id},
            {"$set": {"is_published": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        
        return {"message": f"Press release {'published' if new_status else 'unpublished'}", "is_published": new_status}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PRESS RELEASE TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# ANNOUNCEMENTS MANAGEMENT
# ==============================================================

@api_router.get("/announcements")
async def get_announcements_public():
    """Public endpoint - Get all published announcements"""
    try:
        announcements = await db.announcements.find({"is_published": True}, {"_id": 0}).sort("publish_date", -1).to_list(length=None)
        return announcements
    except Exception as e:
        print(f"[ANNOUNCEMENTS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/announcements/rss")
async def get_announcements_rss():
    """Public RSS feed for announcements (for Google News)"""
    try:
        import re
        announcements = await db.announcements.find(
            {"is_published": True}, 
            {"_id": 0}
        ).sort("publish_date", -1).limit(50).to_list(length=50)
        
        # Build RSS feed
        rss_items = []
        for ann in announcements:
            pub_date = ann.get('publish_date', datetime.now(timezone.utc))
            if isinstance(pub_date, str):
                pub_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            
            # Format date for RSS (RFC 822)
            pub_date_rfc = pub_date.strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Clean description (strip HTML tags for RSS)
            description = ann.get('excerpt', '')
            if not description:
                description = re.sub('<.*?>', '', ann.get('content', ''))[:300] + '...'
            
            # Get announcement type label
            type_labels = {
                'general': 'Company Update',
                'promotion': 'Promotion',
                'acquisition': 'Acquisition',
                'product': 'New Product',
                'service': 'New Service',
                'partnership': 'Partnership'
            }
            category = type_labels.get(ann.get('announcement_type', 'general'), 'Announcement')
            
            item = f"""
            <item>
                <title>{ann.get('title', '')}</title>
                <link>https://credlocity.com/announcements/{ann.get('slug', ann.get('id'))}</link>
                <guid isPermaLink="true">https://credlocity.com/announcements/{ann.get('slug', ann.get('id'))}</guid>
                <description><![CDATA[{description}]]></description>
                <category>{category}</category>
                <pubDate>{pub_date_rfc}</pubDate>
                <author>announcements@credlocity.com (Credlocity)</author>
            </item>
            """
            rss_items.append(item)
        
        rss_feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>Credlocity Announcements</title>
        <link>https://credlocity.com/press-releases</link>
        <description>Latest announcements from Credlocity - promotions, acquisitions, new products and services</description>
        <language>en-us</language>
        <copyright>Copyright {datetime.now().year} Credlocity Business Group LLC</copyright>
        <atom:link href="https://credlocity.com/api/announcements/rss" rel="self" type="application/rss+xml" />
        {''.join(rss_items)}
    </channel>
</rss>"""
        
        return Response(content=rss_feed, media_type="application/rss+xml")
    except Exception as e:
        print(f"[ANNOUNCEMENTS RSS FEED ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/announcements/{slug}")
async def get_announcement_by_slug(slug: str):
    """Public endpoint - Get announcement by slug with related employee details"""
    try:
        announcement = await db.announcements.find_one({"slug": slug, "is_published": True}, {"_id": 0})
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        # Fetch related employee details
        if announcement.get('related_employees'):
            employees = await db.authors.find(
                {"id": {"$in": announcement['related_employees']}, "status": "active"},
                {"_id": 0, "id": 1, "full_name": 1, "slug": 1, "title": 1, "photo_url": 1}
            ).to_list(None)
            announcement['related_employee_details'] = employees
        
        return announcement
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANNOUNCEMENT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/announcements", dependencies=[Depends(check_permissions("author"))])
async def get_all_announcements():
    """Admin endpoint - Get all announcements"""
    try:
        announcements = await db.announcements.find({}, {"_id": 0}).sort("created_at", -1).to_list(length=None)
        return announcements
    except Exception as e:
        print(f"[ADMIN ANNOUNCEMENTS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/announcements/{announcement_id}", dependencies=[Depends(check_permissions("author"))])
async def get_announcement_by_id(announcement_id: str):
    """Admin endpoint - Get announcement by ID"""
    try:
        announcement = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
        return announcement
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN ANNOUNCEMENT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/announcements", dependencies=[Depends(check_permissions("author"))])
async def create_announcement(
    data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Create a new announcement"""
    try:
        announcement = {
            "id": str(uuid.uuid4()),
            "title": data.get("title"),
            "slug": generate_slug(data.get("title")),
            "content": data.get("content"),
            "excerpt": data.get("excerpt"),
            "announcement_type": data.get("announcement_type", "general"),
            "publish_date": data.get("publish_date"),
            "is_published": data.get("is_published", True),
            "featured_image": data.get("featured_image"),
            "related_employees": data.get("related_employees", []),
            "related_press_releases": data.get("related_press_releases", []),
            "related_blog_posts": data.get("related_blog_posts", []),
            "meta_title": data.get("meta_title"),
            "meta_description": data.get("meta_description"),
            "meta_keywords": data.get("meta_keywords", []),
            "og_title": data.get("og_title"),
            "og_description": data.get("og_description"),
            "og_image": data.get("og_image"),
            "canonical_url": data.get("canonical_url"),
            "schema_type": data.get("schema_type", "NewsArticle"),
            "schema_types": data.get("schema_types", ["NewsArticle", "BreadcrumbList", "Organization"]),
            "schema_data": data.get("schema_data", {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user.get("id")
        }
        
        await db.announcements.insert_one(announcement)
        announcement.pop("_id", None)
        return announcement
    except Exception as e:
        print(f"[ANNOUNCEMENT CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/announcements/{announcement_id}", dependencies=[Depends(check_permissions("author"))])
async def update_announcement(
    announcement_id: str,
    data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing announcement"""
    try:
        existing = await db.announcements.find_one({"id": announcement_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        update_data = {}
        allowed_fields = [
            "title", "content", "excerpt", "announcement_type", "publish_date",
            "is_published", "featured_image", "related_employees", "related_press_releases",
            "related_blog_posts", "meta_title", "meta_description", "meta_keywords",
            "og_title", "og_description", "og_image", "canonical_url", "schema_type", "schema_types", "schema_data"
        ]
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        if "title" in update_data:
            update_data["slug"] = generate_slug(update_data["title"])
        
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.announcements.update_one(
            {"id": announcement_id},
            {"$set": update_data}
        )
        
        updated = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANNOUNCEMENT UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/announcements/{announcement_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_announcement(announcement_id: str):
    """Delete an announcement"""
    try:
        result = await db.announcements.delete_one({"id": announcement_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        return {"message": "Announcement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANNOUNCEMENT DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/announcements/{announcement_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_announcement_published(announcement_id: str):
    """Toggle announcement published status"""
    try:
        announcement = await db.announcements.find_one({"id": announcement_id})
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        new_status = not announcement.get("is_published", False)
        await db.announcements.update_one(
            {"id": announcement_id},
            {"$set": {"is_published": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {"message": f"Announcement {'published' if new_status else 'unpublished'}", "is_published": new_status}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANNOUNCEMENT TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/team/{member_id}/press-announcements")
async def get_team_member_press_announcements(member_id: str):
    """Get press releases and announcements related to a team member"""
    try:
        # Get press releases linked to this team member
        press_releases = await db.press_releases.find(
            {"related_employees": member_id, "is_published": True},
            {"_id": 0}
        ).sort("publish_date", -1).to_list(None)
        
        # Get announcements linked to this team member
        announcements = await db.announcements.find(
            {"related_employees": member_id, "is_published": True},
            {"_id": 0}
        ).sort("publish_date", -1).to_list(None)
        
        return {
            "press_releases": press_releases,
            "announcements": announcements
        }
    except Exception as e:
        print(f"[TEAM PRESS ANNOUNCEMENTS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# CREDLOCITY PARTNERS MANAGEMENT
# ==============================================================

# Partner Types API
@api_router.get("/partner-types")
async def get_partner_types_public():
    """Public endpoint - Get all active partner types"""
    try:
        types = await db.partner_types.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(None)
        return types
    except Exception as e:
        print(f"[PARTNER TYPES ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/partner-types", dependencies=[Depends(check_permissions("author"))])
async def get_all_partner_types():
    """Admin endpoint - Get all partner types"""
    try:
        types = await db.partner_types.find({}, {"_id": 0}).sort("display_order", 1).to_list(None)
        return types
    except Exception as e:
        print(f"[ADMIN PARTNER TYPES ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/partner-types", dependencies=[Depends(check_permissions("author"))])
async def create_partner_type(data: dict):
    """Create a new partner type"""
    try:
        partner_type = {
            "id": str(uuid.uuid4()),
            "name": data.get("name"),
            "slug": generate_slug(data.get("name")),
            "description": data.get("description"),
            "icon": data.get("icon"),
            "display_order": data.get("display_order", 0),
            "is_active": data.get("is_active", True),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.partner_types.insert_one(partner_type)
        partner_type.pop("_id", None)
        return partner_type
    except Exception as e:
        print(f"[PARTNER TYPE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/partner-types/{type_id}", dependencies=[Depends(check_permissions("author"))])
async def update_partner_type(type_id: str, data: dict):
    """Update a partner type"""
    try:
        update_data = {k: v for k, v in data.items() if v is not None}
        if "name" in update_data:
            update_data["slug"] = generate_slug(update_data["name"])
        
        await db.partner_types.update_one({"id": type_id}, {"$set": update_data})
        updated = await db.partner_types.find_one({"id": type_id}, {"_id": 0})
        return updated
    except Exception as e:
        print(f"[PARTNER TYPE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/partner-types/{type_id}", dependencies=[Depends(check_permissions("admin"))])
async def delete_partner_type(type_id: str):
    """Delete a partner type"""
    try:
        result = await db.partner_types.delete_one({"id": type_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Partner type not found")
        return {"message": "Partner type deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER TYPE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Partners API
@api_router.get("/partners")
async def get_partners_public(partner_type: Optional[str] = None, featured: bool = False):
    """Public endpoint - Get all published partners"""
    try:
        query = {"is_published": True}
        if partner_type:
            query["partner_type_id"] = partner_type
        if featured:
            query["is_featured"] = True
        
        partners = await db.partners.find(query, {"_id": 0}).sort("display_order", 1).to_list(None)
        
        # Enrich with partner type info
        types = {t["id"]: t for t in await db.partner_types.find({}, {"_id": 0}).to_list(None)}
        for partner in partners:
            partner["partner_type"] = types.get(partner.get("partner_type_id"), {})
        
        return partners
    except Exception as e:
        print(f"[PARTNERS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/partners/{slug}")
async def get_partner_by_slug(slug: str):
    """Public endpoint - Get partner by slug with related content"""
    try:
        partner = await db.partners.find_one({"slug": slug, "is_published": True}, {"_id": 0})
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        # Get partner type
        partner_type = await db.partner_types.find_one({"id": partner.get("partner_type_id")}, {"_id": 0})
        partner["partner_type"] = partner_type or {}
        
        # Get related reviews
        if partner.get("featured_review_ids"):
            reviews = await db.reviews.find(
                {"id": {"$in": partner["featured_review_ids"]}},
                {"_id": 0}
            ).to_list(None)
            partner["reviews"] = reviews
        
        # Get related announcements
        if partner.get("related_announcement_ids"):
            announcements = await db.announcements.find(
                {"id": {"$in": partner["related_announcement_ids"]}, "is_published": True},
                {"_id": 0}
            ).to_list(None)
            partner["related_announcements"] = announcements
        
        # Get related press releases
        if partner.get("related_press_release_ids"):
            press_releases = await db.press_releases.find(
                {"id": {"$in": partner["related_press_release_ids"]}, "is_published": True},
                {"_id": 0}
            ).to_list(None)
            partner["related_press_releases"] = press_releases
        
        return partner
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/partners", dependencies=[Depends(check_permissions("author"))])
async def get_all_partners():
    """Admin endpoint - Get all partners"""
    try:
        partners = await db.partners.find({}, {"_id": 0}).sort("created_at", -1).to_list(None)
        types = {t["id"]: t for t in await db.partner_types.find({}, {"_id": 0}).to_list(None)}
        for partner in partners:
            partner["partner_type"] = types.get(partner.get("partner_type_id"), {})
        return partners
    except Exception as e:
        print(f"[ADMIN PARTNERS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/partners/{partner_id}", dependencies=[Depends(check_permissions("author"))])
async def get_partner_by_id(partner_id: str):
    """Admin endpoint - Get partner by ID"""
    try:
        partner = await db.partners.find_one({"id": partner_id}, {"_id": 0})
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        return partner
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN PARTNER GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/partners", dependencies=[Depends(check_permissions("author"))])
async def create_partner(data: dict, current_user: dict = Depends(get_current_user)):
    """Create a new partner"""
    try:
        partner = {
            "id": str(uuid.uuid4()),
            "name": data.get("name"),
            "slug": generate_slug(data.get("name") + "-" + data.get("company_name", "")),
            "company_name": data.get("company_name"),
            "partner_type_id": data.get("partner_type_id"),
            "tagline": data.get("tagline"),
            "photo_url": data.get("photo_url"),
            "company_logo": data.get("company_logo"),
            "cover_image": data.get("cover_image"),
            "short_bio": data.get("short_bio"),
            "full_bio": data.get("full_bio"),
            "what_we_do": data.get("what_we_do"),
            "credentials": data.get("credentials", []),
            "education": data.get("education", []),
            "years_experience": data.get("years_experience"),
            "specializations": data.get("specializations", []),
            "awards": data.get("awards", []),
            "testimonials": data.get("testimonials", []),
            "featured_review_ids": data.get("featured_review_ids", []),
            "client_count": data.get("client_count"),
            "success_rate": data.get("success_rate"),
            "website": data.get("website"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "address": data.get("address"),
            "city": data.get("city"),
            "state": data.get("state"),
            "zip_code": data.get("zip_code"),
            "social_links": data.get("social_links", {}),
            "related_announcement_ids": data.get("related_announcement_ids", []),
            "related_press_release_ids": data.get("related_press_release_ids", []),
            "related_blog_post_ids": data.get("related_blog_post_ids", []),
            "meta_title": data.get("meta_title"),
            "meta_description": data.get("meta_description"),
            "meta_keywords": data.get("meta_keywords", []),
            "og_title": data.get("og_title"),
            "og_description": data.get("og_description"),
            "og_image": data.get("og_image"),
            "canonical_url": data.get("canonical_url"),
            "schema_types": data.get("schema_types", ["Person", "Organization", "LocalBusiness", "ProfessionalService"]),
            "schema_data": data.get("schema_data", {}),
            "is_published": data.get("is_published", True),
            "is_featured": data.get("is_featured", False),
            "display_order": data.get("display_order", 0),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user.get("id")
        }
        
        await db.partners.insert_one(partner)
        partner.pop("_id", None)
        return partner
    except Exception as e:
        print(f"[PARTNER CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/partners/{partner_id}", dependencies=[Depends(check_permissions("author"))])
async def update_partner(partner_id: str, data: dict):
    """Update a partner"""
    try:
        existing = await db.partners.find_one({"id": partner_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        update_data = {k: v for k, v in data.items() if v is not None}
        if "name" in update_data or "company_name" in update_data:
            name = update_data.get("name", existing.get("name"))
            company = update_data.get("company_name", existing.get("company_name"))
            update_data["slug"] = generate_slug(name + "-" + company)
        
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.partners.update_one({"id": partner_id}, {"$set": update_data})
        updated = await db.partners.find_one({"id": partner_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/partners/{partner_id}", dependencies=[Depends(check_permissions("admin"))])
async def delete_partner(partner_id: str):
    """Delete a partner"""
    try:
        result = await db.partners.delete_one({"id": partner_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Partner not found")
        return {"message": "Partner deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/partners/{partner_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_partner_published(partner_id: str):
    """Toggle partner published status"""
    try:
        partner = await db.partners.find_one({"id": partner_id})
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        new_status = not partner.get("is_published", False)
        await db.partners.update_one(
            {"id": partner_id},
            {"$set": {"is_published": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {"message": f"Partner {'published' if new_status else 'unpublished'}", "is_published": new_status}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# LEGAL PAGES MANAGEMENT
# ==============================================================

@api_router.get("/legal-pages")
async def get_legal_pages_public():
    """Public endpoint - Get all published legal pages"""
    try:
        legal_pages = await db.legal_pages.find({"is_published": True}, {"_id": 0}).sort("title", 1).to_list(length=None)
        return legal_pages
    except Exception as e:
        print(f"[LEGAL PAGES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/legal-pages/{slug}")
async def get_legal_page_by_slug(slug: str):
    """Public endpoint - Get legal page by slug"""
    try:
        legal_page = await db.legal_pages.find_one({"slug": slug, "is_published": True}, {"_id": 0})
        if not legal_page:
            raise HTTPException(status_code=404, detail="Legal page not found")
        return legal_page
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LEGAL PAGE GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/legal-pages", dependencies=[Depends(check_permissions("author"))])
async def get_all_legal_pages_admin():
    """Admin endpoint - Get all legal pages"""
    try:
        legal_pages = await db.legal_pages.find({}, {"_id": 0}).sort("title", 1).to_list(length=None)
        return legal_pages
    except Exception as e:
        print(f"[LEGAL PAGES ADMIN GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/legal-pages/{page_id}", dependencies=[Depends(check_permissions("author"))])
async def get_legal_page_by_id(page_id: str):
    """Admin endpoint - Get legal page by ID"""
    try:
        legal_page = await db.legal_pages.find_one({"id": page_id}, {"_id": 0})
        if not legal_page:
            raise HTTPException(status_code=404, detail="Legal page not found")
        return legal_page
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LEGAL PAGE GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/legal-pages", dependencies=[Depends(check_permissions("author"))])
async def create_legal_page(
    legal_page: LegalPageCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new legal page"""
    try:
        page_dict = legal_page.dict()
        page_dict["id"] = str(uuid.uuid4())
        page_dict["slug"] = generate_slug(legal_page.title)
        page_dict["created_at"] = datetime.now(timezone.utc)
        page_dict["updated_at"] = datetime.now(timezone.utc)
        page_dict["last_updated"] = datetime.now(timezone.utc)
        page_dict["created_by"] = current_user.get("id")
        
        await db.legal_pages.insert_one(page_dict)
        return remove_id(page_dict)
    except Exception as e:
        print(f"[LEGAL PAGE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/legal-pages/{page_id}", dependencies=[Depends(check_permissions("author"))])
async def update_legal_page(
    page_id: str,
    legal_page: LegalPageUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing legal page"""
    try:
        existing = await db.legal_pages.find_one({"id": page_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Legal page not found")
        
        page_dict = legal_page.dict(exclude_unset=True)
        if legal_page.title:
            page_dict["slug"] = generate_slug(legal_page.title)
        page_dict["updated_at"] = datetime.now(timezone.utc)
        page_dict["last_updated"] = datetime.now(timezone.utc)
        
        await db.legal_pages.update_one(
            {"id": page_id},
            {"$set": page_dict}
        )
        
        updated = await db.legal_pages.find_one({"id": page_id})
        return remove_id(updated)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LEGAL PAGE UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/legal-pages/{page_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_legal_page(page_id: str):
    """Delete a legal page"""
    try:
        result = await db.legal_pages.delete_one({"id": page_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Legal page not found")
        return {"message": "Legal page deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LEGAL PAGE DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/legal-pages/{page_id}/toggle", dependencies=[Depends(check_permissions("author"))])
async def toggle_legal_page_published(page_id: str):
    """Toggle legal page published status"""
    try:
        legal_page = await db.legal_pages.find_one({"id": page_id})
        if not legal_page:
            raise HTTPException(status_code=404, detail="Legal page not found")
        
        new_status = not legal_page.get("is_published", False)
        await db.legal_pages.update_one(
            {"id": page_id},
            {"$set": {"is_published": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        
        return {"message": f"Legal page {'published' if new_status else 'unpublished'}", "is_published": new_status}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LEGAL PAGE TOGGLE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# REVIEW CATEGORY MANAGEMENT
# ==============================================================

@api_router.get("/review-categories")
async def get_review_categories_public():
    """Public endpoint - Get all active review categories"""
    try:
        categories = await db.review_categories.find({"is_active": True}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return categories
    except Exception as e:
        print(f"[REVIEW CATEGORIES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/review-categories", dependencies=[Depends(check_permissions("author"))])
async def get_all_review_categories_admin():
    """Admin endpoint - Get all review categories"""
    try:
        categories = await db.review_categories.find({}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return categories
    except Exception as e:
        print(f"[REVIEW CATEGORIES ADMIN GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/review-categories/{category_id}", dependencies=[Depends(check_permissions("author"))])
async def get_review_category_by_id(category_id: str):
    """Admin endpoint - Get review category by ID"""
    try:
        category = await db.review_categories.find_one({"id": category_id}, {"_id": 0})
        if not category:
            raise HTTPException(status_code=404, detail="Review category not found")
        return category
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REVIEW CATEGORY GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/review-categories", dependencies=[Depends(check_permissions("author"))])
async def create_review_category(
    category: ReviewCategoryCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new review category"""
    try:
        category_dict = category.dict()
        category_dict["id"] = str(uuid.uuid4())
        category_dict["slug"] = generate_slug(category.name)
        category_dict["created_at"] = datetime.now(timezone.utc)
        category_dict["updated_at"] = datetime.now(timezone.utc)
        
        await db.review_categories.insert_one(category_dict)
        return remove_id(category_dict)
    except Exception as e:
        print(f"[REVIEW CATEGORY CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/review-categories/{category_id}", dependencies=[Depends(check_permissions("author"))])
async def update_review_category(
    category_id: str,
    category: ReviewCategoryUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing review category"""
    try:
        existing = await db.review_categories.find_one({"id": category_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Review category not found")
        
        category_dict = category.dict(exclude_unset=True)
        if category.name:
            category_dict["slug"] = generate_slug(category.name)
        category_dict["updated_at"] = datetime.now(timezone.utc)
        
        await db.review_categories.update_one(
            {"id": category_id},
            {"$set": category_dict}
        )
        
        updated = await db.review_categories.find_one({"id": category_id})
        return remove_id(updated)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REVIEW CATEGORY UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/review-categories/{category_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_review_category(category_id: str):
    """Delete a review category"""
    try:
        result = await db.review_categories.delete_one({"id": category_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Review category not found")
        return {"message": "Review category deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REVIEW CATEGORY DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# OUTSOURCING CLIENT REVIEWS APIs
# ==============================================================

# ==============================================================================
# OUTSOURCING PARTNER PORTAL ENDPOINTS
# ==============================================================================

@api_router.post("/outsourcing/partner/login")
async def partner_login(data: dict):
    """Partner login for outsourcing dashboard"""
    try:
        email = data.get("email")
        password = data.get("password")
        
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")
        
        # Find partner by email
        partner = await db.outsourcing_partners.find_one({"email": email.lower()}, {"_id": 0})
        
        if not partner:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Check password
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        if not pwd_context.verify(password, partner.get("hashed_password", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Check if partner is active
        if partner.get("status") != "active":
            raise HTTPException(status_code=403, detail="Account is not active")
        
        # Generate token
        from jose import jwt
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        token_data = {
            "sub": email,
            "partner_id": partner.get("id"),
            "role": "partner",
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")
        
        # Update last login
        await db.outsourcing_partners.update_one(
            {"id": partner.get("id")},
            {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Remove sensitive data
        partner.pop("hashed_password", None)
        
        return {
            "success": True,
            "token": token,
            "partner": partner
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER LOGIN ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/outsourcing/partner/me")
async def get_partner_profile(authorization: str = Header(None)):
    """Get current partner profile"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from jose import jwt
        SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-in-production-credlocity-2025")
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        partner_id = payload.get("partner_id")
        
        if not partner_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        partner = await db.outsourcing_partners.find_one({"id": partner_id}, {"_id": 0, "hashed_password": 0})
        
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        return partner
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PARTNER PROFILE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/outsource/client-reviews")
async def get_public_outsource_client_reviews():
    """Public endpoint - Get all active outsourcing client reviews for the public page"""
    try:
        reviews = await db.outsource_client_reviews.find(
            {"is_active": True}, 
            {"_id": 0}
        ).sort("display_order", 1).to_list(length=None)
        return reviews
    except Exception as e:
        print(f"[OUTSOURCE REVIEWS PUBLIC GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/outsource/client-reviews/slug/{slug}")
async def get_public_outsource_client_review_by_slug(slug: str):
    """Public endpoint - Get a specific outsourcing client review by slug for individual SEO page"""
    try:
        review = await db.outsource_client_reviews.find_one(
            {"slug": slug, "is_active": True}, 
            {"_id": 0}
        )
        if not review:
            raise HTTPException(status_code=404, detail="Outsource client review not found")
        return review
    except HTTPException:
        raise
    except Exception as e:
        print(f"[OUTSOURCE REVIEW BY SLUG ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/outsource/client-reviews", dependencies=[Depends(check_permissions("author"))])
async def get_admin_outsource_client_reviews():
    """Admin endpoint - Get all outsourcing client reviews"""
    try:
        reviews = await db.outsource_client_reviews.find({}, {"_id": 0}).sort("display_order", 1).to_list(length=None)
        return reviews
    except Exception as e:
        print(f"[OUTSOURCE REVIEWS ADMIN GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/outsource/client-reviews/{review_id}", dependencies=[Depends(check_permissions("author"))])
async def get_outsource_client_review_by_id(review_id: str):
    """Admin endpoint - Get a specific outsourcing client review"""
    try:
        review = await db.outsource_client_reviews.find_one({"id": review_id}, {"_id": 0})
        if not review:
            raise HTTPException(status_code=404, detail="Outsource client review not found")
        return review
    except HTTPException:
        raise
    except Exception as e:
        print(f"[OUTSOURCE REVIEW GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/outsource/client-reviews", dependencies=[Depends(check_permissions("author"))])
async def create_outsource_client_review(
    review: dict,
    current_user: dict = Depends(get_current_user)
):
    """Create a new outsourcing client review"""
    try:
        # Generate slug from company name if not provided
        slug = review.get("slug", "")
        if not slug:
            slug = generate_slug(review.get("company_name", ""))
        
        review_data = {
            "id": str(uuid.uuid4()),
            "company_name": review.get("company_name", ""),
            "company_logo_url": review.get("company_logo_url", ""),
            "slug": slug,
            "ceo_name": review.get("ceo_name", ""),
            "ceo_photo_url": review.get("ceo_photo_url", ""),
            "ceo_title": review.get("ceo_title", "CEO"),
            "testimonial_text": review.get("testimonial_text", ""),
            "full_story": review.get("full_story", ""),
            "video_type": review.get("video_type"),
            "video_file_url": review.get("video_file_url", ""),
            "youtube_embed_url": review.get("youtube_embed_url", ""),
            "switched_from_another": review.get("switched_from_another", False),
            "previous_company_name": review.get("previous_company_name", ""),
            "why_they_switched": review.get("why_they_switched", ""),
            "results_stats": review.get("results_stats", {}),
            "seo_meta_title": review.get("seo_meta_title", ""),
            "seo_meta_description": review.get("seo_meta_description", ""),
            "seo_keywords": review.get("seo_keywords", ""),
            "display_order": review.get("display_order", 0),
            "is_active": review.get("is_active", True),
            "featured": review.get("featured", False),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "created_by": current_user.get("id")
        }
        
        await db.outsource_client_reviews.insert_one(review_data)
        return remove_id(review_data)
    except Exception as e:
        print(f"[OUTSOURCE REVIEW CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/outsource/client-reviews/{review_id}", dependencies=[Depends(check_permissions("author"))])
async def update_outsource_client_review(
    review_id: str,
    review_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update an outsourcing client review"""
    try:
        existing = await db.outsource_client_reviews.find_one({"id": review_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Outsource client review not found")
        
        update_data = {k: v for k, v in review_data.items() if v is not None}
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        await db.outsource_client_reviews.update_one(
            {"id": review_id},
            {"$set": update_data}
        )
        
        updated = await db.outsource_client_reviews.find_one({"id": review_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[OUTSOURCE REVIEW UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/outsource/client-reviews/{review_id}", dependencies=[Depends(check_permissions("author"))])
async def delete_outsource_client_review(review_id: str):
    """Delete an outsourcing client review"""
    try:
        result = await db.outsource_client_reviews.delete_one({"id": review_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Outsource client review not found")
        return {"message": "Outsource client review deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[OUTSOURCE REVIEW DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================
# CLIENT MANAGEMENT SYSTEM APIS
# ==============================================================

# ==================== CMS SETTINGS ====================
@api_router.get("/admin/cms-settings", dependencies=[Depends(check_permissions("author"))])
async def get_cms_settings():
    """Get all CMS settings"""
    try:
        settings = await db.cms_settings.find({}, {"_id": 0}).to_list(None)
        return settings
    except Exception as e:
        print(f"[CMS SETTINGS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/cms-settings/{setting_key}", dependencies=[Depends(check_permissions("author"))])
async def get_cms_setting(setting_key: str):
    """Get a specific CMS setting"""
    try:
        setting = await db.cms_settings.find_one({"setting_key": setting_key}, {"_id": 0})
        if not setting:
            return {"setting_key": setting_key, "setting_value": None}
        return setting
    except Exception as e:
        print(f"[CMS SETTING GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/cms-settings/{setting_key}", dependencies=[Depends(check_permissions("editor"))])
async def update_cms_setting(setting_key: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update or create a CMS setting"""
    try:
        setting_data = {
            "setting_key": setting_key,
            "setting_value": data.get("setting_value"),
            "setting_type": data.get("setting_type", "string"),
            "description": data.get("description"),
            "updated_by": current_user["id"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        existing = await db.cms_settings.find_one({"setting_key": setting_key})
        if existing:
            await db.cms_settings.update_one({"setting_key": setting_key}, {"$set": setting_data})
        else:
            setting_data["id"] = str(uuid.uuid4())
            await db.cms_settings.insert_one(setting_data)
        
        updated = await db.cms_settings.find_one({"setting_key": setting_key}, {"_id": 0})
        return updated
    except Exception as e:
        print(f"[CMS SETTING UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CALENDARS (Round Robin) ====================
@api_router.get("/admin/calendars", dependencies=[Depends(check_permissions("author"))])
async def get_calendars():
    """Get all calendars for round-robin scheduling"""
    try:
        calendars = await db.client_calendars.find({}, {"_id": 0}).to_list(None)
        return calendars
    except Exception as e:
        print(f"[CALENDARS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/calendars", dependencies=[Depends(check_permissions("editor"))])
async def create_calendar(calendar: dict):
    """Create a new calendar for round-robin"""
    try:
        calendar_data = {
            "id": str(uuid.uuid4()),
            "name": calendar.get("name"),
            "url": calendar.get("url"),
            "owner_name": calendar.get("owner_name"),
            "is_active": calendar.get("is_active", True),
            "weight": calendar.get("weight", 1),
            "last_assigned": None,
            "total_assignments": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.client_calendars.insert_one(calendar_data)
        calendar_data.pop("_id", None)
        return calendar_data
    except Exception as e:
        print(f"[CALENDAR CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/calendars/{calendar_id}", dependencies=[Depends(check_permissions("editor"))])
async def update_calendar(calendar_id: str, calendar: dict):
    """Update a calendar"""
    try:
        update_data = {k: v for k, v in calendar.items() if v is not None and k != "id"}
        result = await db.client_calendars.update_one({"id": calendar_id}, {"$set": update_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Calendar not found")
        updated = await db.client_calendars.find_one({"id": calendar_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CALENDAR UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/calendars/{calendar_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_calendar(calendar_id: str):
    """Delete a calendar"""
    try:
        result = await db.client_calendars.delete_one({"id": calendar_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Calendar not found")
        return {"message": "Calendar deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CALENDAR DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/calendars/next", dependencies=[Depends(check_permissions("author"))])
async def get_next_calendar():
    """Get next calendar using weighted round-robin"""
    try:
        calendars = await db.client_calendars.find({"is_active": True}, {"_id": 0}).to_list(None)
        if not calendars:
            # Return default calendly link if no calendars configured
            default_setting = await db.cms_settings.find_one({"setting_key": "default_calendar_url"}, {"_id": 0})
            return {"url": default_setting.get("setting_value") if default_setting else "https://calendly.com/credlocity/oneonone"}
        
        # Simple weighted round-robin: pick calendar with lowest (assignments / weight)
        best = min(calendars, key=lambda c: c.get("total_assignments", 0) / max(c.get("weight", 1), 1))
        
        # Update assignment count
        await db.client_calendars.update_one(
            {"id": best["id"]},
            {"$inc": {"total_assignments": 1}, "$set": {"last_assigned": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {"id": best["id"], "url": best["url"], "name": best.get("name")}
    except Exception as e:
        print(f"[NEXT CALENDAR ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== INTAKE FORM CONFIGS ====================
@api_router.get("/admin/intake-forms", dependencies=[Depends(check_permissions("author"))])
async def get_intake_forms():
    """Get all intake form configurations"""
    try:
        forms = await db.intake_forms.find({}, {"_id": 0}).to_list(None)
        return forms
    except Exception as e:
        print(f"[INTAKE FORMS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/intake-forms/{form_id}", dependencies=[Depends(check_permissions("author"))])
async def get_intake_form(form_id: str):
    """Get a specific intake form configuration"""
    try:
        form = await db.intake_forms.find_one({"id": form_id}, {"_id": 0})
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        return form
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INTAKE FORM GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/intake-forms/by-slug/{slug}")
async def get_intake_form_by_slug(slug: str):
    """Get intake form config by slug (public endpoint for frontend)"""
    try:
        form = await db.intake_forms.find_one({"slug": slug, "is_active": True}, {"_id": 0})
        if not form:
            # Return default config if no form found
            return {
                "id": "default",
                "name": "Default Intake Form",
                "slug": slug,
                "is_active": True,
                "header_title": "Unlock Your Credit Potential",
                "header_subtitle": "Take our 2-minute assessment to discover your personalized path to financial freedom",
                "credit_report_url": "https://credlocity.scorexer.com/scorefusion/scorefusion-signup.jsp?code=50a153cc-c",
                "credit_report_button_text": "Get My Credit Report ($49.95)",
                "calendar_ids": [],
                "default_calendar_url": "https://calendly.com/credlocity/oneonone",
                "warm_lead_button_text": "Schedule My Free Strategy Session",
                "cold_lead_button_text": "Get My Free Consultation",
                "packages": [
                    {"key": "fraud", "name": "Fraud Protection Plan", "price": 99.95, "description": "Perfect for recent identity theft victims"},
                    {"key": "aggressive", "name": "Aggressive Package", "price": 179.95, "description": "Our most popular comprehensive plan"},
                    {"key": "family", "name": "Family Plan", "price": 279.95, "description": "Coverage for you and your spouse"}
                ],
                "credit_report_fee": 49.95,
                "enotary_fee": 39.95,
                "crm_enabled": True,
                "crm_tab_info_id": "QTduWHF0U2lXOWNPNFZvN085bUJ3dz09",
                "crm_company_id": "UmJ1YWN4dkUvbThaUXJqVkdKZ3paUT09"
            }
        return form
    except Exception as e:
        print(f"[INTAKE FORM BY SLUG ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/intake-forms", dependencies=[Depends(check_permissions("editor"))])
async def create_intake_form(form_data: dict, current_user: dict = Depends(get_current_user)):
    """Create a new intake form configuration"""
    try:
        # Check if slug already exists
        existing = await db.intake_forms.find_one({"slug": form_data.get("slug")})
        if existing:
            raise HTTPException(status_code=400, detail="A form with this slug already exists")
        
        form = {
            "id": str(uuid.uuid4()),
            "name": form_data.get("name", "New Intake Form"),
            "slug": form_data.get("slug", "intake"),
            "description": form_data.get("description"),
            "is_active": form_data.get("is_active", True),
            "header_title": form_data.get("header_title", "Unlock Your Credit Potential"),
            "header_subtitle": form_data.get("header_subtitle", "Take our 2-minute assessment to discover your personalized path to financial freedom"),
            "credit_report_url": form_data.get("credit_report_url", "https://credlocity.scorexer.com/scorefusion/scorefusion-signup.jsp?code=50a153cc-c"),
            "credit_report_button_text": form_data.get("credit_report_button_text", "Get My Credit Report ($49.95)"),
            "calendar_ids": form_data.get("calendar_ids", []),
            "default_calendar_url": form_data.get("default_calendar_url", "https://calendly.com/credlocity/oneonone"),
            "warm_lead_button_text": form_data.get("warm_lead_button_text", "Schedule My Free Strategy Session"),
            "cold_lead_button_text": form_data.get("cold_lead_button_text", "Get My Free Consultation"),
            "packages": form_data.get("packages", [
                {"key": "fraud", "name": "Fraud Protection Plan", "price": 99.95, "description": "Perfect for recent identity theft victims"},
                {"key": "aggressive", "name": "Aggressive Package", "price": 179.95, "description": "Our most popular comprehensive plan"},
                {"key": "family", "name": "Family Plan", "price": 279.95, "description": "Coverage for you and your spouse"}
            ]),
            "credit_report_fee": form_data.get("credit_report_fee", 49.95),
            "enotary_fee": form_data.get("enotary_fee", 39.95),
            "crm_enabled": form_data.get("crm_enabled", True),
            "crm_tab_info_id": form_data.get("crm_tab_info_id", "QTduWHF0U2lXOWNPNFZvN085bUJ3dz09"),
            "crm_company_id": form_data.get("crm_company_id", "UmJ1YWN4dkUvbThaUXJqVkdKZ3paUT09"),
            "created_by": current_user.get("full_name", "Unknown"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.intake_forms.insert_one(form)
        form.pop("_id", None)
        return form
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INTAKE FORM CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/intake-forms/{form_id}", dependencies=[Depends(check_permissions("editor"))])
async def update_intake_form(form_id: str, form_data: dict, current_user: dict = Depends(get_current_user)):
    """Update an intake form configuration"""
    try:
        existing = await db.intake_forms.find_one({"id": form_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Check slug uniqueness if changing
        if form_data.get("slug") and form_data.get("slug") != existing.get("slug"):
            slug_exists = await db.intake_forms.find_one({"slug": form_data.get("slug"), "id": {"$ne": form_id}})
            if slug_exists:
                raise HTTPException(status_code=400, detail="A form with this slug already exists")
        
        update_data = {k: v for k, v in form_data.items() if v is not None and k not in ["id", "created_at", "created_by"]}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.intake_forms.update_one({"id": form_id}, {"$set": update_data})
        updated = await db.intake_forms.find_one({"id": form_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INTAKE FORM UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/intake-forms/{form_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_intake_form(form_id: str):
    """Delete an intake form configuration"""
    try:
        result = await db.intake_forms.delete_one({"id": form_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Form not found")
        return {"message": "Form deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INTAKE FORM DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/intake-forms/{form_id}/duplicate", dependencies=[Depends(check_permissions("editor"))])
async def duplicate_intake_form(form_id: str, current_user: dict = Depends(get_current_user)):
    """Duplicate an existing intake form"""
    try:
        original = await db.intake_forms.find_one({"id": form_id}, {"_id": 0})
        if not original:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Create duplicate with new ID and modified name/slug
        duplicate = original.copy()
        duplicate["id"] = str(uuid.uuid4())
        duplicate["name"] = f"{original['name']} (Copy)"
        duplicate["slug"] = f"{original['slug']}-copy-{str(uuid.uuid4())[:8]}"
        duplicate["is_active"] = False  # Duplicates start inactive
        duplicate["created_by"] = current_user.get("full_name", "Unknown")
        duplicate["created_at"] = datetime.now(timezone.utc).isoformat()
        duplicate["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.intake_forms.insert_one(duplicate)
        duplicate.pop("_id", None)
        return duplicate
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INTAKE FORM DUPLICATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CLIENTS ====================
def calculate_lead_score(data: dict) -> tuple:
    """Calculate lead score and status based on assessment answers"""
    score = 0
    
    # Credit score mapping (form sends 'creditScore')
    credit_scores = {"poor": 12, "fair": 10, "good": 6, "excellent": 3, "unknown": 9}
    score += credit_scores.get(data.get("creditScore") or data.get("credit_score_range", ""), 0)
    
    # Timeline mapping
    timeline_scores = {"asap": 12, "1-3months": 10, "3-6months": 7, "6months+": 4}
    score += timeline_scores.get(data.get("timeline", ""), 0)
    
    # Package/Budget mapping (form sends 'budget')
    budget_scores = {"family": 12, "aggressive": 11, "fraud": 9, "payment-plan": 8, "unsure": 7}
    score += budget_scores.get(data.get("budget") or data.get("selected_package", ""), 0)
    
    # Experience mapping
    experience_scores = {"never": 8, "diy": 11, "other-company": 12, "currently-using": 9}
    score += experience_scores.get(data.get("experience", ""), 0)
    
    # Decision maker mapping (form sends 'decision')
    decision_scores = {"me-alone": 12, "discuss-spouse": 9, "spouse-decides": 6, "family-input": 4}
    score += decision_scores.get(data.get("decision") or data.get("decision_maker", ""), 0)
    
    # Determine lead status
    if score >= 37:
        status = "hot"
    elif score >= 25:
        status = "warm"
    else:
        status = "cold"
    
    return score, status


def get_package_details(package_key: str) -> tuple:
    """Get package name and price"""
    packages = {
        "family": ("Family Package", 279.95),
        "aggressive": ("Aggressive Package", 179.95),
        "fraud": ("Fraud Package", 99.95),
        "payment-plan": ("Flexible Payment Plan", 99.95),
        "unsure": ("To Be Determined", 0)
    }
    return packages.get(package_key, ("To Be Determined", 0))


@api_router.get("/admin/clients", dependencies=[Depends(check_permissions("author"))])
async def get_clients(
    lead_status: Optional[str] = None,
    status: Optional[str] = None,
    days: Optional[int] = None
):
    """Get all clients with optional filters"""
    try:
        query = {}
        if lead_status:
            query["lead_status"] = lead_status
        if status:
            query["status"] = status
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            query["created_at"] = {"$gte": cutoff.isoformat()}
        
        clients = await db.clients.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)
        return clients
    except Exception as e:
        print(f"[CLIENTS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/clients/stats", dependencies=[Depends(check_permissions("author"))])
async def get_client_stats():
    """Get client statistics for dashboard"""
    try:
        now = datetime.now(timezone.utc)
        
        # Total clients
        total = await db.clients.count_documents({})
        
        # Clients by lead status
        hot = await db.clients.count_documents({"lead_status": "hot"})
        warm = await db.clients.count_documents({"lead_status": "warm"})
        cold = await db.clients.count_documents({"lead_status": "cold"})
        
        # Clients by time period
        last_7_days = await db.clients.count_documents({
            "created_at": {"$gte": (now - timedelta(days=7)).isoformat()}
        })
        last_15_days = await db.clients.count_documents({
            "created_at": {"$gte": (now - timedelta(days=15)).isoformat()}
        })
        last_30_days = await db.clients.count_documents({
            "created_at": {"$gte": (now - timedelta(days=30)).isoformat()}
        })
        
        # Upfront income (credit report + e-notary fees for those who signed)
        signed_clients = await db.clients.find({"agreement_signed": True}, {"_id": 0}).to_list(None)
        upfront_income = sum(
            (c.get("credit_report_fee", 49.95) if c.get("credit_report_paid") else 0) +
            (c.get("enotary_fee", 39.95) if c.get("enotary_paid") else 0)
            for c in signed_clients
        )
        
        # Potential upfront income (all signed clients)
        potential_upfront = len(signed_clients) * (49.95 + 39.95)
        
        # Estimated monthly income after trial (based on selected packages)
        monthly_income = sum(c.get("package_price", 0) or 0 for c in signed_clients)
        
        # Clients by 7/15/30 with their income projections
        clients_7 = await db.clients.find({
            "created_at": {"$gte": (now - timedelta(days=7)).isoformat()}
        }, {"_id": 0}).to_list(None)
        
        clients_15 = await db.clients.find({
            "created_at": {"$gte": (now - timedelta(days=15)).isoformat()}
        }, {"_id": 0}).to_list(None)
        
        clients_30 = await db.clients.find({
            "created_at": {"$gte": (now - timedelta(days=30)).isoformat()}
        }, {"_id": 0}).to_list(None)
        
        def calc_income(clients_list):
            upfront = sum(c.get("credit_report_fee", 49.95) + c.get("enotary_fee", 39.95) for c in clients_list if c.get("agreement_signed"))
            monthly = sum(c.get("package_price", 0) or 0 for c in clients_list if c.get("agreement_signed"))
            return {"upfront": upfront, "monthly": monthly}
        
        return {
            "total": total,
            "by_lead_status": {"hot": hot, "warm": warm, "cold": cold},
            "by_period": {
                "last_7_days": {"count": last_7_days, "income": calc_income(clients_7)},
                "last_15_days": {"count": last_15_days, "income": calc_income(clients_15)},
                "last_30_days": {"count": last_30_days, "income": calc_income(clients_30)}
            },
            "income": {
                "upfront_collected": upfront_income,
                "upfront_potential": potential_upfront,
                "monthly_after_trial": monthly_income
            },
            "converted": await db.clients.count_documents({"status": "converted"}),
            "pending_consultation": await db.clients.count_documents({"status": "consultation_scheduled"})
        }
    except Exception as e:
        print(f"[CLIENT STATS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/clients/{client_id}", dependencies=[Depends(check_permissions("author"))])
async def get_client(client_id: str):
    """Get a single client by ID"""
    try:
        client = await db.clients.find_one({"id": client_id}, {"_id": 0})
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CLIENT GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/clients/intake")
async def create_client_from_intake(data: dict):
    """Create a new client from intake form (public endpoint - no auth required)"""
    try:
        # Calculate lead score
        score, lead_status = calculate_lead_score(data)
        
        # Get package details - check both frontend fields and budget field
        # Frontend sends packageName/packagePrice directly, or budget field for step 3 selection
        if data.get("packageName") and data.get("packagePrice"):
            package_name = data.get("packageName")
            package_price = float(data.get("packagePrice", 0))
        else:
            package_name, package_price = get_package_details(data.get("budget", ""))
        
        client_data = {
            "id": str(uuid.uuid4()),
            "first_name": data.get("firstName", ""),
            "last_name": data.get("lastName", ""),
            "email": data.get("email", ""),
            "phone": data.get("mobilePhone", ""),
            "date_of_birth": data.get("dateOfBirth"),
            "ssn_last4": data.get("socialSecurityNumber"),
            
            # Assessment answers
            "credit_score_range": data.get("creditScore"),
            "timeline": data.get("timeline"),
            "selected_package": data.get("budget"),
            "experience": data.get("experience"),
            "decision_maker": data.get("decision"),
            
            # Lead scoring
            "assessment_score": score,
            "lead_status": lead_status,
            
            # Package info
            "package_name": package_name,
            "package_price": package_price,
            
            # Agreement info
            "agreement_signed": data.get("agreementAcceptance", False),
            "agreement_signed_at": datetime.now(timezone.utc).isoformat() if data.get("agreementAcceptance") else None,
            "electronic_signature": data.get("electronicSignature"),
            "signature_ip": data.get("ipAddress"),
            
            # Status
            "status": "new",
            "consent_given": data.get("consent", True),
            "source": "intake_form",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.clients.insert_one(client_data)
        
        # If agreement was signed, create agreement record and generate PDF
        if data.get("agreementAcceptance") and data.get("electronicSignature"):
            agreement_data = {
                "id": str(uuid.uuid4()),
                "client_id": client_data["id"],
                "agreement_type": "free_trial",
                "agreement_version": "1.0",
                "package_name": package_name,
                "package_price": package_price,
                "credit_report_fee": 49.95,
                "enotary_fee": 39.95,
                "electronic_signature": data.get("electronicSignature"),
                "signature_date": data.get("agreementDate", datetime.now(timezone.utc).strftime("%B %d, %Y")),
                "signature_ip": data.get("ipAddress", ""),
                "signature_timestamp": datetime.now(timezone.utc).isoformat(),
                "federal_cancel_date": data.get("federalCancelDate", ""),
                "pa_state_cancel_date": data.get("paStateCancelDate"),
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Generate PDF and store as base64
            try:
                client_for_pdf = {
                    "first_name": data.get("firstName", ""),
                    "last_name": data.get("lastName", ""),
                    "email": data.get("email", ""),
                    "phone": data.get("mobilePhone", "")
                }
                pdf_bytes = generate_agreement_pdf(client_for_pdf, agreement_data)
                agreement_data["document_content"] = base64.b64encode(pdf_bytes).decode('utf-8')
            except Exception as pdf_error:
                print(f"[PDF GENERATION WARNING] Could not generate PDF: {pdf_error}")
            
            await db.client_agreements.insert_one(agreement_data)
            
            # Update client with agreement ID
            await db.clients.update_one(
                {"id": client_data["id"]},
                {"$set": {"agreement_document_id": agreement_data["id"]}}
            )
        
        # Get form configuration if form_slug is provided
        form_config = None
        form_slug = data.get("form_slug")
        if form_slug:
            form_config = await db.intake_forms.find_one({"slug": form_slug, "is_active": True}, {"_id": 0})
        
        # Get redirect URL based on lead status
        redirect_data = {}
        if lead_status == "hot":
            # Use form-specific credit report URL if available, otherwise use CMS setting
            if form_config and form_config.get("credit_report_url"):
                redirect_data["redirect_url"] = form_config["credit_report_url"]
                redirect_data["cta"] = form_config.get("credit_report_button_text", "Get My Credit Report ($49.95)")
            else:
                credit_report_setting = await db.cms_settings.find_one({"setting_key": "credit_report_url"}, {"_id": 0})
                redirect_data["redirect_url"] = credit_report_setting.get("setting_value") if credit_report_setting else "https://credlocity.scorexer.com/scorefusion/scorefusion-signup.jsp?code=50a153cc-c"
                redirect_data["cta"] = "Get My Credit Report ($49.95)"
        else:
            # Get calendars - use form-specific calendars if configured, otherwise all active calendars
            form_calendar_ids = form_config.get("calendar_ids", []) if form_config else []
            
            if form_calendar_ids:
                # Use only the calendars assigned to this form
                calendars = await db.client_calendars.find(
                    {"id": {"$in": form_calendar_ids}, "is_active": True}, 
                    {"_id": 0}
                ).to_list(None)
            else:
                # Fallback to all active calendars
                calendars = await db.client_calendars.find({"is_active": True}, {"_id": 0}).to_list(None)
            
            if calendars:
                # Round-robin based on weight
                best = min(calendars, key=lambda c: c.get("total_assignments", 0) / max(c.get("weight", 1), 1))
                await db.client_calendars.update_one(
                    {"id": best["id"]},
                    {"$inc": {"total_assignments": 1}, "$set": {"last_assigned": datetime.now(timezone.utc).isoformat()}}
                )
                redirect_data["redirect_url"] = best["url"]
                redirect_data["assigned_calendar_id"] = best["id"]
            else:
                # Use form's default calendar or global setting
                if form_config and form_config.get("default_calendar_url"):
                    redirect_data["redirect_url"] = form_config["default_calendar_url"]
                else:
                    default_cal = await db.cms_settings.find_one({"setting_key": "default_calendar_url"}, {"_id": 0})
                    redirect_data["redirect_url"] = default_cal.get("setting_value") if default_cal else "https://calendly.com/credlocity/oneonone"
            
            # Use form-specific button text if available
            if form_config:
                redirect_data["cta"] = form_config.get("warm_lead_button_text", "Schedule My Free Strategy Session") if lead_status == "warm" else form_config.get("cold_lead_button_text", "Get My Free Consultation")
            else:
                redirect_data["cta"] = "Schedule My Free Strategy Session" if lead_status == "warm" else "Get My Free Consultation"
        
        client_data.pop("_id", None)
        return {
            "success": True,
            "client_id": client_data["id"],
            "lead_status": lead_status,
            "score": score,
            **redirect_data
        }
    except Exception as e:
        print(f"[CLIENT INTAKE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/clients/{client_id}", dependencies=[Depends(check_permissions("author"))])
async def update_client(client_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a client"""
    try:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_data = {k: v for k, v in data.items() if v is not None and k != "id"}
        
        result = await db.clients.update_one({"id": client_id}, {"$set": update_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Client not found")
        
        updated = await db.clients.find_one({"id": client_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CLIENT UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/clients/{client_id}", dependencies=[Depends(check_permissions("editor"))])
async def delete_client(client_id: str):
    """Delete a client"""
    try:
        result = await db.clients.delete_one({"id": client_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Client not found")
        # Also delete related records
        await db.client_agreements.delete_many({"client_id": client_id})
        await db.client_notes.delete_many({"client_id": client_id})
        await db.client_credits.delete_many({"client_id": client_id})
        return {"message": "Client deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CLIENT DELETE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CLIENT AGREEMENTS ====================
@api_router.get("/admin/clients/{client_id}/agreements", dependencies=[Depends(check_permissions("author"))])
async def get_client_agreements(client_id: str):
    """Get all agreements for a client"""
    try:
        agreements = await db.client_agreements.find({"client_id": client_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
        return agreements
    except Exception as e:
        print(f"[CLIENT AGREEMENTS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/clients/{client_id}/agreements/{agreement_id}", dependencies=[Depends(check_permissions("author"))])
async def get_client_agreement(client_id: str, agreement_id: str):
    """Get a specific agreement"""
    try:
        agreement = await db.client_agreements.find_one({"id": agreement_id, "client_id": client_id}, {"_id": 0})
        if not agreement:
            raise HTTPException(status_code=404, detail="Agreement not found")
        return agreement
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CLIENT AGREEMENT GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_agreement_pdf(client: dict, agreement: dict) -> bytes:
    """Generate a PDF agreement document with all required legal notices"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    
    styles = getSampleStyleSheet()
    # Use unique style names to avoid conflicts with default stylesheet
    styles.add(ParagraphStyle(name='AgreementCenter', alignment=TA_CENTER, fontSize=12, spaceAfter=10))
    styles.add(ParagraphStyle(name='AgreementTitle', alignment=TA_CENTER, fontSize=16, spaceAfter=15, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='AgreementHeading', fontSize=11, spaceAfter=6, spaceBefore=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#166534')))
    styles.add(ParagraphStyle(name='AgreementSubHeading', fontSize=10, spaceAfter=4, spaceBefore=8, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='AgreementBody', fontSize=9, spaceAfter=6, alignment=TA_JUSTIFY, leading=12))
    styles.add(ParagraphStyle(name='AgreementSmall', fontSize=8, spaceAfter=4, leading=10))
    styles.add(ParagraphStyle(name='SignatureStyle', fontSize=12, fontName='Times-Italic', spaceAfter=4))
    
    # Company info constants
    COMPANY_NAME = "Credlocity Business Group LLC"
    COMPANY_ADDRESS = "1500 Chestnut Street, Suite 2"
    COMPANY_CITY = "Philadelphia"
    COMPANY_STATE = "PA"
    COMPANY_POSTCODE = "19102"
    
    # Client info
    full_name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()
    client_address = client.get('address', '')
    client_city = client.get('city', '')
    client_state = client.get('state', '')
    client_postal = client.get('postal_code', '')
    signature = agreement.get('electronic_signature', full_name)
    signature_date = agreement.get('signature_date', 'N/A')
    signature_ip = agreement.get('signature_ip', 'N/A')
    federal_cancel = agreement.get('federal_cancel_date', 'N/A')
    pa_cancel = agreement.get('pa_state_cancel_date', 'N/A')
    
    story = []
    
    # ==================== HEADER ====================
    story.append(Paragraph("CREDLOCITY BUSINESS GROUP LLC", styles['AgreementTitle']))
    story.append(Paragraph("America's Most Trusted Credit Repair Company", styles['AgreementCenter']))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#166534')))
    story.append(Spacer(1, 15))
    
    # ==================== AGREEMENT TITLE ====================
    story.append(Paragraph("FREE TRIAL CREDIT REPAIR SERVICE AGREEMENT", styles['AgreementTitle']))
    story.append(Paragraph(f"Agreement Date: {signature_date}", styles['AgreementCenter']))
    story.append(Spacer(1, 15))
    
    # ==================== PARTIES ====================
    story.append(Paragraph(
        f"This Free Trial Credit Repair Service Agreement (\"Agreement\") is entered into between "
        f"<b>{full_name}</b> (\"Client\" or \"You\") and <b>{COMPANY_NAME}</b> "
        f"(\"Company,\" \"We,\" or \"Us\"), a credit repair organization as defined under the "
        f"Credit Repair Organizations Act, 15 U.S.C. § 1679 et seq.",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 10))
    
    # ==================== SERVICES ====================
    story.append(Paragraph("1. SERVICES TO BE PROVIDED", styles['AgreementHeading']))
    story.append(Paragraph("The Company agrees to provide credit repair services to the Client, which may include:", styles['AgreementBody']))
    services = [
        "• Comprehensive analysis of your credit reports from Equifax, Experian, and TransUnion",
        "• Identification of inaccurate, unverifiable, outdated, or erroneous information",
        "• Preparation and submission of dispute letters to credit bureaus and creditors",
        "• Communication with credit bureaus and creditors on your behalf",
        "• Credit education and counseling",
        "• Monthly progress reports and updates",
        "• Access to client portal for real-time tracking"
    ]
    for service in services:
        story.append(Paragraph(service, styles['AgreementSmall']))
    
    # ==================== FREE TRIAL ====================
    story.append(Paragraph("2. FREE TRIAL PERIOD - 30 DAYS AT NO CHARGE", styles['AgreementHeading']))
    story.append(Paragraph(
        "<b>YOU ARE NOT BEING CHARGED FOR CREDIT REPAIR SERVICES.</b> This agreement provides you with "
        "a <b>30-day FREE TRIAL</b> of our credit repair services beginning from the date you sign this agreement.",
        styles['AgreementBody']
    ))
    
    # ==================== PACKAGE DETAILS ====================
    story.append(Paragraph("3. SELECTED PACKAGE & PRICING", styles['AgreementHeading']))
    package_data = [
        ['Package Selected:', agreement.get('package_name', 'To Be Determined')],
        ['Monthly Price (after trial):', f"${agreement.get('package_price', 0):.2f}/month"],
        ['Credit Report Fee:', f"${agreement.get('credit_report_fee', 49.95):.2f} (one-time)"],
        ['E-Notary Fee:', f"${agreement.get('enotary_fee', 39.95):.2f} (one-time)"],
        ['Total Upfront:', f"${(agreement.get('credit_report_fee', 49.95) + agreement.get('enotary_fee', 39.95)):.2f}"],
    ]
    table = Table(package_data, colWidths=[2.2*inch, 2.8*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0FDF4')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#166534')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    
    # ==================== PENNSYLVANIA STATE NOTICE ====================
    story.append(Paragraph("PENNSYLVANIA STATE NOTICE", styles['AgreementHeading']))
    story.append(Paragraph("<b>Pennsylvania law requires that we inform you of the following:</b>", styles['AgreementBody']))
    story.append(Paragraph(
        "\"You, the buyer, may cancel this contract at any time prior to 12 midnight of the fifth day after "
        "the date of the transaction. See the attached notice of cancellation form for an explanation of this right.\"",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 8))
    
    # PA Notice of Cancellation
    story.append(Paragraph("<b>Notice of Cancellation</b>", styles['AgreementSubHeading']))
    story.append(Paragraph(
        "You may cancel this contract without any penalty or obligation within five days from the date the contract is signed.",
        styles['AgreementBody']
    ))
    story.append(Paragraph(
        "If you cancel, any payment made by you under this contract will be returned within 15 days following "
        "receipt by the seller of your cancellation notice.",
        styles['AgreementBody']
    ))
    story.append(Paragraph(
        f"To cancel this contract, mail or deliver a signed and dated copy of this cancellation notice or "
        f"any other written notice to <b>{COMPANY_NAME}</b> at:",
        styles['AgreementBody']
    ))
    story.append(Paragraph(f"<b>{COMPANY_ADDRESS}, {COMPANY_CITY}, {COMPANY_STATE} {COMPANY_POSTCODE}</b>", styles['AgreementBody']))
    story.append(Paragraph(f"not later than 12 midnight <b>{pa_cancel}</b>.", styles['AgreementBody']))
    story.append(Spacer(1, 6))
    story.append(Paragraph("I hereby cancel this transaction,", styles['AgreementBody']))
    story.append(Paragraph("Date: _________________________", styles['AgreementBody']))
    story.append(Paragraph("Client Signature: _________________________", styles['AgreementBody']))
    story.append(Spacer(1, 10))
    
    # ==================== CONSUMER CREDIT FILE RIGHTS ====================
    story.append(Paragraph("CONSUMER CREDIT FILE RIGHTS UNDER STATE AND FEDERAL LAW", styles['AgreementHeading']))
    
    credit_rights_text = [
        "You have a right to dispute inaccurate information in your credit report by contacting the credit bureau directly. "
        "However, neither you nor any 'credit repair' company or credit repair organization has the right to have accurate, "
        "current, and verifiable information removed from your credit report. The credit bureau must remove accurate, negative "
        "information from your report only if it is over 7 years old. Bankruptcy information can be reported for 10 years.",
        
        "You have a right to obtain a copy of your credit report from a credit bureau. You may be charged a reasonable fee. "
        "There is no fee, however, if you have been turned down for credit, employment, insurance, or a rental dwelling because "
        "of information in your credit report within the preceding 60 days. The credit bureau must provide someone to help you "
        "interpret the information in your credit file. You are entitled to receive a free copy of your credit report if you are "
        "unemployed and intend to apply for employment in the next 60 days, if you are a recipient of public welfare assistance, "
        "or if you have reason to believe that there is inaccurate information in your credit report due to fraud.",
        
        "You have a right to sue a credit repair organization that violates the Credit Repair Organization Act. This law prohibits "
        "deceptive practices by credit repair organizations.",
        
        "You have the right to cancel your contract with any credit repair organization for any reason within 3 business days "
        "from the date you signed it.",
        
        "Credit bureaus are required to follow reasonable procedures to ensure that the information they report is accurate. "
        "However, mistakes may occur.",
        
        "You may, on your own, notify a credit bureau in writing that you dispute the accuracy of information in your credit file. "
        "The credit bureau must then reinvestigate and modify or remove inaccurate or incomplete information. The credit bureau may "
        "not charge any fee for this service. Any pertinent information and copies of all documents you have concerning an error "
        "should be given to the credit bureau.",
        
        "If the credit bureau's reinvestigation does not resolve the dispute to your satisfaction, you may send a brief statement "
        "to the credit bureau, to be kept in your file, explaining why you think the record is inaccurate. The credit bureau must "
        "include a summary of your statement about disputed information with any report it issues about you.",
        
        "The Federal Trade Commission regulates credit bureaus and credit repair organizations. For more information contact:",
        
        "The Public Reference Branch, Federal Trade Commission, Washington, D.C. 20580"
    ]
    
    for para in credit_rights_text:
        story.append(Paragraph(para, styles['AgreementSmall']))
    story.append(Spacer(1, 10))
    
    # ==================== FEDERAL NOTICE OF RIGHT TO CANCEL ====================
    story.append(Paragraph("NOTICE OF RIGHT TO CANCEL", styles['AgreementHeading']))
    story.append(Paragraph(
        f"You may cancel this contract, without any penalty or obligation, at any time before midnight of the 3rd day "
        f"which begins after the date the contract is signed by you. That day is <b>{federal_cancel}</b>.",
        styles['AgreementBody']
    ))
    story.append(Paragraph(
        f"To cancel this contract, mail or deliver a signed, dated copy of this cancellation notice, or any other written "
        f"notice to <b>{COMPANY_NAME}</b>, {COMPANY_ADDRESS}, {COMPANY_CITY}, {COMPANY_STATE} {COMPANY_POSTCODE}, before "
        f"midnight on the 3rd day which begins after the date you have signed this contract stating "
        f"\"I hereby cancel this transaction, (date) (purchaser's signature).\"",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Your signature on this service agreement is acknowledgement of your receipt of this notice by electronically "
        "signing the form indicated below.",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 10))
    
    # ==================== ACKNOWLEDGMENT OF RECEIPT ====================
    story.append(Paragraph("ACKNOWLEDGMENT OF RECEIPT OF NOTICE", styles['AgreementHeading']))
    story.append(Paragraph(
        f"I, <b>{full_name}</b>, hereby acknowledge with my digital signature, receipt of the Notice of Right to Cancel. "
        f"I confirm the fact that I agree and understand what I am signing, and acknowledge that I have received a copy of my Consumer Credit File Rights.",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "*Digital Signatures: In 2000, the U.S. Electronic Signatures in Global and National Commerce (ESIGN) Act established "
        "electronic records and signatures as legally binding, having the same legal effects as traditional paper documents and "
        "handwritten signatures. Read more at the FTC web site: http://www.ftc.gov/os/2001/06/esign7.htm",
        styles['AgreementSmall']
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"I further understand and agree that I <b>{full_name}</b> may request <b>{COMPANY_NAME}</b> send me a separate notice of right to cancel.",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 10))
    
    # First signature block
    sig_table1 = Table([
        [f'{signature}', signature_date],
        ['Client Signature', 'Date']
    ], colWidths=[3*inch, 2*inch])
    sig_table1.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Italic'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('FONTSIZE', (0, 1), (-1, 1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.black),
    ]))
    story.append(sig_table1)
    story.append(Spacer(1, 15))
    
    # ==================== DIGITAL SIGNATURES ACKNOWLEDGMENT ====================
    story.append(Paragraph("DIGITAL SIGNATURES ACKNOWLEDGMENT", styles['AgreementHeading']))
    story.append(Paragraph(
        "This is to certify that my digital signature below is hereby adopted as my true and correct signature.",
        styles['AgreementBody']
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>My information is as follows:</b>", styles['AgreementBody']))
    
    # Client info table
    client_info = [
        ['Name:', full_name],
        ['Address:', client_address if client_address else '(Address on file)'],
        ['City, State, ZIP:', f"{client_city}, {client_state} {client_postal}" if client_city else '(On file)'],
        ['IP Address:', signature_ip],
    ]
    info_table = Table(client_info, colWidths=[1.2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("<b>Signature:</b>", styles['AgreementBody']))
    story.append(Paragraph(f"<i>{signature}</i>", styles['SignatureStyle']))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(
        "*Digital Signatures: In 2000, the U.S. Electronic Signatures in Global and National Commerce (ESIGN) Act established "
        "electronic records and signatures as legally binding, having the same legal effects as traditional paper documents and "
        "handwritten signatures. Read more at the FTC web site: http://www.ftc.gov/os/2001/06/esign7.htm",
        styles['AgreementSmall']
    ))
    story.append(Spacer(1, 15))
    
    # ==================== WITNESS SECTION ====================
    story.append(Paragraph("In witness of their agreement to the terms above, the parties or their authorized agents hereby affix their signatures:", styles['AgreementBody']))
    story.append(Spacer(1, 10))
    
    # Final signature block
    final_sig = Table([
        [full_name, ''],
        [f'{signature}', signature_date],
        ['Client Signature', 'Date'],
        ['', ''],
        [client_address if client_address else '(Address on file)', ''],
        [f"{client_city}, {client_state} {client_postal}" if client_city else '(City, State, ZIP on file)', ''],
    ], colWidths=[3.5*inch, 2*inch])
    final_sig.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (0, 1), 'Times-Italic'),
        ('FONTSIZE', (0, 1), (0, 1), 14),
        ('FONTSIZE', (0, 2), (-1, 2), 8),
        ('FONTSIZE', (0, 4), (-1, -1), 9),
        ('LINEABOVE', (0, 1), (0, 1), 1, colors.black),
    ]))
    story.append(final_sig)
    story.append(Spacer(1, 20))
    
    # ==================== COMPANY FOOTER ====================
    story.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    story.append(Spacer(1, 8))
    story.append(Paragraph("COMPANY INFORMATION", styles['AgreementHeading']))
    story.append(Paragraph(f"<b>{COMPANY_NAME}</b>", styles['AgreementBody']))
    story.append(Paragraph(f"{COMPANY_ADDRESS}, {COMPANY_CITY}, {COMPANY_STATE} {COMPANY_POSTCODE}", styles['AgreementSmall']))
    story.append(Paragraph("Email: Admin@credlocity.com | Web: www.credlocity.com", styles['AgreementSmall']))
    
    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


@api_router.get("/admin/clients/{client_id}/agreements/{agreement_id}/pdf")
async def get_client_agreement_pdf(client_id: str, agreement_id: str, token: Optional[str] = None, view: Optional[bool] = False, authorization: Optional[str] = Header(None)):
    """Generate and return PDF of agreement - supports both header and query param token"""
    try:
        # Verify authentication - try query param first, then Authorization header
        auth_token = token
        if not auth_token and authorization:
            # Extract token from "Bearer <token>" format
            if authorization.startswith("Bearer "):
                auth_token = authorization[7:]
        
        if not auth_token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        payload = decode_token(auth_token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        email = payload.get("sub")
        user = await db.users.find_one({"email": email}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Get client and agreement
        client = await db.clients.find_one({"id": client_id}, {"_id": 0})
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        agreement = await db.client_agreements.find_one({"id": agreement_id, "client_id": client_id}, {"_id": 0})
        if not agreement:
            raise HTTPException(status_code=404, detail="Agreement not found")
        
        # Generate PDF
        pdf_bytes = generate_agreement_pdf(client, agreement)
        
        # Return as downloadable or viewable PDF
        filename = f"Agreement_{client.get('first_name', '')}_{client.get('last_name', '')}_{agreement.get('signature_date', 'N-A').replace(' ', '_').replace(',', '')}.pdf"
        
        # If view=true, display inline; otherwise download
        disposition = "inline" if view else "attachment"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"{disposition}; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGREEMENT PDF ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/clients/intake/generate-agreement-pdf")
async def generate_intake_agreement_pdf(data: dict):
    """Generate PDF agreement from intake form data (public endpoint)"""
    try:
        # Create temporary client and agreement dicts for PDF generation
        client = {
            "first_name": data.get("firstName", ""),
            "last_name": data.get("lastName", ""),
            "email": data.get("email", ""),
            "phone": data.get("mobilePhone", "")
        }
        
        agreement = {
            "signature_date": data.get("agreementDate", datetime.now(timezone.utc).strftime("%B %d, %Y")),
            "electronic_signature": data.get("electronicSignature", ""),
            "signature_ip": data.get("ipAddress", ""),
            "signature_timestamp": datetime.now(timezone.utc).isoformat(),
            "package_name": data.get("packageName", "To Be Determined"),
            "package_price": data.get("packagePrice", 0),
            "credit_report_fee": 49.95,
            "enotary_fee": 39.95,
            "federal_cancel_date": data.get("federalCancelDate", ""),
            "pa_state_cancel_date": data.get("paStateCancelDate", "")
        }
        
        # Generate PDF
        pdf_bytes = generate_agreement_pdf(client, agreement)
        
        # Return as base64 encoded string for frontend
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        return {
            "success": True,
            "pdf_base64": pdf_base64,
            "filename": f"Credlocity_Agreement_{client['first_name']}_{client['last_name']}.pdf"
        }
    except Exception as e:
        print(f"[INTAKE AGREEMENT PDF ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CLIENT NOTES ====================
@api_router.get("/admin/clients/{client_id}/notes", dependencies=[Depends(check_permissions("author"))])
async def get_client_notes(client_id: str):
    """Get all notes for a client"""
    try:
        notes = await db.client_notes.find({"client_id": client_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
        return notes
    except Exception as e:
        print(f"[CLIENT NOTES GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/clients/{client_id}/notes", dependencies=[Depends(check_permissions("author"))])
async def create_client_note(client_id: str, note: dict, current_user: dict = Depends(get_current_user)):
    """Create a note for a client"""
    try:
        note_data = {
            "id": str(uuid.uuid4()),
            "client_id": client_id,
            "title": note.get("title", ""),
            "content": note.get("content", ""),
            "category": note.get("category", "general"),
            "source_type": note.get("source_type"),
            "source_details": note.get("source_details"),
            "document_url": note.get("document_url"),
            "created_by_id": current_user["id"],
            "created_by_name": current_user.get("full_name", "Admin"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.client_notes.insert_one(note_data)
        note_data.pop("_id", None)
        return note_data
    except Exception as e:
        print(f"[CLIENT NOTE CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CLIENT CREDITS ====================
@api_router.get("/admin/clients/{client_id}/credits", dependencies=[Depends(check_permissions("author"))])
async def get_client_credits(client_id: str):
    """Get all credits for a client"""
    try:
        credits = await db.client_credits.find({"client_id": client_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
        return credits
    except Exception as e:
        print(f"[CLIENT CREDITS GET ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/clients/{client_id}/credits", dependencies=[Depends(check_permissions("author"))])
async def create_client_credit(client_id: str, credit: dict, current_user: dict = Depends(get_current_user)):
    """Create a credit for a client"""
    try:
        credit_data = {
            "id": str(uuid.uuid4()),
            "client_id": client_id,
            "credit_type": credit.get("credit_type"),
            "description": credit.get("description", ""),
            "months": credit.get("months"),
            "dollar_amount": credit.get("dollar_amount"),
            "valid_from": datetime.now(timezone.utc).isoformat(),
            "valid_until": credit.get("valid_until"),
            "status": "active",
            "created_by_id": current_user["id"],
            "created_by_name": current_user.get("full_name", "Admin"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.client_credits.insert_one(credit_data)
        credit_data.pop("_id", None)
        return credit_data
    except Exception as e:
        print(f"[CLIENT CREDIT CREATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/clients/{client_id}/credits/{credit_id}", dependencies=[Depends(check_permissions("author"))])
async def update_client_credit_status(client_id: str, credit_id: str, data: dict):
    """Update a client credit status"""
    try:
        update_data = {"status": data.get("status", "used")}
        if data.get("status") == "used":
            update_data["applied_at"] = datetime.now(timezone.utc).isoformat()
        
        result = await db.client_credits.update_one({"id": credit_id, "client_id": client_id}, {"$set": update_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Credit not found")
        
        updated = await db.client_credits.find_one({"id": credit_id}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CLIENT CREDIT UPDATE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ADMIN REVENUE SPLITS ====================

@api_router.get("/admin/revenue-splits")
async def get_admin_revenue_splits(
    status: Optional[str] = None,
    company_id: Optional[str] = None,
    date_range: Optional[str] = "all",
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(get_current_user)
):
    """Get revenue splits for admin dashboard with filtering"""
    if user.get("role") not in ["admin", "director", "superadmin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Build query
    query = {}
    if status and status != "all":
        query["status"] = status
    if company_id:
        query["company_id"] = company_id
    if search:
        query["case_id"] = {"$regex": search, "$options": "i"}
    
    # Date range filtering
    now = datetime.now(timezone.utc)
    if date_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": start.isoformat()}
    elif date_range == "week":
        start = now - timedelta(days=7)
        query["created_at"] = {"$gte": start.isoformat()}
    elif date_range == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": start.isoformat()}
    elif date_range == "quarter":
        quarter_start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": quarter_start.isoformat()}
    elif date_range == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": start.isoformat()}
    
    # Get total count
    total = await db.revenue_splits.count_documents(query)
    total_pages = (total + limit - 1) // limit
    
    # Get splits with pagination
    skip = (page - 1) * limit
    splits_cursor = db.revenue_splits.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    splits = await splits_cursor.to_list(length=limit)
    
    # Enrich with company names
    for split in splits:
        if split.get("company_id"):
            company = await db.companies.find_one({"id": split["company_id"]}, {"_id": 0, "name": 1})
            split["company_name"] = company.get("name") if company else "Unknown"
        else:
            split["company_name"] = "Direct"
    
    # Calculate summary
    all_splits_cursor = db.revenue_splits.find({}, {"_id": 0, "total_revenue": 1, "split_details": 1, "status": 1})
    all_splits = await all_splits_cursor.to_list(length=None)
    
    total_revenue = sum(s.get("total_revenue", 0) for s in all_splits)
    credlocity_total = sum(s.get("split_details", {}).get("credlocity_amount", 0) for s in all_splits)
    company_total = sum(s.get("split_details", {}).get("company_amount", 0) for s in all_splits)
    pending_payouts = sum(
        s.get("split_details", {}).get("company_amount", 0) 
        for s in all_splits 
        if s.get("status") == "pending_payout"
    )
    
    return {
        "splits": splits,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "summary": {
            "total_revenue": total_revenue,
            "credlocity_total": credlocity_total,
            "company_total": company_total,
            "cases_count": len(all_splits),
            "pending_payouts": pending_payouts
        }
    }


@api_router.get("/admin/revenue-splits/export")
async def export_revenue_splits(
    format: str = "csv",
    user: dict = Depends(get_current_user)
):
    """Export revenue splits to CSV"""
    if user.get("role") not in ["admin", "director", "superadmin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    splits = await db.revenue_splits.find({}, {"_id": 0}).sort("created_at", -1).to_list(length=None)
    
    # Build CSV
    lines = ["Case ID,Company ID,Settlement Amount,Total Revenue,Credlocity Share,Company Share,Status,Date"]
    for split in splits:
        lines.append(",".join([
            str(split.get("case_id", "")),
            str(split.get("company_id", "")),
            str(split.get("settlement_amount", 0)),
            str(split.get("total_revenue", 0)),
            str(split.get("split_details", {}).get("credlocity_amount", 0)),
            str(split.get("split_details", {}).get("company_amount", 0)),
            str(split.get("status", "")),
            str(split.get("created_at", ""))
        ]))
    
    csv_content = "\n".join(lines)
    filename = f"revenue_splits_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return {"csv": csv_content, "filename": filename}


# Include the router in the main app (MUST be after all endpoints are defined)
app.include_router(api_router)

# Include the Collections Management System router
from collections_api import collections_router, set_db as set_collections_db
set_collections_db(db)
app.include_router(collections_router, prefix="/api")

# Include the Team Management router
from team_api import team_router
app.include_router(team_router)

# Include the Attorney Network router
from attorney_api import attorney_router
app.include_router(attorney_router)

# Include the Revenue Tracking router
from revenue_api import revenue_router
app.include_router(revenue_router)

# Include the Attorney Marketplace router
from marketplace_api import marketplace_router
app.include_router(marketplace_router)

# Include the Case Update System router
from case_update_api import case_update_router, seed_case_update_status_options
app.include_router(case_update_router, prefix="/api/case-updates", tags=["Case Updates"])

# Include the Attorney Agreement router
from attorney_agreement_api import attorney_agreement_router
app.include_router(attorney_agreement_router, prefix="/api/attorney-agreement", tags=["Attorney Agreement"])

# Include the Credit Repair Reviews router
from credit_repair_api import credit_repair_router, seed_credit_repair_companies
app.include_router(credit_repair_router, prefix="/api/credit-repair", tags=["Credit Repair Reviews"])

# Include the Review Linking router
from review_linking_api import review_linking_router
app.include_router(review_linking_router, tags=["Review Linking"])

# Include the Client Review router
from client_review_api import client_review_router
app.include_router(client_review_router, tags=["Client Reviews"])

# Include the Activity Tracking router
from activity_tracking_api import router as activity_tracking_router
app.include_router(activity_tracking_router, tags=["Activity Tracking"])

# Include the Billing & Settings router
from billing_settings_api import billing_router
app.include_router(billing_router, tags=["Billing & Settings"])

# Include the Case Management router
from case_management_api import case_management_router
app.include_router(case_management_router, tags=["Case Management"])

# Include the Company Management router
from company_management_api import company_router
app.include_router(company_router, tags=["Credit Repair Companies"])


# Include the Security router
from security.security_api import security_router
app.include_router(security_router, tags=["Security"])

# Include the Stripe payments router
from stripe_api import stripe_router
app.include_router(stripe_router, tags=["Stripe Payments"])

# Include the Internal Chat router
from chat_api import chat_router, set_db as set_chat_db
set_chat_db(db)
app.include_router(chat_router, tags=["Internal Chat"])

# Include the Customer Support Chat router
from support_chat_api import support_chat_router, set_db as set_support_chat_db
set_support_chat_db(db)
app.include_router(support_chat_router, tags=["Customer Support Chat"])


# Seed default data on startup
@app.on_event("startup")
async def startup_seed():
    try:
        await seed_case_update_status_options()
        await seed_credit_repair_companies()
    except Exception as e:
        print(f"Warning: Startup seed failed (non-fatal): {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)