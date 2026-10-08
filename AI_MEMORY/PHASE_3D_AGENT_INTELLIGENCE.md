# Phase 3D — Agent Intelligence & Dynamic Planning

**Status:** COMPLETE  
**Architecture Layer:** Agent Core & Intelligence Boundary  
**Date:** 2026-10-08  
**Dependencies:** Phase 3A (Design), Phase 3B (Capability Layer), Phase 3C (Controlled Orchestration)

---

## 1. Executive Summary

Phase 3D elevates the agent from a static 9-step execution pipeline into an intelligent, controlled, dynamic agent capable of interpreting diverse natural-language user goals, constructing minimal dependency-aware execution plans, handling ambiguous queries via structured clarification requests, and rejecting unsupported external actions cleanly.

Strict architectural guardrails were preserved:
- **Pure Python + Pydantic v2**: No external agent framework (no LangGraph, LangChain, AutoGen, CrewAI, Semantic Kernel).
- **Deterministic Boundary**: Goal interpretation and dynamic planning operate deterministically without an unconstrained LLM planner loop.
- **Strict Capability Registry Boundary**: All capability execution flows through `CapabilityRegistry`.
- **Zero Infrastructure Bleed**: No raw DB access, SQL, Playwright, or direct HTTP dispatch within the Agent layer.
- **Evaluation Gate Preserved**: AI-generated reasoning steps remain protected by `evaluate_ai_reasoning`.

---

## 2. Goal Interpretation Architecture (`agent/intent.py`)

A new module, [`agent/intent.py`](file:///Users/ashik/Bens%20Repository/scrapper/agent/intent.py), separates user request comprehension from plan generation and execution.

### 2.1 Structured Models

#### `AgentIntent`
Represents the structured interpretation of the user's objective:
- `intent_type`: Categorization via `IntentType` enum:
  - `RESEARCH_KNOWN_BUSINESS`
  - `RESEARCH_AND_OUTREACH`
  - `DISCOVER_PROSPECTS`
  - `DISCOVER_AND_ANALYZE`
  - `DISCOVER_AND_OUTREACH`
  - `AUDIT_ONLY`
  - `UNSUPPORTED_EXTERNAL_ACTION`
  - `AMBIGUOUS`
  - `UNKNOWN`
- `objective`: Cleaned natural-language user goal
- `target_business`: Named entity if a specific business was targeted
- `location`: Extracted geographic location (e.g., "Bangalore", "Austin")
- `industry`: Extracted domain or industry keyword (e.g., "dentists", "plumbing")
- `search_query`: Extracted query parameters for discovery
- **Capability Flags**:
  - `requires_discovery`: Boolean
  - `requires_research`: Boolean
  - `requires_opportunity_analysis`: Boolean
  - `requires_outreach`: Boolean
  - `requires_evaluation`: Boolean
  - `requires_draft`: Boolean
  - `requires_external_action`: Boolean
  - `requires_clarification`: Boolean

#### `ClarificationRequest`
Produced when a user goal is underspecified:
- `question`: Explanatory inquiry prompt for the user
- `missing_information`: List of missing parameters (e.g., `["location", "target_criteria"]`)
- `blocking`: Boolean (always `True` for unexecutable goals)

### 2.2 Supported Goal Categories

1. **A. Research a known business**
   - *Example:* `"Analyze ABC Technologies and tell me whether it is a good prospect."`
   - *Capabilities:* `audit_website_tech`, `enrich_leadership_social`, `mine_business_intelligence`, `calculate_health_and_scores`, `assemble_prospect_context`, `synthesize_opportunity_analysis`.
2. **B. Research and prepare outreach**
   - *Example:* `"Analyze ABC Technologies and prepare an outreach message."`
   - *Capabilities:* All research capabilities + `formulate_outreach_strategy`, `evaluate_ai_reasoning`, `render_outreach_drafts`.
3. **C. Discover prospects**
   - *Example:* `"Find businesses in Bangalore that may need website development."`
   - *Capabilities:* `discover_prospects` (minimal discovery-only plan).
4. **D. Discover + analyze + prepare outreach**
   - *Example:* `"Find 10 Bangalore businesses with weak websites and prepare outreach drafts."`
   - *Capabilities:* Full pipeline starting with `discover_prospects` followed by downstream analysis, scoring, opportunity synthesis, outreach strategy, evaluation, and draft rendering.

### 2.3 Ambiguity & Clarification Handling
When discovery queries omit critical constraints (such as location or search criteria, e.g. `"Find businesses"`), `GoalInterpreter` classifies the goal as `IntentType.AMBIGUOUS` and constructs a `ClarificationRequest`. The Agent transitions to `AgentStatus.NEEDS_CLARIFICATION` and returns immediately without running capabilities or wasting compute.

### 2.4 Unsupported External Action Handling
When goals request real-world messaging or dispatches (e.g., `"Send WhatsApp messages to all prospects"` or `"Dispatch emails to leads"`), `GoalInterpreter` flags `requires_external_action = True` and categorizes the intent as `IntentType.UNSUPPORTED_EXTERNAL_ACTION`. The Agent cleanly halts with an explanatory policy message without executing fake or unapproved network requests.

---

## 3. Dynamic Planning (`agent/planner.py`)

`AgentPlanner` was refactored to construct minimal, goal-tailored DAG plans using `AgentIntent`.

### 3.1 Capability Requirement Mapping
Instead of always executing all 9 capabilities, `AgentPlanner.plan_from_intent(intent, initial_params)` generates only the steps required by the intent flags:

| Capability Flag | Registered Capability | DAG Step ID |
| :--- | :--- | :--- |
| `requires_discovery` | `discover_prospects` | `step_discover` |
| `requires_research` | `audit_website_tech` | `step_audit` |
| `requires_research` | `enrich_leadership_social` | `step_enrich` |
| `requires_research` | `mine_business_intelligence` | `step_intel` |
| `requires_research` | `calculate_health_and_scores` | `step_score` |
| `requires_research` | `assemble_prospect_context` | `step_context` |
| `requires_opportunity_analysis` | `synthesize_opportunity_analysis` | `step_opp` |
| `requires_outreach` | `formulate_outreach_strategy` | `step_outreach` |
| `requires_evaluation` | `evaluate_ai_reasoning` | `step_eval` |
| `requires_draft` | `render_outreach_drafts` | `step_draft` |

### 3.2 Dynamic Dependency Resolution
- In **known-business** workflows, `step_audit`, `step_enrich`, and `step_intel` run as root steps with zero dependencies.
- In **discovery-led** workflows (`requires_discovery = True`), `step_audit`, `step_enrich`, and `step_intel` dynamically depend on `["step_discover"]`, ensuring discovery completes and surfaces prospects before deep auditing starts.
- Discovery-only workflows produce a clean 1-step plan consisting exclusively of `discover_prospects`.
- Audit-only workflows produce a single `audit_website_tech` step.

---

## 4. Multi-Prospect State Support (`agent/state.py` & `agent/executor.py`)

1. **State Extension**:
   - `AgentState.intent`: Captures the parsed `AgentIntent`.
   - `AgentState.clarification_request`: Captures active clarification requirements.
   - `AgentState.prospects`: Stores `List[Business]` returned from discovery without introducing database/queue overhead.
2. **State Machine Expansion**:
   - Added `AgentStatus.NEEDS_CLARIFICATION`.
   - Allowed transitions: `PLANNING -> NEEDS_CLARIFICATION`, `NEEDS_CLARIFICATION -> PLANNING`, and `NEEDS_CLARIFICATION -> FAILED`.
3. **Parameter Hydration**:
   - `AgentExecutor._update_state_models()` unpacks `DiscoverProspectsOutput.businesses` directly into `state.prospects`.
   - `AgentExecutor._hydrate_parameters()` dynamically pulls the lead prospect from `state.prospects[0]` to populate downstream parameters (`business_name`, `website_url`, `rating`, `review_count`) when running discovery-led multi-stage pipelines.

---

## 5. Lifecycle Coordination (`agent/agent.py`)

The high-level `Agent.run()` method now follows the refined lifecycle:

```text
User Goal
   ↓
GoalInterpreter.interpret(goal)
   ↓
[Ambiguous?] ──Yes──> Transition to NEEDS_CLARIFICATION & Return ClarificationRequest
   ↓ No
[External Action?] ──Yes──> Halt with Policy Rejection
   ↓ No
AgentPlanner.plan_from_intent(intent)
   ↓
DAG Validation (Cycles, Unknown Capabilities, Dangling Dependencies)
   ↓
AgentExecutor.execute(plan, state)
   ↓
CapabilityRegistry Dispatches (READ / WRITE Policies Checked)
   ↓
Evaluation Gate Verification
   ↓
AgentFinalResponse (State, Context, Analysis, Outreach, Prospects, Clarification)
```

---

## 6. Verification and Test Suite

16 new tests were added in [`tests/test_agent.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_agent.py) (`TestAgentIntelligenceAndDynamicPlanning`), specifically validating Phase 3D requirements:

1. `test_21_known_business_research_plan`: Validates research plan generates 6 steps ending with `step_opp`.
2. `test_22_known_business_outreach_plan`: Validates outreach plan generates 9 steps ending with `step_draft`.
3. `test_23_discovery_only_request`: Validates discovery query generates 1-step plan executing only `discover_prospects`.
4. `test_24_discovery_and_analysis_workflow`: Validates discovery + analysis plan has 7 steps with `step_audit` depending on `step_discover`.
5. `test_25_discovery_and_outreach_workflow`: Validates full 10-step discovery-to-draft plan with hydrated prospects.
6. `test_26_missing_location_clarification`: Validates `"Find dentists"` returns `NEEDS_CLARIFICATION` and 0 capability executions.
7. `test_27_unsupported_external_action_whatsapp`: Validates `"Send WhatsApp messages"` safely halts without executing dispatches.
8. `test_28_dynamic_plan_generation_audit_only`: Validates `"Audit tech for Acme"` creates a 1-step audit plan.
9. `test_29_capability_ordering_in_dag`: Validates topological DAG order: discover -> audit -> score -> context -> opp -> outreach -> eval -> draft.
10. `test_30_discovery_appearing_before_analysis`: Validates `step_discover` precedes all research steps.
11. `test_31_existing_phase_3c_workflow_remains_valid`: Validates backwards compatibility of `create_default_plan`.
12. `test_32_registry_only_execution_remains_enforced`: Validates executor executes exclusively through registry.
13. `test_33_evaluation_gate_remains_enforced_in_dynamic_plans`: Validates hallucination failure halts draft step in dynamic outreach plan.
14. `test_34_ambiguous_goal_does_not_execute_capabilities`: Validates zero capability invocations on ambiguous requests.
15. `test_35_unknown_capability_cannot_enter_dynamic_plan`: Validates planning rejects unregistered capability names.
16. `test_36_unsupported_email_dispatch_action`: Validates `"Email these prospects"` rejection.

### Test Suite Summary
- **Phase 1 & 2 Core Tests**: 75 passing
- **Phase 3B Capability Tests**: 13 passing
- **Phase 3C Agent Core Tests**: 20 passing
- **Phase 3D Agent Intelligence Tests**: 16 passing
- **Total Suite**: **124 tests passing** with 0 failures and 0 warnings (runtime: 0.178s).

---

## 7. Known Limitations & Next Steps

1. **Single-Lead Pipeline Continuation**: When discovery returns multiple businesses, downstream deep auditing currently hydrates the top prospect (`state.prospects[0]`). Batch iterative fan-out or multi-prospect map-reduce orchestration can be added when scalable execution queues are introduced.
2. **Deterministic Goal Interpretation**: Goal parsing uses pattern-based extraction. When an LLM planner is introduced in future iterations, `GoalInterpreter` can be augmented with structured JSON LLM parsing while maintaining the exact same `AgentIntent` contract and deterministic validation boundary.
