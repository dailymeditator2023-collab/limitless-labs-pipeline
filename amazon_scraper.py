#!/usr/bin/env python3
"""
Limitless Labs — Amazon India Scraper (In-House)
=================================================
Uses Playwright (headless Chrome) to scrape Amazon.in product pages.
Free, no API key, no monthly limits.

Usage:
    python3 amazon_scraper.py --asin B09TF5BKGF
    python3 amazon_scraper.py --url "https://www.amazon.in/dp/B09TF5BKGF"
    python3 amazon_scraper.py --test   # Run test on sample ASIN

Requirements:
    pip install playwright
    playwright install chromium
"""

import re
import json
import time
import random
import logging
import argparse
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("amazon-scraper")


# ── Config ────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

AMAZON_IN_BASE = "https://www.amazon.in"


# ── ASIN Extraction ──────────────────────────────────────────────────

def extract_asin(url_or_asin: str) -> str:
    """Extract ASIN from URL or return as-is if already an ASIN."""
    if re.match(r'^[A-Z0-9]{10}$', url_or_asin):
        return url_or_asin
    match = re.search(r'/(?:dp|gp/product|product)/([A-Z0-9]{10})', url_or_asin)
    if match:
        return match.group(1)
    match = re.search(r'\b([A-Z0-9]{10})\b', url_or_asin)
    return match.group(1) if match else ""


# ── Core Scraper ─────────────────────────────────────────────────────

def scrape_amazon_product(asin: str, retries: int = 3) -> dict:
    """
    Scrape an Amazon.in product page using Playwright.
    Returns structured product data dict.
    """
    result = {
        "asin": asin,
        "title": "",
        "price": "",
        "mrp": "",
        "rating": 0.0,
        "rating_count": 0,
        "description": "",
        "feature_bullets": [],
        "ingredients_raw": "",
        "serving_size": "",
        "image_url": "",
        "availability": "",
        "brand": "",
        "product_info": {},
        "success": False,
        "error": "",
    }

    url = f"{AMAZON_IN_BASE}/dp/{asin}"

    for attempt in range(1, retries + 1):
        try:
            log.info(f"  Attempt {attempt}/{retries} — Fetching {url}")

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ]
                )

                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1366, "height": 768},
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    extra_http_headers={
                        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    }
                )

                # Block unnecessary resources for speed
                page = context.new_page()
                page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf}", lambda route: route.abort())
                page.route("**/analytics/**", lambda route: route.abort())
                page.route("**/beacon/**", lambda route: route.abort())

                # Navigate
                page.goto(url, wait_until="domcontentloaded", timeout=20000)

                # Random delay to mimic human
                time.sleep(random.uniform(1.5, 3.0))

                # Check for CAPTCHA
                if page.query_selector("#captchacharacters") or "robot" in page.title().lower():
                    log.warning(f"  CAPTCHA detected on attempt {attempt}")
                    browser.close()
                    time.sleep(random.uniform(5, 10))
                    continue

                # ── Extract data ──────────────────────────────────

                # Title
                title_el = page.query_selector("#productTitle")
                if title_el:
                    result["title"] = title_el.inner_text().strip()

                # Price
                price_el = (
                    page.query_selector(".a-price-whole") or
                    page.query_selector("#priceblock_ourprice") or
                    page.query_selector("#priceblock_dealprice") or
                    page.query_selector(".a-price .a-offscreen")
                )
                if price_el:
                    price_text = price_el.inner_text().strip()
                    result["price"] = "₹" + price_text.replace("₹", "").replace(",", "").strip().rstrip(".")

                # MRP (list price / strikethrough price)
                mrp_el = page.query_selector(".basisPrice .a-offscreen")
                if mrp_el:
                    result["mrp"] = mrp_el.inner_text().strip()
                else:
                    result["mrp"] = result["price"]

                # Rating
                rating_el = page.query_selector("#acrPopover .a-icon-alt")
                if rating_el:
                    match = re.search(r'([\d.]+)', rating_el.inner_text())
                    if match:
                        result["rating"] = float(match.group(1))

                # Rating count
                count_el = page.query_selector("#acrCustomerReviewText")
                if count_el:
                    match = re.search(r'([\d,]+)', count_el.inner_text())
                    if match:
                        result["rating_count"] = int(match.group(1).replace(",", ""))

                # Feature bullets
                bullets_el = page.query_selector_all("#feature-bullets ul li span.a-list-item")
                bullets = []
                for b in bullets_el:
                    text = b.inner_text().strip()
                    if text and len(text) > 5 and not text.startswith("›"):
                        bullets.append(text)
                result["feature_bullets"] = bullets

                # Description
                desc_el = page.query_selector("#productDescription")
                if desc_el:
                    result["description"] = desc_el.inner_text().strip()[:1000]

                # Brand
                brand_el = page.query_selector("#bylineInfo")
                if brand_el:
                    brand_text = brand_el.inner_text().strip()
                    brand_text = re.sub(r'^(Visit the |Brand: )', '', brand_text).rstrip(' Store')
                    result["brand"] = brand_text

                # Main image
                img_el = page.query_selector("#landingImage")
                if img_el:
                    result["image_url"] = img_el.get_attribute("src") or ""

                # Availability
                avail_el = page.query_selector("#availability span")
                if avail_el:
                    result["availability"] = avail_el.inner_text().strip()

                # Product information table
                info_rows = page.query_selector_all("#productDetails_techSpec_section_1 tr, #detailBullets_feature_div li")
                prod_info = {}
                for row in info_rows:
                    cells = row.query_selector_all("th, td")
                    if len(cells) == 2:
                        key = cells[0].inner_text().strip()
                        val = cells[1].inner_text().strip()
                        prod_info[key] = val
                    else:
                        # Detail bullets format
                        text = row.inner_text().strip()
                        if ":" in text:
                            parts = text.split(":", 1)
                            prod_info[parts[0].strip()] = parts[1].strip()

                result["product_info"] = prod_info

                # ── Build ingredients raw text ────────────────────

                ingredients_parts = []

                # Check bullets for ingredient/dose mentions
                ingredient_signals = [
                    "mg", "mcg", "iu", "protein", "caffeine", "creatine",
                    "ashwagandha", "theanine", "melatonin", "vitamin",
                    "mineral", "extract", "per serving", "per capsule",
                    "per scoop", "per tablet", "ingredient", "formula",
                    "contains", "blend", "amino", "bcaa", "omega",
                    "collagen", "probiotic", "biotin", "zinc", "iron",
                    "magnesium", "calcium", "folate", "dose", "clinical",
                    "whey", "casein", "isolate", "concentrate",
                ]

                for bullet in bullets:
                    if any(sig in bullet.lower() for sig in ingredient_signals):
                        ingredients_parts.append(bullet)

                # Check description
                if result["description"]:
                    desc_lower = result["description"].lower()
                    if any(sig in desc_lower for sig in ["ingredient", "per serving", "nutrition", "formula"]):
                        ingredients_parts.append(result["description"][:500])

                # Check product info for ingredient fields
                for key, val in prod_info.items():
                    if "ingredient" in key.lower() or "composition" in key.lower():
                        ingredients_parts.append(val)

                # Try to find ingredient section (some products have it)
                ing_section = page.query_selector("#important-information .content")
                if ing_section:
                    ing_text = ing_section.inner_text().strip()
                    if "ingredient" in ing_text.lower()[:50]:
                        ingredients_parts.append(ing_text[:500])

                # Also try the "Important Information" section
                imp_info = page.query_selector_all("#important-information h4, #important-information p, #important-information div.content")
                for el in imp_info:
                    text = el.inner_text().strip()
                    if any(sig in text.lower() for sig in ["ingredient", "direction", "composition"]):
                        ingredients_parts.append(text[:300])

                result["ingredients_raw"] = " | ".join(ingredients_parts)

                # Serving size from product info
                for key, val in prod_info.items():
                    if "serving" in key.lower() or "dose" in key.lower():
                        result["serving_size"] = val
                        break

                browser.close()

                # ── Validate ──────────────────────────────────────
                if result["title"]:
                    result["success"] = True
                    log.info(f"  ✓ {result['title'][:60]}...")
                    log.info(f"    Price: {result['price']} | Rating: {result['rating']} ({result['rating_count']} reviews)")
                    log.info(f"    Bullets: {len(bullets)} | Ingredients text: {len(result['ingredients_raw'])} chars")
                    log.info(f"    Brand: {result['brand']}")
                    return result
                else:
                    log.warning(f"  No title found on attempt {attempt}")

        except PlaywrightTimeout:
            log.warning(f"  Timeout on attempt {attempt}")
        except Exception as e:
            log.error(f"  Error on attempt {attempt}: {e}")
            result["error"] = str(e)

        # Back-off between retries
        if attempt < retries:
            wait = random.uniform(3, 8) * attempt
            log.info(f"  Waiting {wait:.1f}s before retry...")
            time.sleep(wait)

    log.error(f"  ✗ Failed after {retries} attempts for ASIN {asin}")
    return result


# ── Batch Scraper ────────────────────────────────────────────────────

def scrape_batch(asins: list, delay_range: tuple = (4, 8)) -> list:
    """
    Scrape multiple ASINs with random delays between requests.
    Returns list of result dicts.
    """
    results = []
    total = len(asins)

    for i, asin in enumerate(asins, 1):
        log.info(f"\n[{i}/{total}] Processing ASIN: {asin}")
        result = scrape_amazon_product(asin)
        results.append(result)

        # Random delay between products
        if i < total:
            delay = random.uniform(*delay_range)
            log.info(f"  Waiting {delay:.1f}s before next product...")
            time.sleep(delay)

    success = sum(1 for r in results if r["success"])
    log.info(f"\nDone. {success}/{total} products scraped successfully.")
    return results


# ── Integration: Drop-in replacement for research_agent.py ───────────

def scrape_amazon(url: str) -> dict:
    """
    Drop-in replacement for the research agent's scrape_amazon function.
    Takes a URL, returns the same dict format the pipeline expects.
    """
    asin = extract_asin(url) if url else ""
    if not asin:
        log.warning(f"  Could not extract ASIN from: {url}")
        return {
            "title": "", "price": "", "mrp": "", "rating": 0,
            "rating_count": 0, "description": "", "feature_bullets": [],
            "ingredients_raw": "", "serving_size": "", "image_url": "",
            "availability": "", "asin": "",
        }

    result = scrape_amazon_product(asin)

    # Return in the format the research agent expects
    return {
        "title": result["title"],
        "price": result["price"],
        "mrp": result["mrp"],
        "rating": result["rating"],
        "rating_count": result["rating_count"],
        "description": result["description"],
        "feature_bullets": result["feature_bullets"],
        "ingredients_raw": result["ingredients_raw"],
        "serving_size": result["serving_size"],
        "image_url": result["image_url"],
        "availability": result["availability"],
        "asin": result["asin"],
    }


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Amazon.in Product Scraper")
    parser.add_argument("--asin", help="Product ASIN to scrape")
    parser.add_argument("--url", help="Amazon URL to scrape")
    parser.add_argument("--test", action="store_true", help="Test with sample ASIN")
    parser.add_argument("--output", help="Output JSON file path")
    args = parser.parse_args()

    if args.test:
        # Test with a known supplement ASIN
        asin = "B09TF5BKGF"  # AS-IT-IS Caffeine + L-Theanine
        log.info(f"Testing with ASIN: {asin}")
    elif args.url:
        asin = extract_asin(args.url)
    elif args.asin:
        asin = args.asin
    else:
        parser.print_help()
        return

    if not asin:
        log.error("Could not determine ASIN")
        return

    result = scrape_amazon_product(asin)

    # Print results
    print("\n" + "=" * 60)
    print(f"ASIN:        {result['asin']}")
    print(f"Title:       {result['title']}")
    print(f"Brand:       {result['brand']}")
    print(f"Price:       {result['price']}")
    print(f"MRP:         {result['mrp']}")
    print(f"Rating:      {result['rating']} ({result['rating_count']} reviews)")
    print(f"Available:   {result['availability']}")
    print(f"Image:       {result['image_url'][:80]}...")
    print(f"\nBullets ({len(result['feature_bullets'])}):")
    for b in result['feature_bullets']:
        print(f"  • {b[:100]}")
    print(f"\nIngredients Raw ({len(result['ingredients_raw'])} chars):")
    print(f"  {result['ingredients_raw'][:300]}")
    print(f"\nProduct Info:")
    for k, v in result['product_info'].items():
        print(f"  {k}: {v}")
    print(f"\nSuccess: {result['success']}")
    print("=" * 60)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log.info(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
