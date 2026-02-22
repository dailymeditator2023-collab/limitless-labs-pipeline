#!/usr/bin/env python3
"""
Amazon Scraper using Apify API
Uses the junglee/free-amazon-product-scraper actor for reliable scraping.
"""

import os
import re
import json
import time
import logging
import requests

log = logging.getLogger("apify-amazon")

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ACTOR_ID = "junglee~free-amazon-product-scraper"


def scrape_amazon_product_apify(amazon_url: str = None, search_term: str = None, timeout_secs: int = 120) -> dict:
    """
    Scrape an Amazon product using Apify.
    Can either search by product name or extract ASIN from URL.
    Returns product data including star breakdown.
    """
    if not APIFY_TOKEN:
        log.error("APIFY_TOKEN not set")
        return {}
    
    # Build search URL
    if search_term:
        # Use search URL format
        search_url = f"https://www.amazon.in/s?k={requests.utils.quote(search_term)}"
    elif amazon_url:
        # Extract ASIN and search for it
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", amazon_url)
        if not asin_match:
            asin_match = re.search(r"/product/([A-Z0-9]{10})", amazon_url)
        if asin_match:
            asin = asin_match.group(1)
            search_url = f"https://www.amazon.in/s?k={asin}"
        else:
            log.warning(f"Could not extract ASIN from: {amazon_url}")
            return {}
    else:
        log.error("Either amazon_url or search_term required")
        return {}
    
    # Start the actor run
    log.info(f"Starting Apify actor with search: {search_url}")
    
    run_input = {
        "categoryUrls": [{"url": search_url}],
        "maxResults": 5,  # Get top 5 results to find the right product
    }
    
    headers = {
        "Authorization": f"Bearer {APIFY_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # Start the run
    start_resp = requests.post(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs",
        headers=headers,
        json=run_input,
        timeout=30,
    )
    
    if start_resp.status_code != 201:
        log.error(f"Failed to start actor: {start_resp.status_code} - {start_resp.text[:200]}")
        return {}
    
    run_data = start_resp.json().get("data", {})
    run_id = run_data.get("id")
    
    if not run_id:
        log.error("No run ID returned")
        return {}
    
    log.info(f"Run started: {run_id}")
    
    # Poll for completion
    start_time = time.time()
    while time.time() - start_time < timeout_secs:
        status_resp = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            headers=headers,
            timeout=30,
        )
        
        if status_resp.status_code != 200:
            log.warning(f"Status check failed: {status_resp.status_code}")
            time.sleep(5)
            continue
        
        run_status = status_resp.json().get("data", {})
        status = run_status.get("status")
        
        log.info(f"Run status: {status}")
        
        if status == "SUCCEEDED":
            break
        elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
            log.error(f"Run failed with status: {status}")
            return {}
        
        time.sleep(5)
    else:
        log.error("Timeout waiting for run to complete")
        return {}
    
    # Get results
    dataset_id = run_status.get("defaultDatasetId")
    if not dataset_id:
        log.error("No dataset ID found")
        return {}
    
    results_resp = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        headers=headers,
        timeout=30,
    )
    
    if results_resp.status_code != 200:
        log.error(f"Failed to get results: {results_resp.status_code}")
        return {}
    
    items = results_resp.json()
    if not items:
        log.warning("No items returned")
        return {}
    
    log.info(f"Got {len(items)} product(s) from Apify")
    
    # If we searched by ASIN, look for exact match
    if amazon_url:
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", amazon_url)
        if asin_match:
            target_asin = asin_match.group(1)
            for item in items:
                if item.get("asin") == target_asin:
                    log.info(f"Found exact ASIN match: {target_asin}")
                    return item
    
    # Return first result
    return items[0] if items else {}


def scrape_amazon_reviews_apify(amazon_url: str) -> dict:
    """
    Scrape Amazon product and extract review sentiment data.
    Uses the Apify Amazon scraper.
    
    Returns dict with sentiment fields for the research pipeline.
    """
    result = {
        "star_distribution": "",
        "top_praised": "",
        "top_complaints": "",
        "recurring_themes": "",
        "suspicious_pattern": "",
        "helpful_reviews_raw": "",
        "top_pros": "",
        "top_cons": "",
        "rating": 0.0,
        "review_count": 0,
        "title": "",
        "price": "",
        "brand": "",
    }
    
    product_data = scrape_amazon_product_apify(amazon_url)
    
    if not product_data:
        log.warning("No product data returned from Apify")
        return result
    
    # Extract basic product info
    result["title"] = product_data.get("title", "")
    result["price"] = product_data.get("price", "")
    result["brand"] = product_data.get("brand", "")
    result["rating"] = float(product_data.get("stars", 0) or 0)
    result["review_count"] = int(product_data.get("reviewsCount", 0) or 0)
    
    log.info(f"Product: {result['title'][:50]}...")
    log.info(f"Rating: {result['rating']}★ ({result['review_count']} reviews)")
    
    # Extract star distribution if available
    star_dist = product_data.get("starsBreakdown", {})
    if star_dist:
        dist_parts = []
        for stars in [5, 4, 3, 2, 1]:
            pct = star_dist.get(str(stars), 0)
            if pct:
                dist_parts.append(f"{pct}% {stars}-star")
        result["star_distribution"] = ", ".join(dist_parts)
        log.info(f"Star distribution: {result['star_distribution']}")
    
    # Extract reviews if available
    reviews = product_data.get("reviews", [])
    if reviews:
        log.info(f"Found {len(reviews)} reviews")
        
        pros = []
        cons = []
        theme_keywords = {
            "taste": ["taste", "flavor", "flavour", "chocolate", "vanilla", "delicious", "bland"],
            "mixability": ["mix", "blend", "lumps", "clumps", "dissolve", "shaker"],
            "digestion": ["digest", "stomach", "bloat", "gas", "heavy"],
            "results": ["gains", "muscle", "strength", "recovery", "energy", "results"],
            "value": ["price", "value", "expensive", "cheap", "worth", "money"],
            "quality": ["quality", "authentic", "genuine", "fake", "original"],
        }
        theme_counts = {k: 0 for k in theme_keywords}
        
        for rev in reviews:
            text = (rev.get("title", "") + " " + rev.get("text", "")).lower()
            stars = float(rev.get("stars", 3) or 3)
            
            # Count themes
            for theme, keywords in theme_keywords.items():
                if any(kw in text for kw in keywords):
                    theme_counts[theme] += 1
            
            if stars >= 4:
                pros.append(f"[{stars}★] {rev.get('title', '')}: {rev.get('text', '')[:150]}")
            elif stars <= 2:
                cons.append(f"[{stars}★] {rev.get('title', '')}: {rev.get('text', '')[:150]}")
        
        result["top_pros"] = " | ".join(pros[:5]) if pros else "No positive reviews"
        result["top_cons"] = " | ".join(cons[:3]) if cons else "No negative reviews"
        
        # Top themes
        top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        result["recurring_themes"] = ", ".join([f"{t[0]} ({t[1]} mentions)" for t in top_themes if t[1] > 0])
        
        # Extract praised/complaints
        praised = []
        complaints = []
        for rev in [r for r in reviews if float(r.get("stars", 3) or 3) >= 4][:10]:
            text = rev.get("text", "").lower()
            if any(kw in text for kw in ["taste", "flavor", "delicious"]):
                praised.append("Great taste")
            if any(kw in text for kw in ["mix", "dissolve"]):
                praised.append("Mixes well")
            if any(kw in text for kw in ["results", "gains", "effective"]):
                praised.append("Effective results")
        
        for rev in [r for r in reviews if float(r.get("stars", 3) or 3) <= 2][:10]:
            text = rev.get("text", "").lower()
            if any(kw in text for kw in ["fake", "duplicate", "not original"]):
                complaints.append("Authenticity concerns")
            if any(kw in text for kw in ["digest", "stomach", "bloat"]):
                complaints.append("Digestion issues")
            if any(kw in text for kw in ["taste", "awful"]):
                complaints.append("Poor taste")
        
        seen = set()
        result["top_praised"] = ", ".join([x for x in praised if not (x in seen or seen.add(x))][:3]) or "General satisfaction"
        seen = set()
        result["top_complaints"] = ", ".join([x for x in complaints if not (x in seen or seen.add(x))][:3]) or "Minor issues only"
        
        # Store raw for LLM
        result["helpful_reviews_raw"] = json.dumps(reviews[:10], ensure_ascii=False)[:5000]
    
    # Check for suspicious patterns
    suspicious = []
    if star_dist:
        five_star = star_dist.get("5", 0)
        one_star = star_dist.get("1", 0)
        if five_star > 85 and one_star < 5:
            suspicious.append(f"Unusually high 5-star ratio ({five_star}%)")
    
    if suspicious:
        result["suspicious_pattern"] = "⚠️ " + "; ".join(suspicious)
    else:
        result["suspicious_pattern"] = "No suspicious patterns detected"
    
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    # Test
    url = "https://www.amazon.in/dp/B07DWM6MRV"  # MuscleBlaze Biozyme
    print(f"\nTesting Apify scraper: {url}\n")
    
    result = scrape_amazon_reviews_apify(url)
    
    print(f"\nResults:")
    print(f"Title: {result['title'][:60]}...")
    print(f"Rating: {result['rating']}★ ({result['review_count']} reviews)")
    print(f"Star Distribution: {result['star_distribution']}")
    print(f"Top Praised: {result['top_praised']}")
    print(f"Top Complaints: {result['top_complaints']}")
    print(f"Recurring Themes: {result['recurring_themes']}")
    print(f"Suspicious: {result['suspicious_pattern']}")
