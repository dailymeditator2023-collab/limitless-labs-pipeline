#!/usr/bin/env python3
"""
Add RDA (Recommended Daily Allowance) benchmarks to ingredients library.
Uses Indian ICMR RDA values where available, otherwise international RDA.

Two-tier system:
- Effective Dose (therapeutic) — for standalone supplements
- RDA Dose — for multivitamins
"""

import os
import requests
import time

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = "appUOcZUDNPzstZlv"
TBL_INGREDIENTS = "tblTZVtWXvNWsgxTL"

headers = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

# ═══════════════════════════════════════════════════════════════════════════════
# RDA VALUES (Indian ICMR / International)
# Format: ingredient_name_lower -> (rda_low, rda_high)
# ═══════════════════════════════════════════════════════════════════════════════

RDA_VALUES = {
    # ── Vitamins ──
    "vitamin a": ("600mcg", "900mcg"),
    "vitamin b12": ("1mcg", "2.4mcg"),
    "b-complex": ("1mg", "2mg"),  # B1/B2 as reference
    "vitamin c": ("40mg", "90mg"),
    "vitamin d3": ("400IU", "800IU"),  # 10-20mcg
    "vitamin k2": ("55mcg", "120mcg"),
    
    # ── Minerals ──
    "calcium": ("600mg", "1000mg"),
    "magnesium": ("310mg", "420mg"),
    "zinc": ("8mg", "11mg"),
    "iron": ("8mg", "18mg"),
    
    # ── Omega-3 (general health RDA, not therapeutic) ──
    "omega-3 (epa/dha)": ("250mg", "500mg"),
    
    # ── Amino Acids (no RDA — use therapeutic) ──
    # BCAAs, Glutamine, etc. don't have RDA values
    
    # ── Adaptogens (no RDA — use therapeutic) ──
    # Ashwagandha, Rhodiola, etc. don't have official RDA
    
    # ── Other supplements without RDA ──
    # Creatine, Caffeine, etc. — no RDA, use therapeutic
}

# Additional vitamin forms that should map to base vitamin RDA
VITAMIN_ALIASES = {
    "vitamin b1": ("1.0mg", "1.2mg"),
    "vitamin b2": ("1.1mg", "1.3mg"),
    "vitamin b3": ("14mg", "16mg"),
    "vitamin b5": ("5mg", "5mg"),
    "vitamin b6": ("1.3mg", "1.7mg"),
    "vitamin b7": ("30mcg", "100mcg"),  # Biotin
    "vitamin b9": ("200mcg", "400mcg"),  # Folate
    "vitamin e": ("7.5mg", "15mg"),
    "vitamin k": ("55mcg", "120mcg"),
}

RDA_VALUES.update(VITAMIN_ALIASES)


def get_all_ingredients():
    """Fetch all ingredients from library."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_INGREDIENTS}"
    all_records = []
    offset = None
    
    while True:
        params = {"maxRecords": 100}
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params)
        data = r.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    
    return all_records


def update_ingredient_rda(record_id: str, rda_low: str, rda_high: str):
    """Add RDA values to an ingredient record."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TBL_INGREDIENTS}/{record_id}"
    fields = {
        "RDA Dose Low": rda_low,
        "RDA Dose High": rda_high,
    }
    r = requests.patch(url, headers=headers, json={"fields": fields})
    return r.status_code == 200


def main():
    print("=" * 60)
    print("ADDING RDA BENCHMARKS TO INGREDIENTS LIBRARY")
    print("=" * 60)
    
    ingredients = get_all_ingredients()
    print(f"\nFound {len(ingredients)} ingredients in library\n")
    
    updated = 0
    skipped = 0
    
    for rec in ingredients:
        fields = rec.get("fields", {})
        name = fields.get("Ingredient Name", "")
        name_lower = name.lower().strip()
        record_id = rec["id"]
        
        # Check if we have RDA values for this ingredient
        rda = RDA_VALUES.get(name_lower)
        
        if rda:
            rda_low, rda_high = rda
            success = update_ingredient_rda(record_id, rda_low, rda_high)
            if success:
                print(f"✓ {name}: RDA {rda_low} - {rda_high}")
                updated += 1
            else:
                print(f"✗ {name}: Failed to update")
            time.sleep(0.2)  # Rate limiting
        else:
            # No RDA for this ingredient (adaptogens, aminos, etc.)
            print(f"- {name}: No RDA (therapeutic only)")
            skipped += 1
    
    print(f"\n{'=' * 60}")
    print(f"Done. Updated: {updated}, Skipped (no RDA): {skipped}")
    print("=" * 60)


if __name__ == "__main__":
    main()
