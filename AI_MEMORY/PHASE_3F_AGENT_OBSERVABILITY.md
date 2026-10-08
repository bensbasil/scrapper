# Phase 3F — Agent Observability & Execution Tracing

**Date:** 2026-10-08  
**Scope:** Lightweight, Structured Agent Execution Tracing & Auditing  
**Status:** COMPLETE  

---

## 1. Architectural Objective

Phase 3F implements structured observability and execution tracing for the Agent orchestration layer without introducing external monitoring infrastructure (OpenTelemetry, Prometheus, Datadog, Elasticsearch, Redis, or external cloud SDKs).

The system can answer:
- What did the user ask? (`user_goal`)
- How was the request interpreted? (`intent_trace`, `intent_type`)
- Which interpretation source was used? (`intent_source`: `llm`, `deterministic_fallback`, `deterministic`)
- What plan was generated? (`plan_trace`: DAG steps, dependencies, step counts)
- Which capability steps executed? (`step_events`: `STARTED`, `COMPLETED`)
- Which steps were blocked or skipped? (`StepEventStatus.BLOCKED`, `StepEventStatus.SKIPPED`)
- How long did each step take? (`duration_ms` measured via `time.monotonic()`)
- Which failures occurred? (`ErrorCategory`, `error_message`)
- Was fallback used? (`fallback_used: bool`)
- Did evaluation pass or fail? (`evaluation_passed: bool`)
- Why did the Agent stop? (`final_outcome`, `status`, `error_category`)

---

## 2. Telemetry Architectural Boundary

```text
User Goal
   ↓
Agent (run_id assigned, monotonic timer starts)
   ↓
Intent Interpretation (LLMIntentInterpreter / GoalInterpreter)
   ↓ [IntentTrace recorded]
Validation (DeterministicIntentValidator)
   ↓
Planning (AgentPlanner DAG generation & Kahn's validation)
   ↓ [PlanTrace recorded]
Execution (AgentExecutor)
   ↓ [STARTED / COMPLETED / FAILED / BLOCKED events emitted]
Capability Registry
   ↓
Domain Systems

        ↘
       AgentTelemetrySink (InMemoryTelemetrySink)
         ↳ AgentRunTrace (Immutable Run Audit)
```

**Key Architectural Invariants:**
1. **Telemetry Observes, Never Controls**: Telemetry sinks and models are strictly observational. Telemetry code never chooses capabilities, controls state machines, or executes tools.
2. **Registry Exclusivity Maintained**: Telemetry cannot bypass `CapabilityRegistry` or domain policies.
3. **No Infrastructure Coupling**: Clean `AgentTelemetrySink` interface allows future adapters (e.g., OpenTelemetry, Datadog) without modifying Agent core logic.

---

## 3. Core Telemetry Models (`agent/telemetry.py`)

### 3.1 `AgentRunTrace` (Run-Level Audit)
Represents the complete, immutable historical audit of an Agent run:
- `run_id`: Unique identifier for the run (`run_<uuid>`).
- `task_id`: Agent task identifier (`task_<uuid>`).
- `user_goal`: Original natural-language user goal.
- `status`: Final `AgentStatus` string (`COMPLETED`, `FAILED`, `NEEDS_CLARIFICATION`, etc.).
- `started_at` / `completed_at`: ISO format UTC timestamps.
- `duration_ms`: High-resolution total run latency measured via `time.monotonic()`.
- `intent_source`: `llm`, `deterministic_fallback`, or `deterministic`.
- `intent_type`: Categorized intent string.
- `intent_trace`: Structured `IntentTrace`.
- `plan_trace`: Structured `PlanTrace`.
- `step_events`: Chronologically ordered list of `CapabilityTraceEvent` objects.
- Aggregate counters: `plan_step_count`, `executed_step_count`, `failed_step_count`, `blocked_step_count`, `skipped_step_count`.
- `fallback_used`: Boolean flag indicating if LLM fallback was triggered.
- `evaluation_passed`: Boolean flag from evaluation gate (if applicable).
- `error_category`: Categorized high-level error classification (`ErrorCategory`).
- `final_outcome`: Human-readable summary of the run outcome.

### 3.2 `CapabilityTraceEvent` (Step-Level Lifecycle)
Records individual capability lifecycle transitions:
- `run_id`: Correlating run identifier.
- `step_id`: Plan step identifier (e.g. `step_discover`, `step_audit`, `step_draft`).
- `capability_name`: Registered capability name.
- `capability_classification`: Policy class (`READ`, `WRITE`, `EXTERNAL_ACTION`).
- `status`: Lifecycle status (`STARTED`, `COMPLETED`, `FAILED`, `BLOCKED`, `SKIPPED`).
- `started_at` / `completed_at`: ISO format timestamps.
- `duration_ms`: Millisecond duration measured via `time.monotonic()`.
- `error_type`: Categorized `ErrorCategory` if failed.
- `error_message`: Concise error message if failed.
- `dependency_status`: Snapshot dictionary of prerequisite step statuses (e.g. `{"step_discover": "COMPLETED"}`).

### 3.3 `IntentTrace`
Records metadata from the intent interpretation phase:
- `intent_source`: `llm`, `deterministic_fallback`, `deterministic`, or `failed`.
- `intent_type`: Interpreted intent type.
- `validation_succeeded`: Whether deterministic validation passed.
- `clarification_required`: Ambiguity flag.
- `external_action_detected`: Hard policy override flag.
- `duration_ms`: Interpretation latency.
- `fallback_used`: Boolean.
- `provider` / `model`: LLM provider/model metadata (e.g. `gemini`, `gemini-2.5-pro`).
- `error`: Truncated error message if interpretation failed.

### 3.4 `PlanTrace` and `PlanStepTrace`
Records serializable DAG metadata:
- `plan_id`: Plan identifier.
- `workflow_name`: Identified workflow pattern.
- `step_count`: Total steps in generated plan.
- `steps`: List of `PlanStepTrace` (containing `step_id`, `capability_name`, `depends_on`).
- `duration_ms`: Planning latency.
- `validation_succeeded`: Boolean indicating DAG validation success.
- `validation_error`: Validation error string if invalid.

---

## 4. Error Classification Hierarchy (`ErrorCategory`)

Structured classifications ensure consistent error reporting without an over-engineered exception hierarchy:

| Category | Description | Trigger Example |
| :--- | :--- | :--- |
| `INTENT_ERROR` | User intent could not be understood or is outside platform domain | "Fly to Mars" (unknown workflow) |
| `VALIDATION_ERROR` | Plan validation failed (missing steps, unknown capabilities, cycle) | Step references unregistered capability |
| `PLANNING_ERROR` | Dynamic planner failed during DAG synthesis | Planner internal exception |
| `CAPABILITY_ERROR` | Tool execution failed in domain system | Scraper network timeout, scraping blocked |
| `POLICY_ERROR` | Policy violation or blocked external action | Request asks to blast emails directly |
| `EVALUATION_ERROR` | Reasoning failed AI quality / factual grounding gate | Hallucination detected in evaluation |
| `SYSTEM_ERROR` | Unhandled agent internal error | Unexpected runtime failure |

---

## 5. Security & Privacy Guarantees

Telemetry captures **execution metadata**, strictly prohibiting business payloads or credentials:

1. **No Raw HTML / Scraping Payloads**: Scraped DOMs, page bodies, and raw network responses are never stored in `CapabilityTraceEvent` or `AgentRunTrace`.
2. **No Raw Database Rows**: PostgreSQL records, raw prospect models, or full evidence stores are excluded from telemetry.
3. **No Secrets / Credentials**: API keys (e.g. `GEMINI_API_KEY`, `OPENAI_API_KEY`), Bearer tokens, and HTTP authorization headers are never captured.
4. **No Full Prompts or Private LLM Payloads**: Telemetry stores model name, provider, latency, and structured flags—never private raw prompts or multi-kilobyte model completions.

---

## 6. Mutable State (`AgentState`) vs. Immutable Trace (`AgentRunTrace`)

| Dimension | `AgentState` | `AgentRunTrace` |
| :--- | :--- | :--- |
| **Role** | Execution Working State | Historical Audit Record |
| **Mutability** | Mutable (progresses through state machine) | Immutable / Append-only |
| **Payloads** | Holds domain objects (`ProspectContext`, `OpportunityAnalysis`) | Holds execution metadata only |
| **Lifecycle** | Created at start, discarded/persisted post-run | Emitted to `AgentTelemetrySink` for auditing |
| **Target Audience**| Agent Executor and Capability Registry | Engineering, Observability, and Audit logs |

---

## 7. Event Lifecycle and Execution Tracing

```text
Step Lifecycle:
1. Executor inspects PlanStep.
2. Capability registered & policy evaluated.
3. Sink records: CapabilityTraceEvent(status=STARTED).
4. Registry executes capability.
5. If SUCCESS:
     Sink records: CapabilityTraceEvent(status=COMPLETED, duration_ms=...).
   If FAILURE:
     Sink records: CapabilityTraceEvent(status=FAILED, error_type=CAPABILITY_ERROR, ...).
     Downstream steps cascaded:
       Sink records: CapabilityTraceEvent(status=BLOCKED, dependency_status={failed_step: "FAILED"}).
```

---

## 8. Telemetry Abstraction (`AgentTelemetrySink`)

```python
class AgentTelemetrySink:
    def record_run(self, trace: AgentRunTrace) -> None: ...
    def record_step(self, event: CapabilityTraceEvent) -> None: ...
    def get_run(self, run_id: str) -> Optional[AgentRunTrace]: ...
    def get_runs(self) -> List[AgentRunTrace]: ...
    def get_step_events(self, run_id: Optional[str] = None) -> List[CapabilityTraceEvent]: ...
```

- **`InMemoryTelemetrySink`**: Reference in-memory implementation for local execution and unit tests. Supports filtering by `run_id` and memory clearing.
- **Future Adapters**: Can be extended with `OpenTelemetrySink`, `DatadogTelemetrySink`, or `DatabaseTelemetrySink` without touching `Agent` or `AgentExecutor`.

---

## 9. Verification & Test Suite

All 20 Phase 3F unit tests pass in `tests/test_telemetry.py`:
1. Run trace creation and metadata validation.
2. Run start timestamp in ISO format.
3. Run completion timestamp in ISO format.
4. Monotonic duration measurement (`duration_ms >= 0.0`).
5. Intent source recorded (`deterministic` vs `llm`).
6. LLM fallback recorded with provider and model flags.
7. Planning trace recorded with serializable DAG steps.
8. Capability `STARTED` event recorded before execution.
9. Capability `COMPLETED` event recorded with duration.
10. Capability `FAILED` event recorded with `ErrorCategory.CAPABILITY_ERROR`.
11. Blocked dependency trace and cascade tracking.
12. Evaluation gate failure recorded with `ErrorCategory.EVALUATION_ERROR`.
13. Policy rejection recorded with `ErrorCategory.POLICY_ERROR`.
14. Execution ordering preserved across multiple events.
15. Telemetry cannot bypass `CapabilityRegistry`.
16. Telemetry contains no raw HTML or business database rows.
17. Telemetry contains no secrets or API keys.
18. Existing `AgentState` behavior remains unchanged.
19. `InMemoryTelemetrySink` listing, filtering, and clearing.
20. Ambiguous / clarification request tracing.

**Overall Test Suite Status:**
- **161 total tests passing** across 10 test suites in 0.26s.
- Zero regressions.
