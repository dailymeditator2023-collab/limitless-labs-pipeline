# Limitless Labs Pipeline — Full Code Audit Report

**Date:** 2026-02-22
**Scope:** All 16 Python files + 5 GitHub Actions workflows
**Audited by:** Claude (automated deep audit)

---

## Executive Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 5 | Bugs producing wrong scores, crashes, formula injection |
| **HIGH** | 12 | Missing error handling, data integrity risks, security gaps |
| **MEDIUM** | 18 | Code quality, performance, reliability |
| **LOW** | 8 | Style, dead code, minor inconsistencies |

**Top 3 risks right now:**
1. Vitamin E/A/Selenium benchmark mappings are wrong — multivitamin scores are incorrect
2. "Highly Recommended" verdict is unreachable — all 8.0+ products just say "Recommended"
3. No retry logic anywhere — a single Airtable timeout loses data silently

---

## CRITICAL Issues (Fix Immediately)

### C1. Verdict never returns "Highly Recommended"
**File:** `scoring_agent.py:470-479`

Both `>= 8.0` and `>= 7.5` return the same string `"Recommended"`. The docstring (line 19) and PROJECT_GUIDE both define 8.0+ as "Highly Recommended", but the code never produces it.

```python
# CURRENT (broken)
if overall >= 8.0:
    return "Recommended"      # Should be "Highly Recommended"
elif overall >= 7.5:
    return "Recommended"
```

**Impact:** Every high-scoring product gets downgraded on the website. Readers see "Recommended" when they should see "Highly Recommended."

**Fix:** Change line 472 to `return "Highly Recommended"`.

---

### C2. Vitamin E mapped to Vitamin K2 benchmarks
**File:** `ingredients_agent.py:294-301`

```python
"vitamin e": "vitamin k2",
"alpha-tocopherol": "vitamin k2",
```

Vitamin E (should be ~15mg) gets checked against K2 benchmarks (55-120 mcg). Every multivitamin with Vitamin E will have its dose assessment completely wrong.

**Impact:** All multivitamin reviews with Vitamin E have incorrect dosing scores.

---

### C3. Vitamin A mapped to B-Complex benchmarks
**File:** `ingredients_agent.py:357-364`

```python
"vitamin a": "b-complex",
"retinol": "b-complex",
```

Vitamin A (should be ~600-900 mcg) gets checked against B-Complex benchmarks (1-2mg). Same class of bug as C2.

**Impact:** All multivitamin Vitamin A assessments are wrong.

---

### C4. Selenium alias bypasses its own correct benchmark
**File:** `ingredients_agent.py:540-543`

The correct Selenium entry exists in `RDA_BENCHMARKS` at line 82: `"selenium": ("40mcg", "55mcg")`. But the alias table maps `"selenium"` → `"zinc"`, so the lookup hits Zinc (8-14mg) instead.

**Impact:** Selenium doses assessed against zinc thresholds — always shows "Under-dosed."

---

### C5. Airtable formula injection in multiple files
**Files:** `writing_agent.py:71`, `research_agent.py:1073`, `composition_extractor.py:538`, `run_amazon_batch.py:77`

Product names containing single quotes break the Airtable `filterByFormula`:
```python
formula = f"SEARCH(LOWER('{query.lower()}'), LOWER({{Product Name}}))"
```

If a product is named `Nature's Best`, the formula becomes:
```
SEARCH(LOWER('nature's best'), ...)
```
This breaks the query — the product is silently skipped.

**Impact:** Products with apostrophes in their names can't be searched/scored.

---

## HIGH Priority Issues

### H1. Low-score verification flag never written to Airtable
**File:** `scoring_agent.py:550-592`

The PROJECT_GUIDE requires products scoring < 5.0 to be flagged as `"Low Score — Data Verification Required"`. The code logs a warning but never writes this status to Airtable. Products with data errors get published with wrong scores.

### H2. No retry logic on any Airtable API call
**Files:** All agents

Every `requests.get()` and `requests.post()` to Airtable has zero retry logic. A single 429 rate limit or network timeout causes permanent data loss. The scoring agent processes products sequentially — if write fails, that product's scores are gone.

### H3. N+1 query pattern in writing_agent.py
**File:** `writing_agent.py:94-129`

`fetch_latest_score()` fetches the **entire** Scores table (all pages) and then filters in Python. For every product being written, it re-downloads all scores. If there are 500 scores and 50 products to write, that's 25,000 unnecessary records fetched.

### H4. No error handling in ingredients library load
**File:** `ingredients_agent.py:164-183`

If the Airtable call fails during `_load()`, the entire ingredients agent crashes with no recovery. Should catch the exception and continue with an empty cache.

### H5. Ingredient cap at 20 with no warning
**File:** `ingredients_agent.py:849`

```python
return unique[:20]  # Cap at 20 ingredients
```

Multivitamins often have 30+ active ingredients. The last 10+ are silently dropped. Scoring then bases transparency calculations on incomplete data.

### H6. Missing cost data defaults to score of 6.0
**File:** `scoring_agent.py:368-369`

If `cost_per_serving` can't be parsed, the Value dimension silently defaults to 6.0/10. No flag, no warning to the reviewer. Products with missing price data get a free "above average" Value score.

### H7. Score deduplication — re-runs create duplicate records
**File:** `scoring_agent.py:578`

Every scoring run creates a new Score record. If a product is re-scored, both old and new records exist. `cleanup_duplicate_scores.py` exists but isn't run automatically.

### H8. Unhandled OpenAI API errors in writing_agent
**File:** `writing_agent.py:310-327`

The `client.chat.completions.create()` call has no try/catch. Rate limits, context length exceeded, or API outages crash the entire writing run.

### H9. macOS-only Chrome profile path
**Files:** `amazon_reviews_playwright.py:19`, `composition_extractor.py:19`

```python
CHROME_PROFILE_SOURCE = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
```

Hard-coded macOS path. Will crash on any Linux CI/CD environment (including GitHub Actions).

### H10. `signal.alarm()` used in composition_extractor.py
**File:** `composition_extractor.py:266-267`

`signal.alarm(30)` is Unix-only and crashes on Windows. Not relevant for current setup but blocks any future cross-platform use.

### H11. JSON parsing crash on Reddit Sources
**File:** `writing_agent.py:292`

```python
reddit_thread_count=len(json.loads(research.get("Reddit Sources", "[]")))
```

If `Reddit Sources` contains malformed JSON, this throws an unhandled exception and crashes the review generation for that product.

### H12. `apify_amazon.py` uses wrong import
**File:** `apify_amazon.py:33`

Uses `requests.utils.quote()` which doesn't exist — should be `urllib.parse.quote()`. This function will crash on first call.

---

## MEDIUM Priority Issues

### M1. Formula scoring capped at 9.0, not 10.0
**File:** `scoring_agent.py:257`
`base = 5.0 + (quality_ratio * 4.0)` — max possible is 9.0. Other dimensions can reach 10.0. Formula is systematically biased low.

### M2. Unit conversion heuristic is unreliable
**File:** `ingredients_agent.py:967-975`
`if claimed_num < 1 and low_num > 100: claimed_num *= 1000` — guesses unit mismatch from magnitude. Could convert mcg values incorrectly.

### M3. Scoring notes silently truncated
**File:** `scoring_agent.py:577`
`"Scoring Notes": scoring_notes[:2000]` — notes > 2000 chars are truncated with no warning logged.

### M4. Amazon rating defaults to 0 when missing
**File:** `scoring_agent.py:523`
Missing Amazon rating becomes 0.0, which penalizes the Value score unfairly.

### M5. Multivitamin detection is too narrow
**File:** `ingredients_agent.py:1134-1144`
Only matches a hardcoded list of strings. Misses "Advanced Vitamins", "Complete Multivitamin Blend", etc.

### M6. Duplicate ingredients in Airtable library
**File:** `ingredients_agent.py:552-584`
No dedup check before writing. "Omega-3" and "omega-3" both get created as separate records.

### M7. Missing benchmark_high defaults to low * 2
**File:** `ingredients_agent.py:961`
When `benchmark_high` is empty, it assumes 2x the low value. For creatine (5g), this means 10g is "acceptable" — incorrect.

### M8. Suspicious pattern detection is broken
**File:** `research_agent.py:560-562`
Star distribution values initialized to 0 — the `star_counts[5] > 85` check never triggers if scraping failed.

### M9. No pagination in writing_agent fetch
**File:** `writing_agent.py:55-66`
`fetch_scoring_complete()` only fetches `maxRecords: limit`, ignoring any additional pages. Newer products may never be processed.

### M10. Bare `except: pass` blocks throughout scrapers
**Files:** `amazon_reviews_playwright.py:209-222`, `composition_extractor.py:199`
Multiple bare except blocks silently swallow all errors, making debugging impossible.

### M11. Review body truncated to 500 chars
**File:** `amazon_reviews_playwright.py:177`
Detailed customer reviews are cut to 500 chars — loses important nuance for sentiment analysis.

### M12. Hardcoded table IDs duplicated across files
**Files:** `scoring_agent.py:39-45`, `ingredients_agent.py:31-37`, `research_agent.py`, `writing_agent.py`
Same Airtable base/table IDs copy-pasted in 4+ files. A table rename requires editing all of them.

### M13. GitHub Actions: pipeline.yml has command injection risk
**File:** `.github/workflows/pipeline.yml:46-47`
```yaml
python ingredients_agent.py --product "${{ github.event.inputs.product_name }}"
```
User-supplied `product_name` from workflow_dispatch is interpolated into a shell command without sanitization.

### M14. GitHub Actions: notify-pr.yml echoes PR body unsanitized
**File:** `.github/workflows/notify-pr.yml:24`
```yaml
echo "${{ github.event.pull_request.body }}" >> $GITHUB_STEP_SUMMARY
```
PR body is user-controlled and could contain shell metacharacters or markdown injection.

### M15. GitHub Actions: actions not pinned to SHA
**Files:** All workflow files
`actions/checkout@v4`, `actions/setup-python@v5` use floating tags, not SHA pins. A compromised upstream action could execute arbitrary code.

### M16. GitHub Actions: sync-airtable hardcodes base ID
**File:** `.github/workflows/sync-airtable.yml:21`
```yaml
AIRTABLE_BASE_ID: appUOcZUDNPzstZlv
```
Base ID in plain text in the workflow file. Should be a secret.

### M17. GitHub Actions: pipeline runs daily but lacks failure notification
**File:** `.github/workflows/pipeline.yml:20-21`
Scheduled daily at 00:30 UTC but no Slack/email notification on failure. If the pipeline breaks, nobody knows until they check manually.

### M18. Lab testing bonus (1.5) is 3x disclosure bonus (0.5)
**File:** `scoring_agent.py:441-455`
Lab testing adds 1.5 to Transparency while full label disclosure only adds 0.5. This weighting may be intentional but is undocumented.

---

## LOW Priority Issues

### L1. Magic numbers throughout scoring
**File:** `scoring_agent.py` — various lines
Penalty multipliers (0.3, 0.5, 2.0), thresholds (4, 0.8, 0.9), and bonuses are hardcoded with no named constants.

### L2. Dead code: `amazon_scraper.py:364`
`scrape_amazon()` duplicates `scrape_amazon_product()` logic just to reformat output.

### L3. Score version always 1
**File:** `scoring_agent.py:578`
No way to track which algorithm version produced a score.

### L4. Exception logged without traceback
**File:** `scoring_agent.py:664-673`
Uses `log.error(f"Unexpected error: {e}")` instead of `log.exception()`.

### L5. `from collections import Counter` imported inside function
**Files:** `research_agent.py:566`, `amazon_reviews_playwright.py:312`
Should be at module level.

### L6. Review JSON truncated to 5000 chars
**File:** `amazon_reviews_playwright.py:331`
Could cut a review object in half, creating invalid JSON downstream.

### L7. User-Agent strings will age
**Files:** `amazon_scraper.py:105`, `research_agent.py:56-64`
Chrome 120/122 versions are from early 2024. Amazon may flag outdated UAs.

### L8. `push-scores` action calls non-existent `--sync` flag
**File:** `.github/workflows/sync-airtable.yml:81`
`python scoring_agent.py --sync` — the `--sync` flag doesn't exist in scoring_agent.py.

---

## Recommendations by Priority

### This Week (Critical)
1. Fix verdict logic — add "Highly Recommended" return (1 line change)
2. Fix Vitamin E, Vitamin A, Selenium alias mappings (3 line changes)
3. Escape single quotes in all Airtable formula strings
4. Fix `apify_amazon.py` import crash

### Next Sprint (High)
5. Add retry with exponential backoff to all Airtable API calls
6. Write low-score verification flag to Airtable (not just logs)
7. Replace N+1 query in `fetch_latest_score()` with filtered query
8. Add try/catch around OpenAI API calls in writing_agent
9. Raise ingredient cap from 20 to 40 for multivitamins
10. Add `--platform` detection for Chrome profile paths

### Backlog (Medium)
11. Extract shared config (base IDs, table IDs) into a `config.py`
12. Pin GitHub Actions to SHA hashes
13. Add failure notifications to scheduled pipeline runs
14. Sanitize workflow_dispatch inputs
15. Replace bare `except: pass` with specific exception handling
16. Add named constants for all scoring magic numbers

---

*This report covers all 16 Python files and 5 GitHub Actions workflows in the repository.*
