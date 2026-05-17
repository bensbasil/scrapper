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

## Phase 2 — Enrichment 🔄 IN PROGRESS

**Goal:** Go beyond scraped data. Extract emails, detect tech stack, identify decision-makers.

| Deliverable | Status |
| :---------- | :----- |
| Skeleton modules created | ✅ Done |
| `tech_stack_detector` — CMS/analytics detection | 🔲 Next |
| `email_extractor` — email discovery from website | 🔲 Next |
| `email_validator` — MX + syntax validation | 🔲 Next |
| `decision_maker_finder` — owner/founder discovery | 🔲 Next |
| `social_analyzer` — social account audit | 🔲 Next |
| `entity_resolver` — cross-source deduplication | 🔲 Next |
| New DB tables for enrichment data | 🔲 Next |

---

## Phase 3 — Intent Intelligence 🔲 PLANNED

**Goal:** Surface which businesses are most receptive to outreach **right now**.

| Deliverable | Status |
| :---------- | :----- |
| `review_trend_detector` — rating decline signals | 🔲 Planned |
| `freshness_monitor` — stale website detection | 🔲 Planned |
| `hiring_signal_detector` — technical job listing signals | 🔲 Planned |
| `intent_engine` — composite intent scoring | 🔲 Planned |
| Intent score exposed on dashboard | 🔲 Planned |

---

## Phase 4 — New Data Sources 🔲 PLANNED

**Goal:** Expand coverage beyond Google Maps with India-specific sources.

| Deliverable | Status |
| :---------- | :----- |
| `justdial.py` connector | 🔲 Planned |
| `indiamart.py` connector | 🔲 Planned |
| `opencorporates.py` API connector | 🔲 Planned |
| Cross-source deduplication via `entity_resolver` | 🔲 Planned |

---

## Phase 5 — Monitoring & Recrawl 🔲 PLANNED

**Goal:** Keep the intelligence platform fresh over time without manual re-runs.

| Deliverable | Status |
| :---------- | :----- |
| `recrawl_scheduler` — tier-based re-scraping policy | 🔲 Planned |
| `change_detector` — detect website changes between crawls | 🔲 Planned |
| `pipeline_monitor` — run health metrics and summaries | 🔲 Planned |
| Run history visible in dashboard | 🔲 Planned |

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
