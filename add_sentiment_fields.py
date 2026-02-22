#!/usr/bin/env python3
"""
Add new sentiment analysis fields to Airtable Raw Research table.
"""

import os
import requests
import time

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
BASE_ID = "appUOcZUDNPzstZlv"
RAW_RESEARCH_TABLE = "tblC8NLwWuBrw5507"

# New fields to add
NEW_FIELDS = [
    # Amazon sentiment fields
    {"name": "Amazon Star Distribution", "type": "singleLineText"},
    {"name": "Amazon Top Praised", "type": "singleLineText"},
    {"name": "Amazon Top Complaints", "type": "singleLineText"},
    {"name": "Amazon Recurring Themes", "type": "singleLineText"},
    {"name": "Amazon Suspicious Pattern", "type": "singleLineText"},
    {"name": "Amazon Helpful Reviews", "type": "multilineText"},
    # Reddit sentiment fields
    {"name": "Reddit Recommendations", "type": "singleLineText"},
    {"name": "Reddit Alternatives", "type": "singleLineText"},
    {"name": "Reddit Red Flags", "type": "singleLineText"},
    {"name": "Reddit Community Consensus", "type": "multilineText"},
]

def create_field(field_name, field_type):
    """Create a field in Airtable using the Metadata API"""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{RAW_RESEARCH_TABLE}/fields"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "name": field_name,
        "type": field_type,
    }
    
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        print(f"✓ Created: {field_name}")
        return True
    elif resp.status_code == 422 and "already exists" in resp.text.lower():
        print(f"→ Already exists: {field_name}")
        return True
    else:
        print(f"✗ Failed: {field_name} — {resp.status_code}: {resp.text[:100]}")
        return False


def main():
    if not AIRTABLE_TOKEN:
        print("Error: AIRTABLE_TOKEN not set")
        return
    
    print("Adding new sentiment fields to Airtable Raw Research table...\n")
    
    success = 0
    failed = 0
    
    for field in NEW_FIELDS:
        if create_field(field["name"], field["type"]):
            success += 1
        else:
            failed += 1
        time.sleep(0.3)  # Rate limit
    
    print(f"\nDone. {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
