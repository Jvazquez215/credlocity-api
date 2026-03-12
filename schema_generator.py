"""
Schema.org JSON-LD Generator for SEO
Automatically generates structured data for Google
"""
from datetime import datetime
from typing import Dict, List, Optional
import json


def generate_article_schema(post: dict, site_settings: dict = None, base_url: str = "https://credlocity.com") -> dict:
    """
    Generate Article or BlogPosting schema
    https://schema.org/Article
    """
    # Determine article type
    article_type = "NewsArticle" if post.get("is_news") else "BlogPosting"
    
    # Build schema
    schema = {
        "@context": "https://schema.org",
        "@type": article_type,
        "headline": post.get("title", ""),
        "description": post.get("excerpt", ""),
        "url": f"{base_url}/blog/{post.get('slug', '')}",
        "datePublished": post.get("publish_date", post.get("created_at", "")),
        "dateModified": post.get("updated_at", ""),
        "author": generate_author_schema(post, site_settings, base_url),
        "publisher": generate_organization_schema(site_settings, base_url)
    }
    
    # Add image if available
    if post.get("featured_image_url"):
        schema["image"] = {
            "@type": "ImageObject",
            "url": post["featured_image_url"],
            "width": 1200,
            "height": 630
        }
    
    # Add keywords from SEO
    if post.get("seo") and post["seo"].get("keywords"):
        keywords = post["seo"]["keywords"]
        if isinstance(keywords, list):
            schema["keywords"] = ", ".join(keywords)
        else:
            schema["keywords"] = keywords
    
    # Add categories
    if post.get("categories"):
        schema["articleSection"] = post["categories"]
    
    # Add word count if available
    if post.get("content"):
        word_count = len(post["content"].split())
        schema["wordCount"] = word_count
    
    # Add updates/corrections if present
    if post.get("updates") and len(post["updates"]) > 0:
        # Add correction/update information
        critical_updates = [u for u in post["updates"] if u.get("type") == "critical_update"]
        if critical_updates:
            schema["correction"] = []
            for update in critical_updates:
                schema["correction"].append({
                    "@type": "CorrectionComment",
                    "text": update.get("explanation", ""),
                    "datePublished": update.get("date", "")
                })
    
    # Add disclosures to schema (for transparency & E-E-A-T)
    disclosures = post.get("disclosures", {})
    if disclosures and isinstance(disclosures, dict):
        disclosure_text = []
        
        # YMYL disclosure
        if disclosures.get("ymyl_enabled") and disclosures.get("ymyl_content"):
            disclosure_text.append(f"YMYL Content Notice: {disclosures['ymyl_content'][:200]}...")
        
        # Competitor disclosure
        if disclosures.get("competitor_disclosure_enabled") and disclosures.get("competitor_disclosure_content"):
            disclosure_text.append(f"Competitor Disclosure: {disclosures['competitor_disclosure_content'][:200]}...")
        
        # Corrections policy
        if disclosures.get("corrections_enabled") and disclosures.get("corrections_content"):
            disclosure_text.append(f"Corrections Policy: {disclosures['corrections_content'][:200]}...")
        
        # Pseudonym/source protection
        if disclosures.get("pseudonym_enabled"):
            disclosure_text.append("Source Protection: Some names have been changed to protect privacy.")
        
        if disclosure_text:
            schema["abstract"] = " | ".join(disclosure_text)
            schema["isAccessibleForFree"] = True
            schema["isPartOf"] = {
                "@type": "WebSite",
                "name": "Credlocity",
                "url": base_url
            }
    
    # Add reference to pricing page if mentioned
    schema["offers"] = {
        "@type": "AggregateOffer",
        "url": f"{base_url}/pricing",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock"
    }
    
    return schema


def generate_author_schema(post: dict, site_settings: dict = None, base_url: str = "https://credlocity.com") -> dict:
    """
    Generate Person schema for author (uses full author profile data)
    https://schema.org/Person
    """
    author = {
        "@type": "Person",
        "name": post.get("author_name", "Credlocity Team"),
        "url": f"{base_url}/team/{post.get('author_slug', '')}"
    }
    
    # Add job title
    if post.get("author_title"):
        author["jobTitle"] = post["author_title"]
    
    # Add credentials (awards/certifications)
    if post.get("author_credentials") and len(post["author_credentials"]) > 0:
        author["award"] = post["author_credentials"]
    
    # Add experience & bio
    if post.get("author_experience"):
        author["yearsExperience"] = post["author_experience"]
    
    if post.get("author_bio"):
        author["description"] = post["author_bio"]
    
    # Add education
    if post.get("author_education") and len(post["author_education"]) > 0:
        author["alumniOf"] = []
        for edu in post["author_education"]:
            if isinstance(edu, dict):
                author["alumniOf"].append({
                    "@type": "EducationalOrganization",
                    "name": edu.get("institution", ""),
                    "description": edu.get("degree", "")
                })
    
    # Add publications/media features
    if post.get("author_publications") and len(post["author_publications"]) > 0:
        author["sameAs"] = []
        for pub in post["author_publications"]:
            if isinstance(pub, dict) and pub.get("url"):
                author["sameAs"].append(pub["url"])
    
    # Add photo
    if post.get("author_photo_url"):
        author["image"] = {
            "@type": "ImageObject",
            "url": post["author_photo_url"]
        }
    
    # Add author's affiliation (organization from site settings)
    if site_settings:
        org_name = site_settings.get("organization_name", "Credlocity")
        author["worksFor"] = {
            "@type": "Organization",
            "name": org_name,
            "url": base_url
        }
    
    return author


def generate_breadcrumb_schema(post: dict, base_url: str = "https://credlocity.com") -> dict:
    """
    Generate BreadcrumbList schema
    https://schema.org/BreadcrumbList
    """
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": base_url
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Blog",
                "item": f"{base_url}/blog"
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": post.get("title", ""),
                "item": f"{base_url}/blog/{post.get('slug', '')}"
            }
        ]
    }


def generate_faq_schema(faqs: List[dict]) -> dict:
    """
    Generate FAQPage schema
    https://schema.org/FAQPage
    """
    if not faqs:
        return None
    
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq.get("question", ""),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq.get("answer", "")
                }
            }
            for faq in faqs
        ]
    }


def generate_webpage_schema(page_data: dict, base_url: str = "https://credlocity.com") -> dict:
    """
    Generate WebPage schema
    https://schema.org/WebPage
    """
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": page_data.get("title", ""),
        "description": page_data.get("description", ""),
        "url": page_data.get("url", base_url),
        "publisher": {
            "@type": "Organization",
            "name": "Credlocity",
            "url": base_url
        }
    }


def generate_organization_schema(site_settings: dict = None, base_url: str = "https://credlocity.com") -> dict:
    """
    Generate Organization schema (pulls from site settings)
    https://schema.org/Organization
    """
    if not site_settings:
        # Fallback if no settings provided
        return {
            "@type": "Organization",
            "name": "Credlocity",
            "url": base_url,
            "logo": {
                "@type": "ImageObject",
                "url": f"{base_url}/logo.png"
            }
        }
    
    org_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site_settings.get("organization_name", "Credlocity"),
        "url": base_url,
        "description": site_settings.get("default_meta_description", "Credit Repair and Financial Education"),
        "foundingDate": "2008"
    }
    
    # Add logo
    logo_url = site_settings.get("organization_logo") or site_settings.get("logo_url")
    if logo_url:
        org_schema["logo"] = {
            "@type": "ImageObject",
            "url": logo_url if logo_url.startswith("http") else f"{base_url}{logo_url}"
        }
    
    # Add contact information
    if site_settings.get("organization_phone"):
        org_schema["telephone"] = site_settings["organization_phone"]
    
    if site_settings.get("organization_email"):
        org_schema["email"] = site_settings["organization_email"]
    
    # Add address
    address = site_settings.get("organization_address")
    if address and isinstance(address, dict):
        org_schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": address.get("street", ""),
            "addressLocality": address.get("city", ""),
            "addressRegion": address.get("state", ""),
            "postalCode": address.get("zip", ""),
            "addressCountry": address.get("country", "US")
        }
    
    # Add social media profiles
    social = site_settings.get("social_profiles", {})
    if social and isinstance(social, dict):
        same_as = []
        for platform, url in social.items():
            if url:
                same_as.append(url)
        if same_as:
            org_schema["sameAs"] = same_as
    
    return org_schema


def generate_all_schemas(post: dict, site_settings: dict = None, include_faq: bool = False, faqs: List[dict] = None) -> str:
    """
    Generate all applicable schemas for a blog post
    Returns JSON-LD script tag content as array
    """
    schemas = []
    
    # Article schema (required)
    schemas.append(generate_article_schema(post, site_settings))
    
    # Author schema (separate for viewing/editing)
    if post.get("author_name"):
        schemas.append(generate_author_schema(post, site_settings))
    
    # Organization schema (separate for viewing/editing)
    if site_settings:
        schemas.append(generate_organization_schema(site_settings))
    
    # Breadcrumb schema
    schemas.append(generate_breadcrumb_schema(post))
    
    # FAQ schema if applicable
    if include_faq and faqs:
        faq_schema = generate_faq_schema(faqs)
        if faq_schema:
            schemas.append(faq_schema)
    
    # Return as JSON string for script tag
    return json.dumps(schemas, indent=2, ensure_ascii=False)


def validate_schema(schema: dict) -> tuple[bool, str]:
    """
    Basic validation of schema structure
    Returns (is_valid, error_message)
    """
    try:
        # Check required fields
        if "@context" not in schema:
            return False, "Missing @context"
        if "@type" not in schema:
            return False, "Missing @type"
        
        # Validate it's valid JSON
        json.dumps(schema)
        
        return True, "Valid"
    except Exception as e:
        return False, str(e)



def generate_pricing_schema(pricing_data: List[dict], site_settings: dict = None, base_url: str = "https://credlocity.com") -> dict:
    """
    Generate schema for pricing/service offerings
    Uses Product + Offer pattern for each pricing plan
    https://schema.org/Product
    https://schema.org/Offer
    """
    offers = []
    
    for plan in pricing_data:
        # Create an Offer for each plan
        offer = {
            "@type": "Offer",
            "name": plan.get("name", ""),
            "price": plan.get("price", "").replace("$", "").replace(",", ""),
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
            "url": f"{base_url}/pricing",
            "priceValidUntil": "2025-12-31",
            "seller": generate_organization_schema(site_settings, base_url)
        }
        
        # Add trial period if available
        if plan.get("trial"):
            offer["eligibleDuration"] = {
                "@type": "QuantitativeValue",
                "value": plan.get("trial_days", 30),
                "unitCode": "DAY"
            }
        
        # Add description from features
        if plan.get("features"):
            offer["description"] = ", ".join(plan["features"][:5])  # First 5 features
        
        offers.append(offer)
    
    # Create the main Service schema with multiple offers
    schema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Credit Repair Service",
        "name": "Credlocity Credit Repair Plans",
        "description": "Professional credit repair services with transparent pricing and no hidden fees",
        "provider": generate_organization_schema(site_settings, base_url),
        "areaServed": {
            "@type": "Country",
            "name": "United States"
        },
        "offers": offers
    }
    
    # Add aggregate offer info
    prices = [float(plan.get("price", "0").replace("$", "").replace(",", "")) for plan in pricing_data if plan.get("price")]
    if len(prices) > 1:
        schema["offers"] = {
            "@type": "AggregateOffer",
            "priceCurrency": "USD",
            "lowPrice": min(prices),
            "highPrice": max(prices),
            "offerCount": len(pricing_data),
            "offers": offers
        }
    
    return schema

