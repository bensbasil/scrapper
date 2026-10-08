# Phase 4B — Prospect Qualification & Selection

**Status:** COMPLETE  
**Date:** 2026-10-08  
**Architecture Layer:** Agent Orchestration / Domain Qualification (`agent/qualification.py`, `agent/prospects.py`, `agent/agent.py`)

---

## 1. Executive Summary & Objective

In Phase 4A, the platform established `ProspectSet`, `ProspectSelection`, and sequential execution via `ProspectBatchExecutor`. However, without a qualification filter, all discovered candidates meeting basic limits were candidate inputs for expensive deep analysis (website auditing, tech signal extraction, review sentiment mining, context compilation, and LLM-powered opportunity reasoning).

Phase 4B introduces a **deterministic, fast, in-memory qualification stage** positioned between discovery and candidate selection:
```text
User Goal
   ↓
Discovery
   ↓
ProspectSet
   ↓
Qualification (Deterministic Rules & Signals)
   ↓
QualifiedProspectSet
   ↓
ProspectSelection (Filters & Bounds on Qualified)
   ↓
Deep Analysis (CapabilityRegistry Execution)
   ↓
Opportunity Ranking
```

This prevents expensive compute and external rate limit consumption on non-viable businesses (e.g. invalid entities, mismatched categories, out-of-boundary locations, or businesses already engaged).

---

## 2. Critical Architectural Distinction: Qualification vs. Opportunity Score

A central architectural mandate of Phase 4B is the strict separation between **Qualification** and **Opportunity Scoring**:

| Dimension | Prospect Qualification | Opportunity Analysis |
| :--- | :--- | :--- |
| **Question Answered** | *"Is this prospect worth spending computation on?"* | *"How strong is the actual business sales pitch / opportunity?"* |
| **Pipeline Stage** | Pre-Analysis (immediately following Discovery) | Post-Analysis (after technical audits & evidence synthesis) |
| **Model** | [`ProspectQualification`](file:///Users/ashik/Bens%20Repository/scrapper/agent/qualification.py) / `qualification_score` | [`OpportunityAnalysis`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py) / `opportunity_score` |
| **Computation Cost** | In-memory, sub-millisecond, zero network/LLM calls | Deep, multi-step capabilities, LLM reasoning synthesis |
| **Input Signals** | Raw discovery fields (`website`, `phone`, `category`, `address`, `ratings`) | Deep technical signals, conversion friction, review sentiment, SEO deficits |
| **Scoring Formula** | Simple deterministic prioritization heuristic `[0.0 - 1.0]` | Normalized commercial pitch scoring `[0.0 - 100.0]` |

**No Second Scoring Engine:** Qualification never attempts to duplicate or replace the Phase 1/Phase 2 scoring engines or the Phase 2C opportunity reasoner.

---

## 3. Qualification Signals & Deterministic Policy Rules

Qualification inspects only canonical fields already present on the [`Business`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py) model produced by discovery.

### 3.1 Evaluated Signals
- **`business_name`**: Entity identification validity.
- **`website`**: Presence and formatting of URL.
- **`phone`**: Contact viability.
- **`category`**: Trade or vertical classification.
- **`address` / `city`**: Geographic location string.
- **`google_rating` / `jd_rating` / `im_rating`**: Directory ratings.
- **`review_count` / `jd_reviews_count`**: Customer feedback volume.
- **`jd_verified` / `im_verified` / `im_gst_verified`**: Directory authentication flags.
- **`outreach_status`**: Current CRM/engagement state (`new`, `contacted`, `followed_up`, `closed`).

### 3.2 Qualification Policy (`QualificationPolicy`)
Configurable deterministic criteria with automatic derivation from `AgentIntent`:
- **`require_website: bool`** (default `False`): If required, missing URL disqualifies. If optional, missing website is recorded as a valid candidate for digital presence creation.
- **`require_phone: bool`** (default `False`): If required, missing phone number disqualifies.
- **`target_location: Optional[str]`**: Case-insensitive substring match against `address` and `city`.
- **`target_industry: Optional[str]`**: Case-insensitive substring match against `category`.
- **`min_rating: Optional[float]`**: Threshold floor for directory ratings.
- **`min_reviews: Optional[int]`**: Threshold floor for customer review counts.
- **`exclude_already_contacted: bool`** (default `True`): Disqualifies prospects with `outreach_status` in `('contacted', 'followed_up', 'closed')`.

### 3.3 Rule Decisions & Explainability
Every prospect receives:
- **`qualified: bool`**: `True` only if `len(disqualifiers) == 0`.
- **`reasons: List[str]`**: Positive criteria satisfied (e.g. `"Website URL present: https://..."`, `"Fresh prospect (outreach_status='new')"`).
- **`disqualifiers: List[str]`**: Clear failure explanations (e.g. `"Outside requested location: address 'Miami, FL' does not match 'Chicago'"`).
- **`qualification_score: float`**: Pre-analysis sorting score `[0.0 - 1.0]` (0.0 if disqualified, base 0.50 + increments for website, phone, directory verification, review presence).

---

## 4. Domain Set & Selection Flow

### 4.1 `QualifiedProspectSet`
Positioned in [`agent/prospects.py`](file:///Users/ashik/Bens%20Repository/scrapper/agent/prospects.py), `QualifiedProspectSet` partitions a `ProspectSet`:
- **`set_id`**: Qualified set identifier (`qset_...`).
- **`original_set_id`**: Links back to source `ProspectSet`.
- **`total_discovered`**: Total count before qualification.
- **`qualified_count`**: Number passing policy.
- **`disqualified_count`**: Number failing policy.
- **`qualifications`**: Map of `business_name -> ProspectQualification`.
- **`qualified_prospects`**: List of references to qualified [`Business`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py) instances.
- **`disqualified_prospects`**: List of references to disqualified [`Business`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py) instances.

Zero schema duplication: references canonical `Business` models directly.

### 4.2 Selection Boundary (`ProspectSelection`)
`ProspectSelection.select` supports both `ProspectSet` and `QualifiedProspectSet`:
```python
if isinstance(prospect_source, QualifiedProspectSet):
    candidates = list(prospect_source.qualified_prospects)
else:
    candidates = list(prospect_source.prospects)
```
- Disqualified prospects are **never** included in `selected_prospects`.
- Candidates can be sorted by `qualification_score_desc`, `rating_asc`, `rating_desc`, or `review_count_desc`.
- Bounded by `self.max_prospects` and safety limit `max_prospects_per_run`.

---

## 5. Telemetry & Observability Integration

Telemetry records the qualification phase without logging bloated business payloads:
- Emits a `step_qualify` trace event (`capability_name="qualify_prospects"`, status `COMPLETED`, duration in ms).
- Emits per-prospect qualification trace events (`capability_name="qualify_prospect"`, status `COMPLETED` if qualified, `SKIPPED` if disqualified).
- Records high-level aggregate metrics on [`AgentRunTrace`](file:///Users/ashik/Bens%20Repository/scrapper/agent/telemetry.py):
  - `discovered_count`
  - `qualified_count`
  - `disqualified_count`
  - `selected_count`
  - `qualification_duration_ms`

---

## 6. Safety Limits & Failure Behavior

- **Zero-Qualified Sets**: If all discovered prospects are disqualified by policy checks, `QualifiedProspectSet.qualified_count == 0`. Selection yields `[]`, and `Agent.run_prospect_batch` transitions cleanly to `COMPLETED` with reason `"zero prospects qualified for deep analysis"` rather than failing or erroring.
- **Batch Safety Limit**: `max_prospects_per_run` continues to clamp selection even if hundreds of prospects qualify.
- **Known-Business Workflows**: Known-business requests (e.g. "Analyze Acme Plumbing") bypass batch qualification and execute single-business plans directly, ensuring 100% backward compatibility.

---

## 7. Verification & Test Suite Summary

All 22 test requirements are implemented and verified in [`tests/test_prospect_qualification.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_prospect_qualification.py):

| # | Test Scenario | Verified Behavior |
| :--- | :--- | :--- |
| 1 | `test_01_qualification_model_creation` | Validates typed `ProspectQualification` attributes and evaluated signals. |
| 2 | `test_02_qualified_prospect` | Verifies clean qualification of active, valid business entities. |
| 3 | `test_03_disqualified_prospect` | Verifies rejection for missing business names or already-contacted status. |
| 4 | `test_04_qualification_reasons` | Confirms explainable positive reasons for passed criteria. |
| 5 | `test_05_disqualifier_reasons` | Confirms explicit rejection reasons for missing requirements. |
| 6 | `test_06_all_prospects_receive_a_result` | Verifies every candidate in the set receives an individual result record. |
| 7 | `test_07_qualified_set_creation` | Validates `QualifiedProspectSet` attributes, counts, and compatibility properties. |
| 8 | `test_08_disqualified_set_preservation` | Confirms rejected businesses are preserved in `disqualified_prospects`. |
| 9 | `test_09_zero_qualified_prospects` | Confirms graceful handling when zero prospects meet policy criteria. |
| 10 | `test_10_all_qualified_prospects` | Confirms accurate partitioning when all prospects meet policy criteria. |
| 11 | `test_11_location_filtering` | Verifies deterministic rejection of candidates outside target geographic area. |
| 12 | `test_12_industry_filtering` | Verifies deterministic rejection of candidates in non-matching business verticals. |
| 13 | `test_13_selection_after_qualification` | Verifies bounded selection operates on qualified candidates. |
| 14 | `test_14_selection_never_includes_disqualified_prospects` | Proves disqualified candidates are strictly excluded from selection. |
| 15 | `test_15_batch_size_limit_remains_enforced` | Confirms `max_prospects_per_run` safety limit clamps qualified selection. |
| 16 | `test_16_known_business_workflow_remains_unchanged` | Verifies known-business workflows execute without qualification gating. |
| 17 | `test_17_qualification_does_not_call_llm` | Proves qualification makes 0 LLM calls. |
| 18 | `test_18_qualification_does_not_bypass_registry` | Proves capability execution continues exclusively via `CapabilityRegistry`. |
| 19 | `test_19_qualification_telemetry` | Confirms qualification trace events and `AgentRunTrace` counters. |
| 20 | `test_20_aggregate_counts` | Verifies exact matching of discovered, qualified, disqualified, and selected counts. |
| 21 | `test_21_existing_phase_4a_tests_remain_valid` | Proves Phase 4A batch ranking adapters continue working on qualified results. |
| 22 | `test_22_existing_phase_3_tests_remain_valid` | Proves Phase 3 single-business execution workflows remain completely valid. |

**Total Test Results:**
- 205 tests passing across all platform suites (0 failures, 0 errors).
- Execution time: 0.30s.
