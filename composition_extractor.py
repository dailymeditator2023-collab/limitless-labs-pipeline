#!/usr/bin/env python3
"""
Limitless Labs — Composition Extractor

Extracts supplement composition from Amazon product images using GPT-4o Vision.
Falls back to brand websites if Amazon doesn't have label images.

Usage:
    python3 composition_extractor.py --limit 5
    python3 composition_extractor.py --product "Whole Truth"
    python3 composition_extractor.py --url "https://www.amazon.in/dp/B0CLB6K6Y6"
    python3 composition_extractor.py --retry-failed --limit 20
"""

import os
import sys
import json
import time
import random
import base64
import argparse
import logging
import requests
import re

from openai import OpenAI
from playwright.sync_api import sync_playwright

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN") or os.environ.get("AIRTABLE_PAT")

BASE_ID = "appUOcZUDNPzstZlv"
PRODUCTS_TABLE = "tblttA4xVbWsAav0B"

AT_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ── Brand Website Mapping ────────────────────────────────────────────
BRAND_URLS = {
    "cosmix": "https://cosmix.in/",
    "the whole truth": "https://thewholetruthfoods.com/",
    "muscleblaze": "https://www.muscleblaze.com/",
    "oziva": "https://www.oziva.in/",
    "fast&up": "https://www.fastandup.in/",
    "healthkart": "https://www.healthkart.com/",
    "hk vitals": "https://www.hkvitals.com/",
    "swisse": "https://www.swisse.in/",
    "gnc": "https://www.gncindia.com/",
    "optimum nutrition": "https://www.optimumnutrition.in/",
    "nutrabay": "https://nutrabay.com/",
    "carbamide forte": "https://www.carbamideforte.com/",
    "boldfit": "https://www.boldfit.in/",
    "himalaya": "https://himalayawellness.in/",
    "solgar": "https://www.solgar.in/",
    "dymatize": "https://www.dymatize.in/",
    "nakpro": "https://www.nakpro.com/",
    "as-it-is": "https://www.asitisnutrition.com/",
    "bigmuscles": "https://www.bigmusclesnutrition.com/",
    "wellbeing nutrition": "https://www.wellbeingnutrition.com/",
    "myprotein": "https://www.myprotein.co.in/",
    "cellucor": "https://cellucor.com/",
    "now foods": "https://www.nowfoods.com/",
}

# ── OpenAI Client ────────────────────────────────────────────────────
client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# ── Amazon Image Extraction ──────────────────────────────────────────

def extract_label_images_amazon(amazon_url, max_images=10):
    """
    Visit Amazon product page, extract high-res image URLs from the gallery.
    Returns list of image URLs (not base64).
    Returns "AMAZON_404" string if product page is dead/delisted.
    PRIORITIZES thumbnails (which include nutrition labels) over main image.
    """
    log.info(f"  [Amazon] Visiting page...")
    
    image_urls = []
    seen_base_ids = set()
    
    def get_image_id(url):
        match = re.search(r'/images/I/([A-Za-z0-9]+)', url)
        return match.group(1) if match else url
    
    def is_amazon_404(page):
        """Detect Amazon soft 404 / product delisted pages"""
        # Check page title
        title = page.title().lower()
        if "page not found" in title or "404" in title:
            return True
        
        # Check for Amazon's soft 404 indicators
        page_text = page.content().lower()
        soft_404_indicators = [
            "we're sorry",
            "the web address you entered is not a functioning page",
            "looking for something?",
            "try checking the url for errors",
            "we can't find a match for",
            "sorry, we couldn't find that page",
        ]
        for indicator in soft_404_indicators:
            if indicator in page_text:
                return True
        
        # Check for the Amazon dog image (404 page mascot)
        dog_img = page.query_selector("img[alt*='dog']")
        if dog_img:
            # Only count as 404 if there's no product title
            product_title = page.query_selector("#productTitle")
            if not product_title:
                return True
        
        return False
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
        )
        page = context.new_page()
        
        try:
            page.goto(amazon_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            log.error(f"  [Amazon] Failed to load page: {e}")
            browser.close()
            return []
        
        # ─── Check for 404 / delisted product ───
        if is_amazon_404(page):
            log.warning(f"  [Amazon] Product page is 404 / delisted")
            browser.close()
            return "AMAZON_404"

        # ─── NEW: Parse ALL hiRes images from page source JSON ───
        # This gets hidden overflow images that thumbnails miss
        html = page.content()
        
        # Extract hiRes URLs from colorImages JSON in page source
        hiRes_pattern = r'"hiRes"\s*:\s*"(https://[^"]+)"'
        hiRes_matches = re.findall(hiRes_pattern, html)
        
        if hiRes_matches:
            log.info(f"  [Amazon] Found {len(hiRes_matches)} images in page source")
            for url in hiRes_matches:
                img_id = get_image_id(url)
                if img_id and img_id not in seen_base_ids:
                    seen_base_ids.add(img_id)
                    # Normalize to SL1500 for consistent quality
                    normalized = re.sub(r'\._SL\d+_\.', '._SL1500_.', url)
                    image_urls.append(normalized)
        
        # FALLBACK: Get thumbnails if JSON parsing failed
        if not image_urls:
            thumbnails = page.query_selector_all("#altImages .a-spacing-small.item img")
            log.info(f"  [Amazon] Fallback: Found {len(thumbnails)} thumbnail images")
            
            for thumb in thumbnails:
                try:
                    src = thumb.get_attribute("src")
                    if src and "images/I/" in src:
                        if "play-icon" in src or "PKdp-play" in src:
                            continue
                        hi_res = re.sub(r'\._[A-Z]{2}\d+_\.', '._SL1500_.', src)
                        hi_res = re.sub(r'\.SS\d+_.*?\.jpg', '._SL1500_.jpg', hi_res)
                        img_id = get_image_id(hi_res)
                        if img_id not in seen_base_ids:
                            seen_base_ids.add(img_id)
                            image_urls.append(hi_res)
                except:
                    continue
        
        # PRIORITY 2: Main image (only if we need more)
        if len(image_urls) < max_images:
            main_img = page.query_selector("#landingImage")
            if main_img:
                dynamic_data = main_img.get_attribute("data-a-dynamic-image")
                if dynamic_data:
                    try:
                        img_dict = json.loads(dynamic_data)
                        sorted_imgs = sorted(img_dict.items(), key=lambda x: x[1][0] * x[1][1], reverse=True)
                        if sorted_imgs:
                            url = sorted_imgs[0][0]
                            img_id = get_image_id(url)
                            if img_id not in seen_base_ids:
                                seen_base_ids.add(img_id)
                                image_urls.append(url)
                    except:
                        pass
        
        browser.close()
    
    log.info(f"  [Amazon] Found {len(image_urls)} unique product images")
    return image_urls[:max_images]


# ── Brand Website Image Extraction ───────────────────────────────────

def extract_label_images_brand_site(brand, product_name, max_images=12):
    """
    Search the brand's website for the product and extract images.
    Goes directly to brand site (no Google), uses their search.
    Returns list of base64 encoded images.
    
    STRICT 30s TIMEOUT for entire function.
    """
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Brand site took too long")
    
    brand_lower = brand.lower().strip()
    base_url = None
    
    for key, url in BRAND_URLS.items():
        if key in brand_lower or brand_lower in key:
            base_url = url
            break
    
    if not base_url:
        log.info(f"  [Brand] No URL mapped for: {brand}")
        return []
    
    log.info(f"  [Brand] Trying {base_url}...")
    
    # Build search URLs to try
    search_terms = product_name.replace(" ", "+")
    urls_to_try = [
        f"{base_url}search?q={search_terms}",
        f"{base_url}?s={search_terms}",
        f"{base_url}collections/all?q={search_terms}",
    ]
    
    images_base64 = []
    browser = None
    
    # Set 30s alarm for entire function
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                locale="en-IN",
            )
            context.set_default_timeout(8000)  # 8s max per operation
            page = context.new_page()
            
            # Block heavy resources
            page.route("**/*.{woff,woff2,ttf,otf,mp4,webm,gif,ogg}", lambda route: route.abort())
            page.route("**/analytics/**", lambda route: route.abort())
            page.route("**/tracking/**", lambda route: route.abort())
            page.route("**/facebook.**", lambda route: route.abort())
            page.route("**/google-analytics.**", lambda route: route.abort())
            
            product_page = None
            
            # Try each search URL pattern
            for url in urls_to_try:
                try:
                    log.info(f"  [Brand] Trying: {url[:50]}...")
                    page.goto(url, wait_until="domcontentloaded", timeout=8000)
                    time.sleep(1.5)
                    
                    # Look for product links
                    links = page.query_selector_all("a[href*='product'], a[href*='/p/'], a[href*='/sv/']")[:30]
                    name_words = [w for w in product_name.lower().split() if len(w) > 3]
                    
                    for link in links:
                        try:
                            href = link.get_attribute("href") or ""
                            text = (link.inner_text() or "").lower()[:100]
                            
                            if any(w in text or w in href.lower() for w in name_words):
                                product_page = href if href.startswith("http") else base_url.rstrip("/") + href
                                log.info(f"  [Brand] Found product: {product_page[:50]}...")
                                break
                        except:
                            continue
                    
                    if product_page:
                        break
                except Exception as e:
                    log.info(f"  [Brand] Search pattern failed: {str(e)[:40]}")
                    continue
            
            # If no product found, skip (don't waste time on homepage)
            if not product_page:
                log.info(f"  [Brand] No product page found, skipping")
                browser.close()
                signal.alarm(0)
                return []
            
            # Visit product page
            log.info(f"  [Brand] Visiting product page...")
            page.goto(product_page, wait_until="domcontentloaded", timeout=8000)
            log.info(f"  [Brand] Page loaded, sleeping 1.5s...")
            time.sleep(1.5)
            
            # Extract images from product page
            log.info(f"  [Brand] Finding images...")
            images = page.query_selector_all("img")[:25]
            log.info(f"  [Brand] Found {len(images)} img elements, processing...")
            seen_srcs = set()
            skip_patterns = ["logo", "icon", "badge", "star", "cart", "arrow", 
                           "svg", "spinner", "loading", "placeholder", "avatar",
                           "social", "facebook", "instagram", "twitter", "payment"]
            
            img_idx = 0
            for img in images:
                img_idx += 1
                log.info(f"  [Brand] Processing img {img_idx}/{len(images)}...")
                if len(images_base64) >= max_images:
                    log.info(f"  [Brand] Reached max images ({max_images}), stopping")
                    break
                try:
                    src = img.get_attribute("src") or ""
                    if len(src) < 10 or src in seen_srcs:
                        continue
                    if any(skip in src.lower() for skip in skip_patterns):
                        continue
                    seen_srcs.add(src)
                    
                    # Check size
                    box = img.bounding_box()
                    if not box or box["width"] < 100 or box["height"] < 100:
                        continue
                    
                    # Quick screenshot
                    screenshot_bytes = img.screenshot(timeout=3000)
                    if len(screenshot_bytes) > 5000:
                        images_base64.append({
                            "base64": base64.b64encode(screenshot_bytes).decode("utf-8"),
                        })
                        log.info(f"  [Brand] Captured img {img_idx}")
                except TimeoutError:
                    # Re-raise the signal timeout, don't catch it here
                    raise
                except Exception as e:
                    log.info(f"  [Brand] Img {img_idx} failed: {str(e)[:40]}")
                    continue
            
            browser.close()
            log.info(f"  [Brand] Found {len(images_base64)} images from product page")
            return images_base64
            
    except TimeoutError:
        log.error(f"  [Brand] Timeout after 30s")
        if browser:
            try:
                browser.close()
            except:
                pass
        return []
    except Exception as e:
        log.error(f"  [Brand] Error: {str(e)[:60]}")
        if browser:
            try:
                browser.close()
            except:
                pass
        return []
    finally:
        signal.alarm(0)  # Cancel timer


# ── GPT-4o Vision Extraction ─────────────────────────────────────────

def identify_and_extract_composition(images, brand="", product_name="", is_base64=False):
    """
    Send product images to GPT-4o vision.
    Ask it to find the supplement facts panel and extract composition.
    
    Args:
        images: List of image URLs (strings) or base64 dicts
        brand: Brand name for product match verification
        product_name: Product name for verification
        is_base64: If True, images are base64 encoded dicts
    """
    if not images:
        return None
    
    if not client:
        raise RuntimeError("OpenAI client not initialized - check OPENAI_API_KEY")
    
    log.info(f"  Sending {len(images)} images to GPT-4o Vision...")
    
    # Build the prompt
    prompt_text = f"""These are product images from a supplement listing.

TASK:
1. Find the image(s) that show the Supplement Facts panel, Nutrition Label, or Ingredient List
2. Extract the COMPLETE composition in the EXACT format below

⚠️ CRITICAL: Return ONLY the ingredient data in the specified format. 
No preamble, no explanation, no introductory text like "Here's the extracted information".
Start your response directly with "SERVING SIZE:" — nothing before it.

FORMAT (follow exactly):

SERVING SIZE: [e.g., 1 scoop (30g)]
SERVINGS PER CONTAINER: [e.g., 30]

PER SERVING:
- [Ingredient Name]: [Amount with unit]
- [Ingredient Name]: [Amount with unit]
...

OTHER INGREDIENTS: [list if visible]

ALLERGEN INFO: [if visible]

PRODUCT MATCH CHECK:
- Expected: {brand} — {product_name}
- Actual product on label: [what the label says]
- MATCH: YES or NO
(If NO, explain the mismatch)

INGREDIENT WARNINGS:
⚠️ [Ingredient] — [Who should be careful] — [Why]
Flag: allergens (lactose, soy, gluten), stimulants (caffeine dose), artificial sweeteners (sucralose, acesulfame-K), artificial colors, maltodextrin, amino spiking, banned substances.
If nothing concerning: "No specific warnings."

NOTES:
- If you can't find a nutrition/supplement facts label, say "NO LABEL FOUND"
- Include % Daily Value if shown
- Be precise with units (mg, mcg, g, IU, etc.)
- Include proprietary blend details if shown
- If multiple labels visible, extract from the most complete one
"""
    
    content = [{"type": "text", "text": prompt_text}]
    
    # Add images
    for img in images:
        if is_base64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img['base64']}",
                    "detail": "high"
                }
            })
        else:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": img,
                    "detail": "high"
                }
            })
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2500,
            messages=[{"role": "user", "content": content}]
        )
        
        composition = response.choices[0].message.content
        return composition
        
    except Exception as e:
        log.error(f"  GPT-4o Vision error: {e}")
        return None


# ── Airtable Helpers ─────────────────────────────────────────────────

def fetch_products_needing_composition(limit=10):
    """Get products that have Amazon URL but no Product Composition"""
    resp = requests.get(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}",
        headers=AT_HEADERS,
        params={
            "filterByFormula": "AND({Amazon URL} != '', {Product Composition} = '')",
            "maxRecords": limit
        }
    )
    if resp.status_code != 200:
        log.error(f"Failed to fetch products: {resp.text[:200]}")
        return []
    return resp.json().get("records", [])


def fetch_products_no_label_found(limit=10):
    """Get products where previous extraction returned NO_LABEL_FOUND"""
    resp = requests.get(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}",
        headers=AT_HEADERS,
        params={
            "filterByFormula": "AND({Amazon URL} != '', FIND('NO LABEL', {Product Composition}) > 0)",
            "maxRecords": limit
        }
    )
    if resp.status_code != 200:
        log.error(f"Failed to fetch products: {resp.text[:200]}")
        return []
    return resp.json().get("records", [])


def search_product(query):
    """Search for a specific product by name"""
    formula = f"SEARCH(LOWER('{query.lower()}'), LOWER({{Product Name}}))"
    resp = requests.get(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}",
        headers=AT_HEADERS,
        params={"filterByFormula": formula, "maxRecords": 1}
    )
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        return records[0] if records else None
    return None


def update_product_composition(record_id, composition):
    """Save composition to Airtable"""
    resp = requests.patch(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}/{record_id}",
        headers=AT_HEADERS,
        json={"fields": {"Product Composition": composition}}
    )
    if resp.status_code != 200:
        log.error(f"Airtable update failed: {resp.text[:200]}")
        return False
    return True


def update_product_status(record_id, status):
    """Update Review Status field in Airtable (e.g., for delisted products)"""
    resp = requests.patch(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}/{record_id}",
        headers=AT_HEADERS,
        json={"fields": {"Review Status": status}}
    )
    if resp.status_code != 200:
        log.error(f"Airtable status update failed: {resp.text[:200]}")
        return False
    log.info(f"  Updated Airtable status → {status}")
    return True


# ── Main Processing ──────────────────────────────────────────────────

def extract_composition_for_product(record=None, url=None, dry_run=False, try_brand_fallback=True):
    """
    Extract composition for a single product.
    Tries Amazon first, then brand website if Amazon fails.
    """
    
    if record:
        fields = record["fields"]
        product_id = record["id"]
        name = fields.get("Product Name", "Unknown")
        brand = fields.get("Brand", "Unknown")
        amazon_url = fields.get("Amazon URL", "")
        
        log.info(f"Extracting composition: {brand} — {name}")
    else:
        amazon_url = url
        product_id = None
        name = "Unknown"
        brand = "Unknown"
        log.info(f"Extracting composition from URL: {url}")
    
    if not amazon_url:
        log.error("  No Amazon URL provided")
        return False
    
    composition = None
    source = None
    
    # ─── Step 1: Try Amazon ───
    log.info("  [1/2] Trying Amazon...")
    amazon_images = extract_label_images_amazon(amazon_url)
    
    # Handle Amazon 404 / delisted product
    if amazon_images == "AMAZON_404":
        log.warning(f"  ✗ Amazon product page is 404 / delisted — skipping")
        if not dry_run and product_id:
            # Mark in composition field so we don't retry
            update_product_composition(
                product_id, 
                "AMAZON_404 — Product page is delisted or unavailable. Checked: " + 
                time.strftime("%Y-%m-%d %H:%M")
            )
        return False
    
    if amazon_images:
        composition = identify_and_extract_composition(
            amazon_images, brand=brand, product_name=name, is_base64=False
        )
        
        if composition and "NO LABEL FOUND" not in composition.upper():
            source = "Amazon"
    
    # ─── Step 2: Try Brand Website (fallback) ───
    if try_brand_fallback and (not composition or "NO LABEL FOUND" in composition.upper()):
        log.info(f"  [2/2] Amazon failed → trying {brand} website...")
        brand_images = extract_label_images_brand_site(brand, name)
        
        if brand_images:
            brand_composition = identify_and_extract_composition(
                brand_images, brand=brand, product_name=name, is_base64=True
            )
            
            if brand_composition and "NO LABEL FOUND" not in brand_composition.upper():
                composition = brand_composition
                source = "Brand Website"
    
    # ─── Handle results ───
    if not composition or "NO LABEL FOUND" in composition.upper():
        log.warning("  ✗ No label found on Amazon OR brand website")
        
        if not dry_run and product_id:
            update_product_composition(
                product_id, 
                "NO_LABEL_FOUND — checked Amazon and brand website"
            )
        return False
    
    log.info(f"  ✓ Composition extracted from {source} ({len(composition)} chars)")
    
    # Preview
    preview = composition[:200].replace('\n', ' ')
    log.info(f"  Preview: {preview}...")
    
    if dry_run:
        log.info("  [DRY RUN] Would save to Airtable")
        print("\n" + "="*60)
        print(f"EXTRACTED COMPOSITION (from {source}):")
        print("="*60)
        print(composition)
        return True
    
    # Save to Airtable
    if product_id:
        if update_product_composition(product_id, composition):
            log.info(f"  ✓ Saved to Airtable")
            return True
        else:
            log.error(f"  ✗ Failed to save to Airtable")
            return False
    else:
        print("\n" + "="*60)
        print(f"EXTRACTED COMPOSITION (from {source}):")
        print("="*60)
        print(composition)
        return True


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Limitless Labs Composition Extractor")
    parser.add_argument("--product", help="Extract for a specific product by name")
    parser.add_argument("--url", help="Extract from a specific Amazon URL (no Airtable save)")
    parser.add_argument("--limit", type=int, default=5, help="Max products to process")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't save to Airtable")
    parser.add_argument("--retry-failed", action="store_true", 
                        help="Retry products that previously returned NO_LABEL_FOUND")
    parser.add_argument("--amazon-only", action="store_true",
                        help="Skip brand website fallback")
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    if args.url:
        extract_composition_for_product(
            url=args.url, 
            dry_run=True,
            try_brand_fallback=not args.amazon_only
        )
        return

    if not AIRTABLE_TOKEN:
        log.error("AIRTABLE_TOKEN environment variable not set.")
        sys.exit(1)

    if args.product:
        log.info(f"Searching for product: {args.product}")
        record = search_product(args.product)
        if not record:
            log.error(f"Product not found: {args.product}")
            sys.exit(1)
        products = [record]
    elif args.retry_failed:
        log.info("Fetching products with NO_LABEL_FOUND...")
        products = fetch_products_no_label_found(args.limit)
    else:
        log.info("Fetching products needing composition extraction...")
        products = fetch_products_needing_composition(args.limit)

    if not products:
        log.info("No products to process.")
        return

    log.info(f"Found {len(products)} product(s) to process.\n")

    success = 0
    failed = 0

    for i, record in enumerate(products, 1):
        log.info(f"[{i}/{len(products)}]")
        if extract_composition_for_product(
            record, 
            dry_run=args.dry_run,
            try_brand_fallback=not args.amazon_only
        ):
            success += 1
        else:
            failed += 1
        
        if i < len(products):
            delay = random.uniform(3, 6)
            log.info(f"  Waiting {delay:.1f}s before next product...")
            time.sleep(delay)

    log.info("\n" + "="*50)
    log.info(f"Done. {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
