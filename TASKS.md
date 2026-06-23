# Tasks

## ✅ Completed

- [x] Google Maps scraper (`scraper/connectors/public_web/google_maps.py`)
- [x] Website analyzer / static auditor (`scraper/connectors/public_web/company_website.py`)
- [x] Tech signal analyzer — DNS, SSL checks (`scraper/connectors/technical/tech_signals.py`)
- [x] `base_scraper.py` — abstract interface for all connectors
- [x] `pipeline.py` — connector orchestration layer
- [x] `scraper/utils/logger.py` — centralized logging utility
- [x] `scraper/utils/exceptions.py` — shared exception types
- [x] `scoring_engine.py` — heuristic opportunity scoring
- [x] `business_report_generator.py` — human-readable opportunity reports
- [x] `outreach_generator.py` — cold email + WhatsApp pitch templates
- [x] `database/schema.sql` — PostgreSQL schema (5 tables)
- [x] `database/db.py` — connection pool + data access repository
- [x] `pipeline_runner.py` — end-to-end orchestrator with argparse CLI
- [x] Next.js dashboard — list/grid views, scrape trigger, business details
- [x] Skeleton modules created for all new layers (enrichment, intent, monitoring, registries)
- [x] `enrichment/tech_stack_detector.py` — implement `_scan_signatures()` HTML scanning
- [x] `enrichment/email_extractor.py` — implement regex scan + mailto: href extraction
- [x] `intent/review_trend_detector.py` — wire Phase 1 static scoring into `intent_engine`
- [x] `intent/freshness_monitor.py` — implement copyright year extraction from footer
- [x] `intent/intent_engine.py` — wire Phase 1 sub-module scores into composite score
- [x] Update `pipeline_runner.py` to call enrichment modules and persist results
- [x] Add `email_intelligence` and `tech_stacks` tables to `database/schema.sql`

---

## 🔲 Phase 1 — Quick Wins (Completed)

All Phase 1 quick wins are fully implemented, tested, and integrated end-to-end with the DB schema!

---

## ✅ Phase 2 — Intent Intelligence (Completed)

- [x] `intent/hiring_signal_detector.py` — implement `/careers` page parser
- [x] `intent/freshness_monitor.py` — add SSL certificate expiry check
- [x] `enrichment/social_analyzer.py` — implement HTTP reachability and redirect checks per platform
- [x] Update `intent_engine.py` to consume all Phase 2 signals
- [x] Add `intent_profiles` table to `database/schema.sql`
- [x] Add `social_profiles` table to `database/schema.sql`

---

## ✅ Phase 3 — Deep Enrichment (Completed)

- [x] `enrichment/email_validator.py` — implement MX DNS lookup (`pip install dnspython`)
- [x] `enrichment/decision_maker_finder.py` — implement about/team page parser
- [x] `enrichment/entity_resolver.py` — implement fuzzy matching (`pip install rapidfuzz`)
- [x] Add `decision_makers` table to `database/schema.sql`
- [x] Integrate `decision_maker_finder` name into `outreach_generator` templates

---
## ✅ Phase 4 — Business Intelligence Layer

### Revenue Friction Analysis

* [x] `business_intelligence/conversion_analyzer.py`

  * [x] detect missing booking flows
  * [x] detect weak call-to-actions
  * [x] detect lead capture forms
  * [x] detect contact friction
  * [x] detect WhatsApp availability
  * [x] generate conversion friction score

### Customer Pain Mining

* [x] `business_intelligence/review_miner.py`

  * [x] collect review text
  * [x] identify recurring complaints
  * [x] identify recurring praise
  * [x] classify common themes

* [x] `business_intelligence/customer_pain_extractor.py`

  * [x] aggregate review insights
  * [x] identify service bottlenecks
  * [x] identify communication issues
  * [x] identify booking-related complaints
  * [x] identify trust-related complaints

### Competitor Intelligence

* [x] `business_intelligence/competitor_analyzer.py`

  * [x] identify nearby competitors
  * [x] compare website quality
  * [x] compare SEO signals
  * [x] compare conversion features
  * [x] generate competitor gap analysis

### Trust & Credibility Analysis

* [x] `business_intelligence/trust_signal_detector.py`

  * [x] testimonials
  * [x] certifications
  * [x] review widgets
  * [x] awards
  * [x] trust badges
  * [x] social proof indicators

### Opportunity Mapping

* [x] `business_intelligence/opportunity_mapper.py`

  * [x] map detected issues to services
  * [x] generate business impact explanations
  * [x] generate service recommendations
  * [x] generate opportunity reasoning

### Business Health Scoring

* [x] `business_intelligence/business_health_score.py`

  * [x] combine website quality
  * [x] combine review signals
  * [x] combine trust indicators
  * [x] combine conversion indicators
  * [x] generate overall business health score

### Database

* [x] Add `business_health_profiles` table
* [x] Add `competitor_analysis` table
* [x] Add `customer_pain_signals` table

### Integration

* [x] Wire business intelligence modules into `pipeline_runner.py`
* [x] Surface intelligence summaries inside dashboard
* [x] Include opportunity reasoning in outreach generation

## ✅ Phase 5— New Data Source Connectors

- [x] `scraper/connectors/registries/opencorporates.py` — implement REST API calls
  - Register for API key, store as `OC_API_KEY` in `.env`
- [x] `scraper/connectors/registries/justdial.py` — implement Playwright automation
  - Document CSS selectors in `AI_MEMORY/selector_changes.md`
- [x] `scraper/connectors/registries/indiamart.py` — implement Playwright + phone reveal click
  - Document CSS selectors in `AI_MEMORY/selector_changes.md`
- [x] Add `company_registry` table to `database/schema.sql`
- [x] Run `entity_resolver.compare()` after each JustDial/IndiaMart scrape

---

## ✅ Phase 6— Monitoring Layer (Completed)

- [x] `monitoring/pipeline_monitor.py` — implement full stage-level recording
- [x] `monitoring/change_detector.py` — implement field-level diff comparison
- [x] `monitoring/recrawl_scheduler.py` — implement DB query for overdue businesses
- [x] Add `change_events` and `pipeline_runs` tables to `database/schema.sql`
- [x] Wire `recrawl_scheduler` into `pipeline_runner.py` as an optional mode

---

## ✅ Phase 7— Dashboard Enhancements

- [x] Add outreach status tracking to dashboard (New → Contacted → Followed-up → Closed)
- [x] Add intent score column and urgency badge to lead list view
- [x] Add tech stack badges to business detail view
- [x] Add email + decision maker fields to business detail panel
- [x] Add pipeline run history view (from `pipeline_monitor` summaries)
- [x] Add CSV bulk export with all enrichment fields

---

## 🔲 Future (Backlog)

- [ ] LLM-powered outreach generation (Gemini / OpenAI API integration)
- [ ] `analyzer/seo_checker.py` — implement advanced SEO checks
- [ ] `scraper/connectors/social/social_scraper.py` — deep Instagram/Facebook audit
- [ ] `intent/review_trend_detector.py` Phase 2 — historical snapshot comparison
- [ ] FastAPI backend to replace Next.js API routes
