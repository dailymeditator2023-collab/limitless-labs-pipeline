#!/usr/bin/env python3
"""
Batch re-score all products with composition data using the updated alias system.
Runs: ingredients_agent.py → scoring_agent.py for each product.
"""

import subprocess
import os
import sys
import time
import requests

# Config
BASE_ID = 'appUOcZUDNPzstZlv'
PRODUCTS_TABLE = 'tblttA4xVbWsAav0B'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_airtable_pat():
    pat = os.environ.get('AIRTABLE_PAT')
    if not pat:
        env_file = os.path.expanduser('~/clawd/.secrets/airtable.env')
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith('AIRTABLE_PAT='):
                        pat = line.split('=', 1)[1].strip().strip('"')
                        break
    return pat

def get_products_with_composition():
    """Fetch all products with composition data from Airtable."""
    pat = get_airtable_pat()
    headers = {'Authorization': f'Bearer {pat}'}
    url = f'https://api.airtable.com/v0/{BASE_ID}/{PRODUCTS_TABLE}'
    
    products = []
    offset = None
    while True:
        params = {'pageSize': 100}
        if offset:
            params['offset'] = offset
        resp = requests.get(url, headers=headers, params=params)
        data = resp.json()
        products.extend(data.get('records', []))
        offset = data.get('offset')
        if not offset:
            break
    
    # Filter to products with actual composition data
    result = []
    for p in products:
        fields = p.get('fields', {})
        composition = fields.get('Product Composition', '')
        name = fields.get('Product Name', 'Unknown')
        
        if composition and 'NO_LABEL_FOUND' not in composition:
            result.append({
                'id': p['id'],
                'name': name,
                'status': fields.get('Review Status', ''),
                'category': fields.get('Category', '')
            })
    
    return result

def run_agent(script_name, product_name):
    """Run an agent script for a specific product."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    
    env = os.environ.copy()
    # Load secrets
    for env_file in ['airtable.env', 'openai.env']:
        path = os.path.expanduser(f'~/clawd/.secrets/{env_file}')
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, val = line.strip().split('=', 1)
                        env[key] = val.strip('"')
    
    # Agents expect AIRTABLE_TOKEN, not AIRTABLE_PAT
    if 'AIRTABLE_PAT' in env and 'AIRTABLE_TOKEN' not in env:
        env['AIRTABLE_TOKEN'] = env['AIRTABLE_PAT']
    
    result = subprocess.run(
        ['python3', script_path, '--product', product_name],
        capture_output=True,
        text=True,
        env=env,
        timeout=120
    )
    
    return result.returncode == 0, result.stdout, result.stderr

def main():
    print("=" * 60)
    print("BATCH RE-SCORE: Running with new ingredient aliases")
    print("=" * 60)
    print()
    
    products = get_products_with_composition()
    print(f"Found {len(products)} products with composition data")
    print()
    
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    for i, product in enumerate(products, 1):
        name = product['name']
        print(f"[{i}/{len(products)}] {name}")
        
        # Run ingredients agent
        print(f"  → Running ingredients_agent.py...")
        success, stdout, stderr = run_agent('ingredients_agent.py', name)
        
        if not success:
            print(f"  ✗ Ingredients agent failed")
            if stderr:
                print(f"    Error: {stderr[:200]}")
            results['failed'].append((name, 'ingredients', stderr[:200] if stderr else 'Unknown error'))
            continue
        
        # Check for parsed ingredients
        if 'No ingredients parsed' in stdout or 'error' in stdout.lower():
            print(f"  ⚠ No ingredients parsed - skipping scoring")
            results['skipped'].append((name, 'No ingredients parsed'))
            continue
        
        # Run scoring agent
        print(f"  → Running scoring_agent.py...")
        success, stdout, stderr = run_agent('scoring_agent.py', name)
        
        if not success:
            print(f"  ✗ Scoring agent failed")
            results['failed'].append((name, 'scoring', stderr[:200] if stderr else 'Unknown error'))
            continue
        
        # Extract score from output
        score_line = [l for l in stdout.split('\n') if 'Overall:' in l or 'Overall Score:' in l]
        if score_line:
            print(f"  ✓ {score_line[0].strip()}")
        else:
            print(f"  ✓ Scored (see Airtable)")
        
        results['success'].append(name)
        
        # Brief delay between products
        time.sleep(1)
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✓ Success: {len(results['success'])}")
    print(f"⚠ Skipped: {len(results['skipped'])}")
    print(f"✗ Failed:  {len(results['failed'])}")
    print()
    
    if results['success']:
        print("Successful products:")
        for name in results['success']:
            print(f"  ✓ {name}")
    
    if results['skipped']:
        print("\nSkipped (no ingredients):")
        for name, reason in results['skipped']:
            print(f"  ⚠ {name}: {reason}")
    
    if results['failed']:
        print("\nFailed:")
        for name, stage, error in results['failed']:
            print(f"  ✗ {name} ({stage}): {error[:100]}")

if __name__ == '__main__':
    main()
