#!/usr/bin/env python3
"""
Clean up duplicate score records in Airtable.
For each product, keeps only the most recent score (by Created date).
"""

import os
import requests
import time
from collections import defaultdict

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN") or os.environ.get("AIRTABLE_PAT")
BASE_ID = "appUOcZUDNPzstZlv"
SCORES_TABLE = "tblRux91YMnOB7okG"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}


def fetch_all_scores():
    """Fetch all score records"""
    all_records = []
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
            print(f"Error fetching scores: {resp.text}")
            break
            
        data = resp.json()
        all_records.extend(data.get("records", []))
        
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    
    return all_records


def delete_record(record_id):
    """Delete a single record"""
    resp = requests.delete(
        f"https://api.airtable.com/v0/{BASE_ID}/{SCORES_TABLE}/{record_id}",
        headers=HEADERS
    )
    return resp.status_code == 200


def main():
    if not AIRTABLE_TOKEN:
        print("Error: AIRTABLE_TOKEN not set")
        return
    
    print("Fetching all score records...")
    scores = fetch_all_scores()
    print(f"Found {len(scores)} total score records\n")
    
    # Group by product
    by_product = defaultdict(list)
    for rec in scores:
        fields = rec.get("fields", {})
        product_ids = fields.get("Product", [])
        created = rec.get("createdTime", "")
        
        if product_ids:
            product_id = product_ids[0]
            by_product[product_id].append({
                "record_id": rec["id"],
                "created": created,
                "score": fields.get("Score Overall", "?"),
                "verdict": fields.get("Verdict", "?"),
            })
    
    # Find products with duplicates
    duplicates_to_delete = []
    
    for product_id, records in by_product.items():
        if len(records) > 1:
            # Sort by created descending (newest first)
            sorted_recs = sorted(records, key=lambda x: x["created"], reverse=True)
            
            # Keep the newest (first), mark rest for deletion
            keep = sorted_recs[0]
            to_delete = sorted_recs[1:]
            
            print(f"Product {product_id[:12]}... has {len(records)} scores:")
            print(f"  KEEP:   {keep['score']}/10 ({keep['verdict']}) — {keep['created']}")
            for d in to_delete:
                print(f"  DELETE: {d['score']}/10 ({d['verdict']}) — {d['created']}")
                duplicates_to_delete.append(d["record_id"])
            print()
    
    if not duplicates_to_delete:
        print("No duplicates found. All clean!")
        return
    
    print(f"\nDeleting {len(duplicates_to_delete)} duplicate record(s)...\n")
    
    deleted = 0
    failed = 0
    
    for record_id in duplicates_to_delete:
        if delete_record(record_id):
            print(f"  ✓ Deleted {record_id}")
            deleted += 1
        else:
            print(f"  ✗ Failed to delete {record_id}")
            failed += 1
        time.sleep(0.25)  # Rate limit
    
    print(f"\nDone. {deleted} deleted, {failed} failed.")


if __name__ == "__main__":
    main()
