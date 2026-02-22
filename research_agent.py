#!/usr/bin/env python3
"""
Limitless Labs — Research Agent (MVP)
=====================================
Scrapes Amazon.in, Reddit, and web sources for supplement product data.
Writes structured output to Airtable Raw Research table.

MVP version uses free tools:
- requests + BeautifulSoup for Amazon scraping
- requests for Reddit JSON API (no auth needed for public posts)
- DuckDuckGo for web research (lab testing, clinical data)

Designed to swap in Firecrawl/Apify/Perplexity later without changing
the pipeline structure.

Usage:
    python3 research_agent.py                    # Process all Queued products
    python3 research_agent.py --product "AS-IT-IS Whey"  # Process one product by name
    python3 research_agent.py --dry-run           # Scrape but don't write to Airtable
"""

import os
import sys
import json
import time
import re
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

import requests
from bs4 import BeautifulSoup
from amazon_scraper import scrape_amazon as scrape_amazon_playwright
from amazon_reviews_playwright import scrape_reviews_playwright, scrape_reviews_batch, ensure_chrome_profile

# ── Config ────────────────────────────────────────────────────────────

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appUOcZUDNPzstZlv"

# Table IDs
TBL_PRODUCTS      = "tblttA4xVbWsAav0B"
TBL_RAW_RESEARCH  = "tblC8NLwWuBrw5507"
TBL_AGENT_LOG     = "tblcZh2gT8fv99GTK"

AIRTABLE_API = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"

# Global browser context for Amazon scraping (set by batch runner)
BROWSER_CONTEXT = None

# Request headers — rotate user agents to avoid bot detection
import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

def get_amazon_headers():
    """Get headers with a random user agent to avoid bot detection."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.amazon.in/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

def random_delay(min_sec=2, max_sec=6):
    """Add a random delay to avoid bot detection patterns."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay

# Legacy constant for backwards compatibility
AMAZON_HEADERS = get_amazon_headers()

REDDIT_HEADERS = {
    "User-Agent": "LimitlessLabs-ResearchAgent/1.0 (research bot)",
}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("research-agent")


# ── Data Models ───────────────────────────────────────────────────────

@dataclass
class AmazonData:
    rating: float = 0.0
    review_count: int = 0
    price: float = 0.0
    title: str = ""
    brand: str = ""
    top_pros: str = ""
    top_cons: str = ""
    sentiment: str = ""  # Positive / Mixed / Negative
    ingredients_raw: str = ""
    serving_size: str = ""
    image_url: str = ""
    # Enhanced sentiment fields
    star_distribution: str = ""  # e.g., "78% 5-star, 12% 4-star, 5% 3-star, 2% 2-star, 3% 1-star"
    top_praised: str = ""  # Top 3 praised things
    top_complaints: str = ""  # Top 3 complaints  
    recurring_themes: str = ""  # Taste, mixability, digestion, results timeline
    suspicious_pattern: str = ""  # Fake review warning if detected
    helpful_reviews_raw: str = ""  # Raw helpful reviews for LLM analysis

@dataclass
class RedditData:
    sentiment: str = ""  # Positive / Mixed / Negative / Not Found
    summary: str = ""
    sources: list = field(default_factory=list)
    thread_count: int = 0
    # Enhanced sentiment fields
    recommendations: str = ""  # Do people recommend it?
    alternatives_mentioned: str = ""  # What alternatives do they suggest?
    red_flags: str = ""  # Any red flags mentioned
    community_consensus: str = ""  # Overall community take

@dataclass
class WebResearchData:
    lab_tested: bool = False
    lab_testing_body: str = ""
    lab_test_result: str = "Not Available"
    lab_test_url: str = ""
    label_transparency: str = ""
    clinical_summary: str = ""

@dataclass
class ResearchOutput:
    amazon: AmazonData = field(default_factory=AmazonData)
    reddit: RedditData = field(default_factory=RedditData)
    web: WebResearchData = field(default_factory=WebResearchData)
    data_completeness: str = "Minimal"
    research_date: str = ""
    scraped_by: str = "Research Agent MVP"


# ── Airtable Client ──────────────────────────────────────────────────

class AirtableClient:
    """Simple Airtable API wrapper."""

    def __init__(self, token: str, base_id: str):
        self.token = token
        self.base_url = f"https://api.airtable.com/v0/{base_id}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def list_records(self, table_id: str, formula: str = "", fields: list = None,
                     max_records: int = 100) -> list:
        """List records from a table with optional filter formula."""
        params = {"maxRecords": max_records}
        if formula:
            params["filterByFormula"] = formula
        if fields:
            for i, f in enumerate(fields):
                params[f"fields[{i}]"] = f

        records = []
        offset = None

        while True:
            if offset:
                params["offset"] = offset
            resp = requests.get(
                f"{self.base_url}/{table_id}",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
            time.sleep(0.2)  # Rate limit

        return records

    def create_record(self, table_id: str, fields: dict) -> dict:
        """Create a single record."""
        resp = requests.post(
            f"{self.base_url}/{table_id}",
            headers=self.headers,
            json={"fields": fields},
        )
        resp.raise_for_status()
        return resp.json()

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        """Update a single record."""
        resp = requests.patch(
            f"{self.base_url}/{table_id}/{record_id}",
            headers=self.headers,
            json={"fields": fields},
        )
        resp.raise_for_status()
        return resp.json()


# ── Amazon Scraper ────────────────────────────────────────────────────

def scrape_amazon(url: str) -> AmazonData:
    """
    Scrape an Amazon.in product page for key data.

    MVP: Uses requests + BeautifulSoup. Amazon may block aggressive scraping.
    UPGRADE: Replace with Firecrawl API call.
    """
    data = AmazonData()

    if not url or "amazon.in" not in url:
        log.warning(f"Invalid Amazon URL: {url}")
        return data

    try:
        log.info(f"Scraping Amazon: {url}")
        resp = requests.get(url, headers=AMAZON_HEADERS, timeout=15)

        if resp.status_code == 503:
            log.warning("Amazon returned 503 (bot detection). Retrying with delay...")
            time.sleep(3)
            resp = requests.get(url, headers=AMAZON_HEADERS, timeout=15)

        if resp.status_code != 200:
            log.error(f"Amazon returned {resp.status_code}")
            return data

        soup = BeautifulSoup(resp.text, "html.parser")

        # Product title
        title_el = soup.select_one("#productTitle")
        if title_el:
            data.title = title_el.get_text(strip=True)

        # Brand
        brand_el = soup.select_one("#bylineInfo") or soup.select_one("a#bylineInfo")
        if brand_el:
            brand_text = brand_el.get_text(strip=True)
            data.brand = brand_text.replace("Visit the ", "").replace(" Store", "").replace("Brand: ", "")

        # Price
        price_el = soup.select_one(".a-price .a-offscreen") or soup.select_one("#priceblock_ourprice")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_num = re.sub(r"[^\d.]", "", price_text)
            try:
                data.price = float(price_num)
            except ValueError:
                pass

        # Rating
        rating_el = soup.select_one("#acrPopover") or soup.select_one("span[data-hook='rating-out-of-text']")
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            match = re.search(r"(\d+\.?\d*)", rating_text)
            if match:
                data.rating = float(match.group(1))

        # Review count
        count_el = soup.select_one("#acrCustomerReviewText")
        if count_el:
            count_text = count_el.get_text(strip=True)
            count_num = re.sub(r"[^\d]", "", count_text)
            try:
                data.review_count = int(count_num)
            except ValueError:
                pass

        # Main image
        img_el = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
        if img_el:
            data.image_url = img_el.get("src", "") or img_el.get("data-old-hires", "")

        # Product description / ingredients from "About this item" or description
        about_items = soup.select("#feature-bullets .a-list-item")
        if about_items:
            bullet_texts = [li.get_text(strip=True) for li in about_items
                           if li.get_text(strip=True) and "See more" not in li.get_text()]
            data.ingredients_raw = " | ".join(bullet_texts[:10])

        # Try to get ingredient/nutrition info from product description
        desc_el = soup.select_one("#productDescription")
        if desc_el:
            desc_text = desc_el.get_text(strip=True)
            if any(kw in desc_text.lower() for kw in ["ingredient", "protein", "mg", "serving"]):
                if data.ingredients_raw:
                    data.ingredients_raw += " | DESCRIPTION: " + desc_text[:500]
                else:
                    data.ingredients_raw = desc_text[:500]

        # Technical details table (often has serving size)
        tech_rows = soup.select("#productDetails_techSpec_section_1 tr, #detailBullets_feature_div li")
        for row in tech_rows:
            text = row.get_text(strip=True).lower()
            if "serving" in text:
                data.serving_size = row.get_text(strip=True)

        # Determine sentiment from rating
        if data.rating >= 4.0:
            data.sentiment = "Positive"
        elif data.rating >= 3.0:
            data.sentiment = "Mixed"
        elif data.rating > 0:
            data.sentiment = "Negative"

        log.info(f"  → Title: {data.title[:60]}...")
        log.info(f"  → Rating: {data.rating} ({data.review_count} reviews)")
        log.info(f"  → Price: ₹{data.price}")

    except requests.RequestException as e:
        log.error(f"Amazon scrape failed: {e}")
    except Exception as e:
        log.error(f"Amazon parse error: {e}")

    return data


# ── Amazon Review Scraper (Enhanced) ──────────────────────────────────

def scrape_amazon_reviews_enhanced(url: str, max_pages: int = 3) -> dict:
    """
    Enhanced Amazon review scraper:
    - Gets top 10-15 most helpful reviews
    - Extracts star distribution
    - Detects suspicious review patterns (review spikes)
    - Categorizes themes (taste, mixability, digestion, results)

    Returns dict with all sentiment data.
    """
    result = {
        "top_pros": "",
        "top_cons": "",
        "star_distribution": "",
        "top_praised": "",
        "top_complaints": "",
        "recurring_themes": "",
        "suspicious_pattern": "",
        "helpful_reviews_raw": "",
    }

    # Extract ASIN from URL
    asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if not asin_match:
        asin_match = re.search(r"/product/([A-Z0-9]{10})", url)
    if not asin_match:
        log.warning("Could not extract ASIN from URL")
        return result

    asin = asin_match.group(1)

    all_reviews = []
    review_dates = []
    star_counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}

    # First, get the star distribution from the main reviews page
    try:
        main_url = f"https://www.amazon.in/product-reviews/{asin}?sortBy=helpful"
        random_delay(2, 5)  # Random delay before request
        resp = requests.get(main_url, headers=get_amazon_headers(), timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract star distribution from histogram
            histogram = soup.select("#histogramTable tr, [data-hook='rating-distribution'] tr")
            for row in histogram:
                text = row.get_text(strip=True)
                for star in [5, 4, 3, 2, 1]:
                    if f"{star} star" in text.lower():
                        pct_match = re.search(r"(\d+)%", text)
                        if pct_match:
                            star_counts[star] = int(pct_match.group(1))
                            break
    except Exception as e:
        log.warning(f"  Star distribution scrape failed: {e}")

    # Build star distribution string
    if any(star_counts.values()):
        dist_parts = [f"{pct}% {star}-star" for star, pct in sorted(star_counts.items(), reverse=True) if pct > 0]
        result["star_distribution"] = ", ".join(dist_parts)
        log.info(f"  → Star distribution: {result['star_distribution']}")

    # Scrape helpful reviews (sorted by helpfulness)
    for page in range(1, max_pages + 1):
        review_url = f"https://www.amazon.in/product-reviews/{asin}?sortBy=helpful&pageNumber={page}"

        try:
            delay = random_delay(3, 7)  # Random delay between pages
            log.info(f"  Scraping helpful reviews page {page}... (waited {delay:.1f}s)")
            resp = requests.get(review_url, headers=get_amazon_headers(), timeout=15)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            reviews = soup.select("[data-hook='review']")

            for rev in reviews:
                # Get star rating
                star_el = rev.select_one("[data-hook='review-star-rating'] .a-icon-alt, [data-hook='cmps-review-star-rating'] .a-icon-alt")
                stars = 0
                if star_el:
                    match = re.search(r"(\d+\.?\d*)", star_el.get_text())
                    if match:
                        stars = float(match.group(1))

                # Get review date
                date_el = rev.select_one("[data-hook='review-date']")
                review_date = ""
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    # Extract date (e.g., "Reviewed in India on 15 January 2024")
                    date_match = re.search(r"(\d{1,2}\s+\w+\s+\d{4})", date_text)
                    if date_match:
                        review_date = date_match.group(1)
                        review_dates.append(review_date)

                # Get review title
                title_el = rev.select_one("[data-hook='review-title']")
                title = title_el.get_text(strip=True) if title_el else ""

                # Get review text
                body_el = rev.select_one("[data-hook='review-body']")
                if not body_el:
                    continue
                body = body_el.get_text(strip=True)

                # Get helpful votes
                helpful_el = rev.select_one("[data-hook='helpful-vote-statement']")
                helpful_count = 0
                if helpful_el:
                    helpful_match = re.search(r"(\d+)", helpful_el.get_text())
                    if helpful_match:
                        helpful_count = int(helpful_match.group(1))

                all_reviews.append({
                    "stars": stars,
                    "title": title[:100],
                    "body": body[:500],
                    "date": review_date,
                    "helpful": helpful_count,
                })

        except Exception as e:
            log.warning(f"  Review scrape page {page} failed: {e}")
            break

    if not all_reviews:
        log.warning("  No reviews scraped")
        return result

    log.info(f"  → Scraped {len(all_reviews)} reviews")

    # Categorize reviews
    pros = []
    cons = []
    
    # Theme detection keywords
    theme_keywords = {
        "taste": ["taste", "flavor", "flavour", "chocolate", "vanilla", "delicious", "bland", "sweet"],
        "mixability": ["mix", "mixability", "blend", "lumps", "clumps", "dissolve", "shaker"],
        "digestion": ["digest", "stomach", "bloat", "gas", "heavy", "light on stomach", "upset"],
        "results": ["gains", "muscle", "strength", "recovery", "energy", "results", "progress", "effective"],
        "value": ["price", "value", "expensive", "cheap", "worth", "money", "affordable"],
        "quality": ["quality", "authentic", "genuine", "fake", "original", "packaging"],
    }
    theme_counts = {k: 0 for k in theme_keywords}

    for rev in all_reviews:
        text = (rev["title"] + " " + rev["body"]).lower()
        
        # Count themes
        for theme, keywords in theme_keywords.items():
            if any(kw in text for kw in keywords):
                theme_counts[theme] += 1

        # Categorize as pro or con
        if rev["stars"] >= 4:
            pros.append(f"[{rev['stars']}★] {rev['title']}: {rev['body'][:150]}")
        elif rev["stars"] <= 2:
            cons.append(f"[{rev['stars']}★] {rev['title']}: {rev['body'][:150]}")

    # Top pros and cons
    result["top_pros"] = " | ".join(pros[:5]) if pros else "No positive reviews scraped"
    result["top_cons"] = " | ".join(cons[:3]) if cons else "No negative reviews scraped"

    # Extract top praised things (from 4-5 star reviews)
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
    # Dedupe and take top 3
    seen = set()
    unique_praised = [x for x in praised_themes if not (x in seen or seen.add(x))]
    result["top_praised"] = ", ".join(unique_praised[:3]) if unique_praised else "General satisfaction"

    # Extract top complaints (from 1-2 star reviews)
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

    # Detect suspicious review patterns
    suspicious = []
    
    # Check 1: Very high % of 5-star reviews (>85%) with low 1-star (<5%) is suspicious
    if star_counts[5] > 85 and star_counts[1] < 5:
        suspicious.append(f"Unusually high 5-star ratio ({star_counts[5]}%)")
    
    # Check 2: Look for review date clustering (many reviews on same date)
    if review_dates:
        from collections import Counter
        date_counts = Counter(review_dates)
        for date, count in date_counts.items():
            if count >= 5:  # 5+ reviews on same date is suspicious
                suspicious.append(f"Review spike: {count} reviews on {date}")
    
    # Check 3: Very generic reviews in positive category
    generic_count = sum(1 for r in all_reviews 
                        if r["stars"] >= 4 and len(r["body"]) < 50 
                        and any(kw in r["body"].lower() for kw in ["good", "nice", "best", "excellent"]))
    if generic_count >= 5:
        suspicious.append(f"{generic_count} suspiciously generic 5-star reviews")

    if suspicious:
        result["suspicious_pattern"] = "⚠️ " + "; ".join(suspicious)
        log.warning(f"  → Suspicious patterns detected: {result['suspicious_pattern']}")
    else:
        result["suspicious_pattern"] = "No suspicious patterns detected"

    # Store raw helpful reviews for LLM analysis
    helpful_sorted = sorted(all_reviews, key=lambda x: x["helpful"], reverse=True)[:10]
    result["helpful_reviews_raw"] = json.dumps(helpful_sorted, ensure_ascii=False)[:5000]

    return result


# Legacy function for backwards compatibility
def scrape_amazon_reviews(url: str, max_pages: int = 2) -> tuple:
    """Legacy wrapper - calls enhanced version."""
    result = scrape_amazon_reviews_enhanced(url, max_pages)
    return result["top_pros"], result["top_cons"]


# ── Reddit Scraper (Enhanced) ─────────────────────────────────────────

def scrape_reddit(product_name: str, brand: str, category: str = "") -> RedditData:
    """
    Enhanced Reddit scraper:
    - Searches more relevant subreddits based on product category
    - Extracts recommendations, alternatives mentioned, and red flags
    - Provides honest assessment of community discussion availability

    MVP: Uses Reddit's .json endpoint (no OAuth needed for public posts).
    UPGRADE: Replace with Apify Reddit scraper.
    """
    data = RedditData()

    # Search queries — try product name, then brand + category
    queries = [
        f"{brand} {product_name}",
        f"{brand} supplement India",
        f"{brand} review",
    ]

    # Target subreddits based on category
    base_subreddits = ["indiasupplements", "IndianFitness", "Supplements"]
    
    # Add category-specific subreddits
    category_lower = (category or "").lower()
    if any(kw in category_lower for kw in ["collagen", "biotin", "skin", "hair"]):
        base_subreddits.extend(["IndianSkincareAddicts", "IndianHaircare"])
    if any(kw in category_lower for kw in ["nootropic", "brain", "focus", "cognitive"]):
        base_subreddits.extend(["Nootropics", "StackAdvice"])
    if any(kw in category_lower for kw in ["sleep", "melatonin"]):
        base_subreddits.extend(["sleep", "insomnia"])
    if any(kw in category_lower for kw in ["pre-workout", "energy", "caffeine"]):
        base_subreddits.extend(["preworkout"])
    
    # Dedupe subreddits
    subreddits = list(dict.fromkeys(base_subreddits))

    all_posts = []

    for query in queries:
        for sub in subreddits:
            try:
                search_url = (
                    f"https://www.reddit.com/r/{sub}/search.json"
                    f"?q={requests.utils.quote(query)}&restrict_sr=on&sort=relevance&limit=15"
                )
                log.info(f"  Reddit: r/{sub} → '{query}'")

                resp = requests.get(search_url, headers=REDDIT_HEADERS, timeout=10)

                if resp.status_code == 429:
                    log.warning("  Reddit rate limited, waiting 5s...")
                    time.sleep(5)
                    resp = requests.get(search_url, headers=REDDIT_HEADERS, timeout=10)

                if resp.status_code != 200:
                    continue

                result = resp.json()
                posts = result.get("data", {}).get("children", [])

                for post in posts:
                    pd = post.get("data", {})
                    all_posts.append({
                        "title": pd.get("title", ""),
                        "subreddit": pd.get("subreddit", ""),
                        "score": pd.get("score", 0),
                        "num_comments": pd.get("num_comments", 0),
                        "url": f"https://reddit.com{pd.get('permalink', '')}",
                        "selftext": (pd.get("selftext", "") or "")[:500],
                        "created": pd.get("created_utc", 0),
                    })

                time.sleep(1)  # Rate limit

            except Exception as e:
                log.warning(f"  Reddit search failed for r/{sub}: {e}")
                continue

    if not all_posts:
        data.sentiment = "Not Found"
        data.summary = "Limited community discussion available"
        data.community_consensus = "No Reddit discussions found for this product. This is common for newer or less popular brands."
        return data

    # Deduplicate by URL
    seen = set()
    unique_posts = []
    for p in all_posts:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique_posts.append(p)

    # Sort by engagement
    unique_posts.sort(key=lambda x: x["score"] + x["num_comments"], reverse=True)

    data.thread_count = len(unique_posts)
    data.sources = [p["url"] for p in unique_posts[:5]]

    # Build summary from top posts
    summaries = []
    for p in unique_posts[:5]:
        summaries.append(f"[r/{p['subreddit']}] {p['title']} (↑{p['score']}, {p['num_comments']} comments)")

    data.summary = " | ".join(summaries)

    # Analyze content for recommendations, alternatives, and red flags
    all_text = " ".join([p["title"] + " " + p["selftext"] for p in unique_posts]).lower()

    # Check if people recommend it
    recommend_positive = any(kw in all_text for kw in ["recommend", "worth it", "good choice", "great product", "love it", "best"])
    recommend_negative = any(kw in all_text for kw in ["don't recommend", "avoid", "waste of money", "not worth", "stay away", "scam"])
    
    if recommend_positive and not recommend_negative:
        data.recommendations = "Generally recommended by community"
    elif recommend_negative:
        data.recommendations = "Mixed or negative recommendations"
    else:
        data.recommendations = "No strong recommendations either way"

    # Extract alternatives mentioned
    alternative_brands = []
    alt_keywords = ["instead", "alternative", "better option", "try", "switched to", "prefer"]
    competitor_brands = ["muscleblaze", "myprotein", "optimum nutrition", "on", "dymatize", "isopure",
                         "asitis", "as-it-is", "fast&up", "oziva", "healthkart", "big muscles",
                         "gncin", "gnc", "amway", "nutrabay", "nakpro", "avvatar"]
    
    for brand_name in competitor_brands:
        if brand_name in all_text and brand_name.lower() != brand.lower():
            # Check if mentioned as alternative
            for p in unique_posts:
                text = (p["title"] + " " + p["selftext"]).lower()
                if brand_name in text and any(kw in text for kw in alt_keywords):
                    alternative_brands.append(brand_name.title())
                    break
    
    if alternative_brands:
        data.alternatives_mentioned = ", ".join(list(set(alternative_brands))[:3])
    else:
        data.alternatives_mentioned = "No specific alternatives mentioned"

    # Detect red flags
    red_flag_keywords = ["fake", "counterfeit", "duplicate", "expired", "contaminated", 
                         "scam", "fraud", "lawsuit", "banned", "heavy metal", "steroid"]
    detected_flags = []
    for kw in red_flag_keywords:
        if kw in all_text:
            detected_flags.append(kw)
    
    if detected_flags:
        data.red_flags = "⚠️ Mentioned: " + ", ".join(detected_flags)
    else:
        data.red_flags = "No red flags mentioned"

    # Determine overall sentiment
    positive_signals = sum(1 for p in unique_posts if p["score"] > 5)
    negative_signals = sum(1 for p in unique_posts
                          if any(w in (p["title"] + p["selftext"]).lower()
                                 for w in ["fake", "avoid", "waste", "scam", "bad", "worst"]))

    if data.thread_count == 0:
        data.sentiment = "Not Found"
    elif negative_signals > positive_signals:
        data.sentiment = "Negative"
    elif positive_signals > 2:
        data.sentiment = "Positive"
    else:
        data.sentiment = "Mixed"

    # Build community consensus
    if data.thread_count < 3:
        data.community_consensus = f"Limited community discussion ({data.thread_count} threads). Not enough data for consensus."
    elif data.sentiment == "Positive":
        data.community_consensus = f"Community sentiment is generally positive across {data.thread_count} discussions. {data.recommendations}."
    elif data.sentiment == "Negative":
        data.community_consensus = f"Community sentiment leans negative. {data.red_flags if 'No red flags' not in data.red_flags else data.recommendations}."
    else:
        data.community_consensus = f"Mixed opinions in the community ({data.thread_count} discussions). Some recommend it, others suggest alternatives."

    log.info(f"  → {data.thread_count} threads found, sentiment: {data.sentiment}")
    if data.alternatives_mentioned != "No specific alternatives mentioned":
        log.info(f"  → Alternatives mentioned: {data.alternatives_mentioned}")

    return data


# ── Web Research (Lab Testing + Clinical) ─────────────────────────────

def web_research(product_name: str, brand: str) -> WebResearchData:
    """
    Search the web for lab testing data and clinical research.

    MVP: Uses DuckDuckGo HTML search (no API key needed).
    UPGRADE: Replace with Perplexity API calls.
    """
    data = WebResearchData()

    # Search for lab testing
    query = f"{brand} {product_name} lab test COA India Trustified"
    try:
        log.info(f"  Web research: lab testing...")
        results = _duckduckgo_search(query, max_results=5)

        for r in results:
            text = (r["title"] + " " + r["snippet"]).lower()
            if any(kw in text for kw in ["lab test", "coa", "certificate", "trustified",
                                          "informed sport", "nsf", "tested"]):
                data.lab_tested = True
                data.lab_test_url = r["url"]

                if "trustified" in text:
                    data.lab_testing_body = "Trustified"
                elif "informed sport" in text:
                    data.lab_testing_body = "Informed Sport"
                elif "nsf" in text:
                    data.lab_testing_body = "NSF"
                elif "fssai" in text:
                    data.lab_testing_body = "FSSAI"
                else:
                    data.lab_testing_body = "Third Party"

                data.lab_test_result = "Pass"
                break

    except Exception as e:
        log.warning(f"  Lab test search failed: {e}")

    # Check label transparency based on ingredients info
    data.label_transparency = "Unknown"  # Will be refined by Ingredients Agent

    time.sleep(1)

    return data


def _duckduckgo_search(query: str, max_results: int = 5) -> list:
    """
    Simple DuckDuckGo HTML scraper. No API key needed.
    Returns list of {title, url, snippet}.
    """
    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(url, data={"q": query}, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        }, timeout=10)

        soup = BeautifulSoup(resp.text, "html.parser")
        result_divs = soup.select(".result")

        for div in result_divs[:max_results]:
            title_el = div.select_one(".result__title a")
            snippet_el = div.select_one(".result__snippet")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": title_el.get("href", ""),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })

    except Exception as e:
        log.warning(f"DuckDuckGo search failed: {e}")

    return results


# ── Completeness Check ────────────────────────────────────────────────

def assess_completeness(output: ResearchOutput) -> str:
    """Rate the data completeness of the research output."""
    checks = [
        output.amazon.rating > 0,
        output.amazon.review_count > 0,
        output.amazon.price > 0,
        len(output.amazon.ingredients_raw) > 20,
        output.reddit.sentiment != "",
        output.reddit.thread_count > 0,
    ]
    score = sum(checks)
    if score >= 5:
        return "Complete"
    elif score >= 3:
        return "Partial"
    else:
        return "Minimal"


# ── Pipeline Orchestrator ─────────────────────────────────────────────

def research_product(product: dict, airtable: AirtableClient, dry_run: bool = False) -> bool:
    """
    Run the full research pipeline for one product.
    Returns True on success, False on failure.
    """
    fields = product.get("fields", {})
    product_id = product["id"]
    product_name = fields.get("Product Name", "Unknown")
    brand = fields.get("Brand", "")
    amazon_url = fields.get("Amazon URL", "")
    category = fields.get("Category", "")

    log.info(f"{'[DRY RUN] ' if dry_run else ''}Researching: {brand} — {product_name}")
    log.info(f"  Category: {category}")
    log.info(f"  Amazon URL: {amazon_url}")

    start_time = time.time()
    output = ResearchOutput()
    output.research_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Step 1: Scrape Amazon product page
    if amazon_url:
        # Use Playwright scraper for better Amazon data
        amazon_result = scrape_amazon_playwright(amazon_url)
        output.amazon.title = amazon_result.get("title", "")
        output.amazon.rating = amazon_result.get("rating", 0.0)
        output.amazon.review_count = amazon_result.get("rating_count", 0)
        output.amazon.price = float(amazon_result.get("price", "0").replace("₹", "").replace(",", "") or 0)
        output.amazon.brand = amazon_result.get("brand", "")
        output.amazon.ingredients_raw = amazon_result.get("ingredients_raw", "")
        output.amazon.serving_size = amazon_result.get("serving_size", "")
        output.amazon.image_url = amazon_result.get("image_url", "")
        time.sleep(2)

        # Step 1b: Scrape Amazon reviews (using Chrome session)
        log.info("  Scraping customer reviews (Playwright)...")
        review_data = scrape_reviews_playwright(amazon_url, browser_context=BROWSER_CONTEXT)
        output.amazon.top_pros = review_data.get("top_pros", "")
        output.amazon.top_cons = review_data.get("top_cons", "")
        output.amazon.star_distribution = review_data.get("star_distribution", "")
        output.amazon.top_praised = review_data.get("top_praised", "")
        output.amazon.top_complaints = review_data.get("top_complaints", "")
        output.amazon.recurring_themes = review_data.get("recurring_themes", "")
        output.amazon.suspicious_pattern = review_data.get("suspicious_pattern", "")
        output.amazon.helpful_reviews_raw = review_data.get("helpful_reviews_raw", "")
        time.sleep(2)
    else:
        log.warning("  No Amazon URL — skipping Amazon scrape")

    # Step 2: Search Reddit (enhanced with category awareness)
    output.reddit = scrape_reddit(product_name, brand, category)
    time.sleep(2)

    # Step 3: Web research (lab testing)
    output.web = web_research(product_name, brand)

    # Assess completeness
    output.data_completeness = assess_completeness(output)

    elapsed = round(time.time() - start_time, 1)
    log.info(f"  Research complete in {elapsed}s — Completeness: {output.data_completeness}")

    if dry_run:
        log.info("  [DRY RUN] Would write to Airtable:")
        log.info(json.dumps(_build_airtable_fields(output, product_id), indent=2, default=str))
        return True

    # Write to Airtable
    try:
        # Create Raw Research record
        research_fields = _build_airtable_fields(output, product_id)
        airtable.create_record(TBL_RAW_RESEARCH, research_fields)
        log.info("  ✓ Raw Research record created")

        # Update product status
        airtable.update_record(TBL_PRODUCTS, product_id, {
            "Review Status": "Research Complete",
        })
        log.info("  ✓ Product status → Research Complete")

        # Log to Agent Log
        airtable.create_record(TBL_AGENT_LOG, {
            "Agent": "Research Agent",
            "Action": "research_product",
            "Status": "Success",
            "Input Summary": f"{brand} — {product_name}",
            "Output Summary": f"Completeness: {output.data_completeness}, "
                              f"Amazon: {output.amazon.rating}★ ({output.amazon.review_count} reviews), "
                              f"Reddit: {output.reddit.sentiment} ({output.reddit.thread_count} threads)",
            "Tokens Used": 0,  # No LLM tokens in MVP
        })
        log.info("  ✓ Agent Log entry created")

        return True

    except Exception as e:
        log.error(f"  ✗ Airtable write failed: {e}")

        # Log failure
        try:
            airtable.create_record(TBL_AGENT_LOG, {
                "Agent": "Research Agent",
                "Action": "research_product",
                "Status": "Failed",
                "Input Summary": f"{brand} — {product_name}",
                "Error Details": str(e)[:500],
            })
        except:
            pass

        return False


def _build_airtable_fields(output: ResearchOutput, product_id: str) -> dict:
    """Build the Airtable fields dict from research output."""
    fields = {
        # Link to Products table
        "Product": [product_id],
        # Amazon data
        "Amazon Rating": output.amazon.rating,
        "Amazon Review Count": output.amazon.review_count,
        "Amazon Top Pros": output.amazon.top_pros[:2000],
        "Amazon Top Cons": output.amazon.top_cons[:2000],
        # Enhanced Amazon sentiment data
        "Amazon Star Distribution": output.amazon.star_distribution[:500],
        "Amazon Top Praised": output.amazon.top_praised[:500],
        "Amazon Top Complaints": output.amazon.top_complaints[:500],
        "Amazon Recurring Themes": output.amazon.recurring_themes[:500],
        "Amazon Suspicious Pattern": output.amazon.suspicious_pattern[:500],
        "Amazon Helpful Reviews": output.amazon.helpful_reviews_raw[:5000],
        # Reddit data
        "Reddit Summary": output.reddit.summary[:2000],
        "Reddit Sources": json.dumps(output.reddit.sources),
        # Enhanced Reddit sentiment data
        "Reddit Recommendations": output.reddit.recommendations[:500],
        "Reddit Alternatives": output.reddit.alternatives_mentioned[:500],
        "Reddit Red Flags": output.reddit.red_flags[:500],
        "Reddit Community Consensus": output.reddit.community_consensus[:1000],
        # Ingredients
        "Ingredients Raw": output.amazon.ingredients_raw[:5000],
        # Lab testing
        "Third Party Lab Tested": output.web.lab_tested,
        "Lab Testing Body": output.web.lab_testing_body,
        "Lab Test URL": output.web.lab_test_url,
        # Clinical
        "Clinical Research Summary": output.web.clinical_summary,
        # Meta
        "Scraped By": output.scraped_by,
        "Raw JSON": json.dumps(asdict(output), default=str)[:10000],
    }
    # Add singleSelect fields only if they have valid values
    if output.amazon.sentiment in ['Positive', 'Mixed', 'Negative']:
        fields["Amazon Sentiment"] = output.amazon.sentiment
    if output.reddit.sentiment in ['Positive', 'Mixed', 'Negative', 'Neutral', 'Unknown']:
        fields["Reddit Sentiment"] = output.reddit.sentiment
    if output.web.label_transparency in ['Full Disclosure', 'Partial', 'Proprietary Blend']:
        fields["Label Transparency"] = output.web.label_transparency
    if output.web.lab_test_result in ['Pass', 'Partial', 'Fail', 'Not Available']:
        fields["Lab Test Result"] = output.web.lab_test_result
    if output.data_completeness in ['Complete', 'Partial', 'Minimal']:
        fields["Data Completeness"] = output.data_completeness
    return fields


# ── Main ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Limitless Labs Research Agent")
    parser.add_argument("--product", help="Research a specific product by name")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't write to Airtable")
    parser.add_argument("--limit", type=int, default=10, help="Max products to process (default: 10)")
    args = parser.parse_args()

    if not AIRTABLE_TOKEN and not args.dry_run:
        log.error("AIRTABLE_TOKEN environment variable not set.")
        log.error("Set it with: export AIRTABLE_TOKEN='your_token_here'")
        sys.exit(1)

    airtable = AirtableClient(AIRTABLE_TOKEN, AIRTABLE_BASE_ID)

    if args.product:
        # Research a specific product
        log.info(f"Searching for product: {args.product}")
        formula = f"SEARCH(LOWER('{args.product.lower()}'), LOWER({{Product Name}}))"
        products = airtable.list_records(TBL_PRODUCTS, formula=formula, max_records=1)
        if not products:
            log.error(f"Product not found in Airtable: {args.product}")
            sys.exit(1)
    else:
        # Get all Queued products
        log.info("Fetching Queued products from Airtable...")
        formula = "{Review Status} = 'Queued'"
        products = airtable.list_records(TBL_PRODUCTS, formula=formula, max_records=args.limit)

    if not products:
        log.info("No products to research. Nothing queued.")
        return

    log.info(f"Found {len(products)} product(s) to research.\n")

    success = 0
    failed = 0

    for product in products:
        try:
            ok = research_product(product, airtable, dry_run=args.dry_run)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            failed += 1

        # Delay between products
        if len(products) > 1:
            time.sleep(3)

    log.info(f"\n{'=' * 50}")
    log.info(f"Done. {success} succeeded, {failed} failed out of {len(products)} products.")


if __name__ == "__main__":
    main()
