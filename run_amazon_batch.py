#!/usr/bin/env python3
"""
Overnight Amazon Review Scraping - Direct Browser
Processes all products using Chrome's logged-in session.
"""

import os
import sys
import time
import random
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"amazon_batch_{datetime.now().strftime('%Y%m%d_%H%M')}.log")
    ]
)
log = logging.getLogger("amazon-batch")

# Import after path setup
from amazon_reviews_playwright import ensure_chrome_profile, scrape_reviews_playwright

# Airtable config
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN") or os.environ.get("AIRTABLE_PAT")
AIRTABLE_BASE_ID = "appUOcZUDNPzstZlv"
TBL_PRODUCTS = "tblttA4xVbWsAav0B"
TBL_RAW_RESEARCH = "tblC8NLwWuBrw5507"

import requests

def get_products_with_amazon_urls(limit=50):
    """Fetch products that have Amazon URLs and need research."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_PRODUCTS}"
    params = {
        "maxRecords": limit,
        "filterByFormula": "{Amazon URL} != ''"  # All products with Amazon URLs
    }
    
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    
    products = []
    for rec in data.get("records", []):
        fields = rec.get("fields", {})
        amazon_url = fields.get("Amazon URL", "")
        if amazon_url and "amazon" in amazon_url.lower():
            products.append({
                "id": rec["id"],
                "name": fields.get("Product Name", "Unknown"),
                "amazon_url": amazon_url,
            })
    
    return products


def update_product_price(product_id: str, price: float):
    """Update the Products table with price data."""
    if not price:
        return
    
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    update_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_PRODUCTS}/{product_id}"
    fields = {"MRP (₹)": price}
    
    try:
        requests.patch(update_url, headers=headers, json={"fields": fields})
        log.info(f"    Updated product price: ₹{price}")
    except Exception as e:
        log.warning(f"    Failed to update price: {e}")


def update_raw_research(product_id: str, review_data: dict, airtable):
    """Update the Raw Research table with review data."""
    # Find or create raw research record for this product
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Also update product price if available
    if review_data.get("price"):
        update_product_price(product_id, review_data["price"])
    
    # Search for existing record
    search_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_RAW_RESEARCH}"
    params = {"filterByFormula": f"FIND('{product_id}', ARRAYJOIN({{Product}}))"}
    
    resp = requests.get(search_url, headers=headers, params=params)
    records = resp.json().get("records", [])
    
    fields = {
        "Amazon Star Distribution": review_data.get("star_distribution", ""),
        "Amazon Top Praised": review_data.get("top_praised", ""),
        "Amazon Top Complaints": review_data.get("top_complaints", ""),
        "Amazon Recurring Themes": review_data.get("recurring_themes", ""),
        "Amazon Suspicious Pattern": review_data.get("suspicious_pattern", ""),
        "Amazon Helpful Reviews": review_data.get("helpful_reviews_raw", "")[:10000],
    }
    
    if records:
        # Update existing
        record_id = records[0]["id"]
        update_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_RAW_RESEARCH}/{record_id}"
        requests.patch(update_url, headers=headers, json={"fields": fields})
        log.info(f"    Updated Raw Research record")
    else:
        # Create new
        fields["Product"] = [product_id]
        create_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_RAW_RESEARCH}"
        requests.post(create_url, headers=headers, json={"fields": fields})
        log.info(f"    Created Raw Research record")


def main():
    log.info("=" * 70)
    log.info("AMAZON REVIEW BATCH SCRAPER - OVERNIGHT RUN")
    log.info("Using Chrome's logged-in session for full access")
    log.info("=" * 70)
    
    # Get products
    products = get_products_with_amazon_urls(limit=50)
    log.info(f"Found {len(products)} products to process")
    
    if not products:
        log.info("No products to process. Exiting.")
        return
    
    # Setup browser with Chrome profile
    log.info("Setting up browser with Chrome session...")
    profile_dir = ensure_chrome_profile()
    
    p = sync_playwright().start()
    browser_context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        viewport={'width': 1920, 'height': 1080},
        locale='en-IN',
    )
    
    results = {"success": 0, "failed": 0, "skipped": 0}
    start_time = time.time()
    
    try:
        for i, product in enumerate(products, 1):
            log.info(f"\n[{i}/{len(products)}] {product['name']}")
            log.info(f"  URL: {product['amazon_url']}")
            
            try:
                review_data = scrape_reviews_playwright(
                    product['amazon_url'],
                    browser_context=browser_context
                )
                
                if review_data.get("top_praised") or review_data.get("star_distribution"):
                    log.info(f"  ✓ Success: {review_data.get('top_praised', 'no themes')[:50]}")
                    results["success"] += 1
                    
                    # Update Airtable
                    try:
                        update_raw_research(product['id'], review_data, None)
                    except Exception as e:
                        log.warning(f"  Airtable update failed: {e}")
                else:
                    log.warning(f"  ✗ No data extracted")
                    results["failed"] += 1
                
            except Exception as e:
                log.error(f"  ✗ Error: {e}")
                results["failed"] += 1
            
            # Delay between products
            if i < len(products):
                delay = random.uniform(3, 6)
                log.info(f"  Waiting {delay:.1f}s...")
                time.sleep(delay)
    
    finally:
        browser_context.close()
        p.stop()
    
    # Summary
    elapsed = time.time() - start_time
    log.info("\n" + "=" * 70)
    log.info("BATCH COMPLETE")
    log.info("=" * 70)
    log.info(f"Total products: {len(products)}")
    log.info(f"Success: {results['success']}")
    log.info(f"Failed: {results['failed']}")
    log.info(f"Total time: {elapsed/60:.1f} minutes ({elapsed/len(products):.1f}s avg)")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
