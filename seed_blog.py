"""
Seed script for Blog Posts, Categories, and Tags
Creates sample content for testing the blog management system
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from db_client import get_client
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'credlocity_cms')
client = get_client(MONGO_URL)
db = client[DB_NAME]


async def clear_existing_blog_data():
    """Clear existing blog posts, categories, and tags"""
    await db.blog_posts.delete_many({})
    await db.categories.delete_many({})
    await db.tags.delete_many({})
    print("✅ Cleared existing blog data")


async def seed_categories():
    """Create sample categories"""
    categories = [
        {
            "id": str(uuid.uuid4()),
            "name": "Credit Repair",
            "slug": "credit-repair",
            "description": "Tips and guides for repairing your credit score",
            "seo_title": "Credit Repair Tips & Guides | Credlocity",
            "seo_description": "Expert advice on credit repair strategies, dispute letters, and improving your credit score.",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Credit Scores",
            "slug": "credit-scores",
            "description": "Understanding credit scores and how they work",
            "seo_title": "Understanding Credit Scores | Credlocity",
            "seo_description": "Learn about FICO scores, credit bureaus, and factors that impact your credit rating.",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Credit Education",
            "slug": "credit-education",
            "description": "Educational content about credit and personal finance",
            "seo_title": "Credit Education Resources | Credlocity",
            "seo_description": "Free educational resources to help you understand credit reports, scores, and financial health.",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    await db.categories.insert_many(categories)
    print(f"✅ Created {len(categories)} categories")
    return categories


async def seed_tags():
    """Create sample tags"""
    tags = [
        {
            "id": str(uuid.uuid4()),
            "name": "FICO Score",
            "slug": "fico-score",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Credit Report",
            "slug": "credit-report",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Dispute Letter",
            "slug": "dispute-letter",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Beginners Guide",
            "slug": "beginners-guide",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Tips & Tricks",
            "slug": "tips-tricks",
            "post_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    await db.tags.insert_many(tags)
    print(f"✅ Created {len(tags)} tags")
    return tags


async def seed_blog_posts(categories, tags):
    """Create sample blog posts"""
    
    # Get category IDs
    credit_repair_cat = next((c for c in categories if c["slug"] == "credit-repair"), None)
    credit_scores_cat = next((c for c in categories if c["slug"] == "credit-scores"), None)
    credit_edu_cat = next((c for c in categories if c["slug"] == "credit-education"), None)
    
    posts = [
        {
            "id": str(uuid.uuid4()),
            "title": "How to Improve Your Credit Score Fast: 7 Proven Strategies",
            "slug": "how-to-improve-credit-score-fast",
            "content": """
                <h2>Why Your Credit Score Matters</h2>
                <p>Your credit score is more than just a number—it's the key to your financial future. A higher credit score can save you thousands of dollars in interest rates, qualify you for better loans, and even impact job opportunities.</p>
                
                <h2>7 Proven Strategies to Boost Your Credit Score</h2>
                
                <h3>1. Pay Your Bills On Time, Every Time</h3>
                <p>Payment history accounts for 35% of your FICO score. Set up automatic payments or reminders to ensure you never miss a due date. Even one late payment can drop your score by 50-100 points.</p>
                
                <h3>2. Dispute Inaccurate Information</h3>
                <p>Studies show that 79% of credit reports contain errors. Review your reports from all three bureaus (Equifax, Experian, TransUnion) and dispute any inaccuracies. Credlocity can help you craft effective dispute letters.</p>
                
                <h3>3. Reduce Your Credit Utilization Ratio</h3>
                <p>Keep your credit card balances below 30% of your credit limits. Ideally, aim for under 10% for the best results. This factor accounts for 30% of your credit score.</p>
                
                <h3>4. Don't Close Old Credit Accounts</h3>
                <p>The length of your credit history matters. Keep your oldest accounts open and active, even if you don't use them often. Closing accounts shortens your average account age.</p>
                
                <h3>5. Diversify Your Credit Mix</h3>
                <p>Having a mix of credit types (credit cards, auto loans, mortgages) can positively impact your score. However, don't open new accounts just for this reason—only if you need them.</p>
                
                <h3>6. Become an Authorized User</h3>
                <p>Ask a family member with excellent credit to add you as an authorized user on their account. Their positive payment history will be added to your credit report.</p>
                
                <h3>7. Use Credit Repair Services</h3>
                <p>Professional credit repair services like Credlocity can identify and dispute errors, negotiate with creditors, and create a personalized plan to improve your score faster than doing it alone.</p>
                
                <h2>Timeline: When Will You See Results?</h2>
                <ul>
                    <li><strong>30 days:</strong> Dispute resolutions begin to show</li>
                    <li><strong>60-90 days:</strong> Payment history improvements reflect</li>
                    <li><strong>6 months:</strong> Significant score increases with consistent effort</li>
                </ul>
                
                <h2>Get Expert Help</h2>
                <p>At Credlocity, we've helped thousands of clients improve their credit scores by an average of 120 points. Our team of credit experts will create a custom plan tailored to your situation.</p>
                
                <p><strong>Ready to take control of your credit?</strong> Start your free consultation today!</p>
            """,
            "excerpt": "Discover 7 proven strategies to boost your credit score quickly. From disputing errors to optimizing credit utilization, learn expert tips that can increase your score by 100+ points.",
            "categories": [credit_repair_cat["id"], credit_scores_cat["id"]],
            "tags": ["fico-score", "tips-tricks", "beginners-guide"],
            "author_name": "Credlocity Expert Team",
            "author_id": None,
            "featured_image_url": "https://images.unsplash.com/photo-1554224311-beee415c201f?w=1200",
            "featured_image_alt": "Person checking credit score on laptop",
            "seo": {
                "meta_title": "How to Improve Credit Score Fast: 7 Proven Strategies (2025)",
                "meta_description": "Boost your credit score quickly with these 7 expert-approved strategies. Learn how to dispute errors, reduce utilization, and improve payment history.",
                "keywords": "improve credit score, boost credit score, credit repair tips, FICO score, credit utilization",
                "canonical_url": "",
                "robots": "index, follow",
                "schema_type": "HowTo",
                "og_title": "7 Proven Ways to Improve Your Credit Score Fast",
                "og_description": "Want a higher credit score? Follow these 7 expert strategies that actually work.",
                "og_image": "https://images.unsplash.com/photo-1554224311-beee415c201f?w=1200"
            },
            "status": "published",
            "publish_date": datetime.now(timezone.utc).isoformat(),
            "featured_post": True,
            "allow_comments": True,
            "related_posts": [],
            "view_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "last_edited_by": "system"
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Understanding Your Credit Report: A Complete Guide",
            "slug": "understanding-credit-report-guide",
            "content": """
                <h2>What Is a Credit Report?</h2>
                <p>Your credit report is a detailed record of your credit history, compiled by three major credit bureaus: Equifax, Experian, and TransUnion. Lenders, landlords, and even employers use this report to evaluate your financial responsibility.</p>
                
                <h2>Key Components of Your Credit Report</h2>
                
                <h3>1. Personal Information</h3>
                <p>This section includes your name, addresses, Social Security number, date of birth, and employment history. While it doesn't affect your score, errors here can lead to identity theft or mixed files.</p>
                
                <h3>2. Credit Accounts (Trade Lines)</h3>
                <p>All your credit accounts are listed here, including:</p>
                <ul>
                    <li>Credit cards</li>
                    <li>Auto loans</li>
                    <li>Mortgages</li>
                    <li>Student loans</li>
                    <li>Personal loans</li>
                </ul>
                <p>Each account shows the creditor name, account type, date opened, credit limit or loan amount, balance, and payment history.</p>
                
                <h3>3. Credit Inquiries</h3>
                <p><strong>Hard inquiries:</strong> Occur when you apply for credit. Too many in a short period can lower your score.</p>
                <p><strong>Soft inquiries:</strong> Include background checks and pre-approved offers. These don't affect your score.</p>
                
                <h3>4. Public Records</h3>
                <p>This section lists bankruptcies, tax liens, and civil judgments. These are the most damaging items on your report.</p>
                
                <h3>5. Collections</h3>
                <p>Accounts sent to collections agencies for unpaid debts. These can stay on your report for 7 years and severely impact your score.</p>
                
                <h2>How to Read Your Credit Report</h2>
                <p>Look for these red flags:</p>
                <ul>
                    <li>❌ Accounts you don't recognize</li>
                    <li>❌ Late payments you didn't make</li>
                    <li>❌ Incorrect balances or credit limits</li>
                    <li>❌ Duplicate accounts</li>
                    <li>❌ Closed accounts listed as open</li>
                </ul>
                
                <h2>Your Rights Under Federal Law</h2>
                <p>The Fair Credit Reporting Act (FCRA) gives you the right to:</p>
                <ul>
                    <li>One free credit report per year from each bureau</li>
                    <li>Dispute inaccurate information</li>
                    <li>Know who accessed your report</li>
                    <li>Have negative items removed after 7-10 years</li>
                </ul>
                
                <h2>Common Credit Report Errors</h2>
                <p>79% of credit reports contain at least one error. Common mistakes include:</p>
                <ul>
                    <li>Mixed files (your information mixed with someone else's)</li>
                    <li>Incorrect payment statuses</li>
                    <li>Fraudulent accounts from identity theft</li>
                    <li>Outdated negative items</li>
                </ul>
                
                <h2>How Credlocity Can Help</h2>
                <p>Our credit experts will:</p>
                <ul>
                    <li>Thoroughly analyze your credit reports from all three bureaus</li>
                    <li>Identify errors, inaccuracies, and questionable items</li>
                    <li>File disputes on your behalf</li>
                    <li>Follow up with creditors and bureaus</li>
                    <li>Track your progress monthly</li>
                </ul>
                
                <p><strong>Get your free credit report review today</strong> and discover what's holding your score back.</p>
            """,
            "excerpt": "Learn how to read and understand your credit report. Discover what lenders see, how to spot errors, and why 79% of reports contain mistakes that could be hurting your score.",
            "categories": [credit_edu_cat["id"], credit_scores_cat["id"]],
            "tags": ["credit-report", "beginners-guide"],
            "author_name": "Credlocity Expert Team",
            "author_id": None,
            "featured_image_url": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=1200",
            "featured_image_alt": "Person reviewing credit report documents",
            "seo": {
                "meta_title": "Understanding Your Credit Report: Complete Guide (2025)",
                "meta_description": "Learn how to read your credit report, spot errors, and understand what affects your credit score. Free guide from credit repair experts.",
                "keywords": "credit report, credit history, FICO score, credit bureaus, Equifax, Experian, TransUnion",
                "canonical_url": "",
                "robots": "index, follow",
                "schema_type": "Article",
                "og_title": "Complete Guide to Understanding Your Credit Report",
                "og_description": "79% of credit reports have errors. Learn how to read yours and spot mistakes.",
                "og_image": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=1200"
            },
            "status": "published",
            "publish_date": datetime.now(timezone.utc).isoformat(),
            "featured_post": True,
            "allow_comments": True,
            "related_posts": [],
            "view_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "last_edited_by": "system"
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Credit Repair Myths Debunked: What Really Works",
            "slug": "credit-repair-myths-debunked",
            "content": """
                <h2>Separating Fact from Fiction</h2>
                <p>The internet is full of credit repair advice, but not all of it is accurate. Let's debunk the most common myths and reveal what actually works.</p>
                
                <h2>Myth #1: "You Can't Remove Accurate Negative Items"</h2>
                <p><strong>TRUTH:</strong> While legitimate negative items can stay on your report, you CAN dispute them if they're inaccurate, unverifiable, or incomplete. Credit bureaus must investigate and remove items they can't verify within 30 days.</p>
                
                <h2>Myth #2: "Checking Your Credit Hurts Your Score"</h2>
                <p><strong>TRUTH:</strong> Checking your own credit is a "soft inquiry" and does NOT affect your score. You can check as often as you want without any negative impact.</p>
                
                <h2>Myth #3: "Closing Credit Cards Improves Your Score"</h2>
                <p><strong>TRUTH:</strong> Closing cards can actually HURT your score by reducing your available credit and increasing your utilization ratio. Keep old accounts open.</p>
                
                <h2>Myth #4: "You Need to Carry a Balance to Build Credit"</h2>
                <p><strong>TRUTH:</strong> This is completely false. Paying off your balance in full each month is the best way to build credit while avoiding interest charges.</p>
                
                <h2>Myth #5: "Credit Repair Companies Can't Do Anything You Can't Do Yourself"</h2>
                <p><strong>TRUTH:</strong> While you can dispute errors yourself, professional credit repair companies have:</p>
                <ul>
                    <li>Expertise in identifying disputable items</li>
                    <li>Relationships with creditors and bureaus</li>
                    <li>Knowledge of consumer protection laws</li>
                    <li>Time to follow up on disputes</li>
                    <li>Proven strategies that work</li>
                </ul>
                
                <h2>Myth #6: "Bankruptcy Ruins Your Credit Forever"</h2>
                <p><strong>TRUTH:</strong> Bankruptcy is serious, but it's not permanent. Chapter 7 stays on your report for 10 years, Chapter 13 for 7 years. You can start rebuilding immediately and see significant improvement within 2 years.</p>
                
                <h2>Myth #7: "Paying Off Collections Removes Them"</h2>
                <p><strong>TRUTH:</strong> Paying a collection account changes its status to "paid," but it doesn't remove it from your report. Negotiate "pay for delete" agreements before paying.</p>
                
                <h2>Myth #8: "Credit Repair Is a Scam"</h2>
                <p><strong>TRUTH:</strong> While there are some dishonest companies, legitimate credit repair services like Credlocity operate within federal law (Credit Repair Organizations Act) and provide valuable services with proven results.</p>
                
                <h2>What Really Works for Credit Repair</h2>
                <ol>
                    <li><strong>Dispute inaccurate information</strong> with all three bureaus</li>
                    <li><strong>Negotiate with creditors</strong> for goodwill deletions</li>
                    <li><strong>Set up payment plans</strong> for outstanding debts</li>
                    <li><strong>Add positive credit</strong> with secured cards or credit builder loans</li>
                    <li><strong>Monitor your progress</strong> regularly</li>
                </ol>
                
                <h2>The Credlocity Difference</h2>
                <p>Our proven process has helped over 10,000 clients improve their credit scores by an average of 120 points. We:</p>
                <ul>
                    <li>Analyze all three credit reports</li>
                    <li>Identify disputable items</li>
                    <li>File disputes on your behalf</li>
                    <li>Negotiate with creditors</li>
                    <li>Provide ongoing education and support</li>
                </ul>
                
                <p><strong>Stop believing myths and start seeing results.</strong> Get your free credit consultation today!</p>
            """,
            "excerpt": "Don't fall for credit repair myths! Discover what really works and what's just internet folklore. Learn the truth about credit scores, disputes, and professional repair services.",
            "categories": [credit_repair_cat["id"], credit_edu_cat["id"]],
            "tags": ["credit-repair", "dispute-letter"],
            "author_name": "Credlocity Expert Team",
            "author_id": None,
            "featured_image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200",
            "featured_image_alt": "Person confused about credit myths",
            "seo": {
                "meta_title": "Credit Repair Myths Debunked: What Really Works in 2025",
                "meta_description": "Separate credit repair facts from fiction. Learn what really works to improve your credit score and avoid common myths that could be costing you.",
                "keywords": "credit repair myths, credit score myths, credit repair facts, dispute credit errors",
                "canonical_url": "",
                "robots": "index, follow",
                "schema_type": "Article",
                "og_title": "8 Credit Repair Myths Debunked by Experts",
                "og_description": "Stop believing credit myths. Learn what really works from professional credit repair experts.",
                "og_image": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200"
            },
            "status": "published",
            "publish_date": datetime.now(timezone.utc).isoformat(),
            "featured_post": False,
            "allow_comments": True,
            "related_posts": [],
            "view_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "last_edited_by": "system"
        }
    ]
    
    await db.blog_posts.insert_many(posts)
    print(f"✅ Created {len(posts)} blog posts")
    
    # Update category post counts
    await db.categories.update_one(
        {"id": credit_repair_cat["id"]},
        {"$set": {"post_count": 2}}
    )
    await db.categories.update_one(
        {"id": credit_scores_cat["id"]},
        {"$set": {"post_count": 2}}
    )
    await db.categories.update_one(
        {"id": credit_edu_cat["id"]},
        {"$set": {"post_count": 2}}
    )
    
    print("✅ Updated category post counts")
    
    return posts


async def main():
    """Main seeding function"""
    print("🌱 Starting blog seeding process...")
    
    try:
        # Clear existing data
        await clear_existing_blog_data()
        
        # Seed categories
        categories = await seed_categories()
        
        # Seed tags
        tags = await seed_tags()
        
        # Seed blog posts
        posts = await seed_blog_posts(categories, tags)
        
        print("\n✅ Blog seeding completed successfully!")
        print(f"   📁 {len(categories)} categories")
        print(f"   🏷️  {len(tags)} tags")
        print(f"   📝 {len(posts)} blog posts")
        
    except Exception as e:
        print(f"❌ Error during seeding: {str(e)}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
