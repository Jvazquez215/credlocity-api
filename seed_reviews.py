import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = get_client(mongo_url)
db = client[os.environ['DB_NAME']]

sample_reviews = [
    {
        "id": "review-001",
        "client_name": "Sarah Johnson",
        "testimonial_text": "Credlocity removed 3 collections and 5 late payments in just 45 days! My score went from 580 to 720.",
        "full_story": "I was denied for a mortgage because of old collections. Credlocity's team worked aggressively and got them removed. Now I'm a homeowner!",
        "detailed_narrative": """<h2>My Journey from 580 to 720</h2>
<p>When I first contacted Credlocity, I was devastated. My husband and I had been saving for years to buy our first home, but every mortgage lender turned us down because of my credit score.</p>

<h3>The Problem</h3>
<p>I had three old collection accounts from medical bills and five late payments on my credit cards from 2019 when I lost my job. Despite paying everything off, these negative items were still dragging down my score.</p>

<h3>Working with Credlocity</h3>
<p>From day one, my credit specialist at Credlocity was incredible. She explained exactly what was hurting my score and created a custom game plan. Within 45 days, they had:</p>
<ul>
<li>Removed all 3 collection accounts</li>
<li>Deleted 4 of the 5 late payments</li>
<li>Increased my score by 140 points</li>
</ul>

<h3>The Result</h3>
<p>We closed on our dream home in Los Angeles last month. I still can't believe it! Thank you Credlocity for making our dream come true.</p>""",
        "story_title": "From 580 to 720: How Sarah Became a Homeowner",
        "story_slug": "sarah-johnson-homeowner-journey",
        "gallery_photos": [
            "https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=600&h=400&fit=crop",
            "https://images.unsplash.com/photo-1582407947304-fd86f028f716?w=600&h=400&fit=crop",
            "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=600&h=400&fit=crop"
        ],
        "video_url": "",
        "before_score": 580,
        "after_score": 720,
        "points_improved": 140,
        "client_photo_url": "https://i.pravatar.cc/150?img=5",
        "featured_on_homepage": True,
        "show_on_success_stories": True,
        "competitor_switched_from": "Lexington Law",
        "seo_meta_title": "Sarah's Credit Repair Success: 580 to 720 in 45 Days | Credlocity",
        "seo_meta_description": "Discover how Sarah improved her credit score from 580 to 720 in just 45 days with Credlocity, removed 3 collections, and became a homeowner in Los Angeles.",
        "seo_keywords": "credit repair success story, improve credit score 140 points, remove collections, first time homeowner, Credlocity reviews",
        "client_social_links": {
            "facebook": "https://facebook.com/sarahjohnson",
            "instagram": "https://instagram.com/sarah_home_journey",
            "twitter": "",
            "bluesky": "",
            "threads": "",
            "linkedin": "https://linkedin.com/in/sarahjohnson"
        },
        "category": "collections",
        "display_order": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    },
    {
        "id": "review-002",
        "client_name": "Michael Chen",
        "testimonial_text": "Best decision I made! Professional, responsive, and they actually delivered results. 100+ point increase in 60 days.",
        "full_story": "After trying DIY credit repair for months with no results, I hired Credlocity. They knew exactly what to do and my score jumped from 625 to 735.",
        "detailed_narrative": """<h2>From DIY Failure to Credit Success</h2>
<p>I spent six months trying to repair my credit myself. I downloaded all the templates, sent dispute letters, and followed YouTube tutorials. My score? It actually went DOWN 10 points.</p>

<h3>Why I Needed Help</h3>
<p>I was trying to get approved for a business loan to expand my restaurant. The banks kept rejecting me because of some late payments and a charge-off from 2020. I needed professional help.</p>

<h3>The Credlocity Difference</h3>
<p>What impressed me most was their knowledge of FCRA laws. They didn't just send generic dispute letters - they analyzed my credit report like detectives and found legal violations I never would have caught. In 60 days:</p>
<ul>
<li>Removed the charge-off account</li>
<li>Deleted 6 late payment marks</li>
<li>Corrected reporting errors on 2 accounts</li>
<li>Increased my score by 110 points</li>
</ul>

<h3>The Impact</h3>
<p>I got approved for my business loan last week. The expansion is happening! Credlocity didn't just fix my credit - they helped grow my business.</p>""",
        "story_title": "How Michael Chen Grew His Business with Better Credit",
        "story_slug": "michael-chen-business-success",
        "gallery_photos": [
            "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=600&h=400&fit=crop",
            "https://images.unsplash.com/photo-1559329007-40df8a9345d8?w=600&h=400&fit=crop"
        ],
        "video_url": "",
        "before_score": 625,
        "after_score": 735,
        "points_improved": 110,
        "client_photo_url": "https://i.pravatar.cc/150?img=12",
        "featured_on_homepage": True,
        "show_on_success_stories": True,
        "competitor_switched_from": "",
        "seo_meta_title": "Michael Chen's Business Credit Success Story | 625 to 735 | Credlocity",
        "seo_meta_description": "After DIY credit repair failed, Michael Chen hired Credlocity. Learn how he increased his score 110 points in 60 days and got approved for his business loan.",
        "seo_keywords": "business credit repair, entrepreneur credit help, DIY credit repair failure, 110 point increase, business loan approval",
        "client_social_links": {
            "facebook": "",
            "instagram": "https://instagram.com/mikechenbiz",
            "twitter": "https://x.com/mikechenbiz",
            "bluesky": "",
            "threads": "",
            "linkedin": "https://linkedin.com/in/michaelchen"
        },
        "category": "general",
        "display_order": 2,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    },
    {
        "id": "review-003",
        "client_name": "Jennifer Martinez",
        "testimonial_text": "Identity theft destroyed my credit. Credlocity used the 605B block and removed everything. My score went from 520 to 780!",
        "full_story": "I was a victim of identity theft with fraudulent accounts everywhere. Credlocity's expertise with FCRA 605B blocks saved me. I can't thank them enough.",
        "detailed_narrative": """<h2>Recovering from Identity Theft</h2>
<p>Discovering identity theft was terrifying. I checked my credit report and found 8 accounts I never opened - credit cards maxed out, loans in default, my score destroyed at 520.</p>

<h3>The Nightmare Begins</h3>
<p>I filed police reports, contacted the credit bureaus, and disputed everything. Months passed and nothing changed. The fraudulent accounts were still there, ruining my credit and my life.</p>

<h3>Credlocity's FCRA 605B Strategy</h3>
<p>My Credlocity specialist explained something called a "605B block" - a federal protection for identity theft victims. Most credit repair companies don't know how to use it properly. Credlocity does. Within 90 days:</p>
<ul>
<li>Blocked all 8 fraudulent accounts using FCRA 605B</li>
<li>Removed negative marks from affected credit reports</li>
<li>Restored my identity theft victim status</li>
<li>Increased my score by an incredible 260 points</li>
</ul>

<h3>Starting Fresh</h3>
<p>My score is now 780. I'm rebuilding my financial life with confidence. Credlocity gave me back my identity and my future.</p>""",
        "story_title": "Jennifer's 260-Point Credit Recovery After Identity Theft",
        "story_slug": "jennifer-martinez-identity-theft-recovery",
        "gallery_photos": [
            "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=600&h=400&fit=crop",
            "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=600&h=400&fit=crop",
            "https://images.unsplash.com/photo-1434626881859-194d67b2b86f?w=600&h=400&fit=crop"
        ],
        "video_url": "",
        "before_score": 520,
        "after_score": 780,
        "points_improved": 260,
        "client_photo_url": "https://i.pravatar.cc/150?img=9",
        "featured_on_homepage": True,
        "show_on_success_stories": True,
        "competitor_switched_from": "Credit Saint",
        "seo_meta_title": "Identity Theft Credit Recovery: 260-Point Increase | Jennifer Martinez",
        "seo_meta_description": "Jennifer's identity theft nightmare became a success story with Credlocity's FCRA 605B block strategy. See how she went from 520 to 780 credit score.",
        "seo_keywords": "identity theft credit repair, FCRA 605B block, remove fraudulent accounts, 260 point increase, credit restoration",
        "client_social_links": {
            "facebook": "https://facebook.com/jennifermartinez",
            "instagram": "",
            "twitter": "",
            "bluesky": "https://bsky.app/profile/jennifermartinez",
            "threads": "https://threads.net/@jennifermartinez",
            "linkedin": ""
        },
        "category": "identity_theft",
        "display_order": 3,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
]

async def seed_reviews():
    # Delete existing reviews to update with new fields
    await db.reviews.delete_many({})
    print("Cleared existing reviews")
    
    # Convert datetime to ISO format for MongoDB
    for review in sample_reviews:
        review['created_at'] = review['created_at'].isoformat()
        review['updated_at'] = review['updated_at'].isoformat()
    
    result = await db.reviews.insert_many(sample_reviews)
    print(f"✅ Successfully seeded {len(result.inserted_ids)} sample reviews with full story details")
    
    reviews = await db.reviews.find({}, {"_id": 0}).to_list(100)
    print("\n📄 Seeded reviews:")
    for review in reviews:
        print(f"  - {review['client_name']}: {review['before_score']} → {review['after_score']} (+{review['points_improved']} points)")
        print(f"    Story URL: /success-stories/{review['story_slug']}")

if __name__ == "__main__":
    asyncio.run(seed_reviews())
