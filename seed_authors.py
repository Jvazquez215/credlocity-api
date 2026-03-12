"""
Seed script for Author/Team Member profiles
Run with: python seed_authors.py
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import uuid
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def seed_authors():
    """Create sample author profiles"""
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db_name = os.environ.get('DB_NAME', 'test_database')
    db = client[db_name]
    
    print(f"Using database: {db_name}")
    
    # Clear existing authors (optional - comment out to preserve existing)
    await db.authors.delete_many({})
    print("Cleared existing authors")
    
    # Sample authors
    authors = [
        {
            "id": str(uuid.uuid4()),
            "full_name": "Sarah Martinez",
            "slug": "sarah-martinez",
            "email": "sarah.martinez@credlocity.com",
            "title": "Chief Credit Consultant",
            "specialization": "FCRA Compliance & Credit Building",
            "bio": """<p>Sarah Martinez is the Chief Credit Consultant at Credlocity with over 12 years of experience helping thousands of clients rebuild their credit and achieve financial freedom.</p>

<p>After experiencing her own credit challenges early in her career, Sarah became passionate about helping others navigate the complex world of credit repair. She holds certifications in FCRA compliance and has been featured in major financial publications for her expertise.</p>

<h3>Professional Background</h3>
<p>Sarah began her career in consumer finance before transitioning to credit consulting. She has helped over 5,000 clients improve their credit scores, remove inaccurate information, and qualify for better lending terms.</p>

<h3>Approach to Credit Repair</h3>
<p>Sarah believes in empowering clients with education. "Credit repair isn't magic," she often says. "It's understanding your rights under federal law and using proven strategies to challenge inaccurate information."</p>

<p>Her clients appreciate her patient, thorough approach and her commitment to transparency throughout the credit repair process.</p>""",
            "short_bio": "Chief Credit Consultant with 12+ years experience. Helped over 5,000 clients improve their credit scores and achieve financial freedom.",
            "photo_url": "https://randomuser.me/api/portraits/women/44.jpg",
            "photo_alt": "Sarah Martinez, Chief Credit Consultant",
            "credentials": [
                "Certified Credit Consultant (CCC)",
                "FCRA Compliance Specialist",
                "12+ Years Experience",
                "Featured in Financial Times",
                "5,000+ Clients Helped"
            ],
            "years_experience": 12,
            "social_links": {
                "linkedin": "https://linkedin.com/in/sarahmartinez",
                "twitter": "https://twitter.com/sarahmartinez",
                "facebook": "https://facebook.com/sarahmartinez"
            },
            "phone": "(555) 123-4567",
            "office_location": "Philadelphia Office",
            "display_order": 1,
            "featured": True,
            "show_on_team_page": True,
            "seo_meta_title": "Sarah Martinez - Chief Credit Consultant | Credlocity",
            "seo_meta_description": "Meet Sarah Martinez, Credlocity's Chief Credit Consultant with 12+ years experience in credit repair and FCRA compliance. Over 5,000 clients helped.",
            "seo_keywords": "sarah martinez, credit consultant, fcra compliance, credit repair expert",
            "status": "active",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "id": str(uuid.uuid4()),
            "full_name": "Michael Chen",
            "slug": "michael-chen",
            "email": "michael.chen@credlocity.com",
            "title": "Senior Credit Analyst",
            "specialization": "Credit Score Optimization & Dispute Resolution",
            "bio": """<p>Michael Chen is a Senior Credit Analyst at Credlocity, specializing in credit score optimization strategies and dispute resolution. With a background in data analytics and consumer finance, Michael brings a unique analytical approach to credit repair.</p>

<h3>Expertise</h3>
<p>Michael's expertise lies in analyzing credit reports to identify errors and develop customized action plans for each client. His systematic approach has helped hundreds of clients see significant improvements in their credit scores within 60-90 days.</p>

<h3>Educational Background</h3>
<p>Michael holds a degree in Business Administration with a focus on Financial Analytics. He regularly conducts workshops on credit literacy and financial planning.</p>

<h3>Philosophy</h3>
<p>"Every credit report tells a story," Michael explains. "My job is to help clients rewrite their story by addressing inaccuracies and implementing smart credit-building strategies."</p>

<p>Outside of work, Michael volunteers with local nonprofits providing free credit counseling to underserved communities.</p>""",
            "short_bio": "Senior Credit Analyst specializing in score optimization and dispute resolution. Data-driven approach with proven results in 60-90 days.",
            "photo_url": "https://randomuser.me/api/portraits/men/32.jpg",
            "photo_alt": "Michael Chen, Senior Credit Analyst",
            "credentials": [
                "Business Administration Degree",
                "Credit Score Optimization Specialist",
                "8+ Years Experience",
                "Dispute Resolution Expert",
                "Workshop Facilitator"
            ],
            "years_experience": 8,
            "social_links": {
                "linkedin": "https://linkedin.com/in/michaelchen",
                "twitter": "https://twitter.com/michaelchen"
            },
            "phone": "(555) 234-5678",
            "office_location": "Remote",
            "display_order": 2,
            "featured": True,
            "show_on_team_page": True,
            "seo_meta_title": "Michael Chen - Senior Credit Analyst | Credlocity",
            "seo_meta_description": "Michael Chen is a Senior Credit Analyst at Credlocity with expertise in credit score optimization and dispute resolution. 8+ years helping clients improve credit.",
            "seo_keywords": "michael chen, credit analyst, credit score optimization, dispute resolution",
            "status": "active",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "id": str(uuid.uuid4()),
            "full_name": "Jennifer Thompson",
            "slug": "jennifer-thompson",
            "email": "jennifer.thompson@credlocity.com",
            "title": "Mortgage Credit Specialist",
            "specialization": "Mortgage Preparation & First-Time Homebuyers",
            "bio": """<p>Jennifer Thompson specializes in helping clients prepare their credit for mortgage applications. With 10 years of experience in both mortgage lending and credit consulting, she understands exactly what lenders look for and how to position clients for approval.</p>

<h3>Mortgage Expertise</h3>
<p>Jennifer has helped over 300 clients qualify for mortgages by strategically improving their credit profiles. She understands the nuances of credit scoring models used by mortgage lenders and knows how to optimize scores for home loan approval.</p>

<h3>First-Time Homebuyer Focus</h3>
<p>Jennifer is passionate about helping first-time homebuyers achieve their dream of homeownership. She provides comprehensive guidance on credit preparation, score improvement timelines, and what to expect during the mortgage approval process.</p>

<h3>Previous Experience</h3>
<p>Before joining Credlocity, Jennifer worked as a mortgage underwriter for 5 years, giving her insider knowledge of the lending process.</p>

<p>"Homeownership shouldn't be out of reach," Jennifer believes. "With the right credit preparation and guidance, many more people can qualify for mortgages than they realize."</p>""",
            "short_bio": "Mortgage Credit Specialist with 10 years experience. Helped 300+ clients qualify for mortgages through strategic credit optimization.",
            "photo_url": "https://randomuser.me/api/portraits/women/65.jpg",
            "photo_alt": "Jennifer Thompson, Mortgage Credit Specialist",
            "credentials": [
                "Former Mortgage Underwriter",
                "Mortgage Credit Specialist Certification",
                "10+ Years Experience",
                "First-Time Homebuyer Expert",
                "300+ Mortgage Approvals Assisted"
            ],
            "years_experience": 10,
            "social_links": {
                "linkedin": "https://linkedin.com/in/jenniferthompson",
                "facebook": "https://facebook.com/jenniferthompson",
                "instagram": "https://instagram.com/jenniferthompson"
            },
            "phone": "(555) 345-6789",
            "office_location": "Philadelphia Office",
            "display_order": 3,
            "featured": False,
            "show_on_team_page": True,
            "seo_meta_title": "Jennifer Thompson - Mortgage Credit Specialist | Credlocity",
            "seo_meta_description": "Jennifer Thompson specializes in mortgage credit preparation at Credlocity. 10+ years experience helping first-time homebuyers qualify for mortgages.",
            "seo_keywords": "jennifer thompson, mortgage credit specialist, first-time homebuyer, mortgage preparation",
            "status": "active",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "id": str(uuid.uuid4()),
            "full_name": "David Rodriguez",
            "slug": "david-rodriguez",
            "email": "david.rodriguez@credlocity.com",
            "title": "CEO & Founder",
            "specialization": "Credit Repair Strategy & Business Credit",
            "bio": """<p>David Rodriguez is the founder and CEO of Credlocity. After experiencing his own credit challenges following a business failure in 2010, David learned the intricacies of credit repair firsthand and discovered his passion for helping others.</p>

<h3>Founding Credlocity</h3>
<p>In 2013, David founded Credlocity with a mission to provide transparent, effective credit repair services. What started as a small operation helping local clients has grown into one of the most trusted names in credit restoration.</p>

<h3>Expertise</h3>
<p>David specializes in both personal and business credit repair. His unique perspective as both a business owner and credit expert allows him to provide comprehensive solutions for entrepreneurs and business owners.</p>

<h3>Industry Recognition</h3>
<p>David has been featured in numerous financial publications and frequently speaks at industry conferences about consumer credit rights and best practices in credit repair.</p>

<h3>Vision</h3>
<p>"At Credlocity, we believe everyone deserves a second chance," David states. "Financial mistakes shouldn't define your future. With the right knowledge and support, anyone can rebuild their credit and achieve their financial goals."</p>""",
            "short_bio": "CEO & Founder of Credlocity. Pioneering transparent credit repair since 2013. Expert in personal and business credit restoration.",
            "photo_url": "https://randomuser.me/api/portraits/men/75.jpg",
            "photo_alt": "David Rodriguez, CEO & Founder",
            "credentials": [
                "Credlocity Founder & CEO",
                "15+ Years Credit Industry Experience",
                "Business Credit Expert",
                "Industry Speaker",
                "Featured in Major Financial Publications"
            ],
            "years_experience": 15,
            "social_links": {
                "linkedin": "https://linkedin.com/in/davidrodriguez",
                "twitter": "https://twitter.com/davidrodriguez",
                "facebook": "https://facebook.com/davidrodriguez",
                "instagram": "https://instagram.com/davidrodriguez"
            },
            "phone": "(555) 456-7890",
            "office_location": "Philadelphia HQ",
            "display_order": 0,
            "featured": True,
            "show_on_team_page": True,
            "seo_meta_title": "David Rodriguez - CEO & Founder | Credlocity",
            "seo_meta_description": "Meet David Rodriguez, founder and CEO of Credlocity. 15+ years experience in credit repair and business credit restoration. Industry leader and speaker.",
            "seo_keywords": "david rodriguez, credlocity ceo, credit repair founder, business credit expert",
            "status": "active",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    ]
    
    # Insert authors
    result = await db.authors.insert_many(authors)
    print(f"✅ Created {len(result.inserted_ids)} authors:")
    
    for author in authors:
        print(f"   - {author['full_name']} ({author['title']})")
    
    # Close connection
    client.close()
    print("\n✅ Author seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_authors())
