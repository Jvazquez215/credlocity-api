"""
Credlocity Document Center API
Manages documentation sections with annotated screenshots for CMS knowledge base
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

documentation_router = APIRouter(prefix="/api/documentation")

db = None

def set_db(database):
    global db
    db = database

from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user):
    if user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin access required")


@documentation_router.get("/sections")
async def list_sections(category: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"is_published": True}
    if category:
        query["category"] = category
    sections = await db.documentation_sections.find(query, {"_id": 0}).sort("order", 1).to_list(100)
    return sections


@documentation_router.get("/sections/{section_id}")
async def get_section(section_id: str, user: dict = Depends(get_current_user)):
    section = await db.documentation_sections.find_one({"id": section_id}, {"_id": 0})
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@documentation_router.post("/sections")
async def create_section(data: dict, user: dict = Depends(get_current_user)):
    require_admin(user)
    now = datetime.now(timezone.utc).isoformat()
    section = {
        "id": str(uuid4()),
        "title": data.get("title", ""),
        "slug": data.get("slug", ""),
        "description": data.get("description", ""),
        "category": data.get("category", "general"),
        "icon": data.get("icon", "FileText"),
        "order": data.get("order", 99),
        "content_blocks": data.get("content_blocks", []),
        "is_published": data.get("is_published", True),
        "created_by": user.get("id"),
        "created_at": now,
        "updated_at": now
    }
    await db.documentation_sections.insert_one(section)
    section.pop("_id", None)
    return section


@documentation_router.put("/sections/{section_id}")
async def update_section(section_id: str, data: dict, user: dict = Depends(get_current_user)):
    require_admin(user)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data.pop("id", None)
    data.pop("_id", None)
    result = await db.documentation_sections.update_one({"id": section_id}, {"$set": data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Section not found")
    updated = await db.documentation_sections.find_one({"id": section_id}, {"_id": 0})
    return updated


@documentation_router.delete("/sections/{section_id}")
async def delete_section(section_id: str, user: dict = Depends(get_current_user)):
    require_admin(user)
    result = await db.documentation_sections.delete_one({"id": section_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Section not found")
    return {"message": "Section deleted"}


@documentation_router.get("/categories")
async def list_categories(user: dict = Depends(get_current_user)):
    return [
        {"id": "getting-started", "label": "Getting Started", "icon": "Rocket"},
        {"id": "operations", "label": "Operations", "icon": "Settings"},
        {"id": "finance", "label": "Finance & Billing", "icon": "DollarSign"},
        {"id": "hr", "label": "HR & Training", "icon": "Users"},
        {"id": "legal", "label": "Legal", "icon": "Scale"},
        {"id": "marketing", "label": "Marketing & Content", "icon": "Megaphone"},
        {"id": "admin", "label": "Administration", "icon": "Shield"},
    ]


async def seed_documentation():
    """Seed the document center with comprehensive CMS documentation."""
    existing = await db.documentation_sections.count_documents({})
    if existing > 0:
        return

    sections = [
        {
            "id": str(uuid4()),
            "title": "Dashboard & KPIs",
            "slug": "dashboard-kpis",
            "description": "Understanding your master dashboard and department-specific metrics",
            "category": "getting-started",
            "icon": "LayoutDashboard",
            "order": 1,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Credlocity Master Dashboard is your command center. It aggregates Key Performance Indicators (KPIs) from every department into a single, scannable view. Depending on your role, you may see a department-specific dashboard instead."},
                {"type": "callout", "variant": "info", "content": "Your dashboard view is determined by your RBAC group. Admins see the Master Dashboard; Collection Reps see the Collections Dashboard; Marketing team sees the Marketing Dashboard, etc."},
                {"type": "screenshot", "image_url": "", "alt_text": "Master Dashboard Overview", "annotations": [
                    {"x": 12, "y": 8, "num": "1", "text": "Content KPIs: Total blog posts, pages, FAQs, and media files across the platform."},
                    {"x": 45, "y": 8, "num": "2", "text": "Collections & Revenue: Active accounts, total amount owed, and commission payouts."},
                    {"x": 78, "y": 8, "num": "3", "text": "HR & Payroll: Employee count, pending payroll, and training completion rates."},
                    {"x": 12, "y": 55, "num": "4", "text": "Legal KPIs: Active lawsuits, cases in marketplace, and attorney network size."},
                    {"x": 45, "y": 55, "num": "5", "text": "Client Stats: Total clients, active cases, and recent submissions."},
                    {"x": 78, "y": 55, "num": "6", "text": "Outsourcing Stats: Partner count, active client files, and monthly revenue."}
                ]},
                {"type": "text", "title": "Understanding KPI Cards", "content": "Each KPI card shows a metric title, the current value, and often a trend indicator or sub-metric. Green values indicate positive trends, red indicates areas needing attention. Cards are organized by department so you can quickly scan the area most relevant to your role."},
                {"type": "list", "title": "Department Dashboards", "items": [
                    "Admin/Super Admin -> Master Dashboard (all KPIs across departments)",
                    "Collection Rep/Manager -> Collections Dashboard (active trackers, accounts, commissions earned)",
                    "Marketing -> Marketing Dashboard (content stats, blog performance, review queue)",
                    "HR & Payroll -> HR Dashboard (payroll summary, training progress, team overview)",
                    "Legal -> Legal Dashboard (active lawsuits, marketplace cases, attorney network)",
                    "Finance -> Finance Dashboard (revenue overview, commission payouts, billing stats)"
                ]}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Navigation & Sidebar",
            "slug": "navigation-sidebar",
            "description": "How the CMS sidebar is organized and how permissions control visibility",
            "category": "getting-started",
            "icon": "Menu",
            "order": 2,
            "content_blocks": [
                {"type": "text", "title": "Sidebar Structure", "content": "The admin sidebar is organized into department sections. Each section contains links to related features. The sections you see depend on your assigned permissions through the RBAC system."},
                {"type": "screenshot", "image_url": "", "alt_text": "Sidebar Navigation", "annotations": [
                    {"x": 8, "y": 5, "num": "1", "text": "Dashboard link: Returns you to your role-specific dashboard from anywhere."},
                    {"x": 8, "y": 15, "num": "2", "text": "Operations section: Collections, Clients, and Outsourcing modules."},
                    {"x": 8, "y": 35, "num": "3", "text": "Legal section: Attorney Marketplace and Lawsuits Filed."},
                    {"x": 8, "y": 50, "num": "4", "text": "Marketing section: Website content, Reviews & Social Proof management."},
                    {"x": 8, "y": 65, "num": "5", "text": "HR & Payroll: Team management, Authors/Profiles, Payroll, Training, Security."},
                    {"x": 8, "y": 80, "num": "6", "text": "Finance, Partners, Tools, and Admin sections at the bottom."}
                ]},
                {"type": "callout", "variant": "warning", "content": "If you cannot see a section or link, it means your user group does not have the required permission. Contact your administrator to request access."},
                {"type": "list", "title": "Department Sections", "items": [
                    "Operations: Collections (accounts, approval queue, dialpad, commission settings), Clients (list, profiles), Outsourcing (dashboard, partners, invoices, work logs, tickets)",
                    "Legal: Attorney Marketplace (case submissions, bidding), Lawsuits Filed (case tracking)",
                    "Marketing: Website (blog, pages, FAQs, education hub, press releases, banners, media), Reviews & Social Proof (reviews, outsource reviews, categories)",
                    "HR & Payroll: Team Management, Authors/Profiles, Payroll, Training, Security",
                    "Finance: Billing (dashboard, plans, invoices, settings)",
                    "Partners: Affiliates & Partners directory",
                    "Tools: Internal Chat, Support Chat, Document Center",
                    "Admin: Access Control (RBAC), Site Settings, Marketplace Management"
                ]}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Collections System",
            "slug": "collections-system",
            "description": "How collection accounts, payment plans, fees, and commissions work",
            "category": "operations",
            "icon": "Wallet",
            "order": 3,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Collections module manages consumer debt collection accounts. Each account represents a consumer with an outstanding balance. Collection Representatives work these accounts by contacting consumers, negotiating payment plans, and processing payments."},
                {"type": "screenshot", "image_url": "", "alt_text": "Collections Account List", "annotations": [
                    {"x": 15, "y": 5, "num": "1", "text": "Search bar: Filter accounts by name, account number, or status."},
                    {"x": 75, "y": 5, "num": "2", "text": "Status filters: Active, Paid, Delinquent, Closed."},
                    {"x": 15, "y": 30, "num": "3", "text": "Account details: Consumer name, account number, original balance."},
                    {"x": 60, "y": 30, "num": "4", "text": "Amount Owed: Current outstanding balance after payments."},
                    {"x": 80, "y": 30, "num": "5", "text": "Status badge: Shows current account state (active, payment plan, etc)."}
                ]},
                {"type": "text", "title": "Fee Structure (2024+ Accounts)", "content": "Every collection account has a standard fee structure applied when a payment plan is created. These fees are revenue for Credlocity and partially fund rep commissions."},
                {"type": "table", "title": "Standard Fees", "headers": ["Fee", "Amount", "Waivable?", "Max Waive"], "rows": [
                    ["Collection File Processing", "$150.00", "No", "N/A"],
                    ["Collection Fee", "$350.00", "Yes", "$175.00"],
                    ["Payment Processing", "$190.00", "Yes", "$90.00"],
                    ["Late Fee (1-10 days)", "$10.50", "Yes", "Per tier"],
                    ["Late Fee (11-15 days)", "$17.50", "Yes", "Per tier"],
                    ["Late Fee (16-30 days)", "$30.00", "Yes", "Per tier"],
                    ["Late Fee (31-90 days)", "$50.00", "Yes", "Per tier"]
                ]},
                {"type": "text", "title": "Commission Rules", "content": "Collection Representatives earn commissions based on payments collected. The commission structure is designed to incentivize full and timely collections."},
                {"type": "list", "title": "Key Commission Rules", "items": [
                    "Base Rate: 20% of all collected amounts (past due + late fees kept), EXCLUDING the collection fee",
                    "Collection Fee: Rep keeps 100% of the collection fee, paid immediately when first payment is received",
                    "Payment Plans: The 20% commission only unlocks when 70% of the tier's owed amount is collected",
                    "Late fees that are waived are subtracted from the commission base",
                    "All commission entries automatically flow into the Payroll system"
                ]},
                {"type": "table", "title": "Payment Tier System", "headers": ["Tier", "Name", "Min Down Payment", "Max Months", "Collection Fee Max Waive", "Processing Max Waive"], "rows": [
                    ["1", "Payment in Full", "100%", "0", "$125", "$70"],
                    ["2", "Payment Plan (3-4 Mo)", "25%", "4", "$75", "$40"],
                    ["3", "Extended Plan (5-6 Mo)", "30%", "6", "$50", "$25"]
                ]},
                {"type": "callout", "variant": "tip", "content": "The Commission Dashboard (Collections > Commission Dashboard) shows real-time progress toward the 70% threshold for each active payment plan, plus a leaderboard of top-earning reps."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Payroll Management",
            "slug": "payroll-management",
            "description": "Managing employee pay periods, commissions, bonuses, and pay stubs",
            "category": "finance",
            "icon": "Banknote",
            "order": 4,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Payroll module handles all employee compensation. It integrates directly with the Collections commission system so that earned commissions automatically appear in payroll. The system supports salary, hourly, and commission-based pay structures."},
                {"type": "screenshot", "image_url": "", "alt_text": "Payroll Dashboard", "annotations": [
                    {"x": 15, "y": 8, "num": "1", "text": "Overview tab: Summary cards showing total payroll, pending commissions, and upcoming pay period."},
                    {"x": 50, "y": 8, "num": "2", "text": "Tab navigation: Overview, Employees, Commissions, Bonuses, Pay Periods."},
                    {"x": 80, "y": 8, "num": "3", "text": "Quick actions: Run payroll, add bonus, create pay period."}
                ]},
                {"type": "list", "title": "Payroll Dashboard Tabs", "items": [
                    "Overview: High-level summary cards (Total Payroll Cost, Pending Commissions, Active Employees, Upcoming Pay Date)",
                    "Employees: Payroll profiles with salary/hourly rate, pay type, and department",
                    "Commissions: All commission entries from Collections, showing type (collection fee vs 20% base), amount, and status",
                    "Bonuses: One-time or recurring bonuses assigned to employees",
                    "Pay Periods: Create and run payroll for date ranges. Running payroll generates pay stubs."
                ]},
                {"type": "text", "title": "Running Payroll", "content": "To process payroll: 1) Go to Pay Periods tab, 2) Create a new pay period with start/end dates, 3) Click 'Run Payroll' - this calculates base pay + commissions + bonuses - deductions for each employee and generates downloadable PDF pay stubs."},
                {"type": "callout", "variant": "info", "content": "Commission entries flow automatically from Collections. When a rep earns a commission (either the immediate collection fee or the 20% base upon hitting the 70% threshold), it appears in the Commissions tab ready for the next payroll run."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Outsourcing Partner Management",
            "slug": "outsourcing-partners",
            "description": "Managing outsourcing partners, service agreements, billing, and work logs",
            "category": "operations",
            "icon": "Handshake",
            "order": 5,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Outsourcing module manages relationships with credit repair outsourcing partners. Each partner has a full profile with billing history, work logs, service agreements, escalation tickets, and notes. Partners are billed based on consumer accounts processed."},
                {"type": "screenshot", "image_url": "", "alt_text": "Outsourcing Partner Profile", "annotations": [
                    {"x": 15, "y": 5, "num": "1", "text": "Partner header: Company name, contact info, and approval status."},
                    {"x": 50, "y": 12, "num": "2", "text": "Tab navigation: Profile, Notes, Agreements, Pricing, Billing, Work Logs, Escalations."},
                    {"x": 80, "y": 5, "num": "3", "text": "Quick actions: Create Escalation ticket."}
                ]},
                {"type": "list", "title": "Partner Profile Tabs", "items": [
                    "Profile: Company details, contact info, CRM platform, status management",
                    "Notes: Communication log (phone calls, emails, internal updates) with categories",
                    "Agreements: Generate PDF service agreements with custom pricing OR upload external documents",
                    "Pricing: Current cost per consumer, active client count, billing cycle, pricing history",
                    "Billing: Credits, discounts, applied coupons, and full invoice history",
                    "Work Logs: Daily tracking of disputes processed and letters sent",
                    "Escalations: Support tickets with urgency levels and status tracking"
                ]},
                {"type": "text", "title": "Service Agreements", "content": "The system can generate professional PDF service agreements with dynamic pricing. Admins set the rate per account, account range (e.g., 35-50 accounts), and package name. The system calculates monthly minimums and maximums, then generates a legally-formatted PDF ready for signing."},
                {"type": "callout", "variant": "tip", "content": "Use the 'Generate Service Agreement' button on the Agreements tab to create a new agreement. The pricing preview shows calculated monthly costs before you generate the PDF."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "RBAC & Permissions",
            "slug": "rbac-permissions",
            "description": "How role-based access control manages what each user can see and do",
            "category": "admin",
            "icon": "Shield",
            "order": 6,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "Credlocity uses a Role-Based Access Control (RBAC) system to manage what each employee can access. Users are assigned to Groups, and each Group has a set of Permissions. The system controls both sidebar navigation visibility and API access."},
                {"type": "screenshot", "image_url": "", "alt_text": "Permissions Manager", "annotations": [
                    {"x": 20, "y": 10, "num": "1", "text": "Group list: All defined groups (Admin, Collection Manager, Marketing, HR, etc)."},
                    {"x": 60, "y": 10, "num": "2", "text": "Permission grid: Check/uncheck permissions for the selected group."},
                    {"x": 60, "y": 50, "num": "3", "text": "Permission categories: Content, Collections, Legal, Outsourcing, HR, etc."}
                ]},
                {"type": "list", "title": "Default Groups", "items": [
                    "Super Admin: Full access to everything",
                    "Admin: Full access except system-level settings",
                    "Collection Manager: Collections, reports, commission settings",
                    "Collection Rep: View/edit assigned collection accounts",
                    "Marketing: Blog, pages, FAQs, reviews, media library",
                    "HR & Payroll: Team management, payroll, training",
                    "Legal: Lawsuits, attorney marketplace, case management",
                    "Partner: Outsourcing partner portal access"
                ]},
                {"type": "text", "title": "How Permissions Work", "content": "Each permission is a dot-notation string like 'collections.view' or 'content.edit'. When you navigate the sidebar, items are only shown if your group has the corresponding permission. The same permissions are checked on the backend for API requests."},
                {"type": "callout", "variant": "warning", "content": "Only Super Admin and Admin roles can manage RBAC settings. Navigate to Admin > Access Control to view and edit group permissions."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Training Center",
            "slug": "training-center",
            "description": "Employee training modules, quizzes, certificates, and assignments",
            "category": "hr",
            "icon": "GraduationCap",
            "order": 7,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Training Center is where employees complete onboarding and ongoing education. Administrators create training modules with step-by-step guides, then assign them to employees or departments. Each module can include a quiz, and passing the quiz generates a PDF certificate."},
                {"type": "list", "title": "Training Flow", "items": [
                    "1. Admin creates a training module with title, department, and step-by-step content",
                    "2. Admin adds a quiz with multiple-choice questions and a passing score",
                    "3. Admin assigns the module to specific employees or entire departments",
                    "4. Employees see assignments in 'My Assignments' and complete the steps",
                    "5. After completing all steps, the employee takes the quiz",
                    "6. Passing the quiz generates a downloadable PDF certificate",
                    "7. Admin tracks progress via the Progress Dashboard (completion rates, scores, top performers)"
                ]},
                {"type": "text", "title": "Quiz System", "content": "Each module can have a quiz with multiple-choice questions. Admins set correct answers and a passing score percentage. Employees get instant feedback showing which answers were correct/incorrect with explanations. Failed attempts can be retried."},
                {"type": "callout", "variant": "tip", "content": "The Progress Dashboard shows department-level stats, individual completion rates, and a drill-down report for each module. Use this to identify who needs additional training."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Content Management",
            "slug": "content-management",
            "description": "Managing blog posts, pages, FAQs, media library, and SEO",
            "category": "marketing",
            "icon": "PenTool",
            "order": 8,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Content Management system handles all public-facing content. This includes blog posts, static pages, FAQs, education hub articles, press releases, and the media library. All content supports SEO metadata, schema markup, and featured images."},
                {"type": "list", "title": "Content Types", "items": [
                    "Blog Posts: Rich text articles with categories, tags, author attribution, featured images, and SEO metadata",
                    "Pages: Static content pages with customizable layouts, canonical URLs, and schema markup",
                    "FAQs: Categorized frequently asked questions with rich text answers",
                    "Education Hub: Credit education articles and dispute letter templates",
                    "Press Releases: Company news and announcements",
                    "Media Library: Centralized image/file storage with drag-and-drop upload"
                ]},
                {"type": "text", "title": "SEO Features", "content": "Every content item supports meta title, meta description, canonical URL, Open Graph image, and robots directives (index/noindex, follow/nofollow). Schema.org structured data can be configured per page for enhanced search results."},
                {"type": "text", "title": "Rich Text Editor", "content": "The editor supports headings (H1-H6), bold/italic/underline/strikethrough, text colors and highlights, alignment, ordered/unordered lists, blockquotes, code blocks, tables, image upload/drag-drop, YouTube embeds, and raw HTML insertion."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Support & Chat Systems",
            "slug": "support-chat",
            "description": "Internal team chat, customer support live chat, and chatbot configuration",
            "category": "operations",
            "icon": "MessageCircle",
            "order": 9,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "Credlocity has two chat systems: Internal Chat for team communication and Customer Support Chat for handling customer inquiries. Both are accessible from the sidebar under Tools."},
                {"type": "list", "title": "Internal Chat Features", "items": [
                    "Direct Messages: 1-on-1 conversations between team members",
                    "Group Channels: Custom channels for project teams or topics",
                    "Department Channels: Auto-created channels for each department (Collections, Sales, Support, Legal, etc)",
                    "File Sharing: Attach files to messages",
                    "Unread Counts: Badge indicators for unread messages"
                ]},
                {"type": "list", "title": "Customer Support Chat Features", "items": [
                    "Live Chat: Real-time customer sessions with agent queue (Waiting/Active/Mine filters)",
                    "Chatbot Settings: AI model configuration, system prompt, temperature, working hours",
                    "Knowledge Base: Article management with import from FAQs/Blog posts",
                    "Analytics: Session stats, resolution rate, top-performing agents",
                    "Canned Responses: Pre-written reply templates for common questions"
                ]},
                {"type": "text", "title": "Chat Widget", "content": "The public-facing chat widget appears on the Credlocity website. It captures visitor info (name, email) to create leads, then starts a live chat session. The widget can be configured to hide on specific pages (e.g., client intake portal) and respects working hours settings."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Billing & Subscriptions",
            "slug": "billing-subscriptions",
            "description": "Stripe integration, subscription plans, invoices, and coupons",
            "category": "finance",
            "icon": "CreditCard",
            "order": 10,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "The Billing module manages company subscriptions via Stripe. It includes subscription plan management, invoice generation, coupon/discount codes, and billing settings for the public pricing page."},
                {"type": "list", "title": "Billing Components", "items": [
                    "Billing Dashboard: Overview of active subscriptions, revenue, and recent transactions",
                    "Subscription Plans: Create and manage tiered plans (Basic, Pro, Enterprise) with Stripe integration",
                    "Invoices: View and manage all invoices, filter by status (paid, pending, overdue)",
                    "Coupons: Create discount codes with percentage or fixed-amount discounts, usage limits, expiration dates",
                    "Companies: Manage subscribing companies with their plan details and payment history",
                    "Website Pricing: Configure the public pricing page content and plan display"
                ]}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid4()),
            "title": "Client Management",
            "slug": "client-management",
            "description": "Managing client profiles, case submissions, and the attorney marketplace",
            "category": "legal",
            "icon": "Users",
            "order": 11,
            "content_blocks": [
                {"type": "text", "title": "Overview", "content": "Client Management handles consumer profiles who have engaged Credlocity's services. Each client has a detailed profile with their credit issues, associated cases, and communication history."},
                {"type": "list", "title": "Client Features", "items": [
                    "Client List: Searchable directory of all clients with status filters",
                    "Client Profile: Detailed view with contact info, credit issues, case history, and notes",
                    "Case Submission: Admin can submit cases to the Attorney Marketplace on behalf of clients",
                    "Attorney Marketplace: Attorneys bid on FCRA cases with real-time notifications"
                ]},
                {"type": "text", "title": "Attorney Marketplace", "content": "When a client has a viable FCRA case, it's submitted to the Attorney Marketplace. Attorneys receive notifications and can place bids. The system supports outbid notifications, bidding deadlines, and automatic revenue splitting (40% Credlocity / 60% referring company) when cases settle."},
                {"type": "callout", "variant": "info", "content": "Revenue splits are tracked in the Revenue Split Report (Finance > Revenue). Each settled case generates entries showing the exact split amounts between Credlocity and the referring company."}
            ],
            "is_published": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    ]

    for section in sections:
        await db.documentation_sections.insert_one(section)
    print(f"[SEED] Seeded {len(sections)} documentation sections")


async def seed_cms_mastery_training():
    """Seed a CMS Mastery training module with comprehensive quiz."""
    existing = await db.training_modules.find_one({"title": "Credlocity CMS Mastery"})
    if existing:
        return

    now = datetime.now(timezone.utc).isoformat()
    module_id = str(uuid4())

    # Get the admin user for created_by
    admin = await db.users.find_one({"email": "Admin@credlocity.com"}, {"_id": 0})
    admin_id = admin.get("id", "system") if admin else "system"

    module = {
        "id": module_id,
        "title": "Credlocity CMS Mastery",
        "description": "Comprehensive training on all Credlocity CMS features, KPIs, navigation, and workflows. Every employee must complete this module and pass the quiz.",
        "department": "General",
        "content": "",
        "steps": [
            {
                "id": str(uuid4()),
                "title": "Dashboard & KPIs Overview",
                "content": "The Master Dashboard is the first screen you see after login. It displays KPIs from every department:\n\n- Content Overview: Total pages, blog posts, reviews, and team members\n- Collections & Revenue: Commission earned, pending commissions, active trackers, and a link to the Collections Dashboard\n- HR & Payroll: Active employees, annual salaries, monthly commissions, and bonuses\n- Legal: Active lawsuits, marketplace cases, and attorney network size\n- Client Stats: Total clients, active cases, and recent submissions\n- Outsourcing: Partner count, client files, and monthly revenue\n\nYour dashboard view depends on your RBAC group. Admins see all KPIs; other roles see their department dashboard.",
                "order": 1
            },
            {
                "id": str(uuid4()),
                "title": "Sidebar Navigation & Permissions",
                "content": "The sidebar is organized into department sections:\n\n- Operations: Collections, Clients, Outsourcing\n- Legal: Attorney Marketplace, Lawsuits Filed\n- Marketing: Website (blog, pages, FAQs), Reviews & Social Proof\n- HR & Payroll: Team Management, Authors/Profiles, Payroll, Training, Security\n- Finance: Billing\n- Partners: Affiliates & Partners\n- Tools: Team Chat, Customer Support, Document Center\n- Admin: Access Control, Site Settings\n\nVisibility is controlled by RBAC permissions. If you can't see a section, your group doesn't have the required permission.",
                "order": 2
            },
            {
                "id": str(uuid4()),
                "title": "Collections & Commission System",
                "content": "The Collections module manages consumer debt accounts.\n\nFee Structure:\n- Collection File Processing: $150 (non-waivable)\n- Collection Fee: $350 (waivable up to $175)\n- Payment Processing: $190 (waivable up to $90)\n- Late fees vary by tier ($10.50 to $50)\n\nCommission Rules:\n- Base Rate: 20% of collected amounts (excluding collection fee)\n- Collection Fee: Rep keeps 100%, paid on first payment\n- 70% Threshold: The 20% commission only unlocks when 70% of the tier is collected\n\nPayment Tiers:\n- Tier 1 (Full Payment): 100% down, max waive $125/$70\n- Tier 2 (3-4 months): 25% down, max waive $75/$40\n- Tier 3 (5-6 months): 30% down, max waive $50/$25",
                "order": 3
            },
            {
                "id": str(uuid4()),
                "title": "Payroll Management",
                "content": "The Payroll module has 5 tabs:\n\n1. Overview: Summary cards (Total Payroll, Pending Commissions, Active Employees, Upcoming Pay Date)\n2. Employees: Payroll profiles with salary/hourly rate and department\n3. Commissions: All commission entries from Collections (collection fee and 20% base)\n4. Bonuses: One-time or recurring bonuses\n5. Pay Periods: Create periods and run payroll to generate pay stubs\n\nCommissions flow automatically from Collections. When a rep earns a commission, it appears in the Commissions tab for the next payroll run.",
                "order": 4
            },
            {
                "id": str(uuid4()),
                "title": "Outsourcing Partner Management",
                "content": "The Outsourcing module manages credit repair outsourcing partners.\n\nPartner Profile Tabs:\n- Profile: Company details, contact, CRM platform, status\n- Notes: Communication log with categories\n- Agreements: Generate PDF service agreements with custom pricing OR upload documents\n- Pricing: Cost per consumer, billing cycle, pricing history\n- Billing: Credits, discounts, coupons, invoices\n- Work Logs: Daily tracking of disputes and letters\n- Escalations: Support tickets with urgency levels\n\nService Agreements: Set rate per account ($30 default), account range (35-50), and package name. System generates a professional PDF.",
                "order": 5
            },
            {
                "id": str(uuid4()),
                "title": "RBAC, Content Management & Support",
                "content": "RBAC (Access Control):\n- Users are assigned to Groups (Admin, Collection Rep, Marketing, HR, Legal, etc.)\n- Groups have Permissions (dot-notation: collections.view, content.edit, etc.)\n- Permissions control sidebar visibility AND API access\n\nContent Management:\n- Blog posts, pages, FAQs, education hub, press releases, media library\n- Full SEO support: meta title/description, canonical URLs, schema markup, robots directives\n- Rich text editor: headings, formatting, tables, images, YouTube, HTML\n\nSupport & Chat:\n- Internal Chat: DMs, group channels, department channels\n- Customer Support: Live chat with agent queue, chatbot settings, knowledge base, analytics\n- Chat Widget: Public-facing widget with lead capture and working hours",
                "order": 6
            }
        ],
        "status": "published",
        "order": 0,
        "created_by": admin_id,
        "created_by_name": "Master Administrator",
        "created_at": now,
        "updated_at": now
    }

    await db.training_modules.insert_one(module)
    module.pop("_id", None)

    # Create the quiz
    quiz_id = str(uuid4())
    quiz = {
        "id": quiz_id,
        "module_id": module_id,
        "passing_score": 70,
        "questions": [
            {"id": str(uuid4()), "question": "What determines which dashboard view an employee sees upon login?", "options": ["Their department", "Their RBAC group", "Their seniority level", "Their login count"], "correct_answer": 1, "explanation": "Dashboard views are determined by the user's RBAC group. Admins see the Master Dashboard; other roles see their department-specific dashboard."},
            {"id": str(uuid4()), "question": "What is the standard Collection File Processing fee?", "options": ["$100", "$150", "$200", "$350"], "correct_answer": 1, "explanation": "The Collection File Processing fee is $150 and is non-waivable."},
            {"id": str(uuid4()), "question": "What percentage of collected amounts does a Collection Rep earn as base commission?", "options": ["10%", "15%", "20%", "25%"], "correct_answer": 2, "explanation": "Collection Reps earn 20% of all collected amounts (past due + late fees kept), excluding the collection fee."},
            {"id": str(uuid4()), "question": "What threshold must be met before the 20% base commission is paid out?", "options": ["50% of tier amount collected", "60% of tier amount collected", "70% of tier amount collected", "100% of tier amount collected"], "correct_answer": 2, "explanation": "The 20% commission only unlocks when 70% of the tier's owed amount has been collected."},
            {"id": str(uuid4()), "question": "Which fee does the Collection Rep keep 100% of?", "options": ["Processing fee", "Collection fee", "Late fee", "File processing fee"], "correct_answer": 1, "explanation": "The Rep keeps 100% of the collection fee ($350), paid immediately when the first payment is received."},
            {"id": str(uuid4()), "question": "How many payment tiers exist in the collection system?", "options": ["2", "3", "4", "5"], "correct_answer": 1, "explanation": "There are 3 tiers: Payment in Full (Tier 1), Payment Plan 3-4 months (Tier 2), and Extended Plan 5-6 months (Tier 3)."},
            {"id": str(uuid4()), "question": "What is the minimum down payment percentage for Tier 3 (Extended Plan)?", "options": ["10%", "20%", "25%", "30%"], "correct_answer": 3, "explanation": "Tier 3 (Extended Plan, 5-6 months) requires a minimum 30% down payment."},
            {"id": str(uuid4()), "question": "How are commissions transferred to the Payroll system?", "options": ["Manual entry by HR", "Automatic flow from Collections", "Monthly batch import", "Employee self-reporting"], "correct_answer": 1, "explanation": "Commission entries flow automatically from the Collections system into the Payroll Commissions tab."},
            {"id": str(uuid4()), "question": "What does the Payroll system generate when you 'Run Payroll'?", "options": ["Commission reports", "Tax forms", "PDF pay stubs for each employee", "Bank transfer requests"], "correct_answer": 2, "explanation": "Running payroll calculates base pay + commissions + bonuses - deductions and generates downloadable PDF pay stubs."},
            {"id": str(uuid4()), "question": "What is the default rate per account for outsourcing service agreements?", "options": ["$20.00", "$25.00", "$30.00", "$35.00"], "correct_answer": 2, "explanation": "The default rate per account is $30.00 for outsourcing service agreements."},
            {"id": str(uuid4()), "question": "In the RBAC system, what controls sidebar navigation visibility?", "options": ["User's email domain", "User's department", "Permissions assigned to the user's group", "User's login frequency"], "correct_answer": 2, "explanation": "Sidebar items are only shown if the user's RBAC group has the corresponding permission (dot-notation like 'collections.view')."},
            {"id": str(uuid4()), "question": "Which tabs are available on an Outsourcing Partner's profile?", "options": ["Only Profile and Billing", "Profile, Notes, Agreements, Pricing, Billing, Work Logs, Escalations", "Profile, Chat, Documents", "Profile and Settings only"], "correct_answer": 1, "explanation": "A partner profile has 7 tabs: Profile, Notes, Agreements, Pricing, Billing, Work Logs, and Escalations."},
            {"id": str(uuid4()), "question": "What happens when a client's FCRA case is submitted to the Attorney Marketplace?", "options": ["It is assigned to a random attorney", "Attorneys receive notifications and can place bids", "The client contacts attorneys directly", "It is sent to an external legal service"], "correct_answer": 1, "explanation": "Cases go to the Attorney Marketplace where attorneys receive notifications and place competitive bids."},
            {"id": str(uuid4()), "question": "What is the revenue split when an Attorney Marketplace case settles?", "options": ["50% / 50%", "40% Credlocity / 60% referring company", "60% Credlocity / 40% referring company", "70% Credlocity / 30% referring company"], "correct_answer": 1, "explanation": "The revenue split is 40% Credlocity and 60% for the referring company when a case settles."},
            {"id": str(uuid4()), "question": "Which chat systems does Credlocity provide?", "options": ["Only customer support chat", "Internal Chat and Customer Support Chat", "Email only", "Video conferencing"], "correct_answer": 1, "explanation": "Credlocity provides both Internal Chat (team communication with DMs, groups, departments) and Customer Support Chat (live chat with customers, chatbot, knowledge base)."},
            {"id": str(uuid4()), "question": "What does the public chat widget capture from visitors?", "options": ["Credit card info", "Social security number", "Name and email for lead creation", "Phone number only"], "correct_answer": 2, "explanation": "The chat widget captures visitor name and email to create leads, then starts a live chat session."},
            {"id": str(uuid4()), "question": "What SEO features does the content management system support?", "options": ["Only meta titles", "Meta title, meta description, canonical URL, Open Graph, robots directives, schema markup", "No SEO features", "Only keyword tags"], "correct_answer": 1, "explanation": "Full SEO support includes meta title/description, canonical URLs, Open Graph images, robots directives, and Schema.org structured data."},
            {"id": str(uuid4()), "question": "How is the Training Center structured?", "options": ["Video lessons only", "Modules with steps, quizzes, certificates, and assignments", "PDF downloads only", "External training links"], "correct_answer": 1, "explanation": "Training modules contain step-by-step guides, can include quizzes with a passing score, generate PDF certificates, and support assignments to employees or departments."},
            {"id": str(uuid4()), "question": "What is the maximum collection fee waiver for Tier 1 (Payment in Full)?", "options": ["$50", "$75", "$100", "$125"], "correct_answer": 3, "explanation": "For Tier 1 (Payment in Full), the maximum collection fee waiver is $125."},
            {"id": str(uuid4()), "question": "Where can an admin manage user groups and permissions?", "options": ["Team Management", "Site Settings", "Admin > Access Control", "Security page"], "correct_answer": 2, "explanation": "RBAC group and permission management is done through Admin > Access Control in the sidebar."}
        ],
        "created_by": admin_id,
        "created_at": now,
        "updated_at": now
    }

    await db.training_quizzes.insert_one(quiz)
    quiz.pop("_id", None)
    print(f"[SEED] Seeded CMS Mastery training module with {len(quiz['questions'])} quiz questions")
