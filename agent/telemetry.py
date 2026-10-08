"""
agent/telemetry.py
------------------
Lightweight, structured telemetry and execution tracing for the Agent layer (Phase 3F).
Provides auditability, explainability, and error classification without external infrastructure.
Does NOT store business intelligence payloads, raw HTML, secrets, or large database models.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ErrorCategory(str, Enum):
    """Structured error classifications for Agent observability."""
    INTENT_ERROR = "INTENT_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PLANNING_ERROR = "PLANNING_ERROR"
    CAPABILITY_ERROR = "CAPABILITY_ERROR"
    POLICY_ERROR = "POLICY_ERROR"
    EVALUATION_ERROR = "EVALUATION_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class StepEventStatus(str, Enum):
    """Lifecycle statuses for capability step trace events."""
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class CapabilityTraceEvent(BaseModel):
    """
    Step-level trace event recording metadata for a single capability lifecycle phase.
    Does NOT store raw business payloads, HTML, or large domain objects.
    """
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Unique run identifier")
    step_id: str = Field(..., description="Plan step identifier (e.g. 'step_audit')")
    capability_name: str = Field(..., description="Registered capability name")
    capability_classification: Optional[str] = Field(
        default=None,
        description="Policy class: READ, WRITE, or EXTERNAL_ACTION"
    )
    status: StepEventStatus = Field(..., description="Event status: STARTED, COMPLETED, FAILED, BLOCKED, SKIPPED")
    started_at: Optional[str] = Field(default=None, description="ISO timestamp when step started")
    completed_at: Optional[str] = Field(default=None, description="ISO timestamp when step completed")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Duration in milliseconds measured via monotonic clock")
    error_type: Optional[ErrorCategory] = Field(default=None, description="Categorized error classification if failed")
    error_message: Optional[str] = Field(default=None, description="Concise error explanation if failed")
    batch_id: Optional[str] = Field(default=None, description="Batch identifier if part of multi-prospect execution")
    prospect_id: Optional[str] = Field(default=None, description="Prospect/business identifier if processing a specific prospect")
    dependency_status: Dict[str, str] = Field(
        default_factory=dict,
        description="Snapshot of dependency step statuses (e.g. {'step_discover': 'COMPLETED'})"
    )


class IntentTrace(BaseModel):
    """
    Structured trace of the intent interpretation phase.
    Captures interpretation mechanism, timing, and entity presence without raw prompts.
    """
    model_config = ConfigDict(extra="ignore")

    intent_source: str = Field(..., description="Mechanism: 'llm', 'deterministic_fallback', 'deterministic', 'failed'")
    intent_type: Optional[str] = Field(default=None, description="Interpreted intent type string")
    validation_succeeded: bool = Field(default=True, description="Whether deterministic validation passed")
    clarification_required: bool = Field(default=False, description="Whether request was ambiguous")
    external_action_detected: bool = Field(default=False, description="Whether external communication was requested")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Interpretation duration in milliseconds")
    fallback_used: bool = Field(default=False, description="Whether fallback to rule-based interpreter occurred")
    provider: Optional[str] = Field(default=None, description="LLM provider name if used (e.g. 'gemini')")
    model: Optional[str] = Field(default=None, description="LLM model identifier if used")
    error: Optional[str] = Field(default=None, description="Interpretation error message if failed")


class PlanStepTrace(BaseModel):
    """Serializable metadata for a planned step."""
    model_config = ConfigDict(extra="ignore")

    step_id: str
    capability_name: str
    depends_on: List[str] = Field(default_factory=list)


class PlanTrace(BaseModel):
    """
    Structured trace of the DAG planning and validation phase.
    """
    model_config = ConfigDict(extra="ignore")

    plan_id: str = Field(..., description="Plan identifier")
    workflow_name: str = Field(default="custom", description="Workflow pattern name")
    step_count: int = Field(default=0, ge=0, description="Total number of steps in plan")
    steps: List[PlanStepTrace] = Field(default_factory=list, description="Ordered plan step metadata")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Planning duration in milliseconds")
    validation_succeeded: bool = Field(default=True, description="Whether DAG validation passed")
    validation_error: Optional[str] = Field(default=None, description="Validation error message if failed")


class AgentRunTrace(BaseModel):
    """
    Top-level, immutable audit trace representing an entire Agent task execution.
    Explains what happened, how it was interpreted, what ran, and why it stopped.
    """
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Unique run identifier")
    task_id: str = Field(..., description="Agent task identifier")
    user_goal: str = Field(..., description="Original user goal statement")
    status: str = Field(..., description="Final AgentStatus string (COMPLETED, FAILED, etc.)")
    started_at: str = Field(..., description="ISO timestamp when run started")
    completed_at: Optional[str] = Field(default=None, description="ISO timestamp when run finished")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Total run duration in milliseconds")

    # Intent and Planning Sub-traces
    intent_source: Optional[str] = Field(default=None, description="Source of intent ('llm', 'deterministic_fallback', etc.)")
    intent_type: Optional[str] = Field(default=None, description="Classified intent type")
    intent_trace: Optional[IntentTrace] = Field(default=None, description="Intent interpretation trace")
    plan_trace: Optional[PlanTrace] = Field(default=None, description="Planning trace")

    # Execution Step Events
    step_events: List[CapabilityTraceEvent] = Field(default_factory=list, description="Ordered execution step events")

    # Aggregate Counters
    plan_step_count: int = Field(default=0, ge=0, description="Total planned steps")
    executed_step_count: int = Field(default=0, ge=0, description="Successfully executed steps")
    failed_step_count: int = Field(default=0, ge=0, description="Failed steps")
    blocked_step_count: int = Field(default=0, ge=0, description="Blocked steps due to dependency failure")
    skipped_step_count: int = Field(default=0, ge=0, description="Skipped steps")

    # Observability Flags
    fallback_used: bool = Field(default=False, description="Whether fallback interpreter was utilized")
    evaluation_passed: Optional[bool] = Field(default=None, description="Evaluation gate result if evaluated")
    batch_id: Optional[str] = Field(default=None, description="Batch identifier if multi-prospect execution")
    discovered_count: Optional[int] = Field(default=None, description="Total discovered prospects count")
    qualified_count: Optional[int] = Field(default=None, description="Count of qualified prospects")
    disqualified_count: Optional[int] = Field(default=None, description="Count of disqualified prospects")
    selected_count: Optional[int] = Field(default=None, description="Count of selected prospects for deep analysis")
    qualification_duration_ms: Optional[float] = Field(default=None, description="Duration of qualification phase in ms")
    error_category: Optional[ErrorCategory] = Field(default=None, description="High-level error category if run failed")
    final_outcome: str = Field(default="", description="Human-readable outcome summary")


class AgentTelemetrySink:
    """Base interface for Agent telemetry sinks."""

    def record_run(self, trace: AgentRunTrace) -> None:
        raise NotImplementedError

    def record_step(self, event: CapabilityTraceEvent) -> None:
        raise NotImplementedError

    def get_run(self, run_id: str) -> Optional[AgentRunTrace]:
        raise NotImplementedError

    def get_runs(self) -> List[AgentRunTrace]:
        raise NotImplementedError

    def get_step_events(
        self,
        run_id: Optional[str] = None,
        prospect_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> List[CapabilityTraceEvent]:
        raise NotImplementedError


class InMemoryTelemetrySink(AgentTelemetrySink):
    """
    Lightweight, in-memory telemetry sink for local testing and inspection.
    Stores traces in memory without database or external infrastructure dependencies.
    """

    def __init__(self):
        self._runs: Dict[str, AgentRunTrace] = {}
        self._step_events: List[CapabilityTraceEvent] = []

    def record_run(self, trace: AgentRunTrace) -> None:
        self._runs[trace.run_id] = trace

    def record_step(self, event: CapabilityTraceEvent) -> None:
        self._step_events.append(event)

    def get_run(self, run_id: str) -> Optional[AgentRunTrace]:
        return self._runs.get(run_id)

    def get_runs(self) -> List[AgentRunTrace]:
        return list(self._runs.values())

    def get_step_events(
        self,
        run_id: Optional[str] = None,
        prospect_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> List[CapabilityTraceEvent]:
        events = self._step_events
        if run_id:
            events = [e for e in events if e.run_id == run_id]
        if prospect_id:
            events = [e for e in events if e.prospect_id == prospect_id]
        if batch_id:
            events = [e for e in events if e.batch_id == batch_id]
        return list(events)

    def clear(self) -> None:
        self._runs.clear()
        self._step_events.clear()
