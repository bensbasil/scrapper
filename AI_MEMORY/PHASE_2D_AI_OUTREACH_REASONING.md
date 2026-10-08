# Phase 2D — AI Outreach Reasoning

**Date:** 2026-10-08  
**Scope:** AI Outreach Strategy Reasoner, Evidence-Grounded Value Propositions, Clean Separation of Reasoning vs. Writing, and Pipeline Integration  
**Status:** COMPLETE  

---

## 1. Objective

Phase 2D builds a dedicated **OutreachReasoner** that converts structured business/opportunity reasoning (`ProspectContext` + `OpportunityAnalysis`) into a high-quality, evidence-grounded outreach strategy (`OutreachStrategy`), which is then consumed by [`OutreachGenerator`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py).

The target architecture:

```text
ProspectContext
      │
      ▼
OpportunityReasoner (ai/opportunity_reasoner.py)
      │
      ▼
OpportunityAnalysis (schemas/ai.py)
      │
      ▼
OutreachReasoner (ai/outreach_reasoner.py)
      │
      ▼
LLMClient (ai/client.py)
      │
      ▼
OutreachStrategy (schemas/ai.py)
      │
      ▼
OutreachGenerator (analyzer/outreach_generator.py)
      │
      ▼
Pipeline Result & Storage
```

---

## 2. Existing Outreach Flow Audit

Prior to Phase 2D:
1. `OutreachGenerator` was burdened with dual responsibilities: both determining the high-level sales angle/positioning and formatting/drafting email and WhatsApp text.
2. In Phase 2A/2B, `OutreachGenerator` was modified to accept `prospect_context` and communicate through `LLMClient`, but it lacked access to the rich commercial diagnosis synthesized by `OpportunityReasoner` (e.g. executive diagnosis, commercial recommendations, pricing tiers).
3. `OutreachStrategy` existed in `schemas/ai.py`, but was not yet produced by a dedicated reasoner or integrated into the pipeline.

---

## 3. OutreachReasoner Architecture & Boundary

Implemented in [`ai/outreach_reasoner.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/outreach_reasoner.py):
- **Pure In-Memory Service:** Operates exclusively on typed [`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py) and [`OpportunityAnalysis`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py).
- **Zero Infrastructure Coupling:** Never executes SQL, connects to PostgreSQL, launches Playwright, or makes raw HTTP socket requests.
- **Provider-Independent:** Communicates with LLMs exclusively via [`LLMClient`](file:///Users/ashik/Bens%20Repository/scrapper/ai/client.py).
- **Clear Responsibility Separation:**
  - `OpportunityReasoner`: Decides business diagnosis, revenue bottlenecks, and service recommendations.
  - `OutreachReasoner`: Decides target persona, strongest pain point to lead with, value proposition, pitch angle, objections, and messaging copy.
  - `OutreachGenerator`: Coordinates final draft packaging, audit summaries, prompt templates, and rule-based template generation.

---

## 4. Structured Inputs

`OutreachReasoner.reason(context, opportunity_analysis)` consumes:
- **ProspectContext:**
  - Business identity: name, category, location, website.
  - Contact intelligence: verified decision maker name and role.
  - ScoreCard: polarities (`sales_opportunity_score` vs `digital_health_rating`), buying intent score, outreach urgency.
  - Intelligence signals: verified review complaints, praise, competitor gap summary, trust deficiencies.
  - Verifiable evidence items list.
- **OpportunityAnalysis:**
  - `executive_diagnosis`: Core revenue leakage diagnosis.
  - `primary_pain_category`: Weakness category (`conversion`, `reputation`, `technical`, `visibility`, `infrastructure`).
  - `recommendations`: Concrete commercial services, target problems, and ROI impacts.
  - `strategic_pitch_angle`: Primary commercial sales pitch angle.
  - `cited_evidence_points`: Grounded factual claims from evidence.

---

## 5. Evidence-Grounded Outreach Contract

Defined in [`schemas/ai.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py):

```python
class OutreachStrategy(BaseModel):
    positioning_summary: str
    primary_angle: str
    target_decision_maker_type: Optional[str] = None
    strongest_pain_point: Optional[str] = None
    value_proposition: Optional[str] = None
    recommended_service: Optional[str] = None
    cold_email_subject: str
    cold_email_body: str      # Strictly under 120 words
    whatsapp_message: str     # Strictly under 50 words
    call_opening_hook: Optional[str] = None
    anticipated_objection: Optional[str] = None
    objection_counter: Optional[str] = None
    cited_evidence_points: List[str] = Field(default_factory=list)
    confidence_score: float = 1.0
    reasoning_mode: str = "ai"  # "ai" | "deterministic_fallback"
    evidence_sufficiency: str = "sufficient"  # "sufficient" | "insufficient"
```

---

## 6. Prompt Construction & Anti-Hallucination Constraints

The reasoner enforces strict copywriting and factual grounding standards:
1. **Factual Grounding:** References only verified complaints, competitor gaps, and technical defects present in the inputs.
2. **Respect Decision Maker Provenance:** If verified in context, addresses the person by name; otherwise uses generic professional greetings (`"Hi team,"`) without inventing names.
3. **Low-Friction Copy:**
   - Cold email subject: Punchy, under 8 words, free of spam triggers.
   - Cold email body: Concise, under 120 words, conversational, offering low-friction CTA (e.g. 2-minute video mockup).
   - WhatsApp copy: Punchy, under 50 words.
4. **Objection Anticipation:** Explicitly anticipates the most likely prospect objection and prepares a polite counter.

---

## 7. Deterministic Fallback Behavior

If the LLM provider is unavailable (`LLMClient.is_available == False`), the provider fails (HTTP 500, 429, timeout), or response validation fails:
- Returns `_build_deterministic_fallback(context, opp_analysis)`:
  - Sets `reasoning_mode = "deterministic_fallback"`.
  - Derives `primary_angle` and `strongest_pain_point` from `OpportunityAnalysis` or `context.opportunity`.
  - Uses verified review complaints and competitor gaps.
  - Generates grounded cold email, WhatsApp copy, and call hooks using proven consultative templates.
  - Sets `cited_evidence_points` from verified claims. Zero hallucinations.

If evidence is empty or `OpportunityAnalysis` was marked insufficient:
- `_build_insufficient_evidence_strategy(context, opp_analysis)` short-circuits with `evidence_sufficiency="insufficient"` and an exploratory audit offer without calling the LLM.

---

## 8. Pipeline Integration Point

Integrated into [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py):

```text
Step 13: Business Intelligence Analysis & Opportunity Mapping
       ↓
ProspectContext assembly (context_builder.build_context)
       ↓
Step 14: AI Opportunity Reasoning (opportunity_reasoner.reason)
       ↓
Step 14b: AI Outreach Strategy Reasoning (outreach_reasoner.reason)
       ↓
Step 5: Generate Outreach Drafts (outreach_generator.generate_outreach)
       ↓
Step 4: Generate Human-Readable Report (report_generator.generate_report)
```

- Injects `outreach_strategy` directly into `prospect_context.outreach_strategy`.
- Passes `outreach_strategy` into `OutreachGenerator.generate_outreach(...)`, which adopts the strategy's angles, positioning, and copy.
- Tracks `outreach_reasoning` stage duration in `stages_results`.

---

## 9. Tests

Created [`tests/test_outreach_reasoner.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_outreach_reasoner.py) with 9 unit tests:

| Test Case | Focus | Result |
| :--- | :--- | :--- |
| `test_prompt_construction` | Verifies prompt includes identity, decision maker, opportunity diagnosis, complaints | **PASS** |
| `test_successful_structured_reasoning` | Verifies end-to-end strategy synthesis and validation into `OutreachStrategy` | **PASS** |
| `test_insufficient_evidence_handling` | Minimal evidence triggers exploratory fallback without LLM call | **PASS** |
| `test_provider_failure_triggers_deterministic_fallback` | Upstream HTTP 500 error triggers safe deterministic fallback | **PASS** |
| `test_malformed_llm_response_triggers_deterministic_fallback` | Unparseable JSON triggers safe deterministic fallback | **PASS** |
| `test_validation_failure_triggers_deterministic_fallback` | Schema violation triggers safe deterministic fallback | **PASS** |
| `test_no_configured_provider_uses_deterministic_fallback_immediately` | Disabled LLM client executes deterministic fallback immediately | **PASS** |
| `test_pure_in_memory_no_db_or_network` | Asserts zero database, SQL, or network socket attributes on reasoner | **PASS** |
| `test_outreach_generator_consumes_outreach_strategy` | Verifies `OutreachGenerator` consumes `OutreachStrategy` cleanly | **PASS** |

### Complete Core Test Suite Execution
`./.venv/bin/python3 -m unittest tests.test_schemas tests.test_refactored_interfaces tests.test_context_builder tests.test_llm_client tests.test_opportunity_reasoner tests.test_outreach_reasoner`  
**Result:** 64 tests, 0 failures, 0 errors (**OK** in 0.158s).

---

## 10. Architectural Decisions

1. **Reasoning vs. Writing Separation:**
   `OutreachReasoner` is the strategist (deciding angles, value proposition, evidence, objections), while `OutreachGenerator` remains the draft assembler.
2. **Transparent Provenance:**
   The `reasoning_mode` field (`ai` vs `deterministic_fallback`) guarantees full observability of how outreach copy was produced.
3. **Pipeline Non-Disruption:**
   If the LLM layer fails or has no credentials, deterministic outreach continues without interruption or degradation.

---

## 11. Deferred Work

- **Phase 2E**: Multi-channel campaign sequencing (automated follow-up cadence scheduling).
- **Dedicated Strategy Database Column**: Persisting `OutreachStrategy` in a dedicated PostgreSQL JSONB column (currently held in memory and `PipelineResult`).

---

## 12. Known Limitations

- Pre-existing environment failures in 5 legacy test files due to missing `pytest` in the virtualenv (documented in Phase 1 baseline). All 64 `unittest`-compatible tests pass with 100% success rate.
