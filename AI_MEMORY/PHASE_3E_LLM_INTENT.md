# Phase 3E — LLM-Powered Intent Interpretation

**Status:** COMPLETE  
**Architecture Layer:** Agent Intelligence & Intent Interpretation  
**Date:** 2026-10-08  
**Dependencies:** Phase 2B (LLM Abstraction), Phase 3C (Controlled Orchestration), Phase 3D (Dynamic Planning)

---

## 1. Executive Summary

Phase 3E introduces the provider-independent `LLMClient` into the Agent layer for **natural-language goal interpretation ONLY**. 

The boundary is strictly enforced:
- The LLM translates natural-language goals into structured `AgentIntent`.
- The LLM does **NOT** select capabilities, plan execution order, generate code/SQL, invoke tools, access databases, or bypass safety policies.
- Deterministic planning and validation retain complete authority over capability sequencing, DAG construction, policy enforcement, and execution.
- If the LLM is unavailable, times out, throws provider errors, or returns malformed/contradictory outputs, the Agent automatically falls back to the deterministic `GoalInterpreter` with zero disruption.

---

## 2. Why the LLM is Used (and Why Only for Intent)

### 2.1 The Need for Natural-Language Flexibility
Users communicate business goals with wide linguistic variety:
- *"Analyze Apex Plumbing and prepare outreach"*
- *"Find 10 dentists in Chicago and write cold outreach drafts for them"*
- *"Inspect tech stack for Zenith Fitness"*

While deterministic regex pattern matching handles structured phrasing, natural language easily introduces vocabulary shifts, compound clauses, and complex parameter specifications. The LLM excels at parsing varied expressions into structured fields.

### 2.2 Why the LLM Does NOT Plan or Select Tools
Allowing an LLM to generate tool calls, choose capability names, or dictate execution sequences creates serious vulnerabilities:
1. **Hallucinated Capabilities:** LLMs frequently invent non-existent tools or call dangerous shell/database commands.
2. **Nondeterministic Execution DAGs:** LLMs can skip prerequisite steps (e.g. attempting to formulate outreach without first assembling evidence context).
3. **Security Bypasses:** An adversarial or confused LLM could attempt to trigger external actions (e.g. mass emailing leads) without authorization.
4. **Unpredictable Failure Modes:** Pure LLM orchestration loops suffer from nondeterministic deadlocks, infinite loops, and cost inflation.

By restricting the LLM to returning structured `AgentIntent`—and using deterministic Kahn's topological sort and capability mappings for planning—the platform gains natural-language flexibility with 100% deterministic safety guarantees.

---

## 3. Architecture Flow

```text
User Natural-Language Goal
           ↓
LLMIntentInterpreter (calls LLMClient.generate_structured)
           ↓
[LLM Available & Valid?]
      ├── Yes ──> Raw AgentIntent
      └── No ───> Fallback: Deterministic GoalInterpreter
           ↓
DeterministicIntentValidator
      ├── Validates IntentType & Required Entities
      ├── Overrides External Action Keywords (Safety Interception)
      ├── Checks Ambiguity & Missing Information (Location/Industry)
      └── Enforces Semantic Consistency (Draft requires Outreach, etc.)
           ↓
Validated AgentIntent (intent_source: 'llm' | 'deterministic_fallback' | 'deterministic')
           ↓
AgentPlanner.plan_from_intent(intent)
           ↓
Validated Capability DAG
           ↓
AgentExecutor (strictly via CapabilityRegistry)
```

---

## 4. Architectural Components

### 4.1 Structured Intent Contract (`agent/intent.py`)
`AgentIntent` represents the domain's structured requirement contract:
- `intent_type`: `IntentType` enum (`RESEARCH_KNOWN_BUSINESS`, `RESEARCH_AND_OUTREACH`, `DISCOVER_PROSPECTS`, `DISCOVER_AND_ANALYZE`, `DISCOVER_AND_OUTREACH`, `AUDIT_ONLY`, `UNSUPPORTED_EXTERNAL_ACTION`, `AMBIGUOUS`, `UNKNOWN`).
- `objective`: Cleaned statement of the task.
- `target_business`: Extracted company name if specified.
- `location`, `industry`, `search_query`: Extracted discovery constraints.
- **Requirement Flags**: `requires_discovery`, `requires_research`, `requires_opportunity_analysis`, `requires_outreach`, `requires_evaluation`, `requires_draft`, `requires_external_action`, `requires_clarification`.
- `clarification_request`: Optional `ClarificationRequest` if ambiguous.

Resilience additions in Phase 3E:
- `@field_validator("intent_type", mode="before")`: Normalizes case-insensitive strings to enum members.
- `@model_validator(mode="before")`: Normalizes aliases (e.g. `requires_outreach_strategy` -> `requires_outreach`).
- `model_config = ConfigDict(extra="ignore")`: Automatically drops any injected fields (such as `tools`, `capabilities`, `execution_steps`).

### 4.2 LLM Intent Interpreter (`agent/llm_intent.py`)
`LLMIntentInterpreter`:
- Reuses the provider-independent `ai.client.LLMClient`.
- Sends a concise, domain-specific system prompt describing supported intent types and rules.
- Invokes `llm_client.generate_structured(prompt, response_model=AgentIntent, system_prompt=...)`.
- Passes the result to `DeterministicIntentValidator`.
- If `LLMClient.is_available` is `False` or if any error occurs (parsing error, schema error, timeout, HTTP 500, semantic contradiction), falls back to `GoalInterpreter.interpret(...)`.

### 4.3 Deterministic Intent Validator (`agent/llm_intent.py`)
`DeterministicIntentValidator` validates all LLM outputs before planning:
1. **Hard Security Override:** Scans the raw user goal for external messaging keywords (`send email`, `send whatsapp`, `dispatch`, `blast`, `broadcast`). If present or if `requires_external_action` is `True`, forces `intent_type = UNSUPPORTED_EXTERNAL_ACTION` and turns off all capability flags.
2. **Ambiguity & Location Validation:** If discovery is requested without a location or search query, categorizes intent as `AMBIGUOUS`, sets `requires_clarification = True`, and attaches a `ClarificationRequest`.
3. **Known Business Entity Validation:** For research/outreach/audit intents, ensures `target_business` is present or inferable from parameters/heuristics.
4. **Contradiction Rejection:** Enforces logical constraints:
   - `requires_draft` requires `requires_outreach` and `requires_evaluation`.
   - `requires_outreach` requires `requires_opportunity_analysis`.
   - `requires_opportunity_analysis` requires `requires_research`.
   - `DISCOVER_PROSPECTS` cannot have research or outreach flags.
   - `AUDIT_ONLY` cannot have opportunity or outreach flags.

---

## 5. Fallback Order & Safety Guarantees

| Scenario | Execution Path | `intent_source` | Result |
| :--- | :--- | :--- | :--- |
| **Case A: LLM succeeds** | LLM → Validator → Planner → Executor | `"llm"` | Optimal dynamic plan executed |
| **Case B: LLM unavailable / error** | LLM fails → `GoalInterpreter` → Planner → Executor | `"deterministic_fallback"` | Robust fallback plan executed |
| **Case C: Both fail** | LLM fails → Fallback fails → Controlled failure | `"failed"` | State `FAILED`, 0 capabilities run |
| **Standalone Deterministic** | Explicit `GoalInterpreter` passed to `Agent` | `"deterministic"` | Deterministic plan executed |

### Safety Invariants
1. **Zero Registry Bypass:** The LLM cannot call `CapabilityRegistry.execute()` or bypass policy checks.
2. **Zero Tool Injection:** Any `tools` or `execution_steps` hallucinated by the model are discarded by Pydantic schema validation.
3. **External Action Lockdown:** Requests to send real messages (WhatsApp, email) are intercepted and rejected with an explicit policy message.
4. **Evaluation Gate Maintained:** AI-generated outreach plans always include `evaluate_ai_reasoning` and halt before drafting if evaluation fails.

---

## 6. Observability

`AgentState.intent_source` and `AgentFinalResponse.intent_source` record the exact mechanism used to obtain the intent:
- `"llm"`: Structured intent generated by upstream LLM and verified by validator.
- `"deterministic_fallback"`: Upstream LLM was unavailable, timed out, or invalid; successfully recovered via rule-based interpreter.
- `"deterministic"`: Agent was run in standalone rule-based mode.
- `"failed"`: Both interpreters were unable to parse the goal.

This enables production monitoring, latency profiling, and debugging without inspecting raw logs.

---

## 7. Verification & Test Suite

17 new unit tests were added in [`tests/test_agent.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_agent.py) under `TestLLMIntentInterpretation`:

1. `test_37_valid_structured_llm_intent`: Validates LLM output produces executable plan with `intent_source="llm"`.
2. `test_38_llm_intent_validation_missing_location`: Validates missing location in LLM discovery output triggers `NEEDS_CLARIFICATION`.
3. `test_39_malformed_llm_output_triggers_fallback`: Validates JSON decoding failure triggers deterministic fallback.
4. `test_40_missing_required_fields_in_llm_output`: Validates schema validation failure triggers deterministic fallback.
5. `test_41_unsupported_intent_from_llm`: Validates `UNKNOWN` intent transitions safely to `FAILED`.
6. `test_42_llm_unavailable_triggers_fallback`: Validates unconfigured LLM client immediately falls back to rule-based interpreter.
7. `test_43_llm_timeout_triggers_fallback`: Validates LLM timeout triggers fallback.
8. `test_44_llm_provider_500_triggers_fallback`: Validates HTTP 500 error triggers fallback.
9. `test_45_both_interpreters_fail_safe_failure`: Validates dual failure halts safely in `FAILED` state with 0 executions.
10. `test_46_llm_cannot_inject_capability_names`: Validates injected capabilities are dropped and not scheduled.
11. `test_47_llm_cannot_inject_execution_steps`: Validates injected execution steps array is ignored.
12. `test_48_llm_cannot_bypass_registry`: Validates plan validation rejects unregistered tools.
13. `test_49_discovery_intent_produces_discovery_first_plan`: Validates discovery step precedes analysis steps.
14. `test_50_outreach_intent_produces_evaluation_gate`: Validates evaluation failure blocks drafting.
15. `test_51_external_action_intent_remains_policy_controlled`: Validates external action requests cannot bypass safety policy.
16. `test_52_semantic_contradictions_rejected_by_validator`: Validates validator catches contradictory requirement flags.
17. `test_53_deterministic_interpreter_standalone_mode`: Validates standalone deterministic interpreter mode (`intent_source="deterministic"`).

### Complete Test Suite Status
- **Phase 1 & 2 Core Tests**: 75 passing
- **Phase 3B Capability Tests**: 13 passing
- **Phase 3C Agent Core Tests**: 20 passing
- **Phase 3D Dynamic Planning Tests**: 16 passing
- **Phase 3E LLM Intent Tests**: 17 passing
- **Total Suite**: **141 tests passing** in 0.260s (100% pass rate, 0 failures, 0 regressions).

---

## 8. Known Limitations

1. **Entity Extraction Nuance:** When multiple businesses are mentioned in a single free-form goal, the LLM currently extracts the primary `target_business` or `target_businesses` list. Orchestration currently plans single-lead pipelines.
2. **Context-Free Intent:** Intent interpretation is stateless and evaluated per request. Session-level conversational memory across multiple turns is out of scope for Phase 3E.
