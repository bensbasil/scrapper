# Roadmap

## Vision

Build a modular, AI-powered Lead Intelligence Platform that:

1. Discovers local businesses across multiple data sources
2. Enriches them with digital presence signals
3. Detects intent — who needs help **right now**
4. Generates actionable, personalized outreach
5. Monitors and re-evaluates leads over time

---

## Phase 1 — Foundation ✅ COMPLETE

**Goal:** Core scrape → analyze → score → outreach pipeline working end-to-end.

| Deliverable | Status |
| :---------- | :----- |
| Google Maps scraper (Playwright) | ✅ Done |
| Website static auditor (BeautifulSoup) | ✅ Done |
| Tech signal analyzer (DNS/SSL) | ✅ Done |
| Scoring engine (heuristic rules) | ✅ Done |
| Business report generator | ✅ Done |
| Outreach generator (email + WhatsApp) | ✅ Done |
| PostgreSQL schema (5 tables) | ✅ Done |
| Database repository layer | ✅ Done |
| Pipeline orchestrator CLI | ✅ Done |
| Next.js dashboard (list/grid/detail) | ✅ Done |
| 500+ businesses processed and stored | ✅ Done |

---

## Phase 2 — Enrichment ✅ COMPLETE

**Goal:** Go beyond scraped data. Extract emails, detect tech stack, identify decision-makers.

| Deliverable | Status |
| :---------- | :----- |
| Skeleton modules created | ✅ Done |
| `tech_stack_detector` — CMS/analytics detection | ✅ Done |
| `email_extractor` — email discovery from website | ✅ Done |
| `email_validator` — MX + syntax validation | ✅ Done |
| `decision_maker_finder` — owner/founder discovery | ✅ Done |
| `social_analyzer` — social account audit | ✅ Done |
| `entity_resolver` — cross-source deduplication | ✅ Done |
| New DB tables for enrichment data | ✅ Done |

---

## Phase 3 — Intent Intelligence ✅ COMPLETE

**Goal:** Surface which businesses are most receptive to outreach **right now**.

| Deliverable | Status |
| :---------- | :----- |
| `review_trend_detector` — rating decline signals | ✅ Done |
| `freshness_monitor` — stale website detection | ✅ Done |
| `hiring_signal_detector` — technical job listing signals | ✅ Done |
| `intent_engine` — composite intent scoring | ✅ Done |
| Intent score exposed on dashboard | ✅ Done |

---

## Phase 4 — New Data Sources ✅ COMPLETE

**Goal:** Expand coverage beyond Google Maps with India-specific sources.

| Deliverable | Status |
| :---------- | :----- |
| `opencorporates.py` API connector | ✅ Done |
| `justdial.py` connector | ✅ Done |
| `indiamart.py` connector | ✅ Done |
| Cross-source deduplication via `entity_resolver` | ✅ Done |

---

## Phase 5 — Monitoring & Recrawl ✅ COMPLETE

**Goal:** Keep the intelligence platform fresh over time without manual re-runs.

| Deliverable | Status |
| :---------- | :----- |
| `recrawl_scheduler` — tier-based re-scraping policy | ✅ Done |
| `change_detector` — detect website changes between crawls | ✅ Done |
| `pipeline_monitor` — run health metrics and summaries | ✅ Done |
| Run history visible in dashboard | ✅ Done |

---

## Phase 6 — Dashboard & CRM Layer 🔲 PLANNED

**Goal:** Upgrade the dashboard into a lightweight lead management interface.

| Deliverable | Status |
| :---------- | :----- |
| Outreach status tracking (New → Contacted → Closed) | 🔲 Planned |
| Intent score badge + urgency filter | 🔲 Planned |
| Tech stack badges on business cards | 🔲 Planned |
| Email + decision maker fields in detail view | 🔲 Planned |
| Bulk CSV export with all enrichment fields | 🔲 Planned |
| Pipeline run history panel | 🔲 Planned |

---

## Phase 7 — AI Layer 🔲 FUTURE

**Goal:** Replace rule-based outreach with LLM-generated, hyper-personalized copy.

| Deliverable | Status |
| :---------- | :----- |
| Gemini / OpenAI API integration | 🔲 Future |
| LLM-powered cold email generation | 🔲 Future |
| LLM-powered WhatsApp message generation | 🔲 Future |
| Predictive opportunity scoring (ML model) | 🔲 Future |
| Automated outreach follow-up suggestions | 🔲 Future |

---

## Guiding Principles

- **MVP simplicity first** — don't overengineer before the simpler version is proven
- **One module at a time** — implement, test, wire into pipeline, then move on
- **Preserve working functionality** — never refactor a working module while building a new one
- **Log everything** — every module uses centralized logging
- **Modular outputs** — every module returns a `@dataclass`, not raw strings or dicts
