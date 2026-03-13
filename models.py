from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from uuid import uuid4

# User Models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    hashed_password: str
    full_name: str
    role: str = "viewer"  # super_admin, admin, editor, author, viewer
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "viewer"

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]

# Page Models
class SEOMetadata(BaseModel):
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    robots: str = "index, follow"
    keywords: Optional[str] = None

class Page(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    slug: str
    content: str
    parent_id: Optional[str] = None
    status: str = "draft"  # draft, published
    placement: str = "main"  # main, footer, hidden
    seo: SEOMetadata = Field(default_factory=SEOMetadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str

class PageCreate(BaseModel):
    title: str
    slug: str
    content: str = ""
    parent_id: Optional[str] = None
    status: str = "draft"
    placement: str = "main"
    seo: SEOMetadata = Field(default_factory=SEOMetadata)

class PageUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    parent_id: Optional[str] = None
    status: Optional[str] = None
    placement: Optional[str] = None
    seo: Optional[SEOMetadata] = None

# Author Models (see comprehensive Author class below at line ~617)

class AuthorCreate(BaseModel):
    name: str
    slug: str
    title: str
    bio: str
    photo: Optional[str] = None
    email: Optional[EmailStr] = None
    credentials: Optional[str] = None

# Blog Models (Enhanced for SEO and Content Management)
class BlogPostSEO(BaseModel):
    """Extended SEO metadata specifically for blog posts"""
    meta_title: Optional[str] = ""  # 60 char limit
    meta_description: Optional[str] = ""  # 160 char limit
    keywords: Optional[str] = ""  # Comma-separated
    canonical_url: Optional[str] = ""
    robots: str = "index, follow"  # index/follow, noindex/nofollow, etc.
    schema_type: str = "BlogPosting"  # BlogPosting, Article, HowTo, FAQPage
    og_title: Optional[str] = ""
    og_description: Optional[str] = ""
    og_image: Optional[str] = ""

class BlogPost(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Core Content
    title: str
    slug: str  # Must be unique, critical for SEO
    content: str  # Rich HTML from TipTap
    excerpt: Optional[str] = ""  # Auto-generate from content if blank
    
    # Organization
    categories: List[str] = []  # Category IDs or names
    tags: List[str] = []  # Tag names
    is_news: bool = False  # Mark as news for RSS feed and news sitemap
    read_time_minutes: int = 0  # Estimated read time
    
    # Author
    author_name: str = "Credlocity Team"  # Default author
    author_id: Optional[str] = None  # Link to Author model
    author_slug: Optional[str] = None  # For linking to author profile
    author_photo_url: Optional[str] = None  # Author photo
    author_title: Optional[str] = None  # Author title/position
    author_credentials: List[str] = []  # Author credentials for E-E-A-T
    author_experience: Optional[int] = None  # Years of experience for E-E-A-T
    author_education: List[dict] = []  # Author education for E-E-A-T
    author_publications: List[dict] = []  # Author publications/media features for E-E-A-T
    author_bio: Optional[str] = None  # Author bio
    
    # Media
    featured_image_url: Optional[str] = ""
    featured_image_alt: Optional[str] = ""
    
    # SEO (Comprehensive)
    seo: BlogPostSEO = Field(default_factory=BlogPostSEO)
    
    # Publishing
    status: str = "draft"  # draft, published, scheduled
    publish_date: Optional[datetime] = None  # When it was/will be published
    scheduled_publish: Optional[datetime] = None  # For scheduled posts
    
    # Engagement
    featured_post: bool = False  # Show in featured section
    allow_comments: bool = True
    
    # Related Content & Interlinking
    related_posts: List[str] = []  # Post IDs (manual selection)
    related_topics: List[str] = []  # Topic/category IDs for auto cross-linking
    related_pages: List[dict] = []  # [{url: "/pricing", title: "Our Pricing", description: ""}]
    related_education_hub: bool = False  # Link to Education Hub (Phase 5)
    related_press_releases: List[str] = []  # Press Release IDs for interlinking
    related_lawsuits: List[str] = []  # Lawsuit IDs for interlinking
    
    # Analytics (Basic tracking)
    view_count: int = 0
    
    # Updates & Corrections System
    updates: List[dict] = []  # Array of update objects
    
    # Disclosure Management System
    disclosures: dict = {
        # YMYL (Your Money Your Life)
        "ymyl_enabled": False,
        "ymyl_content": "",  # Editable YMYL disclosure
        
        # General Disclosures
        "general_disclosure_enabled": False,
        "general_disclosure_type": "",  # "affiliate", "sponsored", "partnership", "other"
        "general_disclosure_content": "",
        
        # Competitor Disclosure
        "competitor_disclosure_enabled": False,
        "competitor_disclosure_content": "",
        
        # Corrections & Accountability
        "corrections_enabled": False,
        "corrections_content": "",
        
        # Pseudonym/Confidential Sources
        "pseudonym_enabled": False,
        "pseudonym_reason": "",  # "nature_of_info", "speak_freely", "other"
        "pseudonym_content": ""
    }
    
    # Schema.org Management
    schemas: dict = {
        "auto_generate": True,  # Auto-generate schemas from post data
        "article_type": "BlogPosting",  # "Article", "BlogPosting", "NewsArticle"
        "include_author": True,
        "include_breadcrumb": True,
        "include_faq": False,
        "custom_schema": ""  # Custom JSON-LD if needed
    }
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None  # User ID
    last_edited_by: Optional[str] = None  # User ID

class BlogPostCreate(BaseModel):
    title: str
    slug: str
    content: str
    excerpt: Optional[str] = ""
    categories: List[str] = []
    tags: List[str] = []
    is_news: bool = False
    read_time_minutes: int = 0
    author_name: str = "Credlocity Team"
    author_id: Optional[str] = None
    author_slug: Optional[str] = None
    author_photo_url: Optional[str] = None
    author_title: Optional[str] = None
    author_credentials: List[str] = []
    author_experience: Optional[int] = None
    author_education: List[dict] = []
    author_publications: List[dict] = []
    author_bio: Optional[str] = None
    featured_image_url: Optional[str] = ""
    featured_image_alt: Optional[str] = ""
    seo: BlogPostSEO = Field(default_factory=BlogPostSEO)
    status: str = "draft"
    publish_date: Optional[datetime] = None
    scheduled_publish: Optional[datetime] = None
    featured_post: bool = False
    allow_comments: bool = True
    related_posts: List[str] = []
    related_topics: List[str] = []
    related_pages: List[dict] = []
    related_education_hub: bool = False  # Link to Education Hub
    related_press_releases: List[str] = []
    related_lawsuits: List[str] = []
    updates: List[dict] = []  # Updates and corrections
    disclosures: dict = {}
    schemas: dict = {}

class BlogPostUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    is_news: Optional[bool] = None
    read_time_minutes: Optional[int] = None
    author_name: Optional[str] = None
    author_id: Optional[str] = None
    author_slug: Optional[str] = None
    author_photo_url: Optional[str] = None
    author_title: Optional[str] = None
    author_credentials: Optional[List[str]] = None
    author_experience: Optional[int] = None
    author_education: Optional[List[dict]] = None
    author_publications: Optional[List[dict]] = None
    author_bio: Optional[str] = None
    featured_image_url: Optional[str] = None
    featured_image_alt: Optional[str] = None
    seo: Optional[BlogPostSEO] = None
    status: Optional[str] = None
    publish_date: Optional[datetime] = None
    scheduled_publish: Optional[datetime] = None
    featured_post: Optional[bool] = None
    allow_comments: Optional[bool] = None
    related_posts: Optional[List[str]] = None
    related_topics: Optional[List[str]] = None
    related_pages: Optional[List[dict]] = None
    related_education_hub: Optional[bool] = None
    related_press_releases: Optional[List[str]] = None
    related_lawsuits: Optional[List[str]] = None
    updates: Optional[List[dict]] = None  # Updates and corrections
    disclosures: Optional[dict] = None  # Disclosure management
    schemas: Optional[dict] = None  # Schema.org management

# Category Model for Blog Organization
class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str  # URL-friendly name
    description: Optional[str] = ""
    parent_id: Optional[str] = None  # For hierarchical categories
    post_count: int = 0  # Auto-calculated
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = ""
    parent_id: Optional[str] = None
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

# Tag Model for Blog Taxonomy
class Tag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str  # URL-friendly name
    post_count: int = 0  # Auto-calculated
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TagCreate(BaseModel):
    name: str
    slug: str

class TagUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None

# Media Models (Enhanced)
class MediaEnhanced(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str  # Unique filename (UUID-based)
    original_filename: str  # Original uploaded filename
    file_type: str  # image, video, document
    mime_type: str  # image/jpeg, video/mp4, application/pdf
    file_size: int  # in bytes
    url: str  # Full URL to access file
    alt_text: Optional[str] = ""
    caption: Optional[str] = ""
    folder: str = "/"  # Path like /images/team/
    width: Optional[int] = None  # For images
    height: Optional[int] = None  # For images
    uploaded_by: str  # User ID
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    used_in: List[str] = []  # Array of page/post IDs where this media is used

class MediaCreate(BaseModel):
    alt_text: Optional[str] = ""
    caption: Optional[str] = ""
    folder: str = "/"

class MediaUpdate(BaseModel):
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    folder: Optional[str] = None

# Review/Testimonial Model (Enhanced for Credlocity)
class ReviewEnhanced(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    testimonial_text: str  # Short quote for display (homepage/cards)
    full_story: str  # Longer detailed story (success stories list)
    detailed_narrative: Optional[str] = ""  # Rich HTML content for individual story page
    story_title: Optional[str] = ""  # Custom title for individual page
    story_slug: str = ""  # URL slug for individual page (e.g., "maria-g-homeowner-journey")
    gallery_photos: List[str] = []  # Photo URLs for individual page gallery
    
    # SEO FIELDS:
    seo_meta_title: Optional[str] = ""  # Custom meta title for story page
    seo_meta_description: Optional[str] = ""  # Custom meta description (160 chars)
    seo_keywords: Optional[str] = ""  # Focus keywords (comma-separated)
    
    # SOCIAL MEDIA LINKS:
    client_social_links: Optional[Dict[str, str]] = {}  # Facebook, Instagram, Twitter, BlueSky, Threads, LinkedIn
    
    video_url: Optional[str] = ""  # YouTube/Vimeo embed URL
    before_score: int = 0  # Credit score before (300-850)
    after_score: int = 0  # Credit score after (300-850)
    points_improved: int = 0  # Auto-calculated or manually set
    client_photo_url: Optional[str] = ""  # From Media Library
    featured_on_homepage: bool = False
    show_on_success_stories: bool = True
    competitor_switched_from: Optional[str] = ""
    category: Optional[str] = ""  # collection_removal, identity_theft, late_payments, etc
    display_order: int = 0  # For manual ordering
    display_on_lawsuits_page: bool = False  # Show on lawsuits page
    location: Optional[str] = ""  # City, State for display
    review_category: Optional[str] = "general"  # lawsuit, switched_from_competitor, general, attorney_testimonials, etc.
    competitor_switched_from: Optional[str] = ""  # Credit Saint, Creditrepair.com, Lexington Law, The Credit People, etc.
    category_ids: List[str] = []  # Array of category IDs this review belongs to
    schema_data: Optional[dict] = {}  # Schema.org structured data for this review
    
    # ATTORNEY REVIEW FIELDS:
    is_attorney_review: bool = False  # Flag for attorney testimonials
    attorney_settlement_amount: Optional[float] = None  # How much money attorney got client
    linked_client_review_id: Optional[str] = None  # Link to related client review
    linked_client_review_name: Optional[str] = None  # Display name of linked client
    credlocity_points_gained: Optional[int] = None  # Points gained by Credlocity's credit repair
    attorney_points_gained: Optional[int] = None  # Additional points from attorney's legal action
    attorney_firm_name: Optional[str] = ""  # Attorney's firm name
    attorney_profile_video_url: Optional[str] = ""  # Attorney's video testimonial
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReviewEnhancedCreate(BaseModel):
    client_name: str
    testimonial_text: str
    full_story: str
    detailed_narrative: Optional[str] = ""
    story_title: Optional[str] = ""
    story_slug: str = ""
    gallery_photos: List[str] = []
    seo_meta_title: Optional[str] = ""
    seo_meta_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    client_social_links: Optional[Dict[str, str]] = {}
    video_url: Optional[str] = ""
    before_score: int  # 300-850
    after_score: int  # 300-850
    client_photo_url: Optional[str] = ""
    featured_on_homepage: bool = False
    show_on_success_stories: bool = True
    competitor_switched_from: Optional[str] = ""
    category: Optional[str] = ""
    display_order: int = 0
    display_on_lawsuits_page: bool = False
    location: Optional[str] = ""
    review_category: Optional[str] = "general"
    category_ids: List[str] = []
    schema_data: Optional[dict] = {}
    # Attorney review fields
    is_attorney_review: bool = False
    attorney_settlement_amount: Optional[float] = None
    linked_client_review_id: Optional[str] = None
    linked_client_review_name: Optional[str] = None
    credlocity_points_gained: Optional[int] = None
    attorney_points_gained: Optional[int] = None
    attorney_firm_name: Optional[str] = ""
    attorney_profile_video_url: Optional[str] = ""

class ReviewEnhancedUpdate(BaseModel):
    client_name: Optional[str] = None
    testimonial_text: Optional[str] = None
    full_story: Optional[str] = None
    detailed_narrative: Optional[str] = None
    story_title: Optional[str] = None
    story_slug: Optional[str] = None
    gallery_photos: Optional[List[str]] = None
    seo_meta_title: Optional[str] = None
    seo_meta_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    client_social_links: Optional[Dict[str, str]] = None
    video_url: Optional[str] = None
    before_score: Optional[int] = None
    after_score: Optional[int] = None
    client_photo_url: Optional[str] = None
    featured_on_homepage: Optional[bool] = None
    show_on_success_stories: Optional[bool] = None
    competitor_switched_from: Optional[str] = None
    category: Optional[str] = None
    display_order: Optional[int] = None
    display_on_lawsuits_page: Optional[bool] = None
    location: Optional[str] = None
    review_category: Optional[str] = None
    category_ids: Optional[List[str]] = None
    schema_data: Optional[dict] = None
    # Attorney review fields
    is_attorney_review: Optional[bool] = None
    attorney_settlement_amount: Optional[float] = None
    linked_client_review_id: Optional[str] = None
    linked_client_review_name: Optional[str] = None
    credlocity_points_gained: Optional[int] = None
    attorney_points_gained: Optional[int] = None
    attorney_firm_name: Optional[str] = None
    attorney_profile_video_url: Optional[str] = None


# Banner Models
class Banner(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str
    position: str = "top"  # top, bottom, center
    bg_color: str = "#012697"
    text_color: str = "#ffffff"
    cta_text: Optional[str] = None
    cta_link: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BannerCreate(BaseModel):
    title: str
    content: str
    position: str = "top"
    bg_color: str = "#012697"
    text_color: str = "#ffffff"
    cta_text: Optional[str] = None
    cta_link: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True

# Settings Model
class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "site_settings"
    site_name: str = "Credlocity"
    tagline: str = "CREDIT REPAIR DONE RIGHT"
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#012697"
    secondary_color: str = "#59a52c"
    contact_email: str = ""
    contact_phone: str = ""
    social_links: Dict[str, str] = {}
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Complaint Model
class Complaint(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    complainant_name: str
    complainant_email: EmailStr
    complaint_details: str
    state: Optional[str] = None
    date_of_service: Optional[str] = None
    
    # NEW FIELDS
    person_spoke_to: Optional[str] = ""  # Contact person at company
    complaint_types: List[str] = []  # refund_issue, croa_violation, tsr_violation, customer_service, billing, lack_communication, nothing_done
    screenshots: List[str] = []  # URLs to uploaded screenshots
    audio_recordings: List[str] = []  # URLs to uploaded audio files
    
    status: str = "pending"  # pending, investigating, resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ComplaintCreate(BaseModel):
    company_name: str
    complainant_name: str
    complainant_email: EmailStr
    complaint_details: str
    state: Optional[str] = None
    date_of_service: Optional[str] = None
    person_spoke_to: Optional[str] = ""
    complaint_types: List[str] = []
    screenshots: List[str] = []
    audio_recordings: List[str] = []

# Review/Testimonial Model
class Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    location: str
    rating: int  # 1-5
    review_text: str
    review_date: str
    display_on_home: bool = False
    category: Optional[str] = None  # mortgage, auto, identity_theft, etc
    score_before: Optional[int] = None
    score_after: Optional[int] = None
    savings: Optional[str] = None
    video_url: Optional[str] = None
    social_handle: Optional[str] = None
    social_platform: Optional[str] = None  # instagram, facebook, bluesky, etc
    display_on_lawsuits_page: bool = False  # Show on lawsuits page
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReviewCreate(BaseModel):
    client_name: str
    location: str
    rating: int
    review_text: str
    review_date: str
    display_on_home: bool = False
    category: Optional[str] = None
    score_before: Optional[int] = None
    score_after: Optional[int] = None
    savings: Optional[str] = None
    video_url: Optional[str] = None
    social_handle: Optional[str] = None
    social_platform: Optional[str] = None
    display_on_lawsuits_page: bool = False

class ReviewUpdate(BaseModel):
    client_name: Optional[str] = None
    location: Optional[str] = None
    rating: Optional[int] = None
    review_text: Optional[str] = None
    review_date: Optional[str] = None
    display_on_home: Optional[bool] = None
    category: Optional[str] = None
    score_before: Optional[int] = None
    score_after: Optional[int] = None
    savings: Optional[str] = None
    video_url: Optional[str] = None
    social_handle: Optional[str] = None
    social_platform: Optional[str] = None
    display_on_lawsuits_page: Optional[bool] = None


# Author/Team Member Models
class Author(BaseModel):
    """Author/Team Member Profile for blog posts and team pages"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    full_name: str  # "John Smith"
    slug: str  # "john-smith" (unique, for URL)
    email: Optional[str] = ""
    
    # Professional Info
    title: str  # "Credit Repair Specialist", "CEO", "Senior Consultant"
    specialization: Optional[str] = ""  # "FCRA Compliance", "Credit Building", "Mortgage Consultation"
    
    # Biography
    bio: str  # Rich HTML from TipTap - full biography/story
    short_bio: Optional[str] = ""  # 150-300 chars for author cards
    
    # Media
    photo_url: Optional[str] = ""  # Headshot/profile photo (optional)
    photo_alt: Optional[str] = ""  # Alt text for photo (optional)
    
    # Credentials & Experience
    credentials: List[str] = []  # ["Certified Credit Consultant", "10+ years experience", "FICO Expert"]
    years_experience: Optional[int] = 0
    
    # Education
    education: List[dict] = []  # [{"degree": "MBA", "institution": "Harvard", "year": "2015"}]
    
    # Publications & Media Features
    publications: List[dict] = []  # [{"title": "Featured in Forbes", "url": "https://...", "publication": "Forbes", "date": "2024-01-15"}]
    
    # Social Media Links
    social_links: dict = {}  # {"linkedin": "url", "twitter": "url", "facebook": "url", "instagram": "url"}
    
    # Contact (optional)
    phone: Optional[str] = ""
    office_location: Optional[str] = ""  # "Philadelphia Office", "Remote"
    
    # Display Options
    display_order: int = 0  # For team page ordering (lower = higher on page)
    featured: bool = False  # Show on homepage "Meet the Team" section
    show_on_team_page: bool = True
    
    # SEO (for individual author pages)
    seo_meta_title: Optional[str] = ""  # "John Smith - Credit Repair Expert | Credlocity"
    seo_meta_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    
    # Status
    status: str = "active"  # active, inactive, former_employee
    
    # Stats (auto-calculated)
    post_count: int = 0  # Number of blog posts by this author
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AuthorCreate(BaseModel):
    """Model for creating a new author"""
    full_name: str
    slug: str
    email: Optional[str] = ""
    title: str
    specialization: Optional[str] = ""
    bio: str
    short_bio: Optional[str] = ""
    photo_url: Optional[str] = ""  # Made optional
    photo_alt: Optional[str] = ""  # Made optional
    credentials: List[str] = []
    years_experience: Optional[int] = 0
    social_links: dict = {}
    phone: Optional[str] = ""
    office_location: Optional[str] = ""
    display_order: int = 0
    featured: bool = False
    show_on_team_page: bool = True
    seo_meta_title: Optional[str] = ""
    seo_meta_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    status: str = "active"

class AuthorUpdate(BaseModel):
    """Model for updating an author"""
    full_name: Optional[str] = None
    slug: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    specialization: Optional[str] = None
    bio: Optional[str] = None
    short_bio: Optional[str] = None
    photo_url: Optional[str] = None
    photo_alt: Optional[str] = None
    credentials: Optional[List[str]] = None
    years_experience: Optional[int] = None
    social_links: Optional[dict] = None
    phone: Optional[str] = None
    office_location: Optional[str] = None
    display_order: Optional[int] = None
    featured: Optional[bool] = None
    show_on_team_page: Optional[bool] = None
    seo_meta_title: Optional[str] = None
    seo_meta_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    status: Optional[str] = None



# FAQ Models (Phase 3C)
class FAQ(BaseModel):
    """FAQ Model for frequently asked questions"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Core Content
    question: str = Field(min_length=1)
    answer: str  # HTML content from TipTap
    
    # Organization
    category: str  # Category name (e.g., "Equifax FAQs")
    category_slug: str  # URL-friendly category slug
    slug: str  # Unique slug for individual FAQ URL
    order: int = 0  # For sorting within category (lower = higher on page)
    
    # SEO Fields
    seo_meta_title: Optional[str] = ""
    seo_meta_description: Optional[str] = ""
    keywords: List[str] = []  # Focus keywords
    
    # Author Attribution (E-E-A-T)
    author_id: Optional[str] = ""
    author_name: Optional[str] = ""
    author_credentials: List[str] = []
    
    # Related Content (Interlinking)
    related_blog_posts: List[str] = []  # Blog post IDs
    related_faqs: List[str] = []  # FAQ IDs
    
    # Publishing
    status: str = "published"  # draft, published
    
    # Analytics
    views: int = 0
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FAQCreate(BaseModel):
    """Model for creating a new FAQ"""
    question: str
    answer: str
    category: str
    category_slug: str
    slug: str
    order: int = 0
    seo_meta_title: Optional[str] = ""
    seo_meta_description: Optional[str] = ""
    keywords: List[str] = []
    author_id: Optional[str] = ""
    author_name: Optional[str] = ""
    author_credentials: List[str] = []
    related_blog_posts: List[str] = []
    related_faqs: List[str] = []
    status: str = "published"

class FAQUpdate(BaseModel):
    """Model for updating an FAQ"""
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    category_slug: Optional[str] = None
    slug: Optional[str] = None
    order: Optional[int] = None
    seo_meta_title: Optional[str] = None
    seo_meta_description: Optional[str] = None
    keywords: Optional[List[str]] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    author_credentials: Optional[List[str]] = None
    related_blog_posts: Optional[List[str]] = None
    related_faqs: Optional[List[str]] = None
    status: Optional[str] = None

class FAQCategory(BaseModel):
    """FAQ Category Model for organizing FAQs"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    name: str  # "Equifax FAQs", "Credit Repair FAQs"
    slug: str  # "equifax-faqs", "credit-repair-faqs"
    icon: Optional[str] = ""  # Emoji icon (e.g., "📊", "🏦")
    description: Optional[str] = ""  # Short description
    
    # Stats
    faq_count: int = 0  # Auto-calculated
    
    # Display
    order: int = 0  # For sorting categories (lower = higher on page)
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FAQCategoryCreate(BaseModel):
    """Model for creating FAQ category"""
    name: str
    slug: str
    icon: Optional[str] = ""
    description: Optional[str] = ""
    order: int = 0

class FAQCategoryUpdate(BaseModel):
    """Model for updating FAQ category"""
    name: Optional[str] = None
    slug: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


# Site Settings Model (Phase 4)
class SiteSettings(BaseModel):
    """Site-wide settings model (singleton pattern)"""
    model_config = ConfigDict(extra="ignore")
    id: str = "site_settings"  # Singleton ID
    
    # Branding
    logo_url: Optional[str] = ""
    logo_dark_url: Optional[str] = ""  # For dark backgrounds
    favicon_url: Optional[str] = ""
    brand_color_primary: str = "#2563eb"  # Tailwind blue-600
    brand_color_secondary: str = "#1e40af"  # Tailwind blue-800
    
    # Global SEO
    default_meta_title: str = "Credlocity - Ethical Credit Repair Since 2008"
    default_meta_description: str = "America's trusted credit repair company. Ethical, transparent credit repair services helping over 79,000 clients improve their credit scores."
    default_keywords: List[str] = ["credit repair", "fix credit", "credit score", "credit restoration"]
    default_og_image: Optional[str] = ""
    
    # Schema.org Organization
    organization_name: str = "Credlocity"
    organization_logo: Optional[str] = ""
    organization_phone: Optional[str] = ""
    organization_email: Optional[str] = ""
    organization_address: Optional[dict] = {}  # {street, city, state, zip}
    social_profiles: dict = {}  # {facebook, twitter, linkedin, instagram}
    
    # Analytics & Tracking API Keys
    google_analytics_id: Optional[str] = ""  # GA4: G-XXXXXXXXXX
    google_search_console_id: Optional[str] = ""  # Verification code
    google_tag_manager_id: Optional[str] = ""  # GTM-XXXXXXX
    facebook_pixel_id: Optional[str] = ""
    
    # SEO Tools
    sitemap_enabled: bool = True
    robots_txt_custom: Optional[str] = ""  # Custom robots.txt (optional)
    
    # AI Features
    chatbot_enabled: bool = False  # CreditSage AI Chatbot
    
    # Admin Restrictions
    admin_logo_editable_by: List[str] = ["super_admin"]  # Only super admins can change branding
    
    # Metadata
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SiteSettingsUpdate(BaseModel):
    """Model for updating site settings"""
    logo_url: Optional[str] = None
    logo_dark_url: Optional[str] = None
    favicon_url: Optional[str] = None
    brand_color_primary: Optional[str] = None
    brand_color_secondary: Optional[str] = None
    default_meta_title: Optional[str] = None
    default_meta_description: Optional[str] = None
    default_keywords: Optional[List[str]] = None
    default_og_image: Optional[str] = None
    organization_name: Optional[str] = None
    organization_logo: Optional[str] = None
    organization_phone: Optional[str] = None
    organization_email: Optional[str] = None
    organization_address: Optional[dict] = None
    social_profiles: Optional[dict] = None
    chatbot_enabled: Optional[bool] = None


# ==============================================================
# URL REDIRECT MANAGEMENT
# ==============================================================

class URLRedirect(BaseModel):
    """Manage URL redirects for SEO preservation"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # URLs
    old_url: str  # Former URL path (e.g., /old-blog-post)
    new_url: str  # New URL path (e.g., /blog/new-blog-post)
    
    # Redirect Type
    redirect_type: int = 301  # 301 (permanent) or 302 (temporary)
    
    # Metadata
    reason: str = ""  # Why redirect was created
    created_by: Optional[str] = ""
    
    # Analytics
    hit_count: int = 0  # How many times redirect was used
    
    # Status
    active: bool = True
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# BLOG UPDATE TRACKING
# ==============================================================

class BlogUpdate(BaseModel):
    """Track updates/corrections to blog posts"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Associated Blog
    blog_post_id: str  # ID of blog post being updated
    
    # Update Details
    update_type: str = "update"  # "update" or "critical_update"
    update_title: str  # Short title of update
    update_content: str  # HTML content of the update
    
    # Placement
    insert_location: str = "bottom"  # "top", "bottom", or "inline_after_paragraph_{n}"
    highlight_changes: bool = True  # Highlight updated sections
    
    # Timestamps
    update_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))  # Editable
    display_date: Optional[str] = ""  # Custom display date if different
    
    # Visibility
    show_notice: bool = True  # Show update notice banner
    notice_position: str = "top"  # "top" or "bottom" of article
    
    # Metadata
    created_by: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# AFFILIATE PROGRAM PAGES
# ==============================================================

class AffiliatePage(BaseModel):
    """Affiliate program pages for different industries"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    title: str  # e.g., "Real Estate Affiliate Program"
    slug: str  # e.g., "real-estate-affiliate"
    industry_type: str  # real_estate, car_dealership, broker, social_media_influencer
    
    # Hero Section
    hero_title: str
    hero_subtitle: str
    hero_image_url: Optional[str] = ""
    cta_button_text: str = "Apply Now"
    cta_button_link: str = ""
    
    # Content Sections
    overview: str  # Rich HTML - program overview
    benefits: str  # Rich HTML - benefits list
    how_it_works: str  # Rich HTML - step-by-step process
    requirements: str  # Rich HTML - eligibility requirements
    commission_structure: str  # Rich HTML - commission details
    
    # FAQs
    faqs: List[dict] = []  # [{question: str, answer: str}]
    
    # SEO
    seo_meta_title: str = ""
    seo_meta_description: str = ""
    seo_keywords: List[str] = []
    canonical_url: str = ""
    
    # Schema
    schema_type: str = "WebPage"
    
    # Publishing
    status: str = "published"  # draft, published
    order: int = 0  # Display order on main affiliate page
    
    # Analytics
    views: int = 0
    applications: int = 0  # Track affiliate applications
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# ENHANCED COMPLAINT SYSTEM
# ==============================================================

class ComplaintUpdate(BaseModel):
    """Enhanced complaint model with additional fields"""
    # Existing fields remain, adding new ones
    person_spoke_to: Optional[str] = ""  # Contact person at company
    complaint_types: List[str] = []  # refund_issue, croa_violation, tsr_violation, etc.
    screenshots: List[str] = []  # URLs to uploaded screenshots
    audio_recordings: List[str] = []  # URLs to uploaded audio files

    social_profiles: Optional[dict] = None
    google_analytics_id: Optional[str] = None
    google_search_console_id: Optional[str] = None
    google_tag_manager_id: Optional[str] = None
    facebook_pixel_id: Optional[str] = None
    sitemap_enabled: Optional[bool] = None
    robots_txt_custom: Optional[str] = None



# ==============================================================
# CREDIT EDUCATION HUB MODELS (Phase 5)
# ==============================================================

class EducationHubSection(BaseModel):
    """Individual section within the Education Hub pillar page"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    h2_title: str  # H2 heading for section
    content: str  # Rich HTML from TipTap (2000+ words recommended per section)
    order: int  # For reordering sections
    video_ids: List[str] = []  # Associated video IDs for this section
    show_letters: bool = False  # Show letter templates in this section

class EducationHub(BaseModel):
    """Main Education Hub pillar page (singleton pattern)"""
    model_config = ConfigDict(extra="ignore")
    id: str = "education_hub"  # Singleton ID
    
    # Hero Content
    h1_title: str = "The Ultimate 2025 Guide to Credit Repair: Your FCRA & CROA Legal Handbook"
    hero_subtitle: str = "Your Complete Resource for Understanding Credit, Consumer Rights, and Ethical Credit Repair"
    hero_image_url: Optional[str] = ""
    
    # Introduction (before sections)
    introduction: str = ""  # Rich HTML - 500-1000 words intro
    
    # Main Sections (topic clusters)
    sections: List[EducationHubSection] = []
    
    # Table of Contents Settings
    show_toc: bool = True
    toc_title: str = "Guide Navigation"
    
    # SEO
    seo_meta_title: str = "Complete Credit Repair Guide 2025 | FCRA & CROA Handbook"
    seo_meta_description: str = "Comprehensive 5000+ word guide to credit repair, FCRA rights, CROA protections, and step-by-step DIY credit improvement strategies."
    seo_keywords: List[str] = ["credit repair", "FCRA", "CROA", "credit dispute", "credit score improvement"]
    canonical_url: str = "/credit-repair-guide"
    
    # Schema.org
    schema_type: str = "HowTo"  # HowTo for step-by-step guides
    
    # Publishing
    status: str = "published"  # draft, published
    slug: str = "credit-repair-guide"
    
    # Analytics
    views: int = 0
    avg_time_on_page: int = 0  # seconds
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_edited_by: Optional[str] = ""

class EducationHubUpdate(BaseModel):
    """Model for updating Education Hub"""
    h1_title: Optional[str] = None
    hero_subtitle: Optional[str] = None
    hero_image_url: Optional[str] = None
    introduction: Optional[str] = None
    sections: Optional[List[EducationHubSection]] = None
    show_toc: Optional[bool] = None
    toc_title: Optional[str] = None
    seo_meta_title: Optional[str] = None
    seo_meta_description: Optional[str] = None
    seo_keywords: Optional[List[str]] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = None
    status: Optional[str] = None
    slug: Optional[str] = None


class EducationVideo(BaseModel):
    """Video content with full SEO and placement control"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    title: str
    description: str = ""  # Rich text description/transcript
    
    # Video Source (one of these)
    video_type: str = "youtube"  # youtube, vimeo, upload, url
    youtube_url: Optional[str] = ""  # Full YouTube URL
    vimeo_url: Optional[str] = ""  # Full Vimeo URL
    uploaded_video_url: Optional[str] = ""  # If uploaded to server
    custom_embed_code: Optional[str] = ""  # For other platforms
    
    # Thumbnail
    thumbnail_url: Optional[str] = ""  # Custom thumbnail or auto-generated
    
    # FULL SEO FEATURES (NEW)
    url_slug: str = ""  # e.g., "fcra-section-609-explained"
    title_tag: str = ""  # SEO title tag (50-60 chars)
    meta_description: str = ""  # Meta description (150-160 chars)
    keywords: List[str] = []  # Focus keywords
    schema_type: str = "VideoObject"  # Schema.org type
    video_schema_data: dict = {}  # Additional schema properties
    canonical_url: Optional[str] = ""  # Canonical URL if needed
    
    # Video Metadata for Schema
    duration_iso: Optional[str] = ""  # ISO 8601 format (PT1M30S)
    upload_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_url: Optional[str] = ""  # Direct video file URL
    embed_url: Optional[str] = ""  # Embed player URL
    
    # Placement Control (NEW)
    placements: List[dict] = []  # [{"page_id": "...", "page_type": "blog/page/education_hub", "position": 1, "x": 0, "y": 0}]
    
    # Organization
    category: str = "general"  # fcra, croa, dispute_tactics, credit_basics, etc.
    duration_seconds: int = 0  # Video length
    tags: List[str] = []  # Video tags
    
    # Display
    featured: bool = False  # Show prominently
    order: int = 0  # For sorting
    show_in_gallery: bool = True  # Show in video gallery
    
    # Analytics
    views: int = 0
    
    # Status
    status: str = "published"  # draft, published
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EducationVideoCreate(BaseModel):
    """Model for creating education video"""
    title: str
    description: str = ""
    video_type: str = "youtube"
    youtube_url: Optional[str] = ""
    vimeo_url: Optional[str] = ""
    uploaded_video_url: Optional[str] = ""
    custom_embed_code: Optional[str] = ""
    thumbnail_url: Optional[str] = ""
    url_slug: str = ""
    title_tag: str = ""
    meta_description: str = ""
    keywords: List[str] = []
    schema_type: str = "VideoObject"
    video_schema_data: dict = {}
    canonical_url: Optional[str] = ""
    duration_iso: Optional[str] = ""
    content_url: Optional[str] = ""
    embed_url: Optional[str] = ""
    placements: List[dict] = []
    category: str = "general"
    duration_seconds: int = 0
    tags: List[str] = []
    featured: bool = False
    order: int = 0
    show_in_gallery: bool = True
    status: str = "published"

class EducationVideoUpdate(BaseModel):
    """Model for updating education video"""
    title: Optional[str] = None
    description: Optional[str] = None
    video_type: Optional[str] = None
    youtube_url: Optional[str] = None
    vimeo_url: Optional[str] = None
    uploaded_video_url: Optional[str] = None
    custom_embed_code: Optional[str] = None
    thumbnail_url: Optional[str] = None
    url_slug: Optional[str] = None
    title_tag: Optional[str] = None
    meta_description: Optional[str] = None
    keywords: Optional[List[str]] = None
    schema_type: Optional[str] = None
    video_schema_data: Optional[dict] = None
    canonical_url: Optional[str] = None
    duration_iso: Optional[str] = None
    content_url: Optional[str] = None
    embed_url: Optional[str] = None
    placements: Optional[List[dict]] = None
    category: Optional[str] = None
    duration_seconds: Optional[int] = None
    tags: Optional[List[str]] = None
    featured: Optional[bool] = None
    order: Optional[int] = None
    show_in_gallery: Optional[bool] = None
    status: Optional[str] = None


class SampleLetterField(BaseModel):
    """Fillable field definition for letter templates"""
    field_id: str  # Unique ID like "consumer_name", "account_number"
    field_label: str  # Display label: "Your Full Name", "Account Number"
    field_type: str = "text"  # text, textarea, date, number, select
    placeholder: str = ""  # Placeholder text
    required: bool = True
    options: List[str] = []  # For select fields
    help_text: str = ""  # Helper text for user

class SampleLetter(BaseModel):
    """Sample letter template for consumers to fill and download"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    title: str  # "609 Dispute Letter to Equifax"
    description: str  # When to use this letter
    letter_type: str = "credit_bureau"  # credit_bureau, creditor, goodwill, cease_and_desist
    target_recipient: str = "generic"  # equifax, experian, transunion, creditor, collection_agency
    
    # Letter Template
    letter_body: str  # Full letter text with {{placeholders}} for dynamic fields
    
    # Fillable Fields
    fields: List[SampleLetterField] = []  # Ordered list of fields user must fill
    
    # SEO & Info
    usage_instructions: str = ""  # Rich HTML - how to use this letter
    legal_disclaimer: str = "This letter is provided for informational purposes only and does not constitute legal advice."
    success_rate: Optional[str] = ""  # "High", "Moderate", "Varies"
    
    # Organization
    category: str = "dispute"  # dispute, goodwill, validation, cease_and_desist
    order: int = 0
    
    # Display
    featured: bool = False
    
    # Analytics
    downloads: int = 0
    
    # Status
    status: str = "published"  # draft, published
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SampleLetterCreate(BaseModel):
    """Model for creating sample letter"""
    title: str
    description: str
    letter_type: str = "credit_bureau"
    target_recipient: str = "generic"
    letter_body: str
    fields: List[SampleLetterField] = []
    usage_instructions: str = ""
    legal_disclaimer: str = "This letter is provided for informational purposes only and does not constitute legal advice."
    success_rate: Optional[str] = ""
    category: str = "dispute"
    order: int = 0
    featured: bool = False
    status: str = "published"

class SampleLetterUpdate(BaseModel):
    """Model for updating sample letter"""
    title: Optional[str] = None
    description: Optional[str] = None
    letter_type: Optional[str] = None
    target_recipient: Optional[str] = None
    letter_body: Optional[str] = None
    fields: Optional[List[SampleLetterField]] = None
    usage_instructions: Optional[str] = None
    legal_disclaimer: Optional[str] = None
    success_rate: Optional[str] = None
    category: Optional[str] = None
    order: Optional[int] = None
    featured: Optional[bool] = None
    status: Optional[str] = None



# Affiliate Models
class Affiliate(BaseModel):
    """Model for affiliate product/service pages"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    slug: str
    description: str  # Short description
    content: str  # Full content/review
    affiliate_link: str
    company_name: str
    
    # Rating and features
    rating: Optional[float] = None  # Out of 5
    pros: List[str] = []
    cons: List[str] = []
    
    # Pricing info
    pricing_text: Optional[str] = None  # e.g., "$99/month"
    pricing_details: Optional[str] = None
    
    # Images
    featured_image_url: Optional[str] = None
    featured_image_alt: Optional[str] = None
    logo_url: Optional[str] = None
    
    # Commission and tracking
    commission_rate: Optional[str] = None
    disclosure: Optional[str] = None  # Affiliate disclosure
    
    # Features/highlights
    key_features: List[str] = []
    
    # SEO
    seo: Optional[SEOMetadata] = None
    
    # Status
    status: str = "draft"  # draft, published
    featured: bool = False
    order: int = 0  # For sorting
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    created_by: Optional[str] = None
    last_edited_by: Optional[str] = None

class AffiliateCreate(BaseModel):
    """Model for creating affiliate pages"""
    title: str
    slug: str
    description: str
    content: str
    affiliate_link: str
    company_name: str
    rating: Optional[float] = None
    pros: List[str] = []
    cons: List[str] = []
    pricing_text: Optional[str] = None
    pricing_details: Optional[str] = None
    featured_image_url: Optional[str] = None
    featured_image_alt: Optional[str] = None
    logo_url: Optional[str] = None
    commission_rate: Optional[str] = None
    disclosure: Optional[str] = None
    key_features: List[str] = []
    seo: Optional[SEOMetadata] = None
    status: str = "draft"
    featured: bool = False
    order: int = 0

class AffiliateUpdate(BaseModel):
    """Model for updating affiliate pages"""
    title: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    affiliate_link: Optional[str] = None
    company_name: Optional[str] = None
    rating: Optional[float] = None
    pros: Optional[List[str]] = None
    cons: Optional[List[str]] = None
    pricing_text: Optional[str] = None
    pricing_details: Optional[str] = None
    featured_image_url: Optional[str] = None
    featured_image_alt: Optional[str] = None
    logo_url: Optional[str] = None
    commission_rate: Optional[str] = None
    disclosure: Optional[str] = None
    key_features: Optional[List[str]] = None
    seo: Optional[SEOMetadata] = None
    status: Optional[str] = None
    featured: Optional[bool] = None
    order: Optional[int] = None




# Partner Leads Model
class PartnerLead(BaseModel):
    """Model for partner/affiliate signup leads"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str
    last_name: str
    email: str
    mobile_phone: str
    company_name: Optional[str] = None
    partner_type: str  # real-estate, mortgage, car-dealership, social-media-influencer
    
    # Metadata
    source_url: Optional[str] = None  # Which page they signed up from
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Status tracking
    status: str = "new"  # new, contacted, approved, rejected
    notes: Optional[str] = None
    
    # CRM sync
    crm_synced: bool = False
    crm_sync_date: Optional[datetime] = None
    crm_response: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PartnerLeadCreate(BaseModel):
    """Model for creating partner leads"""
    first_name: str
    last_name: str
    email: str
    mobile_phone: str
    company_name: Optional[str] = None



# Page Builder Models
class PageBuilderLayout(BaseModel):
    """Model for page builder layouts (visual editor pages)"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    page_id: str  # Reference to the Page this layout belongs to
    layout_data: dict  # JSON structure of the page layout
    # layout_data structure:
    # {
    #   "components": [
    #     {
    #       "id": "unique-id",
    #       "type": "text|image|video|button|blog_list|review_list|hero|section",
    #       "props": {...},  # Component-specific properties
    #       "position": {"x": 0, "y": 0},
    #       "size": {"width": "100%", "height": "auto"},
    #       "order": 0
    #     }
    #   ],
    #   "settings": {
    #     "background": "#fff",
    #     "padding": "20px",
    #     ...
    #   }
    # }
    version: int = 1  # For version control
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None
    last_edited_by: Optional[str] = None


# Banner & Popup Model
class BannerPopup(BaseModel):
    id: Optional[str] = None
    type: str  # "banner" or "popup"
    title: str
    content: str
    cta_text: Optional[str] = None
    cta_link: Optional[str] = None
    position: Optional[str] = "top"  # For banners: top, bottom, floating
    trigger: Optional[str] = "onload"  # For popups: onload, onexit, onscroll, timed
    delay: Optional[int] = 0  # Delay in seconds
    display_pages: List[str] = []  # Empty = all pages, or specific slugs
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    dismissible: bool = True
    background_color: Optional[str] = "#3B82F6"
    text_color: Optional[str] = "#FFFFFF"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# ==============================================================
# LAWSUIT MANAGEMENT ENHANCEMENTS
# ==============================================================

class LawsuitViolation(BaseModel):
    """Model for lawsuit violations/legal claims"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str  # e.g., "Violation of 15 U.S.C. § 1681i"
    description: str  # e.g., "Failure to reinvestigate disputed information"
    law_section: Optional[str] = None  # e.g., "15 U.S.C. § 1681i"
    law_name: Optional[str] = None  # e.g., "Fair Credit Reporting Act"
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LawsuitOutcomeStage(BaseModel):
    """Model for lawsuit outcome/stage options"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str  # e.g., "Discovery Phase", "Settlement Negotiations", "Trial Pending"
    description: Optional[str] = None
    is_final_outcome: bool = False  # True for final outcomes like "Settled", "Won", "Dismissed"
    display_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LawsuitCategoryOption(BaseModel):
    """Model for lawsuit category options"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str  # e.g., "Client", "Industry", "Class Action"
    description: Optional[str] = None
    display_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LawsuitTypeOption(BaseModel):
    """Model for lawsuit type options"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str  # e.g., "FCRA", "FDCPA", "State Law Claims"
    description: Optional[str] = None
    schema_template: Optional[dict] = None  # Pre-built schema for this type
    display_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PartyRole(BaseModel):
    """Model for party roles in lawsuits"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str  # e.g., "Plaintiff", "Defendant", "Amicus Curiae", "Intervenor"
    description: Optional[str] = None
    display_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# LAWSUIT MANAGEMENT
# ==============================================================

class Lawsuit(BaseModel):
    """Model for lawsuits filed"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    case_number: str
    lawsuit_category_id: str  # Reference to LawsuitCategoryOption
    lawsuit_type_ids: List[str] = []  # Multi-select references to LawsuitTypeOption
    party_role_id: str  # Reference to PartyRole (plaintiff/defendant/etc.)
    topic: str
    description: str
    brief_description: str
    date_filed: datetime
    
    # Legal Claims & Violations
    violation_ids: List[str] = []  # References to LawsuitViolation
    
    # Case Status
    outcome_stage_id: Optional[str] = None  # Reference to LawsuitOutcomeStage
    outcome_notes: Optional[str] = None  # Additional notes about the outcome
    
    # Documents & Links
    filed_documents: List[dict] = []  # [{url: "", title: ""}]
    public_docket_link: Optional[str] = None
    press_coverage: List[str] = []  # URLs to news coverage
    
    # Relationships
    related_company: Optional[str] = None
    related_press_release_id: Optional[str] = None
    related_blog_posts: Optional[List[str]] = None  # List of blog post IDs
    
    # Rich Content (keeping these for additional details)
    case_summary_html: Optional[str] = None  # For additional case background
    
    # Administrative
    is_active: bool = True
    
    # Legacy fields (keeping for backward compatibility)
    background: Optional[str] = None
    legal_claims: Optional[str] = None
    current_status: Optional[str] = None
    personal_impact: Optional[str] = None
    implications: Optional[str] = None
    conclusion: Optional[str] = None
    
    # SEO & Metadata
    slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []
    schema_type: Optional[str] = "LegalService"
    schema_data: Optional[dict] = {}
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LawsuitCreate(BaseModel):
    title: str
    case_number: str
    lawsuit_category_id: str
    lawsuit_type_ids: List[str] = []
    party_role_id: str
    topic: str
    description: str
    brief_description: str
    date_filed: datetime
    violation_ids: List[str] = []
    outcome_stage_id: Optional[str] = None
    outcome_notes: Optional[str] = None
    filed_documents: List[dict] = []
    public_docket_link: Optional[str] = None
    press_coverage: List[str] = []
    related_company: Optional[str] = None
    related_press_release_id: Optional[str] = None
    related_blog_posts: Optional[List[str]] = None
    case_summary_html: Optional[str] = None
    is_active: bool = True
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []
    schema_type: Optional[str] = "LegalService"
    schema_data: Optional[dict] = {}


class LawsuitUpdate(BaseModel):
    """Model for updating lawsuits"""
    title: Optional[str] = None
    case_number: Optional[str] = None
    lawsuit_category_id: Optional[str] = None
    lawsuit_type_ids: Optional[List[str]] = None
    party_role_id: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    brief_description: Optional[str] = None
    date_filed: Optional[datetime] = None
    violation_ids: Optional[List[str]] = None
    outcome_stage_id: Optional[str] = None
    outcome_notes: Optional[str] = None
    filed_documents: Optional[List[dict]] = None
    public_docket_link: Optional[str] = None
    press_coverage: Optional[List[str]] = None
    related_company: Optional[str] = None
    related_press_release_id: Optional[str] = None
    related_blog_posts: Optional[List[str]] = None
    case_summary_html: Optional[str] = None
    is_active: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = None
    schema_type: Optional[str] = None
    schema_data: Optional[dict] = None


# ==============================================================
# PRESS RELEASE MANAGEMENT
# ==============================================================

class PressRelease(BaseModel):
    """Model for press releases"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    slug: str  # Auto-generated from title for URL
    content: str  # Rich text/HTML content
    excerpt: str  # For list view
    publish_date: datetime
    is_published: bool = True
    featured_image: Optional[str] = None
    
    # Related Content
    related_blog_posts: List[str] = []  # Array of blog post IDs
    related_lawsuits: List[str] = []  # Array of lawsuit IDs
    related_employees: List[str] = []  # Array of team member IDs
    
    # SEO
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    
    # Schema.org
    schema_type: Optional[str] = "NewsArticle"
    schema_data: Optional[dict] = {}
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None


class PressReleaseCreate(BaseModel):
    """Model for creating press releases"""
    title: str
    content: str
    excerpt: str
    publish_date: datetime
    is_published: bool = True
    featured_image: Optional[str] = None
    related_blog_posts: List[str] = []
    related_lawsuits: List[str] = []
    related_employees: List[str] = []
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = "NewsArticle"
    schema_data: Optional[dict] = {}


class PressReleaseUpdate(BaseModel):
    """Model for updating press releases"""
    title: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    publish_date: Optional[datetime] = None
    is_published: Optional[bool] = None
    featured_image: Optional[str] = None
    related_blog_posts: Optional[List[str]] = None
    related_lawsuits: Optional[List[str]] = None
    related_employees: Optional[List[str]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = None
    schema_data: Optional[dict] = None
    related_employees: Optional[List[str]] = None
    # Employee linking
    related_employees: Optional[List[str]] = None  # Array of team member IDs


# ==============================================================
# ANNOUNCEMENT MANAGEMENT
# ==============================================================

class Announcement(BaseModel):
    """Model for company announcements (promotions, acquisitions, new products/services)"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    slug: str  # Auto-generated from title for URL
    content: str  # Rich text/HTML content
    excerpt: str  # For list view/preview
    announcement_type: str = "general"  # general, promotion, acquisition, product, service, partnership
    publish_date: datetime
    is_published: bool = True
    featured_image: Optional[str] = None
    
    # Related Content
    related_employees: List[str] = []  # Array of team member IDs
    related_press_releases: List[str] = []  # Array of press release IDs
    related_blog_posts: List[str] = []  # Array of blog post IDs
    
    # SEO
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    
    # Schema.org
    schema_type: Optional[str] = "NewsArticle"
    schema_data: Optional[dict] = {}
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None


class AnnouncementCreate(BaseModel):
    """Model for creating announcements"""
    title: str
    content: str
    excerpt: str
    announcement_type: str = "general"
    publish_date: datetime
    is_published: bool = True
    featured_image: Optional[str] = None
    related_employees: List[str] = []
    related_press_releases: List[str] = []
    related_blog_posts: List[str] = []
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = "NewsArticle"
    schema_data: Optional[dict] = {}


class AnnouncementUpdate(BaseModel):
    """Model for updating announcements"""
    title: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    announcement_type: Optional[str] = None
    publish_date: Optional[datetime] = None
    is_published: Optional[bool] = None
    featured_image: Optional[str] = None
    related_employees: Optional[List[str]] = None
    related_press_releases: Optional[List[str]] = None
    related_blog_posts: Optional[List[str]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = None
    schema_types: Optional[List[str]] = None
    schema_data: Optional[dict] = None


# ==============================================================
# CREDLOCITY PARTNERS MANAGEMENT
# ==============================================================

class PartnerType(BaseModel):
    """Model for partner types/categories"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # e.g., "Real Estate", "Funding", "Mortgage"
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None  # Icon name or URL
    display_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Partner(BaseModel):
    """Model for Credlocity Partners - E-E-A-T optimized"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    name: str  # Full name of partner/representative
    slug: str
    company_name: str
    partner_type_id: str  # Link to PartnerType
    tagline: Optional[str] = None  # Short one-liner
    
    # Profile Images
    photo_url: Optional[str] = None  # Personal photo
    company_logo: Optional[str] = None  # Company logo
    cover_image: Optional[str] = None  # Banner/cover image
    
    # Bio & Description (E-E-A-T: Experience, Expertise)
    short_bio: str  # For listing cards
    full_bio: str  # Detailed bio for landing page
    what_we_do: Optional[str] = None  # Services description
    
    # Credentials & Expertise (E-E-A-T: Expertise, Authoritativeness)
    credentials: List[str] = []  # Certifications, licenses, etc.
    education: List[dict] = []  # [{"institution": "", "degree": "", "year": ""}]
    years_experience: Optional[int] = None
    specializations: List[str] = []
    awards: List[dict] = []  # [{"name": "", "year": "", "issuer": ""}]
    
    # Social Proof (E-E-A-T: Trustworthiness)
    testimonials: List[dict] = []  # Quick testimonials on profile
    featured_review_ids: List[str] = []  # Link to detailed reviews
    client_count: Optional[int] = None  # "Served 500+ clients"
    success_rate: Optional[str] = None  # "98% client satisfaction"
    
    # Contact & Links
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    social_links: dict = {}  # {"linkedin": "", "twitter": "", "facebook": ""}
    
    # Related Content (Interlinking)
    related_announcement_ids: List[str] = []
    related_press_release_ids: List[str] = []
    related_blog_post_ids: List[str] = []
    
    # SEO (E-E-A-T optimized)
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: List[str] = []
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_types: List[str] = ["Person", "Organization", "LocalBusiness", "ProfessionalService"]
    schema_data: dict = {}
    
    # Publishing
    is_published: bool = True
    is_featured: bool = False  # Show on homepage
    display_order: int = 0
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PartnerCreate(BaseModel):
    """Model for creating partners"""
    name: str
    company_name: str
    partner_type_id: str
    tagline: Optional[str] = None
    photo_url: Optional[str] = None
    company_logo: Optional[str] = None
    cover_image: Optional[str] = None
    short_bio: str
    full_bio: str
    what_we_do: Optional[str] = None
    credentials: List[str] = []
    education: List[dict] = []
    years_experience: Optional[int] = None
    specializations: List[str] = []
    awards: List[dict] = []
    testimonials: List[dict] = []
    featured_review_ids: List[str] = []
    client_count: Optional[int] = None
    success_rate: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    social_links: dict = {}
    related_announcement_ids: List[str] = []
    related_press_release_ids: List[str] = []
    related_blog_post_ids: List[str] = []
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: List[str] = []
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_types: List[str] = []
    is_published: bool = True
    is_featured: bool = False
    display_order: int = 0


class PartnerUpdate(BaseModel):
    """Model for updating partners"""
    name: Optional[str] = None
    company_name: Optional[str] = None
    partner_type_id: Optional[str] = None
    tagline: Optional[str] = None
    photo_url: Optional[str] = None
    company_logo: Optional[str] = None
    cover_image: Optional[str] = None
    short_bio: Optional[str] = None
    full_bio: Optional[str] = None
    what_we_do: Optional[str] = None
    credentials: Optional[List[str]] = None
    education: Optional[List[dict]] = None
    years_experience: Optional[int] = None
    specializations: Optional[List[str]] = None
    awards: Optional[List[dict]] = None
    testimonials: Optional[List[dict]] = None
    featured_review_ids: Optional[List[str]] = None
    client_count: Optional[int] = None
    success_rate: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    social_links: Optional[dict] = None
    related_announcement_ids: Optional[List[str]] = None
    related_press_release_ids: Optional[List[str]] = None
    related_blog_post_ids: Optional[List[str]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_types: Optional[List[str]] = None
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    display_order: Optional[int] = None


# ==============================================================
# REVIEW CATEGORY MANAGEMENT
# ==============================================================

class ReviewCategory(BaseModel):
    """Model for review categories/sections"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # e.g., "Clients Who Switched from Lexington Law"
    slug: str  # Auto-generated from name
    description: Optional[str] = ""  # Optional description for the section
    display_order: int = 0  # Order on the page
    is_active: bool = True  # Show/hide on public page
    icon: Optional[str] = ""  # Optional emoji or icon class
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewCategoryCreate(BaseModel):
    """Model for creating review categories"""
    name: str
    description: Optional[str] = ""
    display_order: int = 0
    is_active: bool = True
    icon: Optional[str] = ""


class ReviewCategoryUpdate(BaseModel):
    """Model for updating review categories"""
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    icon: Optional[str] = None


# ==============================================================
# LEGAL PAGES MANAGEMENT
# ==============================================================

class LegalPage(BaseModel):
    """Model for legal and policy pages"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str  # e.g., "Privacy Policy", "Terms of Service"
    slug: str  # Auto-generated from title for URL
    content: str  # Rich text/HTML content
    is_published: bool = True
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # SEO
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None


class LegalPageCreate(BaseModel):
    """Model for creating legal pages"""
    title: str
    content: str
    is_published: bool = True
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class LegalPageUpdate(BaseModel):
    """Model for updating legal pages"""
    title: Optional[str] = None
    content: Optional[str] = None
    is_published: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class PageBuilderLayoutUpdate(BaseModel):
    """Model for updating page builder layouts"""
    layout_data: Optional[dict] = None
    version: Optional[int] = None

    partner_type: str
    source_url: Optional[str] = None



# ==============================================================
# OUTSOURCING MANAGEMENT MODELS
# ==============================================================

class CRMPlatform(BaseModel):
    """Model for CRM platforms that outsource partners use"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # e.g., "DisputeFox", "Credit Repair Cloud"
    description: Optional[str] = None
    website: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CRMPlatformCreate(BaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None


# ==============================================================
# OUTSOURCING CLIENT REVIEWS
# ==============================================================

class OutsourceClientReview(BaseModel):
    """Model for outsourcing client reviews/testimonials"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Company Info
    company_name: str
    company_logo_url: Optional[str] = ""
    slug: Optional[str] = ""  # URL slug for individual page
    
    # CEO Info
    ceo_name: str
    ceo_photo_url: Optional[str] = ""
    ceo_title: Optional[str] = "CEO"
    
    # Testimonial
    testimonial_text: str
    full_story: Optional[str] = ""  # Extended story/case study content (HTML)
    
    # Video Review (file upload or YouTube embed)
    video_type: Optional[str] = None  # "file" or "youtube"
    video_file_url: Optional[str] = ""  # For uploaded files
    youtube_embed_url: Optional[str] = ""  # For YouTube embeds
    
    # Switched From Another Company
    switched_from_another: bool = False
    previous_company_name: Optional[str] = ""
    why_they_switched: Optional[str] = ""
    
    # Results & Stats (for SEO-rich detail page)
    results_stats: Optional[dict] = {}  # e.g., {"disputes_processed": 500, "deletion_rate": "85%", "months_partnered": 12}
    
    # SEO Fields
    seo_meta_title: Optional[str] = ""
    seo_meta_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    
    # Display Settings
    display_order: int = 0
    is_active: bool = True
    featured: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None

class OutsourceClientReviewCreate(BaseModel):
    """Model for creating outsourcing client reviews"""
    company_name: str
    company_logo_url: Optional[str] = ""
    slug: Optional[str] = ""
    ceo_name: str
    ceo_photo_url: Optional[str] = ""
    ceo_title: Optional[str] = "CEO"
    testimonial_text: str
    full_story: Optional[str] = ""
    video_type: Optional[str] = None
    video_file_url: Optional[str] = ""
    youtube_embed_url: Optional[str] = ""
    switched_from_another: bool = False
    previous_company_name: Optional[str] = ""
    why_they_switched: Optional[str] = ""
    results_stats: Optional[dict] = {}
    seo_meta_title: Optional[str] = ""
    seo_meta_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    display_order: int = 0
    is_active: bool = True
    featured: bool = False

class OutsourceClientReviewUpdate(BaseModel):
    """Model for updating outsourcing client reviews"""
    company_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    slug: Optional[str] = None
    ceo_name: Optional[str] = None
    ceo_photo_url: Optional[str] = None
    ceo_title: Optional[str] = None
    testimonial_text: Optional[str] = None
    full_story: Optional[str] = None
    video_type: Optional[str] = None
    video_file_url: Optional[str] = None
    youtube_embed_url: Optional[str] = None
    switched_from_another: Optional[bool] = None
    previous_company_name: Optional[str] = None
    why_they_switched: Optional[str] = None
    results_stats: Optional[dict] = None
    seo_meta_title: Optional[str] = None
    seo_meta_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    featured: Optional[bool] = None



class OutsourcePartnerInquiry(BaseModel):
    """Model for initial outsource partner inquiry form submissions"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    contact_first_name: str
    contact_last_name: str
    contact_email: EmailStr
    contact_phone: str
    position: str  # Position at the CRO
    current_platform: str  # CRM platform they're using
    status: str = "pending"  # pending, approved, disapproved, pending_review
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OutsourcePartnerInquiryCreate(BaseModel):
    company_name: str
    contact_first_name: str
    contact_last_name: str
    contact_email: EmailStr
    contact_phone: str
    position: str
    current_platform: str

class PricingHistoryEntry(BaseModel):
    """Model for tracking pricing changes history"""
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cost_per_consumer: float
    active_client_count: int
    changed_by: Optional[str] = None
    notes: Optional[str] = None

class OutsourcePartner(BaseModel):
    """Model for approved outsource partners"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    inquiry_id: Optional[str] = None
    company_name: str
    contact_first_name: str
    contact_last_name: str
    contact_email: EmailStr
    contact_phone: str
    position: str
    crm_platform_id: Optional[str] = None
    crm_username: Optional[str] = None
    crm_password: Optional[str] = None
    status: str = "approved"
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: bool = True
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    portal_password_hash: Optional[str] = None
    last_portal_login: Optional[datetime] = None
    
    # Pricing fields
    cost_per_consumer: float = 0.0  # Price per consumer/file
    active_client_count: int = 0  # Number of active clients being processed
    billing_cycle: str = "monthly"  # weekly, bi-weekly, monthly
    
    # Pricing history
    pricing_history: list = []  # List of PricingHistoryEntry as dicts

class OutsourcePartnerCreate(BaseModel):
    inquiry_id: Optional[str] = None
    company_name: str
    contact_first_name: str
    contact_last_name: str
    contact_email: EmailStr
    contact_phone: str
    position: str
    crm_platform_id: Optional[str] = None
    crm_username: Optional[str] = None
    crm_password: Optional[str] = None
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = None
    cost_per_consumer: float = 0.0
    active_client_count: int = 0
    billing_cycle: str = "monthly"

class OutsourcePartnerUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_first_name: Optional[str] = None
    contact_last_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    position: Optional[str] = None
    crm_platform_id: Optional[str] = None
    crm_username: Optional[str] = None
    crm_password: Optional[str] = None
    status: Optional[str] = None
    billing_email: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: Optional[bool] = None
    cost_per_consumer: Optional[float] = None
    active_client_count: Optional[int] = None
    billing_cycle: Optional[str] = None

class WorkLog(BaseModel):
    """Model for tracking work done for outsource partners"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    work_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str
    hours_worked: Optional[float] = None
    disputes_filed: Optional[int] = None
    accounts_processed: Optional[int] = None
    notes: Optional[str] = None
    performed_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class WorkLogCreate(BaseModel):
    partner_id: str
    work_date: Optional[datetime] = None
    description: str
    hours_worked: Optional[float] = None
    disputes_filed: Optional[int] = None
    accounts_processed: Optional[int] = None
    notes: Optional[str] = None

class OutsourceInvoice(BaseModel):
    """Model for invoices to outsource partners"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    invoice_number: str
    invoice_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: datetime
    line_items: List[Dict[str, Any]] = []
    subtotal: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    status: str = "unpaid"
    paid_date: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OutsourceInvoiceCreate(BaseModel):
    partner_id: str
    due_date: datetime
    line_items: List[Dict[str, Any]]
    tax_rate: Optional[float] = 0.0


# ==============================================================
# ATTORNEY MARKETPLACE & CASE MANAGEMENT MODELS
# ==============================================================

# ----- User Profile Extensions -----

class UserProfile(BaseModel):
    """Extended user profile with marketplace associations"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # Reference to users collection
    role: str  # credlocity_admin, credlocity_support, company_owner, company_staff, attorney, attorney_staff
    company_id: Optional[str] = None  # For company users
    attorney_profile_id: Optional[str] = None  # For attorneys
    permissions: List[str] = []  # Additional custom permissions
    is_verified: bool = False
    verification_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ----- Credit Repair Company Models -----

class CreditRepairCompany(BaseModel):
    """Credit repair company that subscribes to the platform"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    legal_name: str
    dba_name: Optional[str] = None
    
    # Contact Information
    email: str
    phone: str
    website: Optional[str] = None
    address: str
    city: str
    state: str
    zip_code: str
    
    # Business Details
    tax_id: Optional[str] = None  # Encrypted
    business_license: Optional[str] = None
    states_licensed: List[str] = []
    
    # Banking (Encrypted)
    bank_account_info: Optional[str] = None  # Encrypted
    bank_routing_number: Optional[str] = None  # Encrypted
    bank_account_number: Optional[str] = None  # Encrypted
    
    # Platform Status
    status: str = "pending"  # pending, active, suspended, cancelled
    subscription_status: str = "none"  # none, trial, active, past_due, cancelled
    signup_fee_paid: bool = False
    signup_fee_paid_at: Optional[datetime] = None
    
    # Settings
    auto_publish_cases: bool = False
    default_case_tier: Optional[str] = None
    notification_preferences: Dict[str, Any] = {}
    
    # Metadata
    owner_user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreditRepairCompanyCreate(BaseModel):
    """Create a credit repair company"""
    name: str
    legal_name: str
    email: str
    phone: str
    address: str
    city: str
    state: str
    zip_code: str
    dba_name: Optional[str] = None
    website: Optional[str] = None
    states_licensed: List[str] = []


class CompanySubscription(BaseModel):
    """Subscription record for a credit repair company"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    
    # Subscription Details
    plan_type: str = "standard"  # standard, premium, enterprise
    status: str = "active"  # active, past_due, cancelled, suspended
    
    # Pricing
    signup_fee: float = 500.00
    monthly_fee: float = 199.99
    signup_fee_paid: bool = False
    signup_fee_paid_at: Optional[datetime] = None
    
    # Billing
    current_period_start: datetime
    current_period_end: datetime
    next_billing_date: datetime
    
    # Payment Integration
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    payment_method_id: Optional[str] = None
    
    # Grace Period
    past_due_since: Optional[datetime] = None
    cancellation_date: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompanyRevenueSplit(BaseModel):
    """Revenue split record for case settlements"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    case_id: str
    
    # Settlement Details
    settlement_amount: float
    settlement_date: datetime
    
    # Revenue Split
    company_share_percentage: float = 60.0
    credlocity_share_percentage: float = 40.0
    company_amount: float
    credlocity_amount: float
    
    # Payment Status
    payment_status: str = "pending"  # pending, processing, paid, failed
    payment_date: Optional[datetime] = None
    payment_reference: Optional[str] = None
    
    # Metadata (immutable after creation)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ----- Attorney Profile Models -----

class AttorneyProfile(BaseModel):
    """Attorney profile for marketplace participation"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # Reference to users collection
    
    # Personal Info
    first_name: str
    last_name: str
    email: str
    phone: str
    
    # Professional Info
    bar_number: Optional[str] = None  # Encrypted
    bar_number_verified: bool = False
    licensed_states: List[str] = []
    law_firm_name: Optional[str] = None
    years_experience: Optional[int] = None
    practice_areas: List[str] = []  # consumer_law, credit_repair, debt_collection, etc.
    
    # Verification Status
    verified: bool = False
    malpractice_insurance_on_file: bool = False
    background_check_completed: bool = False
    payment_method_on_file: bool = False
    terms_accepted: bool = False
    terms_accepted_at: Optional[datetime] = None
    
    # Platform Activity
    total_bids: int = 0
    total_cases_won: int = 0
    total_cases_settled: int = 0
    average_settlement_amount: Optional[float] = None
    success_rate: Optional[float] = None
    
    # Profile
    bio: Optional[str] = None
    profile_photo_url: Optional[str] = None
    
    # Banking (Encrypted)
    bank_account_info: Optional[str] = None
    
    # Status
    status: str = "pending"  # pending, active, suspended, banned
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AttorneyProfileCreate(BaseModel):
    """Create attorney profile"""
    first_name: str
    last_name: str
    email: str
    phone: str
    bar_number: Optional[str] = None
    licensed_states: List[str] = []
    law_firm_name: Optional[str] = None
    practice_areas: List[str] = []
    bio: Optional[str] = None


# ----- Case Management Models -----

class Case(BaseModel):
    """Main case record for credit repair disputes"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    
    # Case Identification
    case_number: str  # Auto-generated unique identifier
    case_title: str
    
    # Client Information (Some may be encrypted)
    client_first_name: str
    client_last_name: str
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_ssn: Optional[str] = None  # Encrypted
    client_dob: Optional[str] = None  # Encrypted
    
    # Case Details
    case_type: str = "credit_repair"  # credit_repair, debt_collection, fcra_violation, fdcpa_violation
    case_tier: str = "bronze"  # bronze, silver, gold, platinum
    estimated_value: Optional[float] = None
    
    # Violations Summary
    violation_count: int = 0
    violation_types: List[str] = []  # fcra_1681, fdcpa_1692, tcpa, etc.
    
    # Warner Compliance
    warner_compliant: bool = False
    warner_score: Optional[int] = None
    warner_certifications: Dict[str, bool] = {}
    
    # Documentation Quality
    documentation_score: Optional[int] = None
    has_credit_reports: bool = False
    has_power_of_attorney: bool = False
    has_dispute_letters: bool = False
    
    # Interview Status
    interview_completed: bool = False
    interview_date: Optional[datetime] = None
    interview_notes: Optional[str] = None
    
    # Case Status
    status: str = "draft"  # draft, ready, published, bidding, assigned, in_progress, settled, closed
    readiness_score: Optional[int] = None
    readiness_notes: Optional[str] = None
    
    # Marketplace
    published_at: Optional[datetime] = None
    marketplace_listing_id: Optional[str] = None
    
    # Assignment
    assigned_attorney_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    payment_verified: bool = False
    
    # Settlement
    settlement_amount: Optional[float] = None
    settlement_date: Optional[datetime] = None
    settlement_documents: List[str] = []
    
    # Timeline
    timeline_start_date: Optional[datetime] = None
    timeline_events: List[Dict] = []
    
    # Metadata
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseCreate(BaseModel):
    """Create a new case"""
    case_title: str
    client_first_name: str
    client_last_name: str
    case_type: str = "credit_repair"
    client_email: Optional[str] = None
    client_phone: Optional[str] = None


class CaseViolation(BaseModel):
    """Specific violation associated with a case"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    
    # Violation Details
    violation_type: str  # fcra_1681e, fcra_1681i, fdcpa_1692e, fdcpa_1692f, tcpa, etc.
    violation_code: str  # Specific section code
    violation_description: str
    
    # Severity
    severity: str = "moderate"  # minor, moderate, major, willful
    estimated_damages: Optional[float] = None
    
    # Evidence
    evidence_type: str = "document"  # document, recording, correspondence
    evidence_document_ids: List[str] = []
    evidence_summary: Optional[str] = None
    
    # Dates
    violation_date: Optional[datetime] = None
    discovered_date: Optional[datetime] = None
    
    # Status
    status: str = "identified"  # identified, documented, disputed, resolved
    
    # Metadata
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseDispute(BaseModel):
    """Dispute record associated with a case"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    
    # Dispute Details
    dispute_type: str  # initial, reinvestigation, escalated, legal
    creditor_name: str
    account_number: Optional[str] = None  # Partial or masked
    bureau: str  # experian, equifax, transunion
    
    # Amounts
    disputed_amount: Optional[float] = None
    original_amount: Optional[float] = None
    
    # Timeline
    dispute_sent_date: Optional[datetime] = None
    response_due_date: Optional[datetime] = None
    response_received_date: Optional[datetime] = None
    
    # Response
    response_type: Optional[str] = None  # verified, updated, deleted, no_response
    response_summary: Optional[str] = None
    
    # Documents
    dispute_letter_id: Optional[str] = None
    response_document_ids: List[str] = []
    
    # Status
    status: str = "pending"  # draft, pending, in_review, resolved, escalated
    resolution: Optional[str] = None
    
    # Metadata
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseDocument(BaseModel):
    """Document associated with a case"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    
    # Document Info
    document_type: str  # credit_report, dispute_letter, response, power_of_attorney, identification, evidence
    document_name: str
    file_name: str
    file_size: int
    file_type: str  # pdf, jpg, png, doc, etc.
    
    # Storage
    storage_path: str
    url: str
    preview_url: Optional[str] = None  # Redacted version for preview
    
    # Access Control
    visible_before_payment: bool = False
    sensitive: bool = False
    
    # Metadata
    uploaded_by: str
    upload_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    
    # Status
    status: str = "active"  # active, archived, deleted


class CaseAssignment(BaseModel):
    """Case assignment to attorney"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    attorney_id: str
    company_id: str
    
    # Assignment Details
    bid_id: Optional[str] = None
    bid_amount: Optional[float] = None
    
    # Payment
    payment_verified: bool = False
    payment_verification_date: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    
    # Status
    status: str = "pending"  # pending, active, completed, cancelled
    
    # Timeline
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Granted By
    granted_by: str


# ----- Marketplace Models -----

class MarketplaceListing(BaseModel):
    """Case listing in the attorney marketplace"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    company_id: str
    
    # Listing Details
    title: str
    description: str
    case_tier: str
    violation_types: List[str] = []
    estimated_value: float
    
    # Warner Compliance Display
    warner_compliant: bool = False
    warner_score: Optional[int] = None
    
    # Location
    client_state: str
    jurisdiction: Optional[str] = None
    
    # Bidding
    bidding_type: str = "open"  # open, sealed, fixed_price
    minimum_bid: Optional[float] = None
    buy_now_price: Optional[float] = None
    
    # Timeline
    listing_start: datetime
    listing_end: Optional[datetime] = None
    
    # Status
    status: str = "active"  # active, bidding, closed, awarded, cancelled
    
    # Statistics
    view_count: int = 0
    bid_count: int = 0
    
    # Winning
    winning_bid_id: Optional[str] = None
    winning_attorney_id: Optional[str] = None
    awarded_at: Optional[datetime] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseBid(BaseModel):
    """Attorney bid on a marketplace listing"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    listing_id: str
    case_id: str
    attorney_id: str
    
    # Bid Details
    bid_amount: float
    bid_type: str = "standard"  # standard, buy_now, pledge
    
    # Attorney Proposal
    proposed_strategy: Optional[str] = None
    estimated_timeline: Optional[str] = None
    contingency_percentage: Optional[float] = None  # For contingency fee arrangements
    
    # Status
    status: str = "pending"  # draft, pending, accepted, rejected, withdrawn, expired
    
    # Response
    response_notes: Optional[str] = None
    responded_at: Optional[datetime] = None
    responded_by: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BidCreate(BaseModel):
    """Create a bid on a listing"""
    listing_id: str
    bid_amount: float
    bid_type: str = "standard"
    proposed_strategy: Optional[str] = None
    estimated_timeline: Optional[str] = None
    contingency_percentage: Optional[float] = None


# ----- Interview & Timeline Models -----

class CaseInterview(BaseModel):
    """Interview record for case assessment"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    
    # Interview Details
    interview_type: str = "initial"  # initial, follow_up, final
    conducted_by: str
    interview_date: datetime
    
    # Questions & Answers
    questions_answers: List[Dict[str, Any]] = []
    
    # Assessment
    credibility_score: Optional[int] = None
    completeness_score: Optional[int] = None
    
    # Notes
    notes: Optional[str] = None
    red_flags: List[str] = []
    strengths: List[str] = []
    
    # Status
    status: str = "scheduled"  # scheduled, completed, cancelled
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseTimelineEvent(BaseModel):
    """Timeline event for case tracking"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    
    # Event Details
    event_type: str  # dispute_sent, response_received, violation_identified, document_uploaded, status_change
    event_date: datetime
    description: str
    
    # References
    related_document_id: Optional[str] = None
    related_dispute_id: Optional[str] = None
    related_violation_id: Optional[str] = None
    
    # Actor
    created_by: str
    created_by_role: str  # company_staff, attorney, system
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ----- Audit & Access Logging -----

class AuditLogEntry(BaseModel):
    """Audit log entry for compliance"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Event
    event_type: str
    user_id: Optional[str] = None
    action: str
    
    # Resource
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    
    # Result
    success: bool = True
    failure_reason: Optional[str] = None
    
    # Context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    # Retention
    retention_years: int = 7
    
    # Timestamp
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentAccessLog(BaseModel):
    """Document access log for compliance tracking"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    case_id: str
    user_id: str
    
    # Access Details
    access_type: str  # view, download, preview
    access_granted: bool = True
    
    # Context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Timestamp
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    notes: Optional[str] = None
    terms: Optional[str] = None

class OutsourceInvoiceUpdate(BaseModel):
    due_date: Optional[datetime] = None
    line_items: Optional[List[Dict[str, Any]]] = None
    tax_rate: Optional[float] = None
    status: Optional[str] = None
    paid_date: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    notes: Optional[str] = None

class ServiceAgreement(BaseModel):
    """Model for service agreements with outsource partners"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    agreement_type: str
    effective_date: datetime
    expiration_date: Optional[datetime] = None
    services_included: List[str] = []
    pricing_model: Optional[str] = None
    rate: Optional[float] = None
    agreement_file_url: Optional[str] = None
    signed_date: Optional[datetime] = None
    signed_by: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ServiceAgreementCreate(BaseModel):
    partner_id: str
    agreement_type: str
    effective_date: datetime
    expiration_date: Optional[datetime] = None
    services_included: List[str] = []
    pricing_model: Optional[str] = None
    rate: Optional[float] = None


# ==============================================================
# OUTSOURCE ESCALATION TICKET SYSTEM
# ==============================================================

class OutsourceTicketCategory(BaseModel):
    """Model for configurable ticket escalation categories"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # e.g., "Billing Issue", "Technical Issue"
    description: Optional[str] = None
    default_urgency: str = "medium"  # low, medium, high, critical
    display_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OutsourceEscalationTicket(BaseModel):
    """Model for outsourcing escalation tickets"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticket_number: str  # Auto-generated like ESC-2025-0001
    partner_id: str
    
    # Ticket Details
    category_id: str  # Reference to OutsourceTicketCategory
    subject: str
    notes: str  # Detailed description/notes
    
    # Contact Info
    contact_name: str  # Who they spoke to on the phone
    communication_method: str  # "phone", "email", "text"
    
    # Submitted by (auto-filled from logged-in user)
    submitted_by_id: str
    submitted_by_name: str
    
    # Auto-calculated fields
    urgency: str = "medium"  # low, medium, high, critical
    response_time_hours: int = 24  # Based on urgency
    
    # Status tracking
    status: str = "open"  # open, in_progress, waiting, resolved, closed
    assigned_to_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    
    # Resolution
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[str] = None
    resolved_by_name: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_by: Optional[datetime] = None

class OutsourceEscalationTicketCreate(BaseModel):
    partner_id: str
    category_id: str
    subject: str
    notes: str
    contact_name: str
    communication_method: str  # "phone", "email", "text"

class OutsourceEscalationTicketUpdate(BaseModel):
    category_id: Optional[str] = None
    subject: Optional[str] = None
    notes: Optional[str] = None
    contact_name: Optional[str] = None
    communication_method: Optional[str] = None
    urgency: Optional[str] = None
    status: Optional[str] = None
    assigned_to_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    resolution_notes: Optional[str] = None


# ==============================================================
# ENHANCED WORK LOG MODEL
# ==============================================================

class OutsourceWorkLog(BaseModel):
    """Enhanced model for tracking work done for outsource partners"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    work_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disputes_processed: int = 0
    letters_sent: int = 0
    description: Optional[str] = None
    
    # Archive functionality
    is_archived: bool = False
    archived_at: Optional[datetime] = None
    archived_by: Optional[str] = None
    
    # Tracking
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OutsourceWorkLogCreate(BaseModel):
    partner_id: str
    work_date: Optional[datetime] = None
    disputes_processed: int = 0
    letters_sent: int = 0
    description: Optional[str] = None

class OutsourceWorkLogUpdate(BaseModel):
    work_date: Optional[datetime] = None
    disputes_processed: Optional[int] = None
    letters_sent: Optional[int] = None
    description: Optional[str] = None
    is_archived: Optional[bool] = None


# ==============================================================
# OUTSOURCE PARTNER NOTES SYSTEM
# ==============================================================

class OutsourcePartnerNote(BaseModel):
    """Model for partner notes with document attachments"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    
    # Note content
    title: str
    content: str
    category: str  # billing, customer_care, technical, general, contract, etc.
    
    # Communication source
    source_type: str  # email, text, phone, internal_update, file_processing
    
    # Contact info based on source type
    contact_email: Optional[str] = None  # For email source
    contact_phone: Optional[str] = None  # For phone/text source
    contact_name: Optional[str] = None   # For phone/text source
    
    # Attachments
    attachments: List[dict] = []  # [{filename, url, uploaded_at}]
    
    # Tracking
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# OUTSOURCE PARTNER AGREEMENTS
# ==============================================================

class OutsourcePartnerAgreement(BaseModel):
    """Model for partner agreement documents"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    
    # Agreement details
    title: str
    description: Optional[str] = None
    agreement_type: str  # service_agreement, nda, amendment, addendum, etc.
    
    # File info
    file_name: str
    file_url: str
    file_size: Optional[int] = None
    
    # Dates
    effective_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    
    # Status
    status: str = "active"  # active, expired, terminated, pending
    
    # Tracking
    uploaded_by_id: str
    uploaded_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# OUTSOURCE BILLING CREDITS & DISCOUNTS
# ==============================================================

class OutsourcePartnerCredit(BaseModel):
    """Model for partner billing credits"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    
    # Credit type
    credit_type: str  # month_credit, dollar_credit, freemium
    
    # Credit details
    description: str
    
    # Values (based on type)
    months: Optional[int] = None          # For month_credit
    dollar_amount: Optional[float] = None  # For dollar_credit
    
    # Validity
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: Optional[datetime] = None
    
    # Status
    status: str = "active"  # active, used, expired, cancelled
    applied_to_invoice_id: Optional[str] = None
    applied_at: Optional[datetime] = None
    
    # Tracking
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutsourcePartnerDiscount(BaseModel):
    """Model for partner billing discounts"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_id: str
    
    # Discount type
    discount_type: str  # percentage, dollar_amount, per_file
    
    # Discount details
    description: str
    
    # Values (based on type)
    percentage: Optional[float] = None       # For percentage discount (e.g., 10 for 10%)
    dollar_amount: Optional[float] = None    # For flat dollar discount
    per_file_amount: Optional[float] = None  # For per-file discount (e.g., $3 per file)
    
    # Duration
    duration_months: Optional[int] = None    # How many months this applies
    start_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_date: Optional[datetime] = None
    
    # Status
    status: str = "active"  # active, expired, cancelled
    
    # Tracking
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================
# OUTSOURCE COUPON SYSTEM
# ==============================================================

class OutsourceCoupon(BaseModel):
    """Model for billing coupons"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Coupon code
    code: str  # Unique coupon code
    name: str
    description: Optional[str] = None
    
    # Discount rules
    discount_type: str  # percentage, dollar_amount, per_file, free_months
    discount_value: float  # The value (percentage, dollar amount, or months)
    
    # Applicability
    applies_to: str = "all"  # all, new_partners, specific_partners
    specific_partner_ids: List[str] = []
    
    # Duration/Limits
    duration_months: Optional[int] = None  # How many months discount applies
    max_uses: Optional[int] = None         # Maximum number of times coupon can be used
    times_used: int = 0
    
    # Validity
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: Optional[datetime] = None
    
    # Status
    status: str = "active"  # active, expired, depleted, disabled
    
    # Tracking
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutsourceAppliedCoupon(BaseModel):
    """Model for tracking applied coupons to partners"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    coupon_id: str
    coupon_code: str
    partner_id: str
    
    # Applied details
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    applied_by_id: str
    applied_by_name: str
    
    # Duration tracking
    months_remaining: Optional[int] = None
    expires_at: Optional[datetime] = None
    
    # Status
    status: str = "active"  # active, expired, cancelled



# ==============================================================
# CLIENT MANAGEMENT SYSTEM MODELS
# ==============================================================

class CMSSettings(BaseModel):
    """Model for configurable CMS settings like routing URLs"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    setting_key: str  # e.g., 'credit_report_url', 'calendars', 'hot_lead_redirect'
    setting_value: str  # The actual value
    setting_type: str = "string"  # string, json, array
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClientCalendar(BaseModel):
    """Model for round-robin calendar scheduling"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    url: str
    owner_name: Optional[str] = None
    is_active: bool = True
    weight: int = 1  # For weighted round-robin
    last_assigned: Optional[datetime] = None
    total_assignments: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Client(BaseModel):
    """Model for credit repair clients/leads"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Personal Information
    first_name: str
    last_name: str
    email: str
    phone: str
    date_of_birth: Optional[str] = None
    ssn_last4: Optional[str] = None
    
    # Address (collected separately or from agreement)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    
    # Assessment Answers
    credit_score_range: Optional[str] = None  # poor, fair, good, excellent, unknown
    timeline: Optional[str] = None  # asap, 1-3months, 3-6months, 6months+
    selected_package: Optional[str] = None  # family, aggressive, fraud, payment-plan, unsure
    experience: Optional[str] = None  # never, diy, other-company, currently-using
    decision_maker: Optional[str] = None  # me-alone, discuss-spouse, spouse-decides, family-input
    
    # Lead Scoring
    assessment_score: int = 0
    lead_status: str = "cold"  # hot, warm, cold
    
    # Package & Pricing Info
    package_name: Optional[str] = None
    package_price: Optional[float] = None
    
    # Upfront Fees
    credit_report_fee: float = 49.95
    enotary_fee: float = 39.95
    credit_report_paid: bool = False
    enotary_paid: bool = False
    
    # Agreement Status
    agreement_signed: bool = False
    agreement_signed_at: Optional[datetime] = None
    agreement_document_id: Optional[str] = None
    electronic_signature: Optional[str] = None
    signature_ip: Optional[str] = None
    
    # Status & Workflow
    status: str = "new"  # new, contacted, consultation_scheduled, converted, inactive
    assigned_calendar_id: Optional[str] = None
    assigned_to: Optional[str] = None
    
    # CRM Integration
    external_crm_id: Optional[str] = None
    crm_sync_status: Optional[str] = None
    
    # Notes & Activity
    notes: Optional[str] = None
    last_contact_date: Optional[datetime] = None
    next_followup_date: Optional[datetime] = None
    
    # Tracking
    source: str = "intake_form"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    consent_given: bool = True


class ClientAgreement(BaseModel):
    """Model for storing signed client agreements"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    
    # Agreement Details
    agreement_type: str = "free_trial"  # free_trial, service_agreement
    agreement_version: str = "1.0"
    
    # Package Details at time of signing
    package_name: Optional[str] = None
    package_price: Optional[float] = None
    credit_report_fee: float = 49.95
    enotary_fee: float = 39.95
    
    # Signature Info
    electronic_signature: str
    signature_date: str
    signature_ip: str
    signature_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cancellation Dates
    federal_cancel_date: str
    pa_state_cancel_date: Optional[str] = None
    
    # Document Storage
    document_url: Optional[str] = None  # URL to stored PDF
    document_content: Optional[str] = None  # Base64 encoded PDF or HTML content
    
    # Status
    status: str = "active"  # active, cancelled, expired
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClientNote(BaseModel):
    """Model for client notes"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    title: str
    content: str
    category: str = "general"  # general, call, email, sms, meeting
    source_type: Optional[str] = None
    source_details: Optional[str] = None
    document_url: Optional[str] = None
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClientCredit(BaseModel):
    """Model for client billing credits"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    credit_type: str  # month_credit, dollar_credit, freemium
    description: str
    months: Optional[int] = None
    dollar_amount: Optional[float] = None
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: Optional[datetime] = None
    status: str = "active"
    applied_to_invoice_id: Optional[str] = None
    applied_at: Optional[datetime] = None
    created_by_id: str
    created_by_name: str


# ============ FORM BUILDER MODELS ============

class IntakeFormConfig(BaseModel):
    """Configurable settings for intake forms - same form structure, different routing/settings"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Basic Info
    name: str  # e.g., "Main Intake Form", "Landing Page Form"
    slug: str  # URL path where form appears: /intake, /apply, /get-started
    description: Optional[str] = None
    is_active: bool = True
    
    # Header Customization
    header_title: str = "Unlock Your Credit Potential"
    header_subtitle: str = "Take our 2-minute assessment to discover your personalized path to financial freedom"
    
    # Credit Report Link (for HOT leads)
    credit_report_url: str = "https://credlocity.scorexer.com/scorefusion/scorefusion-signup.jsp?code=50a153cc-c"
    credit_report_button_text: str = "Get My Credit Report ($49.95)"
    
    # Calendar IDs for round-robin (for WARM/COLD leads)
    # References FormCalendar collection - rotates per submission
    calendar_ids: List[str] = []
    default_calendar_url: str = "https://calendly.com/credlocity/oneonone"
    warm_lead_button_text: str = "Schedule My Free Strategy Session"
    cold_lead_button_text: str = "Get My Free Consultation"
    
    # Package Options (shown in Step 3)
    packages: List[Dict[str, Any]] = [
        {"key": "fraud", "name": "Fraud Protection Plan", "price": 99.95, "description": "Perfect for recent identity theft victims"},
        {"key": "aggressive", "name": "Aggressive Package", "price": 179.95, "description": "Our most popular comprehensive plan"},
        {"key": "family", "name": "Family Plan", "price": 279.95, "description": "Coverage for you and your spouse"}
    ]
    
    # Upfront Fees
    credit_report_fee: float = 49.95
    enotary_fee: float = 39.95
    
    # CRM Settings (pulse.disputeprocess.com)
    crm_enabled: bool = True
    crm_tab_info_id: str = "QTduWHF0U2lXOWNPNFZvN085bUJ3dz09"
    crm_company_id: str = "UmJ1YWN4dkUvbThaUXJqVkdKZ3paUT09"
    
    # Metadata
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FormCalendar(BaseModel):
    """Calendars available for round-robin assignment"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # e.g., "John's Calendar", "Sales Team A"
    url: str  # Calendly or other booking URL
    weight: int = 1  # Higher = gets more assignments
    is_active: bool = True
    total_assignments: int = 0
    last_assigned: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ COLLECTIONS MANAGEMENT SYSTEM MODELS ============

class CollectionsEmployee(BaseModel):
    """Employee model for collections team with hierarchy support"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    password_hash: str
    full_name: str
    role: str = "collections_agent"  # collections_agent, team_leader, collections_manager, director, admin
    reports_to_id: Optional[str] = None  # FK to another employee for hierarchy
    base_salary: float = 500.00
    is_active: bool = True
    phone: Optional[str] = None
    hire_date: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionsAccount(BaseModel):
    """Past due account for collections management"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str  # FK to clients collection
    client_name: str  # Denormalized for quick access
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    package_type: str = "individual"  # individual, couple
    monthly_rate: float = 179.95  # 179.95 or 279.95
    first_failed_payment_date: str  # ISO date string YYYY-MM-DD
    days_past_due: int = 0  # Computed: current_date - first_failed_payment_date
    current_tier: int = 1  # 1-4, auto-assigned based on days_past_due
    past_due_balance: float = 0.0
    account_status: str = "active"  # active, disputed, payment_plan, resolved, legal_review
    last_contact_date: Optional[str] = None
    assigned_rep_id: Optional[str] = None  # FK to collections_employees
    assigned_rep_name: Optional[str] = None  # Denormalized
    notes_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionsContact(BaseModel):
    """Individual contact log entry"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str  # FK to collections_accounts
    contact_date: str  # YYYY-MM-DD
    contact_type: str  # call, text, email
    contact_number: int  # 1-3
    contact_time: str  # ISO datetime
    outcome: str  # Required, min 10 chars
    template_used: Optional[str] = None
    completed_by_rep_id: str
    completed_by_rep_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionsDailyCompliance(BaseModel):
    """Daily compliance tracking per account"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str
    date: str  # YYYY-MM-DD
    calls_completed: int = 0  # max 3
    texts_completed: int = 0  # max 3
    emails_completed: int = 0  # max 3
    compliance_met: bool = False  # True when 3/3/3
    auto_note_generated: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionsTicket(BaseModel):
    """Dispute ticket for collections accounts"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticket_number: str  # Auto-generated: CT-YYYYMMDD-XXX
    account_id: str
    client_name: str
    account_balance: float
    dispute_date: str  # ISO datetime
    assigned_rep_id: str
    assigned_rep_name: Optional[str] = None
    status: str = "open"  # open, under_investigation, resolved_valid_debt, resolved_client_error, resolved_credlocity_error, escalated_legal
    priority: str = "high"  # high, medium, low
    investigation_notes: Optional[str] = None
    findings_summary: Optional[str] = None
    resolved_by_id: Optional[str] = None
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaymentAgreement(BaseModel):
    """Payment agreement/plan for collections"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str
    client_name: str
    tier_accepted: int  # 1-4
    tier_name: str  # e.g., "Tier 3 (Modified)"
    
    # Balance Info
    original_balance: float
    discount_percentage: float = 0.0
    discount_amount: float = 0.0
    adjusted_balance: float
    
    # Payment Terms
    down_payment_amount: float
    down_payment_date: str  # YYYY-MM-DD
    remaining_balance: float
    payment_frequency: str  # weekly, bi_weekly, monthly
    number_of_payments: int
    payment_amount: float
    total_plan_amount: float
    
    # Fee Breakdown - Non-Waivable
    credit_reports_charge: float = 199.80
    services_rendered_charge: float = 0.0
    non_waivable_total: float = 0.0
    
    # Fee Breakdown - Waivable (Original vs Adjusted)
    late_fees_original: float = 0.0
    late_fees_adjusted: float = 0.0
    collection_fee_original: float = 0.0
    collection_fee_adjusted: float = 0.0
    file_processing_fee_original: float = 0.0
    file_processing_fee_adjusted: float = 0.0
    payment_processing_fee_original: float = 0.0
    payment_processing_fee_adjusted: float = 0.0
    conditional_charge_original: Optional[float] = None
    conditional_charge_adjusted: Optional[float] = None
    conditional_charge_description: Optional[str] = None
    
    # Computed totals
    adjusted_fees_total: float = 0.0
    waived_amount_total: float = 0.0
    
    # Documents
    agreement_pdf_url: Optional[str] = None
    cc_auth_pdf_url: Optional[str] = None
    
    # Status & Metadata
    status: str = "active"  # active, completed, defaulted, cancelled
    created_by_rep_id: str
    created_by_rep_name: Optional[str] = None
    approved_by_id: Optional[str] = None
    approved_by_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaymentScheduleItem(BaseModel):
    """Individual payment in a payment schedule"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agreement_id: str
    payment_number: int  # 0 = down payment, 1+ = installments
    payment_date: str  # YYYY-MM-DD
    payment_amount: float
    status: str = "scheduled"  # scheduled, paid, failed, skipped
    paid_date: Optional[str] = None
    rep_commission_amount: float = 0.0
    rep_commission_paid: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EmployeeCommissionOverride(BaseModel):
    """Custom commission rates for specific employees"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    
    # Tier rates
    tier_1_rate: Optional[float] = None  # default 5.00
    tier_1_bonus_48hr: Optional[float] = None  # default 1.00
    tier_2_full_rate: Optional[float] = None  # default 12.00
    tier_2_plan_rate: Optional[float] = None  # default 6.00
    tier_3_full_rate: Optional[float] = None  # default 20.00
    tier_3_plan_rate: Optional[float] = None  # default 10.00
    tier_4_full_rate: Optional[float] = None  # default 30.00
    tier_4_plan_rate: Optional[float] = None  # default 15.00
    
    # Payment plan rates
    down_payment_rate: Optional[float] = None  # default 5.00
    monthly_payment_rate: Optional[float] = None  # default 3.00
    completion_bonus_rate: Optional[float] = None  # default 2.00
    
    # Bonus rates
    retention_rate: Optional[float] = None  # default 3.00
    reactivation_rate: Optional[float] = None  # default 5.00
    
    override_reason: str
    approved_by_id: str
    approved_by_name: Optional[str] = None
    effective_date: str  # YYYY-MM-DD
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommissionTransaction(BaseModel):
    """Individual commission earned"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    employee_name: Optional[str] = None
    account_id: Optional[str] = None
    agreement_id: Optional[str] = None
    transaction_type: str  # direct_collection, payment_plan_down, payment_plan_installment, payment_plan_completion, retention, reactivation, team_override, team_bonus, dept_override, dept_bonus, performance_bonus
    amount_collected: float = 0.0
    commission_rate: float = 0.0
    commission_amount: float = 0.0
    payment_date: str  # YYYY-MM-DD
    commission_month: str  # YYYY-MM-01
    status: str = "pending"  # pending, approved, paid
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommissionEarnings(BaseModel):
    """Monthly commission summary per employee"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    employee_name: Optional[str] = None
    month: str  # YYYY-MM-01
    base_salary: float = 500.00
    direct_collections_commission: float = 0.0
    payment_plan_commission: float = 0.0
    retention_bonus: float = 0.0
    reactivation_bonus: float = 0.0
    team_override_commission: float = 0.0  # for team leaders
    team_performance_bonus: float = 0.0
    department_override_commission: float = 0.0  # for managers
    department_performance_bonus: float = 0.0
    monthly_performance_bonus: float = 0.0
    quality_bonus: float = 0.0
    total_earnings: float = 0.0
    total_collected_amount: float = 0.0
    payment_status: str = "pending"  # pending, processing, paid
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionsNote(BaseModel):
    """Notes for collections accounts"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str
    ticket_id: Optional[str] = None
    note_type: str = "manual"  # manual, auto_compliance, system, investigation
    note_text: str
    created_by_id: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionsSettings(BaseModel):
    """System settings for collections module"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    setting_key: str
    setting_value: str
    setting_type: str = "string"  # string, number, json
    description: Optional[str] = None
    updated_by_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
