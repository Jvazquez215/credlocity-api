"""
Seed the Home page with its current design as page builder components
This allows the user to edit the existing home page design
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
import os
from datetime import datetime, timezone
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = get_client(mongo_url)
db = client[os.environ['DB_NAME']]

# Home page design as page builder components
HOME_LAYOUT = {
    "components": [
        # Hero Section
        {
            "id": "hero-section",
            "type": "section",
            "order": 0,
            "props": {
                "style": {
                    "background": "linear-gradient(135deg, #012697 0%, #59a52c 100%)",
                    "color": "#ffffff",
                    "padding": "80px 16px",
                    "textAlign": "center"
                },
                "children": []
            }
        },
        {
            "id": "hero-heading",
            "type": "heading",
            "order": 1,
            "props": {
                "content": "CREDIT REPAIR DONE RIGHT",
                "level": "h1",
                "style": {
                    "fontSize": "48px",
                    "fontWeight": "bold",
                    "marginBottom": "24px",
                    "textAlign": "center",
                    "color": "#ffffff"
                }
            }
        },
        {
            "id": "hero-subtitle",
            "type": "text",
            "order": 2,
            "props": {
                "content": "The most comprehensive credit education and repair service on the internet",
                "style": {
                    "fontSize": "24px",
                    "marginBottom": "32px",
                    "textAlign": "center",
                    "color": "#f0f0f0"
                }
            }
        },
        
        # Trust Indicators Section
        {
            "id": "trust-heading",
            "type": "heading",
            "order": 3,
            "props": {
                "content": "Why Choose Credlocity",
                "level": "h2",
                "style": {
                    "fontSize": "36px",
                    "fontWeight": "bold",
                    "marginTop": "60px",
                    "marginBottom": "16px",
                    "textAlign": "center",
                    "color": "#012697"
                }
            }
        },
        {
            "id": "trust-subtitle",
            "type": "text",
            "order": 4,
            "props": {
                "content": "We're not just another credit repair company. We're your partner in financial freedom.",
                "style": {
                    "fontSize": "20px",
                    "marginBottom": "48px",
                    "textAlign": "center",
                    "color": "#666666"
                }
            }
        },
        
        # Testimonials Section
        {
            "id": "testimonials-heading",
            "type": "heading",
            "order": 5,
            "props": {
                "content": "Real Results from Real Clients",
                "level": "h2",
                "style": {
                    "fontSize": "36px",
                    "fontWeight": "bold",
                    "marginTop": "60px",
                    "marginBottom": "16px",
                    "textAlign": "center",
                    "color": "#012697"
                }
            }
        },
        {
            "id": "testimonials-subtitle",
            "type": "text",
            "order": 6,
            "props": {
                "content": "Don't just take our word for it. See what our clients are saying about their credit repair journey.",
                "style": {
                    "fontSize": "20px",
                    "marginBottom": "48px",
                    "textAlign": "center",
                    "color": "#666666"
                }
            }
        },
        {
            "id": "reviews-list",
            "type": "review_list",
            "order": 7,
            "props": {
                "limit": 3,
                "featured": True,
                "layout": "grid",
                "columns": "3",
                "show_ratings": True,
                "show_image": True,
                "show_score_improvement": True,
                "source_filter": "all",
                "auto_play": False,
                "style": {
                    "marginBottom": "60px"
                }
            }
        },
        
        # Blog Section
        {
            "id": "blog-heading",
            "type": "heading",
            "order": 8,
            "props": {
                "content": "Latest Credit Education Articles",
                "level": "h2",
                "style": {
                    "fontSize": "36px",
                    "fontWeight": "bold",
                    "marginTop": "60px",
                    "marginBottom": "16px",
                    "textAlign": "center",
                    "color": "#012697"
                }
            }
        },
        {
            "id": "blog-list",
            "type": "blog_list",
            "order": 9,
            "props": {
                "limit": 3,
                "category": "all",
                "layout": "grid",
                "columns": "3",
                "show_excerpt": True,
                "show_image": True,
                "show_date": True,
                "show_author": True,
                "style": {
                    "marginBottom": "60px"
                }
            }
        },
        
        # CTA Section
        {
            "id": "cta-heading",
            "type": "heading",
            "order": 10,
            "props": {
                "content": "Ready to Take Control of Your Credit?",
                "level": "h2",
                "style": {
                    "fontSize": "36px",
                    "fontWeight": "bold",
                    "marginTop": "60px",
                    "marginBottom": "16px",
                    "textAlign": "center",
                    "color": "#012697"
                }
            }
        },
        {
            "id": "cta-text",
            "type": "text",
            "order": 11,
            "props": {
                "content": "Start your 30-day free trial today. No credit card required. No first work fee. Cancel anytime.",
                "style": {
                    "fontSize": "20px",
                    "marginBottom": "32px",
                    "textAlign": "center",
                    "color": "#666666"
                }
            }
        },
        {
            "id": "cta-button",
            "type": "button",
            "order": 12,
            "props": {
                "text": "Start Your Free Trial",
                "link": "https://credlocity.scorexer.com/portal-signUp/signup.jsp?id=a2dLYWJBMVhuOWRoMlB2cyt5MFVtUT09",
                "style": {
                    "backgroundColor": "#59a52c",
                    "color": "#ffffff",
                    "padding": "16px 48px",
                    "fontSize": "18px",
                    "fontWeight": "600",
                    "borderRadius": "8px",
                    "marginBottom": "60px",
                    "textAlign": "center"
                }
            }
        }
    ],
    "settings": {
        "background": "#ffffff",
        "maxWidth": "1200px",
        "margin": "0 auto",
        "padding": "20px"
    }
}

async def seed_home_layout():
    """Seed the home page layout"""
    print("🏠 Seeding Home page layout...")
    
    # Get home page
    home_page = await db.pages.find_one({"slug": "home"})
    if not home_page:
        print("❌ Home page not found. Please run seed_pages.py first.")
        return
    
    page_id = home_page.get("id")
    
    # Check if layout already exists
    existing_layout = await db.page_builder_layouts.find_one({"page_id": page_id})
    
    if existing_layout:
        print("⚠️  Home page layout already exists. Updating...")
        await db.page_builder_layouts.update_one(
            {"page_id": page_id},
            {
                "$set": {
                    "layout_data": HOME_LAYOUT,
                    "updated_at": datetime.now(timezone.utc),
                    "version": existing_layout.get("version", 1) + 1
                }
            }
        )
        print("✅ Home page layout updated!")
    else:
        # Create new layout
        layout = {
            "id": str(uuid.uuid4()),
            "page_id": page_id,
            "layout_data": HOME_LAYOUT,
            "version": 1,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "created_by": home_page.get("created_by")
        }
        await db.page_builder_layouts.insert_one(layout)
        print("✅ Home page layout created!")
    
    print(f"   Components: {len(HOME_LAYOUT['components'])}")
    print(f"   Page ID: {page_id}")

async def main():
    try:
        await seed_home_layout()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(main())
