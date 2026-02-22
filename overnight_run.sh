#!/bin/bash
cd ~/clawd/scripts/research-agent

# Load secrets
set -a
. ~/clawd/.secrets/airtable.env
. ~/clawd/.secrets/openai.env
set +a

# Map AIRTABLE_PAT to AIRTABLE_TOKEN if needed
export AIRTABLE_TOKEN="${AIRTABLE_TOKEN:-$AIRTABLE_PAT}"

echo "Started at $(date)" > ~/overnight_log.txt
echo "AIRTABLE_TOKEN set: ${AIRTABLE_TOKEN:0:10}..." >> ~/overnight_log.txt
echo "OPENAI_API_KEY set: ${OPENAI_API_KEY:0:10}..." >> ~/overnight_log.txt

echo "=== COMPOSITION EXTRACTOR ===" >> ~/overnight_log.txt
python3 composition_extractor.py --limit 50 2>&1 | tee -a ~/overnight_log.txt

echo "=== INGREDIENTS AGENT ===" >> ~/overnight_log.txt
python3 ingredients_agent.py --limit 30 2>&1 | tee -a ~/overnight_log.txt

echo "=== SCORING AGENT ===" >> ~/overnight_log.txt
python3 scoring_agent.py --limit 30 2>&1 | tee -a ~/overnight_log.txt

echo "=== WRITING AGENT ===" >> ~/overnight_log.txt
python3 writing_agent.py --limit 30 2>&1 | tee -a ~/overnight_log.txt

echo "=== GENERATING SUMMARY ===" >> ~/overnight_log.txt
python3 -c "
import os, requests
TOKEN = os.environ['AIRTABLE_TOKEN']
BASE = 'appUOcZUDNPzstZlv'
TABLE = 'tblttA4xVbWsAav0B'
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}
all_records = []
offset = None
while True:
    params = {'maxRecords': 100}
    if offset: params['offset'] = offset
    resp = requests.get(f'https://api.airtable.com/v0/{BASE}/{TABLE}', headers=HEADERS, params=params)
    data = resp.json()
    all_records.extend(data.get('records', []))
    offset = data.get('offset')
    if not offset: break
print(f'Total products: {len(all_records)}')
statuses = {}
sources = {}
for rec in all_records:
    f = rec.get('fields', {})
    s = f.get('Review Status', 'Unknown')
    src = f.get('Composition Source', 'None')
    statuses[s] = statuses.get(s, 0) + 1
    sources[src] = sources.get(src, 0) + 1
print('  Review Status:')
for k, v in sorted(statuses.items(), key=lambda x: -x[1]): print(f'    {k}: {v}')
print('  Composition Source:')
for k, v in sorted(sources.items(), key=lambda x: -x[1]): print(f'    {k}: {v}')
" > ~/overnight_summary.txt 2>&1

cat ~/overnight_summary.txt >> ~/overnight_log.txt
echo "DONE at $(date)" >> ~/overnight_log.txt
echo "DONE at $(date)" >> ~/overnight_summary.txt
