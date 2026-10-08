"""
ai/opportunity_reasoner.py
--------------------------
AI Opportunity Reasoning service for synthesizing commercial diagnosis,
value proposition, and service recommendations from structured ProspectContext.

Key Architectural Guarantees:
- Consumes ONLY typed ProspectContext (schemas/context.py).
- Communicates with LLMs exclusively via LLMClient (ai/client.py).
- NO direct PostgreSQL, SQL, Playwright, scraping, or raw HTTP connections.
- Strict evidence-grounding: prohibits hallucinating issues absent from evidence.
- Safe, non-fabricated deterministic fallback on LLM unavailability or failure.
"""

import logging
from typing import Optional, List, Dict, Any

from schemas.context import ProspectContext, EvidenceItem
from schemas.ai import OpportunityAnalysis, CommercialRecommendation
from schemas.opportunity import ServiceRecommendation
from ai.client import LLMClient
from ai.exceptions import LLMError

logger = logging.getLogger(__name__)


class OpportunityReasoner:
    """
    Synthesizes executive commercial diagnoses and prioritized service recommendations
    from verified prospect evidence.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def reason(self, context: ProspectContext) -> OpportunityAnalysis:
        """
        Main reasoning entry point.
        Evaluates ProspectContext and produces a validated OpportunityAnalysis.
        Falls back gracefully to deterministic rule-based analysis if LLM is unavailable or fails.
        """
        b_name = context.business.business_name

        # Check for evidence sufficiency first
        if not self._is_evidence_sufficient(context):
            logger.info(f"[{b_name}] Insufficient prospect evidence detected. Producing conservative baseline.")
            return self._build_insufficient_evidence_analysis(context)

        # Attempt structured AI generation if LLM provider is available
        if self.llm_client.is_available:
            try:
                logger.info(f"[{b_name}] Synthesizing AI commercial diagnosis via {self.llm_client.config.provider}...")
                prompt = self._build_reasoning_prompt(context)
                system_prompt = self._build_system_prompt()
                analysis = self.llm_client.generate_structured(
                    prompt=prompt,
                    response_model=OpportunityAnalysis,
                    system_prompt=system_prompt,
                )
                # Ensure reasoning_mode is explicitly marked as AI
                analysis.reasoning_mode = "ai"
                logger.info(f"[{b_name}] AI opportunity reasoning generated successfully.")
                return analysis
            except LLMError as e:
                logger.warning(
                    f"[{b_name}] AI opportunity reasoning failed ({e}). Falling back to deterministic analysis."
                )
            except Exception as e:
                logger.error(
                    f"[{b_name}] Unexpected error during AI opportunity reasoning ({e}). Falling back."
                )
        else:
            logger.info(f"[{b_name}] No AI provider available. Using deterministic opportunity analysis.")

        # Fallback to deterministic analysis
        return self._build_deterministic_fallback(context)

    # -------------------------------------------------------------------------
    # Prompt Construction
    # -------------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Constructs system instructions enforcing factual grounding and semantic accuracy."""
        return """You are a senior B2B digital agency commercial strategist and business analyst.
Your task is to analyze the provided prospect evidence and produce a structured commercial opportunity diagnosis.

CRITICAL RULES:
1. STRICT FACTUAL GROUNDING:
   - You must cite ONLY issues, customer complaints, competitor gaps, or technical flaws explicitly present in the provided evidence.
   - NEVER invent or assume technical defects (e.g. do NOT claim SSL is missing, site is slow, or booking is broken unless stated in the evidence).
   - If the prospect has few digital flaws, acknowledge their baseline strengths rather than fabricating weaknesses.

2. SCORE POLARITY ADHERENCE:
   - 'sales_opportunity_score' (0-100): HIGHER score means WORSE digital condition for the prospect and GREATER sales pitch opportunity for our agency.
   - 'digital_health_rating' (0-100): HIGHER score means HEALTHIER business presence.
   - NEVER praise a prospect with a high sales_opportunity_score (>75) for having 'an exceptional online presence'.

3. DISTINGUISH EVIDENCE FROM RECOMMENDATION:
   - In 'cited_evidence_points', cite exact verifiable facts from the context.
   - In 'recommendations', propose high-ROI commercial services that directly resolve the cited bottlenecks.
   - Clearly categorize the primary pain as: 'conversion', 'reputation', 'technical', 'visibility', or 'infrastructure'.

4. INSUFFICIENT EVIDENCE:
   - If the provided evidence is minimal, ambiguous, or lacks verifiable bottlenecks, set 'evidence_sufficiency' to 'insufficient', 'confidence_score' to <= 0.4, and explicitly state in 'executive_diagnosis' that further data collection is required.
"""

    def _build_reasoning_prompt(self, context: ProspectContext) -> str:
        """Builds structured evidence prompt from ProspectContext."""
        b = context.business
        s = context.scores

        prompt_lines = [
            f"# Prospect Profile: {b.business_name}",
            f"- Industry / Category: {b.category or 'Local Business'}",
            f"- Physical Address: {b.address or 'Not provided'}",
            f"- Website: {b.website or 'No website detected'}",
            "",
            "## Score Metrics (Note Polarities):",
            f"- Sales Opportunity Score: {s.sales_opportunity_score}/100 (Higher = greater digital weakness / sales pitch need)",
            f"- Digital Health Rating: {s.digital_health_rating}/100 (Higher = healthier presence)",
            f"- Buying Intent Score: {s.buying_intent_score}/100 (Urgency: {s.outreach_urgency})",
            f"- Component Penalties (Higher = worse): Website Weakness={s.website_weakness_penalty}/100, SEO Weakness={s.seo_weakness_penalty}/100, Conversion Friction={s.conversion_friction_score}/100",
        ]

        # Enrichment
        if context.enrichment:
            e = context.enrichment
            prompt_lines.append("\n## Technical Stack & Contacts:")
            techs = []
            if getattr(e, "cms", None):
                techs.append(e.cms)
            if getattr(e, "frontend_framework", None):
                techs.append(e.frontend_framework)
            if getattr(e, "analytics_tools", None):
                techs.extend(e.analytics_tools)
            if getattr(e, "tech_stack", None):
                techs.extend([t for t in e.tech_stack if t not in techs])
            if techs:
                prompt_lines.append(f"- Detected Technologies: {', '.join(techs)}")
            if e.decision_maker_name:
                prompt_lines.append(f"- Identified Decision Maker: {e.decision_maker_name}")

        # Intelligence
        if context.intelligence:
            intel = context.intelligence
            prompt_lines.append("\n## Business Intelligence & Market Signals:")
            if intel.recurring_complaints:
                prompt_lines.append(f"- Top Customer Complaints from Reviews: {', '.join(intel.recurring_complaints[:4])}")
            if intel.recurring_praise:
                prompt_lines.append(f"- Customer Praises: {', '.join(intel.recurring_praise[:3])}")
            if intel.competitor_gap_summary:
                prompt_lines.append(f"- Local Competitor Benchmark: {intel.competitor_gap_summary}")
            if intel.trust_signals:
                prompt_lines.append(f"- Trust Deficiencies: {', '.join(intel.trust_signals)}")

        # Intent
        if context.intent:
            it = context.intent
            prompt_lines.append("\n## Intent & Velocity Signals:")
            if it.top_intent_signals:
                prompt_lines.append(f"- Intent Signals: {', '.join(it.top_intent_signals)}")

        # Existing Deterministic Baseline
        if context.opportunity and context.opportunity.service_recommendations:
            recs_text = [r.service_name for r in context.opportunity.service_recommendations]
            prompt_lines.append("\n## Existing Deterministic Recommendations:")
            prompt_lines.append(f"- Baseline Services: {', '.join(recs_text)}")
            if context.opportunity.opportunity_reasoning:
                prompt_lines.append(f"- Baseline Reasoning: {context.opportunity.opportunity_reasoning}")

        # Verifiable Evidence Items
        prompt_lines.append("\n## Verifiable Evidence Items:")
        if context.evidence:
            for item in context.evidence[:15]:
                prompt_lines.append(f"- [{item.category.upper()}] {item.claim} (Source: {item.source})")
        else:
            prompt_lines.append("- No discrete atomic evidence recorded.")

        prompt_lines.append("\nSynthesize this evidence into a structured OpportunityAnalysis.")
        return "\n".join(prompt_lines)

    # -------------------------------------------------------------------------
    # Evidence Sufficiency & Deterministic Fallbacks
    # -------------------------------------------------------------------------

    def _is_evidence_sufficient(self, context: ProspectContext) -> bool:
        """
        Determines whether the ProspectContext contains enough verified evidence
        to perform reliable AI opportunity diagnosis without hallucinating.
        """
        # If there are zero evidence items and zero penalties and zero complaints, evidence is insufficient
        if not context.evidence and context.scores.sales_opportunity_score == 0.0:
            return False
        return True

    def _build_insufficient_evidence_analysis(self, context: ProspectContext) -> OpportunityAnalysis:
        """Generates an explicit insufficient evidence result without fabricating claims."""
        b_name = context.business.business_name
        return OpportunityAnalysis(
            executive_diagnosis=f"Insufficient verified data available for {b_name} to diagnose revenue bottlenecks without live discovery.",
            primary_pain_category="visibility",
            recommendations=[
                CommercialRecommendation(
                    service_name="Comprehensive Digital Audit",
                    target_problem="Missing baseline telemetry and digital presence data",
                    commercial_impact="Establishes definitive digital presence benchmark",
                    suggested_pricing_tier="entry",
                )
            ],
            strategic_pitch_angle="Exploratory Discovery: Offer a free complete digital footprint audit",
            cited_evidence_points=["Insufficient telemetry recorded in prospect evidence context"],
            confidence_score=0.2,
            reasoning_mode="deterministic_fallback",
            evidence_sufficiency="insufficient",
        )

    def _build_deterministic_fallback(self, context: ProspectContext) -> OpportunityAnalysis:
        """
        Builds a safe, non-fabricated OpportunityAnalysis entirely from
        deterministic scores and recommendations already in ProspectContext.
        """
        b_name = context.business.business_name
        s = context.scores
        opp = context.opportunity
        intel = context.intelligence

        # Determine primary pain category from highest penalty score
        if s.conversion_friction_score > 50:
            category = "conversion"
        elif s.seo_weakness_penalty > 50:
            category = "visibility"
        elif s.website_weakness_penalty > 50:
            category = "technical"
        elif intel and intel.recurring_complaints:
            category = "reputation"
        else:
            category = "technical"

        # Transform deterministic service recommendations
        recs: List[CommercialRecommendation] = []
        if opp and opp.service_recommendations:
            for sr in opp.service_recommendations:
                recs.append(
                    CommercialRecommendation(
                        service_name=sr.service_name,
                        target_problem=f"Identified bottleneck in {sr.service_name.lower()}",
                        commercial_impact=sr.impact_explanation,
                        suggested_pricing_tier="core",
                    )
                )

        if not recs:
            recs.append(
                CommercialRecommendation(
                    service_name="Digital Presence Optimization",
                    target_problem="Unoptimized online profile and conversion channels",
                    commercial_impact="Improves customer discovery and local conversion rates",
                    suggested_pricing_tier="entry",
                )
            )

        # Formulate executive diagnosis from deterministic opportunity reasoning
        if opp and opp.opportunity_reasoning:
            diagnosis = opp.opportunity_reasoning
        else:
            diagnosis = (
                f"Deterministic audit: {b_name} presents a sales opportunity score of "
                f"{s.sales_opportunity_score}/100 with principal deficiencies in {category}."
            )

        # Formulate pitch angle from detected pain points
        if opp and opp.detected_pain_points:
            angle = f"Focus on fixing critical customer bottleneck: {opp.detected_pain_points[0]}"
        elif intel and intel.competitor_gap_summary:
            angle = f"Competitor displacement angle: {intel.competitor_gap_summary}"
        else:
            angle = "Foundational digital upgrade and customer conversion recovery"

        # Harvest cited evidence points from verified evidence items
        cited: List[str] = []
        for item in context.evidence[:5]:
            cited.append(f"{item.claim} (via {item.source})")

        if not cited:
            cited = context.summary_bullets[:3] if context.summary_bullets else ["Deterministic pipeline scoring data"]

        return OpportunityAnalysis(
            executive_diagnosis=diagnosis,
            primary_pain_category=category,
            recommendations=recs,
            strategic_pitch_angle=angle,
            cited_evidence_points=cited,
            confidence_score=0.75,
            reasoning_mode="deterministic_fallback",
            evidence_sufficiency="sufficient",
        )
