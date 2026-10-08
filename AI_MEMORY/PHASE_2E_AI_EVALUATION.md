# Phase 2E — AI Evaluation Foundation

**Date:** 2026-10-08  
**Scope:** AI Reasoning Quality Evaluation Architecture, Deterministic Evaluators, Heuristic Hallucination Detection, and Synthetic Benchmarks  
**Status:** COMPLETE  

---

## 1. Executive Summary

Phase 2E introduces a production-oriented, deterministic evaluation layer for the AI reasoning pipeline developed across Phase 2B–2D:

```text
ProspectContext
      ↓
OpportunityReasoner  → [OpportunityEvaluator]
      ↓                        ↓
OpportunityAnalysis            ↓
      ↓                        ↓
OutreachReasoner      → [OutreachEvaluator]
      ↓                        ↓
OutreachStrategy               ↓
      ↓                        ↓
OutreachGenerator     → [EvaluationRunner] → EvaluationResult
```

The evaluation infrastructure operates purely in-memory, requiring **zero live LLM-as-a-judge calls**, **zero external SaaS/LangSmith dependencies**, **zero database queries**, and **zero network requests**. It computes explainable metrics bounded between `0.0` and `1.0`, verifies structural validity, checks evidence grounding against verified prospect findings, enforces scorecard polarity constraints, cross-checks opportunity-to-outreach consistency, and flags heuristic hallucinations with status `confirmed_supported` or `potentially_unsupported`.

---

## 2. Evaluation Architecture

The evaluation subsystem resides in a dedicated package:
```text
evaluation/
├── __init__.py          # Exports EvaluationResult, EvaluationRunner, evaluators, models
├── models.py            # Pydantic v2 evaluation contracts & metrics
├── evaluators.py        # OpportunityEvaluator, OutreachEvaluator, EvaluationRunner
└── datasets/
    ├── __init__.py      # Dataset exports
    └── fixtures.py      # 6 standard deterministic synthetic test fixtures
```

### Architectural Principles:
1. **Decoupled from Core Pipeline**: The evaluators inspect `ProspectContext`, `OpportunityAnalysis`, and `OutreachStrategy` without modifying the core reasoners or generators.
2. **Deterministic & Fast**: Executes in sub-millisecond timeframes using token-overlap matching and heuristic rules.
3. **Strict Bounds**: All scores (`overall_score`, `grounding_score`, `relevance_score`, `consistency_score`, `evidence_coverage_score`) are clamped to `[0.0, 1.0]`.
4. **Conservative Hallucination Flagging**: Labels potential factual issues as explainable heuristic flags, distinguishing between `confirmed_supported` and `potentially_unsupported` rather than asserting false certainty.

---

## 3. Evaluation Contracts (Pydantic v2 Schemas)

Defined in [`evaluation/models.py`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/models.py):

### `EvaluationResult` (Canonical Top-Level Contract)
- `overall_score: float` (0.0 to 1.0)
- `grounding_score: float` (0.0 to 1.0)
- `relevance_score: float` (0.0 to 1.0)
- `consistency_score: float` (0.0 to 1.0)
- `evidence_coverage_score: float` (0.0 to 1.0)
- `hallucination_flags: List[str]` (human-readable warnings)
- `issues: List[str]` (defects and mismatches)
- `passed: bool` (production deployment threshold)
- `structural_validity: bool`
- `opportunity_evaluation: Optional[ComponentEvaluation]`
- `outreach_evaluation: Optional[ComponentEvaluation]`
- `heuristic_details: List[HeuristicFlag]`

### `ComponentEvaluation` (Per-Model Breakdown)
- `component_name: str` ('opportunity_analysis' or 'outreach_strategy')
- `score: float` (0.0 to 1.0)
- `structural_validity: bool`
- `grounding_score: float`
- `relevance_score: float`
- `consistency_score: float`
- `evidence_coverage_score: float`
- `supported_claims: List[str]`
- `unsupported_claims: List[str]`
- `issues: List[str]`
- `passed: bool`

### `HeuristicFlag` (Explainable Indicator)
- `flag_type: str` (e.g. `contradiction_website_exists`, `unsupported_cited_evidence`, `polarity_contradiction_praised_deficiency`)
- `status: str` (`confirmed_supported` or `potentially_unsupported`)
- `claim: str` (the specific claim or text evaluated)
- `reason: str` (clear explanation citing context facts)
- `severity: str` (`info`, `warning`, or `error`)

### `BatchEvaluationSummary`
- Aggregates `total_evaluated`, `passed_count`, `failed_count`, averages for all metrics, and total hallucination flags across benchmark suites.

---

## 4. Deterministic Evaluators Implemented

Defined in [`evaluation/evaluators.py`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/evaluators.py):

### 1. `OpportunityEvaluator`
- **Structural Validity**: Checks required fields, string lengths, valid pain categories (`conversion`, `reputation`, `technical`, `visibility`, `infrastructure`, `growth`, `general`), confidence bounds `[0.0, 1.0]`, valid modes, and recommendation schema integrity.
- **Evidence Grounding**: Evaluates `cited_evidence_points` against verified findings corpus (complaints, bottlenecks, conversion flaws, detected pain points) while filtering out common stop words and business identity terms.
- **Evidence Coverage**: Computes ratio of supported findings cited against available context findings.
- **Polarity Consistency**: 
  - Prevents glowing praise (e.g. `exceptional online presence`) when `sales_opportunity_score >= 70`.
  - Prevents catastrophic disaster claims when `digital_health_rating >= 85`.
  - Validates `primary_pain_category` against ScoreCard penalty metrics.
- **Commercial Relevance**: Evaluates recommendation completeness, tier validity, and clear business impact.

### 2. `OutreachEvaluator`
- **Structural Validity**: Checks subject line lengths (<= 150 chars), copy completeness, and valid modes.
- **Evidence Grounding**: Verifies cited copy claims against context evidence findings.
- **Cross-Component Consistency**:
  - Checks alignment between `strongest_pain_point` and `OpportunityAnalysis.primary_pain_category` / recommendations.
  - Checks whether `recommended_service` matches one of the recommended services from `OpportunityAnalysis`.
- **Direct Contradiction Checks**:
  - Catches copy claiming "missing website" when `business.website` is active.
  - Catches copy claiming "poor rating" when `business.google_rating >= 4.2`.
- **Commercial Relevance**: Checks copy length discipline (subject words <= 15, email words <= 200) and presence of a concrete value proposition.

### 3. `EvaluationRunner`
- Runs Opportunity and Outreach evaluators jointly or individually.
- Computes weighted overall score:
  $$\text{base} = 0.30 \times \text{grounding} + 0.30 \times \text{consistency} + 0.20 \times \text{relevance} + 0.20 \times \text{coverage}$$
  $$\text{overall} = \max(0.0, \min(1.0, \text{base} - 0.25 \times N_{\text{errors}} - 0.10 \times N_{\text{warnings}}))$$
- Determines `passed`: requires `overall_score >= 0.70`, 0 severe error flags, and `structural_validity == True`.
- Provides batch execution via `evaluate_batch()`.

---

## 5. Heuristic Hallucination Detector

The heuristic detector operates conservatively without making false claims of infallibility. It classifies claims into:
- `confirmed_supported`: Token overlap >= 35% or exact substring match against verified context findings corpus.
- `potentially_unsupported`: Token overlap < 35% with context findings corpus.

### Specific Contradiction Checks:
| Flag Type | Trigger Condition | Severity |
| :--- | :--- | :--- |
| `contradiction_website_exists` | Output claims "no website" / "missing website" while `business.website` is non-empty. | `error` |
| `contradiction_rating_high` | Output claims "bad rating" / "low rating" / "poor reviews" while `business.google_rating >= 4.2`. | `error` |
| `polarity_contradiction_praised_deficiency` | Output praises "flawless digital presence" while `scores.sales_opportunity_score >= 70`. | `error` |
| `polarity_contradiction_catastrophic_healthy` | Output claims "catastrophic failure" while `scores.digital_health_rating >= 85`. | `error` |
| `unsupported_cited_evidence` | Cited evidence point has 0% or low token overlap with verified context findings. | `warning` |
| `unsupported_outreach_claim` | Outreach copy cites technical or reputation defects absent from evidence. | `warning` |

---

## 6. Synthetic Evaluation Datasets

Defined in [`evaluation/datasets/fixtures.py`](file:///Users/ashik/Bens%20Repository/scrapper/evaluation/datasets/fixtures.py):

1. **`strong_evidence_good_reasoning`**: Rich evidence (iOS booking bug, missed callbacks), well-grounded AI opportunity diagnosis, consistent consultative outreach.  
   *Result:* Score = `0.900`, `passed=True`, 0 flags, 0 issues.
2. **`strong_evidence_poor_reasoning`**: Rich deficiency evidence, but AI output praises digital presence (polarity failure).  
   *Result:* Score = `0.295`, `passed=False`, polarity flag raised.
3. **`unsupported_hallucination`**: Top-rated prospect (4.9 stars, active website), but AI fabricates "no website found" and "missing SSL".  
   *Result:* Score = `0.000`, `passed=False`, 5 severe contradiction flags.
4. **`opportunity_consistent_outreach_inconsistent`**: Good opportunity diagnosis (conversion focus), but outreach diverges to pitch unrelated MySQL database vulnerabilities.  
   *Result:* Score = `0.527`, `passed=False`, consistency mismatch flagged.
5. **`insufficient_evidence`**: Prospect with 0 reviews and 0 audits. AI provides cautious exploratory outreach.  
   *Result:* Score = `1.000`, `passed=True`, 0 hallucinations.
6. **`deterministic_fallback`**: Rule-based fallback outputs generated when LLM is unavailable.  
   *Result:* Score = `0.867`, `passed=True`, 0 hallucinations.

---

## 7. Verification and Test Results

The test suite in [`tests/test_evaluation.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_evaluation.py) includes 11 comprehensive tests:
- Structural validity passes for valid models
- Structural validity fails for malformed models
- Evidence grounding detects supported claims
- Evidence grounding detects unsupported claims
- Consistency checks detect contradictory pain points and services
- Hallucination detector catches active website contradictions and high rating contradictions
- Polarity contradictions caught when praising deficient prospects
- Insufficient evidence handled cleanly without hallucinations
- Deterministic fallback handled cleanly
- All scores bounded strictly between 0.0 and 1.0 across all scenarios
- Pure in-memory execution verified (0 LLM, 0 DB, 0 network calls)

### Test Execution Summary:
```text
Ran 75 tests in 0.160s

OK (100% pass rate)
- tests.test_schemas: 8 tests PASS
- tests.test_refactored_interfaces: 12 tests PASS
- tests.test_context_builder: 9 tests PASS
- tests.test_llm_client: 17 tests PASS
- tests.test_opportunity_reasoner: 9 tests PASS
- tests.test_outreach_reasoner: 9 tests PASS
- tests.test_evaluation: 11 tests PASS
```

---

## 8. Limitations and Edge Cases

1. **Vocabulary Paraphrasing**: Since grounding uses token-overlap rather than semantic embeddings, heavily rephrased synonyms (e.g. "client discontent" for "customer complaints") may receive lower token overlap scores unless recognized by finding terms.
2. **Compound Business Names**: Token matching filters out business name tokens to avoid false positive matches on business identity.
3. **Heuristic Flags are Signals, Not Absolute Proof**: Contradiction flags are tagged as `potentially_unsupported` to prevent automated over-rejection of subtle edge cases.

---

## 9. Production Readiness Assessment

- **Stability**: Highly stable, zero side-effects on existing data structures or pipeline execution.
- **Resource Footprint**: Negligible CPU and memory overhead; executes in under 2ms per prospect.
- **Observability**: Rich breakdown provided via `ComponentEvaluation` and `HeuristicFlag` models.
- **Deployment Fit**: Ready for integration into offline evaluation runs, CI/CD regression gates, and online inference quality audits.

---

## 10. Deferred Phase 2 / Phase 3 Capabilities

- **LLM-as-a-Judge**: Deferred to offline evaluation pipelines where cost and latency are acceptable.
- **Semantic Embedding Grounding**: Deferred until vector embeddings or local lightweight embedding models are considered.
- **Automated Prompt Tuning**: Using evaluation scores to guide few-shot prompt optimization in future milestones.
