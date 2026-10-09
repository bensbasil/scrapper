# Phase 4D — End-to-End Agent Workflow & Evaluation Gate

**Date:** 2026-10-09  
**Scope:** Phase 4D Integration Verification, Execution Paths, Evaluation Gate Hardening & State Integrity  
**Status:** COMPLETE  

---

## 1. Executive Summary

Phase 4D verifies and hardens the complete agent workflow across Phases 2 through 4C, ensuring that **discovery**, **qualification**, **selection**, **evidence acquisition**, **canonical prospect context assembly**, **opportunity reasoning**, **outreach strategy synthesis**, **deterministic evaluation**, and **draft rendering** operate as a unified, coherent system.

The end-to-end architecture is governed by strict boundaries:
```text
User Request (Natural Language or Structured Params)
   ↓
Intent Interpretation & Validation (agent/intent.py / agent/llm_intent.py)
   ↓
Planning & Dependency DAG Resolution (agent/planner.py)
   ↓
Discovery & Source Ingestion (application/capabilities/discovery.py)
   ↓
Deterministic Qualification (agent/qualification.py)
   ↓
Candidate Selection & Clamping (agent/prospects.py)
   ↓
Evidence Acquisition (agent/evidence.py)
   ↓
Canonical ProspectContext Assembly (ai/context_builder.py, schemas/context.py)
   ↓
AI Opportunity Reasoning (ai/opportunity_reasoner.py, schemas/ai.py)
   ↓
AI Outreach Strategy Formulation (ai/outreach_reasoner.py, schemas/ai.py)
   ↓
Evaluation Gate (evaluation/evaluators.py, application/capabilities/evaluation.py)
   ↓ (GATED: Only when passed=True)
Outreach Draft Rendering (analyzer/outreach_generator.py, schemas/outreach.py)
   ↓
Final Response Synthesis & Audit Trace (agent/models.py, agent/telemetry.py)
```

---

## 2. Real Execution Paths Traced

### Path A: Known-Business Workflow
- **Entry Point:** `Agent.run("Research Apex Plumbing Pros and prepare consultative outreach drafts", initial_params={"business_name": "Apex Plumbing Pros", "website_url": "https://apex.com"})`
- **Intent Interpretation:** `GoalInterpreter` classifies as `IntentType.RESEARCH_AND_OUTREACH`. Flags: `requires_research=True`, `requires_opportunity_analysis=True`, `requires_outreach=True`, `requires_evaluation=True`, `requires_draft=True`, `requires_discovery=False`.
- **Planning:** `AgentPlanner.plan_from_intent` generates linear 9-step DAG:
  `step_audit` → `step_enrich` → `step_intel` → `step_score` → `step_context` → `step_opp` → `step_outreach` → `step_eval` → `step_draft`.
- **Validation:** `validate_plan` checks capability registry registration and acyclic dependencies.
- **Execution:** `AgentExecutor.run(state)` hydrates parameters sequentially, executes each capability via `CapabilityRegistry.execute`, updates state intermediate domain models (`state.prospect_context`, `state.opportunity_analysis`, `state.outreach_strategy`, `state.evaluation_result`), checks the evaluation gate, and renders `state.outreach_draft`.
- **Outcome:** `state.status == AgentStatus.COMPLETED`.

### Path B: Discovery-Only Workflow
- **Entry Point:** `Agent.run("Find dentists in Austin")`
- **Intent Interpretation:** `GoalInterpreter` extracts `industry="dentists"`, `location="Austin"`, `constraints={"limit": 10}`. Classifies as `IntentType.DISCOVER_PROSPECTS`. Flags: `requires_discovery=True`, all downstream reasoning flags `False`.
- **Planning:** Generates 1-step plan: `step_discover` (`discover_prospects`).
- **Execution:** Executes directory discovery via `CapabilityRegistry.execute("discover_prospects", ...)`.
- **State Hydration:** `_update_state_models` receives `DiscoverProspectsOutput`, populates `state.prospects = data.businesses` and `state.prospect_set = ProspectSet.from_discovery_output(data, location="Austin")`.
- **Outcome:** `state.status == AgentStatus.COMPLETED`.

### Path C: Multi-Prospect Discovery, Qualification & Batch Execution
- **Entry Point:** `Agent.run_prospect_batch(prospect_set, selection=ProspectSelection(max_prospects=5), include_outreach=True)`
- **Qualification Stage:** `DeterministicProspectQualifier.qualify_set` evaluates candidate businesses against `QualificationPolicy` (e.g. valid business name, website requirement, review volume threshold, rating bounds). Partitions candidates into `QualifiedProspectSet` (`qualified_prospects` vs `disqualified_prospects`) with full reason explainability.
- **Selection Stage:** `ProspectSelection.select` selects top candidates using deterministic ranking (e.g. `qualification_score_desc`, `opportunity_score`, `rating_asc`) bounded to `max_prospects` (clamped to safety limit `max_prospects_per_run = 15`).
- **Batch Execution Loop:** `ProspectBatchExecutor.execute_batch` processes each candidate sequentially with strict failure isolation:
  1. `EvidenceAcquisitionCoordinator.acquire_evidence`: Executes `audit_website_tech` → `enrich_leadership_social` → `mine_business_intelligence` → `calculate_health_and_scores` → `assemble_prospect_context`.
  2. `synthesize_opportunity_analysis`: Synthesizes diagnostic analysis on the canonical `ProspectContext`.
  3. `formulate_outreach_strategy`: Generates consultative positioning and service proposals.
  4. `evaluate_ai_reasoning`: Evaluates factual grounding, consistency, and hallucination flags.
  5. **Evaluation Gate Enforcement:**
     - If `evaluation_result.passed == True`: Executes `render_outreach_drafts`.
     - If `evaluation_result.passed == False`: Blocks `render_outreach_drafts`, records `ErrorCategory.EVALUATION_ERROR`, marks prospect `status = "FAILED"`, and emits a `BLOCKED` trace event for `step_draft`.
- **State Integration:** Aggregates `state.batch_result = ProspectBatchResult(...)`, populates `state.prospect_contexts: Dict[str, ProspectContext]`, and promotes top-ranked candidate to primary state models.
- **Outcome:** `state.status == AgentStatus.COMPLETED` (or `FAILED` if all candidates fail).

---

## 3. Evaluation Gate Enforcement

The execution controller—never the LLM prompt or natural language generator—enforces the evaluation policy:

| Scenario | Evaluation Gate Behavior | Outreach Draft Rendering | Prospect / State Status |
| :--- | :--- | :--- | :--- |
| **Passing Evaluation** (`passed=True`, score ≥ 0.70) | Gate opens | **PERMITTED & RENDERED** | `COMPLETED` |
| **Failed Evaluation** (`passed=False`, score < 0.70 or error flags) | Gate closes | **STRICTLY BLOCKED** | `FAILED` |
| **Hallucination Detected** (fabricated SSL, false rating defect) | Gate closes (`severity="error"`) | **STRICTLY BLOCKED** | `FAILED` |
| **Insufficient Evidence** (< 2 items, zero penalties) | Conservative diagnosis, confidence ≤ 0.40 | **BLOCKED** if ungrounded claims attempted | `FAILED` on ungrounded claims |
| **Deterministic Fallback** (`reasoning_mode="deterministic_fallback"`) | Evaluated for structural validity and polarity | **PERMITTED** only if passing threshold | `COMPLETED` |
| **Batch Single Candidate Failure** (Candidate A fails eval) | Candidate A gate closes | Candidate A blocked; Candidate B proceeds | Candidate A: `FAILED`, Candidate B: `COMPLETED` |
| **External Messaging** (`"Send WhatsApp/email"`) | Intercepted at intent layer before execution | **NEVER DISPATCHED** (0 executions) | `FAILED` (Policy violation) |

---

## 4. Confirmed Defects and Fixes Applied

During rigorous tracing and integration testing, two subtle evaluation-gate consistency defects were identified and resolved:

### Defect 1: Batch-Level Evaluation Gate Status & Telemetry Gap
- **Location:** [`agent/prospects.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/agent/prospects.py#L526-L550)
- **Root Cause:** When `_invoke_cap("evaluate_ai_reasoning")` executed, the underlying capability succeeded (returning an `EvaluationResult` with `passed=False`). `_invoke_cap` added the capability to `completed_steps` and emitted a `COMPLETED` trace event. Consequently, `failed_steps` was empty, causing `ProspectExecutionResult.status` to be marked `"COMPLETED"` even though evaluation failed and drafting was blocked.
- **Fix:** Added an explicit evaluation gate check in `_invoke_cap` and `_execute_single_prospect`. When `eval_res.passed == False`:
  1. `evaluate_ai_reasoning` is added to `failed_steps` (and excluded from `completed_steps`).
  2. Emits `CapabilityTraceEvent` with `status=StepEventStatus.FAILED` and `error_type=ErrorCategory.EVALUATION_ERROR`.
  3. Emits `CapabilityTraceEvent` for `step_draft` with `status=StepEventStatus.BLOCKED`.
  4. Prospect status becomes `"FAILED"` and `batch_result.failed_count` is incremented accurately.

### Defect 2: Single-Task AgentExecutor Execution Record & Step Status Inconsistency
- **Location:** [`agent/executor.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/agent/executor.py#L324-L332)
- **Root Cause:** When `evaluate_ai_reasoning` returned `passed=False`, `AgentExecutor._execute_step` transitioned state to `FAILED` and blocked downstream steps, but left `step.status` and `state.completed_steps[-1].status` as `COMPLETED`.
- **Fix:** Explicitly set `step.status = StepStatus.FAILED` and `state.completed_steps[-1].status = StepStatus.FAILED`, `state.completed_steps[-1].error = gate_err`.

---

## 5. Integration Verification & Actual Results

### Phase 4D Dedicated Integration Suite
Ran [`tests/test_end_to_end_workflow.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_end_to_end_workflow.py):
```text
tests/test_end_to_end_workflow.py .................                      [100%]
============================== 17 passed in 0.17s ==============================
```

**17 End-to-End Scenarios Tested & Verified:**
1. `test_01_known_business_workflow_succeeds_with_sufficient_evidence`: End-to-end known business research, opportunity, outreach, evaluation, and draft rendering.
2. `test_02_discovery_workflow_qualifies_and_selects_candidates_correctly`: Discovered prospects partitioned by deterministic qualification and prioritized by selection criteria.
3. `test_03_multi_prospect_workflow_preserves_prospect_isolation`: Independent contexts, opportunity analyses, and opportunity rankings across prospects.
4. `test_04_missing_website_produces_honest_partial_evidence_result`: Partial data handling without crashing or hallucinating digital defects.
5. `test_05_evidence_acquisition_failure_handled_without_corrupting_other_prospects`: Scraping failure on one prospect isolated from other batch candidates.
6. `test_06_failed_ai_evaluation_blocks_draft_rendering`: Execution controller strictly prevents outreach draft rendering when evaluation fails.
7. `test_07_passing_evaluation_permits_draft_rendering`: High-quality verified reasoning unlocks outreach drafting.
8. `test_08_deterministic_fallback_is_explicitly_represented_and_evaluated`: Deterministic fallback mode is explicitly tagged and structurally validated.
9. `test_09_insufficient_evidence_cannot_silently_pass_as_grounded_reasoning`: Ungrounded claims against empty evidence fail the evaluation gate.
10. `test_10_ambiguous_intent_returns_clarification_rather_than_executing_plan`: Underspecified goal safely requests structured clarification before capability execution.
11. `test_11_unsupported_external_send_requests_cannot_dispatch_messages`: Real-world messaging blocked at intent boundary.
12. `test_12_repeated_runs_maintain_independent_state_and_telemetry`: Multiple runs on the same Agent instance maintain clean state and trace boundaries.
13. `test_13_batch_size_limits_remain_enforced`: Batch limit clamping (15) and strict rejection verified.
14. `test_14_capability_and_evaluation_errors_correctly_categorized`: Verified distinct telemetry error types (`CAPABILITY_ERROR`, `EVALUATION_ERROR`, `POLICY_ERROR`).
15. `test_15_batch_level_evaluation_failure_isolation`: Candidate A evaluation failure does not block Candidate B from receiving drafts.
16. `test_16_downstream_stages_cannot_execute_before_required_upstream_results`: Prerequisite failure cascades `BLOCKED` status to dependent DAG steps.
17. `test_17_final_response_distinguishes_status_outcomes`: `AgentFinalResponse` accurately represents `COMPLETED`, `FAILED`, and `NEEDS_CLARIFICATION`.

### Complete Platform Test Suite
Ran `./.venv/bin/pytest`:
```text
tests/test_agent.py .................................................... [ 20%]
.                                                                        [ 20%]
tests/test_api_server.py ...                                             [ 21%]
tests/test_capabilities.py .............                                 [ 26%]
tests/test_context_builder.py .........                                  [ 30%]
tests/test_end_to_end_workflow.py .................                      [ 36%]
tests/test_entity_resolver.py ...                                        [ 37%]
tests/test_evaluation.py ...........                                     [ 42%]
tests/test_evidence_acquisition.py ......................                [ 50%]
tests/test_llm_client.py .................                               [ 57%]
tests/test_opportunity_reasoner.py .........                             [ 60%]
tests/test_outreach_generator.py ..                                      [ 61%]
tests/test_outreach_reasoner.py .........                                [ 65%]
tests/test_prospect_batch.py ......................                      [ 73%]
tests/test_prospect_qualification.py ......................              [ 82%]
tests/test_refactored_interfaces.py ............                         [ 86%]
tests/test_schemas.py ........                                           [ 89%]
tests/test_scoring_engine.py ...                                         [ 91%]
tests/test_social_scraper.py ...                                         [ 92%]
tests/test_telemetry.py ....................                             [100%]

============================= 258 passed in 0.42s ==============================
```
**Total Platform Test Count:** **258 passed, 0 failed across all 20 test files in 0.42s (100% pass rate).**

---

## 6. Limitations & Production Considerations

1. **LLM Non-Determinism in Production:** While deterministic unit tests enforce rigid grounding and structure, live LLM generation requires continued evaluation gate monitoring to intercept stochastic hallucinations before copies reach CRM/staging.
2. **Upstream Directory Scraping Volatility:** Live directory scrapers (Google Maps, Yellow Pages) face bot detection and rate limits. The architecture's graceful degradation to partial evidence and batch failure isolation ensures platform resilience.
3. **Evaluation Threshold Tuning:** The 0.70 composite pass threshold and zero-error policy are currently calibrated for B2B local service consulting. Complex multi-enterprise domains may require calibrated domain-specific heuristic weights in future milestones.

---

## 7. Phase Deliverables Summary

- [`agent/prospects.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/agent/prospects.py): Hardened evaluation gate failure handling, blocked step tracing, and prospect failure categorization.
- [`agent/executor.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/agent/executor.py): Synchronized step status and execution record status on evaluation gate failure.
- [`tests/test_end_to_end_workflow.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_end_to_end_workflow.py): 17 comprehensive integration tests covering end-to-end workflows and evaluation gates.
- [`AI_MEMORY/PHASE_4D_END_TO_END_WORKFLOW.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_4D_END_TO_END_WORKFLOW.md): Complete architecture, execution tracing, and defect log.
- [`AI_MEMORY/PHASE_4_EXECUTION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_4_EXECUTION.md): Updated Phase 4 milestones log with Phase 4D.
