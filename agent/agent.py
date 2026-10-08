import logging
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from agent.models import (
    AgentStatus,
    StepStatus,
    ApprovalStatus,
    AgentFinalResponse,
)
from agent.intent import GoalInterpreter, AgentIntent, IntentType
from agent.llm_intent import LLMIntentInterpreter
from agent.state import AgentState
from agent.planner import AgentPlanner, PlanValidationError
from agent.executor import AgentExecutor
from agent.policies import PolicyEnforcer, ExecutionPolicyConfig
from agent.telemetry import (
    AgentTelemetrySink,
    InMemoryTelemetrySink,
    AgentRunTrace,
    CapabilityTraceEvent,
    IntentTrace,
    ErrorCategory,
    StepEventStatus,
)
from application.capabilities.registry import CapabilityRegistry
from ai.client import LLMClient
from agent.prospects import (
    ProspectSet,
    QualifiedProspectSet,
    ProspectSelection,
    ProspectBatchResult,
    ProspectBatchExecutor,
)
from agent.qualification import (
    ProspectQualification,
    QualificationPolicy,
    DeterministicProspectQualifier,
)

logger = logging.getLogger(__name__)


class Agent:
    """
    Thin, controlled Agent orchestrator.
    Directs capability execution through CapabilityRegistry without directly
    touching infrastructure or raw domain databases.
    Observes execution and emits auditable run traces via AgentTelemetrySink.
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        planner: Optional[AgentPlanner] = None,
        policy_config: Optional[ExecutionPolicyConfig] = None,
        policy_enforcer: Optional[PolicyEnforcer] = None,
        executor: Optional[AgentExecutor] = None,
        interpreter: Optional[Any] = None,
        llm_client: Optional[LLMClient] = None,
        telemetry_sink: Optional[AgentTelemetrySink] = None,
        max_executions: int = 15,
        max_prospects_per_run: int = 15,
        batch_executor: Optional[ProspectBatchExecutor] = None,
        qualifier: Optional[DeterministicProspectQualifier] = None,
    ):
        self.registry = registry or CapabilityRegistry.default_registry()
        self.telemetry_sink = telemetry_sink or InMemoryTelemetrySink()
        self.interpreter = interpreter or LLMIntentInterpreter(llm_client=llm_client)
        self.planner = planner or AgentPlanner(registry=self.registry, interpreter=self.interpreter)
        self.policy_enforcer = policy_enforcer or PolicyEnforcer(config=policy_config)
        self.max_prospects_per_run = max_prospects_per_run
        self.qualifier = qualifier or DeterministicProspectQualifier()
        self.batch_executor = batch_executor or ProspectBatchExecutor(
            registry=self.registry,
            policy_enforcer=self.policy_enforcer,
            telemetry_sink=self.telemetry_sink,
            max_prospects_per_run=self.max_prospects_per_run,
        )
        self.executor = executor or AgentExecutor(
            registry=self.registry,
            policy_enforcer=self.policy_enforcer,
            max_executions=max_executions,
            telemetry_sink=self.telemetry_sink
        )
        if not getattr(self.executor, "telemetry_sink", None):
            self.executor.telemetry_sink = self.telemetry_sink

    def run(
        self,
        user_goal: str,
        initial_params: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> AgentState:
        """
        Executes an end-to-end task against a user goal.
        1. Initializes AgentState and telemetry run
        2. Interprets intent via LLMIntentInterpreter / GoalInterpreter
        3. Generates Plan via AgentPlanner
        4. Validates Plan dependencies and registered capabilities
        5. Progresses state machine and executes steps via AgentExecutor
        6. Synthesizes structured AgentFinalResponse and records AgentRunTrace
        """
        t_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        state = AgentState(task_id=t_id, run_id=run_id, user_goal=user_goal)
        run_start_mono = time.monotonic()
        run_started_at = datetime.utcnow().isoformat()
        logger.info(f"[Agent:{t_id}] Starting run for goal: '{user_goal}' (run_id: {run_id})")

        # 1. Interpret user intent
        res = self.interpreter.interpret(user_goal, initial_params)
        if isinstance(res, tuple):
            intent, source = res
        else:
            intent = res
            source = "deterministic"

        state.intent = intent
        state.intent_source = source

        # Check and enforce batch safety limits on requested count
        requested_limit = intent.constraints.get("limit")
        if requested_limit and requested_limit > self.max_prospects_per_run:
            logger.warning(
                f"[Agent:{t_id}] Requested {requested_limit} prospects exceeds safety limit {self.max_prospects_per_run}. Constraining."
            )
            intent.constraints["limit"] = self.max_prospects_per_run
            intent.constraints["constrained_from"] = requested_limit
            state.record_error(
                f"Requested prospect count ({requested_limit}) exceeds maximum allowed safety limit ({self.max_prospects_per_run}). Constrained to {self.max_prospects_per_run}."
            )

        # 2. Check for Ambiguities requiring clarification
        if intent.requires_clarification and intent.clarification_request:
            state.clarification_request = intent.clarification_request
            state.transition_to(
                AgentStatus.NEEDS_CLARIFICATION,
                reason=intent.clarification_request.question
            )
            self._synthesize_final_response(state)
            self._finalize_run_trace(state, run_start_mono, run_started_at)
            return state

        # 3. Check for Unsupported External Actions
        if intent.requires_external_action:
            err = "Unsupported external action: direct message dispatching/sending is blocked by safety policy."
            state.record_error(err)
            state.transition_to(AgentStatus.FAILED, reason=err)
            self._synthesize_final_response(state)
            self._finalize_run_trace(state, run_start_mono, run_started_at, error_category=ErrorCategory.POLICY_ERROR)
            return state

        # 4. Check for Unknown Workflow / Interpretation Failure
        if intent.intent_type == IntentType.UNKNOWN:
            err = (
                intent.constraints.get("error")
                or f"No deterministic workflow pattern found for goal: '{user_goal}'"
            )
            state.record_error(err)
            state.transition_to(AgentStatus.FAILED, reason=err)
            self._synthesize_final_response(state)
            self._finalize_run_trace(state, run_start_mono, run_started_at, error_category=ErrorCategory.INTENT_ERROR)
            return state

        # 5. Generate plan from intent
        try:
            plan = self.planner.plan_from_intent(intent, initial_params)
            state.plan = plan
        except Exception as e:
            err = f"Planning failed: {e}"
            state.record_error(err)
            state.transition_to(AgentStatus.FAILED, reason=err)
            self._synthesize_final_response(state)
            self._finalize_run_trace(state, run_start_mono, run_started_at, error_category=ErrorCategory.PLANNING_ERROR)
            return state

        # 6. Validate plan
        try:
            self.planner.validate_plan(plan, registry=self.registry)
        except PlanValidationError as e:
            err = f"Plan validation failed: {e}"
            state.record_error(err)
            state.transition_to(AgentStatus.FAILED, reason=err)
            self._synthesize_final_response(state)
            self._finalize_run_trace(state, run_start_mono, run_started_at, error_category=ErrorCategory.VALIDATION_ERROR)
            return state

        # 7. Transition to EXECUTING
        state.transition_to(AgentStatus.EXECUTING, reason="Plan validated; commencing execution")

        # 8. Controlled Execution Loop
        self.executor.run(state)

        # 9. Synthesize final response and trace
        self._synthesize_final_response(state)
        self._finalize_run_trace(state, run_start_mono, run_started_at)
        return state

    def approve(self, state: AgentState, approval_id: str) -> AgentState:
        """
        Grants human approval for a paused step and resumes execution.
        """
        if not state.approval_request or state.approval_request.approval_id != approval_id:
            err = f"No pending approval request found matching '{approval_id}'."
            state.record_error(err)
            return state

        if state.status != AgentStatus.WAITING_FOR_APPROVAL:
            err = f"State is not in WAITING_FOR_APPROVAL (currently {state.status.value})."
            state.record_error(err)
            return state

        state.approval_request.status = ApprovalStatus.APPROVED
        state.approval_request.resolved_at = datetime.utcnow().isoformat()
        state.transition_to(AgentStatus.EXECUTING, reason="Human approval granted")

        self.executor.run(state)
        self._synthesize_final_response(state)
        return state

    def reject(self, state: AgentState, approval_id: str, reason: str = "") -> AgentState:
        """
        Rejects human approval for a paused step and halts execution safely.
        """
        if not state.approval_request or state.approval_request.approval_id != approval_id:
            err = f"No pending approval request found matching '{approval_id}'."
            state.record_error(err)
            return state

        state.approval_request.status = ApprovalStatus.REJECTED
        state.approval_request.resolved_at = datetime.utcnow().isoformat()
        rej_msg = reason or "Human approval was rejected."
        state.record_error(f"Approval rejected: {rej_msg}")
        state.transition_to(AgentStatus.FAILED, reason=rej_msg)

        self._synthesize_final_response(state)
        return state

    def run_prospect_batch(
        self,
        prospect_set: ProspectSet,
        selection: Optional[ProspectSelection] = None,
        qualification_policy: Optional[QualificationPolicy] = None,
        qualifier: Optional[DeterministicProspectQualifier] = None,
        include_outreach: bool = False,
        task_id: Optional[str] = None
    ) -> AgentState:
        """
        Executes controlled batch analysis across a ProspectSet using ProspectBatchExecutor.
        Enforces qualification, selection, batch safety boundaries, and preserves failure isolation.
        """
        t_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        user_goal = f"Batch analysis of {len(prospect_set)} prospects in set {prospect_set.set_id}"
        state = AgentState(
            task_id=t_id,
            run_id=run_id,
            user_goal=user_goal,
            prospect_set=prospect_set,
            prospect_selection=selection
        )
        run_start_mono = time.monotonic()
        run_started_at = datetime.utcnow().isoformat()
        state.transition_to(AgentStatus.EXECUTING, reason="Starting controlled multi-prospect batch execution")

        # 1. Deterministic Qualification Stage (Phase 4B)
        qual_start = time.monotonic()
        active_qualifier = qualifier or (
            DeterministicProspectQualifier(policy=qualification_policy)
            if qualification_policy is not None else self.qualifier
        )
        qualified_set = active_qualifier.qualify_set(prospect_set)
        qual_dur_ms = (time.monotonic() - qual_start) * 1000.0

        state.qualified_prospect_set = qualified_set
        state.discovered_count = qualified_set.total_discovered
        state.qualified_count = qualified_set.qualified_count
        state.disqualified_count = qualified_set.disqualified_count

        if self.telemetry_sink:
            # Emit batch qualification trace event
            self.telemetry_sink.record_step(
                CapabilityTraceEvent(
                    run_id=run_id,
                    step_id="step_qualify",
                    capability_name="qualify_prospects",
                    capability_classification="READ",
                    status=StepEventStatus.COMPLETED,
                    started_at=datetime.utcnow().isoformat(),
                    completed_at=datetime.utcnow().isoformat(),
                    duration_ms=qual_dur_ms,
                )
            )
            # Emit per-prospect qualification trace events
            for q in qualified_set.qualifications.values():
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=run_id,
                        step_id=f"qualify_{q.prospect_id}",
                        capability_name="qualify_prospect",
                        capability_classification="READ",
                        status=StepEventStatus.COMPLETED if q.qualified else StepEventStatus.SKIPPED,
                        prospect_id=q.prospect_id,
                        started_at=datetime.utcnow().isoformat(),
                        completed_at=datetime.utcnow().isoformat(),
                        duration_ms=0.0,
                    )
                )

        # 2. Candidate Selection Stage (from QualifiedProspectSet)
        if selection is None:
            selection = ProspectSelection(
                max_prospects=min(len(qualified_set.qualified_prospects) if qualified_set.qualified_prospects else 1, self.max_prospects_per_run)
            )

        state.prospect_selection = selection

        # 3. Controlled Batch Execution across Qualified Prospects
        batch_result = self.batch_executor.execute_batch(
            prospect_set=qualified_set,
            selection=selection,
            include_outreach=include_outreach,
            run_id=run_id,
            task_id=t_id
        )
        state.batch_result = batch_result
        state.selected_count = batch_result.selected_count

        # Populate state prospects from selected candidates
        state.prospects = [r.business for r in batch_result.results]

        # Populate bounded mapping of prospect_id -> ProspectContext for multi-prospect runs
        for r in batch_result.results:
            if r.prospect_context:
                state.prospect_contexts[r.prospect_id] = r.prospect_context

        # Top ranked candidate populates primary state domain models for explainability
        if batch_result.results:
            top = batch_result.ranked_results()[0]
            if top.prospect_context:
                state.prospect_context = top.prospect_context
            if top.opportunity_analysis:
                state.opportunity_analysis = top.opportunity_analysis
            if top.outreach_strategy:
                state.outreach_strategy = top.outreach_strategy
            if top.evaluation_result:
                state.evaluation_result = top.evaluation_result
            if top.outreach_draft:
                state.outreach_draft = top.outreach_draft

        if batch_result.completed_count > 0:
            state.transition_to(
                AgentStatus.COMPLETED,
                reason=f"Batch execution completed ({batch_result.completed_count}/{batch_result.selected_count} successful)"
            )
        elif batch_result.selected_count == 0:
            state.transition_to(
                AgentStatus.COMPLETED,
                reason="Batch execution completed: zero prospects qualified for deep analysis"
            )
        else:
            state.transition_to(
                AgentStatus.FAILED,
                reason="All prospects in batch failed execution"
            )

        self._synthesize_final_response(state)
        self._finalize_run_trace(state, run_start_mono, run_started_at, qualification_dur_ms=qual_dur_ms)
        return state

    def _synthesize_final_response(self, state: AgentState) -> None:
        """
        Generates a typed final response envelope summarizing task results.
        """
        completed_caps: List[str] = [
            rec.capability_name
            for rec in state.completed_steps
            if rec.status == StepStatus.COMPLETED
        ]

        if state.batch_result:
            summary = (
                f"Multi-prospect batch execution completed: {state.batch_result.completed_count}/"
                f"{state.batch_result.selected_count} prospects successfully analyzed."
            )
        elif state.status == AgentStatus.COMPLETED:
            summary = (
                f"Successfully completed task with {len(completed_caps)} capabilities. "
                f"Generated evidence context, AI opportunity analysis, and consultative outreach."
            )
        elif state.status == AgentStatus.NEEDS_CLARIFICATION:
            q = state.clarification_request.question if state.clarification_request else "Missing information."
            summary = f"Execution paused requiring clarification: {q}"
        elif state.status == AgentStatus.WAITING_FOR_APPROVAL:
            appr = state.approval_request
            cap = appr.capability_name if appr else "unknown"
            summary = f"Execution paused awaiting human approval for capability '{cap}'."
        elif state.status == AgentStatus.FAILED:
            primary_error = state.errors[0] if state.errors else "Unknown failure"
            summary = f"Task halted with status FAILED. Primary issue: {primary_error}"
        else:
            summary = f"Task in status {state.status.value}."

        qual_summary = None
        if state.discovered_count > 0 or (state.batch_result and state.batch_result.discovered_count is not None):
            qual_summary = {
                "discovered": state.discovered_count or (state.batch_result.discovered_count if state.batch_result else 0),
                "qualified": state.qualified_count if state.qualified_prospect_set else (state.batch_result.qualified_count if state.batch_result else 0),
                "disqualified": state.disqualified_count if state.qualified_prospect_set else (state.batch_result.disqualified_count if state.batch_result else 0),
                "selected": state.selected_count or (state.batch_result.selected_count if state.batch_result else 0),
            }

        state.final_response = AgentFinalResponse(
            task_id=state.task_id,
            run_id=state.run_id,
            user_goal=state.user_goal,
            status=state.status,
            completed_capabilities=completed_caps,
            prospect_context=state.prospect_context,
            opportunity_analysis=state.opportunity_analysis,
            outreach_strategy=state.outreach_strategy,
            evaluation_result=state.evaluation_result,
            outreach_draft=state.outreach_draft,
            prospects=state.prospects,
            prospect_set=state.prospect_set,
            batch_result=state.batch_result,
            qualification_summary=qual_summary,
            clarification_question=state.clarification_request.question if state.clarification_request else None,
            intent_source=state.intent_source,
            errors=state.errors,
            summary=summary
        )

    def _finalize_run_trace(
        self,
        state: AgentState,
        start_mono: float,
        started_at: str,
        error_category: Optional[ErrorCategory] = None,
        qualification_dur_ms: Optional[float] = None,
    ) -> None:
        """
        Compiles and records the immutable AgentRunTrace to telemetry sink.
        Does NOT store large payloads or secrets.
        """
        duration_ms = (time.monotonic() - start_mono) * 1000.0
        completed_at = datetime.utcnow().isoformat()

        plan_steps = state.plan.steps if state.plan else []
        plan_step_count = len(plan_steps)
        executed_count = sum(1 for s in plan_steps if s.status == StepStatus.COMPLETED)
        failed_count = sum(1 for s in plan_steps if s.status == StepStatus.FAILED)
        blocked_count = sum(1 for s in plan_steps if s.status == StepStatus.BLOCKED)
        skipped_count = sum(1 for s in plan_steps if s.status == StepStatus.SKIPPED)

        step_events = self.telemetry_sink.get_step_events(state.run_id)
        eval_passed = state.evaluation_result.passed if state.evaluation_result else None

        intent_trace = getattr(self.interpreter, "last_trace", None)
        if not intent_trace and state.intent:
            intent_trace = IntentTrace(
                intent_source=state.intent_source or "deterministic",
                intent_type=state.intent.intent_type.value if state.intent.intent_type else None,
                validation_succeeded=True,
                clarification_required=state.intent.requires_clarification,
                external_action_detected=state.intent.requires_external_action,
                duration_ms=0.0,
                fallback_used=(state.intent_source == "deterministic_fallback")
            )

        plan_trace = getattr(self.planner, "last_trace", None)

        fallback_used = False
        if intent_trace and intent_trace.fallback_used:
            fallback_used = True
        elif state.intent_source == "deterministic_fallback":
            fallback_used = True

        err_cat = error_category
        if not err_cat and state.status == AgentStatus.FAILED:
            for ev in step_events:
                if ev.status == StepEventStatus.FAILED and ev.error_type:
                    err_cat = ev.error_type
                    break
            if not err_cat:
                if any("Unsupported external action" in e for e in state.errors):
                    err_cat = ErrorCategory.POLICY_ERROR
                elif any("No deterministic workflow pattern" in e for e in state.errors):
                    err_cat = ErrorCategory.INTENT_ERROR
                elif any("Plan validation failed" in e for e in state.errors):
                    err_cat = ErrorCategory.VALIDATION_ERROR
                elif any("Planning failed" in e for e in state.errors):
                    err_cat = ErrorCategory.PLANNING_ERROR
                else:
                    err_cat = ErrorCategory.SYSTEM_ERROR

        batch_id = state.batch_result.batch_id if state.batch_result else None
        disc_cnt = state.discovered_count if state.discovered_count > 0 else (state.batch_result.discovered_count if state.batch_result else None)
        qual_cnt = state.qualified_count if state.discovered_count > 0 else (state.batch_result.qualified_count if state.batch_result else None)
        disq_cnt = state.disqualified_count if state.discovered_count > 0 else (state.batch_result.disqualified_count if state.batch_result else None)
        sel_cnt = state.selected_count if state.selected_count > 0 else (state.batch_result.selected_count if state.batch_result else None)

        run_trace = AgentRunTrace(
            run_id=state.run_id or state.task_id,
            task_id=state.task_id,
            user_goal=state.user_goal,
            batch_id=batch_id,
            status=state.status.value,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            intent_source=state.intent_source,
            intent_type=state.intent.intent_type.value if state.intent and state.intent.intent_type else None,
            intent_trace=intent_trace,
            plan_trace=plan_trace,
            step_events=step_events,
            plan_step_count=plan_step_count,
            executed_step_count=executed_count,
            failed_step_count=failed_count,
            blocked_step_count=blocked_count,
            skipped_step_count=skipped_count,
            fallback_used=fallback_used,
            evaluation_passed=eval_passed,
            discovered_count=disc_cnt,
            qualified_count=qual_cnt,
            disqualified_count=disq_cnt,
            selected_count=sel_cnt,
            qualification_duration_ms=qualification_dur_ms,
            error_category=err_cat,
            final_outcome=state.final_response.summary if state.final_response else ""
        )

        state.trace = run_trace
        self.telemetry_sink.record_run(run_trace)
