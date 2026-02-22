## Research Agent — Setup & Deployment Guide

### What This Does
The Research Agent is a Python script that:
1. Reads products with status "Queued" from the Airtable Products table
2. Scrapes Amazon.in for product data (price, rating, reviews, ingredients)
3. Searches Reddit (r/indiasupplements, r/IndianFitness, etc.) for community sentiment
4. Searches the web for lab testing data
5. Writes all structured data to the Airtable Raw Research table
6. Updates the product status to "Research Complete"
7. Logs every action to the Agent Log table

No paid APIs needed. Uses requests + BeautifulSoup + Reddit public JSON API + DuckDuckGo.

---

### Installation on Hostinger (SSH)

```bash
# 1. Create directory
mkdir -p ~/research-agent
cd ~/research-agent

# 2. Upload the files (research_agent.py and requirements.txt)
#    Or copy-paste them into the server

# 3. Install dependencies
pip3 install --user -r requirements.txt
# If pip3 not available:
python3 -m pip install --user -r requirements.txt

# 4. Set your Airtable API token
#    Get a personal access token from: https://airtable.com/create/tokens
#    It needs these scopes:
#      - data.records:read
#      - data.records:write
#    And access to base: appUOcZUDNPzstZlv

export AIRTABLE_TOKEN="pat_your_token_here"

# To make it permanent, add to ~/.bashrc:
echo 'export AIRTABLE_TOKEN="pat_your_token_here"' >> ~/.bashrc
```

---

### Usage

```bash
cd ~/research-agent

# Dry run — scrape but don't write to Airtable (test first!)
python3 research_agent.py --dry-run --limit 1

# Research all Queued products (up to 10)
python3 research_agent.py

# Research a specific product by name
python3 research_agent.py --product "AS-IT-IS Whey Protein"

# Process more products at once
python3 research_agent.py --limit 20
```

---

### Prerequisites in Airtable

Before running, make sure:

1. **Products table** has products with:
   - `Product Name` filled in
   - `Brand` filled in
   - `Amazon URL` filled in (the full amazon.in product page URL)
   - `Review Status` set to `Queued`

2. **Raw Research table** exists with these fields:
   - Product (linked record to Products)
   - Amazon Rating (number)
   - Amazon Review Count (number)
   - Amazon Top Pros (long text)
   - Amazon Top Cons (long text)
   - Amazon Sentiment (single select: Positive / Mixed / Negative)
   - Reddit Sentiment (single select: Positive / Mixed / Negative / Not Found)
   - Reddit Summary (long text)
   - Reddit Sources (long text)
   - Ingredients Raw (long text)
   - Label Transparency (single select)
   - Third Party Lab Tested (checkbox)
   - Lab Testing Body (single line text)
   - Lab Test Result (single line text)
   - Lab Test URL (URL)
   - Clinical Research Summary (long text)
   - Data Completeness (single select: Complete / Partial / Incomplete)
   - Scraped By (single line text)
   - Raw JSON (long text)

3. **Agent Log table** exists with:
   - Agent Name (single line text)
   - Action (single line text)
   - Status (single select: Success / Failed)
   - Input Summary (long text)
   - Output Summary (long text)
   - Error Details (long text)
   - Tokens Used (number)

---

### Testing Flow

1. Set ONE product to status "Queued" in Airtable
2. Run: `python3 research_agent.py --dry-run --limit 1`
3. Check the output — it should print the scraped data
4. If it looks good, run without --dry-run: `python3 research_agent.py --limit 1`
5. Check Airtable — Raw Research table should have a new record
6. Check the product — status should be "Research Complete"
7. Check Agent Log — should have a new entry

---

### Known Limitations (MVP)

- **Amazon may block scraping** after many requests. The script handles 503 errors with a retry, but heavy usage will need Firecrawl ($16/mo).
- **Reddit rate limits** at ~60 requests/minute. The script adds delays, but processing 50+ products rapidly may hit limits.
- **No ingredient parsing** — the script grabs raw ingredient text from Amazon. The Ingredients Agent (next to build) will structure this.
- **DuckDuckGo** sometimes returns limited results. Perplexity API ($5/1000 queries) will give much better lab testing and clinical data.
- **No proxy rotation** — all requests come from one IP. If Amazon blocks the Hostinger IP, you'll need a proxy service.

---

### Upgrade Path

When you're ready for paid tools, the script is modular — swap one function at a time:

| Current (Free) | Upgrade To | What Changes |
|----------------|------------|-------------|
| `scrape_amazon()` with BeautifulSoup | Firecrawl API | Replace function body, same output |
| `scrape_amazon_reviews()` with BeautifulSoup | Apify Amazon Reviews actor | Replace function body, same output |
| `scrape_reddit()` with Reddit JSON API | Apify Reddit scraper | Replace function body, same output |
| `web_research()` with DuckDuckGo | Perplexity API | Replace function body, same output |

Each scraper function returns a dataclass. The Airtable writing logic doesn't change.

---

### Troubleshooting

**"AIRTABLE_TOKEN environment variable not set"**
→ Run: `export AIRTABLE_TOKEN="pat_your_token_here"`

**"Product not found in Airtable"**
→ Check the product name spelling matches exactly what's in Airtable

**Amazon returns empty data**
→ Amazon may be blocking. Try: add `time.sleep(5)` between requests, or test from a different IP

**Reddit returns "Not Found" for everything**
→ Reddit may be rate limiting. Wait a few minutes and try again

**"TABLE_NOT_FOUND" error**
→ The table ID may have changed. Check Airtable base and update the table IDs at the top of research_agent.py
