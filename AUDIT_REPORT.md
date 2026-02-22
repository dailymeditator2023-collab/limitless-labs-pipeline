# Limitless Labs Pipeline — Security & Code Audit Report

**Date:** 2026-02-22
**Scope:** All files referencing "limitless" or part of the Limitless Labs pipeline
**Files Audited:** 6 core Python files + supporting scripts

---

## Files Identified

| File | Lines | Purpose |
|------|-------|---------|
| `writing_agent.py` | 425 | Generates AI-written reviews via GPT-4o |
| `scoring_agent.py` | 681 | Scores products on formula/dosing/value/transparency |
| `research_agent.py` | 1114 | Scrapes Amazon, Reddit, web for product data |
| `composition_extractor.py` | 760 | Extracts supplement labels via GPT-4o Vision |
| `ingredients_agent.py` | 1285 | Analyzes ingredients against clinical benchmarks |
| `amazon_scraper.py` | 422 | Playwright-based Amazon.in product scraper |

---

## Critical Findings

### 1. Airtable API Token Exposure Risk (HIGH)

**Files:** All 6 files
**Issue:** Every file reads `AIRTABLE_TOKEN` from environment variables and constructs headers inline. The token is a **personal access token** with read/write access to the entire base (`appUOcZUDNPzstZlv`). If any log output or exception traceback includes the headers dict, the token leaks.

- `research_agent.py:47` — `AIRTABLE_API` URL constructed with hardcoded base ID
- `writing_agent.py:40-43` — Headers dict with bearer token in global scope
- `composition_extractor.py:44-47` — Same pattern

**Recommendation:** Avoid embedding tokens in global-scope dicts. Consider a helper that builds headers on-demand and never logs them.

---

### 2. Airtable Formula Injection (HIGH)

**Files:** `writing_agent.py:71`, `research_agent.py:1073`, `scoring_agent.py:641`, `ingredients_agent.py:1245`, `composition_extractor.py:538`

**Issue:** User-supplied product names are interpolated directly into Airtable `filterByFormula` strings using f-strings/format, with no escaping:
```python
formula = f"SEARCH(LOWER('{args.product.lower()}'), LOWER({{Product Name}}))"
```

A product name containing a single quote (`'`) will break the formula and could manipulate query behavior. Example: `O'Brien's Whey` would produce malformed Airtable formula syntax.

**Recommendation:** Escape single quotes in user input before embedding in Airtable formulas (replace `'` with `\\'`).

---

### 3. OpenAI API Key in Global Scope (MEDIUM)

**Files:** `writing_agent.py:32,46-48`, `composition_extractor.py:38,83-85`

**Issue:** `OPENAI_API_KEY` is read at module import time and an OpenAI client is created at module scope. If the module is imported (not just run as main), it will attempt to create a client even when not needed.

---

### 4. Hardcoded Airtable Base & Table IDs (MEDIUM)

**Files:** All files

**Issue:** Base ID `appUOcZUDNPzstZlv` and table IDs are hardcoded across all files. If the base is cloned or recreated, every file needs manual updates. There is no single configuration file.

**Recommendation:** Centralize all Airtable IDs in a shared config module or `.env` file.

---

### 5. Duplicated AirtableClient Class (MEDIUM)

**Files:** `research_agent.py:164-224`, `scoring_agent.py:57-100`, `ingredients_agent.py:104-148`

**Issue:** The `AirtableClient` class is copy-pasted across three files with identical implementations. Any bug fix or improvement must be applied in three places.

**Recommendation:** Extract to a shared `airtable_client.py` module.

---

### 6. No Input Validation on Amazon URLs (MEDIUM)

**Files:** `research_agent.py:238-239`, `composition_extractor.py:600`

**Issue:** Amazon URLs from Airtable are passed directly to HTTP requests and Playwright without validation beyond checking for `"amazon.in"` in the string. A malicious URL in the Airtable data could redirect the scraper to an arbitrary domain.

```python
if not url or "amazon.in" not in url:  # weak check
```

A URL like `https://evil.com?amazon.in` would pass this check.

**Recommendation:** Parse URLs properly and verify the hostname is `www.amazon.in` or `amazon.in`.

---

### 7. Bare `except` Clauses (MEDIUM)

**Files:** Multiple locations across all files

**Issue:** Several bare `except:` or `except Exception:` clauses silently swallow errors:
- `scoring_agent.py:618` — `except: pass` hides agent log write failures
- `research_agent.py:996-997` — `except: pass` hides failure logging errors
- `ingredients_agent.py:1219-1220` — Same pattern
- `composition_extractor.py:198,217` — `except: continue` hides image extraction errors

**Recommendation:** At minimum log the exception. Silent `except: pass` makes debugging very difficult.

---

### 8. No Rate Limiting / Retry Logic for Airtable API (LOW)

**Files:** `writing_agent.py:55-66`, `composition_extractor.py:504-517`

**Issue:** Airtable API calls in `writing_agent.py` and `composition_extractor.py` use raw `requests.get/patch` without retry logic. Airtable has a 5 requests/second rate limit. The `AirtableClient` class in other files adds `time.sleep(0.2)` during pagination but no retry on 429 errors.

---

### 9. `signal.SIGALRM` Not Available on Windows (LOW)

**File:** `composition_extractor.py:236,266-267`

**Issue:** `signal.SIGALRM` is Unix-only. The `extract_label_images_brand_site` function will crash on Windows. This may not matter for the deployment target (Hostinger Linux), but limits portability.

---

### 10. Incorrect Alias Mappings in Ingredients Library (LOW)

**File:** `ingredients_agent.py:294-301, 358-363`

**Issue:** Several alias mappings appear incorrect:
- Lines 294-301: `"vitamin e"` and its forms map to `"vitamin k2"` — the comment says "Note: maps to K2 entry which has E benchmarks" but this is confusing and likely a workaround
- Lines 358-363: `"vitamin a"` and its forms map to `"b-complex"` — comment says "Using b-complex as fallback" but Vitamin A has nothing to do with B-complex
- Line 541-543: `"selenium"` maps to `"zinc"` — comment says "Using zinc as proxy" but they are different minerals

These incorrect mappings will produce wrong dosing assessments.

---

### 11. Verdict Logic Has Redundant Condition (LOW)

**File:** `scoring_agent.py:470-479`

**Issue:** The `determine_verdict` function has redundant conditions:
```python
if overall >= 8.0:
    return "Recommended"
elif overall >= 7.5:
    return "Recommended"
```
Both branches return the same verdict. The original framework mentions "Highly Recommended" for 8.0+ but the code doesn't differentiate.

---

### 12. Missing `playwright` in requirements.txt (LOW)

**File:** `requirements.txt`

**Issue:** Only lists `requests` and `beautifulsoup4`, but 4 files import `playwright`. The `openai` package is also missing. Anyone installing from `requirements.txt` will get import errors.

---

### 13. Overnight Script Uses Hardcoded Paths (LOW)

**File:** `overnight_run.sh:2,6-7`

**Issue:** The script hardcodes paths like `~/clawd/scripts/research-agent` and `~/clawd/.secrets/airtable.env`. These are specific to one developer's machine and won't work on other deployments.

---

### 14. Legacy Backwards Compatibility Code (INFO)

**File:** `research_agent.py:92-93`

**Issue:** `AMAZON_HEADERS = get_amazon_headers()` is called at module scope "for backwards compatibility" but is never used elsewhere in the file (the code now calls `get_amazon_headers()` fresh each time for user-agent rotation). This is dead code.

---

### 15. Reddit User-Agent Identifies as Bot (INFO)

**File:** `research_agent.py:96-97`

```python
REDDIT_HEADERS = {
    "User-Agent": "LimitlessLabs-ResearchAgent/1.0 (research bot)",
}
```

**Issue:** Reddit may rate-limit or block user agents that self-identify as bots. This is honest but not effective for scraping.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH | 2 |
| MEDIUM | 5 |
| LOW | 6 |
| INFO | 2 |
| **Total** | **15** |

The most impactful issues are the **formula injection vulnerability** (all user-facing query functions) and **incorrect ingredient alias mappings** (causing wrong dosing assessments for Vitamin A, Vitamin E, and Selenium). The code duplication across files also increases maintenance burden and risk of inconsistency.
