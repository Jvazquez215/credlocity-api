from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client, AsyncIOMotorDatabase
import os
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import shutil
import uuid
from PIL import Image
import io


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
    EducationVideo, EducationVideoCreate, EducationVideoUpdate
)
from auth import (
    verify_password, get_password_hash, create_access_token,
    decode_token, security
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = get_client(mongo_url)
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
    show_on_success_stories: Optional[bool] = None
):
    """Get all reviews with optional filters"""
    query = {}
    if featured_on_homepage is not None:
        query["featured_on_homepage"] = featured_on_homepage
    if show_on_success_stories is not None:
        query["show_on_success_stories"] = show_on_success_stories
    
    reviews = await db.reviews.find(query, {"_id": 0}).sort("display_order", 1).to_list(1000)
    
    for review in reviews:
        if isinstance(review.get('created_at'), str):
            review['created_at'] = datetime.fromisoformat(review['created_at'])
        if isinstance(review.get('updated_at'), str):
            review['updated_at'] = datetime.fromisoformat(review['updated_at'])
    
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



# Include the router in the main app
app.include_router(api_router)

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


# Duplicate video endpoints removed - using complete set below

# Removed duplicate endpoint

# POST /api/education-videos - Create new video
@api_router.post("/education-videos")
async def create_education_video(
    video: dict,
    current_user: dict = Depends(get_current_user)
):
    """Create new education video"""
    try:
        video_obj = EducationVideo(**video)
        video_dict = video_obj.model_dump()
        
        result = await db.education_videos.insert_one(video_dict)
        return {"message": "Video created successfully", "id": video_obj.id}
    except Exception as e:
        print(f"[EDUCATION VIDEOS API ERROR] create_education_video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# GET /api/education-videos/{video_id} - Get single video
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
        print(f"[EDUCATION VIDEOS API ERROR] get_education_video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# PUT /api/education-videos/{video_id} - Update video
@api_router.put("/education-videos/{video_id}")
async def update_education_video(
    video_id: str,
    video_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update education video"""
    try:
        video_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await db.education_videos.update_one(
            {"id": video_id},
            {"$set": video_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {"message": "Video updated successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[EDUCATION VIDEOS API ERROR] update_education_video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# DELETE /api/education-videos/{video_id} - Delete video
@api_router.delete("/education-videos/{video_id}")
async def delete_education_video(
    video_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete education video"""
    try:
        result = await db.education_videos.delete_one({"id": video_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {"message": "Video deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[EDUCATION VIDEOS API ERROR] delete_education_video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# POST /api/education-videos/{video_id}/increment-views - Track video views
@api_router.post("/education-videos/{video_id}/increment-views")
async def increment_video_views(video_id: str):
    """Increment video view count"""
    try:
        await db.education_videos.update_one(
            {"id": video_id},
            {"$inc": {"views": 1}}
        )
        return {"message": "View count incremented"}
    except Exception as e:
        print(f"[EDUCATION VIDEOS API ERROR] increment_video_views: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

@api_router.get("/news-sitemap.xml")
async def generate_news_sitemap():
    """Google News sitemap"""
    try:
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        news_posts = await db.blog_posts.find({"status": "published", "is_news": True, "publish_date": {"$gte": two_days_ago}}).sort("publish_date", -1).to_list(None)
        
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
        
        for post in news_posts:
            sitemap += '  <url>\n'
            sitemap += f'    <loc>https://credlocity.com/blog/{post.get("slug", "")}</loc>\n'
            sitemap += '    <news:news>\n'
            sitemap += '      <news:publication><news:name>Credlocity</news:name><news:language>en</news:language></news:publication>\n'
            sitemap += f'      <news:publication_date>{post.get("publish_date", datetime.now(timezone.utc)).isoformat()}</news:publication_date>\n'
            sitemap += f'      <news:title>{post.get("title", "")}</news:title>\n'
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

@api_router.get("/affiliate-pages")
async def get_affiliate_pages(status: Optional[str] = None):
    """Get affiliate pages"""
    try:
        query = {}
        if status:
            query["status"] = status
        pages = await db.affiliate_pages.find(query).sort("order", 1).to_list(None)
        for page in pages:
            if "_id" in page:
                page["id"] = str(page.pop("_id"))
        return pages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/affiliate-pages/slug/{slug}")
async def get_affiliate_page_by_slug(slug: str):
    """Get affiliate page by slug"""
    try:
        page = await db.affiliate_pages.find_one({"slug": slug, "status": "published"})
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        if "_id" in page:
            page["id"] = str(page.pop("_id"))
        await db.affiliate_pages.update_one({"id": page["id"]}, {"$inc": {"views": 1}})
        return page
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/affiliate-pages")
async def create_affiliate_page(page_data: dict, current_user: dict = Depends(get_current_user)):
    """Create affiliate page"""
    try:
        from models import AffiliatePage
        page = AffiliatePage(**page_data)
        await db.affiliate_pages.insert_one(page.model_dump())
        return {"message": "Created", "id": page.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/affiliate-pages/{page_id}")
async def update_affiliate_page(page_id: str, page_data: dict, current_user: dict = Depends(get_current_user)):
    """Update affiliate page"""
    try:
        page_data["updated_at"] = datetime.now(timezone.utc)
        result = await db.affiliate_pages.update_one({"id": page_id}, {"$set": page_data})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"message": "Updated"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================
# Video Management API (Education Hub)
# =====================================

@api_router.get("/education-videos")
async def get_education_videos(
    category: Optional[str] = None,
    status: Optional[str] = None,
    featured: Optional[bool] = None,
    show_in_gallery: Optional[bool] = None
):
    """Get all education videos with optional filtering"""
    try:
        query = {}
        if category:
            query["category"] = category
        if status:
            query["status"] = status
        if featured is not None:
            query["featured"] = featured
        if show_in_gallery is not None:
            query["show_in_gallery"] = show_in_gallery
        
        videos = await db.education_videos.find(query).sort("order", 1).to_list(None)
        for video in videos:
            if "_id" in video:
                video["id"] = str(video.pop("_id"))
        return videos
    except Exception as e:
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
        if "_id" in video:
            video["id"] = str(video.pop("_id"))
        
        # Increment view count
        await db.education_videos.update_one({"id": video["id"]}, {"$inc": {"views": 1}})
        video["views"] = video.get("views", 0) + 1
        
        return video
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
        
        return {"message": "Video updated successfully"}
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)