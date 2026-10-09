"""
agent/prospects.py
------------------
Domain-level representation of Prospect Sets and controlled multi-prospect execution (Phase 4A).
Defines:
- ProspectSet: typed collection of discovered candidate prospects reusing canonical Business schema.
- ProspectSelection: explicit filtering and candidate selection semantics.
- ProspectExecutionResult: structured per-prospect outcome and domain models.
- ProspectBatchResult: typed batch result with ranking adapters.
- ProspectBatchExecutor: controlled sequential execution engine enforcing batch safety limits,
  failure isolation, and per-prospect telemetry through CapabilityRegistry.
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

from pydantic import BaseModel, ConfigDict, Field

from schemas.business import Business
from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult
from application.capabilities.registry import CapabilityRegistry
from application.contracts.outputs import DiscoverProspectsOutput
from agent.policies import PolicyEnforcer
from agent.qualification import ProspectQualification
from agent.evidence import EvidenceAcquisitionCoordinator, EvidenceAcquisitionResult
from agent.telemetry import (
    AgentTelemetrySink,
    CapabilityTraceEvent,
    StepEventStatus,
    ErrorCategory,
)

logger = logging.getLogger(__name__)


class BatchSizeLimitExceededError(Exception):
    """Raised when requested prospect batch size exceeds configured safety limit."""
    pass


class ProspectSet(BaseModel):
    """
    Typed domain model representing a discovered collection of candidate prospects.
    Reuses canonical schemas.business.Business directly without schema duplication.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    set_id: str = Field(default_factory=lambda: f"pset_{uuid.uuid4().hex[:8]}", description="Unique prospect set ID")
    source: str = Field(default="gmaps", description="Discovery source (e.g. 'gmaps', 'justdial', 'indiamart')")
    query: str = Field(default="", description="Search query used for discovery")
    location: Optional[str] = Field(default=None, description="Geographic location constraint")
    total_discovered: int = Field(default=0, ge=0, description="Total prospects discovered in search")
    prospects: List[Business] = Field(default_factory=list, description="Discovered candidate businesses")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @classmethod
    def from_discovery_output(
        cls,
        output: DiscoverProspectsOutput,
        location: Optional[str] = None,
        set_id: Optional[str] = None
    ) -> "ProspectSet":
        """Factory method constructing a ProspectSet from a DiscoverProspectsOutput."""
        return cls(
            set_id=set_id or f"pset_{uuid.uuid4().hex[:8]}",
            source=output.source,
            query=output.query,
            location=location,
            total_discovered=output.total_found or len(output.businesses),
            prospects=list(output.businesses),
        )

    def get_prospect(self, business_name: str) -> Optional[Business]:
        """Lookup a prospect by business name."""
        for p in self.prospects:
            if p.business_name.lower() == business_name.lower():
                return p
        return None

    def __len__(self) -> int:
        return len(self.prospects)


class QualifiedProspectSet(BaseModel):
    """
    Typed domain model representing a discovered ProspectSet partitioned by deterministic qualification.
    Retains full explainability of why each candidate was qualified or disqualified.
    Reuses canonical schemas.business.Business without duplication.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    set_id: str = Field(default_factory=lambda: f"qset_{uuid.uuid4().hex[:8]}", description="Unique qualified set ID")
    original_set_id: str = Field(..., description="ID of source ProspectSet")
    source: str = Field(default="gmaps", description="Discovery source")
    query: str = Field(default="", description="Search query")
    location: Optional[str] = Field(default=None, description="Geographic constraint")
    total_discovered: int = Field(default=0, ge=0, description="Total discovered prospects count")
    qualified_count: int = Field(default=0, ge=0, description="Count of qualified prospects")
    disqualified_count: int = Field(default=0, ge=0, description="Count of disqualified prospects")
    qualifications: Dict[str, ProspectQualification] = Field(
        default_factory=dict,
        description="Detailed qualification results keyed by business name"
    )
    qualified_prospects: List[Business] = Field(
        default_factory=list,
        description="References to qualified Business models"
    )
    disqualified_prospects: List[Business] = Field(
        default_factory=list,
        description="References to disqualified Business models"
    )
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def prospects(self) -> List[Business]:
        """Provides backward-compatibility: returns qualified prospects."""
        return self.qualified_prospects

    def get_prospect(self, business_name: str) -> Optional[Business]:
        """Lookup a prospect by business name among qualified prospects."""
        for p in self.qualified_prospects:
            if p.business_name.lower() == business_name.lower():
                return p
        return None

    def get_qualification(self, business_name: str) -> Optional[ProspectQualification]:
        """Lookup detailed qualification decision for a business."""
        return self.qualifications.get(business_name)

    def __len__(self) -> int:
        return len(self.qualified_prospects)


class ProspectSelection(BaseModel):
    """
    Typed selection criteria determining which discovered prospects receive deeper analysis.
    Does NOT perform scraping or AI reasoning.
    """
    model_config = ConfigDict(extra="ignore")

    selection_id: str = Field(default_factory=lambda: f"sel_{uuid.uuid4().hex[:8]}")
    max_prospects: int = Field(default=5, ge=1, description="Maximum prospects to select for deep analysis")
    minimum_score: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Minimum rating filter")
    required_industry: Optional[str] = Field(default=None, description="Filter by category/industry")
    required_location: Optional[str] = Field(default=None, description="Filter by location/address")
    ranking: Optional[str] = Field(
        default=None,
        description="Pre-analysis ordering: 'rating_asc', 'rating_desc', 'review_count_desc', 'qualification_score_desc'"
    )
    selection_reason: str = Field(default="", description="Rationale explaining selection criteria")

    def select(self, prospect_source: Union[ProspectSet, QualifiedProspectSet]) -> List[Business]:
        """
        Deterministically filters, sorts, and bounds prospects from a ProspectSet or QualifiedProspectSet.
        When provided a QualifiedProspectSet, only qualified prospects are considered for selection.
        """
        if isinstance(prospect_source, QualifiedProspectSet):
            candidates = list(prospect_source.qualified_prospects)
        else:
            candidates = list(prospect_source.prospects)

        # 1. Filter by minimum score/rating
        if self.minimum_score is not None:
            candidates = [
                b for b in candidates
                if (getattr(b, "google_rating", None) or getattr(b, "rating", 0.0) or 0.0) >= self.minimum_score
            ]

        # 2. Filter by required industry/category
        if self.required_industry:
            req_ind = self.required_industry.lower()
            candidates = [
                b for b in candidates
                if req_ind in (getattr(b, "category", "") or "").lower()
            ]

        # 3. Filter by required location
        if self.required_location:
            req_loc = self.required_location.lower()
            candidates = [
                b for b in candidates
                if req_loc in (getattr(b, "address", "") or "").lower()
                or req_loc in (getattr(b, "city", "") or "").lower()
            ]

        # 4. Sort if ranking criteria specified
        if self.ranking == "rating_asc":
            candidates.sort(
                key=lambda b: getattr(b, "google_rating", None) or getattr(b, "rating", 0.0) or 0.0
            )
        elif self.ranking == "rating_desc":
            candidates.sort(
                key=lambda b: getattr(b, "google_rating", None) or getattr(b, "rating", 0.0) or 0.0,
                reverse=True
            )
        elif self.ranking == "review_count_desc":
            candidates.sort(
                key=lambda b: getattr(b, "review_count", 0) or 0,
                reverse=True
            )
        elif self.ranking == "qualification_score_desc" and isinstance(prospect_source, QualifiedProspectSet):
            candidates.sort(
                key=lambda b: getattr(prospect_source.get_qualification(b.business_name), "qualification_score", 0.0) or 0.0,
                reverse=True
            )

        # 5. Cap at max_prospects safety boundary
        return candidates[:self.max_prospects]


class ProspectExecutionResult(BaseModel):
    """
    Structured outcome of processing a single prospect through deep analysis capabilities.
    Reuses existing typed models without duplicating ProspectContext or OpportunityAnalysis.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    prospect_id: str = Field(..., description="Business name or identifier")
    business: Business = Field(..., description="Reference to canonical Business entity")
    status: str = Field(..., description="Outcome status: 'COMPLETED', 'FAILED', 'BLOCKED'")
    completed_steps: List[str] = Field(default_factory=list, description="Capabilities successfully executed")
    failed_steps: List[str] = Field(default_factory=list, description="Capabilities that failed")
    prospect_context: Optional[ProspectContext] = Field(default=None, description="Compiled ProspectContext")
    opportunity_analysis: Optional[OpportunityAnalysis] = Field(default=None, description="Synthesized OpportunityAnalysis")
    outreach_strategy: Optional[OutreachStrategy] = Field(default=None, description="Formulated OutreachStrategy")
    evaluation_result: Optional[EvaluationResult] = Field(default=None, description="EvaluationResult verifying reasoning")
    outreach_draft: Optional[OutreachDraft] = Field(default=None, description="Rendered cold outreach drafts")
    opportunity_score: Optional[float] = Field(default=None, description="Normalized sales opportunity score (0-100)")
    errors: List[str] = Field(default_factory=list, description="Encountered errors for this prospect")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Processing duration in milliseconds")


class ProspectBatchResult(BaseModel):
    """
    Typed, serializable result representing multi-prospect batch execution.
    Maintains per-prospect outcomes, aggregate statistics, and ranking adapters.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    batch_id: str = Field(default_factory=lambda: f"batch_{uuid.uuid4().hex[:8]}")
    requested_count: int = Field(..., ge=0, description="Total prospects requested")
    selected_count: int = Field(..., ge=0, description="Count of prospects selected for deep analysis")
    completed_count: int = Field(default=0, ge=0, description="Prospects completed successfully")
    failed_count: int = Field(default=0, ge=0, description="Prospects that encountered execution failure")
    blocked_count: int = Field(default=0, ge=0, description="Prospects blocked by policy or dependency")
    discovered_count: Optional[int] = Field(default=None, description="Total discovered prospects count")
    qualified_count: Optional[int] = Field(default=None, description="Count of qualified prospects")
    disqualified_count: Optional[int] = Field(default=None, description="Count of disqualified prospects")
    results: List[ProspectExecutionResult] = Field(default_factory=list, description="Per-prospect execution results")
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = Field(default=None)
    duration_ms: float = Field(default=0.0, ge=0.0)

    def ranked_results(self, criterion: str = "opportunity_score") -> List[ProspectExecutionResult]:
        """
        Ranks completed results using existing canonical signals without inventing new scoring formulas.
        - 'opportunity_score': Ranks by sales_opportunity_score (higher pitch opportunity first).
        - 'rating_asc': Ranks by lower rating first (greater pain / need for reputation service).
        - 'review_count_desc': Ranks by higher review count first (established businesses).
        - 'confidence_desc': Ranks by AI diagnostic confidence score first.
        """
        completed = [r for r in self.results if r.status == "COMPLETED"]
        uncompleted = [r for r in self.results if r.status != "COMPLETED"]

        if criterion == "opportunity_score":
            completed.sort(
                key=lambda r: (
                    r.opportunity_score if r.opportunity_score is not None else
                    (r.prospect_context.scores.sales_opportunity_score if r.prospect_context and getattr(r.prospect_context, "scores", None) else 0.0)
                ),
                reverse=True
            )
        elif criterion == "rating_asc":
            completed.sort(
                key=lambda r: getattr(r.business, "google_rating", None) or getattr(r.business, "rating", 5.0) or 5.0
            )
        elif criterion == "review_count_desc":
            completed.sort(
                key=lambda r: getattr(r.business, "review_count", 0) or 0,
                reverse=True
            )
        elif criterion == "confidence_desc":
            completed.sort(
                key=lambda r: r.opportunity_analysis.confidence_score if r.opportunity_analysis else 0.0,
                reverse=True
            )

        return completed + uncompleted


class ProspectBatchExecutor:
    """
    Controlled multi-prospect execution abstraction.
    Processes selected prospects sequentially through CapabilityRegistry.
    Enforces batch safety limits, failure isolation, per-prospect telemetry,
    and opportunity ranking without distributed worker overhead.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        policy_enforcer: Optional[PolicyEnforcer] = None,
        telemetry_sink: Optional[AgentTelemetrySink] = None,
        max_prospects_per_run: int = 15,
        strict_limit: bool = False,
        evidence_coordinator: Optional[EvidenceAcquisitionCoordinator] = None,
    ):
        self.registry = registry
        self.policy_enforcer = policy_enforcer or PolicyEnforcer()
        self.telemetry_sink = telemetry_sink
        self.max_prospects_per_run = max_prospects_per_run
        self.strict_limit = strict_limit
        self.evidence_coordinator = evidence_coordinator or EvidenceAcquisitionCoordinator(
            registry=self.registry,
            policy_enforcer=self.policy_enforcer,
            telemetry_sink=self.telemetry_sink,
        )

    def execute_batch(
        self,
        prospect_set: Union[ProspectSet, QualifiedProspectSet],
        selection: Optional[ProspectSelection] = None,
        include_outreach: bool = False,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> ProspectBatchResult:
        """
        Executes deep analysis sequentially across selected prospects with failure isolation.
        """
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        r_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
        start_mono = time.monotonic()
        started_at = datetime.utcnow().isoformat()

        if isinstance(prospect_set, QualifiedProspectSet):
            discovered_count = prospect_set.total_discovered
            qualified_count = prospect_set.qualified_count
            disqualified_count = prospect_set.disqualified_count
            total_cand = len(prospect_set.qualified_prospects)
        else:
            discovered_count = len(prospect_set.prospects)
            qualified_count = len(prospect_set.prospects)
            disqualified_count = 0
            total_cand = len(prospect_set.prospects)

        # 1. Enforce batch safety limit
        if selection is None:
            selection = ProspectSelection(
                max_prospects=min(total_cand, self.max_prospects_per_run)
            )

        requested_count = selection.max_prospects
        if requested_count > self.max_prospects_per_run:
            if self.strict_limit:
                raise BatchSizeLimitExceededError(
                    f"Requested prospect batch count ({requested_count}) exceeds "
                    f"configured safety limit ({self.max_prospects_per_run})."
                )
            logger.warning(
                f"[ProspectBatchExecutor] Requested count {requested_count} exceeds safety limit "
                f"{self.max_prospects_per_run}. Constraining to {self.max_prospects_per_run}."
            )
            selection.max_prospects = self.max_prospects_per_run

        # 2. Select candidates
        selected_prospects = selection.select(prospect_set)
        selected_count = len(selected_prospects)
        logger.info(
            f"[ProspectBatchExecutor:{batch_id}] Processing {selected_count} selected prospects "
            f"(from {discovered_count} total discovered, {qualified_count} qualified)."
        )

        results: List[ProspectExecutionResult] = []

        # 3. Controlled Sequential Execution Loop
        for biz in selected_prospects:
            p_result = self._execute_single_prospect(
                biz=biz,
                batch_id=batch_id,
                run_id=r_id,
                include_outreach=include_outreach,
            )
            results.append(p_result)

        # 4. Aggregate metrics
        completed_count = sum(1 for r in results if r.status == "COMPLETED")
        failed_count = sum(1 for r in results if r.status == "FAILED")
        blocked_count = sum(1 for r in results if r.status == "BLOCKED")
        duration_ms = (time.monotonic() - start_mono) * 1000.0
        completed_at = datetime.utcnow().isoformat()

        return ProspectBatchResult(
            batch_id=batch_id,
            requested_count=requested_count,
            selected_count=selected_count,
            completed_count=completed_count,
            failed_count=failed_count,
            blocked_count=blocked_count,
            discovered_count=discovered_count,
            qualified_count=qualified_count,
            disqualified_count=disqualified_count,
            results=results,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

    def _execute_single_prospect(
        self,
        biz: Business,
        batch_id: str,
        run_id: str,
        include_outreach: bool = False,
    ) -> ProspectExecutionResult:
        """
        Executes the capability pipeline for one prospect with strict failure isolation.
        A failure here never aborts other prospects in the batch.
        """
        prospect_start_mono = time.monotonic()
        p_id = biz.business_name
        logger.info(f"[ProspectBatchExecutor:{batch_id}] Starting deep analysis for '{p_id}'")

        completed_steps: List[str] = []
        failed_steps: List[str] = []
        errors: List[str] = []

        capability_data: Dict[str, Any] = {}
        prospect_ctx: Optional[ProspectContext] = None
        opp_analysis: Optional[OpportunityAnalysis] = None
        outreach_strat: Optional[OutreachStrategy] = None
        eval_res: Optional[EvaluationResult] = None
        draft_res: Optional[OutreachDraft] = None

        # Helper to execute a capability via CapabilityRegistry with policy checks & telemetry
        def _invoke_cap(cap_name: str, params: Dict[str, Any], step_id: str) -> Optional[Any]:
            nonlocal completed_steps, failed_steps, errors
            desc = self.registry.get(cap_name)
            if not desc:
                err = f"Unregistered capability '{cap_name}'"
                failed_steps.append(cap_name)
                errors.append(err)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=run_id,
                            batch_id=batch_id,
                            prospect_id=p_id,
                            step_id=step_id,
                            capability_name=cap_name,
                            status=StepEventStatus.FAILED,
                            error_type=ErrorCategory.CAPABILITY_ERROR,
                            error_message=err,
                        )
                    )
                return None

            policy_eval = self.policy_enforcer.evaluate(desc)
            if not policy_eval.is_allowed:
                err = f"Policy violation on '{cap_name}': {policy_eval.reason}"
                failed_steps.append(cap_name)
                errors.append(err)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=run_id,
                            batch_id=batch_id,
                            prospect_id=p_id,
                            step_id=step_id,
                            capability_name=cap_name,
                            status=StepEventStatus.FAILED,
                            error_type=ErrorCategory.POLICY_ERROR,
                            error_message=err,
                        )
                    )
                return None

            # Telemetry: STARTED
            start_mono = time.monotonic()
            if self.telemetry_sink:
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=run_id,
                        batch_id=batch_id,
                        prospect_id=p_id,
                        step_id=step_id,
                        capability_name=cap_name,
                        capability_classification=desc.policy_class.value,
                        status=StepEventStatus.STARTED,
                        started_at=datetime.utcnow().isoformat(),
                    )
                )

            # Invoke via registry exclusively
            res = self.registry.execute(cap_name, params)
            dur_ms = (time.monotonic() - start_mono) * 1000.0

            if not res.success:
                failed_steps.append(cap_name)
                err_msg = res.error or f"Capability '{cap_name}' execution failed"
                errors.append(err_msg)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=run_id,
                            batch_id=batch_id,
                            prospect_id=p_id,
                            step_id=step_id,
                            capability_name=cap_name,
                            capability_classification=desc.policy_class.value,
                            status=StepEventStatus.FAILED,
                            started_at=datetime.utcnow().isoformat(),
                            completed_at=datetime.utcnow().isoformat(),
                            duration_ms=dur_ms,
                            error_type=ErrorCategory.CAPABILITY_ERROR,
                            error_message=err_msg,
                        )
                    )
                return None

            if cap_name == "evaluate_ai_reasoning" and isinstance(res.data, EvaluationResult) and not res.data.passed:
                failed_steps.append(cap_name)
                issue_text = "; ".join(res.data.issues or ["Evaluation score failed quality gate"])
                err_msg = f"Evaluation gate failed: {issue_text}"
                errors.append(err_msg)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=run_id,
                            batch_id=batch_id,
                            prospect_id=p_id,
                            step_id=step_id,
                            capability_name=cap_name,
                            capability_classification=desc.policy_class.value,
                            status=StepEventStatus.FAILED,
                            started_at=datetime.utcnow().isoformat(),
                            completed_at=datetime.utcnow().isoformat(),
                            duration_ms=dur_ms,
                            error_type=ErrorCategory.EVALUATION_ERROR,
                            error_message=err_msg,
                        )
                    )
                return res.data

            completed_steps.append(cap_name)
            if self.telemetry_sink:
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=run_id,
                        batch_id=batch_id,
                        prospect_id=p_id,
                        step_id=step_id,
                        capability_name=cap_name,
                        capability_classification=desc.policy_class.value,
                        status=StepEventStatus.COMPLETED,
                        started_at=datetime.utcnow().isoformat(),
                        completed_at=datetime.utcnow().isoformat(),
                        duration_ms=dur_ms,
                    )
                )
            return res.data

        # 1-5. Evidence Acquisition Pipeline (Phase 4C)
        evidence_res = self.evidence_coordinator.acquire_evidence(
            business=biz,
            run_id=run_id,
            batch_id=batch_id,
        )
        completed_steps.extend(evidence_res.completed_capabilities)
        failed_steps.extend(evidence_res.failed_capabilities)
        errors.extend(evidence_res.errors)

        if not evidence_res.success or evidence_res.context is None:
            dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0
            return ProspectExecutionResult(
                prospect_id=p_id,
                business=biz,
                status="FAILED",
                completed_steps=completed_steps,
                failed_steps=failed_steps,
                prospect_context=evidence_res.context,
                errors=errors,
                duration_ms=dur_ms,
            )

        prospect_ctx = evidence_res.context

        # 6. Synthesize Opportunity Analysis
        opp_analysis = _invoke_cap(
            "synthesize_opportunity_analysis",
            {"context": prospect_ctx},
            "step_opp"
        )
        if opp_analysis is None:
            dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0
            return ProspectExecutionResult(
                prospect_id=p_id,
                business=biz,
                status="FAILED",
                completed_steps=completed_steps,
                failed_steps=failed_steps,
                prospect_context=prospect_ctx,
                errors=errors,
                duration_ms=dur_ms,
            )

        # 7. Optional Outreach Strategy & Drafting
        if include_outreach and opp_analysis:
            outreach_strat = _invoke_cap(
                "formulate_outreach_strategy",
                {"context": prospect_ctx, "opportunity_analysis": opp_analysis},
                "step_outreach"
            )
            if outreach_strat:
                eval_res = _invoke_cap(
                    "evaluate_ai_reasoning",
                    {
                        "context": prospect_ctx,
                        "opportunity_analysis": opp_analysis,
                        "outreach_strategy": outreach_strat
                    },
                    "step_eval"
                )
                if eval_res and eval_res.passed:
                    draft_res = _invoke_cap(
                        "render_outreach_drafts",
                        {"context": prospect_ctx, "outreach_strategy": outreach_strat},
                        "step_draft"
                    )
                elif eval_res and not eval_res.passed:
                    if self.telemetry_sink:
                        self.telemetry_sink.record_step(
                            CapabilityTraceEvent(
                                run_id=run_id,
                                batch_id=batch_id,
                                prospect_id=p_id,
                                step_id="step_draft",
                                capability_name="render_outreach_drafts",
                                capability_classification=None,
                                status=StepEventStatus.BLOCKED,
                                started_at=datetime.utcnow().isoformat(),
                                completed_at=datetime.utcnow().isoformat(),
                                duration_ms=0.0,
                                error_type=None,
                                error_message="Prerequisite step 'step_eval' failed evaluation gate",
                                dependency_status={"step_eval": "FAILED"},
                            )
                        )

        # Determine prospect status
        status = "COMPLETED" if (len(failed_steps) == 0 and prospect_ctx is not None) else "FAILED"
        dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0

        # Calculate opportunity score from scores if present
        opp_score = None
        if prospect_ctx and getattr(prospect_ctx, "scores", None):
            opp_score = prospect_ctx.scores.sales_opportunity_score
        elif opp_analysis and getattr(opp_analysis, "confidence_score", None) is not None:
            opp_score = opp_analysis.confidence_score * 100.0

        valid_ctx = prospect_ctx if isinstance(prospect_ctx, ProspectContext) else None
        valid_opp = opp_analysis if isinstance(opp_analysis, OpportunityAnalysis) else None
        valid_outreach = outreach_strat if isinstance(outreach_strat, OutreachStrategy) else None
        valid_eval = eval_res if isinstance(eval_res, EvaluationResult) else None
        valid_draft = draft_res if isinstance(draft_res, OutreachDraft) else None

        return ProspectExecutionResult(
            prospect_id=p_id,
            business=biz,
            status=status,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            prospect_context=valid_ctx,
            opportunity_analysis=valid_opp,
            outreach_strategy=valid_outreach,
            evaluation_result=valid_eval,
            outreach_draft=valid_draft,
            opportunity_score=opp_score,
            errors=errors,
            duration_ms=dur_ms,
        )
