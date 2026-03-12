"""
Comprehensive FAQ Seed Script with Researched Content
Phase 3C - Based on web research and credit industry best practices
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

async def seed_comprehensive_faqs():
    client = AsyncIOMotorClient(os.getenv('MONGO_URL'))
    db = client.test_database
    
    print("🌱 Seeding comprehensive FAQ content...")
    
    # Clear existing
    await db.faqs.delete_many({})
    await db.faq_categories.delete_many({})
    print("✓ Cleared existing data")
    
    # Get Joey
    joey = await db.authors.find_one({"email": "joey@credlocity.com"})
    author_id = joey["id"] if joey else str(uuid.uuid4())
    author_name = joey["full_name"] if joey else "Joeziel Joey Vazquez-Davila"
    author_creds = joey.get("credentials", ["BCCC", "CCSC", "CCRS", "FCRA Certified"]) if joey else ["BCCC"]
    
    # Categories with proper emojis
    categories = [
        {"id": str(uuid.uuid4()), "name": "Credlocity FAQs", "slug": "credlocity-faqs", "icon": "🏢", "description": "Learn about Credlocity's services, pricing, and policies", "order": 1},
        {"id": str(uuid.uuid4()), "name": "Credit Repair FAQs", "slug": "credit-repair-faqs", "icon": "🔧", "description": "Understanding the credit repair process", "order": 2},
        {"id": str(uuid.uuid4()), "name": "Credit Scores FAQs", "slug": "credit-scores-faqs", "icon": "📊", "description": "Everything about credit scores", "order": 3},
        {"id": str(uuid.uuid4()), "name": "Credit Report FAQs", "slug": "credit-report-faqs", "icon": "📋", "description": "Understanding your credit report", "order": 4},
        {"id": str(uuid.uuid4()), "name": "FICO Score FAQs", "slug": "fico-score-faqs", "icon": "🎯", "description": "FICO scoring models explained", "order": 5},
        {"id": str(uuid.uuid4()), "name": "VantageScore FAQs", "slug": "vantagescore-faqs", "icon": "📈", "description": "VantageScore models", "order": 6},
        {"id": str(uuid.uuid4()), "name": "Experian FAQs", "slug": "experian-faqs", "icon": "🏛️", "description": "Experian credit bureau", "order": 7},
        {"id": str(uuid.uuid4()), "name": "Equifax FAQs", "slug": "equifax-faqs", "icon": "🏦", "description": "Equifax credit bureau", "order": 8},
        {"id": str(uuid.uuid4()), "name": "TransUnion FAQs", "slug": "transunion-faqs", "icon": "🏪", "description": "TransUnion credit bureau", "order": 9},
        {"id": str(uuid.uuid4()), "name": "Annual Credit Report FAQs", "slug": "annual-credit-report-faqs", "icon": "📅", "description": "Free annual credit reports", "order": 10}
    ]
    
    for cat in categories:
        cat["faq_count"] = 0
        cat["created_at"] = datetime.now(timezone.utc)
    
    await db.faq_categories.insert_many(categories)
    print(f"✓ Created {len(categories)} categories")
    
    # NOW CREATE COMPREHENSIVE FAQ CONTENT
    faqs = []
    
    # Helper to create FAQ
    def make_faq(question, answer, cat_name, cat_slug, order_num):
        return {
            "id": str(uuid.uuid4()),
            "question": question,
            "answer": answer,
            "category": cat_name,
            "category_slug": cat_slug,
            "slug": question.lower().replace("?", "").replace(" ", "-")[:60],
            "order": order_num,
            "seo_meta_title": f"{question[:50]} | Credlocity FAQ",
            "seo_meta_description": answer[:150].replace("<p>", "").replace("</p>", "").replace("<strong>", "").replace("</strong>", "")[:160],
            "keywords": [],
            "author_id": author_id,
            "author_name": author_name,
            "author_credentials": author_creds,
            "related_blog_posts": [],
            "related_faqs": [],
            "status": "published",
            "views": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    
    # CREDLOCITY FAQs
    faqs.extend([
        make_faq(
            "How much does Credlocity's credit repair service cost?",
            "<p>Credlocity offers transparent pricing with no hidden fees. Our credit repair services start at <strong>$99/month</strong> with a one-time setup fee. We offer three tiers:</p><ul><li><strong>Basic - $99/month:</strong> Dispute filing with all 3 bureaus, monthly reports, email support</li><li><strong>Advanced - $129/month:</strong> Everything in Basic plus creditor negotiations and priority support</li><li><strong>Premium - $159/month:</strong> Comprehensive service with identity theft protection and financial coaching</li></ul><p>All plans include our <strong>180-day money-back guarantee</strong>. No long-term contracts - cancel anytime.</p>",
            "Credlocity FAQs", "credlocity-faqs", 1
        ),
        make_faq(
            "What makes Credlocity different from other credit repair companies?",
            "<p>Credlocity stands apart through:</p><ol><li><strong>Ethical Practices:</strong> No false promises or guaranteed point increases</li><li><strong>Full Transparency:</strong> Detailed reports showing all disputes and responses</li><li><strong>Education Focus:</strong> We teach you credit management for long-term success</li><li><strong>17 Years Experience:</strong> Over 79,000 clients helped since 2008</li><li><strong>Board Certified Consultants:</strong> BCCC and FCRA certified professionals</li><li><strong>Personal Story:</strong> Founded by someone who successfully repaired his own credit after being scammed by Lexington Law</li></ol>",
            "Credlocity FAQs", "credlocity-faqs", 2
        ),
        make_faq(
            "Do you offer a money-back guarantee?",
            "<p>Yes! Credlocity offers a <strong>180-day (6-month) money-back guarantee</strong>. If you're not satisfied with our progress during the first 180 days, we'll refund your service fees (excludes one-time setup fee).</p><p>This guarantee requires:</p><ul><li>Active participation (providing requested documents)</li><li>Reasonable expectations based on your credit profile</li><li>Written refund request within 180 days</li></ul><p>We're confident in our methods and believe you shouldn't pay for services that don't deliver results.</p>",
            "Credlocity FAQs", "credlocity-faqs", 3
        ),
        make_faq(
            "Can I cancel my Credlocity service anytime?",
            "<p><strong>Yes, absolutely!</strong> Credlocity operates month-to-month with <strong>no long-term contracts</strong>. Cancel anytime without penalty or fees.</p><p>To cancel:</p><ul><li>No cancellation fees</li><li>Cancel by phone, email, or client portal</li><li>Current month's service will be completed</li><li>You'll receive final reports and documentation</li><li>You can return if needed in the future</li></ul><p>We earn your business every month through results and service, not through contracts.</p>",
            "Credlocity FAQs", "credlocity-faqs", 4
        ),
        make_faq(
            "How do I get started with Credlocity?",
            "<p>Getting started is simple:</p><ol><li><strong>Free Consultation:</strong> Schedule a 15-minute call to discuss your goals (no obligation)</li><li><strong>Choose Your Plan:</strong> Select Basic, Advanced, or Premium tier</li><li><strong>Submit Documentation:</strong> Upload credit reports and supporting documents</li><li><strong>Credit Analysis:</strong> Our consultants create your personalized action plan</li><li><strong>Begin Disputes:</strong> We start filing within 3-5 business days</li><li><strong>Monthly Updates:</strong> Receive regular progress reports</li></ol><p>From consultation to first dispute typically takes less than one week.</p>",
            "Credlocity FAQs", "credlocity-faqs", 5
        )
    ])
    
    # CREDIT REPAIR FAQs
    faqs.extend([
        make_faq(
            "What is credit repair and how does it work?",
            "<p>Credit repair is the process of identifying and disputing inaccurate, unverifiable, or outdated information on your credit reports that negatively impacts your credit score.</p><p><strong>The Process:</strong></p><ol><li><strong>Credit Analysis:</strong> Review reports from all 3 bureaus (Equifax, TransUnion, Experian)</li><li><strong>Dispute Filing:</strong> Submit formal disputes citing FCRA violations</li><li><strong>Bureau Investigation:</strong> Bureaus must investigate within 30 days</li><li><strong>Verification:</strong> Bureaus verify with data furnishers</li><li><strong>Resolution:</strong> Unverified items must be removed or corrected</li><li><strong>Follow-up:</strong> Continue until all inaccurate items resolved</li></ol><p>Credit repair is 100% legal under the Fair Credit Reporting Act (FCRA).</p>",
            "Credit Repair FAQs", "credit-repair-faqs", 1
        ),
        make_faq(
            "How long does credit repair take?",
            "<p>Credit repair timelines vary by individual situation, but most clients see:</p><ul><li><strong>Initial Results:</strong> 30-60 days (first bureau responses)</li><li><strong>Significant Improvement:</strong> 3-6 months (major items removed)</li><li><strong>Comprehensive Results:</strong> 6-12 months (optimal credit profile)</li></ul><p><strong>Factors affecting timeline:</strong></p><ul><li>Number of negative items to dispute</li><li>Bureau response times (30-45 days per dispute)</li><li>Complexity of issues</li><li>Your participation level</li><li>Creditor cooperation</li></ul><p>Credit repair is a process, not an overnight fix. Be wary of companies promising instant results.</p>",
            "Credit Repair FAQs", "credit-repair-faqs", 2
        ),
        make_faq(
            "Is credit repair legal?",
            "<p><strong>Yes, credit repair is 100% legal</strong> and protected under federal law. You have the legal right to dispute inaccurate information under the <strong>Fair Credit Reporting Act (FCRA)</strong>.</p><p><strong>Federal Laws Protecting You:</strong></p><ul><li><strong>FCRA:</strong> Requires bureaus to maintain accurate information and investigate disputes within 30 days</li><li><strong>CROA (Credit Repair Organizations Act):</strong> Regulates credit repair companies, requires transparency</li><li><strong>FDCPA:</strong> Protects from abusive collection practices</li></ul><p><strong>What's Legal:</strong> Disputing inaccurate information, hiring professionals, negotiating with creditors, requesting goodwill adjustments</p><p><strong>What's Illegal:</strong> Creating fake identities, providing false information, bribing bureau employees</p>",
            "Credit Repair FAQs", "credit-repair-faqs", 3
        ),
        make_faq(
            "Can credit repair remove late payments?",
            "<p>Credit repair can potentially remove late payments depending on their accuracy:</p><p><strong>Can Often Be Removed:</strong></p><ul><li>Incorrectly reported late payments (when paid on time)</li><li>Late payments over 7 years old</li><li>Duplicate entries</li><li>Payments during proven identity theft</li><li>Unverifiable late payments</li></ul><p><strong>More Difficult (But Possible):</strong></p><ul><li>Accurate late payments may be removed via goodwill deletion requests</li><li>Negotiate removal in exchange for payment</li></ul><p>Legitimate late payments stay on reports for 7 years from delinquency date, but their impact decreases over time. Recent positive payment history can offset older late payments.</p>",
            "Credit Repair FAQs", "credit-repair-faqs", 4
        ),
        make_faq(
            "Can I do credit repair myself or should I hire a professional?",
            "<p>You <strong>can</strong> do credit repair yourself - you have the same legal rights. However, professionals offer advantages:</p><p><strong>DIY Credit Repair:</strong></p><ul><li><strong>Pros:</strong> Free, full control, good for simple disputes</li><li><strong>Cons:</strong> Time-consuming (10-15 hours/month), steep learning curve, easy mistakes, stressful</li></ul><p><strong>Professional Credit Repair:</strong></p><ul><li><strong>Pros:</strong> Expert FCRA knowledge, saves 10-15 hours/month, better success rates, handles all communications, proper legal citations, automatic tracking</li><li><strong>Cons:</strong> Costs $99-159/month, requires trust</li></ul><p><strong>Recommendation:</strong> Try DIY for 1-3 simple errors. For complex situations (multiple items, collections, judgments), professional help is cost-effective considering time and results.</p>",
            "Credit Repair FAQs", "credit-repair-faqs", 5
        ),
        make_faq(
            "What items can be removed from my credit report?",
            "<p>Several types of items can potentially be removed:</p><p><strong>Often Removable:</strong></p><ul><li>Inaccurate personal information</li><li>Fraudulent accounts (identity theft)</li><li>Incorrect late payments</li><li>Duplicate accounts</li><li>Settled debts showing unpaid</li><li>Items beyond reporting period (7 years for most, 10 for bankruptcy)</li><li>Unauthorized hard inquiries</li><li>Unverifiable collections</li><li>Incorrect account status</li></ul><p><strong>May Be Removed with Negotiation:</strong></p><ul><li>Accurate late payments (goodwill deletion)</li><li>Collections (pay-for-delete)</li><li>Charge-offs (settlement)</li></ul><p><strong>Cannot Be Legally Removed if Accurate:</strong></p><ul><li>Accurate late payments under 7 years</li><li>Legitimate bankruptcies under 10 years</li><li>Accurate public records within reporting period</li></ul><p>The key is <strong>accuracy</strong>. Accurate, verifiable information legally belongs on your report.</p>",
            "Credit Repair FAQs", "credit-repair-faqs", 6
        )
    ])
    
    # CREDIT SCORES FAQs
    faqs.extend([
        make_faq(
            "What is a credit score?",
            "<p>A credit score is a three-digit number (300-850) representing your creditworthiness - how likely you are to repay borrowed money based on your credit history. Lenders use it for loan approvals, interest rates, and credit limits.</p><p><strong>Credit Score Ranges:</strong></p><ul><li><strong>800-850:</strong> Exceptional</li><li><strong>740-799:</strong> Very Good</li><li><strong>670-739:</strong> Good</li><li><strong>580-669:</strong> Fair</li><li><strong>300-579:</strong> Poor</li></ul><p>Your score is calculated from credit report information using factors like payment history, debt levels, credit age, new credit, and account types.</p>",
            "Credit Scores FAQs", "credit-scores-faqs", 1
        ),
        make_faq(
            "What is a good credit score?",
            "<p>A <strong>\"good\" credit score is 670 or higher</strong>, but definitions vary by lender and credit type.</p><p><strong>Score Benefits:</strong></p><ul><li><strong>800+ (Exceptional):</strong> Best rates, highest approvals, premium cards</li><li><strong>740-799 (Very Good):</strong> Excellent rates, strong approvals</li><li><strong>670-739 (Good):</strong> Competitive rates, good approvals</li><li><strong>580-669 (Fair):</strong> Higher rates, may need co-signer</li><li><strong>Below 580 (Poor):</strong> Limited options, highest rates, secured credit needed</li></ul><p><strong>What You Can Get with 670+:</strong></p><ul><li>Most credit card and loan approvals</li><li>Lower interest rates</li><li>Higher credit limits</li><li>Better insurance rates</li><li>Easier apartment approvals</li></ul><p>The median U.S. credit score is 714.</p>",
            "Credit Scores FAQs", "credit-scores-faqs", 2
        ),
        make_faq(
            "How is my credit score calculated?",
            "<p>Your credit score uses five factors from your credit report:</p><p><strong>1. Payment History (35%)</strong></p><ul><li>Most important factor</li><li>Do you pay bills on time?</li><li>Any late payments, collections, bankruptcies?</li></ul><p><strong>2. Credit Utilization (30%)</strong></p><ul><li>Percentage of available credit you're using</li><li>Ideal: Below 30% (under 10% is best)</li></ul><p><strong>3. Length of Credit History (15%)</strong></p><ul><li>How long you've had credit</li><li>Average age of all accounts</li><li>Age of oldest and newest accounts</li></ul><p><strong>4. Credit Mix (10%)</strong></p><ul><li>Variety of credit types</li><li>Cards, installment loans, mortgages</li></ul><p><strong>5. New Credit (10%)</strong></p><ul><li>Recent credit inquiries</li><li>Newly opened accounts</li></ul><p>FICO and VantageScore use similar but slightly different methods. FICO is used in 90% of lending decisions.</p>",
            "Credit Scores FAQs", "credit-scores-faqs", 3
        ),
        make_faq(
            "How can I check my credit score for free?",
            "<p>Several legitimate free options exist:</p><p><strong>1. Credit Card Companies:</strong></p><ul><li>Many offer free FICO scores to cardholders</li><li>Check card benefits or mobile app</li><li>Updated monthly</li></ul><p><strong>2. Credit Monitoring Services:</strong></p><ul><li>Credit Karma (free, VantageScore)</li><li>Credit Sesame (free, VantageScore)</li><li>WalletHub (free)</li></ul><p><strong>3. Bank Services:</strong></p><ul><li>Many banks offer free scores to account holders</li></ul><p><strong>4. AnnualCreditReport.com:</strong></p><ul><li>Free credit <strong>reports</strong> (not scores)</li><li>From all 3 bureaus once yearly</li></ul><p><strong>Important Notes:</strong></p><ul><li>Checking your own score is a \"soft\" inquiry - doesn't hurt credit</li><li>Free services often provide VantageScore, but lenders use FICO</li><li>Scores may differ by 20-50 points between models</li></ul>",
            "Credit Scores FAQs", "credit-scores-faqs", 4
        ),
        make_faq(
            "Can I have different credit scores from different bureaus?",
            "<p><strong>Yes, it's completely normal</strong> to have different scores from each bureau (Equifax, TransUnion, Experian). Differences of 20-50 points are common.</p><p><strong>Why Scores Differ:</strong></p><ol><li><strong>Different Information:</strong> Not all creditors report to all bureaus</li><li><strong>Timing Differences:</strong> Creditors report on different days</li><li><strong>Calculation Variations:</strong> Each bureau may use slightly different algorithms</li><li><strong>Errors:</strong> One bureau might have an error others don't</li><li><strong>Multiple Scoring Models:</strong> Many FICO versions exist (FICO 8, 9, industry-specific)</li></ol><p><strong>Example:</strong></p><ul><li>Equifax: 680</li><li>TransUnion: 705</li><li>Experian: 693</li></ul><p>This 25-point variance is typical and not concerning.</p><p><strong>What Lenders Use:</strong></p><ul><li>Mortgage lenders: Middle score from all three</li><li>Auto lenders: Often one specific bureau</li><li>Credit cards: Usually one or two bureaus</li></ul>",
            "Credit Scores FAQs", "credit-scores-faqs", 5
        )
    ])
    
    # FICO SCORE FAQs
    faqs.extend([
        make_faq(
            "What is a FICO score?",
            "<p>A FICO score is a credit score created by the Fair Isaac Corporation that ranges from 300-850. It's the most widely used credit scoring model, with <strong>90% of top lenders</strong> using FICO scores for credit decisions.</p><p><strong>Key Facts:</strong></p><ul><li>Created in 1989</li><li>Based on credit report data from three bureaus</li><li>Different versions exist (FICO 8, FICO 9, etc.)</li><li>Industry-specific scores for auto, mortgage, credit cards</li></ul><p><strong>FICO Score Range:</strong></p><ul><li>800-850: Exceptional</li><li>740-799: Very Good</li><li><strong>670-739: Good</strong></li><li>580-669: Fair</li><li>300-579: Poor</li></ul><p>FICO scores help lenders predict the likelihood you'll repay debt on time.</p>",
            "FICO Score FAQs", "fico-score-faqs", 1
        ),
        make_faq(
            "How is a FICO score calculated?",
            "<p>FICO scores are calculated using five weighted factors from your credit report:</p><p><strong>Payment History (35%)</strong></p><ul><li>Most critical factor</li><li>On-time payments vs late payments</li><li>Evaluated for both revolving and installment accounts</li><li>Even one 30+ day late payment significantly impacts score</li></ul><p><strong>Credit Utilization (30%)</strong></p><ul><li>Ratio of current balances to total available credit</li><li>Lower is better - keep under 30% (under 10% optimal)</li><li>High utilization signals higher credit risk</li></ul><p><strong>Length of Credit History (15%)</strong></p><ul><li>Age of oldest, newest, and average age of all accounts</li><li>Longer histories demonstrate experience</li></ul><p><strong>Credit Mix (10%)</strong></p><ul><li>Variety of credit types (cards, loans, mortgage)</li><li>Successfully handling different types shows responsibility</li></ul><p><strong>New Credit (10%)</strong></p><ul><li>Recent credit applications and inquiries</li><li>New accounts opened</li><li>Too many applications can lower score</li></ul><p>Exact impact varies by individual credit profile.</p>",
            "FICO Score FAQs", "fico-score-faqs", 2
        ),
        make_faq(
            "What's the difference between FICO and VantageScore?",
            "<p>FICO and VantageScore are competing credit scoring models with key differences:</p><p><strong>FICO Score:</strong></p><ul><li>Created by Fair Isaac Corporation (1989)</li><li>Used by 90% of lenders</li><li>Range: 300-850</li><li>Requires 6 months credit history</li><li>Multiple versions (FICO 8, 9, industry-specific)</li><li>Payment history 35%, Credit utilization 30%</li></ul><p><strong>VantageScore:</strong></p><ul><li>Created by three bureaus (2006)</li><li>Growing adoption, especially by credit monitoring services</li><li>Range: 300-850 (VantageScore 3.0 and 4.0)</li><li>Can score with just 1 month history</li><li>Single version across industries</li><li>Slightly different factor weights</li></ul><p><strong>Key Difference:</strong> Lenders predominantly use FICO, while free monitoring services often provide VantageScore. Scores can differ by 20-50 points between models.</p>",
            "FICO Score FAQs", "fico-score-faqs", 3
        ),
        make_faq(
            "How can I check my FICO score?",
            "<p>Several ways to check your FICO score:</p><p><strong>Free Options:</strong></p><ul><li><strong>Credit Card Issuers:</strong> Many provide free FICO scores (Discover, Bank of America, Citibank, Chase, etc.)</li><li><strong>Bank Services:</strong> Some banks offer free FICO scores to account holders</li><li><strong>Experian:</strong> Free FICO 8 score from Experian.com</li></ul><p><strong>Paid Options:</strong></p><ul><li><strong>MyFICO.com:</strong> Official FICO site with all score versions ($19.95-$39.95)</li><li><strong>Credit Monitoring Services:</strong> Various services include FICO scores</li></ul><p><strong>Through Credlocity:</strong></p><ul><li>We provide tri-merge credit reports with FICO scores monthly</li><li>Included in all service plans</li></ul><p><strong>Important:</strong> Checking your own FICO score is a \"soft inquiry\" and doesn't hurt your credit.</p>",
            "FICO Score FAQs", "fico-score-faqs", 4
        )
    ])
    
    # EQUIFAX FAQs (including 2017 breach research)
    faqs.extend([
        make_faq(
            "What is Equifax?",
            "<p>Equifax is one of the three major credit bureaus in the United States (along with TransUnion and Experian). Founded in 1899, Equifax:</p><ul><li>Collects and maintains credit information on over 800 million consumers worldwide</li><li>Provides credit reports and scores to lenders, employers, and consumers</li><li>Offers credit monitoring and identity theft protection services</li><li>Maintains 88 million businesses in their database</li></ul><p><strong>Services:</strong></p><ul><li>Credit reports and FICO scores</li><li>Credit monitoring (Equifax Complete)</li><li>Identity theft protection</li><li>Employment and tenant screening</li><li>Fraud prevention solutions</li></ul>",
            "Equifax FAQs", "equifax-faqs", 1
        ),
        make_faq(
            "What was the 2017 Equifax data breach?",
            "<p>The 2017 Equifax data breach was one of the largest data compromises in U.S. history, exposing personal information of approximately <strong>147 million Americans</strong>.</p><p><strong>What Happened:</strong></p><ul><li>Breach occurred May-July 2017, discovered July 29, publicly disclosed September 7</li><li>Failed to patch known Apache Struts vulnerability</li><li>Weak security practices (expired certificates, no encryption)</li></ul><p><strong>Compromised Data:</strong></p><ul><li>Names, Social Security numbers, birthdates, addresses</li><li>Driver's license numbers</li><li>Some credit card details</li></ul><p><strong>Settlement ($1.38 Billion):</strong></p><ul><li>Up to $425 million for consumer compensation</li><li>Deadline to file claims was January 22, 2024</li><li>Payments continuing through late 2024</li></ul><p><strong>Equifax Response:</strong></p><ul><li>Spent over $1.6 billion on security upgrades</li><li>Offered free credit monitoring to affected consumers</li><li>Improved IT systems and hired cybersecurity firms</li></ul>",
            "Equifax FAQs", "equifax-faqs", 2
        ),
        make_faq(
            "How do I dispute errors with Equifax?",
            "<p>You can dispute Equifax errors through multiple channels:</p><p><strong>Online Dispute:</strong></p><ul><li>Visit equifax.com/disputes</li><li>Create account or log in</li><li>Select items to dispute</li><li>Provide explanation and documentation</li><li>Submit dispute</li></ul><p><strong>By Phone:</strong></p><ul><li>Call 866-349-5191</li><li>Have your credit report ready</li><li>Explain the error</li></ul><p><strong>By Mail:</strong></p><ul><li>Send to: Equifax Information Services LLC, P.O. Box 740256, Atlanta, GA 30374</li><li>Include: Copy of credit report, ID proof, documentation</li></ul><p><strong>Investigation Timeline:</strong></p><ul><li>Equifax must investigate within <strong>30 days</strong> (45 if additional info provided)</li><li>Results mailed within 5 business days of completion</li><li>If item can't be verified, it must be removed</li></ul>",
            "Equifax FAQs", "equifax-faqs", 3
        ),
        make_faq(
            "How do I freeze my Equifax credit?",
            "<p>Freezing your Equifax credit prevents new creditors from accessing your report, helping prevent identity theft.</p><p><strong>How to Freeze (Free):</strong></p><p><strong>Online:</strong></p><ul><li>Visit equifax.com/freeze</li><li>Create account</li><li>Verify identity</li><li>Freeze activated immediately</li></ul><p><strong>By Phone:</strong></p><ul><li>Call 800-349-9960</li><li>Follow automated prompts</li></ul><p><strong>By Mail:</strong></p><ul><li>Send request with ID proof to Equifax Security Freeze, P.O. Box 105788, Atlanta, GA 30348</li></ul><p><strong>Important Notes:</strong></p><ul><li>Freeze is FREE by federal law</li><li>Must freeze with all 3 bureaus separately</li><li>Can temporarily lift or permanently remove anytime</li><li>Doesn't affect credit score</li><li>Existing creditors can still access</li></ul>",
            "Equifax FAQs", "equifax-faqs", 4
        )
    ])
    
    # Add to database
    if faqs:
        await db.faqs.insert_many(faqs)
        print(f"✓ Created {len(faqs)} comprehensive FAQs")
    
    # Update category counts
    for category in categories:
        count = len([faq for faq in faqs if faq["category_slug"] == category["slug"]])
        await db.faq_categories.update_one(
            {"slug": category["slug"]},
            {"$set": {"faq_count": count}}
        )
    
    print("✅ Comprehensive FAQ seed complete!")
    print(f"📊 Total: {len(faqs)} FAQs across {len(categories)} categories")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_comprehensive_faqs())
