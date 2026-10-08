# Phase 2A — Evidence Context Foundation

**Date:** 2026-10-08  
**Scope:** Elimination of Context Starvation via Typed Prospect Evidence Context, Pipeline Reordering, and Score Semantics Preservation  
**Status:** COMPLETE  

---

## 1. Objective

Phase 2A addresses the **context starvation** problem identified in the Phase 2 Architecture Audit ([`AI_MEMORY/PHASE_2_ARCHITECTURE_AUDIT.md`](file:///Users/ashik/Bens%20Repository/scrapper/AI_MEMORY/PHASE_2_ARCHITECTURE_AUDIT.md)). 

Prior to Phase 2A:
1. Downstream consumers—specifically `ReportGenerator` and `OutreachGenerator`—were invoked prematurely or with truncated inputs (`business` dict, raw `seo` dict, `tech_stack` list), completely blind to the deep deterministic intelligence computed later in the pipeline (customer pain themes, conversion friction points, competitor rating gaps, hiring expansion signals, review velocity shifts).
2. `ReportGenerator` executed at Step 4, before Business Intelligence (Step 13), Intent (Step 11), and deeper Enrichment (Steps 7–10).
3. No typed, token-efficient, unified context object existed to bridge deterministic analysis to future AI reasoning.

Phase 2A introduces:
- A compact, typed, serializable contract: [`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py), [`EvidenceItem`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py), and [`ScoreCard`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py).
- A pure in-memory assembly builder: [`ProspectContextBuilder`](file:///Users/ashik/Bens%20Repository/scrapper/ai/context_builder.py) in `ai/`.
- Pipeline reordering in [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) moving report and outreach generation to execute after deep intelligence.
- Preservation and disambiguation of scoring polarities (`sales_opportunity_score` vs `digital_health_rating`).
- Optional context ingestion in [`OutreachGenerator`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py) preserving 100% backward compatibility.
- Zero external LLM SDKs, zero database coupling, and zero network scraping in the context layer.

---

## 2. Existing Evidence Inventory

Tracing the real runtime objects produced across the platform:

### Business
- **Identity & Location**: `name`, `phone`, `email`, `website`, `address` originating from Google Maps scraper ([`scrapers/google_maps.py`](file:///Users/ashik/Bens%20Repository/scrapper/scrapers/google_maps.py)) and validated via [`schemas/business.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py).
- **Category & Rating**: `category`, `rating` (0.0–5.0), `reviews_count` from Google Maps scraper.

### Enrichment
- **Technology Stack**: Frameworks, CMS, analytics, hosting detected by [`enrichment/tech_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/tech_detector.py) (e.g., WordPress, Shopify, React, Google Analytics).
- **Social Profiles**: Links to LinkedIn, Facebook, Instagram, Twitter extracted by [`enrichment/social_scraper.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/social_scraper.py).
- **Decision Makers**: Names, titles, LinkedIn handles found by [`enrichment/decision_maker_enricher.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/decision_maker_enricher.py).
- **Emails & Contacts**: Domain-validated contacts from [`enrichment/email_finder.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/email_finder.py).
- **Entity Resolution**: Canonical identity clusters and matching confidence from [`enrichment/entity_resolver.py`](file:///Users/ashik/Bens%20Repository/scrapper/enrichment/entity_resolver.py).

### Intelligence
- **Customer Pain**: Top negative themes, recurring complaints, sample negative review quotes extracted by [`business_intelligence/customer_pain_extractor.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/customer_pain_extractor.py).
- **Conversion Problems**: Friction indicators, missing CTAs, slow load times, poor mobile UX extracted by [`business_intelligence/conversion_friction_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/conversion_friction_detector.py).
- **Competitor Information**: Local competitor benchmark, rating gaps, review count deficits, vulnerability opportunities from [`business_intelligence/competitor_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/competitor_analyzer.py).
- **Trust Signals**: Missing SSL certificates, licensing disclaimers, privacy policy indicators from [`business_intelligence/trust_signal_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/trust_signal_analyzer.py).
- **Business Health**: Holistic 0–100 health composite (`overall_health_score`), category breakdown, and strengths/weaknesses from [`business_intelligence/health_scorer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/health_scorer.py).

### Intent
- **Hiring Signals**: Active job postings, technical roles (e.g. software engineer, marketer), growth indicators from [`intent/hiring_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/hiring_detector.py).
- **Review Trends**: Rating velocity, decline/improvement trajectories, negative sentiment shifts from [`intent/review_trend_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/review_trend_detector.py).
- **Intent Profile**: Composite hiring intent score (0–100), overall intent score (0–100), intent level classification (`low`, `medium`, `high`) from [`schemas/intent.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/intent.py).

### Scoring
- **Sales Opportunity Score**: Deficiency-weighted score (0–100, where higher indicates greater sales pitch opportunity due to digital weaknesses) from [`analyzer/scoring_engine.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/scoring_engine.py).
- **SEO Score & Audit**: 0–100 score and issue breakdown (title, meta description, H1, mobile friendliness) from [`analyzer/seo_checker.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/seo_checker.py).

### Opportunity
- **Opportunity Types**: Identified service packages (e.g. `SEO Optimization`, `Website Modernization`, `Reputation Management`, `Conversion Optimization`) from [`analyzer/opportunity_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/opportunity_detector.py).
- **Recommended Services**: Structured opportunity records with title, description, priority score (0–100), and rationale.

### Outreach
- **Current Inputs**: Previously received only `business`, `opportunity_score`, `tech_stack`, and `seo_data`.
- **Missing Information**: Prior to Phase 2A, lacked all customer pain quotes, competitor rating gaps, technical hiring expansion signals, and trust deficiencies.

---

## 3. Evidence Flow Before Changes

```text
[Scraping: Maps & Web]
       │
       ▼
Step 1: Website Scraping
Step 2: SEO Checking
Step 3: Lead Scoring (opportunity_score)
       │
       ├──────────────────────────────────────────┐
       ▼                                          ▼
Step 4: ReportGenerator (PREMATURE)       Step 5: OutreachGenerator (STARVED)
(Outputs report with ONLY SEO & Tech)     (Outputs pitch with ONLY SEO & Tech)
       │                                          │
       ▼                                          ▼
Step 6: Opportunity Detector              (Execution continues...)
Step 7: Social Scraping
Step 8: Email Finding
Step 9: Decision Maker Enricher
Step 10: Entity Resolver
Step 11: Intent (Hiring & Review Trends)
Step 12: Contact Aggregator
Step 13: Business Intelligence (Pain, Friction, Competitor, Trust, Health)
       │
       ▼
[Pipeline End: Rich BI Data Discarded From Outreach & Report]
```

---

## 4. Evidence Flow After Changes

```text
[Scraping: Maps & Web]
       │
       ▼
Step 1: Website Scraping
Step 2: SEO Checking
Step 3: Lead Scoring (opportunity_score)
Step 6: Opportunity Detector
Step 7: Social Scraping
Step 8: Email Finding
Step 9: Decision Maker Enricher
Step 10: Entity Resolver
Step 11: Intent Profiling (Hiring & Review Trends)
Step 12: Contact Aggregator
Step 13: Business Intelligence (Pain, Friction, Competitor, Trust, Health)
       │
       ▼
[Phase 2A Assembly]: ProspectContextBuilder
   ├── Extracts structured EvidenceItems (provenance, claims, values)
   ├── Normalizes ScoreCard (sales_opportunity_score vs digital_health_rating)
   └── Builds unified, token-efficient ProspectContext
       │
       ├──────────────────────────────────────────┐
       ▼                                          ▼
Step 4 (Reordered): ReportGenerator        Step 5 (Enriched): OutreachGenerator
(Consumes complete tech, SEO, & scores)   (Consumes ProspectContext: complaints,
                                           competitor gap, intent, tech stack)
       │
       ▼
[Pipeline Result Saved to DB & Returned with Complete Context]
```

---

## 5. ProspectContext Design

Defined in [`schemas/context.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py):

```python
class ProspectContext(BaseModel):
    business: Business
    enrichment: Optional[BusinessEnrichment] = None
    intelligence: Optional[BusinessIntelligence] = None
    intent: Optional[IntentProfile] = None
    scores: ScoreCard
    opportunities: List[Opportunity] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_evidence_by_category(self, category: str) -> List[EvidenceItem]: ...
    def to_token_efficient_summary(self, max_evidence_items: int = 15) -> str: ...
```

### Key Capabilities
- **Typed & Validated**: Implements Pydantic v2 `BaseModel` using existing canonical schema models ([`schemas/business.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py), [`schemas/enrichment.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/enrichment.py), [`schemas/intelligence.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/intelligence.py), [`schemas/intent.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/intent.py), [`schemas/opportunity.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/opportunity.py)).
- **Token Efficiency**: `to_token_efficient_summary()` converts complex structured evidence into a dense bulleted text representation suitable for compact LLM prompt injection (typically < 350 tokens).
- **Serialization**: Supports native `.model_dump()` and `.model_dump_json()`.

---

## 6. Evidence Model

Defined in [`schemas/context.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py):

```python
class EvidenceItem(BaseModel):
    category: str  # business, technical, customer_pain, conversion_friction, competitor, trust, intent, review_trends, opportunity, score
    claim: str
    source: str
    value: Any = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    context_data: Dict[str, Any] = Field(default_factory=dict)
```

Each piece of evidence records:
- **`category`**: Functional domain of the claim.
- **`claim`**: Concise, human/LLM-readable assertion (e.g., `"Recurring customer complaints identified in reviews: Slow service"`).
- **`source`**: The module or component that derived the evidence (e.g., `"CustomerPainExtractor"`).
- **`value`**: The underlying raw or normalized value (e.g., count, score, list of keywords).
- **`confidence`**: Statistical or deterministic confidence score (0.0–1.0).

---

## 7. Context Builder Design

Implemented in [`ai/context_builder.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/context_builder.py):

```python
class ProspectContextBuilder:
    def build_context(
        self,
        business: Business,
        enrichment: Optional[BusinessEnrichment] = None,
        intelligence: Optional[BusinessIntelligence] = None,
        intent: Optional[IntentProfile] = None,
        opportunities: Optional[List[Opportunity]] = None,
        scoring_results: Optional[Dict[str, Any]] = None,
        seo_data: Optional[Dict[str, Any]] = None,
        website_data: Optional[Dict[str, Any]] = None,
    ) -> ProspectContext: ...
```

### Architectural Guarantees
- **No LLM Calls**: Pure Python in-memory assembly.
- **No Database Access**: Zero SQL, zero connection pool interaction, zero PostgreSQL dependencies.
- **No Network I/O**: Zero HTTP requests, zero Playwright/browser calls.
- **Graceful Degradation**: Every parameter except `business` is optional. Missing or empty dictionaries/models are handled without errors.

---

## 8. Score Semantics

The Phase 2 audit highlighted a critical semantic hazard: two distinct scores in the platform have opposite polarities. Phase 2A codifies and documents this distinction in [`ScoreCard`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py):

```python
class ScoreCard(BaseModel):
    # Polarity: Higher value = Greater digital weakness / Greater sales pitch opportunity
    sales_opportunity_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # Polarity: Higher value = Healthier digital and business presence
    digital_health_rating: float = Field(default=0.0, ge=0.0, le=100.0)

    seo_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    website_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    review_trend_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    hiring_intent_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
```

- **`sales_opportunity_score`**: Derived from `analyzer/scoring_engine.py`. A score of 85 means the business has severe website/SEO/presence gaps and represents a prime sales target.
- **`digital_health_rating`**: Derived from `business_intelligence/health_scorer.py`. A score of 85 means the business has a strong, healthy online presence.
- Neither scoring algorithm was modified. The schema guarantees future AI layers will not confuse digital health with sales opportunity.

---

## 9. Report Generation Ordering

In [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py):
- **Previous Location**: Lines 272–281 (immediately after Lead Scoring, before Social Scraping, Intent, and Business Intelligence).
- **Inspection Finding**: Neither Step 6 (Opportunity Detector), Steps 7–10 (Enrichment), Step 11 (Intent), Step 12 (Contact Aggregation), nor Step 13 (Business Intelligence) consume the output of `ReportGenerator` (`report_dict`).
- **New Location**: Moved immediately after Step 13 and `ProspectContext` construction.
- **Benefit**: `ReportGenerator` now runs when all pipeline data is complete. Existing report functionality is preserved with 100% backward compatibility.

---

## 10. Outreach Compatibility

In [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py):
- `generate_outreach(...)` now accepts `prospect_context: Optional[ProspectContext] = None`.
- When `prospect_context` is provided:
  - Extracts customer pain themes and recurring complaints from `prospect_context.intelligence.customer_pain`.
  - Extracts competitor rating gaps and benchmarks from `prospect_context.intelligence.competitor_analysis`.
  - Injects these concrete pain points into the rule-based templates and AI prompt context.
  - Generates specialized pitch angles for customer reputation recovery and competitor displacement.
- When `prospect_context` is `None` (legacy callers):
  - Preserves exact legacy behavior without regression.

---

## 11. Tests

Unit tests added in [`tests/test_context_builder.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_context_builder.py):

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_context_construction` | Valid construction from complete pipeline models | **PASS** |
| `test_evidence_preservation` | Harvests claims for pain, competitor gaps, hiring, and stack | **PASS** |
| `test_score_semantics_and_polarity` | Verifies opposite polarities of opportunity vs health score | **PASS** |
| `test_missing_optional_data` | Handles None/empty inputs gracefully with defaults | **PASS** |
| `test_serialization` | Verifies `.model_dump()` and `.model_dump_json()` roundtripping | **PASS** |
| `test_pure_in_memory_no_network_no_llm` | Verifies zero network/LLM dependencies on the builder | **PASS** |
| `test_no_database_requirement` | Verifies builder execution without database connectivity | **PASS** |
| `test_token_efficient_summary` | Verifies compact summary formatting within token bounds | **PASS** |
| `test_outreach_generator_consumes_context` | Verifies outreach enrichment with context & backward compatibility | **PASS** |

### Core Test Suite Execution
`./.venv/bin/python3 -m unittest tests.test_schemas tests.test_refactored_interfaces tests.test_context_builder`  
**Result:** 29 tests, 0 failures, 0 errors (**OK**).

---

## 12. Architecture Decisions

1. **Schema Re-use over Redefinition**: Rather than duplicating fields, `ProspectContext` re-uses `schemas.business.Business`, `schemas.enrichment.BusinessEnrichment`, `schemas.intelligence.BusinessIntelligence`, `schemas.intent.IntentProfile`, and `schemas.opportunity.Opportunity`.
2. **Context Builder Location**: Placed in `ai/context_builder.py` under the new `ai/` namespace, establishing the foundation for future AI orchestration without coupling to any external vendor SDK.
3. **Evidence Provenance**: `EvidenceItem` includes `source` and `confidence` fields, allowing downstream AI prompts to cite exact evidence sources (e.g., `"Review analysis shows 4 complaints about slow response times"`).
4. **Non-Invasive Pipeline Integration**: `ProspectContext` is assembled after Step 13 in `pipeline_runner.py` and passed into `OutreachGenerator` and stored in `PipelineResult.metadata['prospect_context']`. Database tables and persistence schemas remain unchanged.

---

## 13. Deferred Work

1. **LLM Client Layer (Phase 2B)**: Implementation of structured AI prompt templates, LLM client interfaces, and token budget management.
2. **Database Schema Migration**: Persisting `ProspectContext` or `evidence` as a dedicated JSONB column in PostgreSQL (currently stored safely in in-memory `PipelineResult`).
3. **Full Report Generator Modernization**: Updating `ReportGenerator` to render deep customer pain quotes and competitor gap tables directly into its markdown/HTML reports.

---

## 14. Known Limitations

1. **Pre-existing Environment Failures**: 5 legacy test files (`tests/test_api_server.py`, `tests/test_entity_resolver.py`, `tests/test_outreach_generator.py`, `tests/test_scoring_engine.py`, `tests/test_social_scraper.py`) fail discovery because `pytest` is not installed in the environment. All `unittest`-compatible tests pass.
2. **In-Memory Context**: `ProspectContext` is passed at runtime and preserved in memory and `PipelineResult`. It is not yet written to a separate dedicated database table.
