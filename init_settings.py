"""
Initialize default site settings in database
Phase 4 - Site Settings System
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = 'test_database'

async def init_site_settings():
    """Initialize default site settings if not exists"""
    
    client = get_client(MONGO_URL)
    db = client[DB_NAME]
    
    print("🔧 Initializing site settings...")
    
    # Check if settings already exist
    existing = await db.site_settings.find_one({"id": "site_settings"})
    
    if existing:
        print("✓ Site settings already exist - skipping initialization")
        client.close()
        return
    
    # Create default settings
    default_settings = {
        "id": "site_settings",
        "logo_url": "",
        "logo_dark_url": "",
        "favicon_url": "",
        "brand_color_primary": "#2563eb",
        "brand_color_secondary": "#1e40af",
        "default_meta_title": "Credlocity - Ethical Credit Repair Since 2008",
        "default_meta_description": "America's trusted credit repair company. Ethical, transparent credit repair services helping over 79,000 clients improve their credit scores.",
        "default_keywords": ["credit repair", "fix credit", "credit score", "credit restoration"],
        "default_og_image": "",
        "organization_name": "Credlocity",
        "organization_logo": "",
        "organization_phone": "",
        "organization_email": "info@credlocity.com",
        "organization_address": {},
        "social_profiles": {},
        "google_analytics_id": "",
        "google_search_console_id": "",
        "google_tag_manager_id": "",
        "facebook_pixel_id": "",
        "sitemap_enabled": True,
        "robots_txt_custom": "",
        "admin_logo_editable_by": ["super_admin"],
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.site_settings.insert_one(default_settings)
    print("✅ Default site settings created successfully!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(init_site_settings())
