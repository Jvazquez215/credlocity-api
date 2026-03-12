"""
Seed script to create all pages in the CMS database
This ensures all pages are listed and editable in the page builder
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timezone
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Define all pages that should exist in the CMS
PAGES = [
    {
        "title": "Home",
        "slug": "home",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Credlocity - CREDIT REPAIR DONE RIGHT",
            "meta_description": "The most comprehensive credit education and repair service on the internet",
            "og_title": "Credlocity - CREDIT REPAIR DONE RIGHT",
            "og_description": "The most comprehensive credit education and repair service on the internet",
            "og_image": "",
            "canonical_url": "/",
            "robots": "index, follow",
            "keywords": "credit repair, credit score, credit education"
        }
    },
    {
        "title": "Pricing & Plans",
        "slug": "pricing",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Pricing & Plans - Credlocity",
            "meta_description": "Choose the right credit repair plan for your needs. 30-day free trial available.",
            "robots": "index, follow"
        }
    },
    {
        "title": "Understanding Credit Scores",
        "slug": "credit-scores",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Understanding Credit Scores - Credlocity",
            "meta_description": "Learn everything about credit scores and how to improve yours",
            "robots": "index, follow"
        }
    },
    {
        "title": "Why Choose Us",
        "slug": "why-us",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Why Choose Credlocity - Your Trusted Credit Repair Partner",
            "meta_description": "Discover why Credlocity is the best choice for credit repair",
            "robots": "index, follow"
        }
    },
    {
        "title": "Collection Removal",
        "slug": "collection-removal",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Collection Removal Services - Credlocity",
            "meta_description": "Expert collection removal services",
            "robots": "index, follow"
        }
    },
    {
        "title": "Report a Company",
        "slug": "report-company",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Report a Credit Repair Company - Credlocity",
            "meta_description": "Report unethical credit repair companies",
            "robots": "index, follow"
        }
    },
    {
        "title": "Success Stories",
        "slug": "success-stories",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Success Stories - Real Results from Credlocity Clients",
            "meta_description": "Read real success stories from our satisfied clients",
            "robots": "index, follow"
        }
    },
    {
        "title": "Partners Hub",
        "slug": "partners",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Partner Program - Credlocity",
            "meta_description": "Join our partner program",
            "robots": "index, follow"
        }
    },
    {
        "title": "Real Estate Partner Program",
        "slug": "partners/real-estate",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Real Estate Partner Program - Credlocity",
            "meta_description": "Partner with us to help your real estate clients",
            "robots": "index, follow"
        }
    },
    {
        "title": "Mortgage Professionals Program",
        "slug": "partners/mortgage-professionals",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Mortgage Professionals Partner Program - Credlocity",
            "meta_description": "Partner with us to help your mortgage clients",
            "robots": "index, follow"
        }
    },
    {
        "title": "Car Dealerships Program",
        "slug": "partners/car-dealerships",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Car Dealerships Partner Program - Credlocity",
            "meta_description": "Partner with us to help your car dealership clients",
            "robots": "index, follow"
        }
    },
    {
        "title": "Social Media Influencers Program",
        "slug": "partners/social-media-influencers",
        "content": "",
        "status": "published",
        "placement": "main",
        "seo": {
            "meta_title": "Social Media Influencers Partner Program - Credlocity",
            "meta_description": "Partner with us as a social media influencer",
            "robots": "index, follow"
        }
    }
]

async def seed_pages():
    """Create all pages in the database"""
    print("🌱 Starting page seeding...")
    
    # Get admin user
    admin = await db.users.find_one({"email": "Admin@credlocity.com"})
    if not admin:
        print("❌ Admin user not found. Please run initialization first.")
        return
    
    admin_id = admin.get("id")
    created_count = 0
    updated_count = 0
    
    for page_data in PAGES:
        # Check if page already exists
        existing = await db.pages.find_one({"slug": page_data["slug"]})
        
        if existing:
            print(f"⏭️  Page '{page_data['title']}' already exists, skipping...")
            updated_count += 1
            continue
        
        # Create new page
        page = {
            "id": str(uuid.uuid4()),
            "title": page_data["title"],
            "slug": page_data["slug"],
            "content": page_data["content"],
            "parent_id": page_data.get("parent_id"),
            "status": page_data["status"],
            "placement": page_data["placement"],
            "seo": page_data["seo"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": admin_id
        }
        
        await db.pages.insert_one(page)
        print(f"✅ Created page: {page_data['title']} (/{page_data['slug']})")
        created_count += 1
    
    print(f"\n🎉 Page seeding complete!")
    print(f"   Created: {created_count} pages")
    print(f"   Existing: {updated_count} pages")
    print(f"   Total: {len(PAGES)} pages")

async def main():
    try:
        await seed_pages()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(main())
