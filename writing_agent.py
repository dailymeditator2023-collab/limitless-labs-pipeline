#!/usr/bin/env python3
"""
Limitless Labs — Writing Agent

Generates AI-written reviews from scored products using GPT-4o.
Fetches research data and scores, generates review content, saves back to Airtable.

Usage:
    python3 writing_agent.py --limit 2     # Write reviews for first 2 scoring-complete products
    python3 writing_agent.py --product "Whole Truth"  # Write review for specific product
"""

import os
import sys
import json
import time
import argparse
import logging
import requests

from openai import OpenAI

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
SCORES_TABLE = "tblRux91YMnOB7okG"
RAW_RESEARCH_TABLE = "tblC8NLwWuBrw5507"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

# ── OpenAI Client ────────────────────────────────────────────────────
client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# ── Airtable Helpers ─────────────────────────────────────────────────

def fetch_scoring_complete(limit=10):
    """Get all products with Review Status = Scoring Complete"""
    resp = requests.get(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}",
        headers=HEADERS,
        params={
            "filterByFormula": "{Review Status} = 'Scoring Complete'",
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
        headers=HEADERS,
        params={"filterByFormula": formula, "maxRecords": 1}
    )
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        return records[0] if records else None
    return None


def fetch_linked_record(table_id, record_id):
    """Fetch a single linked record"""
    resp = requests.get(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}",
        headers=HEADERS
    )
    if resp.status_code == 200:
        return resp.json().get("fields", {})
    return {}


def fetch_latest_score(product_id):
    """Fetch the most recent score record for a product (sorted by Created desc)"""
    # ARRAYJOIN formula doesn't work reliably for linked records
    # Instead, fetch all scores and filter manually
    all_scores = []
    offset = None
    
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{SCORES_TABLE}",
            headers=HEADERS,
            params=params
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        all_scores.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    
    # Filter scores that link to this product
    matching = [
        s for s in all_scores 
        if product_id in s.get("fields", {}).get("Product", [])
    ]
    
    if not matching:
        return {}
    
    # Sort by created time descending and return latest
    matching.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
    return matching[0].get("fields", {})


def update_product(record_id, review, summary):
    """Write review back to Airtable and update status"""
    resp = requests.patch(
        f"https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}/{record_id}",
        headers=HEADERS,
        json={"fields": {
            "Review Content": review,
            "Review Summary": summary,
            "Review Status": "Writing Complete",
        }}
    )
    if resp.status_code != 200:
        log.error(f"Airtable update failed: {resp.text[:200]}")
        return False
    return True


# ── Review Generation ────────────────────────────────────────────────

REVIEW_PROMPT = """You are writing for Limitless Labs — think Wirecutter for supplements, not Wikipedia. Direct, confident, opinionated. A knowledgeable friend who's done the research.

Write a review for: {brand} — {product_name}
Category: {category}
Price: ₹{price} | Servings: {servings} | Cost per serving: ₹{cost_per_serving}

===== SCORING DATA =====
Overall Score: {overall_score}/10
Formula Score: {formula_score}/10
Dosing Score: {dosing_score}/10
Value Score: {value_score}/10
Transparency Score: {transparency_score}/10
Verdict: {verdict}
Scoring Notes: {scoring_notes}

===== AMAZON CUSTOMER DATA =====
Amazon Rating: {amazon_rating} ({amazon_review_count} reviews)
Star Distribution: {star_distribution}
Top Praised: {top_praised}
Top Complaints: {top_complaints}
Recurring Themes: {recurring_themes}
Suspicious Patterns: {suspicious_pattern}
Sample Reviews: {amazon_pros}
Sample Complaints: {amazon_cons}

===== REDDIT COMMUNITY DATA =====
Reddit Sentiment: {reddit_sentiment}
Thread Count: {reddit_thread_count}
Community Consensus: {reddit_consensus}
Recommendations: {reddit_recommendations}
Alternatives Mentioned: {reddit_alternatives}
Red Flags: {reddit_red_flags}
Discussion Summary: {reddit_summary}

===== INGREDIENTS =====
Ingredients Raw: {ingredients_raw}
Ingredients Structured: {ingredients_structured}

===== TRANSPARENCY =====
Label Transparency: {label_transparency}
Third Party Lab Tested: {lab_tested}
Lab Testing Body: {lab_body}
Clinical Research Summary: {clinical_summary}

===== WRITING RULES (CRITICAL — follow exactly) =====

1. NEVER HEDGE. Don't say "might", "could", "largely", "primarily", "generally". State what IS.

2. NEVER MENTION DATA GAPS OR PIPELINE ISSUES. Phrases like "specifics were not scraped", "data unavailable", "N/A reviews" should NEVER appear. If data is missing, OMIT that section entirely. Don't apologize for missing data.

3. USE SPECIFIC NUMBERS. Not "primarily positive" but "78% 5-star reviews across 23,568 ratings". Not "good protein content" but "24g protein per 33g scoop (73% protein by weight)".

4. THE VERDICT IS ONE CLEAR SENTENCE. Include: what the product IS, its key strength, its key weakness, who should buy it, and what's the better alternative if relevant. Example: "MuscleBlaze Whey Gold is a mid-range protein with excellent transparency but average dosing — good if label honesty is your priority, but AS-IT-IS offers better value per gram."

5. WHAT CUSTOMERS SAY must have CONCRETE INSIGHTS. Not "consumers note purity" but "the #1 praise across 23K reviews: easy digestion with no bloating (rare for whey concentrate). Main complaint: clumps in water, mixes better with milk."

6. EVERY SENTENCE MUST TELL THE READER SOMETHING NEW. Cut filler ruthlessly. No "it's worth noting", no "it should be mentioned", no "consumers might find".

7. BE OPINIONATED. If it's bad, say "skip this". If it's great, say "buy this". If it's mid, say exactly who it's for and who should look elsewhere.

8. ONLY DISCUSS PRIMARY INGREDIENTS FOR THE CATEGORY. This is critical:
   - Protein products: discuss protein, BCAAs, digestive enzymes. Do NOT mention calcium, iron, sodium as "under-dosed" — they're incidental nutrients, not why someone buys protein.
   - Multivitamins: discuss vitamins and minerals. 
   - Pre-workouts: discuss caffeine, beta-alanine, citrulline, creatine.
   - Ashwagandha: discuss ashwagandha, adaptogens.
   - Fish Oil/Omega-3: discuss EPA, DHA, omega-3 content.
   If an ingredient appears but isn't primary for this category, ignore it in dosing analysis.

9. PRICE PER SERVING IS MANDATORY. Always include "At ₹X per serving..." in the VALUE section. If price data is provided above, calculate and use it.

===== REVIEW STRUCTURE =====

## VERDICT BOX
- **Score: X.X/10** — {verdict}
- One clear verdict sentence (see rule #4)
- Sub-scores: Formula X | Dosing X | Value X | Transparency X

## THE BOTTOM LINE
2-3 punchy paragraphs. Lead with the most important finding. Include the Amazon rating with specific numbers. No fluff.

## FORMULA
List key ingredients with SPECIFIC doses vs clinical benchmarks. Example:
- **Whey Protein**: 24g/serving — solid, meets the 20-25g threshold for muscle protein synthesis
- **BCAAs**: 5.2g — adequate but not exceptional; clinical range is 5-10g
Flag proprietary blends. Note ingredient forms (KSM-66 vs generic).

## DOSING VERDICT
One paragraph. What's properly dosed, what's under-dosed, what's missing. Be specific.

## VALUE
Price per serving (if available). Compare to competitors BY NAME. Is the premium justified? Give a clear answer.

## TRANSPARENCY
Lab testing status + certifier. Full disclosure vs prop blend. Brand track record. Red flags if any.

## WHAT CUSTOMERS SAY
ONLY include if you have real data. Structure:

**Amazon** ({amazon_review_count} reviews, {amazon_rating}★)
- Star breakdown: X% 5-star, X% 1-star
- Top praise: [specific, concrete insight]
- Top complaint: [specific, concrete insight]
- Watch out for: [suspicious patterns if any, otherwise skip]

**Reddit**
- [Concrete community insight or skip entirely if no real data]

## WHO SHOULD BUY / WHO SHOULD SKIP
2-3 bullets each. Specific use cases.

## FINAL WORD
1-2 sentences max. Clear recommendation.

===== STYLE =====
- Confident, direct, opinionated
- Use "we" for Limitless Labs voice
- Under 1200 words (shorter is better)
- Markdown formatting
"""


def generate_review(product, scores, research):
    """Generate review text using GPT-4o"""
    if not client:
        raise RuntimeError("OpenAI client not initialized - check OPENAI_API_KEY")

    # Calculate price per serving
    price = product.get("MRP (₹)")
    servings = product.get("Servings Per Pack")
    cost_per_serving = None
    if price and servings and servings > 0:
        cost_per_serving = round(price / servings, 2)
    
    # Use existing cost per serving if we calculated one, otherwise use what's in Airtable
    if not cost_per_serving:
        cost_per_serving = product.get("Cost Per Serving (₹)")

    # Build prompt with all data (including enhanced sentiment fields)
    prompt = REVIEW_PROMPT.format(
        brand=product.get("Brand", "Unknown"),
        product_name=product.get("Product Name", "Unknown"),
        category=product.get("Category", "Unknown"),
        price=price if price else "Not available",
        servings=servings if servings else "Not available",
        cost_per_serving=cost_per_serving if cost_per_serving else "Not available",
        overall_score=scores.get("Score Overall", "N/A"),
        formula_score=scores.get("Score Formula", "N/A"),
        dosing_score=scores.get("Score Dosing", "N/A"),
        value_score=scores.get("Score Value", "N/A"),
        transparency_score=scores.get("Score Transparency", "N/A"),
        verdict=scores.get("Verdict", "N/A"),
        scoring_notes=scores.get("Scoring Notes", "N/A"),
        # Amazon customer data
        amazon_rating=research.get("Amazon Rating", "N/A"),
        amazon_review_count=research.get("Amazon Review Count", "N/A"),
        star_distribution=research.get("Amazon Star Distribution", "N/A"),
        top_praised=research.get("Amazon Top Praised", "N/A"),
        top_complaints=research.get("Amazon Top Complaints", "N/A"),
        recurring_themes=research.get("Amazon Recurring Themes", "N/A"),
        suspicious_pattern=research.get("Amazon Suspicious Pattern", "No suspicious patterns detected"),
        amazon_pros=research.get("Amazon Top Pros", "N/A")[:1000],
        amazon_cons=research.get("Amazon Top Cons", "N/A")[:1000],
        # Reddit community data
        reddit_sentiment=research.get("Reddit Sentiment", "N/A"),
        reddit_thread_count=len(json.loads(research.get("Reddit Sources", "[]"))) if research.get("Reddit Sources") else 0,
        reddit_consensus=research.get("Reddit Community Consensus", "Limited community discussion available"),
        reddit_recommendations=research.get("Reddit Recommendations", "N/A"),
        reddit_alternatives=research.get("Reddit Alternatives", "No specific alternatives mentioned"),
        reddit_red_flags=research.get("Reddit Red Flags", "No red flags mentioned"),
        reddit_summary=research.get("Reddit Summary", "N/A")[:1000],
        # Ingredients
        ingredients_raw=research.get("Ingredients Raw", "N/A")[:2000],
        ingredients_structured=research.get("Ingredients Structured", "N/A")[:2000],
        # Transparency
        label_transparency=research.get("Label Transparency", "N/A"),
        lab_tested=research.get("Third Party Lab Tested", False),
        lab_body=research.get("Lab Testing Body", "N/A"),
        clinical_summary=research.get("Clinical Research Summary", "N/A")[:500],
    )

    # Generate main review
    log.info("  Generating review with GPT-4o...")
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    review = response.choices[0].message.content

    # Generate short summary
    log.info("  Generating summary with GPT-4o-mini...")
    summary_response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"Write a 2-sentence summary of this supplement review for a card preview. Be specific about the score and key finding:\n\n{review[:2000]}"
        }]
    )
    summary = summary_response.choices[0].message.content

    return review, summary


def write_review(record, dry_run=False):
    """Process a single product: fetch data, generate review, save"""
    fields = record["fields"]
    product_id = record["id"]
    name = fields.get("Product Name", "Unknown")
    brand = fields.get("Brand", "Unknown")

    log.info(f"Writing review: {brand} — {name}")

    # Fetch latest score record (sorted by created date descending)
    log.info(f"  Fetching latest score record...")
    scores = fetch_latest_score(product_id)
    if not scores:
        log.warning(f"  No Scores record found for this product")

    # Fetch linked research
    research = {}
    research_ids = fields.get("Raw Research", [])
    if research_ids:
        log.info(f"  Fetching research record...")
        research = fetch_linked_record(RAW_RESEARCH_TABLE, research_ids[0])
    else:
        log.warning(f"  No linked Raw Research record found")

    # Generate review
    try:
        review, summary = generate_review(fields, scores, research)
        log.info(f"  ✓ Review generated ({len(review)} chars)")
        log.info(f"  Summary: {summary[:100]}...")

        if dry_run:
            log.info("  [DRY RUN] Would save to Airtable")
            print("\n" + "="*60)
            print("GENERATED REVIEW:")
            print("="*60)
            print(review)
            print("\n" + "="*60)
            print("SUMMARY:")
            print("="*60)
            print(summary)
            return True

        # Save to Airtable
        if update_product(product_id, review, summary):
            log.info(f"  ✓ Saved to Airtable → Writing Complete")
            return True
        else:
            log.error(f"  ✗ Failed to save to Airtable")
            return False

    except Exception as e:
        log.error(f"  ✗ Error generating review: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Limitless Labs Writing Agent")
    parser.add_argument("--product", help="Write review for a specific product by name")
    parser.add_argument("--limit", type=int, default=5, help="Max products to process")
    parser.add_argument("--dry-run", action="store_true", help="Generate but don't save to Airtable")
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY environment variable not set.")
        log.error("Set it with: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    if not AIRTABLE_TOKEN:
        log.error("AIRTABLE_TOKEN environment variable not set.")
        sys.exit(1)

    if args.product:
        # Write review for specific product
        log.info(f"Searching for product: {args.product}")
        record = search_product(args.product)
        if not record:
            log.error(f"Product not found: {args.product}")
            sys.exit(1)
        products = [record]
    else:
        # Get all Scoring Complete products
        log.info("Fetching Scoring Complete products...")
        products = fetch_scoring_complete(args.limit)

    if not products:
        log.info("No products to write reviews for.")
        return

    log.info(f"Found {len(products)} product(s) to process.\n")

    success = 0
    failed = 0

    for i, record in enumerate(products, 1):
        log.info(f"[{i}/{len(products)}]")
        if write_review(record, dry_run=args.dry_run):
            success += 1
        else:
            failed += 1
        
        # Rate limit between products
        if i < len(products):
            time.sleep(2)

    log.info("\n" + "="*50)
    log.info(f"Done. {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
