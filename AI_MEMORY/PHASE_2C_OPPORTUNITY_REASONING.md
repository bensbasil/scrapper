# Phase 2C — Opportunity Reasoning

**Date:** 2026-10-08  
**Scope:** AI Opportunity Reasoning Service, Evidence-Grounded Commercial Diagnoses, Deterministic Fallbacks, and Pipeline Integration  
**Status:** COMPLETE  

---

## 1. Objective

Phase 2C builds the first real **AI business reasoning capability** on top of the Phase 2B LLM abstraction. 

The objective is to synthesize executive commercial diagnoses, value propositions, and prioritized service recommendations from verified prospect evidence without breaking the Phase 1 architectural boundaries or replacing deterministic scoring.

The resulting architecture:

```text
Pipeline (Stages 1-13)
       ↓
ProspectContext (Unified Evidence Envelope)
       ↓
OpportunityReasoner (ai/opportunity_reasoner.py)
       ↓
LLMClient (ai/client.py)
       ↓
OpportunityAnalysis (schemas/ai.py)
       ↓
Typed Downstream Integration (Outreach & Reporting)
```

---

## 2. Existing Opportunity Flow

Prior to Phase 2C:
1. In Stage 13, `OpportunityMapper.map_opportunities()` in [`business_intelligence/opportunity_mapper.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/opportunity_mapper.py) evaluated 5 rigid heuristic rules (e.g. `web_score > 50`, `booking in issues`) to yield basic service recommendation dictionaries and a static template string.
2. `ProspectContextBuilder` collected these into `prospect_context.opportunity` alongside rich customer complaints, competitor benchmarks, tech stack, and intent signals.
3. However, no component interpreted the holistic intersection of complaints, competitor gaps, and technical deficiencies to formulate an executive commercial thesis.
4. Downstream outreach copy was restricted to template-based statements or basic keyword insertions.

---

## 3. Reasoning Boundary

[`OpportunityReasoner`](file:///Users/ashik/Bens%20Repository/scrapper/ai/opportunity_reasoner.py) strictly enforces the architectural boundary:
- **Operates Exclusively on Memory:** Ingests only typed [`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py).
- **Zero External Infrastructure Coupling:** Never executes SQL, connects to PostgreSQL, launches Playwright, or makes raw HTTP socket calls.
- **Provider-Independent:** Communicates with LLMs exclusively via [`LLMClient`](file:///Users/ashik/Bens%20Repository/scrapper/ai/client.py).
- **Interpretation, Not Measurement:** Does not compute deterministic scores or discover businesses; it interprets verified factual evidence.

---

## 4. ProspectContext Inputs

The reasoner consumes structured data points from `ProspectContext`:
- **Identity:** Business name, category, location, website URL.
- **ScoreCard (Polarities Explicitly Preserved):**
  - `sales_opportunity_score` (0–100, deficiency index: higher = greater digital weakness / sales pitch need).
  - `digital_health_rating` (0–100, health index: higher = healthier presence).
  - `buying_intent_score` (0–100) and `outreach_urgency`.
  - Component penalties: `website_weakness_penalty`, `seo_weakness_penalty`, `conversion_friction_score`, `automation_need_penalty`.
- **Enrichment:** Detected CMS, frontend frameworks, analytics tools, identified decision maker.
- **Intelligence:** Recurring review complaints, praise themes, competitor rating gap benchmark, trust deficiencies.
- **Intent Signals:** Technical hiring roles, website freshness/maintenance decay.
- **Deterministic Opportunity Baseline:** Existing service recommendations from `OpportunityMapper`.
- **Verifiable Evidence Items:** Provenance-backed list of `EvidenceItem` records.

---

## 5. Prompt Construction

Implemented in `OpportunityReasoner._build_reasoning_prompt()` and `_build_system_prompt()`:
- **Clean Markdown Structure:** Formats evidence cleanly into sections (`Score Metrics`, `Technical Stack & Contacts`, `Business Intelligence & Market Signals`, `Intent & Velocity Signals`, `Verifiable Evidence Items`).
- **No Token Bloat:** Avoids serializing huge raw JSON dumps or scraping artifacts.
- **Explicit Schema Contract:** Injects `OpportunityAnalysis.model_json_schema()` directly into generation instructions.

---

## 6. OpportunityAnalysis Contract

Defined in [`schemas/ai.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py):

```python
class CommercialRecommendation(BaseModel):
    service_name: str
    target_problem: str
    commercial_impact: str
    suggested_pricing_tier: str = "core"  # "entry" | "core" | "premium"

class OpportunityAnalysis(BaseModel):
    executive_diagnosis: str
    primary_pain_category: str  # "conversion" | "reputation" | "technical" | "visibility" | "infrastructure"
    recommendations: List[CommercialRecommendation]
    strategic_pitch_angle: str
    cited_evidence_points: List[str]
    confidence_score: float = 1.0
    reasoning_mode: str = "ai"  # "ai" | "deterministic_fallback"
    evidence_sufficiency: str = "sufficient"  # "sufficient" | "insufficient"
```

- **Backward Compatibility:** All new fields (`reasoning_mode`, `evidence_sufficiency`) have defaults, ensuring zero breaking changes across existing callers.
- **Explicit Distinction:** Callers can inspect `analysis.reasoning_mode` to distinguish between genuine AI reasoning and deterministic fallback.

---

## 7. Evidence-Grounding Rules

The system prompt enforces 4 strict rules:
1. **Strict Factual Grounding:** Never invent defects. Only cite complaints, missing assets, or technical bugs explicitly present in the provided evidence.
2. **Score Polarity Adherence:** Prohibits congratulating prospects with high `sales_opportunity_score` on their "great online presence".
3. **Distinguish Evidence from Recommendation:** Ground `cited_evidence_points` in verified claims, while framing `recommendations` as actionable commercial fixes.
4. **Insufficient Evidence Handling:** If evidence is sparse, empty, or ambiguous, sets `evidence_sufficiency="insufficient"`, `confidence_score <= 0.4`, and states in `executive_diagnosis` that discovery data is insufficient rather than guessing.

---

## 8. Deterministic Fallback

If:
- No LLM API key exists (`LLMClient.is_available == False`),
- An upstream provider fails (HTTP 429/500, network error, timeout),
- The model returns unparseable JSON or schema validation fails,

`OpportunityReasoner` returns `_build_deterministic_fallback(context)`:
- Sets `reasoning_mode = "deterministic_fallback"`.
- Determines `primary_pain_category` from the highest penalty score in `ScoreCard`.
- Maps existing `ServiceRecommendation` records from `prospect_context.opportunity` into `CommercialRecommendation` objects.
- Formulates `executive_diagnosis` from `prospect_context.opportunity.opportunity_reasoning`.
- Gathers `cited_evidence_points` from verified `EvidenceItem` claims.
- **Zero Hallucination:** Never fakes an AI response; guarantees immediate, reliable completion.

---

## 9. Integration Point

Integrated into [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) immediately after Stage 13:

```text
collect & enrich (Steps 1-10)
       ↓
intent & intelligence (Steps 11-13)
       ↓
deterministic opportunity mapping (Step 13a)
       ↓
ProspectContext assembly (context_builder.build_context)
       ↓
AI Opportunity Reasoning (opportunity_reasoner.reason)
       ↓
Outreach Generation (outreach_generator.generate_outreach)
       ↓
Human-Readable Report (report_generator.generate_report)
```

- Injected `opportunity_analysis.executive_diagnosis` into `analysis_dict["opportunity_reasoning"]` for downstream personalization.
- Attached `opportunity_analysis` directly to `prospect_context.opportunity_analysis`.
- Recorded `opportunity_reasoning` stage duration in `stages_results`.

---

## 10. Tests

Created [`tests/test_opportunity_reasoner.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_opportunity_reasoner.py) with 9 unit tests (mocked LLMClient, zero live API calls):

| Test Case | Focus | Result |
| :--- | :--- | :--- |
| `test_prompt_construction` | Verifies prompt includes identity, polarities, complaints, stack, evidence | **PASS** |
| `test_successful_structured_reasoning` | Verifies end-to-end reasoning and parsing into `OpportunityAnalysis` | **PASS** |
| `test_insufficient_evidence_handling` | Minimal context triggers `evidence_sufficiency="insufficient"` without LLM call | **PASS** |
| `test_provider_failure_triggers_deterministic_fallback` | Upstream HTTP 500 error triggers safe deterministic fallback | **PASS** |
| `test_malformed_llm_response_triggers_deterministic_fallback` | Unparseable JSON triggers safe deterministic fallback | **PASS** |
| `test_validation_failure_triggers_deterministic_fallback` | Schema violation triggers safe deterministic fallback | **PASS** |
| `test_no_configured_provider_uses_deterministic_fallback_immediately` | Disabled LLM client executes deterministic fallback immediately | **PASS** |
| `test_pure_in_memory_no_db_or_network` | Asserts zero database, SQL, or network attributes on reasoner | **PASS** |
| `test_backward_compatibility_with_opportunity_pipeline` | Maps existing `Opportunity` data into `OpportunityAnalysis` cleanly | **PASS** |

### Complete Core Test Suite Execution
`./.venv/bin/python3 -m unittest tests.test_schemas tests.test_refactored_interfaces tests.test_context_builder tests.test_llm_client tests.test_opportunity_reasoner`  
**Result:** 55 tests, 0 failures, 0 errors (**OK** in 0.207s).

---

## 11. Architecture Decisions

1. **Deterministic Baseline Preservation:**
   `OpportunityMapper` remains active as the deterministic baseline. `OpportunityReasoner` enriches and interprets it, rather than replacing it.
2. **Explicit Fallback Transparency:**
   The `reasoning_mode` field (`ai` vs `deterministic_fallback`) ensures that downstream consumers, operators, and logging clearly know the provenance of the diagnosis.
3. **Evidence Sufficiency Short-Circuit:**
   If a prospect has no verified evidence, the reasoner immediately produces an insufficient-evidence diagnosis rather than sending empty prompts to the LLM.
4. **Pipeline Non-Disruption:**
   The pipeline continues uninterrupted whether an LLM is active, degraded, or completely absent.

---

## 12. Deferred Work

- **Phase 2D**: Full `OutreachReasoner` consuming `OpportunityAnalysis` and `ProspectContext` to generate consultative multi-channel outreach strategies.
- **Dedicated Opportunity DB Persistence**: Saving `OpportunityAnalysis` to a dedicated PostgreSQL JSONB column (currently held in memory and `PipelineResult`).

---

## 13. Known Limitations

- Pre-existing environment failures in 5 legacy test files due to missing `pytest` in the virtualenv (documented in Phase 1 baseline). All `unittest`-compatible tests (55 tests) pass with 100% success rate.
