"""
Auto-seed content data and demo accounts on startup if collections are empty.
This ensures FAQs, reviews, authors, blog posts, pages, education hub,
and demo user accounts persist across container restarts.

Only seeds a collection if it's empty — won't overwrite existing data.
"""
import json
import os
import uuid
import bcrypt
from pathlib import Path
from datetime import datetime, timezone

SEED_DIR = Path(__file__).parent / "seed_data"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def seed_content(db):
    """Seed all content collections if they're empty."""

    collections_to_seed = [
        {"collection": "faq_categories", "file": "faq_categories.json", "name": "FAQ Categories"},
        {"collection": "faqs", "file": "faqs.json", "name": "FAQs"},
        {"collection": "reviews", "file": "reviews.json", "name": "Reviews"},
        {"collection": "authors", "file": "authors.json", "name": "Authors"},
        {"collection": "blog_posts", "file": "blog_posts.json", "name": "Blog Posts"},
        {"collection": "pages", "file": "pages.json", "name": "Pages"},
        {"collection": "education_hub", "file": "education_hub.json", "name": "Education Hub"},
    ]

    seeded_any = False

    for cfg in collections_to_seed:
        coll = db[cfg["collection"]]
        count = await coll.count_documents({})

        if count > 0:
            print(f"  ✓ {cfg['name']}: already has {count} documents, skipping")
            continue

        data_file = SEED_DIR / cfg["file"]
        if not data_file.exists():
            print(f"  ⚠ {cfg['name']}: seed file {cfg['file']} not found, skipping")
            continue

        with open(data_file) as f:
            items = json.load(f)

        if isinstance(items, dict):
            items = [items]

        if not items:
            print(f"  ⚠ {cfg['name']}: seed file is empty, skipping")
            continue

        for item in items:
            item.pop("_id", None)
            if "created_at" not in item:
                item["created_at"] = datetime.now(timezone.utc).isoformat()

        await coll.insert_many(items)
        seeded_any = True
        print(f"  ✅ {cfg['name']}: seeded {len(items)} documents")

    if not seeded_any:
        print("  Content already populated, no seeding needed.")

    return seeded_any


async def seed_demo_accounts(db):
    """Seed demo user accounts for all roles if they don't exist."""
    from auth import get_password_hash

    now = datetime.now(timezone.utc)
    password = "Credit123!"

    # --- CMS Users (editor, author, viewer) ---
    cms_users = [
        {
            "id": str(uuid.uuid4()),
            "email": "editor@credlocity.com",
            "hashed_password": get_password_hash(password),
            "full_name": "Demo Editor",
            "role": "editor",
            "is_active": True,
            "department": "Content",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "email": "author@credlocity.com",
            "hashed_password": get_password_hash(password),
            "full_name": "Demo Author",
            "role": "author",
            "is_active": True,
            "department": "Content",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "email": "viewer@credlocity.com",
            "hashed_password": get_password_hash(password),
            "full_name": "Demo Viewer",
            "role": "viewer",
            "is_active": True,
            "department": "Support",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    ]

    for user in cms_users:
        existing = await db.users.find_one({"email": user["email"]})
        if not existing:
            await db.users.insert_one(user)
            print(f"  ✅ CMS user: {user['email']} ({user['role']})")
        else:
            print(f"  ✓ CMS user: {user['email']} already exists")

    # --- Attorney ---
    att_email = "attorney@credlocity.com"
    existing_att = await db.attorneys.find_one({"email": att_email})
    if not existing_att:
        attorney = {
            "id": str(uuid.uuid4()),
            "email": att_email,
            "full_name": "James Mitchell, Esq.",
            "password_hash": _hash_password(password),
            "phone": "(555) 123-4567",
            "bar_number": "BAR-2024-001",
            "state": "California",
            "firm_name": "Mitchell Legal Group",
            "firm_address": "456 Legal Ave",
            "firm_city": "Los Angeles",
            "firm_state": "CA",
            "firm_zip": "90001",
            "practice_areas": ["credit repair", "consumer protection", "FDCPA"],
            "years_experience": 12,
            "bio": "Consumer protection attorney specializing in credit repair and FDCPA cases.",
            "status": "approved",
            "commission_rate": 0.15,
            "referral_code": f"ATT-{str(uuid.uuid4())[:8].upper()}",
            "cases_assigned": 0,
            "cases_resolved": 0,
            "total_earnings": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        await db.attorneys.insert_one(attorney)
        print(f"  ✅ Attorney: {att_email}")
    else:
        print(f"  ✓ Attorney: {att_email} already exists")

    # --- Outsourcing Partner ---
    partner_email = "partner@credlocity.com"
    existing_partner = await db.outsourcing_partners.find_one({"email": partner_email})
    if not existing_partner:
        partner = {
            "id": str(uuid.uuid4()),
            "company_name": "Demo Credit Solutions",
            "contact_first_name": "Maria",
            "contact_last_name": "Garcia",
            "contact_email": partner_email,
            "email": partner_email,
            "hashed_password": _hash_password(password),
            "phone": "(555) 987-6543",
            "status": "active",
            "is_active": True,
            "services": ["bureau_letters", "dispute_processing"],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        await db.outsourcing_partners.insert_one(partner)
        print(f"  ✅ Partner: {partner_email}")
    else:
        print(f"  ✓ Partner: {partner_email} already exists")
