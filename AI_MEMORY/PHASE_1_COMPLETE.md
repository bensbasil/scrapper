# Phase 1 — Foundation Complete

**Date:** 2026-10-08  
**Scope:** Phase 1 Architectural Baseline, Boundary Reconciliations, and Foundation Freeze  
**Status:** P8 Complete — Foundation Frozen  

---

## 1. Final Architecture

The platform architecture organizes business opportunity discovery, technical auditing, commercial intelligence, and automated outreach into a 12-layer unidirectional system. Data flows inward and downward through an orchestrator, strictly isolating presentation, domain calculations, external network retrieval, and database persistence.

```
[Presentation Layer]
      │ Next.js WebApp (Browser / Dashboard)
      ▼ HTTP REST / SSE (Port 8000)
[API Layer]
      │ FastAPI Server (api_server.py)
      ▼ Orchestrates Tasks
[Application Orchestration]
      │ MVPPipeline (pipeline_runner.py)
      ├── 1. Discovery Layer (GoogleMaps, JustDial, IndiaMart)
      ├── 2. Scraping Layer (WebsiteAnalyzer, TechSignals, SocialScraper, OpenCorporates)
      ├── 3. Enrichment Layer (TechStack, EmailExtractor, EmailValidator, DecisionMaker, EntityResolver)
      ├── 4. Intelligence Layer (Conversion, ReviewMiner, PainExtractor, Competitor, TrustSignals, HealthScore)
      ├── 5. Intent Layer (HiringSignals, Freshness, ReviewTrend, IntentEngine)
      ├── 6. Scoring Layer (ScoringEngine, SEOChecker)
      ├── 7. Opportunity Detection Layer (OpportunityMapper, BusinessReportGenerator)
      ├── 8. Outreach Layer (OutreachGenerator)
      └── 12. Monitoring Layer (PipelineMonitor, ChangeDetector, RecrawlScheduler)
      │
      ▼ Read / Write via Typed Models & DTOs
[Persistence Layer]
      │ ScraperRepository & DatabaseManager (database/db.py)
      ▼ SQL Connection Pool
[PostgreSQL Database] (Port 5432)
```

### Architectural Principles Established:
1. **Unidirectional Execution Flow:** Orchestration calls domain modules sequentially; domain modules never invoke orchestrators or upstream layers.
2. **Domain Layer Purity:** Domain intelligence, intent detection, scoring, and opportunity mapping operate as pure computational functions over in-memory data structures without issuing direct SQL queries or uncoordinated network calls.
3. **Persistence Isolation:** Raw SQL execution is strictly encapsulated within the Persistence Layer (`database/db.py`). API routes and domain services never execute inline SQL.
4. **Boundary Mediation:** High-level workflows interact with capabilities through clean functional contracts rather than touching raw browser instances, raw sockets, or database cursors.

---

## 2. Canonical Module Map

During Phase 1 auditing (P1–P3), severe code drift and dead stubs between `analyzer/` and `business_intelligence/` were identified and cataloged. The canonical ownership across all 12 capabilities is established as follows:

| Capability | Canonical Implementation | Canonical Module Location | Status / Notes |
| :--- | :--- | :--- | :--- |
| **Discovery** | `GoogleMapsScraper`, `JustDialScraper`, `IndiaMartScraper` | [`scraper/connectors/public_web/google_maps.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/public_web/google_maps.py), [`scraper/connectors/registries/`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/) | Active; orchestrated by `pipeline_runner.py` |
| **Scraping** | `WebsiteAnalyzer`, `TechSignalAnalyzer`, `SocialScraper`, `OpenCorporatesScraper` | [`scraper/connectors/public_web/company_website.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/public_web/company_website.py), [`scraper/connectors/technical/tech_signals.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/technical/tech_signals.py), [`scraper/connectors/social/`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/social/), [`scraper/connectors/registries/`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/) | Active. Orphaned [`scraper/pipeline.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/pipeline.py) identified as dead code |
| **Enrichment** | `TechStackDetector`, `EmailExtractor`, `EmailValidator`, `DecisionMakerFinder`, `EntityResolver`, `SocialAnalyzer` | [`enrichment/`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/) | Active. Dead re-export shim [`analyzer/social_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/social_analyzer.py) identified |
| **Intelligence** | `ConversionAnalyzer`, `ReviewMiner`, `CustomerPainExtractor`, `CompetitorAnalyzer`, `TrustSignalDetector`, `OpportunityMapper`, `BusinessHealthScore` | [`business_intelligence/`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/) | **Active canonical modules.** 6 placeholder stubs in `analyzer/` identified as dead code |
| **Intent** | `HiringSignalDetector`, `FreshnessMonitor`, `ReviewTrendDetector`, `IntentEngine` | [`intent/`](file:///Users/ashik/Bens%20Repository/scrapper/intent/) | Active. Dead stub [`analyzer/growth_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/growth_signal_detector.py) identified |
| **Scoring** | `ScoringEngine`, `SEOChecker` | [`analyzer/scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/scoring_engine.py), [`analyzer/seo_checker.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/seo_checker.py) | **Active canonical modules in `analyzer/`** |
| **Opportunity Detection** | `OpportunityMapper`, `ReportGenerator` | [`business_intelligence/opportunity_mapper.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/opportunity_mapper.py), [`analyzer/business_report_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/business_report_generator.py) | Active |
| **Outreach** | `OutreachGenerator` | [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py) | **Active canonical module in `analyzer/`** |
| **Persistence** | `DatabaseManager`, `ScraperRepository` | [`database/db.py`](file:///Users/ashik/Bens%20Repository/scrapper/database/db.py), [`database/schema.sql`](file:///Users/ashik/Bens%20Repository/scrapper/database/schema.sql) | Active monolithic DAO (1,374 lines) |
| **API** | FastAPI Application (`app`) | [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) | Active; route mutations refactored in P6 to use `repo.*` |
| **Presentation** | Next.js App Router | [`dashboard/src/`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard/src/) | Active UI; currently contains direct PostgreSQL connection (`src/lib/db.ts`) |
| **Monitoring** | `PipelineMonitor`, `ChangeDetector`, `RecrawlScheduler` | [`monitoring/`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/) | Active |

### Duplicate / Dead Code Inventory (Preserved for Foundation Freeze):
- `analyzer/business_health_score.py` (40-line stub returning 0.0)
- `analyzer/competitor_analyzer.py` (40-line stub returning empty insights)
- `analyzer/customer_pain_extractor.py` (38-line stub returning empty profiles)
- `analyzer/review_miner.py` (40-line stub returning empty analysis)
- `analyzer/trust_signal_detector.py` (39-line stub returning empty metrics)
- `analyzer/growth_signal_detector.py` (39-line dead stub; superseded by `intent/hiring_signal_detector.py`)
- `analyzer/social_analyzer.py` (12-line shim re-exporting `enrichment.social_analyzer`)
- `scraper/pipeline.py` (102-line orphaned script unreferenced by any runner)
- `dashboard/src/lib/logEmitter.ts` (orphaned EventEmitter unreferenced by frontend)

---

## 3. Architecture Boundaries

The architecture defines four critical system boundaries:

### 1. Presentation Boundary
- **Rule:** The Dashboard (`dashboard/src/`) must interact with backend capabilities strictly via HTTP REST and SSE streaming exposed by [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py).
- **Constraint:** Direct database queries from Next.js server components via Node `pg` violate this boundary and are scheduled for retirement in frontend cleanup tasks.

### 2. API & Orchestration Boundary
- **Rule:** API route handlers validate HTTP payloads, delegate execution to the orchestrator or repository layer, and return typed responses.
- **Enforcement:** Closed the raw SQL boundary violation in P6: [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) now contains **zero inline SQL statements**, delegating all CRUD actions to `ScraperRepository`.

### 3. Domain Intelligence Boundary
- **Rule:** Domain capabilities (Enrichment, Intelligence, Intent, Scoring, Opportunity, Outreach) must remain decoupled from infrastructure.
- **Enforcement:** Closed database coupling violations in P6:
  - `CompetitorAnalyzer` no longer requires an injected `ScraperRepository`; it can execute as a pure domain function accepting `raw_competitors`.
  - `ReviewTrendDetector` no longer mandates a database read/write; it accepts `previous_rating` and `save_snapshot=False` for pure in-memory execution.

### 4. Future Agent Boundary
The future AI agent will act as an intelligent coordinator, never a low-level script executor. The future execution architecture must adhere strictly to:

```
User / API
  └── Application Orchestration
        └── Domain Capabilities
              └── Persistence

[Future Agent Integration]
Agent
  └── Application Capability Tools
        └── Domain Capabilities
              └── Persistence
```

#### Absolute Boundary Constraints for Future Agents:
The future agent must **NEVER** directly access:
- **SQL / Raw Queries:** No SQL strings, schema inspection, or database migrations.
- **PostgreSQL:** No database connections, connection pools, or transactions.
- **Playwright:** No browser launch, page navigation, or DOM selector manipulation.
- **Raw HTTP:** No socket connections, manual header crafting, or proxy management.
- **Scraper Internals:** No anti-blocking algorithms, CAPTCHA solvers, or connector plumbing.
- **Filesystem Internals:** No direct reading/writing to local disk directories.

All agent interactions must be mediated exclusively through high-level application capability tools (e.g. `discover_businesses()`, `audit_lead()`, `generate_outreach()`, `retrieve_lead_summary()`).

---

## 4. Schemas

In P5, a centralized typed schema foundation was introduced in [`schemas/`](file:///Users/ashik/Bens%20Repository/scrapper/schemas) using Pydantic v2:

1. **[`schemas/business.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py) (`Business`):**
   - Core business entity model representing discovered/persisted businesses (name, category, address, phone, website, rating, reviews, coordinates, outreach status, recrawl tier).
2. **[`schemas/enrichment.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/enrichment.py) (`BusinessEnrichment`):**
   - Technical stack detections (CMS, frontend framework, analytics), validated contact emails (`ValidatedEmail`), decision maker profiles (`DecisionMakerCandidate`), and social activity.
3. **[`schemas/intelligence.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/intelligence.py) (`BusinessIntelligence`):**
   - Deep commercial intelligence profile (overall health score, website health, conversion friction, booking flow detection, recurring complaints, trust signals, and competitor comparisons via `CompetitorComparison`).
4. **[`schemas/intent.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/intent.py) (`IntentProfile`):**
   - Buying readiness signals (hiring signals, copyright freshness, review velocity trends, outreach urgency level: `urgent`, `high`, `normal`, `low`, and structured `IntentSignal` items).
5. **[`schemas/opportunity.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/opportunity.py) (`Opportunity`):**
   - Commercial opportunity synthesis (opportunity score 0–100, website quality score, SEO score, automation score, service recommendations via `ServiceRecommendation`, and opportunity reasoning).
6. **[`schemas/outreach.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/outreach.py) (`OutreachDraft`):**
   - Tailored sales messaging drafts (pitch angles, cold email copy, WhatsApp copy, and generation mode metadata: `gemini`, `openai`, `template`).
7. **[`schemas/pipeline.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/pipeline.py) (`PipelineResult`):**
   - Unified orchestration output model aggregating all stage schemas alongside execution observability telemetry (`StageExecution` list with stage names, durations, and error messages).
8. **[`schemas/__init__.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/__init__.py):**
   - Central re-export of all domain models and the `from_dataclass(target_class, dc_instance)` interoperability adapter.

All schemas are verified with 100% test pass rate in [`tests/test_schemas.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_schemas.py).

---

## 5. Refactoring Completed

Phase 1 implemented minimal, non-breaking interface refactorings in P6 to decouple domain logic and seal persistence boundaries:

1. **Decoupled `CompetitorAnalyzer`:**
   - Updated constructor: `repo: Optional[Any] = None`.
   - Updated method: `analyze(..., raw_competitors: Optional[List[Dict[str, Any]]] = None)`.
   - Backward compatibility: When `raw_competitors` is omitted and `repo` is provided, queries database exactly as before. When `raw_competitors` is provided, executes purely in-memory.
2. **Decoupled `ReviewTrendDetector`:**
   - Preserves pre-supplied `previous_rating` instead of overwriting from database.
   - Added `save_snapshot: bool = True` guard to bypass database writes in pure analysis runs.
   - Backward compatibility: Preserves existing database snapshot queries and insertions when called from [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py).
3. **Repository CRUD Centralization:**
   - Added 4 dedicated persistence methods to `ScraperRepository` in [`database/db.py`](file:///Users/ashik/Bens%20Repository/scrapper/database/db.py):
     - `delete_all_businesses()`
     - `delete_business(business_id: int)`
     - `batch_delete_businesses(business_ids: List[int])`
     - `update_business(business_id: int, updates: Dict[str, Any])`
4. **API Route Persistence Delegation:**
   - Refactored `DELETE /api/businesses`, `DELETE /api/businesses/{id}`, `POST /api/businesses/batch-delete`, and `PATCH /api/businesses/{id}` in [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) to delegate exclusively to `repo.*` methods.
   - Completely eliminated raw SQL strings from the API layer.
5. **Refactor Test Coverage:**
   - Implemented 12 unit tests in [`tests/test_refactored_interfaces.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_refactored_interfaces.py) covering all decoupled domain analyzers, repository methods, and API route delegations.

---

## 6. Test Baseline

The post-P5/P6 test baseline established in P7 yielded the following empirical verification metrics:

- **34 checks attempted**
- **31 passed**
- **0 failed**
- **3 environment-blocked**
- **0 Phase 1 regressions**

*(Verified against [`AI_MEMORY/PHASE_1_TEST_REPORT.md`](file:///Users/ashik/Bens%20Repository/scrapper/AI_MEMORY/PHASE_1_TEST_REPORT.md))*

### Detailed Breakdown:
- **`tests/test_schemas.py` (8 tests):** 8 PASSED (100% pass rate).
- **`tests/test_refactored_interfaces.py` (12 tests):** 12 PASSED (100% pass rate).
- **`tests/test_scoring_engine.py` (3 tests):** 3 PASSED (Logic execution verified).
- **`tests/test_entity_resolver.py` (3 tests):** 3 PASSED (Logic execution verified).
- **`tests/test_outreach_generator.py` (2 tests):** 2 PASSED (Logic execution verified).
- **`tests/test_social_scraper.py` (3 tests):** 3 PASSED (Logic execution verified).
- **`tests/test_api_server.py` (3 tests):** 3 Environment-Blocked (Missing `pytest`, missing `httpx`, and offline PostgreSQL service).

### Smoke Tests Verified:
1. **CLI Orchestrator:** `./.venv/bin/python3 pipeline_runner.py --help` -> Exit Code 0.
2. **FastAPI OpenAPI Schema:** `app.openapi()` indexed all 12 REST route paths -> Exit Code 0.
3. **Canonical Module Imports:** All 38 canonical components across 7 layers imported with zero errors -> Exit Code 0.
4. **Schema Serialization:** Instantiation and JSON serialization of nested `PipelineResult` -> Exit Code 0.
5. **Decoupled Domain Execution:** In-memory execution of `CompetitorAnalyzer` and `ReviewTrendDetector` without database connections -> Exit Code 0.

---

## 7. Known Technical Debt

1. **Dual Database Access in Next.js Dashboard:**
   - Server components in `dashboard/src/app/` bypass FastAPI and query PostgreSQL directly via Node `pg` (`dashboard/src/lib/db.ts`), duplicating SQL queries and database connection pools.
2. **Monolithic Repository (`database/db.py`):**
   - `ScraperRepository` spans 1,374 lines and 42 methods, managing all 15+ database tables in a single class without domain sub-repositories.
3. **Startup DDL Schema Execution:**
   - Every execution of `MVPPipeline` runs `db_manager.execute_schema()`, executing a 325-line DDL script on startup.
4. **Redundant Network I/O in Pipeline:**
   - Target business websites are fetched up to 7–8 times across different pipeline stages because HTML DOM snapshots are not cached or shared across analyzers.
5. **Subprocess Management in API Server:**
   - `api_server.py` executes scraping jobs via OS subprocesses (`create_subprocess_exec`) constrained by a single global process lock, rather than utilizing an asynchronous task queue or worker model.
6. **Next.js `/api/logs` SSE Proxy Misconfiguration:**
   - `dashboard/next.config.ts` regex excludes `/api/logs`, leading to 404 errors when browsers connect directly to port 3000 for real-time logs.

---

## 8. Deferred Work

The following items were identified and explicitly deferred from Phase 1 to preserve stability:

1. **Physical Deletion of Duplicate Stubs:**
   - Deletion of the 6 dead stubs in `analyzer/` (`business_health_score.py`, `competitor_analyzer.py`, `customer_pain_extractor.py`, `review_miner.py`, `trust_signal_detector.py`, `growth_signal_detector.py`), dead shim `analyzer/social_analyzer.py`, and orphaned `scraper/pipeline.py`.
2. **Next.js Dashboard Refactor:**
   - Removal of `dashboard/src/lib/db.ts` and updating Next.js server components to fetch via FastAPI REST endpoints.
3. **DOM Snapshot In-Memory Caching:**
   - Updating `WebsiteAnalyzer` to produce a `RawScrapeSnapshot` and refactoring downstream modules to accept it.
4. **Repository Decomposition:**
   - Splitting `ScraperRepository` into `BusinessRepository`, `AuditRepository`, `IntelligenceRepository`, etc.
5. **Test Environment Standardization:**
   - Creating `requirements-dev.txt` declaring `pytest>=7.4.0`, `httpx>=0.24.0`, and `anyio>=4.0.0`.
   - Mocking repository calls in `tests/test_api_server.py` to decouple test execution from live PostgreSQL.
6. **Comprehensive Domain Test Suites:**
   - Writing automated unit tests for untested `business_intelligence/` and `intent/` submodules.

---

## 9. Phase 2 Entry Criteria

Phase 2 will introduce the AI/LLM intelligence layer. Entry into Phase 2 is governed by the following strict criteria:

### What Phase 2 May Safely Introduce:
1. **AI / LLM Intelligence Layer:**
   - Reasoning capabilities for opportunity synthesis, commercial angle generation, and personalized outreach drafting.
   - Structured prompt management and provider abstraction (e.g. Gemini / OpenAI clients with resilient retries).
2. **Application Capability Tools:**
   - Clean Python tool functions exposing domain capabilities to future agents using typed Pydantic models from [`schemas/`](file:///Users/ashik/Bens%20Repository/scrapper/schemas).
3. **Contextual Analysis Workflows:**
   - Multi-step reasoning over enriched lead data without altering underlying scraper or persistence mechanics.

### What Phase 2 Must NOT Introduce:
- **No Agent Frameworks:** Do NOT introduce LangGraph, Celery, Redis, pgvector, vector databases, RAG frameworks, microservices, or Kubernetes.
- **No Infrastructure Violations:** AI components must NEVER interact directly with SQL, PostgreSQL, Playwright, raw sockets, or local filesystem paths.
- **No Boundary Breaches:** All interactions must pass through application orchestration and domain capability tools.

---

## 10. Important Architecture Decisions

The following architectural decisions are established and must be treated as stable baselines:

1. **ADR-01: Canonical Intelligence Package:**
   - `business_intelligence/` is the sole canonical source for commercial intelligence algorithms. Files in `analyzer/` with duplicate names are dead stubs.
2. **ADR-02: Pydantic v2 Schema Standard:**
   - All inter-stage data transfer and API contracts standardize on Pydantic v2 models in [`schemas/`](file:///Users/ashik/Bens%20Repository/scrapper/schemas). Internal dataclasses are bridged via `from_dataclass()`.
3. **ADR-03: Pure Domain Analyzers:**
   - Domain analytics algorithms must never take database connection objects or DAO repositories as mandatory parameters. They must operate over in-memory domain inputs.
4. **ADR-04: Persistence Encapsulation:**
   - All database SQL queries belong strictly inside `ScraperRepository` (and future domain repositories). No inline SQL in API handlers or CLI runners.
5. **ADR-05: Preserved Backward Compatibility:**
   - Any refactoring must strictly preserve the external interfaces of `pipeline_runner.py` and `api_server.py` until formal multi-stage migration plans are approved.

---

## 11. Files/Modules That Should Not Be Changed Without Architectural Review

The following core modules represent foundational contracts and must NOT be altered without formal architectural review:

1. **[`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py):** Primary CLI orchestrator and execution flow for discovery through outreach.
2. **[`database/db.py`](file:///Users/ashik/Bens%20Repository/scrapper/database/db.py):** Central database connection pool and monolithic `ScraperRepository`.
3. **[`database/schema.sql`](file:///Users/ashik/Bens%20Repository/scrapper/database/schema.sql):** Canonical relational database DDL schema.
4. **[`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py):** FastAPI REST and SSE server contracts.
5. **[`schemas/`](file:///Users/ashik/Bens%20Repository/scrapper/schemas) (`*.py`):** Canonical Pydantic v2 data contracts.
6. **[`business_intelligence/`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/) (`*.py`):** Production domain intelligence algorithms.
7. **[`intent/`](file:///Users/ashik/Bens%20Repository/scrapper/intent/) (`*.py`):** Commercial intent and urgency signal detectors.
8. **[`analyzer/scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/scoring_engine.py) & [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py):** Canonical scoring and outreach implementations.

---

## 12. Phase 1 Status

All Phase 1 foundational requirements, audits, duplicate mappings, boundary specifications, typed schema foundations, interface decouplings, regression test validations, and baseline freezings are fully reconciled and complete.

`P8 STATUS: COMPLETE`
