# Phase 3B — Application Capability Layer

**Date:** 2026-10-08  
**Scope:** Implementation of Typed Application Capability Tool Layer, Pydantic Contracts, Safety Policy Matrix, and Capability Registry  
**Status:** COMPLETE  

---

## 1. Executive Summary

Phase 3B implements the **Application Capability Tool Layer** (`application/`), creating a typed, boundary-enforced interface between future Agent orchestration and the existing canonical domain modules:

```text
Future Agent (Phase 3C+)
        ↓
CapabilityRegistry (application/capabilities/registry.py)
        ↓
Application Capability Tools (application/capabilities/*.py)
        ↓
Canonical Domain Modules (Enrichment, Intelligence, Scoring, AI Reasoners, Evaluation)
        ↓
Infrastructure (Playwright, Sockets, PostgreSQL, External LLM APIs)
```

The capability layer completely shields the Agent from low-level infrastructure concerns:
- Zero raw database connections or SQL queries are exposed to the Agent.
- Zero Playwright browser objects or scraper internals are leaked.
- Zero raw HTTP clients or socket descriptors are exposed.
- All 10 tools have typed Pydantic v2 input and output contracts.
- Safety policies (`READ` vs `WRITE`) are explicitly bound to every capability.

---

## 2. Directory Structure

```text
application/
├── __init__.py                  # Public exports: CapabilityRegistry, CapabilityDescriptor, PolicyClass, CapabilityResult
├── policies/
│   ├── __init__.py              # Policy exports
│   └── classification.py        # PolicyClass enum (READ, WRITE, EXTERNAL_ACTION)
├── contracts/
│   ├── __init__.py              # Contract exports
│   ├── base.py                  # CapabilityResult[T] generic result envelope
│   ├── inputs.py                # Pydantic v2 input schemas for all 10 capabilities
│   └── outputs.py               # Dedicated output schemas (DiscoverProspectsOutput, AuditWebsiteTechOutput, EnrichLeadershipSocialOutput)
└── capabilities/
    ├── __init__.py              # Capability tool exports
    ├── discovery.py             # DiscoverProspectsCapability
    ├── website_audit.py         # AuditWebsiteTechCapability
    ├── enrichment.py            # EnrichLeadershipSocialCapability
    ├── intelligence.py          # MineBusinessIntelligenceCapability
    ├── scoring.py               # CalculateHealthAndScoresCapability
    ├── context.py               # AssembleProspectContextCapability
    ├── opportunity.py           # SynthesizeOpportunityAnalysisCapability
    ├── outreach.py              # FormulateOutreachStrategyCapability & RenderOutreachDraftsCapability
    ├── evaluation.py            # EvaluateAIReasoningCapability
    └── registry.py              # CapabilityRegistry & CapabilityDescriptor
```

---

## 3. Capability Implementations & Safety Matrix

| Capability Name | Policy Class | Purpose | Delegated Canonical Module | Input Contract | Output Contract |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`discover_prospects`** | `READ` | Discovers candidate businesses via search query and location. | `GoogleMapsScraper`, `JustDialScraper`, `IndiaMartScraper` | `DiscoverProspectsInput` | `DiscoverProspectsOutput` |
| **`audit_website_tech`** | `READ` | Audits website DOM, mobile friendliness, DNS, SSL, and CMS tech stack. | `WebsiteAnalyzer`, `TechSignalAnalyzer` | `AuditWebsiteTechInput` | `AuditWebsiteTechOutput` |
| **`enrich_leadership_social`** | `READ` | Identifies decision-maker names, roles, and scores social presence. | `DecisionMakerFinder`, `SocialAnalyzer` | `EnrichLeadershipSocialInput` | `EnrichLeadershipSocialOutput` |
| **`mine_business_intelligence`** | `READ` | Extracts customer complaints, conversion friction, and competitor gap. | `ReviewMiner`, `CustomerPainExtractor`, `ConversionAnalyzer` | `MineBusinessIntelligenceInput` | `BusinessIntelligence` |
| **`calculate_health_and_scores`** | `READ` | Calculates normalized polarities, opportunity score, and digital health rating. | `ScoringEngine`, `BusinessHealthScore` | `CalculateHealthAndScoresInput` | `ScoreCard` |
| **`assemble_prospect_context`** | `READ` | Compiles verified facts, scores, complaints, and evidence into context. | `ProspectContextBuilder` | `AssembleProspectContextInput` | `ProspectContext` |
| **`synthesize_opportunity_analysis`**| `READ` | Synthesizes AI executive commercial diagnosis and service recommendations. | `OpportunityReasoner` | `SynthesizeOpportunityInput` | `OpportunityAnalysis` |
| **`formulate_outreach_strategy`** | `READ` | Devises consultative pitch angle, objection handling, and copy strategy. | `OutreachReasoner` | `FormulateOutreachStrategyInput` | `OutreachStrategy` |
| **`evaluate_ai_reasoning`** | `READ` | Evaluates grounding fidelity, polarity adherence, and hallucinations. | `EvaluationRunner` | `EvaluateAIReasoningInput` | `EvaluationResult` |
| **`render_outreach_drafts`** | `WRITE` | Renders finalized cold email & WhatsApp copy, staging draft in database. | `OutreachGenerator`, `ScraperRepository` | `RenderOutreachDraftsInput` | `OutreachDraft` |

---

## 4. Capability Result Envelope Contract

Defined in [`application/contracts/base.py`](file:///Users/ashik/Bens%20Repository/scrapper/application/contracts/base.py):

```python
class CapabilityResult(BaseModel, Generic[T]):
    success: bool
    capability_name: str
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

Each execution captures:
- `duration_ms`: Execution latency in milliseconds.
- `policy_class`: Safety policy category (`READ` or `WRITE`).
- `data`: Strongly-typed payload matching the capability's output schema.
- `error`: Clear human-readable error description upon parameter validation or domain failure.

---

## 5. Capability Registry

Defined in [`application/capabilities/registry.py`](file:///Users/ashik/Bens%20Repository/scrapper/application/capabilities/registry.py):

- **Discovery Boundary**: Provides `get(name)` and `list_capabilities()` exposing `CapabilityDescriptor` metadata (`name`, `description`, `policy_class`, `input_schema`, `output_schema`) for Agent introspection.
- **Dispatch Boundary**: Provides `execute(name, params)` which:
  1. Validates incoming parameters against the registered `input_schema`.
  2. Measures execution duration.
  3. Executes the underlying capability handler.
  4. Returns a typed `CapabilityResult[T]`.
- **Pre-Wired Registry**: `CapabilityRegistry.default_registry()` instantiates and registers all 10 canonical capabilities.

---

## 6. Testing and Verification

A comprehensive unit test suite in [`tests/test_capabilities.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_capabilities.py) validates the entire capability layer (13 tests):
- Registry discovery and catalog completeness (all 10 capabilities registered).
- Policy classifications verified (9 `READ`, 1 `WRITE`).
- Execution of `assemble_prospect_context` producing valid `ProspectContext`.
- Deterministic calculation of `calculate_health_and_scores` without LLM calls.
- AI reasoning delegation in `synthesize_opportunity_analysis` and `formulate_outreach_strategy`.
- Pure in-memory evaluation execution in `evaluate_ai_reasoning`.
- Staged draft generation in `render_outreach_drafts`.
- Mocked discovery and website audit capability isolation.
- Parameter validation rejection and unregistered capability handling.

### Test Results:
```text
Ran 88 tests in 0.169s

OK (100% pass rate)
- tests.test_schemas: 8 tests PASS
- tests.test_refactored_interfaces: 12 tests PASS
- tests.test_context_builder: 9 tests PASS
- tests.test_llm_client: 17 tests PASS
- tests.test_opportunity_reasoner: 9 tests PASS
- tests.test_outreach_reasoner: 9 tests PASS
- tests.test_evaluation: 11 tests PASS
- tests.test_capabilities: 13 tests PASS
```

Import smoke test:
```text
python3 -c "import application, evaluation, ai, schemas, pipeline_runner, analyzer; print('All layers import cleanly!')"
All layers import cleanly!
```
