# Canonical Architectural Module Ownership Map (P3)

**Date:** 2026-10-07  
**Scope:** Architectural Ownership Mapping across all 12 platform capabilities  
**Status:** Architectural Plan Only (No code modified, no files moved/renamed/deleted)

---

## 1. Summary Ownership Matrix

| Capability | Canonical Module | Current Callers | Migration Needed | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **Discovery** | [`scraper/connectors/public_web/google_maps.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/public_web/google_maps.py) *(Primary)*<br>[`scraper/connectors/registries/justdial.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/justdial.py)<br>[`scraper/connectors/registries/indiamart.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/indiamart.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) | Yes: Abstract hardcoded source-switching branches into a unified connector interface; decouple runner from source pagination | Low |
| **Scraping** | [`scraper/connectors/public_web/company_website.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/public_web/company_website.py)<br>[`scraper/connectors/technical/tech_signals.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/technical/tech_signals.py)<br>[`scraper/connectors/social/social_scraper.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/social/social_scraper.py)<br>[`scraper/connectors/registries/opencorporates.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/opencorporates.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)<br>[`tests/test_social_scraper.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_social_scraper.py) | Yes: Retire dead orphaned [`scraper/pipeline.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/pipeline.py); pass cached HTML snapshot across analyzers to eliminate redundant network I/O | Medium |
| **Enrichment** | [`enrichment/tech_stack_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/tech_stack_detector.py)<br>[`enrichment/email_extractor.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/email_extractor.py)<br>[`enrichment/email_validator.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/email_validator.py)<br>[`enrichment/decision_maker_finder.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/decision_maker_finder.py)<br>[`enrichment/entity_resolver.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/entity_resolver.py)<br>[`enrichment/social_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/social_analyzer.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)<br>[`tests/test_entity_resolver.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_entity_resolver.py) | Yes: Retire unused shim [`analyzer/social_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/social_analyzer.py); consume shared DOM/HTML snapshot | Low |
| **Intent** | [`intent/hiring_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/hiring_signal_detector.py)<br>[`intent/freshness_monitor.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/freshness_monitor.py)<br>[`intent/review_trend_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/review_trend_detector.py)<br>[`intent/intent_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/intent_engine.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) | Yes: Retire obsolete [`analyzer/growth_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/growth_signal_detector.py); decouple `ReviewTrendDetector` from DB DAO; add unit tests | Low |
| **Intelligence** | [`business_intelligence/conversion_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/conversion_analyzer.py)<br>[`business_intelligence/review_miner.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/review_miner.py)<br>[`business_intelligence/customer_pain_extractor.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/customer_pain_extractor.py)<br>[`business_intelligence/competitor_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/competitor_analyzer.py)<br>[`business_intelligence/trust_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/trust_signal_detector.py)<br>[`business_intelligence/business_health_score.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/business_health_score.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) | Yes: Retire 6 dead placeholder stubs in `analyzer/`; decouple `CompetitorAnalyzer` from DB repo; add comprehensive test suite | Medium |
| **Scoring** | [`analyzer/scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/scoring_engine.py)<br>[`analyzer/seo_checker.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/seo_checker.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)<br>[`tests/test_scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_scoring_engine.py) | Minimal: Maintain canonical modules in `analyzer/`; standardize polarity semantics between `opportunity_score` and health scores | Low |
| **Opportunity Detection** | [`business_intelligence/opportunity_mapper.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/opportunity_mapper.py)<br>[`analyzer/business_report_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/business_report_generator.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) | Moderate: Reorder execution in pipeline so `ReportGenerator` consumes structured BI opportunity reasoning; unify service recommendation taxonomies | Low |
| **Outreach** | [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)<br>[`tests/test_outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_outreach_generator.py) | Low: Centralize LLM API configuration; add timeout/retry policies for external LLM API endpoints | Low |
| **Persistence** | [`database/db.py`](file:///Users/ashik/Bens%20Repository/scrapper/database/db.py) (`DatabaseManager`, `ScraperRepository`)<br>[`database/schema.sql`](file:///Users/ashik/Bens%20Repository/scrapper/database/schema.sql) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)<br>[`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py)<br>[`dashboard`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard) *(direct pg)* | High: Eliminate Next.js direct PostgreSQL connection; remove startup DDL execution on every CLI invocation; decompose 1,312-line god DAO | High |
| **API** | [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) | Next.js Dashboard (via HTTP proxy)<br>[`tests/test_api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_api_server.py) | Moderate: Move inline SQL mutations into `ScraperRepository`; fix `/api/logs` proxying in `next.config.ts`; replace raw OS subprocess with worker queue | Medium |
| **Dashboard** | [`dashboard/src/`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard/src) (Next.js 16 App Router) | End User (Browser) | Moderate: Decouple from direct Node `pg` pool; route all queries through FastAPI; remove dead `logEmitter.ts` | Medium |
| **Monitoring** | [`monitoring/pipeline_monitor.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/pipeline_monitor.py)<br>[`monitoring/change_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/change_detector.py)<br>[`monitoring/recrawl_scheduler.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/recrawl_scheduler.py) | [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)<br>[`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) | Low: Expose stage performance metrics and change event history to API endpoints; add unit tests | Low |

---

## 2. Granular Capability Analysis & Ownership Reasoning

### 1. Discovery
1. **Current implementation:**
   - [`scraper/connectors/public_web/google_maps.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/public_web/google_maps.py) (`GoogleMapsScraper`): Primary discovery engine for local businesses using Playwright to query Google Maps, scroll search results, extract business cards, ratings, reviews, and website URLs.
   - [`scraper/connectors/registries/justdial.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/justdial.py) (`JustDialScraper`): Secondary discovery source using Playwright to extract directory listings and verified status.
   - [`scraper/connectors/registries/indiamart.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/indiamart.py) (`IndiaMartScraper`): Secondary B2B discovery source using Playwright to extract supplier profiles, GST verification, and click-to-reveal phone numbers.
   - [`monitoring/recrawl_scheduler.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/recrawl_scheduler.py) (`RecrawlScheduler`): Re-discovery mechanism querying overdue businesses from PostgreSQL based on recrawl cadences.
2. **Canonical implementation:**
   - Discovery connector contracts belong under `scraper/connectors/` (`google_maps.py`, `justdial.py`, `indiamart.py`), triggered either directly by query or scheduled via `monitoring/recrawl_scheduler.py`.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (`MVPPipeline.run()`, lines 514–555).
4. **Dependencies:**
   - `playwright` (Chromium engine), `beautifulsoup4`, `requests`, `psycopg2-binary` (for `RecrawlScheduler`).
5. **Whether consolidation is required:**
   - Yes: Currently, `pipeline_runner.py` contains hardcoded `if source == "gmaps" ... elif source == "justdial" ... elif source == "indiamart" ...` logic. Pagination, URL decoding, and return entity structures diverge across the three connectors.
6. **Safe migration direction:**
   - Define a shared `DiscoveryConnector` protocol/interface returning a standardized `DiscoveredBusiness` entity. Adapt existing scrapers to return this unified structure without renaming or moving existing files.
7. **Any unresolved ambiguity:**
   - Playwright lifecycle management: Each discovery connector manages its own browser instance lifecycle rather than sharing an initialized browser pool, increasing startup latency.

---

### 2. Scraping (DOM & Technical Signals)
1. **Current implementation:**
   - [`scraper/connectors/public_web/company_website.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/public_web/company_website.py) (`WebsiteAnalyzer`): Performs HTTP GET on candidate websites, parses DOM with BeautifulSoup (title, meta tags, forms, phone, email, social links, viewport/mobile friendliness).
   - [`scraper/connectors/technical/tech_signals.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/technical/tech_signals.py) (`TechSignalAnalyzer`): Uses raw sockets and `dnspython` for DNS resolution, MX lookups, and SSL certificate inspection.
   - [`scraper/connectors/social/social_scraper.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/social/social_scraper.py) (`SocialScraper`): Headless browser inspection of public Instagram and Facebook profiles (followers, bio, handle).
   - [`scraper/connectors/registries/opencorporates.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/connectors/registries/opencorporates.py) (`OpenCorporatesScraper`): HTTP client querying OpenCorporates API for incorporation dates and registry status.
   - *Dead/Legacy:* [`scraper/pipeline.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/pipeline.py) (`AcquisitionPipeline`): Early scaffolding script that writes raw JSON to `data/raw/` and imports `analyzer.website_conversion_analyzer`. Unused by any active runner.
   - *Abstract Base:* [`scraper/base_scraper.py`](file:///Users/ashik/Bens%20Repository/scrapper/scraper/base_scraper.py) (`BaseScraper`).
2. **Canonical implementation:**
   - Specialized connectors under `scraper/connectors/public_web/`, `scraper/connectors/technical/`, `scraper/connectors/social/`, and `scraper/connectors/registries/`.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stages 1, 2, 8, 9).
   - [`tests/test_social_scraper.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_social_scraper.py).
4. **Dependencies:**
   - `requests`, `beautifulsoup4`, `playwright`, `dnspython`.
5. **Whether consolidation is required:**
   - Yes:
     1. Deprecate and retire orphaned `scraper/pipeline.py`.
     2. Implement DOM snapshot caching: currently, `WebsiteAnalyzer`, `TechStackDetector`, `EmailExtractor`, `DecisionMakerFinder`, `FreshnessMonitor`, `ConversionAnalyzer`, and `TrustSignalDetector` independently make up to 7–8 duplicate HTTP requests to the same target website.
6. **Safe migration direction:**
   - Modify `WebsiteAnalyzer` to return the fetched HTML text and parsed BeautifulSoup tree in a context payload so downstream analyzers reuse it rather than refetching.
7. **Any unresolved ambiguity:**
   - Connector inheritance discrepancy: `SocialScraper`, `GoogleMapsScraper`, `JustDialScraper`, and `IndiaMartScraper` inherit from `BaseScraper`, but `WebsiteAnalyzer` and `TechSignalAnalyzer` do not.

---

### 3. Enrichment
1. **Current implementation:**
   - [`enrichment/tech_stack_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/tech_stack_detector.py) (`TechStackDetector`): Scans HTML signatures for CMS, frameworks, and analytics scripts.
   - [`enrichment/email_extractor.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/email_extractor.py) (`EmailExtractor`): Regex extraction of emails and `mailto:` links.
   - [`enrichment/email_validator.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/email_validator.py) (`EmailValidator`): MX DNS validation using `dnspython`.
   - [`enrichment/decision_maker_finder.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/decision_maker_finder.py) (`DecisionMakerFinder`): Crawls `/about`, `/team`, `/contact` pages for leadership names and roles.
   - [`enrichment/entity_resolver.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/entity_resolver.py) (`EntityResolver`): Fuzzy matching using RapidFuzz for cross-source entity deduplication.
   - [`enrichment/social_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/social_analyzer.py) (`SocialAnalyzer`): Validates HTTP status and redirects of detected social links.
   - *Dead Shim:* [`analyzer/social_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/social_analyzer.py) (12-line re-export shim: `from enrichment.social_analyzer import SocialAnalyzer, ...`).
2. **Canonical implementation:**
   - The `enrichment/` package exclusively.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stages 5, 6, 7, 8).
   - [`tests/test_entity_resolver.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_entity_resolver.py).
4. **Dependencies:**
   - `dnspython`, `rapidfuzz`, `requests`, `beautifulsoup4`.
5. **Whether consolidation is required:**
   - Yes:
     1. Retire unused shim `analyzer/social_analyzer.py`.
     2. Feed cached HTML DOM into `tech_stack_detector`, `email_extractor`, and `decision_maker_finder`.
6. **Safe migration direction:**
   - Confirm all imports target `enrichment.social_analyzer` directly (already satisfied in `pipeline_runner.py`), then deprecate `analyzer/social_analyzer.py`.
7. **Any unresolved ambiguity:**
   - None. Module boundaries in `enrichment/` are well-defined and decoupled.

---

### 4. Intent
1. **Current implementation:**
   - [`intent/hiring_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/hiring_signal_detector.py) (`HiringSignalDetector`): Crawls `/careers`, `/jobs` paths and scores technical hiring needs.
   - [`intent/freshness_monitor.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/freshness_monitor.py) (`FreshnessMonitor`): Inspects website footer copyright year and SSL certificate expiration.
   - [`intent/review_trend_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/review_trend_detector.py) (`ReviewTrendDetector`): Compares review counts and ratings against historical snapshots.
   - [`intent/intent_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/intent_engine.py) (`IntentEngine`): Synthesizes composite buying intent score (0–100) and urgency levels (`urgent`, `high`, `medium`, `low`).
   - *Dead Stub:* [`analyzer/growth_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/growth_signal_detector.py) (39-line stub returning hardcoded zeros).
2. **Canonical implementation:**
   - The `intent/` package exclusively.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stages 10, 11, 12).
4. **Dependencies:**
   - `requests`, `beautifulsoup4`, `psycopg2-binary` (via `ScraperRepository`).
5. **Whether consolidation is required:**
   - Yes:
     1. Retire the obsolete stub `analyzer/growth_signal_detector.py`.
     2. Decouple `ReviewTrendDetector` from direct database DAO access. Currently, it accepts `repo` in `__init__` and executes SQL within its calculation loop.
6. **Safe migration direction:**
   - Pass historical review snapshot records into `ReviewTrendDetector.detect()` as arguments rather than injecting the persistence repository.
   - Add automated unit tests for all `intent/` modules.
7. **Any unresolved ambiguity:**
   - Newly discovered businesses lack prior review snapshots in PostgreSQL; `ReviewTrendDetector` falls back gracefully to static score analysis, but this logic assumes immediate database availability.

---

### 5. Intelligence
1. **Current implementation:**
   - [`business_intelligence/conversion_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/conversion_analyzer.py) (`ConversionAnalyzer`): Audits CTAs, booking flows, lead forms, contact friction, WhatsApp widgets.
   - [`business_intelligence/review_miner.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/review_miner.py) (`ReviewMiner`): Extracts category-specific complaints, praise, and review health metrics.
   - [`business_intelligence/customer_pain_extractor.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/customer_pain_extractor.py) (`CustomerPainExtractor`): Classifies operational bottlenecks, communication issues, and computes composite pain score.
   - [`business_intelligence/competitor_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/competitor_analyzer.py) (`CompetitorAnalyzer`): Queries local competitors in the same city/category and computes score gap metrics.
   - [`business_intelligence/trust_signal_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/trust_signal_detector.py) (`TrustSignalDetector`): Parses DOM for testimonials, accreditation, review widgets, awards, trust badges.
   - [`business_intelligence/business_health_score.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/business_health_score.py) (`BusinessHealthScore`): Computes composite business health ratings combining all signals.
   - *Dead Stubs in `analyzer/`:*
     - `analyzer/business_health_score.py` (40 lines, stub)
     - `analyzer/competitor_analyzer.py` (40 lines, stub)
     - `analyzer/customer_pain_extractor.py` (38 lines, stub)
     - `analyzer/review_miner.py` (40 lines, stub)
     - `analyzer/trust_signal_detector.py` (39 lines, stub)
     - `analyzer/website_conversion_analyzer.py` (52 lines, dead code)
2. **Canonical implementation:**
   - The `business_intelligence/` package exclusively.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stage 13: lines 60–66, 126–132, 398–461).
4. **Dependencies:**
   - `requests`, `beautifulsoup4`, `psycopg2-binary` (via `ScraperRepository` in `CompetitorAnalyzer`).
5. **Whether consolidation is required:**
   - Yes:
     1. Retire all 6 duplicate stubs in `analyzer/` in Phase 2. They possess completely incompatible method signatures and dataclass structures, posing severe silent crash risks if accidentally imported.
     2. Decouple `CompetitorAnalyzer` from the DB `repo`.
     3. Write comprehensive unit tests for `business_intelligence/` (currently has 0 tests).
6. **Safe migration direction:**
   - Decouple DB dependencies by passing pre-fetched competitor records into `CompetitorAnalyzer.analyze()`. Verify no outside callers use `analyzer.*` stubs before pruning them.
7. **Any unresolved ambiguity:**
   - `ReviewMiner` currently uses static category mock taxonomies rather than parsing real scraped customer reviews from Google Maps or JustDial.

---

### 6. Scoring
1. **Current implementation:**
   - [`analyzer/scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/scoring_engine.py) (`ScoringEngine`): Heuristic opportunity scoring evaluating digital presence via rule-based penalties to produce `opportunity_score` (0–100), `website_quality_score`, `seo_score`, and `automation_need_score`.
   - [`analyzer/seo_checker.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/seo_checker.py) (`SEOChecker`): Audits HTML title, meta tags, viewport, robots.txt, and sitemap.xml.
2. **Canonical implementation:**
   - `analyzer/scoring_engine.py` and `analyzer/seo_checker.py`.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stages 3 and 4).
   - [`tests/test_scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_scoring_engine.py).
4. **Dependencies:**
   - Python standard library, `requests`, `beautifulsoup4`.
5. **Whether consolidation is required:**
   - Minimal: These 2 modules in `analyzer/` are active, canonical, and tested.
   - Clarify semantic polarity between `opportunity_score` and `business_health_score`.
6. **Safe migration direction:**
   - Maintain both modules in `analyzer/`. Document polarity differences in data models and API schemas.
7. **Any unresolved ambiguity:**
   - Inverse scoring polarity: `opportunity_score` uses **higher = worse website** (greater sales opportunity), whereas `business_health_score` uses **higher = healthier business**.

---

### 7. Opportunity Detection
1. **Current implementation:**
   - [`business_intelligence/opportunity_mapper.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/opportunity_mapper.py) (`OpportunityMapper`): Maps detected technical weaknesses, conversion friction, and competitor gaps into concrete pitch recommendations (`service_recommendations`) and structured rationale (`opportunity_reasoning`).
   - [`analyzer/business_report_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/business_report_generator.py) (`ReportGenerator`): Formats human-readable plain text executive summaries, weakness lists, and pitch strategies.
2. **Canonical implementation:**
   - Both modules perform complementary aspects: `OpportunityMapper` for structured service mapping/rationale; `ReportGenerator` for human-readable plain text formatting.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (`ReportGenerator` at Stage 4, `OpportunityMapper` at Stage 13).
4. **Dependencies:**
   - Python standard library (`dataclasses`, `typing`, `json`).
5. **Whether consolidation is required:**
   - Yes: Currently `ReportGenerator` runs at Stage 4 before BI analysis runs at Stage 13. As a result, the plain text report generated at Stage 4 misses the rich competitor gap analysis, customer pain points, and conversion friction insights discovered later at Stage 13.
6. **Safe migration direction:**
   - Move or re-invoke `ReportGenerator` after Stage 13 in `pipeline_runner.py` so it directly consumes `OpportunityMapperResult`.
7. **Any unresolved ambiguity:**
   - Divergent recommendation taxonomies: `ScoringEngine.likely_service_match` (Stage 4) and `OpportunityMapper.service_recommendations` (Stage 13) use distinct service labeling.

---

### 8. Outreach
1. **Current implementation:**
   - [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py) (`OutreachGenerator`): Generates cold email pitches, WhatsApp drafts, outreach angles, and subject lines. Supports AI generation via Google Gemini API (`gemini-1.5-flash`) or OpenAI API (`gpt-4o-mini`) via raw HTTP `requests.post`, falling back to local deterministic templates if API keys are missing.
2. **Canonical implementation:**
   - `analyzer/outreach_generator.py`.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stage 14: lines 463–487).
   - [`tests/test_outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_outreach_generator.py).
4. **Dependencies:**
   - `requests`, `os` (reads `GEMINI_API_KEY`, `OPENAI_API_KEY`, `GEMINI_MODEL`, `OPENAI_MODEL`).
5. **Whether consolidation is required:**
   - Low: Retain module in `analyzer/`. Centralize environment variable reads into a typed configuration object; add retry and timeout policies to HTTP calls.
6. **Safe migration direction:**
   - Keep `analyzer/outreach_generator.py` canonical. Wrap LLM HTTP calls in a resilient client utility.
7. **Any unresolved ambiguity:**
   - Direct HTTP calls via `requests.post` rather than official SDKs: keeps the dependency footprint small, but requires manual HTTP status and error handling maintenance.

---

### 9. Persistence
1. **Current implementation:**
   - [`database/db.py`](file:///Users/ashik/Bens%20Repository/scrapper/database/db.py):
     - `DatabaseManager`: Manages a PostgreSQL `ThreadedConnectionPool` and executes full DDL schema via `execute_schema()` at startup.
     - `ScraperRepository`: Monolithic DAO spanning 1,312 lines and 38 methods executing raw parameterized SQL queries across 12+ tables.
   - [`database/schema.sql`](file:///Users/ashik/Bens%20Repository/scrapper/database/schema.sql): 325-line PostgreSQL DDL script defining all tables, indexes, and constraints.
   - [`dashboard/src/lib/db.ts`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard/src/lib/db.ts): Node.js `pg` pool connecting directly to PostgreSQL from Next.js Server Components.
2. **Canonical implementation:**
   - Persistence ownership belongs exclusively to `database/db.py` and `database/schema.sql`.
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py)
   - [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py)
   - [`monitoring/pipeline_monitor.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/pipeline_monitor.py)
   - [`monitoring/recrawl_scheduler.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/recrawl_scheduler.py)
   - [`intent/review_trend_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/review_trend_detector.py)
   - [`business_intelligence/competitor_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/competitor_analyzer.py)
   - Next.js Server Components via [`dashboard/src/lib/businesses.ts`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard/src/lib/businesses.ts), [`dashboard/src/app/runs/page.tsx`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard/src/app/runs/page.tsx), [`dashboard/src/app/business/[id]/page.tsx`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard/src/app/business/[id]/page.tsx).
4. **Dependencies:**
   - `psycopg2-binary` (Python), `pg` (Node.js).
5. **Whether consolidation is required:**
   - High / Critical:
     1. Eliminate Next.js direct PostgreSQL queries via Node `pg`. Frontend must fetch exclusively from FastAPI REST endpoints.
     2. Stop running DDL `execute_schema()` on every CLI pipeline invocation.
     3. Decompose `ScraperRepository` (1,312 lines) into modular repositories (`BusinessRepository`, `EnrichmentRepository`, `IntelligenceRepository`, `RunRepository`).
     4. Move ad-hoc inline SQL in `api_server.py` (DELETE, PATCH) into repository methods.
6. **Safe migration direction:**
   - Step 1: Add missing read endpoints in FastAPI to cover dashboard data requirements.
   - Step 2: Refactor Next.js server components to query FastAPI endpoints.
   - Step 3: Decompose `ScraperRepository` in Python without breaking existing method signatures.
7. **Any unresolved ambiguity:**
   - Absence of database migration tool (e.g. Alembic); schema changes are currently unversioned raw SQL scripts.

---

### 10. API
1. **Current implementation:**
   - [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py): FastAPI application running on Uvicorn. Exposes REST endpoints (`/api/businesses`, `/api/businesses/{id}`, `/api/scrape`, `/api/status`, `/api/stop`, `/api/runs`, `/api/logs` via SSE).
   - Manages pipeline execution by spawning `pipeline_runner.py` as an OS subprocess (`asyncio.create_subprocess_exec` / `subprocess.Popen`) and streaming stdout to SSE clients.
2. **Canonical implementation:**
   - `api_server.py`.
3. **Existing callers:**
   - Next.js dashboard client components (via HTTP rewrite proxy).
   - [`tests/test_api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_api_server.py).
4. **Dependencies:**
   - `fastapi`, `uvicorn`, `pydantic`, `python-dotenv`.
5. **Whether consolidation is required:**
   - Moderate:
     1. Replace OS subprocess CLI invocation with an in-process worker queue or task runner.
     2. Move inline SQL mutations in DELETE and PATCH endpoints into `ScraperRepository`.
     3. Fix SSE proxy configuration in `dashboard/next.config.ts`.
6. **Safe migration direction:**
   - Consolidate all direct DB access in `api_server.py` into repository calls. Abstract subprocess runner behind an asynchronous job executor.
7. **Any unresolved ambiguity:**
   - Subprocess runner in `api_server.py` contains Windows-specific virtualenv executable heuristics (`os.path.join(rootDir, "..", "env", "Scripts", "python.exe")`) with fallback to `sys.executable`.

---

### 11. Dashboard
1. **Current implementation:**
   - [`dashboard/`](file:///Users/ashik/Bens%20Repository/scrapper/dashboard): Next.js 16 (App Router) + React 19 + Tailwind CSS.
   - Features: Prospect list/grid view, scrape trigger panel with source selector (Google Maps, JustDial, IndiaMart), business detail view with intent badges, tech stack pills, email/decision makers, and outreach copy viewer.
   - Dual data access: Server components connect directly to PostgreSQL via Node `pg` (`src/lib/db.ts`), while client components issue mutations and trigger runs via FastAPI (`/api/scrape`, `/api/status`, `/api/businesses/[id]`).
2. **Canonical implementation:**
   - `dashboard/` directory.
3. **Existing callers:**
   - End User (Browser).
4. **Dependencies:**
   - Next.js 16, React 19, Tailwind CSS, Lucide React, Node `pg`.
5. **Whether consolidation is required:**
   - Moderate:
     1. Eliminate Node `pg` dependency and `dashboard/src/lib/db.ts`. All data fetching must go through FastAPI.
     2. Fix `/api/logs` SSE rewrite exclusion in `dashboard/next.config.ts`.
     3. Remove orphaned file `dashboard/src/lib/logEmitter.ts`.
6. **Safe migration direction:**
   - Verify FastAPI endpoints provide all fields needed by `getBusinesses()` and `getBusinessDetail()`, then convert Next.js server components to `fetch()` from FastAPI.
7. **Any unresolved ambiguity:**
   - Switching Next.js entirely to FastAPI requires that the API server is always running whenever the dashboard is running.

---

### 12. Monitoring
1. **Current implementation:**
   - [`monitoring/pipeline_monitor.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/pipeline_monitor.py) (`PipelineMonitor`): Context manager for measuring execution time, record counts, and failure tracking per pipeline stage; writes run metadata to PostgreSQL `pipeline_runs` table and local JSON/log files.
   - [`monitoring/change_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/change_detector.py) (`ChangeDetector`): Computes SHA-256 hashes of website HTML and structured payloads; detects changes across crawls and writes diff events to `change_events` table.
   - [`monitoring/recrawl_scheduler.py`](file:///Users/ashik/Bens%20Repository/scrapper/monitoring/recrawl_scheduler.py) (`RecrawlScheduler`): Queries PostgreSQL for businesses due for re-crawl based on tier cadences (Tier 1: 7 days, Tier 2: 30 days, Tier 3: 90 days).
2. **Canonical implementation:**
   - The `monitoring/` package exclusively (`monitoring/pipeline_monitor.py`, `monitoring/change_detector.py`, `monitoring/recrawl_scheduler.py`).
3. **Existing callers:**
   - [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) (stages 0, 1, 15).
   - [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) (`/api/recrawl` triggers recrawl mode).
4. **Dependencies:**
   - Python standard library (`hashlib`, `json`, `datetime`), `psycopg2-binary` (via `ScraperRepository`).
5. **Whether consolidation is required:**
   - Low: Monitoring modules are well-scoped and canonical.
   - Consolidation needed: Expose change event history through FastAPI so the dashboard can display change history. Add automated unit tests.
6. **Safe migration direction:**
   - Maintain current structure; implement automated tests.
7. **Any unresolved ambiguity:**
   - Duplicate outputs: `PipelineMonitor` writes summaries to disk (`logs/pipeline_runs.log` and `data/cache/run_summaries.json`) and also writes to PostgreSQL `pipeline_runs` table.

---

## 3. Important Architectural Migration Decisions

1. **Retire Dead Stubs in `analyzer/`:**
   The 6 duplicate files in `analyzer/` (`business_health_score.py`, `competitor_analyzer.py`, `customer_pain_extractor.py`, `review_miner.py`, `trust_signal_detector.py`, `website_conversion_analyzer.py`), along with `growth_signal_detector.py` and `social_analyzer.py`, should be safely removed in Phase 2. They are dead code, and their incompatible signatures present serious silent crash risks if accidentally imported.
2. **Retire `scraper/pipeline.py`:**
   The `AcquisitionPipeline` class is completely abandoned and should be removed or archived.
3. **Decouple Frontend from Direct PostgreSQL:**
   Next.js should be a pure consumer of the FastAPI backend. Direct `pg` Pool connections in the frontend create dual schema maintenance, connection pool bloat, and conflicting deployment requirements.
4. **Implement DOM/HTML Caching:**
   A single crawl of a website by `WebsiteAnalyzer` should cache the HTML response in memory and pass it to `TechStackDetector`, `EmailExtractor`, `DecisionMakerFinder`, `FreshnessMonitor`, `ConversionAnalyzer`, and `TrustSignalDetector`, reducing network requests from 8 requests per business down to 1.
5. **Decouple Domain Analytics from Database DAO:**
   Domain modules like `CompetitorAnalyzer` and `ReviewTrendDetector` should not receive `repo` instances. Data should be queried by the orchestrator and passed as plain dataclasses/dictionaries into the analyzers.

---

## 4. Unresolved Issues & Ambiguities

1. **Inverted Score Semantics:**
   `opportunity_score` (in `scoring_engine.py`) uses **higher = worse website** (more opportunity to pitch), whereas `business_health_score` (in `business_intelligence/`) uses **higher = healthier business**. This dual convention causes confusion when interpreting metrics in reports and dashboard views.
2. **Orchestrator Stage Sequencing:**
   `ReportGenerator` runs at Stage 4, prior to Stage 13 (Business Intelligence). Consequently, the plain-text opportunity report generated at Stage 4 does not include the rich competitor gap analysis, customer pain points, or conversion friction insights discovered later in Stage 13.
3. **Mock Data in Production Code:**
   `ReviewMiner` currently generates synthetic review praise and complaints based on hardcoded category dictionaries rather than parsing live Google Maps reviews.
