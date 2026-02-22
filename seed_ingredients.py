#!/usr/bin/env python3
"""
Seed the Ingredients Library with common supplement ingredients and clinical benchmarks.
"""
import os
import requests
import json

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN") or os.environ.get("AIRTABLE_PAT")
BASE_ID = "appUOcZUDNPzstZlv"
TABLE_ID = "tblTZVtWXvNWsgxTL"  # Ingredients Library

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# Clinical benchmark data for common supplement ingredients
INGREDIENTS = [
    # Protein
    {
        "Ingredient Name": "Whey Protein",
        "Category": "Protein",
        "What It Does": "Complete protein source for muscle protein synthesis. Contains all essential amino acids including high leucine content.",
        "Who It's For": "Athletes, bodybuilders, anyone needing convenient protein",
        "Effective Dose Low": "20g",
        "Effective Dose High": "40g",
        "Clinical Evidence": "Strong",
        "Common Forms": "Concentrate, Isolate, Hydrolysate",
        "Best Form": "Isolate (>90% protein, low lactose)",
    },
    {
        "Ingredient Name": "Casein",
        "Category": "Protein",
        "What It Does": "Slow-digesting protein for sustained amino acid release. Ideal for overnight muscle recovery.",
        "Who It's For": "Those seeking sustained protein release, nighttime use",
        "Effective Dose Low": "20g",
        "Effective Dose High": "40g",
        "Clinical Evidence": "Strong",
        "Common Forms": "Micellar Casein, Calcium Caseinate",
        "Best Form": "Micellar Casein",
    },
    {
        "Ingredient Name": "Pea Protein",
        "Category": "Protein",
        "What It Does": "Plant-based complete protein with good BCAA profile. Hypoallergenic alternative to dairy.",
        "Who It's For": "Vegans, those with dairy allergies",
        "Effective Dose Low": "20g",
        "Effective Dose High": "40g",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Isolate",
        "Best Form": "Isolate",
    },
    # Caffeine & Energy
    {
        "Ingredient Name": "Caffeine",
        "Category": "Caffeine & Energy",
        "What It Does": "Central nervous system stimulant. Increases alertness, reduces perceived exertion, enhances focus.",
        "Who It's For": "Those seeking energy, focus, or exercise performance boost",
        "Effective Dose Low": "100mg",
        "Effective Dose High": "400mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Anhydrous, Natural (from green tea/coffee)",
        "Best Form": "Anhydrous for precise dosing",
    },
    {
        "Ingredient Name": "L-Theanine",
        "Category": "Caffeine & Energy",
        "What It Does": "Promotes relaxation without drowsiness. Synergizes with caffeine for smooth focus.",
        "Who It's For": "Those seeking calm focus, pairs well with caffeine",
        "Effective Dose Low": "100mg",
        "Effective Dose High": "200mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "L-Theanine",
        "Best Form": "Suntheanine (patented form)",
    },
    {
        "Ingredient Name": "L-Carnitine",
        "Category": "Caffeine & Energy",
        "What It Does": "Transports fatty acids into mitochondria for energy production. May support fat metabolism.",
        "Who It's For": "Those seeking fat metabolism support, endurance athletes",
        "Effective Dose Low": "1000mg",
        "Effective Dose High": "3000mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "L-Carnitine Tartrate, Acetyl-L-Carnitine, Carnipure",
        "Best Form": "Carnipure L-Carnitine Tartrate",
    },
    # Pre-Workout
    {
        "Ingredient Name": "Citrulline",
        "Category": "Pre-Workout",
        "What It Does": "Increases nitric oxide production, enhances blood flow, reduces fatigue during exercise.",
        "Who It's For": "Athletes seeking pump, endurance, and recovery",
        "Effective Dose Low": "3000mg",
        "Effective Dose High": "8000mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "L-Citrulline, Citrulline Malate (2:1)",
        "Best Form": "L-Citrulline or Citrulline Malate 2:1",
    },
    {
        "Ingredient Name": "Beta-Alanine",
        "Category": "Pre-Workout",
        "What It Does": "Buffers lactic acid, delays muscle fatigue during high-intensity exercise.",
        "Who It's For": "Athletes doing high-intensity interval training",
        "Effective Dose Low": "2000mg",
        "Effective Dose High": "5000mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Beta-Alanine, CarnoSyn",
        "Best Form": "CarnoSyn (patented, tested)",
    },
    {
        "Ingredient Name": "Creatine Monohydrate",
        "Category": "Pre-Workout",
        "What It Does": "Increases phosphocreatine stores for ATP regeneration. Enhances strength, power, muscle gain.",
        "Who It's For": "Strength athletes, anyone seeking muscle/strength gains",
        "Effective Dose Low": "3000mg",
        "Effective Dose High": "5000mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Monohydrate, HCL, Buffered",
        "Best Form": "Creapure Monohydrate",
    },
    {
        "Ingredient Name": "Arginine",
        "Category": "Pre-Workout",
        "What It Does": "Precursor to nitric oxide. May enhance blood flow (though citrulline is more effective).",
        "Who It's For": "Those seeking vasodilation/pump",
        "Effective Dose Low": "3000mg",
        "Effective Dose High": "6000mg",
        "Clinical Evidence": "Limited",
        "Common Forms": "L-Arginine, AAKG",
        "Best Form": "L-Arginine (citrulline preferred)",
    },
    {
        "Ingredient Name": "Betaine",
        "Category": "Pre-Workout",
        "What It Does": "May enhance power output and muscle endurance. Supports methylation.",
        "Who It's For": "Strength and power athletes",
        "Effective Dose Low": "1500mg",
        "Effective Dose High": "2500mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Betaine Anhydrous, TMG",
        "Best Form": "Betaine Anhydrous",
    },
    # Nootropics
    {
        "Ingredient Name": "Lion's Mane",
        "Category": "Nootropics",
        "What It Does": "Supports nerve growth factor (NGF). May enhance cognitive function and neuroprotection.",
        "Who It's For": "Those seeking cognitive enhancement, brain health",
        "Effective Dose Low": "500mg",
        "Effective Dose High": "3000mg",
        "Clinical Evidence": "Emerging",
        "Common Forms": "Fruiting body extract, Mycelium",
        "Best Form": "Fruiting body extract (>30% beta-glucans)",
    },
    {
        "Ingredient Name": "Bacopa Monnieri",
        "Category": "Nootropics",
        "What It Does": "Adaptogenic herb that may improve memory formation and reduce anxiety.",
        "Who It's For": "Students, those seeking memory enhancement",
        "Effective Dose Low": "300mg",
        "Effective Dose High": "600mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Standardized extract (bacosides)",
        "Best Form": "Standardized to 50% bacosides",
    },
    {
        "Ingredient Name": "Alpha-GPC",
        "Category": "Nootropics",
        "What It Does": "Choline source that crosses blood-brain barrier. Supports acetylcholine synthesis.",
        "Who It's For": "Those seeking cognitive enhancement, focus",
        "Effective Dose Low": "300mg",
        "Effective Dose High": "600mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Alpha-GPC 50%",
        "Best Form": "Alpha-GPC 50%",
    },
    {
        "Ingredient Name": "Phosphatidylserine",
        "Category": "Nootropics",
        "What It Does": "Phospholipid that supports cell membrane integrity. May reduce cortisol and enhance cognition.",
        "Who It's For": "Those seeking stress reduction, cognitive support",
        "Effective Dose Low": "100mg",
        "Effective Dose High": "300mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Soy-derived, Sunflower-derived",
        "Best Form": "Sunflower-derived (allergen-free)",
    },
    # Sleep & Recovery
    {
        "Ingredient Name": "Melatonin",
        "Category": "Sleep & Recovery",
        "What It Does": "Hormone that regulates sleep-wake cycle. Helps with sleep onset and jet lag.",
        "Who It's For": "Those with sleep issues, travelers",
        "Effective Dose Low": "0.5mg",
        "Effective Dose High": "5mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Immediate release, Extended release",
        "Best Form": "Immediate release for sleep onset",
    },
    {
        "Ingredient Name": "Magnesium",
        "Category": "Sleep & Recovery",
        "What It Does": "Essential mineral for 300+ enzymatic reactions. Supports sleep, muscle relaxation, recovery.",
        "Who It's For": "Most adults (common deficiency), athletes",
        "Effective Dose Low": "200mg",
        "Effective Dose High": "400mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Glycinate, Citrate, Oxide, Threonate",
        "Best Form": "Glycinate (high absorption, calming)",
    },
    {
        "Ingredient Name": "Zinc",
        "Category": "Sleep & Recovery",
        "What It Does": "Essential mineral for immune function, testosterone production, and recovery.",
        "Who It's For": "Athletes, those with deficiency, immune support",
        "Effective Dose Low": "15mg",
        "Effective Dose High": "30mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Picolinate, Citrate, Gluconate, Oxide",
        "Best Form": "Picolinate or Citrate",
    },
    {
        "Ingredient Name": "GABA",
        "Category": "Sleep & Recovery",
        "What It Does": "Inhibitory neurotransmitter. May promote relaxation (though oral bioavailability is debated).",
        "Who It's For": "Those seeking relaxation, sleep support",
        "Effective Dose Low": "100mg",
        "Effective Dose High": "750mg",
        "Clinical Evidence": "Limited",
        "Common Forms": "GABA, PharmaGABA",
        "Best Form": "PharmaGABA (fermented, may cross BBB better)",
    },
    {
        "Ingredient Name": "Glycine",
        "Category": "Sleep & Recovery",
        "What It Does": "Amino acid that may improve sleep quality by lowering body temperature.",
        "Who It's For": "Those seeking better sleep quality",
        "Effective Dose Low": "3000mg",
        "Effective Dose High": "5000mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Glycine powder",
        "Best Form": "Pure glycine",
    },
    # Adaptogens
    {
        "Ingredient Name": "Ashwagandha",
        "Category": "Adaptogens",
        "What It Does": "Adaptogen that reduces cortisol, anxiety. May enhance strength and testosterone in men.",
        "Who It's For": "Stressed individuals, athletes seeking recovery",
        "Effective Dose Low": "300mg",
        "Effective Dose High": "600mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Root extract, KSM-66, Sensoril",
        "Best Form": "KSM-66 (full-spectrum, most researched)",
    },
    {
        "Ingredient Name": "Rhodiola Rosea",
        "Category": "Adaptogens",
        "What It Does": "Adaptogen that may reduce fatigue and enhance mental performance under stress.",
        "Who It's For": "Those experiencing fatigue, mental stress",
        "Effective Dose Low": "200mg",
        "Effective Dose High": "600mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Standardized extract (rosavins/salidroside)",
        "Best Form": "3% rosavins, 1% salidroside",
    },
    {
        "Ingredient Name": "Panax Ginseng",
        "Category": "Adaptogens",
        "What It Does": "Traditional adaptogen that may enhance energy, cognition, and immune function.",
        "Who It's For": "Those seeking energy and vitality",
        "Effective Dose Low": "200mg",
        "Effective Dose High": "400mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Korean Red Ginseng, standardized extract",
        "Best Form": "Standardized to ginsenosides",
    },
    {
        "Ingredient Name": "Holy Basil (Tulsi)",
        "Category": "Adaptogens",
        "What It Does": "Adaptogenic herb that may reduce stress, anxiety, and support blood sugar balance.",
        "Who It's For": "Those seeking stress relief",
        "Effective Dose Low": "300mg",
        "Effective Dose High": "600mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "Leaf extract",
        "Best Form": "Standardized leaf extract",
    },
    # Vitamins & Minerals
    {
        "Ingredient Name": "Vitamin D3",
        "Category": "Vitamins & Minerals",
        "What It Does": "Essential for calcium absorption, bone health, immune function, mood regulation.",
        "Who It's For": "Most adults (widespread deficiency), those with limited sun exposure",
        "Effective Dose Low": "1000 IU",
        "Effective Dose High": "5000 IU",
        "Clinical Evidence": "Strong",
        "Common Forms": "D3 (cholecalciferol), D2 (ergocalciferol)",
        "Best Form": "D3 (more effective than D2)",
    },
    {
        "Ingredient Name": "Vitamin B12",
        "Category": "Vitamins & Minerals",
        "What It Does": "Essential for energy metabolism, nerve function, red blood cell formation.",
        "Who It's For": "Vegans, elderly, those with absorption issues",
        "Effective Dose Low": "500mcg",
        "Effective Dose High": "2500mcg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Cyanocobalamin, Methylcobalamin",
        "Best Form": "Methylcobalamin (active form)",
    },
    {
        "Ingredient Name": "Vitamin C",
        "Category": "Vitamins & Minerals",
        "What It Does": "Antioxidant, supports immune function, collagen synthesis, iron absorption.",
        "Who It's For": "General health, athletes, smokers",
        "Effective Dose Low": "500mg",
        "Effective Dose High": "2000mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Ascorbic acid, Sodium ascorbate, Liposomal",
        "Best Form": "Liposomal or buffered forms",
    },
    {
        "Ingredient Name": "Omega-3 (EPA/DHA)",
        "Category": "Vitamins & Minerals",
        "What It Does": "Essential fatty acids for brain health, heart health, reducing inflammation.",
        "Who It's For": "Most adults, especially those not eating fatty fish",
        "Effective Dose Low": "1000mg",
        "Effective Dose High": "3000mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Fish oil, Algae oil, Krill oil",
        "Best Form": "Triglyceride form fish oil or Algae (vegan)",
    },
    {
        "Ingredient Name": "Iron",
        "Category": "Vitamins & Minerals",
        "What It Does": "Essential for oxygen transport, energy production. Common deficiency in women.",
        "Who It's For": "Women, vegetarians, those with diagnosed deficiency",
        "Effective Dose Low": "18mg",
        "Effective Dose High": "45mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Ferrous sulfate, Ferrous bisglycinate, Heme iron",
        "Best Form": "Ferrous bisglycinate (gentle, well-absorbed)",
    },
    {
        "Ingredient Name": "Calcium",
        "Category": "Vitamins & Minerals",
        "What It Does": "Essential for bone health, muscle contraction, nerve signaling.",
        "Who It's For": "Those with low dairy intake, postmenopausal women",
        "Effective Dose Low": "500mg",
        "Effective Dose High": "1000mg",
        "Clinical Evidence": "Strong",
        "Common Forms": "Carbonate, Citrate, Hydroxyapatite",
        "Best Form": "Citrate (better absorbed, especially without food)",
    },
    {
        "Ingredient Name": "Vitamin K2",
        "Category": "Vitamins & Minerals",
        "What It Does": "Directs calcium to bones, away from arteries. Synergizes with D3 for bone health.",
        "Who It's For": "Those taking D3, seeking bone/cardiovascular health",
        "Effective Dose Low": "100mcg",
        "Effective Dose High": "200mcg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "MK-4, MK-7",
        "Best Form": "MK-7 (longer half-life)",
    },
    {
        "Ingredient Name": "B-Complex",
        "Category": "Vitamins & Minerals",
        "What It Does": "Group of 8 B vitamins essential for energy metabolism, nerve function, cell health.",
        "Who It's For": "Stressed individuals, vegetarians, those seeking energy support",
        "Effective Dose Low": "25mg B1/B2/B3",
        "Effective Dose High": "100mg B1/B2/B3",
        "Clinical Evidence": "Strong",
        "Common Forms": "Standard, Methylated/Active forms",
        "Best Form": "Methylated forms (for those with MTHFR variants)",
    },
    {
        "Ingredient Name": "Electrolytes",
        "Category": "Vitamins & Minerals",
        "What It Does": "Sodium, potassium, magnesium for hydration, muscle function, nerve signaling.",
        "Who It's For": "Athletes, those sweating heavily, keto dieters",
        "Effective Dose Low": "500mg sodium",
        "Effective Dose High": "2000mg sodium",
        "Clinical Evidence": "Strong",
        "Common Forms": "Tablets, powders, drinks",
        "Best Form": "Balanced ratio (sodium:potassium:magnesium)",
    },
    # Additional common ingredients
    {
        "Ingredient Name": "BCAAs",
        "Category": "Protein",
        "What It Does": "Branched-chain amino acids (leucine, isoleucine, valine). May reduce muscle soreness.",
        "Who It's For": "Fasted training, endurance athletes (though whole protein is generally preferred)",
        "Effective Dose Low": "5000mg",
        "Effective Dose High": "10000mg",
        "Clinical Evidence": "Moderate",
        "Common Forms": "2:1:1, 4:1:1, 8:1:1 ratios",
        "Best Form": "2:1:1 ratio (most researched)",
    },
    {
        "Ingredient Name": "Glutamine",
        "Category": "Sleep & Recovery",
        "What It Does": "Most abundant amino acid. May support gut health and immune function during intense training.",
        "Who It's For": "Endurance athletes, those with gut issues",
        "Effective Dose Low": "5000mg",
        "Effective Dose High": "10000mg",
        "Clinical Evidence": "Limited",
        "Common Forms": "L-Glutamine",
        "Best Form": "L-Glutamine powder",
    },
]


def get_existing_ingredients():
    """Fetch existing ingredient names to avoid duplicates."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    params = {"fields[]": "Ingredient Name"}
    resp = requests.get(url, headers=HEADERS, params=params)
    if resp.status_code != 200:
        print(f"Error fetching existing ingredients: {resp.text}")
        return set()
    
    existing = set()
    for record in resp.json().get("records", []):
        name = record.get("fields", {}).get("Ingredient Name", "")
        if name:
            existing.add(name.lower())
    return existing


def seed_ingredients():
    """Seed the Ingredients Library with benchmark data."""
    if not AIRTABLE_TOKEN:
        print("Error: AIRTABLE_TOKEN not set")
        return
    
    existing = get_existing_ingredients()
    print(f"Found {len(existing)} existing ingredients in library")
    
    added = 0
    skipped = 0
    
    for ing in INGREDIENTS:
        name = ing["Ingredient Name"]
        if name.lower() in existing:
            print(f"  Skipping {name} (already exists)")
            skipped += 1
            continue
        
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
        resp = requests.post(url, headers=HEADERS, json={"fields": ing})
        
        if resp.status_code == 200:
            print(f"  ✓ Added {name}")
            added += 1
        else:
            print(f"  ✗ Failed to add {name}: {resp.text[:100]}")
    
    print(f"\nDone. Added {added}, skipped {skipped} (already existed)")
    print(f"Ingredients Library now has {len(existing) + added} ingredients")


if __name__ == "__main__":
    seed_ingredients()
