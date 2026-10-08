"""
agent/executor.py
-----------------
Controlled execution engine for the Agent orchestration layer.
Executes plan steps through the CapabilityRegistry, enforces safety policies,
tracks dependencies, hydrates contextual inputs, enforces evaluation gates,
and respects hard execution safety limits.
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from agent.models import (
    StepStatus,
    AgentStatus,
    PlanStep,
    ExecutionRecord,
    ApprovalRequest,
    ApprovalStatus,
)
from agent.state import AgentState
from agent.policies import PolicyEnforcer, ExecutionPolicyConfig
from agent.telemetry import (
    CapabilityTraceEvent,
    StepEventStatus,
    ErrorCategory,
    AgentTelemetrySink,
)
from application.capabilities.registry import CapabilityRegistry
from application.contracts.outputs import DiscoverProspectsOutput
from agent.prospects import ProspectSet
from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult

logger = logging.getLogger(__name__)


class AgentExecutor:
    """
    Execution controller that executes plan steps strictly through CapabilityRegistry.
    Never interacts directly with raw databases, browser instances, or sockets.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        policy_enforcer: Optional[PolicyEnforcer] = None,
        max_executions: int = 15,
        telemetry_sink: Optional[AgentTelemetrySink] = None,
    ):
        self.registry = registry
        self.policy_enforcer = policy_enforcer or PolicyEnforcer()
        self.max_executions = max_executions
        self.telemetry_sink = telemetry_sink

    def run(self, state: AgentState) -> AgentState:
        """
        Main execution loop. Progresses eligible plan steps until completion,
        approval pause, execution limit, or failure.
        """
        if state.status != AgentStatus.EXECUTING:
            logger.warning(
                f"[AgentExecutor:{state.task_id}] Cannot execute state with status {state.status.value}"
            )
            return state

        if not state.plan or not state.plan.steps:
            state.record_error("Plan is empty; nothing to execute.")
            state.transition_to(AgentStatus.FAILED, reason="Empty plan")
            return state

        step_map: Dict[str, PlanStep] = {s.step_id: s for s in state.plan.steps}

        while True:
            # 1. Enforce hard execution safety limit
            if state.execution_count >= self.max_executions:
                err = f"Safety execution limit exceeded: maximum {self.max_executions} executions reached."
                state.record_error(err)
                state.transition_to(AgentStatus.FAILED, reason="Execution limit reached")
                return state

            # 2. Find eligible steps
            eligible_step = self._find_next_eligible_step(state, step_map)

            # If no step can be executed right now
            if eligible_step is None:
                # Check whether remaining steps are blocked/failed
                has_pending = any(s.status == StepStatus.PENDING for s in state.plan.steps)
                has_failed_or_blocked = any(
                    s.status in (StepStatus.FAILED, StepStatus.BLOCKED)
                    for s in state.plan.steps
                )

                if has_failed_or_blocked:
                    state.transition_to(
                        AgentStatus.FAILED,
                        reason="Workflow halted due to failed or blocked steps."
                    )
                elif not has_pending:
                    state.transition_to(
                        AgentStatus.COMPLETED,
                        reason="All planned steps completed successfully."
                    )
                break

            # 3. Process the selected eligible step
            should_pause = self._execute_step(state, eligible_step)
            if should_pause:
                # Execution paused (e.g. for approval or after failure)
                break

        return state

    def _find_next_eligible_step(
        self,
        state: AgentState,
        step_map: Dict[str, PlanStep]
    ) -> Optional[PlanStep]:
        """
        Identifies the next step whose dependencies are satisfied.
        Cascades BLOCKED status if any prerequisite failed.
        """
        for step in state.plan.steps:
            if step.status != StepStatus.PENDING:
                continue

            # Check all dependencies
            deps_satisfied = True
            for dep_id in step.depends_on:
                dep_step = step_map.get(dep_id)
                if not dep_step:
                    step.status = StepStatus.BLOCKED
                    deps_satisfied = False
                    break

                if dep_step.status in (StepStatus.FAILED, StepStatus.BLOCKED, StepStatus.SKIPPED):
                    step.status = StepStatus.BLOCKED
                    logger.warning(
                        f"[AgentExecutor:{state.task_id}] Step '{step.step_id}' BLOCKED because dependency '{dep_id}' is {dep_step.status.value}."
                    )
                    deps_satisfied = False
                    break

                if dep_step.status != StepStatus.COMPLETED:
                    # Still pending/running
                    deps_satisfied = False
                    break

            if deps_satisfied:
                return step

        return None

    def _execute_step(self, state: AgentState, step: PlanStep) -> bool:
        """
        Executes a single eligible step.
        Returns True if execution loop should pause/terminate, False to continue loop.
        """
        step.status = StepStatus.RUNNING
        run_id = getattr(state, "run_id", None) or state.task_id
        start_mono = time.monotonic()
        start_time = datetime.utcnow()

        # 1. Lookup capability in registry
        descriptor = self.registry.get(step.capability_name)
        classification = descriptor.policy_class.value if descriptor else None

        # Telemetry: Record STARTED event
        if self.telemetry_sink:
            step_map = {s.step_id: s for s in state.plan.steps} if state.plan else {}
            dep_status = {
                dep: (step_map[dep].status.value if dep in step_map else "UNKNOWN")
                for dep in step.depends_on
            }
            self.telemetry_sink.record_step(
                CapabilityTraceEvent(
                    run_id=run_id,
                    step_id=step.step_id,
                    capability_name=step.capability_name,
                    capability_classification=classification,
                    status=StepEventStatus.STARTED,
                    started_at=start_time.isoformat(),
                    dependency_status=dep_status,
                )
            )

        if descriptor is None:
            err = f"Unknown capability '{step.capability_name}' in step '{step.step_id}'."
            step.status = StepStatus.FAILED
            state.record_error(err)
            if self.telemetry_sink:
                duration_ms = (time.monotonic() - start_mono) * 1000.0
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=run_id,
                        step_id=step.step_id,
                        capability_name=step.capability_name,
                        capability_classification=None,
                        status=StepEventStatus.FAILED,
                        started_at=start_time.isoformat(),
                        completed_at=datetime.utcnow().isoformat(),
                        duration_ms=duration_ms,
                        error_type=ErrorCategory.CAPABILITY_ERROR,
                        error_message=err,
                    )
                )
            state.transition_to(AgentStatus.FAILED, reason=f"Unknown capability: {step.capability_name}")
            return True

        # 2. Check safety policy
        policy_eval = self.policy_enforcer.evaluate(descriptor)
        if policy_eval.requires_approval:
            approval_id = f"appr_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{step.step_id}"
            state.approval_request = ApprovalRequest(
                approval_id=approval_id,
                task_id=state.task_id,
                capability_name=step.capability_name,
                reason=policy_eval.reason,
                status=ApprovalStatus.PENDING,
                created_at=datetime.utcnow().isoformat()
            )
            step.status = StepStatus.PENDING
            state.transition_to(
                AgentStatus.WAITING_FOR_APPROVAL,
                reason=f"Human approval required for {step.capability_name}"
            )
            logger.info(f"[AgentExecutor:{state.task_id}] Pausing for human approval on '{step.capability_name}'")
            return True

        if not policy_eval.is_allowed:
            err = f"Policy violation on '{step.capability_name}': {policy_eval.reason}"
            step.status = StepStatus.FAILED
            state.record_error(err)
            if self.telemetry_sink:
                duration_ms = (time.monotonic() - start_mono) * 1000.0
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=run_id,
                        step_id=step.step_id,
                        capability_name=step.capability_name,
                        capability_classification=classification,
                        status=StepEventStatus.FAILED,
                        started_at=start_time.isoformat(),
                        completed_at=datetime.utcnow().isoformat(),
                        duration_ms=duration_ms,
                        error_type=ErrorCategory.POLICY_ERROR,
                        error_message=err,
                    )
                )
            state.transition_to(AgentStatus.FAILED, reason="Policy violation")
            return True

        # 3. Hydrate parameters dynamically from state
        hydrated_params = self._hydrate_parameters(state, step)

        # 4. Invoke capability through registry
        state.execution_count += 1
        call_start_mono = time.monotonic()
        result = self.registry.execute(step.capability_name, hydrated_params)
        end_time = datetime.utcnow()
        duration_ms = (time.monotonic() - call_start_mono) * 1000.0

        # 5. Create audit execution record
        record = ExecutionRecord(
            step_id=step.step_id,
            capability_name=step.capability_name,
            status=StepStatus.COMPLETED if result.success else StepStatus.FAILED,
            started_at=start_time.isoformat(),
            completed_at=end_time.isoformat(),
            duration_ms=duration_ms,
            error=result.error
        )
        state.completed_steps.append(record)

        # 6. Handle failure
        if not result.success:
            step.status = StepStatus.FAILED
            err = f"Capability '{step.capability_name}' execution failed: {result.error}"
            state.record_error(err)
            if self.telemetry_sink:
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=run_id,
                        step_id=step.step_id,
                        capability_name=step.capability_name,
                        capability_classification=classification,
                        status=StepEventStatus.FAILED,
                        started_at=start_time.isoformat(),
                        completed_at=end_time.isoformat(),
                        duration_ms=duration_ms,
                        error_type=ErrorCategory.CAPABILITY_ERROR,
                        error_message=result.error or err,
                    )
                )
            self._cascade_blocked(state, step.step_id)
            state.transition_to(AgentStatus.FAILED, reason=f"Capability failure: {step.capability_name}")
            return True

        # 7. Update state with successful output
        step.status = StepStatus.COMPLETED
        state.capability_results[step.capability_name] = result.data
        self._update_state_models(state, result.data)

        if self.telemetry_sink:
            self.telemetry_sink.record_step(
                CapabilityTraceEvent(
                    run_id=run_id,
                    step_id=step.step_id,
                    capability_name=step.capability_name,
                    capability_classification=classification,
                    status=StepEventStatus.COMPLETED,
                    started_at=start_time.isoformat(),
                    completed_at=end_time.isoformat(),
                    duration_ms=duration_ms,
                )
            )

        # 8. Evaluation Gate Check
        if step.capability_name == "evaluate_ai_reasoning" and isinstance(result.data, EvaluationResult):
            if not result.data.passed:
                issue_text = "; ".join(result.data.issues or ["Evaluation score failed quality gate"])
                gate_err = f"Evaluation gate failed: {issue_text}"
                state.record_error(gate_err)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=run_id,
                            step_id=step.step_id,
                            capability_name=step.capability_name,
                            capability_classification=classification,
                            status=StepEventStatus.FAILED,
                            started_at=start_time.isoformat(),
                            completed_at=datetime.utcnow().isoformat(),
                            duration_ms=duration_ms,
                            error_type=ErrorCategory.EVALUATION_ERROR,
                            error_message=gate_err,
                        )
                    )
                self._cascade_blocked(state, step.step_id)
                state.transition_to(AgentStatus.FAILED, reason="Evaluation gate failed")
                return True

        return False

    def _cascade_blocked(self, state: AgentState, failed_step_id: str) -> None:
        """Marks all steps transitively dependent on failed_step_id as BLOCKED."""
        if not state.plan:
            return
        run_id = getattr(state, "run_id", None) or state.task_id
        for s in state.plan.steps:
            if failed_step_id in s.depends_on and s.status == StepStatus.PENDING:
                s.status = StepStatus.BLOCKED
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=run_id,
                            step_id=s.step_id,
                            capability_name=s.capability_name,
                            capability_classification=None,
                            status=StepEventStatus.BLOCKED,
                            started_at=datetime.utcnow().isoformat(),
                            completed_at=datetime.utcnow().isoformat(),
                            duration_ms=0.0,
                            error_type=None,
                            error_message=f"Prerequisite step '{failed_step_id}' failed or was blocked",
                            dependency_status={failed_step_id: "FAILED"}
                        )
                    )
                self._cascade_blocked(state, s.step_id)

    def _hydrate_parameters(self, state: AgentState, step: PlanStep) -> Dict[str, Any]:
        """
        Hydrates capability arguments using state context and previous step results.
        """
        params = dict(step.input_parameters)
        cap = step.capability_name

        # If discovery has populated prospects in state, hydrate default prospect data
        if state.prospects:
            first_p = state.prospects[0]
            if "business_name" not in params or params.get("business_name") in ("Target Prospect", ""):
                params["business_name"] = first_p.business_name
            if "website_url" not in params or not params.get("website_url") or params.get("website_url") == "https://example.com":
                params["website_url"] = first_p.website or ""
            if "category" not in params or params.get("category") == "Local Business":
                params["category"] = first_p.category or "Local Business"
            rating = getattr(first_p, "rating", getattr(first_p, "google_rating", None))
            if "rating" not in params and rating is not None:
                params["rating"] = rating
            review_count = getattr(first_p, "review_count", None)
            if "review_count" not in params and review_count is not None:
                params["review_count"] = review_count

        if cap == "assemble_prospect_context":
            if state.prospects:
                first_p = state.prospects[0]
                b_dict = params.get("business_data", {})
                if not b_dict or b_dict.get("business_name") == "Target Prospect":
                    params["business_data"] = first_p.model_dump() if hasattr(first_p, "model_dump") else first_p.__dict__

            if "audit_website_tech" in state.capability_results and "analysis_data" not in params:
                audit_out = state.capability_results["audit_website_tech"]
                params["analysis_data"] = audit_out.model_dump() if hasattr(audit_out, "model_dump") else audit_out
            if "enrich_leadership_social" in state.capability_results:
                enrich_out = state.capability_results["enrich_leadership_social"]
                if hasattr(enrich_out, "validated_emails") and "email_data" not in params:
                    params["email_data"] = {"emails": [e.email for e in enrich_out.validated_emails]}
                if hasattr(enrich_out, "decision_makers") and "decision_data" not in params:
                    params["decision_data"] = {
                        "decision_makers": [
                            d.model_dump() if hasattr(d, "model_dump") else d
                            for d in enrich_out.decision_makers
                        ]
                    }
            if "mine_business_intelligence" in state.capability_results and "review_mine_data" not in params:
                intel_out = state.capability_results["mine_business_intelligence"]
                params["review_mine_data"] = intel_out.model_dump() if hasattr(intel_out, "model_dump") else intel_out
            if "calculate_health_and_scores" in state.capability_results and "health_data" not in params:
                score_out = state.capability_results["calculate_health_and_scores"]
                params["health_data"] = score_out.model_dump() if hasattr(score_out, "model_dump") else score_out

        elif cap == "synthesize_opportunity_analysis":
            if "context" not in params and state.prospect_context is not None:
                params["context"] = state.prospect_context

        elif cap == "formulate_outreach_strategy":
            if "context" not in params and state.prospect_context is not None:
                params["context"] = state.prospect_context
            if "opportunity_analysis" not in params and state.opportunity_analysis is not None:
                params["opportunity_analysis"] = state.opportunity_analysis

        elif cap == "evaluate_ai_reasoning":
            if "context" not in params and state.prospect_context is not None:
                params["context"] = state.prospect_context
            if "opportunity_analysis" not in params and state.opportunity_analysis is not None:
                params["opportunity_analysis"] = state.opportunity_analysis
            if "outreach_strategy" not in params and state.outreach_strategy is not None:
                params["outreach_strategy"] = state.outreach_strategy

        elif cap == "render_outreach_drafts":
            if "context" not in params and state.prospect_context is not None:
                params["context"] = state.prospect_context
            if "outreach_strategy" not in params and state.outreach_strategy is not None:
                params["outreach_strategy"] = state.outreach_strategy

        return params

    def _update_state_models(self, state: AgentState, data: Any) -> None:
        """Maps typed capability outputs directly to AgentState attributes."""
        if isinstance(data, DiscoverProspectsOutput):
            state.prospects = data.businesses
            loc = state.intent.location if state.intent else None
            state.prospect_set = ProspectSet.from_discovery_output(data, location=loc)
        elif isinstance(data, ProspectContext):
            state.prospect_context = data
            if data.business and data.business.business_name:
                state.prospect_contexts[data.business.business_name] = data
        elif isinstance(data, OpportunityAnalysis):
            state.opportunity_analysis = data
        elif isinstance(data, OutreachStrategy):
            state.outreach_strategy = data
        elif isinstance(data, EvaluationResult):
            state.evaluation_result = data
        elif isinstance(data, OutreachDraft):
            state.outreach_draft = data
