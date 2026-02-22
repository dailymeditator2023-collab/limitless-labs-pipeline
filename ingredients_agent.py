#!/usr/bin/env python3
"""
Limitless Labs — Ingredients Agent
====================================
Reads raw ingredient data from the Raw Research table, checks each ingredient
against the Ingredients Library, structures the analysis, and writes it back.

If an ingredient is not in the library, it researches it via DuckDuckGo
and adds it to the library for future consistency.

Usage:
    python3 ingredients_agent.py                     # Process all "Research Complete" products
    python3 ingredients_agent.py --product "AS-IT-IS Whey"  # Process one product
    python3 ingredients_agent.py --dry-run            # Analyze but don't write to Airtable
"""

import os
import sys
import json
import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appUOcZUDNPzstZlv"

TBL_PRODUCTS         = "tblttA4xVbWsAav0B"
TBL_RAW_RESEARCH     = "tblC8NLwWuBrw5507"
TBL_INGREDIENTS_LIB  = "tblTZVtWXvNWsgxTL"
TBL_AGENT_LOG        = "tblcZh2gT8fv99GTK"

AIRTABLE_API = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingredients-agent")


# ── Airtable Client (shared with research_agent) ─────────────────────

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


# ── Ingredients Library Cache ─────────────────────────────────────────

class IngredientsLibrary:
    """
    In-memory cache of the Airtable Ingredients Library.
    Loads once at startup, adds new ingredients as they're discovered.
    """

    def __init__(self, airtable: AirtableClient):
        self.airtable = airtable
        self.cache = {}  # ingredient_name_lower -> record fields
        self._load()

    def _load(self):
        """Load all ingredients from Airtable into cache."""
        log.info("Loading Ingredients Library from Airtable...")
        records = self.airtable.list_records(TBL_INGREDIENTS_LIB, max_records=500)
        for rec in records:
            fields = rec.get("fields", {})
            name = fields.get("Ingredient Name", "").strip()
            if name:
                self.cache[name.lower()] = {
                    "record_id": rec["id"],
                    "name": name,
                    "what_it_does": fields.get("What It Does", ""),
                    "dose_low": fields.get("Effective Dose Low", ""),
                    "dose_high": fields.get("Effective Dose High", ""),
                    "clinical_evidence": fields.get("Clinical Evidence", ""),
                    "best_form": fields.get("Best Form", ""),
                    "pubmed_refs": fields.get("PubMed References", ""),
                    "notes": fields.get("Notes", ""),
                }
        log.info(f"  Loaded {len(self.cache)} ingredients")

    def lookup(self, ingredient_name: str) -> Optional[dict]:
        """
        Look up an ingredient. Tries exact match, then fuzzy match.
        Returns None if not found.
        """
        name_lower = ingredient_name.strip().lower()

        # Exact match
        if name_lower in self.cache:
            return self.cache[name_lower]

        # Fuzzy: check if any cached name is contained in the query or vice versa
        for key, val in self.cache.items():
            if key in name_lower or name_lower in key:
                return val

        # Common aliases
        aliases = {
            "whey protein concentrate": "whey protein",
            "whey protein isolate": "whey protein",
            "whey protein hydrolysate": "whey protein",
            "ksm-66": "ashwagandha",
            "ksm-66 ashwagandha": "ashwagandha",
            "ashwagandha ksm-66": "ashwagandha",
            "sensoril ashwagandha": "ashwagandha",
            "caffeine anhydrous": "caffeine",
            "natural caffeine": "caffeine",
            "l-theanine": "theanine",
            "suntheanine": "theanine",
            "creatine monohydrate": "creatine",
            "creapure creatine": "creatine",
            "micronized creatine": "creatine",
            "melatonin": "melatonin",
            "vitamin d3": "vitamin d",
            "cholecalciferol": "vitamin d",
            "fish oil": "omega-3",
            "omega-3 fatty acids": "omega-3",
            "epa": "omega-3",
            "dha": "omega-3",
            "bcaa": "bcaas",
            "branched chain amino acids": "bcaas",
            "l-leucine": "leucine",
            "beta-alanine": "beta alanine",
            "citrulline malate": "citrulline",
            "l-citrulline": "citrulline",
        }

        resolved = aliases.get(name_lower, "")
        if resolved and resolved in self.cache:
            return self.cache[resolved]

        return None

    def add_ingredient(self, name: str, data: dict, write_to_airtable: bool = True) -> dict:
        """Add a new ingredient to the library."""
        entry = {
            "name": name,
            "what_it_does": data.get("what_it_does", ""),
            "dose_low": data.get("dose_low", ""),
            "dose_high": data.get("dose_high", ""),
            "clinical_evidence": data.get("clinical_evidence", "Emerging"),
            "best_form": data.get("best_form", ""),
            "pubmed_refs": data.get("pubmed_refs", ""),
            "notes": data.get("notes", "Auto-added by Ingredients Agent"),
        }

        if write_to_airtable:
            try:
                airtable_fields = {
                    "Ingredient Name": name,
                    "What It Does": entry["what_it_does"],
                    "Effective Dose Low": entry["dose_low"],
                    "Effective Dose High": entry["dose_high"],
                    "Clinical Evidence": entry["clinical_evidence"],
                    "Best Form": entry["best_form"],
                    "PubMed References": entry["pubmed_refs"],
                    "Notes": entry["notes"],
                }
                result = self.airtable.create_record(TBL_INGREDIENTS_LIB, airtable_fields)
                entry["record_id"] = result["id"]
                log.info(f"  ✓ Added to Ingredients Library: {name}")
            except Exception as e:
                log.warning(f"  ✗ Failed to add {name} to library: {e}")

        self.cache[name.lower()] = entry
        return entry


# ── Ingredient Parser ─────────────────────────────────────────────────

def clean_ingredient_name(name: str) -> str:
    """Clean markdown formatting and normalize ingredient names."""
    if not name:
        return ""
    
    # Remove markdown formatting
    name = re.sub(r'\*\*|\*|__|_', '', name)  # Bold/italic markers
    name = re.sub(r'^#+\s*', '', name)  # Headers
    name = re.sub(r'^\s*[-•·]\s*', '', name)  # Bullet points
    name = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', name)  # Links
    
    # Remove common prefixes that aren't ingredient names
    name = re.sub(r'^(SERVING SIZE|SERVINGS|PER SERVING|PER CONTAINER|NUMBER OF|NUTRIENTS|ALLERGEN|OTHER INGREDIENTS|DIRECTIONS|STORAGE|WARNINGS?)[:,]?\s*', '', name, flags=re.IGNORECASE)
    
    # Remove trailing colons
    name = re.sub(r':+\s*$', '', name).strip()
    
    # Canonical name mapping for common variations
    canonical_map = {
        'total protein': 'Protein',
        'protein': 'Protein',
        'whey protein': 'Whey Protein',
        'whey protein isolate': 'Whey Protein Isolate',
        'whey protein concentrate': 'Whey Protein Concentrate',
        'plant protein': 'Plant Protein',
        'pea protein': 'Pea Protein',
        'total carbohydrates': 'Carbohydrates',
        'carbohydrate': 'Carbohydrates',
        'total sugars': 'Sugar',
        'total sugar': 'Sugar',
        'added sugars': 'Added Sugar',
        'added sugar': 'Added Sugar',
        'dietary fiber': 'Fiber',
        'dietary fibre': 'Fiber',
        'total fat': 'Fat',
        'saturated fat': 'Saturated Fat',
        'trans fat': 'Trans Fat',
        'energy value': 'Calories',
        'energy': 'Calories',
        'calories': 'Calories',
        'vitamin a': 'Vitamin A',
        'vitamin c': 'Vitamin C',
        'vitamin d': 'Vitamin D',
        'vitamin d3': 'Vitamin D3',
        'vitamin e': 'Vitamin E',
        'vitamin k': 'Vitamin K',
        'vitamin b1': 'Vitamin B1',
        'vitamin b2': 'Vitamin B2',
        'vitamin b3': 'Vitamin B3',
        'vitamin b5': 'Vitamin B5',
        'vitamin b6': 'Vitamin B6',
        'vitamin b12': 'Vitamin B12',
        'thiamine': 'Vitamin B1',
        'riboflavin': 'Vitamin B2',
        'niacin': 'Vitamin B3',
        'pantothenic acid': 'Vitamin B5',
        'pyridoxine': 'Vitamin B6',
        'cobalamin': 'Vitamin B12',
        'folic acid': 'Folate',
        'folate': 'Folate',
        'l-carnitine': 'L-Carnitine',
        'l-carnitine tartrate': 'L-Carnitine',
        'caffeine anhydrous': 'Caffeine',
        'caffeine': 'Caffeine',
    }
    
    # Try canonical mapping
    name_lower = name.lower().strip()
    if name_lower in canonical_map:
        return canonical_map[name_lower]
    
    return name.strip()


def parse_ingredients_raw(raw_text: str) -> list:
    """
    Parse raw ingredient text (from Amazon scrape) into a list of
    {name, claimed_dose} dicts.

    Handles common formats:
    - "Whey Protein Concentrate 30g"
    - "Ashwagandha KSM-66 (600mg)"
    - "Caffeine 200mg | L-Theanine 100mg"
    - Bullet-separated Amazon descriptions
    """
    ingredients = []
    if not raw_text:
        return ingredients

    # Pre-clean: remove markdown section headers that aren't ingredients
    raw_text = re.sub(r'\*\*(SERVING SIZE|SERVINGS|PER SERVING|PER CONTAINER|NUMBER OF|NUTRIENTS|ALLERGEN|OTHER INGREDIENTS|VITAMINS|MINERALS|AMINO ACID)[^*]*\*\*:?', '', raw_text, flags=re.IGNORECASE)
    
    # Split by common delimiters
    parts = re.split(r'[|•·,;]|\n', raw_text)

    for part in parts:
        part = part.strip()
        if not part or len(part) < 3:
            continue

        # Skip non-ingredient text
        skip_patterns = [
            r"^(see more|about this|item|product|brand|visit|disclaimer)",
            r"^(free|fast|delivery|ship|return|refund|warranty)",
            r"^(how to use|direction|storage|best before|mfg|exp)",
            r"^(country of origin|manufacturer|marketed by|imported by)",
            r"^[\d]+\s*(star|rating|review|customer)",
        ]
        if any(re.match(p, part.lower()) for p in skip_patterns):
            continue

        # Try to extract ingredient name and dose
        # Pattern: "IngredientName 500mg" or "IngredientName (500mg)"
        dose_match = re.search(
            r'(\d+\.?\d*)\s*(mg|g|mcg|iu|ml|μg|billion cfu|capsule|tablet)',
            part, re.IGNORECASE
        )

        if dose_match:
            dose = dose_match.group(0)
            # Name is everything before the dose
            name = part[:dose_match.start()].strip().rstrip("-(")

            # Clean up: remove leading "Contains", "Provides", "With", "Added"
            name = re.sub(r'^(contains|provides|with|added|per serving of|per scoop of)\s+',
                          '', name, flags=re.IGNORECASE).strip()

            # If name is just a number or too short, try to get name from after the dose
            if not name or len(name) < 3:
                after = part[dose_match.end():].strip()
                # Remove leading "of", "per serving", "per scoop"
                after = re.sub(r'^(of|per\s+serving|per\s+scoop|per\s+capsule)\s*',
                               '', after, flags=re.IGNORECASE).strip()
                if after and len(after) > 2:
                    name = re.split(r'[,;|]', after)[0].strip()[:60]

            # Also clean trailing "per scoop", "per serving"
            name = re.sub(r'\s*(per\s+scoop|per\s+serving|per\s+capsule|per\s+tablet)\s*$',
                          '', name, flags=re.IGNORECASE).strip()

            if name and len(name) > 2:
                clean_name = clean_ingredient_name(name)
                if clean_name and len(clean_name) > 1:
                    ingredients.append({
                        "name": clean_name,
                        "claimed_dose": dose.strip(),
                    })
        else:
            # No dose found — might be a descriptive ingredient
            # Check if it looks like an ingredient name
            ingredient_signals = [
                "protein", "whey", "casein", "creatine", "caffeine", "theanine",
                "ashwagandha", "melatonin", "vitamin", "mineral", "omega",
                "fish oil", "collagen", "probiotic", "extract", "powder",
                "amino", "bcaa", "glutamine", "citrulline", "beta-alanine",
                "magnesium", "zinc", "iron", "calcium", "selenium",
                "biotin", "folate", "niacin", "riboflavin", "thiamine",
            ]
            if any(sig in part.lower() for sig in ingredient_signals):
                clean_name = clean_ingredient_name(part[:80])
                if clean_name and len(clean_name) > 1:
                    ingredients.append({
                        "name": clean_name,
                        "claimed_dose": "",
                    })

    # Deduplicate by name
    seen = set()
    unique = []
    for ing in ingredients:
        key = ing["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(ing)

    return unique[:20]  # Cap at 20 ingredients


# ── Ingredient Analyzer ───────────────────────────────────────────────

def analyze_ingredient(name: str, claimed_dose: str, library: IngredientsLibrary,
                       dry_run: bool = False) -> dict:
    """
    Analyze a single ingredient against the library.
    Returns structured assessment dict.
    """
    result = {
        "ingredient_name": name,
        "claimed_dose": claimed_dose,
        "clinical_benchmark": "",
        "assessment": "Unknown",
        "notes": "",
    }

    # Look up in library
    lib_entry = library.lookup(name)

    if lib_entry:
        dose_low = lib_entry.get("dose_low", "")
        dose_high = lib_entry.get("dose_high", "")

        if dose_low and dose_high:
            result["clinical_benchmark"] = f"{dose_low}–{dose_high}"
        elif dose_low:
            result["clinical_benchmark"] = f"{dose_low}+"
        elif dose_high:
            result["clinical_benchmark"] = f"Up to {dose_high}"

        # Assess if claimed dose meets benchmark
        if claimed_dose and dose_low:
            result["assessment"] = _assess_dose(claimed_dose, dose_low, dose_high)
        else:
            result["assessment"] = "Not Assessed"

        result["notes"] = lib_entry.get("notes", "")

        evidence = lib_entry.get("clinical_evidence", "")
        if evidence:
            result["notes"] = f"Evidence: {evidence}. {result['notes']}"

    else:
        # Ingredient not in library — research it
        log.info(f"    → {name} not in library, researching...")
        researched = _research_ingredient(name)

        if researched:
            # Add to library
            if not dry_run:
                library.add_ingredient(name, researched, write_to_airtable=True)
            else:
                library.add_ingredient(name, researched, write_to_airtable=False)

            result["clinical_benchmark"] = f"{researched.get('dose_low', '')}–{researched.get('dose_high', '')}"
            result["notes"] = researched.get("what_it_does", "")

            if claimed_dose and researched.get("dose_low"):
                result["assessment"] = _assess_dose(
                    claimed_dose, researched["dose_low"], researched.get("dose_high", "")
                )
            else:
                result["assessment"] = "Not Assessed"
        else:
            result["assessment"] = "No Data"
            result["notes"] = "Ingredient not found in library or web research"

    return result


def _assess_dose(claimed: str, benchmark_low: str, benchmark_high: str = "") -> str:
    """
    Compare claimed dose against clinical benchmark.
    Returns: "On Point" / "Under-dosed" / "Over-dosed" / "Not Assessed"
    """
    # Extract numeric value from claimed dose
    claimed_num = _extract_mg(claimed)
    low_num = _extract_mg(benchmark_low)
    high_num = _extract_mg(benchmark_high) if benchmark_high else low_num * 2

    if claimed_num <= 0 or low_num <= 0:
        return "Not Assessed"

    # Normalize units (convert g to mg if needed)
    if claimed_num < 1 and low_num > 100:
        claimed_num *= 1000  # Probably grams vs mg

    if claimed_num >= low_num * 0.8:  # Within 80% of low end
        if high_num > 0 and claimed_num > high_num * 1.5:
            return "Over-dosed"
        return "On Point"
    elif claimed_num >= low_num * 0.5:
        return "Slightly Under-dosed"
    else:
        return "Under-dosed"


def _extract_mg(text: str) -> float:
    """Extract numeric mg value from dose text like '600mg' or '2g'."""
    if not text:
        return 0

    text = str(text).strip()

    # Try to find number with unit
    match = re.search(r'(\d+\.?\d*)\s*(mg|g|mcg|iu|μg)', text, re.IGNORECASE)
    if match:
        num = float(match.group(1))
        unit = match.group(2).lower()
        if unit == 'g':
            return num * 1000
        elif unit in ('mcg', 'μg'):
            return num / 1000
        return num

    # Just a number
    match = re.search(r'(\d+\.?\d*)', text)
    if match:
        return float(match.group(1))

    return 0


# ── Web Research for Unknown Ingredients ──────────────────────────────

def _research_ingredient(name: str) -> Optional[dict]:
    """
    Research an unknown ingredient via DuckDuckGo.

    MVP: Simple web search for clinical dose info.
    UPGRADE: Replace with Perplexity API for better synthesis.
    """
    try:
        query = f"{name} supplement effective dose clinical research"
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(url, data={"q": query}, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        }, timeout=10)

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select(".result")

        combined_text = ""
        for r in results[:5]:
            snippet = r.select_one(".result__snippet")
            if snippet:
                combined_text += " " + snippet.get_text(strip=True)

        if not combined_text:
            return None

        # Try to extract dose information from search results
        data = {
            "what_it_does": "",
            "dose_low": "",
            "dose_high": "",
            "clinical_evidence": "Emerging",
            "best_form": "",
            "notes": f"Auto-researched. Source: web search for '{name}'",
        }

        # Look for dose patterns
        dose_patterns = [
            r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\s*(mg|g|mcg)',  # "200-400mg"
            r'effective\s+dose[:\s]+(\d+\.?\d*)\s*(mg|g|mcg)',      # "effective dose: 200mg"
            r'recommended[:\s]+(\d+\.?\d*)\s*(mg|g|mcg)',           # "recommended: 200mg"
            r'clinical\s+dose[:\s]+(\d+\.?\d*)\s*(mg|g|mcg)',       # "clinical dose: 200mg"
        ]

        for pattern in dose_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 3:
                    data["dose_low"] = f"{groups[0]}{groups[2]}"
                    data["dose_high"] = f"{groups[1]}{groups[2]}"
                elif len(groups) >= 2:
                    data["dose_low"] = f"{groups[0]}{groups[1]}"
                break

        # Extract what it does (first sentence-like chunk mentioning the ingredient)
        sentences = re.split(r'[.!]', combined_text)
        for s in sentences:
            s = s.strip()
            if name.lower().split()[0] in s.lower() and 10 < len(s) < 200:
                data["what_it_does"] = s[:200]
                break

        return data if data["dose_low"] else None

    except Exception as e:
        log.warning(f"    Web research failed for {name}: {e}")
        return None


# ── Pipeline ──────────────────────────────────────────────────────────

def process_product(product_record: dict, research_records: list,
                    library: IngredientsLibrary, airtable: AirtableClient,
                    dry_run: bool = False) -> bool:
    """
    Process one product's ingredients.
    Returns True on success.
    """
    fields = product_record.get("fields", {})
    product_id = product_record["id"]
    product_name = fields.get("Product Name", "Unknown")
    brand = fields.get("Brand", "")

    log.info(f"{'[DRY RUN] ' if dry_run else ''}Processing: {brand} — {product_name}")

    # Find the Raw Research record for this product
    research_record = None
    for rr in research_records:
        rr_products = rr.get("fields", {}).get("Product", [])
        if product_id in rr_products:
            research_record = rr
            break

    if not research_record:
        log.warning(f"  No Raw Research record found for {product_name}")
        return False

    # PRIORITY: Use Product Composition (from label extraction) if available
    # Fall back to Ingredients Raw (from web research) if not
    raw_ingredients = fields.get("Product Composition") or ""
    if raw_ingredients:
        log.info(f"  Using Product Composition ({len(raw_ingredients)} chars)")
    else:
        raw_ingredients = research_record.get("fields", {}).get("Ingredients Raw", "")
        if raw_ingredients:
            log.info(f"  Using Ingredients Raw (no Product Composition)")
    
    if not raw_ingredients:
        log.warning(f"  No ingredients data for {product_name}")
        return False

    # Parse raw ingredients
    parsed = parse_ingredients_raw(raw_ingredients)
    log.info(f"  Parsed {len(parsed)} ingredients from raw text")

    if not parsed:
        log.warning(f"  Could not parse any ingredients from: {raw_ingredients[:100]}...")
        return False

    # Analyze each ingredient
    structured = []
    for ing in parsed:
        log.info(f"  Analyzing: {ing['name']} ({ing['claimed_dose'] or 'no dose'})")
        analysis = analyze_ingredient(
            ing["name"], ing["claimed_dose"], library, dry_run=dry_run
        )
        structured.append(analysis)

    # Determine label transparency
    total = len(structured)
    with_dose = sum(1 for s in structured if s["claimed_dose"])
    if total > 0:
        dose_ratio = with_dose / total
        if dose_ratio >= 0.8:
            label_transparency = "Full Disclosure"
        elif dose_ratio >= 0.3:
            label_transparency = "Partial"
        else:
            label_transparency = "Proprietary Blend"
    else:
        label_transparency = "Proprietary Blend"

    structured_json = json.dumps(structured, indent=2)

    log.info(f"  Label transparency: {label_transparency}")
    log.info(f"  Assessments: {', '.join(s['assessment'] for s in structured)}")

    if dry_run:
        log.info(f"  [DRY RUN] Structured ingredients:")
        for s in structured:
            log.info(f"    {s['ingredient_name']}: {s['claimed_dose']} → "
                     f"{s['assessment']} (benchmark: {s['clinical_benchmark']})")
        return True

    # Write back to Airtable
    try:
        # Update Raw Research with structured ingredients
        airtable.update_record(TBL_RAW_RESEARCH, research_record["id"], {
            "Ingredients Structured": structured_json,
            "Label Transparency": label_transparency,
        })
        log.info("  ✓ Raw Research updated with structured ingredients")

        # Update product status
        airtable.update_record(TBL_PRODUCTS, product_id, {
            "Review Status": "Scoring",
        })
        log.info("  ✓ Product status → Ingredients Complete")

        # Agent log
        airtable.create_record(TBL_AGENT_LOG, {
            "Agent": "Ingredients Agent",
            "Action": "analyze_ingredients",
            "Status": "Success",
            "Input Summary": f"{brand} — {product_name} ({len(parsed)} ingredients)",
            "Output Summary": f"Transparency: {label_transparency}, "
                              f"Assessments: {sum(1 for s in structured if s['assessment'] == 'On Point')}/{total} on point",
            "Tokens Used": 0,
        })

        return True

    except Exception as e:
        log.error(f"  ✗ Airtable write failed: {e}")
        try:
            airtable.create_record(TBL_AGENT_LOG, {
                "Agent": "Ingredients Agent",
                "Action": "analyze_ingredients",
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
    parser = argparse.ArgumentParser(description="Limitless Labs Ingredients Agent")
    parser.add_argument("--product", help="Process a specific product by name")
    parser.add_argument("--dry-run", action="store_true", help="Analyze but don't write to Airtable")
    parser.add_argument("--limit", type=int, default=10, help="Max products to process")
    args = parser.parse_args()

    if not AIRTABLE_TOKEN and not args.dry_run:
        log.error("AIRTABLE_TOKEN not set. Run: export AIRTABLE_TOKEN='pat_...'")
        sys.exit(1)

    airtable = AirtableClient(AIRTABLE_TOKEN, AIRTABLE_BASE_ID)

    # Load ingredients library
    library = IngredientsLibrary(airtable)

    # Get products to process
    if args.product:
        formula = f"SEARCH(LOWER('{args.product.lower()}'), LOWER({{Product Name}}))"
        products = airtable.list_records(TBL_PRODUCTS, formula=formula, max_records=1)
        if not products:
            log.error(f"Product not found: {args.product}")
            sys.exit(1)
    else:
        formula = "{Review Status} = 'Research Complete'"
        products = airtable.list_records(TBL_PRODUCTS, formula=formula, max_records=args.limit)

    if not products:
        log.info("No products to process. None at 'Research Complete' status.")
        return

    log.info(f"Found {len(products)} product(s) to process.\n")

    # Load all Raw Research records (needed to find linked records)
    research_records = airtable.list_records(TBL_RAW_RESEARCH, max_records=500)
    log.info(f"Loaded {len(research_records)} Raw Research records.\n")

    success = 0
    failed = 0

    for product in products:
        try:
            ok = process_product(product, research_records, library, airtable, dry_run=args.dry_run)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            failed += 1
        time.sleep(1)

    log.info(f"\n{'=' * 50}")
    log.info(f"Done. {success} succeeded, {failed} failed.")
    log.info(f"Ingredients Library now has {len(library.cache)} ingredients.")


if __name__ == "__main__":
    main()
