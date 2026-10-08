"""
agent/state.py
--------------
AgentState tracking and explicit state machine transitions.
Ensures valid lifecycle progression and prevents arbitrary state mutation.
"""

import logging
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, ConfigDict, Field

from agent.models import (
    AgentStatus,
    Plan,
    ExecutionRecord,
    ApprovalRequest,
    AgentFinalResponse,
)
from agent.intent import AgentIntent, ClarificationRequest
from schemas.business import Business
from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult

logger = logging.getLogger(__name__)


class InvalidStateTransitionError(Exception):
    """Raised when an illegal Agent state transition is attempted."""
    pass


VALID_TRANSITIONS: Dict[AgentStatus, Set[AgentStatus]] = {
    AgentStatus.PLANNING: {
        AgentStatus.EXECUTING,
        AgentStatus.NEEDS_CLARIFICATION,
        AgentStatus.FAILED,
    },
    AgentStatus.NEEDS_CLARIFICATION: {
        AgentStatus.PLANNING,
        AgentStatus.FAILED,
    },
    AgentStatus.EXECUTING: {
        AgentStatus.WAITING_FOR_APPROVAL,
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
    },
    AgentStatus.WAITING_FOR_APPROVAL: {AgentStatus.EXECUTING, AgentStatus.FAILED},
    AgentStatus.COMPLETED: set(),
    AgentStatus.FAILED: set(),
}


class AgentState(BaseModel):
    """
    Typed, explainable task state for Agent orchestration.
    Maintains intermediate domain models, plan execution progress,
    audit records, and safety counters.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str = Field(..., description="Unique task identifier")
    run_id: Optional[str] = Field(default=None, description="Unique telemetry run identifier")
    user_goal: str = Field(..., description="High-level user request or intent")
    status: AgentStatus = Field(default=AgentStatus.PLANNING, description="Current lifecycle state")
    plan: Optional[Plan] = Field(default=None, description="Structured execution plan")
    trace: Optional[Any] = Field(default=None, description="AgentRunTrace immutable execution history")
    current_step_index: int = Field(default=0, ge=0, description="Index of currently running or next step")
    completed_steps: List[ExecutionRecord] = Field(default_factory=list, description="Historical audit records")
    capability_results: Dict[str, Any] = Field(default_factory=dict, description="Raw results by capability name")

    # Typed Intermediate Domain Models (reusing canonical schemas)
    prospect_context: Optional[ProspectContext] = Field(default=None, description="Compiled ProspectContext for primary/single prospect")
    prospect_contexts: Dict[str, ProspectContext] = Field(default_factory=dict, description="Bounded mapping of prospect_id -> ProspectContext for multi-prospect runs")
    opportunity_analysis: Optional[OpportunityAnalysis] = Field(default=None, description="Structured OpportunityAnalysis")
    outreach_strategy: Optional[OutreachStrategy] = Field(default=None, description="Structured OutreachStrategy")
    evaluation_result: Optional[EvaluationResult] = Field(default=None, description="EvaluationResult verifying reasoning")
    outreach_draft: Optional[OutreachDraft] = Field(default=None, description="Rendered cold outreach drafts")

    # Human Approval & Error Tracking
    intent: Optional[AgentIntent] = Field(default=None, description="Interpreted user intent")
    intent_source: Optional[str] = Field(default=None, description="Source of interpreted intent: 'llm', 'deterministic_fallback', 'deterministic'")
    clarification_request: Optional[ClarificationRequest] = Field(default=None, description="Active clarification request if paused")
    prospects: List[Business] = Field(default_factory=list, description="Discovered candidate prospect businesses")
    prospect_set: Optional[Any] = Field(default=None, description="Discovered ProspectSet collection")
    qualified_prospect_set: Optional[Any] = Field(default=None, description="QualifiedProspectSet partitioned collection")
    prospect_selection: Optional[Any] = Field(default=None, description="Active ProspectSelection criteria")
    batch_result: Optional[Any] = Field(default=None, description="ProspectBatchResult from multi-prospect run")
    discovered_count: int = Field(default=0, ge=0, description="Total discovered prospects count")
    qualified_count: int = Field(default=0, ge=0, description="Count of qualified prospects")
    disqualified_count: int = Field(default=0, ge=0, description="Count of disqualified prospects")
    selected_count: int = Field(default=0, ge=0, description="Count of selected prospects for deep analysis")
    approval_request: Optional[ApprovalRequest] = Field(default=None, description="Active approval request if paused")
    errors: List[str] = Field(default_factory=list, description="Logged execution or planning errors")
    final_response: Optional[AgentFinalResponse] = Field(default=None, description="Synthesized final response")

    # Safety limits
    execution_count: int = Field(default=0, ge=0, description="Number of capability executions invoked")

    def transition_to(self, new_status: AgentStatus, reason: str = "") -> None:
        """
        Transitions the agent to a new status with validation against allowed state transitions.
        Raises InvalidStateTransitionError if the transition is illegal.
        """
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            err_msg = (
                f"Illegal state transition from {self.status.value} to {new_status.value}."
                + (f" Reason: {reason}" if reason else "")
            )
            logger.error(f"[AgentState:{self.task_id}] {err_msg}")
            raise InvalidStateTransitionError(err_msg)

        logger.info(
            f"[AgentState:{self.task_id}] State changed: {self.status.value} -> {new_status.value}"
            + (f" ({reason})" if reason else "")
        )
        self.status = new_status

    def record_error(self, message: str) -> None:
        """Logs an error message into the state."""
        self.errors.append(message)
        logger.error(f"[AgentState:{self.task_id}] {message}")
