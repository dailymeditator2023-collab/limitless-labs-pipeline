# Limitless Labs — Project Guide for Leo

> **Last updated:** February 22, 2026
> **Owner:** Rahul (Founder)
> **Primary workspace:** WordPress on Hostinger + Airtable + Claude ecosystem
> **Site:** [limitlesslabs.in](https://limitlesslabs.in)

---

## 1. What Is Limitless Labs?

Limitless Labs is an **independent supplement review platform** — positioned as "the last page you read before buying a supplement."

The core promise is **research-backed reviews with no paid placements or brand bias**, serving as supplement intelligence for Indian consumers navigating a crowded market.

### Mission & Editorial Policy

- Provide logic-driven verdicts based on ingredient science, clinical dosing benchmarks, and aggregated multi-source data.
- **Strict editorial independence** — no paid placements, no brand partnerships influencing reviews.
- **Critical conflict-of-interest policy:** Smart Caffeine products are **excluded from all reviews** because they are owned by the platform's founders. This is non-negotiable.
- Target audience: Indian consumers seeking trustworthy supplement guidance.

---

## 2. Content & Scoring Framework

### 2.1 Scoring System (4 Dimensions, Weighted)

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| **Formula** | 30% | Quality and completeness of the ingredient profile |
| **Dosing** | 30% | Accuracy vs. clinical dosing benchmarks from research |
| **Value** | 20% | Price-to-quality ratio, cost per serving analysis |
| **Transparency** | 20% | Label clarity, third-party testing, proprietary blend disclosure |

Each dimension scores on a scale, and the weighted composite produces a **final verdict**. Verdicts are displayed as styled "verdict pills" on the site.

**Composite score formula:**
```
Final Score = (Formula × 0.30) + (Dosing × 0.30) + (Value × 0.20) + (Transparency × 0.20)
```

**Low Score Verification Rule (< 5.0/10):**
Any product scoring below 5.0/10 triggers an automatic data verification hold. A low score on a known brand is more likely a data/extraction problem than a genuinely bad product. The pipeline must:
1. STOP at the Scoring Agent stage — do NOT pass to the Writing Agent
2. Set Airtable status to `"Low Score — Data Verification Required"`
3. Output the full score breakdown + extracted ingredient data for manual review
4. Verification checks before proceeding:
   - Compare extracted data against the actual nutrition label image (OCR accuracy)
   - Verify the "under-dosed" ingredients: what was extracted vs. clinical benchmark
   - Confirm the correct product variant/SKU was scraped
5. Only after data is verified correct → proceed to Writing Agent
6. We publish all reviews regardless of score — readers need to know what to avoid. But we verify data first.

### 2.2 Supplement Categories

Seven core categories are covered. Content rollout is phased, prioritizing high-demand products:

- **Whey Protein** (highest priority)
- **Ashwagandha**
- **Caffeine Stacks** (excluding Smart Caffeine — conflict of interest)
- **Creatine**
- **Multivitamins**
- **Fish Oil / Omega-3**
- **Pre-Workouts**

### 2.3 Review Methodology (Research-First)

Each review follows this pipeline:

1. **Product Selection** — based on market demand, search volume, user requests
2. **Multi-Source Data Collection:**
   - Amazon product data (ingredients, pricing, ratings, review sentiment)
   - Reddit community discussions and sentiment
   - Clinical studies for each ingredient
   - Third-party lab testing results (where available)
3. **Customer Sentiment Analysis** (see 2.5 below)
4. **Structured Analysis** — applying the 4-dimension scoring framework
5. **Review Writing** — comprehensive, research-publication-style writeup including a "What Customers Say" section
6. **Publishing** — via WordPress with ACF Pro structured data

### 2.4 Current Content Status

- **65 published reviews** (as of last update)
- Reviews are stored as WordPress posts with ACF (Advanced Custom Fields) Pro providing structured data fields for scores, ingredients, verdict, etc.

### 2.5 Customer Sentiment Analysis

Every review must include a **"What Customers Say"** section that summarizes real customer feedback from two sources. This is part of the Research Agent's output and gets stored in Airtable before the Writing Agent uses it.

#### Amazon Review Sentiment

**Data collection:**
- Pull the top 10-15 **most helpful** reviews (not just recent — helpful-ranked reviews carry more signal)
- Capture the overall star distribution (e.g., "78% 5-star, 12% 1-star")

**Analysis output:**
- **Top 3 things customers praise** (e.g., taste, mixability, results, price)
- **Top 3 complaints** (e.g., digestion issues, clumping, aftertaste, packaging)
- **Recurring themes** — patterns that appear across multiple reviews (e.g., "multiple reviewers report bloating after 2 weeks")
- **Red flags** — suspicious review patterns that may indicate fake reviews:
  - Spike of 5-star reviews on a single date
  - Generic/repetitive language across reviews
  - Verified purchase ratio unusually low
  - If detected, note it factually: "Review pattern suggests possible incentivized reviews"

#### Reddit Sentiment

**Data collection:**
- Search relevant subreddits: r/IndianFitness, r/supplements, r/IndianSkincareAddicts (for collagen/biotin products), and any brand-specific mentions
- Pull threads where the product or brand is discussed

**Analysis output:**
- **General sentiment** — do people recommend it? What's the consensus?
- **Alternatives suggested** — what do Redditors recommend instead? (useful context for readers)
- **Red flags mentioned** — any quality concerns, side effects, or controversies raised by the community
- If no Reddit discussion exists, say so honestly: "Limited community discussion available for this product"

#### Output Format in Reviews

The "What Customers Say" section in each review has two subsections:

```
## What Customers Say

### Amazon Consensus
[Star distribution summary]
[Top praises]
[Top complaints]
[Any red flags]

### Community Discussion
[Reddit sentiment summary]
[Alternatives mentioned]
[Any red flags]
```

**Rules:**
- Keep it factual — no editorializing. Let the data speak.
- Never fabricate sentiment. If data is thin, say so.
- Attribute claims to the source ("Multiple Amazon reviewers report..." / "Reddit users in r/IndianFitness suggest...")
- This section is separate from the scored dimensions — it's qualitative context, not part of the 4-dimension score

#### Airtable Storage

The Research Agent stores raw sentiment data in Airtable per product:
- `amazon_star_distribution` — percentage breakdown by star rating
- `amazon_top_praises` — summarized positive themes
- `amazon_top_complaints` — summarized negative themes
- `amazon_review_flags` — any suspicious patterns noted
- `reddit_sentiment_summary` — overall community take
- `reddit_alternatives` — products the community recommends instead
- `reddit_flags` — any concerns raised
- `sentiment_data_status` — "Complete", "Partial (No Reddit)", or "Insufficient"

---

## 3. Technical Architecture

### 3.1 Stack Overview

```
┌─────────────────────────────────────────────────────┐
│                    PRESENTATION                      │
│   WordPress (Hostinger) + ACF Pro + Custom Theme    │
│   - Source Serif 4 (headings) + DM Sans (body)      │
│   - Warm cream background aesthetic                  │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│                     DATA LAYER                       │
│          Airtable (Single Source of Truth)          │
│   - Product database                                 │
│   - Ingredient library                               │
│   - Scoring records                                  │
│   - Pipeline status tracking                         │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│                   AGENT PIPELINE                     │
│  Research Agent → Ingredients Agent → Scoring Agent │
│          (Claude API-powered via Leo)               │
└─────────────────────────────────────────────────────┘
```

### 3.2 WordPress Setup

- **Hosting:** Hostinger
- **CMS:** WordPress with ACF Pro for structured review data
- **Theme:** Custom theme with research-publication aesthetic
- **Design tokens:**
  - Headings: `Source Serif 4`
  - Body text: `DM Sans`
  - Background: Warm cream (#F5F0E8 range)
  - Accent colors for verdict pills and category badges

### 3.3 ACF Pro Fields (Key Fields per Review)

Each review post has structured ACF fields including (but not limited to):
- Product name, brand, category
- Overall score (weighted composite)
- Individual dimension scores (Formula, Dosing, Value, Transparency)
- Verdict text and verdict type (for pill styling)
- Ingredient list with dosing data
- Product image
- Price and serving info

### 3.4 Airtable (Central Database)

Airtable is the **single source of truth** for all product and review data. It feeds into both the agent pipeline and WordPress.

Key tables include:
- **Products** — master list with metadata
- **Ingredients** — library with clinical dosing benchmarks
- **Reviews** — scoring data, status, publish state
- **Pipeline Status** — tracking which stage each product is in

### 3.5 Agent Pipeline (Three Specialized Agents)

The content generation pipeline uses three specialized sub-agents:

1. **Research Agent**
   - Scrapes Amazon product pages (BeautifulSoup)
   - Extracts ALL product images from page source JSON (including hidden thumbnails) for label OCR
   - Pulls top 10-15 most helpful Amazon reviews + star distribution for sentiment analysis
   - Pulls Reddit discussions (Reddit JSON API) from relevant subreddits for community sentiment
   - Aggregates sentiment, pricing, rating data
   - Outputs: product data, nutrition label image, Amazon sentiment summary, Reddit sentiment summary
   - Stores all sentiment fields in Airtable (see Section 2.5)
   - Tools: Playwright (non-headless, Mac Mini browser with logged-in Chrome session), BeautifulSoup, Reddit JSON API
   - **Amazon scraping approach:** Uses Mac Mini's real browser (Playwright non-headless) to scrape /dp/ product pages directly. No bot detection issues — real browser, real IP, real session. Processes ~17s per product sequentially. Do NOT use /product-reviews/ URLs (Amazon gates these behind login). Reviews, histogram, and sentiment are available on the main product page.
   - **Apify decision:** Evaluated and rejected. Free tier too slow, Starter plan $49/month unnecessary. Mac Mini browser approach is faster, free, and more reliable.

2. **Ingredients Agent**
   - Parses ingredient labels from collected data
   - Cross-references against the structured ingredient library
   - Assesses clinical dosing accuracy for each ingredient
   - Outputs dosing compliance report

3. **Scoring Agent**
   - Applies the 4-dimension weighted scoring framework
   - Generates the composite score and verdict
   - Produces the structured data that feeds into ACF fields

**Pipeline flow:**
Product selected → Research Agent collects data → Ingredients Agent analyzes → Scoring Agent evaluates → Review written → Published to WordPress

---

## 4. WordPress Issues & Fixes (History)

This section documents the technical issues that have been debugged and resolved on the WordPress site.

**Reference this when you encounter similar symptoms — the fix is likely the same pattern.**

### 4.1 Category Assignment Issues
- **Problem:** Reviews were published without proper category assignments in WordPress
- **Fix:** Ensured category taxonomy terms are correctly assigned during post creation/update
- **Pattern:** Always verify `wp_set_post_terms()` or equivalent is called with correct taxonomy

### 4.2 Incomplete Scoring Data
- **Problem:** Some ACF scoring fields were empty or partially filled
- **Fix:** Validation step added to ensure all four dimension scores + composite are populated before publishing
- **Pattern:** Check all required ACF fields are non-empty before status = 'publish'

### 4.3 Verdict Pill Styling
- **Problem:** Verdict pills (the colored badges showing the verdict) had styling inconsistencies
- **Fix:** CSS corrections for the verdict pill component
- **Debugging approach:** Used `getComputedStyle()` in browser console to inspect actual applied styles rather than searching stylesheets — this is more reliable for WordPress where styles can come from theme, plugins, or inline

### 4.4 Cropped Product Images
- **Problem:** Product images were being cropped incorrectly in review cards/listings
- **Fix:** Adjusted WordPress image size settings and CSS object-fit properties
- **Pattern:** Check both WordPress media settings (Settings → Media) and CSS `object-fit` / `aspect-ratio` properties

### 4.5 CSS Enqueuing Issues
- **Problem:** Custom CSS not loading or being overridden
- **Root cause:** Typically an enqueuing problem in `functions.php` rather than a selector specificity issue
- **Pattern:** Always check `wp_enqueue_style()` order and dependencies first before increasing selector specificity
- **Debugging:** Use browser DevTools → Network tab to verify stylesheet is loading, then `getComputedStyle(element)` to check what's actually applied

### 4.6 Agent Pipeline: Timeout Infinite Loop (Feb 2026)
- **Problem:** Overnight agent job was spinning forever. A `TimeoutError` was caught by an inner `except` block, which prevented the outer timeout logic from terminating the process — causing an infinite loop.
- **Fix:** Restructured exception handling so `TimeoutError` propagates correctly. Job now exits properly on timeout.
- **Remaining issues:**
  - **Amazon product 404s (delisted products):** Dead Amazon URLs still cause failures. Need to detect 404/delisted status and skip/flag these products instead of retrying.
  - **Brand site screenshot timeouts:** Brand websites with lazy-loaded images cause screenshot captures to time out. Need to implement scroll-to-trigger or wait-for-network-idle before capturing.
- **Pattern:** When writing try/except blocks in the agent pipeline, NEVER catch broad `Exception` in an inner block that could swallow `TimeoutError`, `KeyboardInterrupt`, or other control-flow exceptions. Always use specific exception types or re-raise.

### 4.7 Agent Pipeline: Hidden Amazon Images Not Extracted (Feb 2026)
- **Problem:** Nutrition label images hidden behind the "4+" overflow in Amazon thumbnails were not being scraped. Scraper only grabbed the first few visible images.
- **Fix:** Parse the page source for Amazon's image JSON (`colorImages` / `imageGalleryData`) to get ALL image URLs including hidden ones. Extracts hi-res URLs — now gets ~17 images vs. previous ~8.
- **Pattern:** Never rely on visible DOM thumbnails for Amazon images. Always parse the page source JSON for the full set.

### 4.8 Agent Pipeline: Markdown Garbage in Ingredient Parser (Feb 2026)
- **Problem:** Ingredients agent was parsing markdown formatting as ingredient names (e.g., `**SERVING SIZE:**` treated as an ingredient with dose 33g).
- **Fix:** Strip all markdown syntax (`**`, `-`, `#`) before passing to the ingredients agent. Map raw labels to canonical names (`Total Protein` → `Protein`).
- **Pattern:** Always sanitize input text before passing between agents. Never assume upstream output is clean.

### 4.9 Agent Pipeline: Category-Blind Scoring (Feb 2026)
- **Problem:** Scoring agent penalized ALL ingredients equally regardless of product type. A protein powder was scored down for having low calcium (45mg vs. 1000mg RDA) even though nobody buys protein powder for calcium — it's an incidental nutrient from the pea/rice blend.
- **Fix:** Implemented category-aware scoring. Each supplement category defines primary ingredients (scored against clinical benchmarks) and incidental ingredients (present naturally, not penalized). The Dosing dimension only evaluates primary ingredients for that category.
- **Impact:** Cosmix Plant Protein went from 4.7/10 (incorrect) to 8.6/10 (correct) after this fix.
- **Pattern:** Scoring context matters. The framework must know WHAT TYPE of product it's evaluating. If a popular brand scores below 5.0, suspect the scoring logic or data before suspecting the product.

### 4.10 Agent Pipeline: Writing Agent Fetches Stale Score Record (Feb 2026)
- **Problem:** Multiple score records existed for the same product (from re-scoring during debugging). Writing agent grabbed the oldest record (3.4/10) instead of the latest (8.6/10).
- **Fix:** Updated writing agent query to sort by created date descending, limit 1. Cleaned up duplicate score records.
- **Pattern:** Any agent querying Airtable for a product's data must ALWAYS sort by date descending and take the latest record. Never assume only one record exists.

### 4.11 Amazon Bot Detection: Mac Mini Browser Solution (Feb 2026)
- **Problem:** Amazon blocked all scraping attempts — raw requests, User-Agent rotation, and even Playwright headless. Apify free tier was too slow (jobs timing out). Apify Starter plan costs $49/month.
- **Fix:** Use Playwright in non-headless mode controlling the Mac Mini's real Chrome browser with a logged-in Amazon session. Real browser fingerprint + real residential IP = no bot detection.
- **Critical detail:** Scrape product pages (`/dp/ASIN`) NOT review pages (`/product-reviews/ASIN`). Amazon gates dedicated review pages behind sign-in, but the main product page contains reviews, star histogram, and sentiment data.
- **Performance:** ~17 seconds per product, 50 products in ~14 minutes, 90% success rate. 5% failure rate is typically discontinued/invalid ASINs.
- **Cost:** $0/month (vs. $49/month Apify Starter)
- **Pattern:** Always prefer a real browser with a real session over proxy-based scraping services when you have access to a dedicated machine. The Mac Mini is an asset — use it.

### 4.12 General WordPress Debugging Best Practices
- **CSS issues:** Use `getComputedStyle()` — more reliable than searching through stylesheets
- **Element inspection:** Use `document.querySelector()` for programmatic element checks
- **Style conflicts:** Check enqueuing order in `functions.php` before assuming selector issues
- **ACF data:** Use `get_field()` with explicit post ID to verify data exists vs. template rendering issues

---

## 5. Homepage Design & Improvements

### 5.1 Current Homepage Structure

The homepage is being updated based on design mockups. Key sections:

1. **Hero Section**
   - Updated messaging emphasizing independence and research-backed reviews
   - Tagline: "The last page you read before buying a supplement"
   - Clean, editorial aesthetic

2. **Supplement Category Cards**
   - Educational cards for each of the 7 supplement categories
   - Visual design with category-specific iconography

3. **Deep Dive Review Section**
   - Redesigned to showcase featured reviews
   - "Evidence chips" — small badges showing data sources used (e.g., "12 Studies", "847 Amazon Reviews", "Reddit Analyzed")
   - Links to full reviews

4. **Ingredient Glossary Section**
   - Enhanced glossary highlighting key ingredients
   - Quick-reference for consumers
   - Links to detailed ingredient pages

### 5.2 Design Language

- **Aesthetic:** Research publication / academic journal feel
- **Primary background:** Warm cream (#F5F0E8 range)
- **Typography:**
  - Headings: `Source Serif 4` (serif, authoritative)
  - Body: `DM Sans` (clean sans-serif, readable)
- **Color accents:** Used sparingly for verdicts, CTAs, and category badges
- **Spacing:** Generous whitespace, editorial grid

---

## 6. Content Rollout Plan (Three-Phase)

### Phase 1 — Foundation (High-Demand Products)
- Whey Protein reviews (multiple brands)
- Ashwagandha reviews
- Creatine reviews
- Goal: Establish credibility with the most-searched categories

### Phase 2 — Expansion
- Pre-Workout reviews
- Fish Oil / Omega-3 reviews
- Multivitamin reviews
- Goal: Broaden category coverage

### Phase 3 — Depth & Authority
- Comparison articles (e.g., "Brand A vs Brand B")
- Category-level guides ("Best Whey Protein in India 2026")
- Ingredient deep-dives
- Goal: Become the definitive reference

---

## 7. Tools & Integrations

| Tool | Purpose |
|------|---------|
| **WordPress + ACF Pro** | CMS, structured review data, presentation layer |
| **Hostinger** | Hosting |
| **Airtable** | Central database, single source of truth, pipeline tracking |
| **Claude Chat** | Strategy, planning, problem-solving with Rahul |
| **Leo (Claude API agent)** | Content generation, review writing, agent pipeline |
| **Claude Code** | Technical implementation, debugging, code changes |
| **Playwright (Mac Mini)** | Amazon product page scraping via real Chrome browser session |
| **BeautifulSoup** | HTML parsing for extracted page data |
| **Reddit JSON API** | Community sentiment data collection |
| **Apify** | Evaluated and rejected — Mac Mini browser is faster and free |
| **Firecrawl** | Enhanced web scraping (deprioritized — Mac Mini approach preferred) |
| **Perplexity API** | Research synthesis (planned) |
| **Browser DevTools** | Debugging CSS, DOM inspection, network monitoring |

---

## 8. Operational Playbook

> **Purpose:** This is Leo's operating manual for running Limitless Labs with minimal human intervention. Follow these protocols for every action. When in doubt, follow the playbook. When the playbook doesn't cover something, escalate to Rahul.

---

### 8.1 Pre-Publish Checklist

**Run this checklist for EVERY review before setting status to "publish." No exceptions.**

#### Data Completeness Check
```
□ Product name is set (non-empty string)
□ Brand name is set
□ Category taxonomy is assigned (not uncategorized)
□ Formula score is populated (numeric, within valid range)
□ Dosing score is populated (numeric, within valid range)
□ Value score is populated (numeric, within valid range)
□ Transparency score is populated (numeric, within valid range)
□ Composite score exists AND matches the formula:
  → (Formula × 0.30) + (Dosing × 0.30) + (Value × 0.20) + (Transparency × 0.20)
  → If mismatch > 0.1, STOP and recalculate. Do not publish.
□ Verdict text is set (non-empty)
□ Verdict type/tier is set (must match the score range for correct pill styling)
□ Price and serving data are populated
□ Ingredient list is populated (at least 1 ingredient)
```

#### Content Quality Check
```
□ Review body is present and > 300 words
□ No placeholder text remains (search for "TODO", "TBD", "PLACEHOLDER", "[INSERT")
□ No Smart Caffeine products are mentioned or reviewed (HARD BLOCK)
□ All ingredient claims have a data source (clinical study, Amazon data, or Reddit)
□ Verdict language matches the score (don't say "excellent" for a 5/10 product)
```

#### Visual / Rendering Check
```
□ Product image is uploaded and attached to the post
□ Product image aspect ratio is correct (not cropped/stretched)
  → Verify: image width ≥ 600px, aspect ratio between 1:1 and 4:3
□ Featured image is set in WordPress
□ Preview the post (use WordPress preview, not just the editor)
  → Verdict pill renders with correct color
  → Scores display in all 4 dimensions
  → Product image is visible and not cropped
  → Category label appears correctly
  → No broken layouts or overlapping elements
```

#### Airtable Sync Check
```
□ Airtable record status = "Ready to Publish"
□ All WordPress ACF field values match Airtable source values
  → If mismatch: Airtable ALWAYS wins. Update WordPress.
□ After publishing: Update Airtable record status to "Published"
□ After publishing: Record the WordPress post URL in Airtable
```

**If ANY check fails → DO NOT PUBLISH. Fix the issue first, then re-run the full checklist.**

---

### 8.2 Publishing Workflow (Step-by-Step)

Follow this exact sequence. Do not skip steps or reorder.

```
STEP 1: VERIFY SOURCE DATA
├── Confirm Airtable record status = "Ready to Publish"
├── If status = "Low Score — Data Verification Required":
│   ├── Data must be manually verified before proceeding
│   ├── Check extracted data against label image, verify dosing, confirm correct SKU
│   └── Only proceed if verification is complete and data confirmed accurate
├── Confirm all scoring fields are populated in Airtable
├── Confirm ingredient data is complete
└── If anything is missing → STOP. Go back to the agent pipeline.

STEP 2: CREATE/UPDATE WORDPRESS POST
├── Create post as DRAFT (never directly to publish)
├── Set post title = product name + brand
├── Assign correct category taxonomy
├── Populate ALL ACF fields from Airtable data
├── Upload product image, set as featured image
└── Paste/generate review body content

STEP 3: RUN PRE-PUBLISH CHECKLIST (Section 8.1)
├── If all checks pass → proceed to Step 4
└── If any check fails → fix and re-run from Step 3

STEP 4: PREVIEW & VISUAL VERIFICATION
├── Open WordPress preview in browser
├── Verify rendering: verdict pill, scores, image, layout
├── Check on mobile viewport (≤ 480px width) if possible
└── If visual issues → debug using Section 4 patterns, then re-preview

STEP 5: PUBLISH
├── Set post status to "Published"
├── Verify the live URL loads correctly
└── Spot-check: click through from homepage/category page to the review

STEP 6: POST-PUBLISH SYNC
├── Update Airtable record status → "Published"
├── Record the live WordPress URL in Airtable
├── Record the publish date in Airtable
└── Log any issues encountered during this publish cycle
```

---

### 8.3 Error Handling Protocols

**When something goes wrong, follow these decision trees. Do not improvise — follow the tree.**

#### Data Collection Failures

```
Amazon scrape returns empty/error
├── FIRST: Check HTTP status code
│   ├── 404 or "dog page" (Amazon delisted product) → DO NOT RETRY
│   │   ├── Flag in Airtable as "Product Delisted — Amazon 404"
│   │   ├── Skip this product entirely (do not continue review)
│   │   └── Notify Rahul: "Product may need replacement or removal"
│   └── Other error (timeout, 503, network) → retry once after 60 seconds
├── If retry fails → check if URL structure is valid
└── If URL valid but scrape fails → log error, try alternative scraping method
    └── If all methods fail → mark data source as "Unavailable" in Airtable
        → Continue review with remaining data sources
        → Add note in review: "Amazon data unavailable at time of analysis"

Brand site screenshot fails (timeout)
├── Likely cause: lazy-loaded images not triggering without scroll
├── Implement scroll-to-bottom before screenshot capture
├── Use wait-for-network-idle (no requests for 500ms) instead of fixed delay
├── If still failing after scroll + idle wait → capture what's available
└── Log: "Partial screenshot — lazy-load images may be missing"

Reddit JSON API returns no relevant threads
├── Try 3 alternative search queries (different keywords, subreddits)
├── If still no results → mark Reddit data as "Insufficient"
└── Continue review with remaining data sources
    → Do NOT fabricate Reddit sentiment
    → Note in review: "Limited community discussion available"

Clinical study data is ambiguous or conflicting
├── DO NOT make a judgment call
├── Document both positions with sources
├── Flag in Airtable: "Dosing Conflict — Needs Rahul Review"
└── ESCALATE to Rahul with a summary of the conflict
```

#### WordPress / Publishing Failures

```
ACF field fails to save
├── Retry via WP REST API with explicit post ID
├── If REST API fails → check authentication, check field key is correct
├── If field key issue → verify ACF field group is active and assigned to post type
└── If still failing → STOP. Do not publish. Log error and escalate.

CSS / styling breaks after publishing
├── Check: was a WordPress or plugin update applied recently?
│   ├── Yes → likely the update broke something. Check changelog.
│   └── No → proceed to CSS debugging
├── Use getComputedStyle() to identify what's actually applied
├── Check wp_enqueue_style() order in functions.php
├── Check for specificity conflicts from plugin CSS
└── Fix, verify in preview, then clear any caching (server + browser)

Product image displays incorrectly (cropped, stretched, missing)
├── Check image file: is it uploaded? What are the dimensions?
├── Check WordPress media settings (Settings → Media)
├── Check CSS: object-fit, aspect-ratio, max-width properties
├── Check if a caching plugin is serving a stale version
└── Fix, clear cache, verify in preview AND on live site

Review page returns 404
├── Check: is the post status actually "Published"?
├── Check: is the permalink/slug correct?
├── Flush permalinks: Settings → Permalinks → Save (no changes needed)
└── If still 404 → check .htaccess, check for plugin conflicts
```

#### Scoring / Data Integrity Failures

```
Composite score doesn't match dimension scores
├── Recalculate: (Formula × 0.30) + (Dosing × 0.30) + (Value × 0.20) + (Transparency × 0.20)
├── If Airtable has wrong composite → fix in Airtable, re-sync to WordPress
├── If WordPress has wrong composite → re-pull from Airtable
└── NEVER manually override the composite. Always recalculate from dimensions.

Product scores below 5.0/10
├── DO NOT pass to Writing Agent
├── Set Airtable status → "Low Score — Data Verification Required"
├── Verify extraction accuracy:
│   ├── Pull the original nutrition label image
│   ├── Compare OCR output against what the label actually shows
│   ├── Check each "under-dosed" ingredient: extracted dose vs. clinical benchmark
│   └── Confirm correct product variant/SKU was scraped (not a different size/flavor)
├── If data is wrong → fix extraction, re-run Ingredients + Scoring agents
├── If data is verified correct → proceed to Writing Agent, publish the low score
└── ESCALATE to Rahul with the breakdown if unsure

Verdict type doesn't match score range
├── Check the score-to-verdict mapping rules
├── Update verdict type to match the actual score
└── Verify verdict pill styling renders correctly with new type

Duplicate review detected (same product already reviewed)
├── Check Airtable: is there an existing record?
├── If existing review is outdated → this is an UPDATE, not a new review
│   ├── Update the existing WordPress post (do not create a new one)
│   └── Update Airtable record with new data and date
└── If genuine duplicate → discard the new one, log the error
```

---

### 8.4 Airtable ↔ WordPress Sync Protocol

**Cardinal rule: Airtable is ALWAYS the source of truth. If Airtable and WordPress disagree, Airtable wins.**

#### Data Flow Direction

```
Airtable → WordPress (PRIMARY DIRECTION)
├── Product data flows FROM Airtable TO WordPress
├── Scores, verdicts, ingredients originate in Airtable
├── WordPress is the DISPLAY layer, not the data layer
└── Never manually edit scoring data directly in WordPress ACF
    → Always edit in Airtable first, then sync to WordPress

WordPress → Airtable (METADATA ONLY)
├── Post URL (after publishing)
├── Publish date
├── Post status changes
└── Visual/rendering issues flagged during publishing
```

#### Field Mapping

> Leo: Populate this table with exact field names as you discover them.

| Airtable Field | ACF Field Key | Notes |
|----------------|---------------|-------|
| Product Name | `product_name` | Exact match required |
| Brand | `brand_name` | |
| Category | WP taxonomy term | Map to correct term slug |
| Formula Score | `formula_score` | Numeric |
| Dosing Score | `dosing_score` | Numeric |
| Value Score | `value_score` | Numeric |
| Transparency Score | `transparency_score` | Numeric |
| Composite Score | `overall_score` | Calculated, never manually set |
| Verdict Text | `verdict_text` | |
| Verdict Type | `verdict_type` | Controls pill styling |
| Price | `price` | |
| Servings | `servings` | |
| Ingredients | `ingredients` | May be repeater/flexible field |

#### Sync Procedure

```
1. Read all fields from Airtable record
2. For each field in the mapping table:
   a. Get Airtable value
   b. Get current WordPress/ACF value
   c. If they differ → update WordPress with Airtable value
   d. Log the change: "Updated [field] from [old] to [new]"
3. Verify composite score math after sync
4. Update Airtable sync timestamp
```

#### Conflict Resolution

```
Data conflict between Airtable and WordPress
├── Airtable wins. Always.
├── Overwrite WordPress value with Airtable value
├── Log the conflict for review
└── Exception: if Airtable field is EMPTY and WordPress has data
    ├── This means Airtable is incomplete
    ├── DO NOT delete WordPress data
    ├── Flag in Airtable: "Missing data — WordPress has value: [X]"
    └── Escalate to Rahul if it's a scoring field
```

---

### 8.5 Monitoring & Self-Checks

**Run these checks periodically, even when nothing is being published.**

#### Daily Health Check (Automated)
```
□ Homepage loads without errors (HTTP 200)
□ At least 3 random review pages load correctly
□ Product images are rendering (not broken image icons)
□ Verdict pills are displaying with correct colors
□ Category pages are populating with correct reviews
□ No WordPress error logs in the last 24 hours
```

#### Weekly Integrity Check
```
□ Total published reviews in WordPress matches Airtable "Published" count
□ Spot-check 5 random reviews: do WordPress scores match Airtable?
□ Check for any reviews stuck in "Draft" that should be published
□ Check for any Airtable records marked "Ready to Publish" that haven't been published
□ Verify no WordPress or plugin updates are pending (check but don't auto-update)
□ Check site speed (homepage loads in < 3 seconds)
```

#### Monthly Audit
```
□ Full reconciliation: every "Published" Airtable record has a live WordPress URL
□ Every live WordPress review has a corresponding Airtable record
□ All composite scores are mathematically correct
□ No orphaned images (uploaded but not attached to any post)
□ Review the error log from the past month — any recurring patterns?
□ Check Google Search Console for crawl errors on review pages
```

#### If a Check Fails

```
Daily check failure
├── Attempt automated fix (cache clear, retry)
├── If fix works → log and continue
└── If fix fails → escalate to Rahul immediately

Weekly check failure
├── Investigate root cause
├── Fix if it's a known pattern (see Section 4)
├── Log the issue and fix in error log
└── If unknown pattern → escalate to Rahul

Monthly audit discrepancy
├── Document the discrepancy with specifics
├── Fix data alignment (Airtable wins)
├── Add a new check to daily/weekly if it's a new failure mode
└── Report to Rahul in monthly summary
```

---

### 8.6 Escalation Rules

**This defines the boundary between "Leo handles it" and "Rahul needs to decide."**

#### Leo Handles Autonomously (No Escalation Needed)
- CSS/styling fixes (using established debugging patterns from Section 4)
- ACF field sync issues (follow sync protocol in 8.4)
- Image upload/rendering fixes
- Cache clearing
- Permalink/slug fixes
- Re-running the pre-publish checklist
- Retrying failed data collection (Amazon scrape, Reddit API)
- Correcting composite score math errors
- Updating Airtable status fields
- Running scheduled health checks

#### Leo Handles, Then Notifies Rahul
- WordPress or plugin updates (apply if minor/security, notify Rahul)
- New failure pattern not covered in Section 4 (fix it, document it, tell Rahul)
- A data source is consistently unavailable (e.g., Amazon blocking scrapes for 3+ days)
- A review needed > 2 fix cycles before passing the pre-publish checklist
- Any change to theme files (functions.php, template files, style.css)

#### Escalate to Rahul BEFORE Acting
- **Editorial decisions:** which product to review, editorial tone, positioning
- **Scoring conflicts:** ambiguous clinical data, conflicting study results
- **New categories:** adding a supplement category not in the existing seven
- **Structural changes:** modifying the scoring framework, changing weights
- **Smart Caffeine:** ANY mention, review request, or comparison involving Smart Caffeine products → hard block, notify Rahul
- **Third-party requests:** anyone asking for paid placement, sponsorship, or editorial influence
- **Architecture changes:** modifying the Airtable schema, changing ACF field groups, adding new WordPress plugins
- **Bulk operations:** anything affecting more than 5 reviews simultaneously
- **Anything not covered in this playbook**

---

### 8.7 Rollback Procedures

**If something goes wrong after publishing, follow these steps in order.**

#### Severity 1: Review displays incorrectly but content is correct
```
1. Revert post to "Draft" immediately
2. Identify the rendering issue (use Section 4 debugging patterns)
3. Fix in preview mode
4. Re-run visual verification from pre-publish checklist
5. Re-publish
6. Log the issue and fix
```

#### Severity 2: Review has incorrect data (wrong scores, wrong product)
```
1. Revert post to "Draft" immediately
2. Identify source of incorrect data
3. Check Airtable — is the source data correct?
   ├── If Airtable is correct → re-sync from Airtable to WordPress
   └── If Airtable is also wrong → fix in Airtable first, then sync
4. Re-run FULL pre-publish checklist
5. Re-publish
6. Log the issue and root cause
```

#### Severity 3: Site-wide issue (all reviews affected, homepage broken)
```
1. DO NOT make changes
2. Check: was a WordPress/plugin update just applied?
   ├── Yes → attempt rollback of the update
   └── No → check server status on Hostinger
3. If Hostinger issue → check Hostinger status page, contact support
4. If theme/code issue → revert last code change
5. ESCALATE to Rahul immediately regardless of cause
6. Document timeline: what happened, when, what was the last change
```

#### After Any Rollback
```
1. Verify the fix on the live site
2. Run the daily health check
3. Document what happened, why, and how it was fixed
4. If this is a NEW failure mode:
   a. Add it to Section 4 (WordPress Issues & Fixes)
   b. Add a corresponding check to the pre-publish checklist
   c. Notify Rahul
```

---

### 8.8 Logging & Documentation

**Every action Leo takes should leave a trail.**

#### What to Log
- Every publish action (date, product, post URL, any issues encountered)
- Every error and how it was resolved
- Every Airtable ↔ WordPress sync action
- Every escalation to Rahul and the outcome
- Every new failure mode discovered
- Every change to theme files or WordPress configuration

#### Where to Log
- **Airtable "Activity Log" table** (or equivalent) — one row per significant action
- **This project guide** — update Section 4 when new issue patterns are discovered
- **Local memory files** — Leo's local context files for session continuity

#### Log Format
```
[DATE] [ACTION TYPE] [PRODUCT/CONTEXT] [OUTCOME] [NOTES]

Examples:
[2026-02-21] PUBLISH "MuscleBlaze Whey Gold" SUCCESS No issues
[2026-02-21] SYNC "ON Creatine Monohydrate" CONFLICT Airtable score=7.2, WP had 7.0. Updated WP.
[2026-02-21] ERROR Homepage FIXED Verdict pill CSS broken after theme update. Enqueuing order was wrong.
[2026-02-21] ESCALATE "Dosing conflict on Ashwagandha KSM-66" PENDING Two studies disagree on effective dose. Sent to Rahul.
```

---

## 9. Key Principles & Reminders

### Editorial
- **Never review Smart Caffeine products** — conflict of interest, non-negotiable
- **No paid placements** — ever
- **Research-first** — every review must be backed by multi-source data
- **Scoring consistency** — always use the 4-dimension weighted framework
- **Verdict-score alignment** — verdict language must match the numerical score
- **Publish all scores** — low-scoring reviews are valuable to readers. We publish everything, but verify data first on any score below 5.0/10

### Technical
- **Airtable is the single source of truth** — WordPress reflects what's in Airtable
- **CSS debugging:** Always use `getComputedStyle()` first, not stylesheet searching
- **CSS loading issues** are usually enqueuing problems, not selector problems
- **ACF data issues:** Verify with `get_field('field_name', $post_id)` — distinguish between missing data vs. rendering issues
- **Separation of concerns:** WordPress = presentation, Airtable = data, Agents = research + analysis
- **Never publish directly** — always DRAFT → CHECKLIST → PREVIEW → PUBLISH

### Process
- **Agent pipeline order:** Research → Ingredients → Scoring → Review → Publish
- **Always validate** all ACF fields are populated before publishing
- **Test verdict pills** visually after every style change
- **Product images:** Check both WordPress media settings AND CSS when images display incorrectly
- **Follow the playbook** — if it's not in the playbook, escalate

---

## 10. File & Directory Reference

> Leo: Update this section as the project file structure evolves.

Key files and locations to be aware of:

- **WordPress theme directory** — custom theme files (header.php, functions.php, single-review template, archive templates, style.css)
- **ACF field group exports** — JSON exports of field group configurations (keep backed up)
- **Airtable base** — "Limitless Labs" base with Products, Ingredients, Reviews, Pipeline tables
- **Agent scripts** — Python scripts for Research Agent, Ingredients Agent, Scoring Agent
- **This file** — `PROJECT_GUIDE.md` — Leo's primary reference for project context

---

## 11. What's Next / Active Workstreams

> Update this section as priorities shift.

**Completed:**
- [x] Handle Amazon 404s / delisted products in agent pipeline ✅
- [x] Hidden image extraction — parse all Amazon images from page source ✅
- [x] Parser cleanup — strip markdown, canonical ingredient names ✅
- [x] Category-aware scoring — primary vs. incidental ingredients ✅
- [x] Customer sentiment analysis — Amazon helpful reviews + Reddit threads + "What Customers Say" section in reviews ✅
- [x] Fix writing agent stale score bug — sort by date desc, limit 1 ✅
- [x] Clean up duplicate score records in Airtable (8 deleted) ✅
- [x] Amazon scraping via Mac Mini browser — 50 products processed, 90% success, $49/month saved vs Apify ✅
- [x] Fix GPT preamble bug — added "No preamble" instruction, strip preamble from output ✅
- [x] Fix nutrition facts bug — skip macros/minerals in ingredient parser ✅
- [x] Add 200+ ingredient aliases — EPA/DHA, Cyanocobalamin, KSM-66, B-vitamins, etc. ✅
- [x] Two-tier benchmark system — therapeutic vs RDA doses for fair multivitamin scoring ✅
- [x] Full pipeline validation — 40/40 products scored, avg 6.5/10, distribution healthy ✅
- [x] Create batch_rescore.py — runs ingredients + scoring agents on all products with composition data ✅
- [x] GitHub repo setup — https://github.com/dailymeditator2023-collab/limitless-labs-pipeline (PUBLIC) ✅

**Next up:**
- [ ] **Run writing agent** on products needing reviews
- [ ] **Spot-check 3-5 reviews** for accuracy before bulk publishing
- [ ] **Fix brand site screenshot timeouts** — implement scroll-trigger + network-idle wait for lazy-loaded images

**Ongoing:**
- [ ] Homepage improvements rollout (hero, category cards, deep dive section, glossary)
- [ ] Agent pipeline automation (Research → Ingredients → Scoring flow)
- [ ] Firecrawl / Apify integration for enhanced scraping
- [ ] Perplexity API integration for research synthesis
- [ ] Continued Phase 1 content rollout (whey, ashwagandha, creatine reviews)
- [ ] WordPress theme refinements based on design mockups
- [ ] Airtable ↔ WordPress sync automation script
- [ ] Implement automated daily health check script
- [ ] Build pre-publish validation as a callable function/script
- [ ] Set up error logging in Airtable

---

*This document is Leo's primary reference and operating manual for the Limitless Labs project. Follow the playbook. Log everything. Escalate when unsure. Keep this guide updated as the project evolves.*
