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

---

## 🔲 Phase 1 — Quick Wins (Implement Next)

These modules have skeletons. Implement the TODOs.

- [ ] `enrichment/tech_stack_detector.py` — implement `_scan_signatures()` HTML scanning
- [ ] `enrichment/email_extractor.py` — implement regex scan + mailto: href extraction
- [ ] `intent/review_trend_detector.py` — wire Phase 1 static scoring into `intent_engine`
- [ ] `intent/freshness_monitor.py` — implement copyright year extraction from footer
- [ ] `intent/intent_engine.py` — wire Phase 1 sub-module scores into composite score
- [ ] Update `pipeline_runner.py` to call enrichment modules and persist results
- [ ] Add `email_intelligence` and `tech_stacks` tables to `database/schema.sql`

---

## 🔲 Phase 2 — Intent Intelligence

- [ ] `intent/hiring_signal_detector.py` — implement `/careers` page parser
- [ ] `intent/freshness_monitor.py` — add SSL certificate expiry check
- [ ] `enrichment/social_analyzer.py` — implement HTTP HEAD reachability check per platform
- [ ] Update `intent_engine.py` to consume all Phase 2 signals
- [ ] Add `intent_profiles` table to `database/schema.sql`
- [ ] Add `social_profiles` table to `database/schema.sql`

---

## 🔲 Phase 3 — Deep Enrichment

- [ ] `enrichment/email_validator.py` — implement MX DNS lookup (`pip install dnspython`)
- [ ] `enrichment/decision_maker_finder.py` — implement about/team page parser
- [ ] `enrichment/entity_resolver.py` — implement fuzzy matching (`pip install rapidfuzz`)
- [ ] Add `decision_makers` table to `database/schema.sql`
- [ ] Integrate `decision_maker_finder` name into `outreach_generator` templates

---

## 🔲 Phase 4 — New Data Source Connectors

- [ ] `scraper/connectors/registries/opencorporates.py` — implement REST API calls
  - Register for API key, store as `OC_API_KEY` in `.env`
- [ ] `scraper/connectors/registries/justdial.py` — implement Playwright automation
  - Document CSS selectors in `AI_MEMORY/selector_changes.md`
- [ ] `scraper/connectors/registries/indiamart.py` — implement Playwright + phone reveal click
  - Document CSS selectors in `AI_MEMORY/selector_changes.md`
- [ ] Add `company_registry` table to `database/schema.sql`
- [ ] Run `entity_resolver.compare()` after each JustDial/IndiaMart scrape

---

## 🔲 Phase 5 — Monitoring Layer

- [ ] `monitoring/pipeline_monitor.py` — implement full stage-level recording
- [ ] `monitoring/change_detector.py` — implement field-level diff comparison
- [ ] `monitoring/recrawl_scheduler.py` — implement DB query for overdue businesses
- [ ] Add `change_events` and `pipeline_runs` tables to `database/schema.sql`
- [ ] Wire `recrawl_scheduler` into `pipeline_runner.py` as an optional mode

---

## 🔲 Phase 6 — Dashboard Enhancements

- [ ] Add outreach status tracking to dashboard (New → Contacted → Followed-up → Closed)
- [ ] Add intent score column and urgency badge to lead list view
- [ ] Add tech stack badges to business detail view
- [ ] Add email + decision maker fields to business detail panel
- [ ] Add pipeline run history view (from `pipeline_monitor` summaries)
- [ ] Add CSV bulk export with all enrichment fields

---

## 🔲 Future (Backlog)

- [ ] LLM-powered outreach generation (Gemini / OpenAI API integration)
- [ ] `analyzer/seo_checker.py` — implement advanced SEO checks
- [ ] `scraper/connectors/social/social_scraper.py` — deep Instagram/Facebook audit
- [ ] `intent/review_trend_detector.py` Phase 2 — historical snapshot comparison
- [ ] FastAPI backend to replace Next.js API routes
