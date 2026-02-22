#!/usr/bin/env python3
"""
Limitless Labs — Scoring Agent
================================
Reads structured research data and ingredient analysis from Airtable,
applies the scoring framework, and writes scores to the Scores table.

Pure logic — no web scraping, no external APIs beyond Airtable.
This is the fastest and most deterministic agent in the pipeline.

Scoring Framework:
    Formula       (30%): Ingredient quality, fillers, red flags
    Dosing        (30%): % of ingredients at clinical benchmark doses
    Value         (20%): Cost per serving vs category average
    Transparency  (20%): Label disclosure, third-party testing

    Overall = (Formula × 0.30) + (Dosing × 0.30) + (Value × 0.20) + (Transparency × 0.20)

    Verdict: 8.0+ = Highly Recommended / 7.5–7.9 = Recommended / 5.0–7.4 = Average / <5.0 = Skip

Usage:
    python3 scoring_agent.py                          # Score all "Scoring" products
    python3 scoring_agent.py --product "AS-IT-IS Whey"  # Score one product
    python3 scoring_agent.py --dry-run                  # Calculate but don't write
"""

import os
import sys
import json
import re
import time
import logging
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appUOcZUDNPzstZlv"

TBL_PRODUCTS      = "tblttA4xVbWsAav0B"
TBL_RAW_RESEARCH  = "tblC8NLwWuBrw5507"
TBL_SCORES        = "tblRux91YMnOB7okG"
TBL_AGENT_LOG     = "tblcZh2gT8fv99GTK"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scoring-agent")


# ── Airtable Client ──────────────────────────────────────────────────

class AirtableClient:
    def __init__(self, token: str, base_id: str):
        self.token = token
        self.base_url = f"https://api.airtable.com/v0/{base_id}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def list_records(self, table_id: str, formula: str = "", fields: list = None,
                     max_records: int = 100) -> list:
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
            resp = requests.get(f"{self.base_url}/{table_id}",
                                headers=self.headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
            time.sleep(0.2)
        return records

    def create_record(self, table_id: str, fields: dict) -> dict:
        resp = requests.post(f"{self.base_url}/{table_id}",
                             headers=self.headers, json={"fields": fields})
        resp.raise_for_status()
        return resp.json()

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        resp = requests.patch(f"{self.base_url}/{table_id}/{record_id}",
                              headers=self.headers, json={"fields": fields})
        resp.raise_for_status()
        return resp.json()


# ── Category-Aware Ingredient Classification ──────────────────────────

# Primary ingredients are what the product is FOR — these get full scoring weight
# Incidental ingredients are naturally present but not the point — scored leniently
# Unknown ingredients get moderate weight

CATEGORY_PRIMARY_INGREDIENTS = {
    "protein": ["protein", "whey protein", "whey protein isolate", "whey protein concentrate", 
                "casein", "plant protein", "pea protein", "rice protein", "soy protein",
                "bcaa", "leucine", "isoleucine", "valine", "eaa"],
    "whey concentrate": ["whey protein", "whey protein concentrate", "protein", "bcaa"],
    "whey isolate": ["whey protein isolate", "whey protein", "protein", "bcaa"],
    "plant protein": ["plant protein", "pea protein", "rice protein", "protein", "bcaa"],
    "mass gainer": ["protein", "carbohydrates", "calories", "mass gainer blend"],
    "creatine": ["creatine", "creatine monohydrate", "creapure"],
    "pre-workout": ["caffeine", "citrulline", "beta-alanine", "creatine", "arginine", 
                    "nitric oxide", "taurine", "tyrosine"],
    "caffeine": ["caffeine", "l-theanine", "green tea extract"],
    "caffeine-energy": ["caffeine", "l-theanine", "l-carnitine", "taurine", "b vitamins"],
    "ashwagandha": ["ashwagandha", "ksm-66", "sensoril", "withanolides"],
    "adaptogens": ["ashwagandha", "rhodiola", "ginseng", "holy basil", "cordyceps"],
    "sleep": ["melatonin", "magnesium", "l-theanine", "gaba", "valerian", "5-htp"],
    "melatonin": ["melatonin", "magnesium", "l-theanine"],
    "sleep-recovery": ["melatonin", "magnesium", "zinc", "ashwagandha", "l-theanine"],
    "nootropics": ["lion's mane", "bacopa", "ginkgo", "alpha-gpc", "phosphatidylserine",
                   "caffeine", "l-theanine", "omega-3"],
    "omega-3": ["omega-3", "fish oil", "epa", "dha", "algae oil"],
    "multivitamin": ["vitamin a", "vitamin c", "vitamin d", "vitamin e", "vitamin k",
                     "vitamin b1", "vitamin b2", "vitamin b3", "vitamin b5", "vitamin b6",
                     "vitamin b12", "folate", "biotin", "calcium", "magnesium", "zinc",
                     "iron", "selenium", "copper", "manganese", "chromium", "iodine"],
    "vitamins-minerals": ["vitamin", "mineral", "calcium", "magnesium", "zinc", "iron"],
    "vitamin d": ["vitamin d", "vitamin d3", "cholecalciferol"],
    "greens": ["spirulina", "chlorella", "wheatgrass", "barley grass", "greens blend"],
}

# Incidental ingredients — naturally present, don't penalize for low doses
INCIDENTAL_INGREDIENTS = [
    "sodium", "potassium", "sugar", "added sugar", "fiber", "fat", "saturated fat",
    "trans fat", "cholesterol", "carbohydrates", "calories",
    # Minerals naturally present in protein powders (incidental unless it's a multivitamin)
    "calcium", "iron", "zinc", "magnesium", "phosphorus", "copper", "manganese",
    "selenium", "iodine", "chromium", "molybdenum",
    # Amino acids naturally in protein (don't score unless it's a dedicated amino product)
    "aspartic acid", "glutamic acid", "serine", "histidine", "glycine", "threonine",
    "alanine", "proline", "tyrosine", "cystine", "arginine", "lysine", "methionine",
    "phenylalanine", "tryptophan", "valine", "isoleucine", "leucine",
]


def is_primary_ingredient(ingredient_name: str, category: str) -> bool:
    """Check if an ingredient is primary for the given product category."""
    if not category:
        return True  # If no category, treat all as primary
    
    name_lower = ingredient_name.lower().strip()
    category_lower = category.lower().strip()
    
    # Check all matching category keys
    for cat_key, primary_list in CATEGORY_PRIMARY_INGREDIENTS.items():
        if cat_key in category_lower or category_lower in cat_key:
            for primary in primary_list:
                if primary in name_lower or name_lower in primary:
                    return True
    return False


def is_incidental_ingredient(ingredient_name: str) -> bool:
    """Check if an ingredient is incidental (naturally present, not the point)."""
    name_lower = ingredient_name.lower().strip()
    for incidental in INCIDENTAL_INGREDIENTS:
        if incidental in name_lower or name_lower in incidental:
            return True
    return False


# ── Category Averages (for Value scoring) ─────────────────────────────

# Average cost per serving (INR) by category — used as benchmarks
# These should eventually be computed dynamically from the Products table
CATEGORY_AVG_COST = {
    "protein": 60,           # ₹60/serving average
    "whey concentrate": 50,
    "whey isolate": 80,
    "plant protein": 55,
    "mass gainer": 45,
    "adaptogens": 20,
    "ashwagandha": 18,
    "caffeine-energy": 15,
    "caffeine": 15,
    "pre-workout": 50,
    "nootropics": 25,
    "sleep-recovery": 20,
    "sleep": 20,
    "melatonin": 15,
    "vitamins-minerals": 15,
    "omega-3": 12,
    "multivitamin": 15,
    "creatine": 15,
    "vitamin d": 10,
    "greens": 50,
}


# ── Scoring Functions ─────────────────────────────────────────────────

def score_formula(ingredients_structured: list, raw_research: dict, category: str = "") -> tuple:
    """
    Score the formula quality (0-10).
    - Are ingredients appropriate for purpose?
    - Any unnecessary fillers or red flags?
    - Quality of forms used?
    - Category-aware: only penalize under-dosed PRIMARY ingredients

    Returns (score, notes).
    """
    if not ingredients_structured:
        return 5.0, "No structured ingredient data available"

    total = len(ingredients_structured)
    if total == 0:
        return 5.0, "No ingredients parsed"

    notes_parts = []

    # Separate primary vs incidental ingredients
    primary_ingredients = []
    incidental_ingredients = []
    
    for ing in ingredients_structured:
        name = ing.get("ingredient_name", ing.get("name", ""))
        if is_incidental_ingredient(name):
            incidental_ingredients.append(ing)
        elif is_primary_ingredient(name, category):
            primary_ingredients.append(ing)
        else:
            # Unknown - treat as primary by default
            primary_ingredients.append(ing)
    
    # Count good vs bad indicators - ONLY for primary ingredients
    on_point = sum(1 for i in primary_ingredients
                   if i.get("assessment") in ("On Point", "Over-dosed"))
    under_dosed_primary = sum(1 for i in primary_ingredients
                              if "Under" in i.get("assessment", ""))
    no_data = sum(1 for i in primary_ingredients
                  if i.get("assessment") in ("No Data", "Unknown", "Not Assessed"))

    # Base score from assessment ratio (primary ingredients only)
    assessed = len(primary_ingredients) - no_data
    if assessed > 0:
        quality_ratio = on_point / max(assessed, 1)
    else:
        quality_ratio = 0.5

    base = 5.0 + (quality_ratio * 4.0)  # Range: 5.0 - 9.0

    # Bonus for having many good ingredients
    if on_point >= 4:
        base += 0.5
        notes_parts.append(f"{on_point} primary ingredients at effective doses")
    elif on_point >= 2:
        notes_parts.append(f"{on_point} primary ingredients at effective doses")

    # Penalty for under-dosed PRIMARY ingredients only
    if under_dosed_primary > 0:
        penalty = min(under_dosed_primary * 0.5, 2.0)
        base -= penalty
        notes_parts.append(f"{under_dosed_primary} primary ingredients under-dosed (-{penalty:.1f})")
    
    # Note incidental ingredients (no penalty)
    under_dosed_incidental = sum(1 for i in incidental_ingredients 
                                  if "Under" in i.get("assessment", ""))
    if under_dosed_incidental > 0:
        notes_parts.append(f"{under_dosed_incidental} incidental ingredients (no penalty)")

    # Check for red flag ingredients (proprietary blends, artificial colors, etc.)
    red_flags = ["proprietary blend", "artificial color", "artificial flavour",
                 "sucralose", "aspartame", "acesulfame"]
    ingredients_text = json.dumps(ingredients_structured).lower()
    flag_count = sum(1 for rf in red_flags if rf in ingredients_text)
    if flag_count > 0:
        base -= flag_count * 0.3
        notes_parts.append(f"{flag_count} red flag(s) found")

    score = round(max(1.0, min(10.0, base)), 1)
    notes = ". ".join(notes_parts) if notes_parts else "Standard formula"

    return score, notes


def score_dosing(ingredients_structured: list, category: str = "") -> tuple:
    """
    Score dosing accuracy (0-10).
    What percentage of PRIMARY ingredients are at clinical benchmark doses?
    Incidental ingredients don't count against the score.

    Returns (score, notes).
    """
    if not ingredients_structured:
        return 5.0, "No ingredient data"

    # Filter to only primary ingredients for assessment
    primary_assessed = []
    for i in ingredients_structured:
        name = i.get("ingredient_name", i.get("name", ""))
        assessment = i.get("assessment", "")
        
        # Skip if no assessment data
        if assessment in ("No Data", "Unknown", "Not Assessed", ""):
            continue
        
        # Skip incidental ingredients
        if is_incidental_ingredient(name):
            continue
            
        primary_assessed.append(i)

    if not primary_assessed:
        return 5.0, "No primary ingredients could be assessed against benchmarks"

    total = len(primary_assessed)
    on_point = sum(1 for i in primary_assessed if i["assessment"] == "On Point")
    slightly_under = sum(1 for i in primary_assessed if i["assessment"] == "Slightly Under-dosed")
    under_dosed = sum(1 for i in primary_assessed if i["assessment"] == "Under-dosed")

    # Weighted ratio: on point = 1.0, slightly under = 0.5, under = 0
    weighted = (on_point * 1.0 + slightly_under * 0.5) / total

    # Map to 1-10 scale
    score = round(1.0 + weighted * 9.0, 1)

    notes_parts = []
    if on_point > 0:
        notes_parts.append(f"{on_point}/{total} at clinical doses")
    if slightly_under > 0:
        notes_parts.append(f"{slightly_under} slightly under-dosed")
    if under_dosed > 0:
        notes_parts.append(f"{under_dosed} significantly under-dosed")

    notes = ". ".join(notes_parts) if notes_parts else f"{on_point}/{total} at benchmark"

    return max(1.0, min(10.0, score)), notes


def score_value(cost_per_serving: float, category: str, amazon_rating: float = 0) -> tuple:
    """
    Score value for money (0-10).
    Cost per serving vs category average, quality relative to price.

    Returns (score, notes).
    """
    category_lower = category.lower().strip() if category else ""

    # Find category average
    avg_cost = None
    for key, val in CATEGORY_AVG_COST.items():
        if key in category_lower or category_lower in key:
            avg_cost = val
            break

    if not avg_cost:
        avg_cost = 40  # Default fallback

    notes_parts = []

    if cost_per_serving <= 0:
        return 6.0, "Cost per serving unknown, defaulting to average"

    # Price ratio: < 1.0 means cheaper than average
    ratio = cost_per_serving / avg_cost

    if ratio <= 0.5:
        base = 9.5
        notes_parts.append(f"Exceptional value — {int((1-ratio)*100)}% below category average")
    elif ratio <= 0.75:
        base = 8.5
        notes_parts.append(f"Good value — {int((1-ratio)*100)}% below average")
    elif ratio <= 1.0:
        base = 7.5
        notes_parts.append("At or below category average price")
    elif ratio <= 1.25:
        base = 6.5
        notes_parts.append(f"{int((ratio-1)*100)}% above category average")
    elif ratio <= 1.75:
        base = 5.5
        notes_parts.append(f"Premium priced — {int((ratio-1)*100)}% above average")
    elif ratio <= 2.5:
        base = 4.5
        notes_parts.append(f"Expensive — {int((ratio-1)*100)}% above average")
    else:
        base = 3.5
        notes_parts.append(f"Very expensive — {int((ratio-1)*100)}% above average")

    # Bonus for high Amazon rating (quality relative to price)
    if amazon_rating >= 4.3:
        base += 0.3
        notes_parts.append("High customer satisfaction")
    elif amazon_rating >= 4.0:
        base += 0.1

    score = round(max(1.0, min(10.0, base)), 1)
    notes_parts.append(f"₹{cost_per_serving:.0f}/serve vs ₹{avg_cost} avg")

    return score, ". ".join(notes_parts)


def score_transparency(label_transparency: str, lab_tested: bool,
                       lab_body: str = "", ingredients_structured: list = None) -> tuple:
    """
    Score label transparency (0-10).
    Full disclosure, proprietary blends, third-party testing.

    Returns (score, notes).
    """
    notes_parts = []
    base = 5.0

    # Label transparency
    transparency_lower = (label_transparency or "").lower()
    if "full" in transparency_lower:
        base = 8.0
        notes_parts.append("Full label disclosure")
    elif "mostly" in transparency_lower:
        base = 7.0
        notes_parts.append("Mostly transparent labeling")
    elif "partial" in transparency_lower:
        base = 5.5
        notes_parts.append("Partial label disclosure")
    elif "proprietary" in transparency_lower:
        base = 3.0
        notes_parts.append("Uses proprietary blends — doses hidden")
    else:
        base = 5.5
        notes_parts.append("Label transparency unclear")

    # Third-party testing bonus
    if lab_tested:
        base += 1.5
        body_text = lab_body or "third party"
        notes_parts.append(f"Lab tested by {body_text}")
    else:
        notes_parts.append("No third-party lab testing data available")

    # Check if ingredient doses are all disclosed
    if ingredients_structured:
        with_dose = sum(1 for i in ingredients_structured if i.get("claimed_dose"))
        total = len(ingredients_structured)
        if total > 0:
            ratio = with_dose / total
            if ratio >= 0.9:
                base += 0.5
                notes_parts.append("All key ingredient doses disclosed")
            elif ratio < 0.5:
                base -= 0.5
                notes_parts.append(f"Only {with_dose}/{total} ingredient doses disclosed")

    score = round(max(1.0, min(10.0, base)), 1)
    return score, ". ".join(notes_parts)


def calculate_overall(formula: float, dosing: float, value: float,
                      transparency: float) -> float:
    """Weighted overall score."""
    overall = (formula * 0.30) + (dosing * 0.30) + (value * 0.20) + (transparency * 0.20)
    return round(overall, 1)


def determine_verdict(overall: float) -> str:
    """Map overall score to verdict label."""
    if overall >= 8.0:
        return "Recommended"
    elif overall >= 7.5:
        return "Recommended"
    elif overall >= 5.0:
        return "Average"
    else:
        return "Skip"


# ── Pipeline ──────────────────────────────────────────────────────────

def score_product(product_record: dict, research_records: list,
                  airtable: AirtableClient, dry_run: bool = False) -> bool:
    """Score one product. Returns True on success."""
    fields = product_record.get("fields", {})
    product_id = product_record["id"]
    product_name = fields.get("Product Name", "Unknown")
    brand = fields.get("Brand", "")
    category = fields.get("Category", "") or fields.get("Subcategory", "")
    cost_per_serving = 0

    # Try to get cost per serving from product fields
    cost_raw = fields.get("Cost Per Serving", "")
    if cost_raw:
        cost_match = re.search(r'(\d+\.?\d*)', str(cost_raw))
        if cost_match:
            cost_per_serving = float(cost_match.group(1))

    log.info(f"{'[DRY RUN] ' if dry_run else ''}Scoring: {brand} — {product_name}")

    # Find Raw Research record
    research = None
    for rr in research_records:
        rr_products = rr.get("fields", {}).get("Product", [])
        if product_id in rr_products:
            research = rr.get("fields", {})
            break

    if not research:
        log.warning(f"  No Raw Research record found")
        return False

    # Parse structured ingredients
    ingredients_json = research.get("Ingredients Structured", "[]")
    try:
        ingredients = json.loads(ingredients_json) if ingredients_json else []
    except json.JSONDecodeError:
        ingredients = []
        log.warning(f"  Could not parse Ingredients Structured JSON")

    amazon_rating = float(research.get("Amazon Rating", 0) or 0)
    lab_tested = bool(research.get("Third Party Lab Tested", False))
    lab_body = research.get("Lab Testing Body", "")
    label_transparency = research.get("Label Transparency", "")

    # ── Score each dimension (category-aware) ──

    s_formula, n_formula = score_formula(ingredients, research, category)
    log.info(f"  Formula:      {s_formula}/10 — {n_formula}")

    s_dosing, n_dosing = score_dosing(ingredients, category)
    log.info(f"  Dosing:       {s_dosing}/10 — {n_dosing}")

    s_value, n_value = score_value(cost_per_serving, category, amazon_rating)
    log.info(f"  Value:        {s_value}/10 — {n_value}")

    s_transparency, n_transparency = score_transparency(
        label_transparency, lab_tested, lab_body, ingredients
    )
    log.info(f"  Transparency: {s_transparency}/10 — {n_transparency}")

    overall = calculate_overall(s_formula, s_dosing, s_value, s_transparency)
    verdict = determine_verdict(overall)

    log.info(f"  ─────────────────────")
    log.info(f"  Overall:      {overall}/10 → {verdict}")

    # ── Low Score Data Verification Flag ──
    # Products scoring below 5.0 need manual data verification before publishing
    needs_verification = overall < 5.0
    if needs_verification:
        log.warning(f"  ⚠️  LOW SCORE ({overall}/10) — flagging for data verification")

    scoring_notes = (
        f"Formula ({s_formula}): {n_formula}. "
        f"Dosing ({s_dosing}): {n_dosing}. "
        f"Value ({s_value}): {n_value}. "
        f"Transparency ({s_transparency}): {n_transparency}."
    )

    if dry_run:
        return True

    # Write to Airtable
    try:
        # Create Scores record
        score_fields = {
            "Product": [product_id],
            "Score Formula": s_formula,
            "Score Dosing": s_dosing,
            "Score Value": s_value,
            "Score Transparency": s_transparency,
            "Score Overall": overall,
            "Verdict": verdict,
            "Scoring Notes": scoring_notes[:2000],
            "Score Version": 1,
        }
        airtable.create_record(TBL_SCORES, score_fields)
        log.info("  ✓ Scores record created")

        # Update product status
        # Low scores still go to "Scoring Complete" but get flagged in notes
        new_status = "Scoring Complete"
        log.info("  ✓ Product status → Scoring Complete")
        
        update_fields = {"Review Status": new_status}
        
        # Add verification flag for low scores in a notes field if one exists
        if needs_verification:
            log.warning("  ⚠️  Flagged: LOW SCORE needs data verification before publishing")
        
        airtable.update_record(TBL_PRODUCTS, product_id, update_fields)

        # Agent log
        airtable.create_record(TBL_AGENT_LOG, {
            "Agent": "Scoring Agent",
            "Action": "score_product",
            "Status": "Success",
            "Input Summary": f"{brand} — {product_name}",
            "Output Summary": f"Overall: {overall}/10, Verdict: {verdict}",
            "Tokens Used": 0,
        })

        return True

    except Exception as e:
        log.error(f"  ✗ Airtable write failed: {e}")
        try:
            airtable.create_record(TBL_AGENT_LOG, {
                "Agent": "Scoring Agent",
                "Action": "score_product",
                "Status": "Failed",
                "Input Summary": f"{brand} — {product_name}",
                "Error Details": str(e)[:500],
            })
        except:
            pass
        return False


# ── Main ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Limitless Labs Scoring Agent")
    parser.add_argument("--product", help="Score a specific product by name")
    parser.add_argument("--dry-run", action="store_true", help="Calculate but don't write")
    parser.add_argument("--limit", type=int, default=10, help="Max products to process")
    args = parser.parse_args()

    if not AIRTABLE_TOKEN and not args.dry_run:
        log.error("AIRTABLE_TOKEN not set. Run: export AIRTABLE_TOKEN='pat_...'")
        sys.exit(1)

    airtable = AirtableClient(AIRTABLE_TOKEN, AIRTABLE_BASE_ID)

    # Get products
    if args.product:
        formula = f"SEARCH(LOWER('{args.product.lower()}'), LOWER({{Product Name}}))"
        products = airtable.list_records(TBL_PRODUCTS, formula=formula, max_records=1)
        if not products:
            log.error(f"Product not found: {args.product}")
            sys.exit(1)
    else:
        formula = "{Review Status} = 'Scoring'"
        products = airtable.list_records(TBL_PRODUCTS, formula=formula, max_records=args.limit)

    if not products:
        log.info("No products to score. None at 'Scoring' status.")
        return

    log.info(f"Found {len(products)} product(s) to score.\n")

    # Load Raw Research
    research_records = airtable.list_records(TBL_RAW_RESEARCH, max_records=500)
    log.info(f"Loaded {len(research_records)} Raw Research records.\n")

    success = 0
    failed = 0

    for product in products:
        try:
            ok = score_product(product, research_records, airtable, dry_run=args.dry_run)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            failed += 1
        time.sleep(0.5)

    log.info(f"\n{'=' * 50}")
    log.info(f"Done. {success} scored, {failed} failed.")


if __name__ == "__main__":
    main()
