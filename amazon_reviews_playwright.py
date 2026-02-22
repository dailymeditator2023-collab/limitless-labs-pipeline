#!/usr/bin/env python3
"""
Amazon Review Scraper using Playwright
Uses Chrome's logged-in session for full access to reviews.
"""

import os
import re
import json
import time
import shutil
import random
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

log = logging.getLogger("amazon-reviews")

# Chrome profile paths
CHROME_PROFILE_SOURCE = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
CHROME_PROFILE_COPY = "/tmp/chrome-amazon-scraper"


def ensure_chrome_profile():
    """Copy Chrome profile if not already copied (for logged-in session)."""
    if not os.path.exists(CHROME_PROFILE_COPY):
        log.info("Copying Chrome profile for Amazon session...")
        shutil.copytree(CHROME_PROFILE_SOURCE, CHROME_PROFILE_COPY, dirs_exist_ok=True)
    return CHROME_PROFILE_COPY


def scrape_reviews_playwright(amazon_url: str, max_reviews: int = 15, browser_context=None) -> dict:
    """
    Scrape Amazon reviews using Playwright (real browser).
    Gets most helpful reviews, star distribution, and sentiment data.
    
    Args:
        amazon_url: Amazon product URL
        max_reviews: Maximum reviews to extract
        browser_context: Optional existing browser context (for batch processing)
    
    Returns dict with all sentiment data.
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
        "price": None,  # Amazon price in INR
        "price_per_unit": None,  # Price per unit if shown
    }
    
    # Extract ASIN
    asin_match = re.search(r"/dp/([A-Z0-9]{10})", amazon_url)
    if not asin_match:
        asin_match = re.search(r"/product/([A-Z0-9]{10})", amazon_url)
    if not asin_match:
        log.warning("Could not extract ASIN from URL")
        return result
    
    asin = asin_match.group(1)
    product_url = f"https://www.amazon.in/dp/{asin}"
    
    all_reviews = []
    star_counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    review_dates = []
    
    # Track if we created the browser
    own_browser = browser_context is None
    p = None
    page = None
    
    try:
        # Create browser if not provided
        if own_browser:
            p = sync_playwright().start()
            profile_dir = ensure_chrome_profile()
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
                viewport={'width': 1920, 'height': 1080},
                locale='en-IN',
            )
        
        page = browser_context.new_page()
        
        log.info(f"  Loading product page: {product_url}")
        page.goto(product_url, wait_until='domcontentloaded', timeout=45000)
        
        # Wait for page to settle + scroll to trigger lazy loading
        time.sleep(random.uniform(3, 5))
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
        time.sleep(random.uniform(2, 3))
        
        # Check for captcha
        if page.query_selector('input[name="captcha"]') or 'captcha' in page.url.lower():
            log.warning("  Captcha detected")
            return result
        
        # Check for sign-in redirect
        if 'signin' in page.url.lower() or 'sign-in' in page.title().lower():
            log.warning("  Redirected to sign-in page")
            return result
        
        # Extract price
        try:
            price_selectors = [
                '#corePriceDisplay_desktop_feature_div .a-price-whole',
                '#corePrice_desktop .a-price-whole',
                '.a-price-whole',
                '#priceblock_ourprice',
                '#priceblock_dealprice',
            ]
            for selector in price_selectors:
                price_el = page.query_selector(selector)
                if price_el:
                    price_text = price_el.inner_text().replace(',', '').replace('₹', '').strip()
                    if price_text:
                        try:
                            result["price"] = float(price_text.split('.')[0])
                            log.info(f"  Price: ₹{result['price']}")
                            break
                        except ValueError:
                            pass
            
            # Try to get unit price (e.g., "₹1.50 per gram")
            unit_price_el = page.query_selector('.a-price-per-unit, [data-a-strike="true"]')
            if unit_price_el:
                result["price_per_unit"] = unit_price_el.inner_text().strip()
        except Exception as e:
            log.warning(f"  Could not extract price: {e}")
        
        # Extract star distribution from histogram
        try:
            # Try new Amazon layout first
            histogram_el = page.query_selector('#cm_cr_dp_d_rating_histogram')
            if histogram_el:
                text = histogram_el.inner_text()
                # Parse "5 star 56% 4 star 23%..." pattern
                for star in [5, 4, 3, 2, 1]:
                    pattern = rf'{star}\s*star\s*(\d+)%'
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        star_counts[star] = int(match.group(1))
            
            # Fallback to old layout
            if not any(star_counts.values()):
                histogram_rows = page.query_selector_all('#histogramTable tr, [data-hook="rating-distribution"] tr')
                for row in histogram_rows:
                    text = row.inner_text()
                    for star in [5, 4, 3, 2, 1]:
                        if f"{star} star" in text.lower():
                            pct_match = re.search(r'(\d+)%', text)
                            if pct_match:
                                star_counts[star] = int(pct_match.group(1))
                                break
            
            if any(star_counts.values()):
                dist_parts = [f"{pct}% {star}-star" for star, pct in sorted(star_counts.items(), reverse=True) if pct > 0]
                result["star_distribution"] = ", ".join(dist_parts)
                log.info(f"  Star distribution: {result['star_distribution']}")
        except Exception as e:
            log.warning(f"  Could not extract star distribution: {e}")
        
        # Scroll down to load more reviews
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(random.uniform(1, 2))
        
        # Extract reviews
        review_elements = page.query_selector_all('[data-hook="review"]')
        log.info(f"  Found {len(review_elements)} reviews on page")
        
        for rev_el in review_elements[:max_reviews]:
            try:
                # Star rating
                stars = 0
                star_el = rev_el.query_selector('[data-hook="review-star-rating"] .a-icon-alt, [data-hook="cmps-review-star-rating"] .a-icon-alt')
                if star_el:
                    match = re.search(r'(\d+\.?\d*)', star_el.inner_text())
                    if match:
                        stars = float(match.group(1))
                
                # Review date
                review_date = ""
                date_el = rev_el.query_selector('[data-hook="review-date"]')
                if date_el:
                    date_text = date_el.inner_text()
                    date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', date_text)
                    if date_match:
                        review_date = date_match.group(1)
                        review_dates.append(review_date)
                
                # Title
                title = ""
                title_el = rev_el.query_selector('[data-hook="review-title"] span:not(.a-icon-alt)')
                if title_el:
                    title = title_el.inner_text()[:100]
                
                # Body
                body = ""
                body_el = rev_el.query_selector('[data-hook="review-body"] span')
                if body_el:
                    body = body_el.inner_text()[:500]
                
                # Helpful count
                helpful_count = 0
                helpful_el = rev_el.query_selector('[data-hook="helpful-vote-statement"]')
                if helpful_el:
                    helpful_match = re.search(r'(\d+)', helpful_el.inner_text())
                    if helpful_match:
                        helpful_count = int(helpful_match.group(1))
                
                if body:
                    all_reviews.append({
                        "stars": stars,
                        "title": title,
                        "body": body,
                        "date": review_date,
                        "helpful": helpful_count,
                    })
            
            except Exception as e:
                log.warning(f"  Error parsing review: {e}")
                continue
    
    except PlaywrightTimeout:
        log.warning("  Playwright timeout")
        return result
    except Exception as e:
        log.error(f"  Playwright error: {e}")
        return result
    finally:
        # Clean up
        if page:
            try:
                page.close()
            except:
                pass
        if own_browser and browser_context:
            try:
                browser_context.close()
            except:
                pass
        if own_browser and p:
            try:
                p.stop()
            except:
                pass
    
    if not all_reviews:
        log.warning("  No reviews extracted")
        return result
    
    log.info(f"  Extracted {len(all_reviews)} reviews")
    
    # Categorize reviews
    theme_keywords = {
        "taste": ["taste", "flavor", "flavour", "chocolate", "vanilla", "delicious", "bland", "sweet"],
        "mixability": ["mix", "mixability", "blend", "lumps", "clumps", "dissolve", "shaker"],
        "digestion": ["digest", "stomach", "bloat", "gas", "heavy", "light on stomach", "upset"],
        "results": ["gains", "muscle", "strength", "recovery", "energy", "results", "progress", "effective"],
        "value": ["price", "value", "expensive", "cheap", "worth", "money", "affordable"],
        "quality": ["quality", "authentic", "genuine", "fake", "original", "packaging"],
    }
    theme_counts = {k: 0 for k in theme_keywords}
    
    pros = []
    cons = []
    
    for rev in all_reviews:
        text = (rev["title"] + " " + rev["body"]).lower()
        
        for theme, keywords in theme_keywords.items():
            if any(kw in text for kw in keywords):
                theme_counts[theme] += 1
        
        if rev["stars"] >= 4:
            pros.append(f"[{rev['stars']}★] {rev['title']}: {rev['body'][:150]}")
        elif rev["stars"] <= 2:
            cons.append(f"[{rev['stars']}★] {rev['title']}: {rev['body'][:150]}")
    
    result["top_pros"] = " | ".join(pros[:5]) if pros else "No positive reviews scraped"
    result["top_cons"] = " | ".join(cons[:3]) if cons else "No negative reviews scraped"
    
    # Top praised themes (from 4-5 star reviews)
    praised_themes = []
    for rev in [r for r in all_reviews if r["stars"] >= 4][:10]:
        text = rev["body"].lower()
        if any(kw in text for kw in ["taste", "flavor", "delicious"]):
            praised_themes.append("Great taste")
        if any(kw in text for kw in ["mix", "dissolve", "blend"]):
            praised_themes.append("Mixes well")
        if any(kw in text for kw in ["results", "gains", "effective", "works"]):
            praised_themes.append("Effective results")
        if any(kw in text for kw in ["value", "price", "affordable", "worth"]):
            praised_themes.append("Good value")
        if any(kw in text for kw in ["quality", "genuine", "authentic"]):
            praised_themes.append("Good quality")
        if any(kw in text for kw in ["digest", "light on stomach", "no bloat"]):
            praised_themes.append("Easy to digest")
    
    seen = set()
    unique_praised = [x for x in praised_themes if not (x in seen or seen.add(x))]
    result["top_praised"] = ", ".join(unique_praised[:3]) if unique_praised else "General satisfaction"
    
    # Top complaints (from 1-2 star reviews)
    complaint_themes = []
    for rev in [r for r in all_reviews if r["stars"] <= 2][:10]:
        text = rev["body"].lower()
        if any(kw in text for kw in ["taste", "flavor", "awful", "bad taste"]):
            complaint_themes.append("Poor taste")
        if any(kw in text for kw in ["fake", "duplicate", "not original", "counterfeit"]):
            complaint_themes.append("Authenticity concerns")
        if any(kw in text for kw in ["digest", "stomach", "bloat", "gas", "heavy"]):
            complaint_themes.append("Digestion issues")
        if any(kw in text for kw in ["mix", "lumps", "clumps", "doesn't dissolve"]):
            complaint_themes.append("Mixability problems")
        if any(kw in text for kw in ["expensive", "overpriced", "not worth"]):
            complaint_themes.append("Overpriced")
        if any(kw in text for kw in ["no result", "doesn't work", "ineffective"]):
            complaint_themes.append("No results")
    
    seen = set()
    unique_complaints = [x for x in complaint_themes if not (x in seen or seen.add(x))]
    result["top_complaints"] = ", ".join(unique_complaints[:3]) if unique_complaints else "Minor issues only"
    
    # Recurring themes
    top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    result["recurring_themes"] = ", ".join([f"{t[0]} ({t[1]} mentions)" for t in top_themes if t[1] > 0])
    
    # Suspicious patterns
    suspicious = []
    
    if star_counts[5] > 85 and star_counts[1] < 5:
        suspicious.append(f"Unusually high 5-star ratio ({star_counts[5]}%)")
    
    if review_dates:
        from collections import Counter
        date_counts = Counter(review_dates)
        for date, count in date_counts.items():
            if count >= 3:
                suspicious.append(f"Review spike: {count} reviews on {date}")
    
    generic_count = sum(1 for r in all_reviews 
                        if r["stars"] >= 4 and len(r["body"]) < 50 
                        and any(kw in r["body"].lower() for kw in ["good", "nice", "best", "excellent"]))
    if generic_count >= 3:
        suspicious.append(f"{generic_count} suspiciously generic 5-star reviews")
    
    if suspicious:
        result["suspicious_pattern"] = "⚠️ " + "; ".join(suspicious)
    else:
        result["suspicious_pattern"] = "No suspicious patterns detected"
    
    # Raw reviews for LLM
    helpful_sorted = sorted(all_reviews, key=lambda x: x["helpful"], reverse=True)[:10]
    result["helpful_reviews_raw"] = json.dumps(helpful_sorted, ensure_ascii=False)[:5000]
    
    return result


def scrape_reviews_batch(urls: list, delay_range=(3, 5)) -> list:
    """
    Scrape multiple Amazon URLs efficiently with a single browser session.
    
    Args:
        urls: List of (name, amazon_url) tuples
        delay_range: (min, max) seconds to wait between products
    
    Returns:
        List of (name, result_dict) tuples
    """
    results = []
    profile_dir = ensure_chrome_profile()
    
    p = sync_playwright().start()
    browser_context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        viewport={'width': 1920, 'height': 1080},
        locale='en-IN',
    )
    
    try:
        for i, (name, url) in enumerate(urls):
            log.info(f"[{i+1}/{len(urls)}] Scraping: {name}")
            result = scrape_reviews_playwright(url, browser_context=browser_context)
            results.append((name, result))
            
            # Delay between products (except for last one)
            if i < len(urls) - 1:
                delay = random.uniform(*delay_range)
                log.info(f"  Waiting {delay:.1f}s...")
                time.sleep(delay)
    finally:
        browser_context.close()
        p.stop()
    
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    # Test with a single product
    url = "https://www.amazon.in/dp/B0B6WBKSPM"
    print(f"Testing: {url}")
    result = scrape_reviews_playwright(url)
    print(f"Star Distribution: {result['star_distribution']}")
    print(f"Top Praised: {result['top_praised']}")
    print(f"Top Complaints: {result['top_complaints']}")
    print(f"Recurring Themes: {result['recurring_themes']}")
    print(f"Suspicious Pattern: {result['suspicious_pattern']}")
    print(f"Reviews: {len(json.loads(result['helpful_reviews_raw'] or '[]'))}")
