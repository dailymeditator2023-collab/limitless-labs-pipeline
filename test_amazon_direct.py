#!/usr/bin/env python3
"""
Test Amazon scraping via direct browser (Mac Mini) with Chrome's logged-in session.
Uses real product URLs from Airtable.
"""

import time
import logging

from amazon_reviews_playwright import scrape_reviews_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("test-amazon")

# 5 real products from our Airtable (verified working URLs)
TEST_PRODUCTS = [
    ("Fast&Up Activate", "https://www.amazon.in/dp/B0B6WBKSPM"),
    ("MuscleBlaze MB-Vite", "https://www.amazon.in/dp/B08TC9Z9KR"),
    ("OZiva Brain", "https://www.amazon.in/dp/B09HSNPFCB"),
    ("MuscleBlaze Omega 3", "https://www.amazon.in/dp/B08KZTVPC6"),
    ("Healthkart Vitamin D3", "https://www.amazon.in/dp/B0CL6KR49W"),
]

def main():
    log.info("=" * 60)
    log.info("DIRECT BROWSER AMAZON SCRAPER TEST")
    log.info("Using Chrome's logged-in session for full access")
    log.info("=" * 60)
    
    start_time = time.time()
    
    # Use batch function for efficiency (single browser session)
    results = scrape_reviews_batch(TEST_PRODUCTS, delay_range=(3, 5))
    
    total_time = time.time() - start_time
    
    # Summary
    log.info("\n" + "=" * 60)
    log.info("RESULTS SUMMARY")
    log.info("=" * 60)
    
    success_count = 0
    for name, data in results:
        success = bool(data.get("star_distribution") or data.get("top_praised"))
        if success:
            success_count += 1
        
        status = "✓" if success else "✗"
        stars = data.get("star_distribution", "")[:30] or "no histogram"
        praised = data.get("top_praised", "")[:25] or "no data"
        log.info(f"  {status} {name[:25]}: {stars} | {praised}")
    
    log.info(f"\nSuccess rate: {success_count}/{len(results)}")
    log.info(f"Total time: {total_time:.1f}s (avg {total_time/len(results):.1f}s per product)")
    
    log.info("\n" + "=" * 60)
    if success_count == len(results):
        log.info("🎉 ALL PRODUCTS SCRAPED SUCCESSFULLY!")
        log.info("Direct browser + Chrome session works!")
        log.info("Can replace Apify — saving $49/month")
    elif success_count >= 4:
        log.info(f"👍 Excellent success rate ({success_count}/{len(results)})")
        log.info("Direct browser approach is viable")
    elif success_count >= 3:
        log.info(f"👍 Good success rate ({success_count}/{len(results)})")
    else:
        log.info(f"⚠️ Low success rate ({success_count}/{len(results)})")
        log.info("Investigate failures")
    log.info("=" * 60)

if __name__ == "__main__":
    main()
