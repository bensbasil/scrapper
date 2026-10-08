"""
evaluation/evaluators.py
------------------------
Deterministic evaluation engine for AI reasoning quality.
Provides OpportunityEvaluator, OutreachEvaluator, and EvaluationRunner.

Key Guarantees:
- Purely deterministic in-memory execution: 0 live LLM calls, 0 network, 0 database calls.
- Strict score bounds: all scores bounded in [0.0, 1.0].
- Conservative heuristic hallucination detection distinguishing 'confirmed_supported'
  from 'potentially_unsupported' claims.
- Evaluates structural validity, evidence grounding, polarity adherence,
  and cross-component consistency.
"""

import re
import logging
from typing import Optional, List, Dict, Any, Set, Tuple

from schemas.context import ProspectContext, EvidenceItem
from schemas.ai import OpportunityAnalysis, OutreachStrategy, CommercialRecommendation
from evaluation.models import (
    EvaluationResult,
    ComponentEvaluation,
    HeuristicFlag,
    BatchEvaluationSummary,
)

logger = logging.getLogger(__name__)

# Standard English stopwords to filter out during token overlap matching
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with",
    "by", "of", "from", "as", "is", "was", "are", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "our", "their", "your",
    "we", "you", "they", "has", "have", "had", "not", "but", "so", "if",
    "than", "then", "into", "over", "after", "also", "about", "such"
}

# Negative / praising terms for polarity check
PRAISE_TERMS = [
    "exceptional online presence",
    "flawless digital presence",
    "outstanding website",
    "perfect online presence",
    "market leader in digital",
    "industry-leading website",
    "stellar digital footprint"
]

CATASTROPHE_TERMS = [
    "catastrophic failure",
    "broken digital presence",
    "digital disaster",
    "complete failure",
    "zero digital viability"
]

WEBSITE_ABSENCE_TERMS = [
    "no website",
    "missing website",
    "website is missing",
    "lacks a website",
    "doesn't have a website",
    "does not have a website",
    "no web presence",
    "without a website",
    "unregistered website"
]

POOR_REPUTATION_TERMS = [
    "bad rating",
    "low rating",
    "poor reviews",
    "terrible reviews",
    "reputation crisis",
    "abysmal rating",
    "poor star rating",
    "negative review spiral"
]


def _extract_tokens(text: str) -> Set[str]:
    """Extracts lowercase alphabetic/numeric tokens longer than 2 characters excluding stopwords."""
    words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _calculate_token_overlap(
    query: str,
    corpus: str,
    ignore_tokens: Optional[Set[str]] = None
) -> float:
    """Computes the fraction of query tokens present in the corpus text."""
    q_tokens = _extract_tokens(query)
    if ignore_tokens:
        q_tokens = q_tokens - ignore_tokens
    if not q_tokens:
        return 1.0 if not query.strip() else 0.0
    c_tokens = _extract_tokens(corpus)
    if not c_tokens:
        return 0.0
    matched = q_tokens.intersection(c_tokens)
    return len(matched) / len(q_tokens)


def _build_findings_corpus(context: ProspectContext) -> str:
    """
    Builds a text corpus of verified findings, observations, complaints,
    and technical/conversion bottlenecks (excluding general business metadata).
    """
    corpus_parts: List[str] = []

    for bullet in context.summary_bullets:
        corpus_parts.append(bullet)

    for ev in context.evidence:
        corpus_parts.append(ev.claim)
        if ev.value is not None:
            corpus_parts.append(str(ev.value))

    if context.intelligence:
        corpus_parts.extend(getattr(context.intelligence, "bottlenecks", []))
        corpus_parts.extend(getattr(context.intelligence, "recurring_complaints", []))
        corpus_parts.extend(getattr(context.intelligence, "recurring_praise", []))
        corpus_parts.extend(getattr(context.intelligence, "conversion_issues", []))
        if getattr(context.intelligence, "competitor_gap_summary", None):
            corpus_parts.append(context.intelligence.competitor_gap_summary)

    if context.opportunity:
        corpus_parts.extend(getattr(context.opportunity, "detected_pain_points", []))
        corpus_parts.extend(getattr(context.opportunity, "key_findings", []))
        for r in getattr(context.opportunity, "service_recommendations", []):
            corpus_parts.append(r.service_name)
            if hasattr(r, "impact_explanation") and r.impact_explanation:
                corpus_parts.append(r.impact_explanation)
            if hasattr(r, "pitch_angle") and r.pitch_angle:
                corpus_parts.append(r.pitch_angle)

    if context.enrichment:
        if getattr(context.enrichment, "cms", None):
            corpus_parts.append(context.enrichment.cms)
        if getattr(context.enrichment, "frontend_framework", None):
            corpus_parts.append(context.enrichment.frontend_framework)
        corpus_parts.extend(getattr(context.enrichment, "analytics_tools", []))

    return " \n ".join(corpus_parts).lower()


def _build_context_corpus(context: ProspectContext) -> str:
    """Builds a unified text corpus of all verified claims and facts in the ProspectContext."""
    corpus_parts: List[str] = [
        context.business.business_name,
        context.business.category or "",
        context.business.address or "",
        context.business.website or "",
        _build_findings_corpus(context)
    ]
    return " \n ".join(corpus_parts).lower()


class OpportunityEvaluator:
    """
    Evaluates OpportunityAnalysis quality, grounding, consistency, and structural validity.
    """

    VALID_PAIN_CATEGORIES = {
        "conversion", "reputation", "technical", "visibility",
        "infrastructure", "growth", "general"
    }

    def evaluate(
        self,
        context: ProspectContext,
        analysis: OpportunityAnalysis
    ) -> Tuple[ComponentEvaluation, List[HeuristicFlag]]:
        """
        Evaluates an OpportunityAnalysis instance against its ProspectContext.
        Returns a ComponentEvaluation and any generated HeuristicFlags.
        """
        issues: List[str] = []
        heuristic_flags: List[HeuristicFlag] = []
        supported_claims: List[str] = []
        unsupported_claims: List[str] = []

        # -------------------------------------------------------------
        # 1. Structural Validity
        # -------------------------------------------------------------
        structural_validity = True

        if not analysis.executive_diagnosis or len(analysis.executive_diagnosis.strip()) < 10:
            structural_validity = False
            issues.append("executive_diagnosis is empty or too short (< 10 chars)")

        if not analysis.primary_pain_category or analysis.primary_pain_category.lower() not in self.VALID_PAIN_CATEGORIES:
            structural_validity = False
            issues.append(f"primary_pain_category '{analysis.primary_pain_category}' is invalid or unrecognized")

        if not analysis.strategic_pitch_angle or len(analysis.strategic_pitch_angle.strip()) < 5:
            structural_validity = False
            issues.append("strategic_pitch_angle is empty or too short (< 5 chars)")

        if not (0.0 <= analysis.confidence_score <= 1.0):
            structural_validity = False
            issues.append(f"confidence_score {analysis.confidence_score} outside [0.0, 1.0]")

        if analysis.reasoning_mode not in {"ai", "deterministic_fallback"}:
            structural_validity = False
            issues.append(f"reasoning_mode '{analysis.reasoning_mode}' must be 'ai' or 'deterministic_fallback'")

        if analysis.evidence_sufficiency not in {"sufficient", "insufficient"}:
            structural_validity = False
            issues.append(f"evidence_sufficiency '{analysis.evidence_sufficiency}' must be 'sufficient' or 'insufficient'")

        for idx, rec in enumerate(analysis.recommendations):
            if not rec.service_name or not rec.target_problem:
                structural_validity = False
                issues.append(f"recommendation #{idx+1} is missing service_name or target_problem")
            if rec.suggested_pricing_tier not in {"entry", "core", "premium"}:
                structural_validity = False
                issues.append(f"recommendation #{idx+1} tier '{rec.suggested_pricing_tier}' invalid")

        # -------------------------------------------------------------
        # 2. Evidence Grounding & Traceability
        # -------------------------------------------------------------
        findings_corpus = _build_findings_corpus(context)
        name_tokens = _extract_tokens(context.business.business_name)
        cited_points = analysis.cited_evidence_points or []

        if not cited_points:
            if len(context.evidence) >= 2 and analysis.evidence_sufficiency == "sufficient":
                issues.append("No evidence points cited despite available context evidence")
                grounding_score = 0.5
            else:
                grounding_score = 1.0
        else:
            for pt in cited_points:
                pt_clean = pt.strip()
                if not pt_clean:
                    continue
                overlap = _calculate_token_overlap(pt_clean, findings_corpus, ignore_tokens=name_tokens)
                # If direct substring match in findings or >= 35% token overlap against verified findings
                if (findings_corpus and pt_clean.lower() in findings_corpus) or overlap >= 0.35:
                    supported_claims.append(pt_clean)
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="evidence_grounding_verified",
                        status="confirmed_supported",
                        claim=pt_clean,
                        reason=f"Claim matches verified findings with {overlap:.0%} token overlap",
                        severity="info"
                    ))
                else:
                    unsupported_claims.append(pt_clean)
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="unsupported_cited_evidence",
                        status="potentially_unsupported",
                        claim=pt_clean,
                        reason=f"Claim has low ({overlap:.0%}) token overlap with verified context evidence",
                        severity="warning"
                    ))
                    issues.append(f"Cited evidence point lacks context backing: '{pt_clean}'")

            total_evaluated = len(supported_claims) + len(unsupported_claims)
            grounding_score = len(supported_claims) / total_evaluated if total_evaluated > 0 else 1.0

        # -------------------------------------------------------------
        # 3. Evidence Coverage Score
        # -------------------------------------------------------------
        if not context.evidence:
            evidence_coverage_score = 1.0
        else:
            # How many verified evidence items or findings were cited
            max_expected = min(len(context.evidence), 3)
            evidence_coverage_score = min(1.0, len(supported_claims) / max(1, max_expected))

        # -------------------------------------------------------------
        # 4. Consistency & Scorecard Polarity
        # -------------------------------------------------------------
        consistency_score = 1.0
        diag_lower = analysis.executive_diagnosis.lower()

        # Polarity Check 1: sales_opportunity_score high (deficiency) vs unwarranted praise
        if context.scores.sales_opportunity_score >= 70.0:
            for term in PRAISE_TERMS:
                if term in diag_lower:
                    consistency_score -= 0.4
                    issues.append(f"Polarity Contradiction: Praised digital presence ('{term}') while sales_opportunity_score is high ({context.scores.sales_opportunity_score})")
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="polarity_contradiction_praised_deficiency",
                        status="potentially_unsupported",
                        claim=term,
                        reason="Glowing praise contradicts high sales opportunity deficiency score",
                        severity="error"
                    ))
                    break

        # Polarity Check 2: digital_health_rating high vs catastrophic claims
        if context.scores.digital_health_rating >= 85.0:
            for term in CATASTROPHE_TERMS:
                if term in diag_lower:
                    consistency_score -= 0.4
                    issues.append(f"Polarity Contradiction: Diagnosed digital disaster ('{term}') while digital_health_rating is healthy ({context.scores.digital_health_rating})")
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="polarity_contradiction_catastrophic_healthy",
                        status="potentially_unsupported",
                        claim=term,
                        reason="Catastrophic diagnosis contradicts healthy digital rating",
                        severity="error"
                    ))
                    break

        # Check Primary Pain Category alignment with ScoreCard signals
        cat = analysis.primary_pain_category.lower()
        cat_aligned = False
        if cat == "conversion":
            cat_aligned = (context.scores.conversion_friction_score >= 20.0 or
                           any(e.category.lower() == "conversion" for e in context.evidence))
        elif cat == "technical":
            cat_aligned = (context.scores.website_weakness_penalty >= 20.0 or
                           context.scores.seo_weakness_penalty >= 20.0 or
                           any(e.category.lower() == "technical" for e in context.evidence))
        elif cat == "reputation":
            rating = getattr(context.business, "google_rating", None) or getattr(context.business, "rating", None)
            cat_aligned = (rating is not None and rating < 4.2) or (
                context.intelligence and len(context.intelligence.recurring_complaints) > 0
            ) or any(e.category.lower() == "reputation" for e in context.evidence)
        elif cat == "visibility":
            cat_aligned = (context.scores.seo_weakness_penalty >= 20.0 or
                           any(e.category.lower() in {"visibility", "competition"} for e in context.evidence))
        else:
            cat_aligned = True  # Growth/general or insufficient evidence

        if not cat_aligned and analysis.evidence_sufficiency == "sufficient":
            consistency_score -= 0.2
            issues.append(f"primary_pain_category '{cat}' has no backing in ScoreCard penalties or evidence")

        # -------------------------------------------------------------
        # 5. Direct Contradiction Heuristics on Diagnosis
        # -------------------------------------------------------------
        # Missing website contradiction
        if context.business.website and context.business.website.strip().lower() not in {"", "none"}:
            for term in WEBSITE_ABSENCE_TERMS:
                if term in diag_lower:
                    consistency_score -= 0.3
                    issues.append(f"Factual Contradiction: Claimed '{term}' but active website exists ({context.business.website})")
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="contradiction_website_exists",
                        status="potentially_unsupported",
                        claim=term,
                        reason=f"Claim contradicts active website: {context.business.website}",
                        severity="error"
                    ))
                    break

        # Low rating contradiction
        rating = getattr(context.business, "google_rating", None) or getattr(context.business, "rating", None)
        if rating is not None and rating >= 4.2:
            for term in POOR_REPUTATION_TERMS:
                if term in diag_lower:
                    consistency_score -= 0.25
                    issues.append(f"Factual Contradiction: Claimed '{term}' but prospect rating is high ({rating})")
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="contradiction_rating_high",
                        status="potentially_unsupported",
                        claim=term,
                        reason=f"Claim contradicts high verified rating: {rating}",
                        severity="error"
                    ))
                    break

        # -------------------------------------------------------------
        # 6. Commercial Relevance Score
        # -------------------------------------------------------------
        relevance_score = 1.0
        if not analysis.recommendations and analysis.evidence_sufficiency == "sufficient":
            relevance_score -= 0.3
            issues.append("No commercial recommendations provided for sufficient evidence")
        elif analysis.recommendations:
            # Check recommendation quality
            has_impact = any(len(r.commercial_impact.strip()) >= 10 for r in analysis.recommendations)
            if not has_impact:
                relevance_score -= 0.2
                issues.append("Commercial recommendations lack specific impact descriptions")

        # Bound all subscores between 0.0 and 1.0
        grounding_score = max(0.0, min(1.0, grounding_score))
        consistency_score = max(0.0, min(1.0, consistency_score))
        relevance_score = max(0.0, min(1.0, relevance_score))
        evidence_coverage_score = max(0.0, min(1.0, evidence_coverage_score))

        # Overall component score
        comp_score = (
            0.35 * grounding_score +
            0.35 * consistency_score +
            0.15 * relevance_score +
            0.15 * evidence_coverage_score
        )
        if not structural_validity:
            comp_score = min(comp_score, 0.40)
        comp_score = max(0.0, min(1.0, comp_score))

        passed = comp_score >= 0.70 and structural_validity and not any(
            f.severity == "error" for f in heuristic_flags
        )

        evaluation = ComponentEvaluation(
            component_name="opportunity_analysis",
            score=round(comp_score, 3),
            structural_validity=structural_validity,
            grounding_score=round(grounding_score, 3),
            relevance_score=round(relevance_score, 3),
            consistency_score=round(consistency_score, 3),
            evidence_coverage_score=round(evidence_coverage_score, 3),
            supported_claims=supported_claims,
            unsupported_claims=unsupported_claims,
            issues=issues,
            passed=passed
        )

        return evaluation, heuristic_flags


class OutreachEvaluator:
    """
    Evaluates OutreachStrategy quality, evidence grounding, cross-component consistency,
    and factual accuracy against ProspectContext and OpportunityAnalysis.
    """

    def evaluate(
        self,
        context: ProspectContext,
        strategy: OutreachStrategy,
        opportunity_analysis: Optional[OpportunityAnalysis] = None
    ) -> Tuple[ComponentEvaluation, List[HeuristicFlag]]:
        """
        Evaluates an OutreachStrategy instance against its ProspectContext and OpportunityAnalysis.
        Returns a ComponentEvaluation and any generated HeuristicFlags.
        """
        issues: List[str] = []
        heuristic_flags: List[HeuristicFlag] = []
        supported_claims: List[str] = []
        unsupported_claims: List[str] = []

        # -------------------------------------------------------------
        # 1. Structural Validity
        # -------------------------------------------------------------
        structural_validity = True

        if not strategy.positioning_summary or len(strategy.positioning_summary.strip()) < 5:
            structural_validity = False
            issues.append("positioning_summary is empty or too short (< 5 chars)")

        if not strategy.primary_angle or len(strategy.primary_angle.strip()) < 3:
            structural_validity = False
            issues.append("primary_angle is empty or too short (< 3 chars)")

        if not strategy.cold_email_subject or len(strategy.cold_email_subject.strip()) < 3:
            structural_validity = False
            issues.append("cold_email_subject is empty or too short")
        elif len(strategy.cold_email_subject) > 150:
            structural_validity = False
            issues.append("cold_email_subject exceeds max length of 150 chars")

        if not strategy.cold_email_body or len(strategy.cold_email_body.strip()) < 10:
            structural_validity = False
            issues.append("cold_email_body is empty or too short (< 10 chars)")

        if not strategy.whatsapp_message or len(strategy.whatsapp_message.strip()) < 5:
            structural_validity = False
            issues.append("whatsapp_message is empty or too short (< 5 chars)")

        if not (0.0 <= strategy.confidence_score <= 1.0):
            structural_validity = False
            issues.append(f"confidence_score {strategy.confidence_score} outside [0.0, 1.0]")

        if strategy.reasoning_mode not in {"ai", "deterministic_fallback"}:
            structural_validity = False
            issues.append(f"reasoning_mode '{strategy.reasoning_mode}' must be 'ai' or 'deterministic_fallback'")

        if strategy.evidence_sufficiency not in {"sufficient", "insufficient"}:
            structural_validity = False
            issues.append(f"evidence_sufficiency '{strategy.evidence_sufficiency}' must be 'sufficient' or 'insufficient'")

        # -------------------------------------------------------------
        # 2. Evidence Grounding & Traceability
        # -------------------------------------------------------------
        findings_corpus = _build_findings_corpus(context)
        name_tokens = _extract_tokens(context.business.business_name)
        cited_points = strategy.cited_evidence_points or []

        if not cited_points:
            if len(context.evidence) >= 2 and strategy.evidence_sufficiency == "sufficient":
                issues.append("No evidence points cited in outreach despite available context evidence")
                grounding_score = 0.5
            else:
                grounding_score = 1.0
        else:
            for pt in cited_points:
                pt_clean = pt.strip()
                if not pt_clean:
                    continue
                overlap = _calculate_token_overlap(pt_clean, findings_corpus, ignore_tokens=name_tokens)
                if (findings_corpus and pt_clean.lower() in findings_corpus) or overlap >= 0.35:
                    supported_claims.append(pt_clean)
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="outreach_evidence_verified",
                        status="confirmed_supported",
                        claim=pt_clean,
                        reason=f"Outreach claim matches verified findings with {overlap:.0%} token overlap",
                        severity="info"
                    ))
                else:
                    unsupported_claims.append(pt_clean)
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="unsupported_outreach_claim",
                        status="potentially_unsupported",
                        claim=pt_clean,
                        reason=f"Outreach claim has low ({overlap:.0%}) token overlap with verified context evidence",
                        severity="warning"
                    ))
                    issues.append(f"Outreach cited evidence point lacks context backing: '{pt_clean}'")

            total_evaluated = len(supported_claims) + len(unsupported_claims)
            grounding_score = len(supported_claims) / total_evaluated if total_evaluated > 0 else 1.0

        # -------------------------------------------------------------
        # 3. Evidence Coverage Score
        # -------------------------------------------------------------
        if not context.evidence:
            evidence_coverage_score = 1.0
        else:
            max_expected = min(len(context.evidence), 3)
            evidence_coverage_score = min(1.0, len(supported_claims) / max(1, max_expected))

        # -------------------------------------------------------------
        # 4. Consistency: Cross-Component Alignment & Contradictions
        # -------------------------------------------------------------
        consistency_score = 1.0
        outreach_text = f"{strategy.positioning_summary} {strategy.cold_email_subject} {strategy.cold_email_body} {strategy.whatsapp_message} {strategy.strongest_pain_point or ''}".lower()

        # Alignment with OpportunityAnalysis
        if opportunity_analysis:
            # Check pain point alignment
            if strategy.strongest_pain_point:
                opp_corpus = f"{opportunity_analysis.executive_diagnosis} {opportunity_analysis.primary_pain_category} {opportunity_analysis.strategic_pitch_angle}".lower()
                for rec in opportunity_analysis.recommendations:
                    opp_corpus += f" {rec.service_name} {rec.target_problem}"

                pain_overlap = _calculate_token_overlap(strategy.strongest_pain_point, opp_corpus)
                if pain_overlap < 0.20:
                    consistency_score -= 0.30
                    issues.append(f"strongest_pain_point '{strategy.strongest_pain_point}' diverges from OpportunityAnalysis")

            # Check recommended service alignment
            if strategy.recommended_service and opportunity_analysis.recommendations:
                rec_service_names = [r.service_name.lower() for r in opportunity_analysis.recommendations]
                rec_corpus = " ".join(rec_service_names)
                svc_overlap = _calculate_token_overlap(strategy.recommended_service, rec_corpus)
                if svc_overlap < 0.25:
                    consistency_score -= 0.30
                    issues.append(f"recommended_service '{strategy.recommended_service}' does not match OpportunityAnalysis recommendations: {rec_service_names}")

        # Contradiction 1: Missing website claim when website exists
        if context.business.website and context.business.website.strip().lower() not in {"", "none"}:
            for term in WEBSITE_ABSENCE_TERMS:
                if term in outreach_text:
                    consistency_score -= 0.35
                    issues.append(f"Factual Contradiction in Outreach: Claimed '{term}' but website exists ({context.business.website})")
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="contradiction_website_exists",
                        status="potentially_unsupported",
                        claim=term,
                        reason=f"Outreach copy contradicts active website: {context.business.website}",
                        severity="error"
                    ))
                    break

        # Contradiction 2: Low rating claim when rating is high
        rating = getattr(context.business, "google_rating", None) or getattr(context.business, "rating", None)
        if rating is not None and rating >= 4.2:
            for term in POOR_REPUTATION_TERMS:
                if term in outreach_text:
                    consistency_score -= 0.25
                    issues.append(f"Factual Contradiction in Outreach: Claimed '{term}' but rating is {rating}")
                    heuristic_flags.append(HeuristicFlag(
                        flag_type="contradiction_rating_high",
                        status="potentially_unsupported",
                        claim=term,
                        reason=f"Outreach copy contradicts high verified rating: {rating}",
                        severity="error"
                    ))
                    break

        # -------------------------------------------------------------
        # 5. Commercial Relevance Score
        # -------------------------------------------------------------
        relevance_score = 1.0
        # Subject line word count (optimal: 2-10 words)
        subject_words = len(strategy.cold_email_subject.split())
        if subject_words > 15:
            relevance_score -= 0.15
            issues.append(f"Cold email subject line is too long ({subject_words} words)")

        # Body word count (optimal: under 150 words)
        body_words = len(strategy.cold_email_body.split())
        if body_words > 200:
            relevance_score -= 0.20
            issues.append(f"Cold email body exceeds optimal length ({body_words} words)")

        if not strategy.value_proposition:
            relevance_score -= 0.15
            issues.append("Missing value_proposition offer in outreach strategy")

        # Clamp all subscores
        grounding_score = max(0.0, min(1.0, grounding_score))
        consistency_score = max(0.0, min(1.0, consistency_score))
        relevance_score = max(0.0, min(1.0, relevance_score))
        evidence_coverage_score = max(0.0, min(1.0, evidence_coverage_score))

        comp_score = (
            0.35 * grounding_score +
            0.35 * consistency_score +
            0.15 * relevance_score +
            0.15 * evidence_coverage_score
        )
        if not structural_validity:
            comp_score = min(comp_score, 0.40)
        comp_score = max(0.0, min(1.0, comp_score))

        passed = comp_score >= 0.70 and structural_validity and not any(
            f.severity == "error" for f in heuristic_flags
        )

        evaluation = ComponentEvaluation(
            component_name="outreach_strategy",
            score=round(comp_score, 3),
            structural_validity=structural_validity,
            grounding_score=round(grounding_score, 3),
            relevance_score=round(relevance_score, 3),
            consistency_score=round(consistency_score, 3),
            evidence_coverage_score=round(evidence_coverage_score, 3),
            supported_claims=supported_claims,
            unsupported_claims=unsupported_claims,
            issues=issues,
            passed=passed
        )

        return evaluation, heuristic_flags


class EvaluationRunner:
    """
    Main orchestrator for running evaluations across OpportunityAnalysis and OutreachStrategy.
    Aggregates composite metrics and heuristic hallucination flags into an EvaluationResult.
    """

    def __init__(
        self,
        opportunity_evaluator: Optional[OpportunityEvaluator] = None,
        outreach_evaluator: Optional[OutreachEvaluator] = None
    ):
        self.opportunity_evaluator = opportunity_evaluator or OpportunityEvaluator()
        self.outreach_evaluator = outreach_evaluator or OutreachEvaluator()

    def evaluate(
        self,
        context: ProspectContext,
        opportunity_analysis: Optional[OpportunityAnalysis] = None,
        outreach_strategy: Optional[OutreachStrategy] = None
    ) -> EvaluationResult:
        """
        Evaluates AI outputs for a prospect context.
        If opportunity_analysis or outreach_strategy are not explicitly provided,
        they are extracted from context if present.
        """
        opp_analysis = opportunity_analysis or getattr(context, "opportunity_analysis", None)
        out_strategy = outreach_strategy or getattr(context, "outreach_strategy", None)

        all_issues: List[str] = []
        all_heuristic_flags: List[HeuristicFlag] = []
        hallucination_warning_strings: List[str] = []
        structural_valid = True

        opp_eval: Optional[ComponentEvaluation] = None
        out_eval: Optional[ComponentEvaluation] = None

        if opp_analysis:
            opp_eval, opp_flags = self.opportunity_evaluator.evaluate(context, opp_analysis)
            all_issues.extend(opp_eval.issues)
            all_heuristic_flags.extend(opp_flags)
            if not opp_eval.structural_validity:
                structural_valid = False

        if out_strategy:
            out_eval, out_flags = self.outreach_evaluator.evaluate(context, out_strategy, opp_analysis)
            all_issues.extend(out_eval.issues)
            all_heuristic_flags.extend(out_flags)
            if not out_eval.structural_validity:
                structural_valid = False

        # Extract human-readable hallucination flags for warning/error status
        for flag in all_heuristic_flags:
            if flag.status == "potentially_unsupported" or flag.severity in {"warning", "error"}:
                hallucination_warning_strings.append(
                    f"[{flag.flag_type.upper()}] {flag.claim}: {flag.reason}"
                )

        # Compute composite scores
        if opp_eval and out_eval:
            grounding_score = 0.5 * opp_eval.grounding_score + 0.5 * out_eval.grounding_score
            consistency_score = 0.5 * opp_eval.consistency_score + 0.5 * out_eval.consistency_score
            relevance_score = 0.5 * opp_eval.relevance_score + 0.5 * out_eval.relevance_score
            coverage_score = 0.5 * opp_eval.evidence_coverage_score + 0.5 * out_eval.evidence_coverage_score
        elif opp_eval:
            grounding_score = opp_eval.grounding_score
            consistency_score = opp_eval.consistency_score
            relevance_score = opp_eval.relevance_score
            coverage_score = opp_eval.evidence_coverage_score
        elif out_eval:
            grounding_score = out_eval.grounding_score
            consistency_score = out_eval.consistency_score
            relevance_score = out_eval.relevance_score
            coverage_score = out_eval.evidence_coverage_score
        else:
            # Nothing to evaluate
            return EvaluationResult(
                overall_score=0.0,
                grounding_score=0.0,
                relevance_score=0.0,
                consistency_score=0.0,
                evidence_coverage_score=0.0,
                hallucination_flags=[],
                issues=["Neither OpportunityAnalysis nor OutreachStrategy provided for evaluation"],
                passed=False,
                structural_validity=False
            )

        # Calculate overall score with penalty for severe hallucination flags
        base_overall = (
            0.30 * grounding_score +
            0.30 * consistency_score +
            0.20 * relevance_score +
            0.20 * coverage_score
        )

        error_flags_count = sum(1 for f in all_heuristic_flags if f.severity == "error")
        warning_flags_count = sum(1 for f in all_heuristic_flags if f.severity == "warning")

        # Penalize for errors and warnings
        penalty = (0.25 * error_flags_count) + (0.10 * warning_flags_count)
        if not structural_valid:
            penalty += 0.30

        overall_score = max(0.0, min(1.0, base_overall - penalty))

        # Pass condition: overall_score >= 0.70, no severe error flags, and structurally valid
        passed = (
            overall_score >= 0.70 and
            error_flags_count == 0 and
            structural_valid
        )

        return EvaluationResult(
            overall_score=round(overall_score, 3),
            grounding_score=round(grounding_score, 3),
            relevance_score=round(relevance_score, 3),
            consistency_score=round(consistency_score, 3),
            evidence_coverage_score=round(coverage_score, 3),
            hallucination_flags=hallucination_warning_strings,
            issues=all_issues,
            passed=passed,
            structural_validity=structural_valid,
            opportunity_evaluation=opp_eval,
            outreach_evaluation=out_eval,
            heuristic_details=all_heuristic_flags
        )

    def evaluate_batch(
        self,
        fixtures: List[Dict[str, Any]]
    ) -> BatchEvaluationSummary:
        """
        Evaluates a batch of test fixtures.
        Each fixture dict must contain:
        - 'context': ProspectContext
        - 'opportunity_analysis': Optional[OpportunityAnalysis]
        - 'outreach_strategy': Optional[OutreachStrategy]
        """
        results: List[EvaluationResult] = []
        passed_count = 0
        failed_count = 0
        total_hallucinations = 0

        for item in fixtures:
            res = self.evaluate(
                context=item["context"],
                opportunity_analysis=item.get("opportunity_analysis"),
                outreach_strategy=item.get("outreach_strategy")
            )
            results.append(res)
            if res.passed:
                passed_count += 1
            else:
                failed_count += 1
            total_hallucinations += len(res.hallucination_flags)

        total = len(results)
        avg_overall = sum(r.overall_score for r in results) / total if total > 0 else 0.0
        avg_grounding = sum(r.grounding_score for r in results) / total if total > 0 else 0.0
        avg_consistency = sum(r.consistency_score for r in results) / total if total > 0 else 0.0
        avg_relevance = sum(r.relevance_score for r in results) / total if total > 0 else 0.0
        avg_coverage = sum(r.evidence_coverage_score for r in results) / total if total > 0 else 0.0

        return BatchEvaluationSummary(
            total_evaluated=total,
            passed_count=passed_count,
            failed_count=failed_count,
            average_overall_score=round(avg_overall, 3),
            average_grounding_score=round(avg_grounding, 3),
            average_consistency_score=round(avg_consistency, 3),
            average_relevance_score=round(avg_relevance, 3),
            average_evidence_coverage_score=round(avg_coverage, 3),
            total_hallucination_flags=total_hallucinations,
            results=results
        )
