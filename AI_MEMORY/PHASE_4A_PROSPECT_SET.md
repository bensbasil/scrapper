# Phase 4A — Prospect Set & Controlled Multi-Prospect Execution

**Status:** COMPLETE  
**Date:** 2026-10-08  
**Architecture Layer:** Agent Orchestration / Domain Batching (`agent/prospects.py`, `agent/state.py`, `agent/agent.py`)

---

## 1. Executive Summary & Objective

In Phase 3F, the single-business Agent workflow and telemetry tracing were completed. However, discovery capabilities produced lists of businesses stored directly in `AgentState.prospects`, without:
1. A first-class domain representation of a **prospect set**.
2. Controlled selection semantics to decide which candidates receive deep analysis.
3. Batch safety limits protecting against resource exhaustion from open-ended discovery.
4. Failure isolation across multiple prospects.
5. Standardized aggregation and ranking of deep analysis results.

Phase 4A introduces **Prospect Set & Controlled Multi-Prospect Execution**. It establishes:
```text
User Goal
   ↓
Discovery
   ↓
ProspectSet
   ↓
ProspectSelection (criteria + bounds)
   ↓
ProspectBatchExecutor (sequential + failure-isolated)
   ↓
Per-Prospect Analysis (Registry-Exclusive Capabilities)
   ↓
ProspectBatchResult + Opportunity Ranking
```

This is **controlled sequential execution**, NOT distributed worker infrastructure. It establishes strict domain contracts, safety boundaries, and failure isolation before concurrency is considered.

---

## 2. Architecture & Data Contracts

All new multi-prospect models are housed in [`agent/prospects.py`](file:///Users/ashik/Bens%20Repository/scrapper/agent/prospects.py).

### 2.1 `ProspectSet`
Typed domain model representing a discovered collection of candidate prospects:
- **`set_id`**: Unique string identifier (e.g. `set_5914619a`).
- **`source`**: Discovery origin (e.g. `gmaps`, `database`, `manual`).
- **`query`**: Search query used to discover the businesses.
- **`location`**: Optional geographical boundary.
- **`total_discovered`**: Total count of prospects discovered in the set.
- **`prospects`**: List of [`Business`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/business.py) instances.
- **`created_at`**: UTC ISO timestamp.

**Key Design Principle:** `ProspectSet` references the existing canonical `schemas.business.Business` model directly. It does **not** duplicate or redefine the `Business` schema.

### 2.2 `ProspectSelection`
Criteria and bounds governing which prospects from a `ProspectSet` receive downstream deep processing:
- **`max_prospects`**: Upper bound for selection (defaults to 10).
- **`minimum_score`**: Optional float threshold (e.g. minimum composite or opportunity score).
- **`required_industry`**: Optional vertical filter (case-insensitive substring match).
- **`required_location`**: Optional geographic filter.
- **`ranking`**: Optional sorting directive (`"highest_score"`, `"lowest_score"`, `"rating"`, or `None`).
- **`selection_reason`**: Explanatory justification for auditability.

**Method:** `filter_prospects(prospect_set: ProspectSet) -> List[Business]` applies filters, sorting, and bounded truncation deterministically without scraping or AI reasoning.

### 2.3 `ProspectExecutionResult`
Typed result capturing the outcome of per-prospect deep analysis:
- **`prospect_id`**: Business identifier or name.
- **`status`**: `"completed"`, `"failed"`, or `"partial"`.
- **`completed_steps`**: List of successfully executed capability names.
- **`failed_steps`**: List of failed capability names.
- **`opportunity_analysis`**: Optional typed [`OpportunityAnalysis`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py).
- **`outreach_strategy`**: Optional typed [`OutreachStrategy`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py).
- **`evaluation_result`**: Optional typed [`EvaluationResult`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py).
- **`errors`**: List of error strings encountered for this prospect.
- **`duration_ms`**: Monotonic execution duration in milliseconds.

**Signal Adapter:** `opportunity_score` property exposes the canonical overall opportunity score (from `opportunity_analysis.opportunity_score` or context scorecard) for downstream ranking.

### 2.4 `ProspectBatchResult`
Typed aggregate result representing the execution of a selection batch:
- **`batch_id`**: Unique batch identifier (e.g. `batch_7718be7a`).
- **`requested_count`**: Count requested for batch execution.
- **`selected_count`**: Count of prospects selected after filtering.
- **`completed_count`**: Count of prospects successfully completed.
- **`failed_count`**: Count of prospects that encountered execution failure.
- **`blocked_count`**: Count of prospects blocked from execution.
- **`results`**: List of [`ProspectExecutionResult`](file:///Users/ashik/Bens%20Repository/scrapper/agent/prospects.py) items.
- **`started_at`** / **`completed_at`**: UTC ISO timestamps.
- **`duration_ms`**: Aggregate execution duration in milliseconds.

**Method:** `ranked_results(criterion="opportunity_score", descending=True) -> List[ProspectExecutionResult]` sorts results based on existing opportunity signals without inventing new scoring logic.

---

## 3. Batch Safety Limits & Constraint Enforcement

Unbounded batch operations (e.g. "Analyze 5,000 businesses") can cause severe resource exhaustion, rate limit bans, or crashes. Phase 4A introduces explicit safety boundaries:

1. **Configurable Safety Limit (`max_prospects_per_run`)**:
   - Default: `15` prospects per run.
   - Configurable at `Agent` and `ProspectBatchExecutor` initialization.
2. **Intent-Level Constraint Clamping**:
   - When a user requests a count exceeding the safety limit (e.g., `limit=5000`), the `Agent` clamps the limit:
     ```python
     intent.constraints["limit"] = self.max_prospects_per_run
     intent.constraints["constrained_from"] = requested_limit
     state.record_error(
         f"Requested prospect count ({requested_limit}) exceeds maximum allowed safety limit ({self.max_prospects_per_run}). Constrained to {self.max_prospects_per_run}."
     )
     ```
3. **Executor-Level Guard**:
   - `ProspectBatchExecutor.execute_batch` validates `selected_count <= max_prospects_per_run`.
   - If exceeded, it either constrains to the limit or raises `BatchSizeLimitExceededError` depending on configuration.

---

## 4. Failure Isolation Architecture

Multi-prospect processing enforces strict failure isolation:
- An exception, network timeout, or policy block during processing of Prospect A **must never abort** the processing of Prospect B, C, or D.
- If Prospect A fails on a step (e.g. website scrape failure), execution for Prospect A halts with `status="failed"` and records the failure in `failed_steps` and `errors`.
- The loop immediately continues to Prospect B.
- System-level catastrophic failures (e.g., registry unavailability or memory limits) are recorded gracefully.
- The resulting `ProspectBatchResult` accurately reports:
  ```text
  Prospect A → failed (errors: ['Scrape timeout'])
  Prospect B → completed (opportunity_score: 85.0)
  Prospect C → completed (opportunity_score: 92.0)
  ```

---

## 5. Opportunity Ranking

Phase 4A does not create a secondary or competing scoring algorithm. Instead, it reuses the canonical signals from Phase 2 / Phase 3:
- Primary signal: `opportunity_analysis.opportunity_score` (from canonical `OpportunityAnalysis`).
- Fallback signal: `context.scores.composite_score` or `prospect.rating`.
- The `ProspectBatchResult.ranked_results()` method extracts these existing signals and returns sorted `ProspectExecutionResult` items.

---

## 6. Telemetry & Observability Integration

Telemetry events emitted during batch execution integrate seamlessly into the Phase 3F tracing infrastructure:
- **`batch_id`**: Added to `CapabilityTraceEvent` and `AgentRunTrace`.
- **`prospect_id`**: Added to `CapabilityTraceEvent`.
- Filtering: `InMemoryTelemetrySink.get_step_events(run_id, prospect_id, batch_id)` allows querying traces per prospect or per batch.
- Payloads: Strict privacy and size controls are maintained. Telemetry records identifiers, timestamps, capability names, and error messages, but never full HTML or heavy prospect payloads.

---

## 7. Capability Boundary & Non-Distributed Design

### 7.1 Strict Registry Boundary
`ProspectBatchExecutor` invokes capabilities **exclusively** through `CapabilityRegistry.execute(capability_name, input_contract)`.
- It does **not** import raw Playwright, PostgreSQL, Redis, or scraping modules.
- The executor is pure orchestration.

### 7.2 Deliberate Sequential Execution
Phase 4A deliberately uses sequential execution:
- No `asyncio` worker pools.
- No `concurrent.futures.ThreadPoolExecutor`.
- No Celery, Redis queues, Kafka, or background worker services.
- Correct domain semantics, error boundaries, and telemetry contracts must be proven before concurrency is introduced.

### 7.3 Future Scaling Considerations
Because `ProspectBatchExecutor` encapsulates the batch execution boundary behind `execute_batch(prospect_set, selection)`, future phases can introduce concurrency (e.g. bounded worker pools or task queues) entirely behind this interface without altering `ProspectSet`, `ProspectSelection`, or downstream ranking.

---

## 8. Verification & Test Coverage

All 22 test requirements are implemented and verified in [`tests/test_prospect_batch.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_prospect_batch.py):

| # | Test Scenario | Verified Behavior |
| :--- | :--- | :--- |
| 1 | `test_01_prospect_set_creation` | Validates `ProspectSet` creation with typed fields and `from_discovery_output`. |
| 2 | `test_02_prospect_selection_creation` | Validates `ProspectSelection` filtering and sorting contracts. |
| 3 | `test_03_empty_prospect_set` | Verifies graceful execution and zero-count batch result for empty sets. |
| 4 | `test_04_single_prospect_execution` | Verifies end-to-end execution of a single-prospect batch. |
| 5 | `test_05_multiple_prospects_execution` | Verifies execution across multiple prospects in a set. |
| 6 | `test_06_batch_size_limit_enforced` | Verifies `ProspectBatchExecutor` constrains counts exceeding safety limit. |
| 7 | `test_07_requested_count_above_limit_raises_if_not_constrained` | Verifies `BatchSizeLimitExceededError` when strict checking is enabled. |
| 8 | `test_08_successful_batch_metrics` | Verifies accurate calculation of `completed_count`, `duration_ms`, etc. |
| 9 | `test_09_one_prospect_failure_isolation` | Verifies Prospect A failure does not prevent Prospect B success. |
| 10 | `test_10_multiple_prospect_failures_isolated` | Verifies multiple individual failures are recorded independently. |
| 11 | `test_11_failure_isolation_preserves_completed_and_failed` | Confirms completed and failed counts are accurately segregated. |
| 12 | `test_12_system_level_failure_handling` | Confirms uncaught capability exceptions are safely caught per-prospect. |
| 13 | `test_13_prospect_execution_result_creation` | Validates typed `ProspectExecutionResult` attributes and serialization. |
| 14 | `test_14_prospect_batch_result_creation` | Validates typed `ProspectBatchResult` attributes and serialization. |
| 15 | `test_15_ranking_using_existing_opportunity_signals` | Verifies ranking by `opportunity_score` without new scoring logic. |
| 16 | `test_16_no_duplicate_business_model` | Verifies `ProspectSet` uses `schemas.business.Business` directly. |
| 17 | `test_17_registry_only_capability_execution` | Proves all execution goes exclusively through `CapabilityRegistry.execute`. |
| 18 | `test_18_batch_telemetry` | Validates emission of `batch_id` on capability trace events. |
| 19 | `test_19_prospect_specific_telemetry` | Validates distinct `prospect_id` across events for different businesses. |
| 20 | `test_20_existing_agent_workflow_remains_valid` | Validates backwards compatibility for existing single-business agent runs. |
| 21 | `test_21_agent_constrains_excessive_batch_requests` | Confirms agent constrains requests like "Analyze 5000 businesses" to safety limit. |
| 22 | `test_22_existing_discovery_tests_remain_valid` | Validates discovery populates both `state.prospects` and `state.prospect_set`. |

**Total Test Results:**
- 183 tests passing across all platform suites (0 failures, 0 errors).
- Execution time: 0.24s.
