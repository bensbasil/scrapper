"""
schemas/api.py
--------------
Pydantic contracts for external Agent API requests and responses (Phase 4E).
Defines clean, typed API boundaries without exposing raw internal database records,
secrets, raw HTML, or prompt traces.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult


class AgentExecutionRequest(BaseModel):
    """
    Request model for submitting an autonomous goal to the agent.
    Strictly forbids client-injected capability names, plans, or policy overrides.
    """
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=3, max_length=1000, description="Natural language user goal or request")
    limit: Optional[int] = Field(None, ge=1, le=50, description="Optional maximum candidate prospects count (clamped to safety ceiling of 15)")
    business_name: Optional[str] = Field(None, max_length=200, description="Optional target business name")
    website_url: Optional[str] = Field(None, max_length=500, description="Optional target business website URL")
    location: Optional[str] = Field(None, max_length=150, description="Optional target location")
    category: Optional[str] = Field(None, max_length=100, description="Optional industry or category")


class AgentExecutionResponse(BaseModel):
    """
    Structured outcome returned by the Agent execution API.
    Never exposes internal database records, secrets, raw prompts, or HTML.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    task_id: str = Field(..., description="Unique task identifier")
    run_id: Optional[str] = Field(default=None, description="Unique telemetry run identifier")
    user_goal: str = Field(..., description="Original user goal")
    status: str = Field(..., description="Task lifecycle status: COMPLETED, FAILED, NEEDS_CLARIFICATION, WAITING_FOR_APPROVAL")
    completed_capabilities: List[str] = Field(default_factory=list, description="Names of executed capabilities")
    summary: str = Field(default="", description="High-level human-readable outcome summary")

    # Clarification handling
    clarification_question: Optional[str] = Field(default=None, description="Targeted question if status is NEEDS_CLARIFICATION")
    missing_information: List[str] = Field(default_factory=list, description="Missing parameters required to proceed")

    # Canonical AI / reasoning artifacts
    prospect_context: Optional[ProspectContext] = Field(default=None, description="Canonical ProspectContext")
    opportunity_analysis: Optional[OpportunityAnalysis] = Field(default=None, description="Synthesized AI OpportunityAnalysis")
    outreach_strategy: Optional[OutreachStrategy] = Field(default=None, description="Synthesized AI OutreachStrategy")
    evaluation_result: Optional[EvaluationResult] = Field(default=None, description="Deterministic EvaluationResult")
    outreach_draft: Optional[OutreachDraft] = Field(default=None, description="Rendered cold outreach copy")

    # Multi-prospect discovery & qualification summaries
    prospects_count: int = Field(default=0, ge=0, description="Number of discovered prospects")
    qualification_summary: Optional[Dict[str, int]] = Field(default=None, description="Qualification breakdown (discovered, qualified, disqualified, selected)")
    batch_summary: Optional[Dict[str, Any]] = Field(default=None, description="Batch execution statistics if multi-prospect batch was run")

    errors: List[str] = Field(default_factory=list, description="List of non-sensitive errors encountered")

    @classmethod
    def from_state(cls, state: Any) -> "AgentExecutionResponse":
        """Factory method constructing an API response from an AgentState."""
        final_resp = getattr(state, "final_response", None)
        completed_caps = []
        if getattr(state, "completed_steps", None):
            completed_caps = [
                rec.capability_name for rec in state.completed_steps
                if getattr(rec, "status", None) and rec.status.value == "COMPLETED"
            ]
        elif final_resp and getattr(final_resp, "completed_capabilities", None):
            completed_caps = list(final_resp.completed_capabilities)

        clar_q = getattr(state, "clarification_request", None)
        missing_info = clar_q.missing_information if clar_q else []
        if not clar_q and final_resp and getattr(final_resp, "clarification_question", None):
            clar_question_text = final_resp.clarification_question
        else:
            clar_question_text = clar_q.question if clar_q else None

        batch_sum = None
        if getattr(state, "batch_result", None) and state.batch_result:
            br = state.batch_result
            batch_sum = {
                "batch_id": getattr(br, "batch_id", ""),
                "selected_count": getattr(br, "selected_count", 0),
                "completed_count": getattr(br, "completed_count", 0),
                "failed_count": getattr(br, "failed_count", 0),
                "duration_ms": getattr(br, "duration_ms", 0.0),
            }

        summary_text = final_resp.summary if final_resp else ""
        if not summary_text:
            if clar_question_text:
                summary_text = f"Goal clarification needed: {clar_question_text}"
            elif getattr(state, "errors", None):
                summary_text = f"Execution failed: {state.errors[0]}"
            elif getattr(state, "status", None) and getattr(state.status, "value", str(state.status)) == "COMPLETED":
                summary_text = "Goal executed successfully."

        qual_summary = getattr(state, "qualification_summary", None)
        if not qual_summary and final_resp and getattr(final_resp, "qualification_summary", None):
            qual_summary = final_resp.qualification_summary
        if not qual_summary and (getattr(state, "discovered_count", 0) > 0 or getattr(state, "qualified_count", 0) > 0):
            qual_summary = {
                "discovered": getattr(state, "discovered_count", 0),
                "qualified": getattr(state, "qualified_count", 0),
                "disqualified": getattr(state, "disqualified_count", 0),
                "selected": getattr(state, "selected_count", 0),
            }

        return cls(
            task_id=state.task_id,
            run_id=getattr(state, "run_id", None),
            user_goal=state.user_goal,
            status=state.status.value if hasattr(state.status, "value") else str(state.status),
            completed_capabilities=completed_caps,
            summary=summary_text,
            clarification_question=clar_question_text,
            missing_information=missing_info,
            prospect_context=getattr(state, "prospect_context", None),
            opportunity_analysis=getattr(state, "opportunity_analysis", None),
            outreach_strategy=getattr(state, "outreach_strategy", None),
            evaluation_result=getattr(state, "evaluation_result", None),
            outreach_draft=getattr(state, "outreach_draft", None),
            prospects_count=len(state.prospects) if getattr(state, "prospects", None) else 0,
            qualification_summary=qual_summary,
            batch_summary=batch_sum,
            errors=list(getattr(state, "errors", [])),
        )
