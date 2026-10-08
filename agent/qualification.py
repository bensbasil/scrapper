"""
agent/qualification.py
----------------------
Deterministic Prospect Qualification & Pre-Analysis Selection (Phase 4B).

CRITICAL ARCHITECTURAL DISTINCTION:
- ProspectQualification / qualification_score:
    Answers: "Is this discovered prospect worth spending computation on?"
    Evaluated BEFORE deep analysis, based strictly on fast, deterministic discovery signals
    (website presence, category alignment, geographic match, contact viability, directory verification).
    Does NOT replace or represent the sales opportunity.
- OpportunityAnalysis / opportunity_score:
    Answers: "How strong is the actual business opportunity after deep analysis?"
    Evaluated DURING deep analysis by synthesis of website technical audit, customer reviews,
    conversion friction, and sales gap reasoning.

Qualification is:
- deterministic
- explainable
- cheap & in-memory
- bounded
- based on existing canonical signals only
- strictly independent of LLM reasoning
"""

import logging
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field

from schemas.business import Business

if TYPE_CHECKING:
    from agent.prospects import ProspectSet, QualifiedProspectSet

logger = logging.getLogger(__name__)


class ProspectQualification(BaseModel):
    """
    Structured outcome of deterministic qualification for a single candidate prospect.
    Answers whether this prospect should receive deeper computation.
    """
    model_config = ConfigDict(extra="ignore")

    prospect_id: str = Field(..., description="Unique business identifier or name")
    qualified: bool = Field(..., description="Whether prospect passed all deterministic qualification criteria")
    qualification_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Deterministic pre-analysis filtering score [0.0 - 1.0]. NOT an opportunity score."
    )
    reasons: List[str] = Field(default_factory=list, description="Positive qualification signals and criteria met")
    disqualifiers: List[str] = Field(default_factory=list, description="Disqualification reasons that failed policy checks")
    evaluated_signals: Dict[str, Any] = Field(default_factory=dict, description="Snapshot of raw signals evaluated")


class QualificationPolicy(BaseModel):
    """
    Configurable deterministic rules and criteria for prospect qualification.
    Pure rule-based heuristics over canonical Business fields.
    """
    model_config = ConfigDict(extra="ignore")

    require_website: bool = Field(default=False, description="Whether prospect must possess a website URL")
    require_phone: bool = Field(default=False, description="Whether prospect must possess a contact phone number")
    target_location: Optional[str] = Field(default=None, description="Geographic location constraint (case-insensitive substring)")
    target_industry: Optional[str] = Field(default=None, description="Industry/category constraint (case-insensitive substring)")
    min_rating: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Minimum Google or directory rating required")
    min_reviews: Optional[int] = Field(default=None, ge=0, description="Minimum Google or directory review count required")
    exclude_already_contacted: bool = Field(default=True, description="Disqualify prospects with outreach_status in ('contacted', 'followed_up', 'closed')")

    @classmethod
    def from_intent(cls, intent: Any) -> "QualificationPolicy":
        """
        Derives deterministic qualification criteria from an AgentIntent.
        """
        target_loc = getattr(intent, "location", None)
        target_ind = getattr(intent, "industry", None)
        constraints = getattr(intent, "constraints", {}) or {}

        req_web = constraints.get("require_website", False)
        req_phone = constraints.get("require_phone", False)
        min_rat = constraints.get("min_rating")
        min_revs = constraints.get("min_reviews")

        return cls(
            target_location=target_loc,
            target_industry=target_ind,
            require_website=req_web,
            require_phone=req_phone,
            min_rating=float(min_rat) if min_rat is not None else None,
            min_reviews=int(min_revs) if min_revs is not None else None,
        )


class DeterministicProspectQualifier:
    """
    Evaluates discovered candidate prospects against deterministic qualification rules.
    Pure logic over canonical Business models without LLMs, databases, or scrapers.
    """

    def __init__(self, policy: Optional[QualificationPolicy] = None):
        self.policy = policy or QualificationPolicy()

    def qualify_prospect(self, business: Business) -> ProspectQualification:
        """
        Evaluates a single Business entity and produces a ProspectQualification record.
        """
        prospect_id = getattr(business, "business_name", "Unknown Business")
        reasons: List[str] = []
        disqualifiers: List[str] = []

        # 1. Snapshot evaluated signals from canonical Business schema
        rating = getattr(business, "google_rating", None)
        if rating is None:
            rating = getattr(business, "jd_rating", getattr(business, "im_rating", None))

        rev_count = getattr(business, "review_count", None)
        if rev_count is None:
            rev_count = getattr(business, "jd_reviews_count", 0) or 0

        is_verified = bool(
            getattr(business, "jd_verified", False)
            or getattr(business, "im_verified", False)
            or getattr(business, "im_gst_verified", False)
        )

        evaluated_signals: Dict[str, Any] = {
            "business_name": business.business_name,
            "has_website": bool(business.website and business.website.strip()),
            "website_url": business.website,
            "has_phone": bool(business.phone and business.phone.strip()),
            "phone": business.phone,
            "category": business.category,
            "address": business.address,
            "rating": rating,
            "review_count": rev_count,
            "verified_directory": is_verified,
            "outreach_status": business.outreach_status,
        }

        # 2. Rule: Business Identity Validity
        if not business.business_name or not business.business_name.strip():
            disqualifiers.append("Missing business name")
        else:
            reasons.append(f"Valid business entity: '{business.business_name}'")

        # 3. Rule: Outreach Status Check
        if self.policy.exclude_already_contacted and business.outreach_status in ("contacted", "followed_up", "closed"):
            disqualifiers.append(f"Prospect already engaged (outreach_status='{business.outreach_status}')")
        else:
            reasons.append(f"Fresh prospect (outreach_status='{business.outreach_status}')")

        # 4. Rule: Geographic / Location Constraint Match
        if self.policy.target_location:
            req_loc = self.policy.target_location.lower().strip()
            addr = (business.address or "").lower()
            city = (getattr(business, "city", "") or "").lower()
            if req_loc in addr or req_loc in city:
                reasons.append(f"Location matches geographic constraint '{self.policy.target_location}'")
            else:
                disqualifiers.append(
                    f"Outside requested location: address '{business.address or 'None'}' does not match '{self.policy.target_location}'"
                )

        # 5. Rule: Industry / Category Constraint Match
        if self.policy.target_industry:
            req_ind = self.policy.target_industry.lower().strip()
            cat = (business.category or "").lower()
            if req_ind in cat:
                reasons.append(f"Category matches target industry '{self.policy.target_industry}'")
            else:
                disqualifiers.append(
                    f"Category mismatch: '{business.category or 'None'}' does not match target industry '{self.policy.target_industry}'"
                )

        # 6. Rule: Website Presence
        if self.policy.require_website:
            if not business.website or not business.website.strip():
                disqualifiers.append("Missing required website URL for technical audit")
            else:
                reasons.append(f"Website present: {business.website}")
        else:
            if business.website and business.website.strip():
                reasons.append(f"Website present: {business.website}")
            else:
                reasons.append("No website present (valid candidate for new web presence opportunity)")

        # 7. Rule: Contact Phone Presence
        if self.policy.require_phone:
            if not business.phone or not business.phone.strip():
                disqualifiers.append("Missing required contact phone number")
            else:
                reasons.append("Contact phone number available")
        else:
            if business.phone and business.phone.strip():
                reasons.append("Contact phone number available")

        # 8. Rule: Minimum Rating Threshold
        if self.policy.min_rating is not None:
            if rating is not None and rating < self.policy.min_rating:
                disqualifiers.append(f"Rating {rating} is below minimum required {self.policy.min_rating}")
            elif rating is not None:
                reasons.append(f"Rating {rating} meets minimum threshold ({self.policy.min_rating})")
        elif rating is not None:
            reasons.append(f"Directory rating available: {rating}")

        # 9. Rule: Minimum Review Count Threshold
        if self.policy.min_reviews is not None:
            if rev_count < self.policy.min_reviews:
                disqualifiers.append(f"Review count {rev_count} is below minimum required {self.policy.min_reviews}")
            else:
                reasons.append(f"Review count {rev_count} meets minimum threshold ({self.policy.min_reviews})")
        elif rev_count > 0:
            reasons.append(f"Established review presence: {rev_count} reviews")

        # 10. Rule: Directory Verification Signals
        if is_verified:
            reasons.append("Verified vendor status confirmed on local business directories")

        # Decision & Deterministic Filtering Score
        qualified = (len(disqualifiers) == 0)

        if not qualified:
            qualification_score = 0.0
        else:
            # Deterministic filtering score [0.0 - 1.0] for pre-analysis candidate prioritization
            score = 0.50
            if business.website and business.website.strip():
                score += 0.15
            if business.phone and business.phone.strip():
                score += 0.15
            if is_verified:
                score += 0.10
            if rev_count >= 5:
                score += 0.10
            qualification_score = round(min(1.0, score), 2)

        return ProspectQualification(
            prospect_id=prospect_id,
            qualified=qualified,
            qualification_score=qualification_score,
            reasons=reasons,
            disqualifiers=disqualifiers,
            evaluated_signals=evaluated_signals,
        )

    def qualify_set(self, prospect_set: "ProspectSet") -> "QualifiedProspectSet":
        """
        Partitions an entire ProspectSet into qualified and disqualified groups.
        Produces a QualifiedProspectSet preserving every evaluation outcome.
        """
        from agent.prospects import QualifiedProspectSet

        qualifications: Dict[str, ProspectQualification] = {}
        qualified_prospects: List[Business] = []
        disqualified_prospects: List[Business] = []

        for p in prospect_set.prospects:
            q = self.qualify_prospect(p)
            qualifications[p.business_name] = q
            if q.qualified:
                qualified_prospects.append(p)
            else:
                disqualified_prospects.append(p)

        logger.info(
            f"[DeterministicProspectQualifier] Qualified set '{prospect_set.set_id}': "
            f"{len(qualified_prospects)}/{len(prospect_set.prospects)} passed "
            f"({len(disqualified_prospects)} disqualified)"
        )

        return QualifiedProspectSet(
            set_id=f"qset_{prospect_set.set_id}",
            original_set_id=prospect_set.set_id,
            source=prospect_set.source,
            query=prospect_set.query,
            location=prospect_set.location,
            total_discovered=len(prospect_set.prospects),
            qualified_count=len(qualified_prospects),
            disqualified_count=len(disqualified_prospects),
            qualifications=qualifications,
            qualified_prospects=qualified_prospects,
            disqualified_prospects=disqualified_prospects,
        )
