# Canonical Architectural Module Ownership Map (P3)

**Date:** 2026-10-06  
**Scope:** Architecture & Capability Ownership Mapping across the entire repository  
**Status:** Architectural Plan Only (No code modified, no files moved/deleted)

---

## 1. Summary Ownership Matrix

| Capability | Canonical Module | Current Callers | Migration Needed | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **Discovery** | `scraper/connectors/public_web/google_maps.py` *(Primary)*<br>`scraper/connectors/registries/justdial.py`<br>`scraper/connectors/registries/indiamart.py` | `pipeline_runner.py` | Yes: Standardize connector contract; remove discovery loop coupling from `pipeline_runner.py` | Low |
| **Scraping** | `scraper/connectors/public_web/company_website.py`<br>`scraper/connectors/technical/tech_signals.py`<br>`scraper/connectors/social/social_scraper.py`<br>`scraper/connectors/registries/opencorporates.py` | `pipeline_runner.py` | Yes: Retire orphaned `scraper/pipeline.py`; pass cached HTML snapshot across analyzers | Medium |
| **Enrichment** | `enrichment/tech_stack_detector.py`<br>`enrichment/email_extractor.py`<br>`enrichment/email_validator.py`<br>`enrichment/decision_maker_finder.py`<br>`enrichment/entity_resolver.py`<br>`enrichment/social_analyzer.py` | `pipeline_runner.py`<br>`tests/test_entity_resolver.py` | Yes: Retire `analyzer/social_analyzer.py` wrapper; consume shared DOM snapshot | Low |
| **Intent** | `intent/hiring_signal_detector.py`<br>`intent/freshness_monitor.py`<br>`intent/review_trend_detector.py`<br>`intent/intent_engine.py` | `pipeline_runner.py` | Yes: Retire obsolete `analyzer/growth_signal_detector.py`; add unit tests | Low |
| **Intelligence** | `business_intelligence/conversion_analyzer.py`<br>`business_intelligence/review_miner.py`<br>`business_intelligence/customer_pain_extractor.py`<br>`business_intelligence/competitor_analyzer.py`<br>`business_intelligence/trust_signal_detector.py`<br>`business_intelligence/business_health_score.py` | `pipeline_runner.py` | Yes: Retire 6 dead stubs in `analyzer/`; decouple `CompetitorAnalyzer` from DB repo; write unit tests | Medium |
| **Scoring** | `analyzer/scoring_engine.py`<br>`analyzer/seo_checker.py` | `pipeline_runner.py`<br>`tests/test_scoring_engine.py` | Minimal: Keep active modules in `analyzer/`; clarify naming vs. BI health scores | Low |
| **Opportunity Detection** | `business_intelligence/opportunity_mapper.py`<br>`analyzer/business_report_generator.py` | `pipeline_runner.py` | Moderate: Unify service mapping and report text generation under a single contract | Low |
| **Outreach** | `analyzer/outreach_generator.py` | `pipeline_runner.py`<br>`tests/test_outreach_generator.py` | Low: Centralize LLM API config; remove dead prompt generator methods | Low |
| **Persistence** | `database/db.py` (`DatabaseManager`, `ScraperRepository`)<br>`database/schema.sql` | `pipeline_runner.py`<br>`api_server.py`<br>`dashboard` *(direct)* | High: Eliminate Next.js direct DB access; split 1,312-line DAO; stop running DDL on CLI boot | High |
| **API** | `api_server.py` | `dashboard` (via HTTP proxy)<br>`tests/test_api_server.py` | Moderate: Move inline SQL mutations into repository; fix `/api/logs` proxy in `next.config.ts`; replace subprocess with worker queue | Medium |
| **Dashboard** | `dashboard/src/` (Next.js 16 + React 19) | End User (Browser) | Moderate: Decouple from Node `pg` direct DB; consume API endpoints exclusively; clean dead `logEmitter.ts` | Medium |
| **Monitoring** | `monitoring/pipeline_monitor.py`<br>`monitoring/change_detector.py`<br>`monitoring/recrawl_scheduler.py` | `pipeline_runner.py` | Low: Expose run metrics and change events to API endpoints; add automated tests | Low |

---

## 2. Granular Capability Analysis

### 1. Discovery
- **Current Implementation:** [GoogleMapsScraper](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/public_web/google_maps.py) is the primary discovery engine for local businesses by keyword/location. [JustDialScraper](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/registries/justdial.py) and [IndiaMartScraper](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/registries/indiamart.py) provide secondary discovery sources for India markets. Overdue re-discovery is handled by [RecrawlScheduler](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/monitoring/recrawl_scheduler.py).
- **Canonical Implementation:** Keep source connectors under `scraper/connectors/`.
- **Existing Callers:** [pipeline_runner.py](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L516-L547).
- **Dependencies:** Playwright (Chromium), BeautifulSoup, requests.
- **Consolidation Required:** The discovery branching logic (`if source == "justdial" ... elif source == "indiamart" ...`) is hardcoded directly inside `pipeline_runner.py`. It should eventually be abstracted into a clean registry/factory pattern.
- **Safe Migration Direction:** Define a standard `DiscoveryConnector` protocol. No renames required now.
- **Unresolved Ambiguity:** None.

---

### 2. Scraping (DOM & Technical Signals)
- **Current Implementation:** 
  - [WebsiteAnalyzer](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/public_web/company_website.py): Fetches website, evaluates mobile-friendliness, title, contact forms, WhatsApp link, and H1 tags.
  - [TechSignalAnalyzer](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/technical/tech_signals.py): Raw socket DNS resolution and SSL certificate checks.
  - [SocialScraper](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/social/social_scraper.py): Headless browser audit of Instagram/Facebook profiles (followers, handles, bio).
  - [OpenCorporatesScraper](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/registries/opencorporates.py): HTTP company registry lookup.
  - *Legacy/Dead Code:* [scraper/pipeline.py](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/pipeline.py) (`AcquisitionPipeline`) and [scraper/base_scraper.py](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/base_scraper.py).
- **Canonical Implementation:** The specialized connectors under `scraper/connectors/` are canonical.
- **Existing Callers:** `pipeline_runner.py`.
- **Dependencies:** Playwright, BeautifulSoup, dnspython, requests.
- **Consolidation Required:** Yes. Deprecate and remove `scraper/pipeline.py`. Crucially, `company_website.py` should cache the fetched raw HTML so downstream modules don't re-download the same URL.
- **Safe Migration Direction:** Mark `scraper/pipeline.py` as deprecated. Inject cached HTML into downstream analyzers.
- **Unresolved Ambiguity:** `scraper/base_scraper.py` defines abstract interfaces (`run`, `validate`) that some active connectors (`WebsiteAnalyzer`) do not inherit from.

---

### 3. Enrichment
- **Current Implementation:**
  - `enrichment/tech_stack_detector.py`: Scans signatures for CMS, frameworks, and analytics scripts.
  - `enrichment/email_extractor.py`: Regex extraction of emails and mailto links.
  - `enrichment/email_validator.py`: DNS MX record verification.
  - `enrichment/decision_maker_finder.py`: Parses about/team pages for founders, CEOs, and doctors.
  - `enrichment/entity_resolver.py`: Fuzzy matching using RapidFuzz for cross-platform deduplication.
  - `enrichment/social_analyzer.py`: Validates HTTP status and redirects of detected social profile URLs.
  - *Dead/Wrapper:* `analyzer/social_analyzer.py` (12-line shim re-exporting `enrichment.social_analyzer`).
- **Canonical Implementation:** The `enrichment/` package is 100% canonical.
- **Existing Callers:** `pipeline_runner.py`, `tests/test_entity_resolver.py`.
- **Dependencies:** `dnspython`, `rapidfuzz`, `requests`, `beautifulsoup4`.
- **Consolidation Required:** Retire `analyzer/social_analyzer.py`.
- **Safe Migration Direction:** Verify no external callers import `analyzer.social_analyzer` before removing the shim.
- **Unresolved Ambiguity:** None.

---

### 4. Intent
- **Current Implementation:**
  - `intent/hiring_signal_detector.py`: Crawls `/careers`, `/jobs` paths and scores technical hiring needs.
  - `intent/freshness_monitor.py`: Extracts footer copyright year and SSL certificate expiration date.
  - `intent/review_trend_detector.py`: Compares review ratings against historical snapshots.
  - `intent/intent_engine.py`: Synthesizes composite buying intent score (0-100).
  - *Dead/Stub:* `analyzer/growth_signal_detector.py` (39-line stub).
- **Canonical Implementation:** The `intent/` package is 100% canonical.
- **Existing Callers:** `pipeline_runner.py`.
- **Dependencies:** `requests`, `beautifulsoup4`, `psycopg2` (via repo).
- **Consolidation Required:** Retire `analyzer/growth_signal_detector.py`.
- **Safe Migration Direction:** Safe to remove the stub in `analyzer/` as nothing references it.
- **Unresolved Ambiguity:** `ReviewTrendDetector` requires `repo` injected into its constructor to query `review_snapshots`, coupling domain logic to the persistence layer.

---

### 5. Intelligence
- **Current Implementation:**
  - `business_intelligence/conversion_analyzer.py`: Booking flow, CTA, contact friction, WhatsApp detection.
  - `business_intelligence/review_miner.py`: Category praise, complaints, and review health score.
  - `business_intelligence/customer_pain_extractor.py`: Classifies operational bottlenecks and calculates pain score.
  - `business_intelligence/competitor_analyzer.py`: Local area competitor comparison and score gaps.
  - `business_intelligence/trust_signal_detector.py`: Testimonials, certs, review widgets, awards, badges.
  - `business_intelligence/business_health_score.py`: Holistic business health profile (0-100).
  - *Dead/Stubs in `analyzer/`:* `business_health_score.py`, `competitor_analyzer.py`, `customer_pain_extractor.py`, `review_miner.py`, `trust_signal_detector.py`, `website_conversion_analyzer.py`.
- **Canonical Implementation:** The `business_intelligence/` package is 100% canonical.
- **Existing Callers:** `pipeline_runner.py` (lines 60-66, 126-132, 398-461).
- **Dependencies:** `requests`, `beautifulsoup4`, `psycopg2` (via repo).
- **Consolidation Required:** Complete retirement of the 6 dead stubs in `analyzer/`. Write missing unit tests for all 6 active modules.
- **Safe Migration Direction:** Remove dead stubs from `analyzer/`; decouple `CompetitorAnalyzer` from `repo` by passing competitor lists into `analyze()` instead of having it issue SQL queries.
- **Unresolved Ambiguity:** `review_miner.py` currently uses static category mock datasets rather than scraping live Google reviews.

---

### 6. Scoring
- **Current Implementation:**
  - `analyzer/scoring_engine.py` (`ScoringEngine`): Rule-based weighted penalty system producing `opportunity_score`, `website_quality_score`, `seo_score`, and `automation_need_score`.
  - `analyzer/seo_checker.py` (`SEOChecker`): Deep technical audit of titles, meta descriptions, viewport, robots.txt, and XML sitemaps.
- **Canonical Implementation:** `analyzer/scoring_engine.py` and `analyzer/seo_checker.py`.
- **Existing Callers:** `pipeline_runner.py`, `tests/test_scoring_engine.py`.
- **Dependencies:** Standard library, `requests`, `beautifulsoup4`.
- **Consolidation Required:** Keep in `analyzer/`. Ensure naming clearly distinguishes `opportunity_score` (high = poor presence = high opportunity) from `business_health_score` (high = healthy).
- **Safe Migration Direction:** No file moves needed; add documentation clarifying scoring polarity.
- **Unresolved Ambiguity:** Inverse scoring convention (in `scoring_engine`, higher score = worse website, whereas in `business_intelligence`, higher score = healthier business).

---

### 7. Opportunity Detection
- **Current Implementation:**
  - `business_intelligence/opportunity_mapper.py` (`OpportunityMapper`): Translates detected weaknesses, conversion friction, and competitor gaps into concrete pitch services (`service_recommendations`) and structured rationale (`opportunity_reasoning`).
  - `analyzer/business_report_generator.py` (`ReportGenerator`): Formats plaintext executive summary reports summarizing strengths, weaknesses, and next steps.
- **Canonical Implementation:** Both modules perform complementary aspects of opportunity detection.
- **Existing Callers:** `pipeline_runner.py`.
- **Dependencies:** None (pure business logic and string formatting).
- **Consolidation Required:** Feed `opportunity_mapper` recommendations directly into `ReportGenerator` so plain-text reports and database recommendations share identical messaging.
- **Safe Migration Direction:** Keep both modules in their respective directories; unify data contracts.
- **Unresolved Ambiguity:** `ReportGenerator` currently runs at Step 4 before Step 13 (`OpportunityMapper`), meaning plain-text reports lack the deep business intelligence reasoning available later in the pipeline.

---

### 8. Outreach
- **Current Implementation:** [OutreachGenerator](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/analyzer/outreach_generator.py) produces cold email pitches, WhatsApp messages, outreach angles, and structured prompt templates using Gemini 1.5 Flash, OpenAI GPT-4o-mini, or deterministic template fallbacks.
- **Canonical Implementation:** `analyzer/outreach_generator.py`.
- **Existing Callers:** `pipeline_runner.py`, `tests/test_outreach_generator.py`.
- **Dependencies:** `requests`, `os` (API keys: `GEMINI_API_KEY`, `OPENAI_API_KEY`).
- **Consolidation Required:** Move API key reads from inline calls to centralized configuration.
- **Safe Migration Direction:** Keep in `analyzer/outreach_generator.py`.
- **Unresolved Ambiguity:** Uses direct HTTP calls via `requests.post` to Gemini/OpenAI rather than official SDKs (clean for dependency management, but lacks retry/backoff policies).

---

### 9. Persistence
- **Current Implementation:**
  - `database/db.py`: `DatabaseManager` (ThreadedConnectionPool) + `ScraperRepository` (1,312-line monolithic DAO with 38 raw SQL queries).
  - `database/schema.sql`: 325-line PostgreSQL DDL script with 12+ tables.
  - `dashboard/src/lib/db.ts`: Node.js `pg` pool connecting directly to Postgres from Next.js server components.
- **Canonical Implementation:** Python backend DAO belongs in `database/db.py`.
- **Existing Callers:** `pipeline_runner.py`, `api_server.py`, `monitoring/pipeline_monitor.py`, `intent/review_trend_detector.py`, `business_intelligence/competitor_analyzer.py`, `dashboard/` (Node.js).
- **Dependencies:** `psycopg2-binary` (Python), `pg` (TypeScript).
- **Consolidation Required:** 
  1. Remove startup execution of `execute_schema()` on every CLI invocation.
  2. Eliminate direct database access from Next.js; force the dashboard to query FastAPI endpoints.
  3. Decompose `ScraperRepository` into domain-specific repositories (e.g. `BusinessRepository`, `AuditRepository`, `IntelligenceRepository`).
- **Safe Migration Direction:** High-risk area. Must implement in isolated sub-steps: first decouple dashboard, then split DAO.
- **Unresolved Ambiguity:** Schema migrations are currently unversioned raw SQL scripts without a migration tool (e.g. Alembic).

---

### 10. API
- **Current Implementation:** [api_server.py](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py) (FastAPI). Provides endpoints for `/api/businesses`, `/api/businesses/{id}`, `/api/scrape`, `/api/status`, `/api/stop`, `/api/runs`, `/api/logs` (SSE).
- **Canonical Implementation:** `api_server.py`.
- **Existing Callers:** Dashboard client components, `tests/test_api_server.py`.
- **Dependencies:** `fastapi`, `uvicorn`, `pydantic`.
- **Consolidation Required:**
  1. Move ad-hoc inline SQL queries (DELETE, BATCH DELETE, PATCH) into `ScraperRepository`.
  2. Replace OS subprocess execution (`asyncio.create_subprocess_exec` / `subprocess.Popen`) with proper background worker or task runner.
  3. Fix SSE proxy configuration in `next.config.ts`.
- **Safe Migration Direction:** Refactor API endpoints to use repository methods exclusively.
- **Unresolved Ambiguity:** Subprocess execution relies on Windows-specific python path heuristics (`../env/Scripts/python.exe`), which fails on Unix environments if `sys.executable` doesn't match the virtual environment.

---

### 11. Dashboard
- **Current Implementation:** [dashboard/](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard) (Next.js 16 + React 19 + Tailwind CSS).
- **Canonical Implementation:** `dashboard/`.
- **Existing Callers:** Browser / End User.
- **Dependencies:** Next.js, React, Node.js `pg`, Tailwind CSS.
- **Consolidation Required:**
  1. Remove `dashboard/src/lib/db.ts` and update server components to call FastAPI endpoints.
  2. Remove dead file `dashboard/src/lib/logEmitter.ts`.
  3. Fix `dashboard/next.config.ts` rewrite rule to proxy `/api/logs` to FastAPI port 8000.
- **Safe Migration Direction:** Update Next.js `getBusinesses()` and `getBusinessDetail()` to fetch from `http://127.0.0.1:8000/api/...`.
- **Unresolved Ambiguity:** Next.js Server Components currently render fast via direct DB access; moving to FastAPI requires the API server to always be running for the dashboard to render anything.

---

### 12. Monitoring
- **Current Implementation:**
  - `monitoring/pipeline_monitor.py`: Context manager and metrics tracker for pipeline runs, recording stage durations and failure counts.
  - `monitoring/change_detector.py`: Detects DOM and tech signal diffs between consecutive crawls of the same business.
  - `monitoring/recrawl_scheduler.py`: Calculates tier-based recrawl schedules (Tier 1: 7d, Tier 2: 30d, Tier 3: 90d) and returns overdue business tasks.
- **Canonical Implementation:** The `monitoring/` package is 100% canonical.
- **Existing Callers:** `pipeline_runner.py`.
- **Dependencies:** Standard library (`json`, `hashlib`, `datetime`).
- **Consolidation Required:** Low. Expose run statistics and change events to API endpoints for dashboard visualization. Add unit tests.
- **Safe Migration Direction:** Keep as pure observability modules.
- **Unresolved Ambiguity:** `PipelineMonitor` saves run summaries to local files (`logs/pipeline_runs.log`, `data/cache/run_summaries.json`) and also writes to `pipeline_runs` table in PostgreSQL.

---

## 3. Important Architectural Migration Decisions

1. **Delete Dead Stubs in `analyzer/`:**
   The 6 duplicate files in `analyzer/` (`business_health_score.py`, `competitor_analyzer.py`, `customer_pain_extractor.py`, `review_miner.py`, `trust_signal_detector.py`, `website_conversion_analyzer.py`), along with `growth_signal_detector.py` and `social_analyzer.py`, should be safely removed in Phase 2. They are dead code and their presence creates confusion and crash risks.
2. **Retire `scraper/pipeline.py`:**
   The `AcquisitionPipeline` class is completely abandoned and should be removed or archived.
3. **Decouple Frontend from PostgreSQL:**
   Next.js should be a pure consumer of the FastAPI backend. Direct `pg` Pool connections in the frontend create dual schema maintenance, connection pool bloat, and conflicting deployment requirements.
4. **Implement DOM/HTML Caching:**
   A single crawl of a website by `WebsiteAnalyzer` should cache the HTML response in memory and pass it to `TechStackDetector`, `EmailExtractor`, `DecisionMakerFinder`, `FreshnessMonitor`, `ConversionAnalyzer`, and `TrustSignalDetector`, reducing network requests from 8 requests per business down to 1.
5. **Decouple Domain Analytics from Database DAO:**
   Domain modules like `CompetitorAnalyzer` and `ReviewTrendDetector` should not receive `repo` instances. Data should be queried by the orchestrator and passed as plain dataclasses/dictionaries into the analyzers.

---

## 4. Unresolved Ambiguities

1. **Inverted Score Semantics:**
   `opportunity_score` (in `scoring_engine.py`) uses **higher = worse website** (more opportunity to pitch), whereas `business_health_score` (in `business_intelligence/`) uses **higher = healthier business**. This dual convention causes confusion when interpreting metrics in reports and dashboard views.
2. **Orchestrator Stage Sequencing:**
   `ReportGenerator` runs at Step 4, prior to Step 13 (Business Intelligence). Consequently, the plain-text opportunity report generated at Step 4 does not include the rich competitor gap analysis, customer pain points, or conversion friction insights discovered later in Step 13.
3. **Mock Data in Production Code:**
   `ReviewMiner` currently generates synthetic review praise and complaints based on hardcoded category dictionaries rather than parsing live Google Maps reviews.
