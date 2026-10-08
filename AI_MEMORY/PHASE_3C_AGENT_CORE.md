# Phase 3C — Agent Core & Controlled Orchestration

**Date:** 2026-10-08  
**Scope:** Plain Python + Pydantic v2 Agent Orchestration Layer, Deterministic Planner, Dependency-Aware Executor, Policy Enforcer, State Machine, and Quality Gates  
**Status:** COMPLETE  

---

## 1. Executive Summary

Phase 3C establishes the **Agent Orchestration Core** (`agent/`), bridging user goals to the typed Application Capability Layer implemented in Phase 3B.

The architecture strictly adheres to the prescribed layered separation:
```text
User Goal
    ↓
Agent (agent/agent.py)
    ↓
AgentExecutor (agent/executor.py) & PolicyEnforcer (agent/policies.py)
    ↓
CapabilityRegistry (application/capabilities/registry.py)
    ↓
Typed Capability Tools (application/capabilities/*.py)
    ↓
Canonical Domain Modules (Enrichment, Scoring, AI Reasoners, Evaluation)
    ↓
Infrastructure (PostgreSQL, Playwright, LLM APIs)
```

The implementation relies exclusively on standard Python and Pydantic v2. Frameworks such as LangGraph and LangChain remain intentionally deferred to preserve foundational control and deterministic safety.

---

## 2. Directory Structure

```text
agent/
├── __init__.py           # Public exports (Agent, AgentState, AgentPlanner, AgentExecutor, models)
├── models.py             # AgentStatus, StepStatus, ApprovalStatus, PlanStep, Plan, ExecutionRecord, ApprovalRequest, AgentFinalResponse
├── state.py              # AgentState model and validated state machine transitions
├── planner.py            # AgentPlanner with deterministic rule-based workflows and DAG dependency validation
├── executor.py           # AgentExecutor enforcing topological order, parameter hydration, evaluation gate, and execution caps
├── policies.py           # PolicyEnforcer and ExecutionPolicyConfig (READ, WRITE, EXTERNAL_ACTION)
└── agent.py              # High-level Agent orchestrator with plan, validate, execute, and approve/reject lifecycle
```

---

## 3. Core Component Architecture

### 3.1 `AgentState` (`agent/state.py`)
Tracks the end-to-end task progression without duplicating canonical models:
- **`task_id` & `user_goal`**: Unique task tracking and intent specification.
- **`status`**: Current lifecycle phase (`PLANNING`, `EXECUTING`, `WAITING_FOR_APPROVAL`, `COMPLETED`, `FAILED`).
- **`plan`**: Typed [`Plan`](file:///Users/ashik/Bens%20Repository/scrapper/agent/models.py#L48) containing ordered steps.
- **`completed_steps`**: List of [`ExecutionRecord`](file:///Users/ashik/Bens%20Repository/scrapper/agent/models.py#L71) audit items.
- **Intermediate Domain Models**: Direct typed instances of `ProspectContext`, `OpportunityAnalysis`, `OutreachStrategy`, `EvaluationResult`, and `OutreachDraft`.
- **`approval_request`**: Active [`ApprovalRequest`](file:///Users/ashik/Bens%20Repository/scrapper/agent/models.py#L88) if paused for human review.
- **`errors`**: Logged validation or execution failure messages.
- **`final_response`**: Structured [`AgentFinalResponse`](file:///Users/ashik/Bens%20Repository/scrapper/agent/models.py#L104) envelope.
- **`execution_count`**: Counter enforcing the maximum execution limit.

### 3.2 State Machine Transitions
State transitions are strictly validated by `AgentState.transition_to()` against the allowed transition graph:
```text
               ┌──────────┐
               │ PLANNING │
               └────┬──┬──┘
                    │  └───────────────────┐
                    ↓                      ↓
              ┌───────────┐           ┌────────┐
        ┌────►│ EXECUTING ├──────────►│ FAILED │◄───┐
        │     └──┬───┬────┘           └────────┘    │
        │        │   └──────────────┐               │
        │        ↓                  ↓               │
        │ ┌──────────────────────┐ ┌───────────┐    │
        └─┤ WAITING_FOR_APPROVAL │ │ COMPLETED │    │
          └──────────┬───────────┘ └───────────┘    │
                     └──────────────────────────────┘
```
Arbitrary mutations or illegal transitions (e.g. `PLANNING -> COMPLETED` or exiting `COMPLETED`) raise `InvalidStateTransitionError`.

### 3.3 `AgentPlanner` (`agent/planner.py`)
Deterministic, rule-based planner converting user goals into typed `Plan` instances:
- Supports the canonical research and outreach workflow:
  `audit_website_tech` → `enrich_leadership_social` → `mine_business_intelligence` → `calculate_health_and_scores` → `assemble_prospect_context` → `synthesize_opportunity_analysis` → `formulate_outreach_strategy` → `evaluate_ai_reasoning` → `render_outreach_drafts`.
- Performs graph validation using Kahn's topological sort algorithm before execution:
  - Detects duplicate step IDs.
  - Detects missing dependencies.
  - Detects self-referential and circular dependencies.
  - Validates that referenced capabilities exist in `CapabilityRegistry`.

### 3.4 `AgentExecutor` (`agent/executor.py`)
Controlled step-by-step dispatcher:
- **Dependency Ordering**: Only executes steps whose dependencies have reached `StepStatus.COMPLETED`.
- **Failure Cascading**: If a prerequisite fails, all dependent steps are cascaded to `StepStatus.BLOCKED`.
- **Context Hydration**: Automatically maps outputs from prior steps and `AgentState` (such as `ProspectContext`, `OpportunityAnalysis`, and `OutreachStrategy`) into downstream tool arguments.
- **Policy Interception**: Evaluates capability permissions via `PolicyEnforcer`.
- **Safety Execution Cap**: Enforces a hard ceiling of 15 capability executions per task to prevent loops.
- **Evaluation Gate**: After `evaluate_ai_reasoning`, inspects `EvaluationResult.passed`. If the evaluation fails, execution halts safely, exposes the issues, blocks drafting, and transitions state to `FAILED`.

### 3.5 `PolicyEnforcer` (`agent/policies.py`)
Enforces the safety policy matrix:
- **`READ`**: Allowed automatically with zero side-effects.
- **`WRITE`**: Allowed only under configured staged-write policy (`allow_staged_writes=True`). If `require_approval_for_write=True`, pauses for human review.
- **`EXTERNAL_ACTION`**: Strictly requires explicit human approval before execution.

---

## 4. Verification & Test Suite

The test suite in [`tests/test_agent.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_agent.py) validates all 20 required scenarios (100% pass rate in 0.008s):

1. **`test_01_valid_goal_produces_valid_plan`**: Valid user goal produces a structured plan with correct dependency topology.
2. **`test_02_unknown_workflow_fails_safely`**: Unmapped workflows trigger `UnknownWorkflowError`.
3. **`test_03_dependency_validation_works`**: Missing step dependencies are caught by `PlanValidationError`.
4. **`test_04_circular_dependency_is_detected`**: Cyclic dependency loops are identified and rejected.
5. **`test_05_capabilities_execute_through_registry`**: Tool execution strictly dispatches through `CapabilityRegistry.execute()`.
6. **`test_06_correct_dependency_ordering`**: Steps run in topological prerequisite order.
7. **`test_07_capability_outputs_populate_agent_state`**: Outputs populate typed `AgentState` fields directly.
8. **`test_08_capability_failure_stops_dependent_work`**: Failed steps cascade `BLOCKED` status to dependents and halt the task.
9. **`test_09_unknown_capability_is_rejected`**: Unregistered capabilities fail safely.
10. **`test_10_policy_violation_is_rejected`**: Disallowed writes pause for human approval.
11. **`test_11_execution_limit_works`**: Exceeding the maximum 15 execution cap halts the task with a controlled error.
12. **`test_12_valid_state_transitions`**: Lifecycle progression `PLANNING -> EXECUTING -> COMPLETED` passes validation.
13. **`test_13_invalid_state_transitions_rejected`**: Illegal transitions raise `InvalidStateTransitionError`.
14. **`test_14_completed_task_reaches_completed`**: Full successful execution terminates with `COMPLETED`.
15. **`test_15_failed_task_reaches_failed`**: Planning or execution errors terminate with `FAILED`.
16. **`test_16_successful_evaluation_allows_completion`**: Passing the evaluation quality gate permits draft rendering.
17. **`test_17_failed_evaluation_stops_execution`**: Failing the evaluation gate blocks drafting and exposes defects.
18. **`test_18_agent_cannot_directly_call_infrastructure`**: Agent and Executor maintain zero direct imports or dependencies on `psycopg2`, `playwright`, `requests`, or raw sockets.
19. **`test_19_agent_cannot_bypass_capability_registry`**: Unregistered capability calls cannot bypass the registry.
20. **`test_20_no_external_communication_can_occur`**: `EXTERNAL_ACTION` tools strictly enforce human approval gating.

### Full Test Suite Results
- Total test count across all test modules: **108 tests passing** (0.171s).

---

## 5. Architectural Guardrails & Deferred Decisions

- **Preservation of Canonical Pipeline**: [`pipeline_runner.py`](file:///Users/ashik/Bens%20Repository/scrapper/pipeline_runner.py) remains intact and unaffected. The Agent operates as an independent, alternative orchestration layer.
- **Framework Integration**: LangGraph, LangChain, AutoGen, and CrewAI were deliberately excluded. The clean boundary contracts established here make future migration to a graph engine trivial should state checkpointing or distributed state persistence be required.
- **No Direct LLM Planning**: Planning remains deterministic and rule-based in Phase 3C to guarantee deterministic safety before exposing LLM planning.
