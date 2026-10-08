"""
ai/outreach_reasoner.py
-----------------------
AI Outreach Reasoning service for formulating evidence-grounded consultative
outreach strategies, positioning angles, objection handling, and messaging copy.

Key Architectural Guarantees:
- Ingests structured ProspectContext and OpportunityAnalysis.
- Keeps reasoning (strategy, angle, pain points, objections) cleanly separated from template rendering.
- Communicates with LLMs exclusively via LLMClient (ai/client.py).
- NO direct PostgreSQL, SQL, Playwright, scraping, or raw HTTP connections.
- Strict anti-hallucination constraints: references only verified claims.
- Safe, non-fabricated deterministic fallback when LLM is unavailable or fails.
"""

import logging
from typing import Optional, List, Dict, Any

from schemas.context import ProspectContext, EvidenceItem
from schemas.ai import OpportunityAnalysis, OutreachStrategy, CommercialRecommendation
from ai.client import LLMClient
from ai.exceptions import LLMError

logger = logging.getLogger(__name__)


class OutreachReasoner:
    """
    Synthesizes consultative outreach strategies, pitch angles, and objection handling
    from verified prospect evidence and opportunity analyses.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def reason(
        self,
        context: ProspectContext,
        opportunity_analysis: Optional[OpportunityAnalysis] = None,
    ) -> OutreachStrategy:
        """
        Main entry point for outreach strategy reasoning.
        Evaluates ProspectContext and OpportunityAnalysis to produce a validated OutreachStrategy.
        Falls back gracefully to deterministic rule-based strategy if LLM is unavailable or fails.
        """
        b_name = context.business.business_name
        opp_analysis = opportunity_analysis or getattr(context, "opportunity_analysis", None)

        # Check for evidence sufficiency first
        if not self._is_evidence_sufficient(context, opp_analysis):
            logger.info(f"[{b_name}] Insufficient evidence for deep outreach reasoning. Producing exploratory strategy.")
            return self._build_insufficient_evidence_strategy(context, opp_analysis)

        # Attempt structured AI generation if LLM provider is available
        if self.llm_client.is_available:
            try:
                logger.info(f"[{b_name}] Synthesizing AI outreach strategy via {self.llm_client.config.provider}...")
                prompt = self._build_outreach_prompt(context, opp_analysis)
                system_prompt = self._build_system_prompt()
                strategy = self.llm_client.generate_structured(
                    prompt=prompt,
                    response_model=OutreachStrategy,
                    system_prompt=system_prompt,
                )
                strategy.reasoning_mode = "ai"
                logger.info(f"[{b_name}] AI outreach strategy generated successfully.")
                return strategy
            except LLMError as e:
                logger.warning(
                    f"[{b_name}] AI outreach reasoning failed ({e}). Falling back to deterministic strategy."
                )
            except Exception as e:
                logger.error(
                    f"[{b_name}] Unexpected error during AI outreach reasoning ({e}). Falling back."
                )
        else:
            logger.info(f"[{b_name}] No AI provider available. Using deterministic outreach strategy.")

        # Fallback to deterministic strategy
        return self._build_deterministic_fallback(context, opp_analysis)

    # -------------------------------------------------------------------------
    # Prompt Construction
    # -------------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Constructs system instructions enforcing factual grounding and human copywriting."""
        return """You are an elite, consultative B2B sales development strategist and copywriter.
Your goal is to devise a personalized, low-friction outreach strategy based STRICTLY on the provided prospect evidence.

CRITICAL RULES:
1. STRICT FACTUAL GROUNDING:
   - Reference ONLY customer complaints, competitor comparisons, and technical flaws explicitly stated in the context.
   - NEVER fabricate statistics, fake customer feedback, non-existent technical bugs, or unverified revenue numbers.
   - If a decision maker's name is provided in the context, address them directly. If NOT provided, address them professionally as a business leader or team without inventing a name.

2. COPYWRITING STANDARDS (LOW FRICTION, HIGH RELEVANCE):
   - 'cold_email_subject': Punchy, casual, curiosity-driven, under 8 words. No spam triggers (avoid 'guaranteed', '10x', 'free quote').
   - 'cold_email_body': Warm, direct, human tone. Strictly UNDER 120 words. Focus on the impact of the verified problem on their customer experience. Offer a low-friction call-to-action (e.g. 2-minute video mockup or brief teardown).
   - 'whatsapp_message': Informal but respectful, punchy, strictly UNDER 50 words.
   - 'call_opening_hook': 1 sentence conversational opening addressing the primary friction point.
   - 'anticipated_objection' & 'objection_counter': Anticipate their most likely hesitation (e.g. 'we already have an agency' or 'too busy') and provide a gracious, low-pressure counter.

3. STRATEGIC POSITIONING:
   - Define 'primary_angle': Choose a precise angle like 'Customer Voice', 'Invisible Business', 'Leaky Bucket', or 'Competitor Gap'.
   - In 'cited_evidence_points': List the exact verifiable observations directly used in this copy.
"""

    def _build_outreach_prompt(
        self,
        context: ProspectContext,
        opp_analysis: Optional[OpportunityAnalysis],
    ) -> str:
        """Constructs structured evidence prompt combining ProspectContext and OpportunityAnalysis."""
        b = context.business
        s = context.scores

        prompt_lines = [
            f"# Target Prospect: {b.business_name}",
            f"- Industry / Category: {b.category or 'Local Business'}",
            f"- Location: {b.address or 'Local Area'}",
            f"- Website: {b.website or 'No active website detected'}",
        ]

        # Contact info
        if context.enrichment and context.enrichment.decision_maker_name:
            prompt_lines.append(f"- Verified Decision Maker: {context.enrichment.decision_maker_name}")
        else:
            prompt_lines.append("- Verified Decision Maker: Not verified (use generic professional greeting)")

        # Scores & urgency
        prompt_lines.append(
            f"- Sales Opportunity Score: {s.sales_opportunity_score}/100 | Buying Intent: {s.buying_intent_score}/100 ({s.outreach_urgency.upper()})"
        )

        # Opportunity reasoning diagnosis if available
        if opp_analysis:
            prompt_lines.append("\n## Commercial Opportunity Diagnosis:")
            prompt_lines.append(f"- Executive Diagnosis: {opp_analysis.executive_diagnosis}")
            prompt_lines.append(f"- Primary Pain Category: {opp_analysis.primary_pain_category}")
            prompt_lines.append(f"- Strategic Pitch Angle: {opp_analysis.strategic_pitch_angle}")
            if opp_analysis.recommendations:
                recs_str = [f"{r.service_name} ({r.target_problem})" for r in opp_analysis.recommendations]
                prompt_lines.append(f"- Recommended Services: {'; '.join(recs_str)}")
        elif context.opportunity:
            prompt_lines.append("\n## Deterministic Opportunity Baseline:")
            if context.opportunity.opportunity_reasoning:
                prompt_lines.append(f"- Reasoning: {context.opportunity.opportunity_reasoning}")
            if context.opportunity.detected_pain_points:
                prompt_lines.append(f"- Detected Pain Points: {', '.join(context.opportunity.detected_pain_points)}")

        # Business intelligence signals
        if context.intelligence:
            intel = context.intelligence
            prompt_lines.append("\n## Grounded Intelligence Signals:")
            if intel.recurring_complaints:
                prompt_lines.append(f"- Verified Customer Complaints: {', '.join(intel.recurring_complaints[:3])}")
            if intel.competitor_gap_summary:
                prompt_lines.append(f"- Competitor Gap: {intel.competitor_gap_summary}")
            if intel.trust_signals:
                prompt_lines.append(f"- Trust Deficiencies: {', '.join(intel.trust_signals)}")

        # Verifiable evidence items
        prompt_lines.append("\n## Key Verified Evidence Items:")
        if context.evidence:
            for item in context.evidence[:10]:
                prompt_lines.append(f"- {item.claim}")
        else:
            prompt_lines.append("- No discrete atomic evidence recorded.")

        prompt_lines.append("\nSynthesize these inputs into a structured OutreachStrategy.")
        return "\n".join(prompt_lines)

    # -------------------------------------------------------------------------
    # Evidence Sufficiency & Deterministic Fallbacks
    # -------------------------------------------------------------------------

    def _is_evidence_sufficient(
        self,
        context: ProspectContext,
        opp_analysis: Optional[OpportunityAnalysis],
    ) -> bool:
        """Determines whether evidence is sufficient for personalized consultative outreach."""
        if opp_analysis and opp_analysis.evidence_sufficiency == "insufficient":
            return False
        if not context.evidence and context.scores.sales_opportunity_score == 0.0:
            return False
        return True

    def _build_insufficient_evidence_strategy(
        self,
        context: ProspectContext,
        opp_analysis: Optional[OpportunityAnalysis],
    ) -> OutreachStrategy:
        """Constructs safe exploratory outreach strategy when evidence is insufficient."""
        b_name = context.business.business_name
        contact = (
            context.enrichment.decision_maker_name
            if context.enrichment and context.enrichment.decision_maker_name
            else None
        )
        greeting = f"Hi {contact}," if contact else f"Hi {b_name} team,"

        return OutreachStrategy(
            positioning_summary="Exploratory positioning: Introduce agency and offer a complimentary digital health audit.",
            primary_angle="Exploratory Footprint Audit",
            target_decision_maker_type="Business Owner / General Manager",
            strongest_pain_point="Unverified online presence telemetry",
            value_proposition="Establish a baseline audit of online search visibility and customer conversion channels",
            recommended_service="Complimentary Digital Health Assessment",
            cold_email_subject=f"Question regarding {b_name}",
            cold_email_body=(
                f"{greeting}\n\n"
                f"I came across {b_name} while researching local businesses in the area. "
                f"We help local companies optimize their digital channels and customer inquiry pipelines.\n\n"
                f"I put together a quick, complimentary 2-minute overview evaluating your online search visibility. "
                f"Would you be open to me sending that over?\n\n"
                f"Best,\n[Your Name]"
            ),
            whatsapp_message=(
                f"{greeting} I was checking out {b_name} and put together a quick 2-minute video on your local search visibility. Mind if I share it here?"
            ),
            call_opening_hook=f"Hi, I was reviewing {b_name}'s local digital footprint and had a quick observation.",
            anticipated_objection="We are not looking for marketing services right now.",
            objection_counter="Completely understand — this is just a quick 2-minute audit video with actionable insights you can implement yourselves.",
            cited_evidence_points=["Baseline digital footprint audit"],
            confidence_score=0.3,
            reasoning_mode="deterministic_fallback",
            evidence_sufficiency="insufficient",
        )

    def _build_deterministic_fallback(
        self,
        context: ProspectContext,
        opp_analysis: Optional[OpportunityAnalysis],
    ) -> OutreachStrategy:
        """
        Builds a safe, grounded OutreachStrategy derived from existing
        OpportunityAnalysis and ProspectContext without calling an LLM.
        """
        b_name = context.business.business_name
        category = context.business.category or "local business"
        contact = (
            context.enrichment.decision_maker_name
            if context.enrichment and context.enrichment.decision_maker_name
            else None
        )
        salutation = f"Hi {contact}," if contact else f"Hi {b_name} team,"
        short_greeting = f"Hi {contact}!" if contact else f"Hi {b_name} team!"

        # Determine primary pain point and angle
        pain_point = "technical optimization opportunities"
        primary_angle = "Digital Foundation Optimization"
        value_prop = "Recover leaked customer inquiries and improve conversion rates"
        service = "Digital Optimization"

        if opp_analysis:
            primary_angle = opp_analysis.strategic_pitch_angle
            if opp_analysis.recommendations:
                top_rec = opp_analysis.recommendations[0]
                service = top_rec.service_name
                pain_point = top_rec.target_problem
                value_prop = top_rec.commercial_impact
        elif context.opportunity and context.opportunity.detected_pain_points:
            pain_point = context.opportunity.detected_pain_points[0]
            if context.opportunity.service_recommendations:
                service = context.opportunity.service_recommendations[0].service_name

        # Check for complaints or competitor gaps in intelligence
        intel = context.intelligence
        if intel and intel.recurring_complaints:
            pain_point = f"customer feedback regarding {intel.recurring_complaints[0]}"
            primary_angle = "Customer Voice & Reputation Recovery"

        positioning = f"Position as a specialized {service.lower()} consultant focused on resolving {pain_point.lower()}."

        # Construct cold email
        if "website" in pain_point.lower() or not context.business.website:
            subject = f"Question about {b_name}'s digital presence"
            body = (
                f"{salutation}\n\n"
                f"I was looking for {category} in the area and noticed {b_name} doesn't have an active dedicated website set up yet.\n\n"
                f"Without a clean mobile-friendly landing page, potential customers searching locally often end up booking with competitors. "
                f"We build fast, high-converting 1-page sites to solve exactly this.\n\n"
                f"Would you be open to me sending over a quick mockup of what your site could look like? No obligation either way.\n\n"
                f"Best,\n[Your Name]"
            )
            wa_text = (
                f"{short_greeting} I noticed {b_name} doesn't have a website set up yet. Would you be open to a quick, free mockup of what a clean landing page could look like for you?"
            )
        else:
            subject = f"Quick note regarding {b_name}'s website"
            body = (
                f"{salutation}\n\n"
                f"I was browsing {b_name}'s site today while looking for {category} in the area and noticed an issue: {pain_point.lower()}.\n\n"
                f"Usually when this happens, it creates friction for visitors trying to get in touch. "
                f"We specialize in {service.lower()} to help recover those missed opportunities.\n\n"
                f"Would you be opposed to a brief 2-minute video showing exactly how to fix it?\n\n"
                f"Best,\n[Your Name]"
            )
            wa_text = (
                f"{short_greeting} I was checking {b_name}'s website and noticed an issue with {pain_point.lower()}. Mind if I send a quick screenshot and fix walkthrough?"
            )

        # Harvest cited evidence points
        cited = []
        if opp_analysis and opp_analysis.cited_evidence_points:
            cited = opp_analysis.cited_evidence_points[:3]
        elif context.evidence:
            cited = [item.claim for item in context.evidence[:3]]
        else:
            cited = [pain_point]

        return OutreachStrategy(
            positioning_summary=positioning,
            primary_angle=primary_angle,
            target_decision_maker_type="Business Owner / Founder",
            strongest_pain_point=pain_point,
            value_proposition=value_prop,
            recommended_service=service,
            cold_email_subject=subject,
            cold_email_body=body,
            whatsapp_message=wa_text,
            call_opening_hook=f"Hi, calling because I noticed a quick issue with {b_name}'s {pain_point.lower()}.",
            anticipated_objection="We already have a web developer or agency handling this.",
            objection_counter="Totally understand — this is a specific 2-minute fix your current team can implement immediately.",
            cited_evidence_points=cited,
            confidence_score=0.8,
            reasoning_mode="deterministic_fallback",
            evidence_sufficiency="sufficient",
        )
