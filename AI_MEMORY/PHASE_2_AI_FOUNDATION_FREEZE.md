# Phase 2 — AI Foundation Architecture Freeze

**Date:** 2026-10-08  
**Scope:** Architectural Baseline, Responsibility Boundaries, Data Contracts, and Operational Guarantees for the AI Intelligence & Evaluation Layer  
**Status:** AI FOUNDATION ARCHITECTURE FROZEN  

---

## 1. Final Architecture

The complete AI intelligence layer follows a unidirectional, strictly decoupled pipeline:

```text
Deterministic Domain Systems (Discovery, Scraping, Enrichment, Intelligence, Intent, Scoring)
                                      ↓
                         ProspectContextBuilder (ai/context_builder.py)
                                      ↓
                           ProspectContext (schemas/context.py)
                                      ↓
                       OpportunityReasoner (ai/opportunity_reasoner.py)
                                      ↓
                         OpportunityAnalysis (schemas/ai.py)
                                      ↓
                        OutreachReasoner (ai/outreach_reasoner.py)
                                      ↓
                          OutreachStrategy (schemas/ai.py)
                                      ↓
                       OutreachGenerator (analyzer/outreach_generator.py)
                                      ↓
                            OutreachDraft (schemas/outreach.py)
                                      ↓
                         Evaluation (evaluation/evaluators.py)
                                      ↓
                          EvaluationResult (evaluation/models.py)
```

---

## 2. Responsibility Matrix

Each component has a clear, non-overlapping scope of ownership:

| Component | Module | Owns | Explicitly Does NOT Own |
| :--- | :--- | :--- | :--- |
| **`ProspectContextBuilder`** | `ai/context_builder.py` | Ingesting domain outputs, extracting atomic `EvidenceItem` records with provenance, normalizing metric polarities, synthesizing summary bullets. | LLM calls, HTTP requests, SQL queries, Playwright scraping, commercial diagnosis. |
| **`LLMClient`** | `ai/client.py` | Provider-agnostic API communication (Gemini, OpenAI), schema injection, markdown code fence stripping, JSON parsing, Pydantic validation, typed exceptions. | Business reasoning, prompt formulation, prospect data manipulation, persistence. |
| **`OpportunityReasoner`** | `ai/opportunity_reasoner.py` | Business opportunity interpretation, executive diagnostic synthesis, pain category classification, commercial service recommendations, deterministic fallback. | Prompt formatting for emails/messages, database access, web scraping, multi-channel copy generation. |
| **`OutreachReasoner`** | `ai/outreach_reasoner.py` | Consultative positioning strategy, angle determination, decision-maker persona mapping, objection handling, evidence citation mapping, fallback strategy. | Email rendering templates, database inserts, raw LLM HTTP requests, scraper execution. |
| **`OutreachGenerator`** | `analyzer/outreach_generator.py` | Rendering finalized copy drafts (`cold_email_draft`, `whatsapp_draft`), consuming `OutreachStrategy` and `ProspectContext`, maintaining legacy caller compatibility. | Opportunity analysis synthesis, outreach strategy formulation, direct provider HTTP calls. |
| **`EvaluationRunner`** | `evaluation/evaluators.py` | Deterministic verification of structural validity, evidence grounding, polarity adherence, cross-component consistency, and conservative heuristic hallucination detection. | Modifying pipeline outputs, calling live LLM models, database queries, network calls. |

---

## 3. Data Contracts

All data flowing through the AI foundation is validated using typed Pydantic v2 models:

### 1. Unified Context Contract
- **[`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py)**: Unified container holding `Business`, `ScoreCard`, `BusinessEnrichment`, `BusinessIntelligence`, `IntentProfile`, `Opportunity`, `OpportunityAnalysis`, `OutreachStrategy`, `evidence: List[EvidenceItem]`, and `summary_bullets: List[str]`.
- **[`EvidenceItem`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py)**: Atomic factual claim with `category`, `claim`, `source`, `value`, and `confidence`.
- **[`ScoreCard`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py)**: Explicit polarity resolution between `sales_opportunity_score` (higher = worse presence / bigger sales pitch) and `digital_health_rating` (higher = healthier presence).

### 2. AI Reasoning Contracts
- **[`OpportunityAnalysis`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py)**: Holds `executive_diagnosis`, `primary_pain_category`, `recommendations: List[CommercialRecommendation]`, `strategic_pitch_angle`, `cited_evidence_points`, `confidence_score`, `reasoning_mode`, and `evidence_sufficiency`.
- **[`OutreachStrategy`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py)**: Holds `positioning_summary`, `primary_angle`, `target_decision_maker_type`, `strongest_pain_point`, `value_proposition`, `recommended_service`, `cold_email_subject`, `cold_email_body`, `whatsapp_message`, `call_opening_hook`, `anticipated_objection`, `objection_counter`, `cited_evidence_points`, `confidence_score`, `reasoning_mode`, and `evidence_sufficiency`.
- **[`OutreachDraftResponse`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py)**: Minimal contract for structured copy drafting extraction.

### 3. Evaluation Contracts
- **[`EvaluationResult`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/models.py)**: Standardized report with bounded scores (`overall_score`, `grounding_score`, `relevance_score`, `consistency_score`, `evidence_coverage_score`), `hallucination_flags`, `issues`, and `passed`.
- **[`ComponentEvaluation`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/models.py)**: Granular breakdown for Opportunity Analysis or Outreach Strategy.
- **[`HeuristicFlag`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/models.py)**: Explainable flag with `status` (`confirmed_supported` or `potentially_unsupported`), `flag_type`, `claim`, and `reason`.

---

## 4. LLM Boundary

The LLM integration is completely provider-independent:
1. **Configuration**: Managed via [`LLMConfig`](file:///Users/ashik/Bens%20Repository/scrapper/ai/config.py) (`from_env()`) with automatic provider detection (`gemini`, `openai`, or `none`). Zero hardcoded API keys.
2. **Provider Isolation**: `OpportunityReasoner`, `OutreachReasoner`, and `OutreachGenerator` communicate exclusively via `LLMClient`. They have zero awareness of whether Google Gemini or OpenAI is serving the request.
3. **Structured Validation**: `LLMClient.generate_structured()` automatically appends JSON schemas, validates responses with Pydantic v2, and provides safe execution via `generate_structured_safe()`.
4. **Typed Exceptions**:
   - `LLMUnavailableError`: Provider or key missing.
   - `LLMProviderError`: Upstream HTTP error or timeout.
   - `LLMResponseParsingError`: Response text not valid JSON.
   - `LLMValidationError`: Response violates Pydantic schema constraints.

---

## 5. Failure & Fallback Behavior

The AI foundation guarantees deterministic, crash-proof behavior across all failure scenarios:

| Failure Mode | Reasoner Behavior | Output Guarantee |
| :--- | :--- | :--- |
| **No Provider / No API Key** | `is_available == False` detected upfront. No HTTP requests attempted. | Returns deterministic fallback analysis/strategy derived from `ScoreCard` and verified findings. `reasoning_mode="deterministic_fallback"`. |
| **Provider HTTP 500 / Network Outage** | `LLMProviderError` caught gracefully. Warning logged. | Seamless fallback to deterministic rule-based analysis/strategy. Zero unhandled crashes. |
| **Timeout (default 15s)** | `requests.exceptions.Timeout` caught by `LLMClient`. Wrapped in `LLMProviderError`. | Falls back immediately to deterministic output. |
| **Malformed JSON Response** | `LLMResponseParsingError` caught by Reasoner. | Falls back immediately to deterministic output. |
| **Schema Validation Failure** | `LLMValidationError` caught by Reasoner. | Falls back immediately to deterministic output. |
| **Insufficient Prospect Evidence** | `_is_evidence_sufficient()` returns `False` before prompting. | Produces cautious, exploratory baseline without calling LLMs. `evidence_sufficiency="insufficient"`. Prevents fabrication. |

---

## 6. Evaluation Boundary

The evaluation layer in [`evaluation/`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/) provides deterministic, explainable quality checks:

### What the Evaluation Layer CAN Prove:
- **Structural Integrity**: Validates that all required fields exist, string lengths are adequate, scores are bounded in `[0.0, 1.0]`, and enums are legal.
- **Evidence Provenance & Grounding**: Confirms whether cited evidence points correspond to verified findings, complaints, or audit signals in `ProspectContext`.
- **ScoreCard Polarity Consistency**: Detects contradictions where an AI praises a prospect having a severe deficiency (`sales_opportunity_score >= 70`) or diagnoses disaster for a healthy prospect (`digital_health_rating >= 85`).
- **Cross-Component Alignment**: Verifies that the outreach pain point and recommended service match the opportunity diagnosis recommendations.
- **Obvious Contradictions**: Detects claims of "missing website" when `website` is active, or "poor rating" when rating is >= 4.2.

### What the Evaluation Layer CANNOT Prove:
- Does NOT prove real-world commercial conversion rates.
- Does NOT replace human copy review for subjective brand voice or stylistic nuances.
- Does NOT act as an LLM judge; uses heuristic token matching and explicit constraint checking.
- Flags are explicitly tagged as `potentially_unsupported` heuristic indicators rather than absolute ground truth.

---

## 7. Deferred Architecture (Post-Phase 2)

The following capabilities are deliberately out of scope for the AI foundation freeze and deferred to subsequent phases:
- **Agent Orchestration**: Autonomous planning, multi-step agent loops, LangGraph, tool-calling agents.
- **Application Capability Tools**: Tool execution layers for search, CRM sync, or external dispatch.
- **Retrieval Augmented Generation (RAG)**: Vector databases (pgvector, Chroma, Pinecone), semantic embedding indexing.
- **Asynchronous Execution & Workers**: Celery, Redis queue, background job processors.
- **Microservices & Infrastructure**: Kubernetes, Docker Compose production clusters, microservice splits.
- **LLM-as-a-Judge**: Multi-agent evaluation loops requiring runtime LLM calls.

---

## 8. Known Technical Debt

1. **Synchronous Pipeline Processing**: `pipeline_runner.py` executes businesses sequentially in a blocking loop; async concurrency is deferred.
2. **Legacy Pytest Dependency in 5 Tests**: 5 historical tests (`test_api_server`, `test_entity_resolver`, `test_outreach_generator`, `test_scoring_engine`, `test_social_scraper`) import `pytest` which is absent from the minimal environment. The core unittest suite runs cleanly (75 tests).
3. **Token Overlap Vocabulary Boundary**: Evaluator grounding relies on token overlap with stopword removal. Heavy synonyms or paraphrased idioms receive lower grounding scores unless verified terms are retained.

---

## 9. Verification Baseline

- **Test Suite**: 75 passing unit tests across 7 test modules.
- **Execution Time**: ~0.16 seconds.
- **Module Imports**: `evaluation`, `ai`, `schemas`, `pipeline_runner`, `analyzer` import cleanly with 0 side-effects.

---

AI FOUNDATION ARCHITECTURE FROZEN
