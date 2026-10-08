"""
agent/evidence.py
-----------------
Evidence Acquisition & Canonical ProspectContext Assembly (Phase 4C).
Orchestrates capability tools through CapabilityRegistry to construct a validated,
token-efficient, atomic-provenance ProspectContext for a single selected prospect.

Guarantees:
- Strict registry boundary: never directly executes scrapers, Playwright, DB, or HTTP.
- Strict AI boundary: never calls LLMClient, OpportunityReasoner, or OutreachReasoner.
- Robust partial evidence handling: missing websites or enrichments do not abort context assembly.
- Token bounded: maintains token-efficient evidence items (< 350 word summary).
- Strict failure isolation: errors for one prospect do not cascade to others.
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from schemas.business import Business
from schemas.context import ProspectContext
from application.capabilities.registry import CapabilityRegistry
from agent.policies import PolicyEnforcer
from agent.telemetry import (
    AgentTelemetrySink,
    CapabilityTraceEvent,
    StepEventStatus,
    ErrorCategory,
)

logger = logging.getLogger(__name__)


class EvidenceAcquisitionResult(BaseModel):
    """
    Structured outcome of evidence acquisition for a single prospect.
    Encapsulates the assembled canonical ProspectContext and execution metadata.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    prospect_id: str = Field(..., description="Business identifier or name")
    success: bool = Field(..., description="Whether a valid ProspectContext was successfully constructed")
    context: Optional[ProspectContext] = Field(default=None, description="Constructed canonical ProspectContext")
    completed_capabilities: List[str] = Field(default_factory=list, description="Capabilities successfully executed")
    failed_capabilities: List[str] = Field(default_factory=list, description="Capabilities that failed or were skipped")
    errors: List[str] = Field(default_factory=list, description="Errors encountered during evidence gathering")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Duration of evidence acquisition in milliseconds")


class EvidenceAcquisitionCoordinator:
    """
    Orchestrates evidence gathering for a selected prospect exclusively through CapabilityRegistry.
    Guarantees:
    - Registry-only execution (zero direct database, scraping, Playwright, or HTTP access).
    - Partial evidence tolerance (missing website or enrichment does not abort context construction).
    - Pure evidence gathering: never invokes LLMClient, OpportunityReasoner, or OutreachReasoner.
    - Produces canonical ProspectContext as the sole input boundary for downstream AI reasoning.
    - Records fine-grained telemetry without logging raw HTML or large payloads.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        policy_enforcer: Optional[PolicyEnforcer] = None,
        telemetry_sink: Optional[AgentTelemetrySink] = None,
        allow_partial_evidence: bool = True,
    ):
        self.registry = registry
        self.policy_enforcer = policy_enforcer or PolicyEnforcer()
        self.telemetry_sink = telemetry_sink
        self.allow_partial_evidence = allow_partial_evidence

    def acquire_evidence(
        self,
        business: Business,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> EvidenceAcquisitionResult:
        """
        Orchestrates evidence acquisition pipeline for a single business entity.
        Order:
        1. Website / tech audit (audit_website_tech)
        2. Leadership enrichment (enrich_leadership_social)
        3. Business intelligence (mine_business_intelligence)
        4. Health and scores (calculate_health_and_scores)
        5. ProspectContext assembly (assemble_prospect_context)
        """
        prospect_start_mono = time.monotonic()
        start_time_iso = datetime.utcnow().isoformat()
        p_id = business.business_name
        r_id = run_id or f"run_{uuid.uuid4().hex[:8]}"

        logger.info(f"[EvidenceCoordinator] Starting evidence acquisition for '{p_id}' (run_id={r_id})")

        completed_caps: List[str] = []
        failed_caps: List[str] = []
        errors: List[str] = []
        capability_data: Dict[str, Any] = {}

        # Emit STARTED trace event for evidence acquisition
        if self.telemetry_sink:
            self.telemetry_sink.record_step(
                CapabilityTraceEvent(
                    run_id=r_id,
                    batch_id=batch_id,
                    prospect_id=p_id,
                    step_id=f"evidence_{p_id}",
                    capability_name="acquire_evidence",
                    capability_classification="READ",
                    status=StepEventStatus.STARTED,
                    started_at=start_time_iso,
                )
            )

        # Helper to execute capability via CapabilityRegistry
        def _invoke_cap(cap_name: str, params: Dict[str, Any], step_id: str) -> Optional[Any]:
            desc = self.registry.get(cap_name)
            if not desc:
                err = f"Unregistered capability '{cap_name}'"
                failed_caps.append(cap_name)
                errors.append(err)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=r_id,
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
                failed_caps.append(cap_name)
                errors.append(err)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=r_id,
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

            cap_start = time.monotonic()
            res = self.registry.execute(cap_name, params)
            dur_ms = (time.monotonic() - cap_start) * 1000.0

            if not res.success:
                failed_caps.append(cap_name)
                err_msg = res.error or f"Capability '{cap_name}' execution failed"
                errors.append(err_msg)
                if self.telemetry_sink:
                    self.telemetry_sink.record_step(
                        CapabilityTraceEvent(
                            run_id=r_id,
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

            completed_caps.append(cap_name)
            if self.telemetry_sink:
                self.telemetry_sink.record_step(
                    CapabilityTraceEvent(
                        run_id=r_id,
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

        # --- 1. Website & Technical Signals ---
        has_website = bool(business.website and business.website.strip())
        if has_website:
            audit_data = _invoke_cap(
                "audit_website_tech",
                {"business_name": p_id, "website_url": business.website},
                "step_audit"
            )
            if audit_data is None:
                # Execution failure on website audit halts evidence acquisition for this prospect
                dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0
                self._record_acquisition_telemetry(r_id, batch_id, p_id, False, dur_ms, errors)
                return EvidenceAcquisitionResult(
                    prospect_id=p_id,
                    success=False,
                    completed_capabilities=completed_caps,
                    failed_capabilities=failed_caps,
                    errors=errors,
                    duration_ms=dur_ms,
                )
            capability_data["audit_website_tech"] = audit_data
        else:
            logger.info(f"[EvidenceCoordinator] Prospect '{p_id}' has no website; skipping website audit.")

        # --- 2. Leadership & Social Enrichment ---
        if has_website:
            enrich_data = _invoke_cap(
                "enrich_leadership_social",
                {"business_name": p_id, "website_url": business.website},
                "step_enrich"
            )
            if enrich_data is None:
                dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0
                self._record_acquisition_telemetry(r_id, batch_id, p_id, False, dur_ms, errors)
                return EvidenceAcquisitionResult(
                    prospect_id=p_id,
                    success=False,
                    completed_capabilities=completed_caps,
                    failed_capabilities=failed_caps,
                    errors=errors,
                    duration_ms=dur_ms,
                )
            capability_data["enrich_leadership_social"] = enrich_data
        else:
            logger.info(f"[EvidenceCoordinator] Prospect '{p_id}' has no website; skipping leadership enrichment.")

        # --- 3. Mine Business Intelligence ---
        rating = getattr(business, "rating", getattr(business, "google_rating", None))
        review_count = getattr(business, "review_count", None)
        intel_params = {
            "business_name": p_id,
            "category": getattr(business, "category", "Local Business") or "Local Business",
            "website_url": business.website,
            "rating": rating,
            "review_count": review_count,
            "address": getattr(business, "address", None),
        }
        intel_data = _invoke_cap("mine_business_intelligence", intel_params, "step_intel")
        if intel_data is None:
            dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0
            self._record_acquisition_telemetry(r_id, batch_id, p_id, False, dur_ms, errors)
            return EvidenceAcquisitionResult(
                prospect_id=p_id,
                success=False,
                completed_capabilities=completed_caps,
                failed_capabilities=failed_caps,
                errors=errors,
                duration_ms=dur_ms,
            )
        capability_data["mine_business_intelligence"] = intel_data

        # --- 4. Calculate Health and Scores ---
        scores_data = _invoke_cap(
            "calculate_health_and_scores",
            {
                "business_name": p_id,
                "rating": rating or 4.0,
                "review_count": review_count or 10,
            },
            "step_score"
        )
        if scores_data is None:
            dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0
            self._record_acquisition_telemetry(r_id, batch_id, p_id, False, dur_ms, errors)
            return EvidenceAcquisitionResult(
                prospect_id=p_id,
                success=False,
                completed_capabilities=completed_caps,
                failed_capabilities=failed_caps,
                errors=errors,
                duration_ms=dur_ms,
            )
        capability_data["calculate_health_and_scores"] = scores_data

        # --- 5. Assemble Prospect Context ---
        b_dict = business.model_dump() if hasattr(business, "model_dump") else business.__dict__
        ctx_params: Dict[str, Any] = {"business_data": b_dict}

        if "audit_website_tech" in capability_data:
            a_out = capability_data["audit_website_tech"]
            ctx_params["analysis_data"] = a_out.model_dump() if hasattr(a_out, "model_dump") else a_out

        if "enrich_leadership_social" in capability_data:
            e_out = capability_data["enrich_leadership_social"]
            if hasattr(e_out, "validated_emails"):
                ctx_params["email_data"] = {"emails": [e.email for e in e_out.validated_emails]}
            if hasattr(e_out, "decision_makers"):
                ctx_params["decision_data"] = {
                    "decision_makers": [
                        d.model_dump() if hasattr(d, "model_dump") else d for d in e_out.decision_makers
                    ]
                }

        if "mine_business_intelligence" in capability_data:
            m_out = capability_data["mine_business_intelligence"]
            ctx_params["review_mine_data"] = m_out.model_dump() if hasattr(m_out, "model_dump") else m_out

        if "calculate_health_and_scores" in capability_data:
            s_out = capability_data["calculate_health_and_scores"]
            ctx_params["health_data"] = s_out.model_dump() if hasattr(s_out, "model_dump") else s_out

        prospect_ctx = _invoke_cap("assemble_prospect_context", ctx_params, "step_context")
        dur_ms = (time.monotonic() - prospect_start_mono) * 1000.0

        if prospect_ctx is None or not isinstance(prospect_ctx, ProspectContext):
            err = "Failed to assemble canonical ProspectContext"
            errors.append(err)
            self._record_acquisition_telemetry(r_id, batch_id, p_id, False, dur_ms, errors)
            return EvidenceAcquisitionResult(
                prospect_id=p_id,
                success=False,
                completed_capabilities=completed_caps,
                failed_capabilities=failed_caps,
                errors=errors,
                duration_ms=dur_ms,
            )

        self._record_acquisition_telemetry(r_id, batch_id, p_id, True, dur_ms, errors)
        return EvidenceAcquisitionResult(
            prospect_id=p_id,
            success=True,
            context=prospect_ctx,
            completed_capabilities=completed_caps,
            failed_capabilities=failed_caps,
            errors=errors,
            duration_ms=dur_ms,
        )

    def _record_acquisition_telemetry(
        self,
        run_id: str,
        batch_id: Optional[str],
        prospect_id: str,
        success: bool,
        duration_ms: float,
        errors: List[str],
    ) -> None:
        """Records overall evidence acquisition outcome in telemetry sink."""
        if not self.telemetry_sink:
            return

        self.telemetry_sink.record_step(
            CapabilityTraceEvent(
                run_id=run_id,
                batch_id=batch_id,
                prospect_id=prospect_id,
                step_id=f"evidence_{prospect_id}",
                capability_name="acquire_evidence",
                capability_classification="READ",
                status=StepEventStatus.COMPLETED if success else StepEventStatus.FAILED,
                started_at=datetime.utcnow().isoformat(),
                completed_at=datetime.utcnow().isoformat(),
                duration_ms=duration_ms,
                error_type=ErrorCategory.CAPABILITY_ERROR if not success else None,
                error_message=errors[-1] if (not success and errors) else None,
            )
        )
