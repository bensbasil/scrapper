# Phase 1 Architecture Audit Report

**Date:** 2026-10-06  
**Repository:** Business Opportunity Intelligence Platform (`scrapper`)  
**Audited Modules:** `pipeline_runner.py`, `api_server.py`, `scraper/pipeline.py`, `database/db.py`, `analyzer/`, `business_intelligence/`, `dashboard/`, `tests/`

---

## 1. Runtime Flow & Execution Paths

The repository has three execution entry points, but they are architecturally disconnected:

```
[User / CLI]
    └── python pipeline_runner.py (Primary Execution Path)
           ├── Scrapers (Playwright / BeautifulSoup)
           ├── Database Pre-population (PostgreSQL)
           ├── Static Website & SEO Audit
           ├── Scoring & Report Generation
           ├── Enrichment (Tech Stack, Email, Decision Makers, Registry)
           ├── Intent & Business Intelligence Modules
           └── Outreach Copy Drafts (Gemini / OpenAI / Fallback)

[User / Dashboard UI]
    ├── Next.js Server Components (App Router)
    │      └── DIRECT PostgreSQL queries (pg driver, bypassing FastAPI)
    └── Next.js Client Components (Browser)
           └── /api/* rewrites (next.config.ts)
                  └── FastAPI (api_server.py)
                         └── Subprocess spawn (pipeline_runner.py)
                                └── In-memory log buffer (deque) -> SSE stream

[Legacy / Orphaned]
    └── scraper/pipeline.py (AcquisitionPipeline)
           └── Completely unreferenced by pipeline_runner.py and api_server.py
```

### Detailed Trace

1. **Primary Runner (`pipeline_runner.py`)**:
   - `MVPPipeline` initializes every module in `__init__`, including browser clients, and immediately triggers `self.db_manager.execute_schema()`, executing the full 325-line DDL schema script before every run.
   - **Ingestion:** Fetches candidate businesses using `GoogleMapsScraper`, `JustDialScraper`, `IndiaMartScraper`, or `RecrawlScheduler`.
   - **Pre-population:** Inserts all scraped raw businesses into Postgres immediately so they appear on the dashboard before downstream enrichment.
   - **Downstream Processing:** Runs a linear 13-stage waterfall on each business:
     `WebsiteAnalyzer` → `ChangeDetector` → `SEOChecker` → `ScoringEngine` → `ReportGenerator` → `TechStackDetector` → `EmailExtractor` + `EmailValidator` → `DecisionMakerFinder` → `OpenCorporatesScraper` → `SocialAnalyzer` + `SocialScraper` → `FreshnessMonitor` → `HiringSignalDetector` → `ReviewTrendDetector` → `IntentEngine` → `Business Intelligence Suite` (7 submodules) → `OutreachGenerator` → `RecrawlScheduler`.
   - **Redundant Network I/O:** The business website is fetched and parsed independently multiple times across different stages (`WebsiteAnalyzer`, `TechStackDetector`, `EmailExtractor`, `DecisionMakerFinder`, `FreshnessMonitor`, `HiringSignalDetector`, `ConversionAnalyzer`, `TrustSignalDetector`) rather than passing a single cached DOM/HTML snapshot.

2. **API Server (`api_server.py`)**:
   - Does not import or run `MVPPipeline` in-process. Instead, it acts as a subprocess manager: `trigger_scrape()` launches `pipeline_runner.py` as an OS subprocess via `asyncio.create_subprocess_exec` or `subprocess.Popen`.
   - Captures stdout/stderr into an in-memory `collections.deque(maxlen=500)` and streams lines to `/api/logs` via Server-Sent Events (SSE).
   - Hardcodes Windows-specific virtual environment paths (`../env/Scripts/python.exe`, `env/Scripts/python.exe`) with a fallback to `sys.executable`.

3. **Orphaned Pipeline (`scraper/pipeline.py`)**:
   - Contains `AcquisitionPipeline`, which writes raw JSON to `data/raw/` and attempts an ad-hoc import of `WebsiteConversionAnalyzer`.
   - This class is **never imported or executed** by any entry point, CLI, or test in the codebase.

---

## 2. Module Duplication: `analyzer/` vs `business_intelligence/`

There is severe code drift and stub duplication between the `analyzer/` directory and the newer `business_intelligence/` directory:

| Filename / Component | `analyzer/` State | `business_intelligence/` State | Actual Usage in `pipeline_runner.py` |
| :--- | :--- | :--- | :--- |
| `business_health_score.py` | 40-line stub returning `HealthScore(0.0, ...)` | 55-line working class `BusinessHealthScore` | Uses `business_intelligence.BusinessHealthScore` |
| `competitor_analyzer.py` | 40-line stub returning `CompetitorInsights(0.0, ...)` | 100-line working class with DB candidate search | Uses `business_intelligence.CompetitorAnalyzer` |
| `customer_pain_extractor.py` | 38-line stub returning empty profiles | 65-line working regex pain-extractor | Uses `business_intelligence.CustomerPainExtractor` |
| `review_miner.py` | 40-line stub returning empty analysis | 120-line working rule-based review miner | Uses `business_intelligence.ReviewMiner` |
| `trust_signal_detector.py` | 40-line stub returning empty signals | 105-line working HTTP trust signal parser | Uses `business_intelligence.TrustSignalDetector` |
| `conversion_analyzer.py` | Named `website_conversion_analyzer.py` (52 lines, only called in dead `scraper/pipeline.py`) | Named `conversion_analyzer.py` (168 lines, full DOM parser) | Uses `business_intelligence.ConversionAnalyzer` |
| `social_analyzer.py` | 12-line backward-compatibility shim re-exporting `enrichment.social_analyzer` | N/A | Uses `enrichment.social_analyzer` |
| `growth_signal_detector.py` | 39-line dead stub with empty methods | N/A | Dead code (superceded by `intent/hiring_signal_detector.py`) |

### Active Modules in `analyzer/`
Only 4 modules in `analyzer/` are actively used in the pipeline:
- `scoring_engine.py` (Heuristic opportunity scoring engine)
- `business_report_generator.py` (Plain text client reports)
- `outreach_generator.py` (Email/WhatsApp copy generator with Gemini/OpenAI integration)
- `seo_checker.py` (Meta, robots.txt, sitemap audit)

All other files in `analyzer/` are either dead stubs or legacy shims.

---

## 3. Database Coupling

1. **Monolithic DAO / God Object (`database/db.py`)**:
   - `ScraperRepository` spans 1,312 lines and 38 distinct methods. It manages every table in the schema (`businesses`, `website_analyses`, `scoring_results`, `business_reports`, `outreach_drafts`, `tech_stacks`, `email_intelligence`, `social_profiles`, `intent_profiles`, `decision_makers`, `company_registries`, `pipeline_runs`, `change_events`, etc.).
   - All queries use raw, handwritten SQL strings without query builders or an ORM.

2. **Schema Auto-Execution at Startup**:
   - Every execution of `MVPPipeline` runs `self.db_manager.execute_schema()`, which reads and executes `database/schema.sql`. While guarded with `IF NOT EXISTS`, running DDL transactions on every pipeline run adds startup latency and risk.

3. **Domain Logic Coupled to Database**:
   - Domain analytics classes (`CompetitorAnalyzer`, `ReviewTrendDetector`) take `repo` directly as an initialization parameter and issue database queries within business calculation loops, rather than receiving data entities as inputs.

4. **Split Database Architecture & Bypassed Repository**:
   - `api_server.py` bypasses `ScraperRepository` for mutations: endpoints `/api/businesses` (DELETE), `/api/businesses/{id}` (DELETE), `/api/businesses/batch-delete` (POST), and `/api/businesses/{id}` (PATCH) execute ad-hoc inline SQL queries directly against `db_manager.get_connection()`.
   - **Frontend Direct Access:** Next.js Server Components (`dashboard/src/app/page.tsx`, `dashboard/src/app/business/[id]/page.tsx`, `dashboard/src/app/runs/page.tsx`) connect **directly** to PostgreSQL via the Node.js `pg` driver (`dashboard/src/lib/db.ts`), duplicating SQL queries and schema models between TypeScript and Python.

---

## 4. API & Frontend Architecture

1. **Subprocess Management Pattern**:
   - `api_server.py` does not run scraping jobs as internal asynchronous tasks or workers. It invokes Python CLI processes via `subprocess.Popen` / `asyncio.create_subprocess_exec`.
   - Concurrency is restricted by a single global `process_lock`, meaning the API can only execute one scrape job at a time.
   - If the API process is killed uncleanly or worker threads hang, zombie Chromium/Playwright browser instances can persist.

2. **Log Streaming**:
   - Line-by-line output is buffered in a fixed-size `collections.deque(maxlen=500)` and broadcast over an SSE endpoint (`/api/logs`).
   - If multiple clients connect, separate `asyncio.Queue` instances are created with a maximum size of 200 items.

3. **Frontend Routing Bug (`dashboard/next.config.ts`)**:
   - In `next.config.ts`, line 8 configures:
     `source: "/api/:path((?!logs$).*)", destination: "http://127.0.0.1:8000/api/:path*"`
   - It explicitly excludes `/api/logs`, citing a non-existent route (`src/app/api/logs/route.ts`).
   - Because `dashboard/src/app/api/logs/route.ts` does not exist, any browser client connecting to `/api/logs` on port 3000 receives a 404 error instead of proxying to FastAPI.
   - An orphaned file `dashboard/src/lib/logEmitter.ts` exists but is never imported.

---

## 5. Testing & Verification

1. **Test Coverage Gaps**:
   - Only 5 test files exist in `tests/`:
     - `test_api_server.py` (3 test functions)
     - `test_entity_resolver.py` (3 test functions)
     - `test_outreach_generator.py` (2 test functions)
     - `test_scoring_engine.py` (3 test functions)
     - `test_social_scraper.py` (3 test functions)
   - Total test count across the entire repository is only 14 test functions.

2. **Critical Untested Areas**:
   - `pipeline_runner.py` / `MVPPipeline` has 0 tests.
   - All 7 modules in `business_intelligence/` have 0 tests.
   - All 4 modules in `intent/` have 0 tests.
   - All 3 modules in `monitoring/` have 0 tests.
   - All scrapers (`google_maps`, `company_website`, `tech_signals`, `opencorporates`, `justdial`, `indiamart`) have 0 tests.
   - Database operations in `ScraperRepository` have 0 automated unit or regression tests.

3. **Flaky Integration Testing**:
   - `tests/test_api_server.py` tests FastAPI endpoints against a live database without mocks. If PostgreSQL is offline or uninitialized, running `pytest` fails.

---

## 6. Configuration Management

1. **No Centralized Configuration Layer**:
   - There is no unified configuration object (e.g. `pydantic-settings` or `config.py`).
   - Configuration is scattered across files via direct `os.getenv()` calls.

2. **Hardcoded Secrets & Environment Drift**:
   - In `database/db.py`, the default connection string hardcodes credentials:
     `postgresql://postgres:password@localhost:5432/scraper_db`
   - In `api_server.py`, Windows virtual environment paths are hardcoded:
     `os.path.join(rootDir, "..", "env", "Scripts", "python.exe")`
   - `dashboard` requires a separate `DATABASE_URL` in `dashboard/.env.local`, which crashes at startup if not explicitly provided, whereas Python silently falls back to localhost defaults.
   - `outreach_generator.py` reads `GEMINI_API_KEY`, `OPENAI_API_KEY`, `GEMINI_MODEL`, and `OPENAI_MODEL` on demand on each function invocation.

---

## Summary of Priority Architecture Tasks

1. **Eliminate Dead & Duplicate Modules:** Remove the 6 placeholder stubs from `analyzer/` (`business_health_score.py`, `competitor_analyzer.py`, `customer_pain_extractor.py`, `review_miner.py`, `trust_signal_detector.py`, `growth_signal_detector.py`) and delete or integrate legacy `scraper/pipeline.py`.
2. **Resolve Dual Database Access:** Unify data access so the Next.js frontend fetches through FastAPI endpoints rather than keeping a secondary direct PostgreSQL connection via Node `pg`.
3. **Fix Next.js SSE Proxying:** Update `dashboard/next.config.ts` to allow `/api/logs` to proxy to FastAPI, or implement the missing Next.js SSE proxy route.
4. **HTML/DOM Caching:** Cache the fetched website content in `MVPPipeline` to avoid redundant HTTP requests across the 8 downstream website analysis modules.
5. **Centralize Configuration:** Implement a typed configuration module and eliminate hardcoded database fallbacks and Windows paths.
