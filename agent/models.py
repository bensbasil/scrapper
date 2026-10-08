"""
agent/models.py
---------------
Typed Pydantic v2 models for Agent orchestration.
Defines AgentStatus, StepStatus, ApprovalStatus, PlanStep, Plan,
ExecutionRecord, ApprovalRequest, and AgentFinalResponse.
Reuses canonical domain schemas without duplication.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

# Reuse canonical domain models directly
from schemas.business import Business
from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult


class AgentStatus(str, Enum):
    """Lifecycle statuses for the Agent task."""
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StepStatus(str, Enum):
    """Lifecycle statuses for individual plan steps."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, Enum):
    """Lifecycle statuses for human-in-the-loop approvals."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PlanStep(BaseModel):
    """
    Individual step in an agent execution plan.
    Specifies capability to call, rationale, explicit inputs, and dependencies.
    """
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(..., description="Unique identifier for this step within the plan e.g. 'step_1'")
    capability_name: str = Field(..., description="Target capability in CapabilityRegistry")
    reason: str = Field(default="", description="High-level reasoning explaining why this step is planned")
    input_parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to the capability")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Execution status of this step")
    depends_on: List[str] = Field(
        default_factory=list,
        description="List of prerequisite step_ids that must complete before this step can execute"
    )


class Plan(BaseModel):
    """
    Structured, dependency-aware plan containing ordered or dag steps.
    """
    model_config = ConfigDict(extra="ignore")

    plan_id: str = Field(default="plan_default", description="Identifier for this plan")
    workflow_name: str = Field(default="custom", description="Name of the recognized workflow pattern")
    steps: List[PlanStep] = Field(default_factory=list, description="List of plan steps")

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        """Lookup a step by step_id."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_steps_by_capability(self, capability_name: str) -> List[PlanStep]:
        """Lookup steps by capability name."""
        return [s for s in self.steps if s.capability_name == capability_name]


class ExecutionRecord(BaseModel):
    """
    Audit record tracking the execution of a capability.
    Does NOT store giant copies of raw domain objects.
    """
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(..., description="Identifier of the plan step executed")
    capability_name: str = Field(..., description="Name of the executed capability")
    status: StepStatus = Field(..., description="Outcome status")
    started_at: str = Field(..., description="ISO timestamp when execution started")
    completed_at: Optional[str] = Field(default=None, description="ISO timestamp when execution finished")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Duration in milliseconds")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")


class ApprovalRequest(BaseModel):
    """
    Audit and tracking model for human approval gates.
    """
    model_config = ConfigDict(extra="ignore")

    approval_id: str = Field(..., description="Unique approval request ID")
    task_id: str = Field(..., description="Associated Agent task ID")
    capability_name: str = Field(..., description="Capability requiring approval")
    reason: str = Field(..., description="Reason human approval is required")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Current approval status")
    created_at: str = Field(..., description="ISO timestamp when request was created")
    resolved_at: Optional[str] = Field(default=None, description="ISO timestamp when request was resolved")


class AgentFinalResponse(BaseModel):
    """
    Structured final output from an Agent execution run.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str = Field(..., description="Unique ID of the completed task")
    run_id: Optional[str] = Field(default=None, description="Unique trace run identifier")
    user_goal: str = Field(..., description="Original user goal")
    status: AgentStatus = Field(..., description="Final task status")
    completed_capabilities: List[str] = Field(default_factory=list, description="Names of successfully executed capabilities")
    prospect_context: Optional[ProspectContext] = Field(default=None, description="Compiled ProspectContext if generated")
    opportunity_analysis: Optional[OpportunityAnalysis] = Field(default=None, description="AI Opportunity analysis if generated")
    outreach_strategy: Optional[OutreachStrategy] = Field(default=None, description="AI Outreach strategy if generated")
    evaluation_result: Optional[EvaluationResult] = Field(default=None, description="AI reasoning evaluation result if run")
    outreach_draft: Optional[OutreachDraft] = Field(default=None, description="Final rendered outreach drafts if generated")
    prospects: List[Business] = Field(default_factory=list, description="Discovered candidate prospect businesses")
    prospect_set: Optional[Any] = Field(default=None, description="Discovered ProspectSet collection")
    batch_result: Optional[Any] = Field(default=None, description="ProspectBatchResult if multi-prospect batch was executed")
    qualification_summary: Optional[Dict[str, int]] = Field(default=None, description="Aggregate counts for qualification (discovered, qualified, disqualified, selected)")
    clarification_question: Optional[str] = Field(default=None, description="Clarification prompt if status is NEEDS_CLARIFICATION")
    intent_source: Optional[str] = Field(default=None, description="Source of interpreted intent: 'llm', 'deterministic_fallback', 'deterministic'")
    errors: List[str] = Field(default_factory=list, description="List of recorded errors during execution")
    summary: str = Field(default="", description="High-level textual outcome summary")
