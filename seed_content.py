"""
Auto-seed content data on startup if collections are empty.
This ensures FAQs, reviews, authors, blog posts, pages, and education hub
data persist across container restarts (embedded MongoDB loses data on restart).

Only seeds a collection if it's empty — won't overwrite existing data.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

SEED_DIR = Path(__file__).parent / "seed_data"


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
            # Single document (like education_hub settings)
            items = [items]

        if not items:
            print(f"  ⚠ {cfg['name']}: seed file is empty, skipping")
            continue

        # Clean MongoDB-specific fields that might cause conflicts
        for item in items:
            item.pop("_id", None)
            # Add created_at if not present
            if "created_at" not in item:
                item["created_at"] = datetime.now(timezone.utc).isoformat()

        await coll.insert_many(items)
        seeded_any = True
        print(f"  ✅ {cfg['name']}: seeded {len(items)} documents")

    if not seeded_any:
        print("  Content already populated, no seeding needed.")

    return seeded_any
