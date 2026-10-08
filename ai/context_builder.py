"""
ai/context_builder.py
---------------------
Dedicated context-building component for assembling Phase 1 pipeline data
into a unified, typed, token-efficient ProspectContext (schemas/context.py).

Responsibilities:
- Ingests structured domain entities and dictionaries from pipeline stages.
- Resolves metric polarities (sales_opportunity_score vs digital_health_rating).
- Extracts verifiable EvidenceItem records with clear source attribution.
- Synthesizes compact summary bullets.
- Performs pure assembly: NO LLM calls, NO HTTP, NO SQL, NO Playwright.
"""

from typing import Optional, List, Dict, Any
from dataclasses import is_dataclass, asdict

from schemas.business import Business
from schemas.enrichment import (
    BusinessEnrichment,
    ValidatedEmail,
    DecisionMakerCandidate,
)
from schemas.intelligence import (
    BusinessIntelligence,
    CompetitorComparison,
)
from schemas.intent import IntentProfile
from schemas.opportunity import Opportunity, ServiceRecommendation
from schemas.context import EvidenceItem, ScoreCard, ProspectContext


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Helper to safely convert dataclasses, Pydantic models, or dicts to plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return {}


class ProspectContextBuilder:
    """
    Assembles pipeline stage outputs into a validated, typed ProspectContext.
    Operates as a pure in-memory transformation service.
    """

    def build_context(
        self,
        business_data: Optional[Any] = None,
        analysis_data: Optional[Any] = None,
        seo_data: Optional[Any] = None,
        scoring_data: Optional[Any] = None,
        tech_data: Optional[Any] = None,
        email_data: Optional[Any] = None,
        decision_data: Optional[Any] = None,
        social_data: Optional[Any] = None,
        registry_data: Optional[Any] = None,
        freshness_data: Optional[Any] = None,
        hiring_data: Optional[Any] = None,
        review_trend_data: Optional[Any] = None,
        intent_data: Optional[Any] = None,
        conversion_data: Optional[Any] = None,
        review_mine_data: Optional[Any] = None,
        pain_data: Optional[Any] = None,
        competitor_data: Optional[Any] = None,
        trust_data: Optional[Any] = None,
        health_data: Optional[Any] = None,
        opportunity_data: Optional[Any] = None,
    ) -> ProspectContext:
        """
        Builds a comprehensive, validated ProspectContext from any subset
        of pipeline stage data, handling missing stages gracefully.
        """
        b_dict = _to_dict(business_data)
        a_dict = _to_dict(analysis_data)
        seo_dict = _to_dict(seo_data)
        s_dict = _to_dict(scoring_data)
        t_dict = _to_dict(tech_data)
        e_dict = _to_dict(email_data)
        d_dict = _to_dict(decision_data)
        soc_dict = _to_dict(social_data)
        reg_dict = _to_dict(registry_data)
        f_dict = _to_dict(freshness_data)
        h_dict = _to_dict(hiring_data)
        rt_dict = _to_dict(review_trend_data)
        i_dict = _to_dict(intent_data)
        c_dict = _to_dict(conversion_data)
        rm_dict = _to_dict(review_mine_data)
        p_dict = _to_dict(pain_data)
        comp_dict = _to_dict(competitor_data)
        tr_dict = _to_dict(trust_data)
        hlth_dict = _to_dict(health_data)
        opp_dict = _to_dict(opportunity_data)

        # 1. Identity Resolution
        b_name = (
            b_dict.get("business_name")
            or a_dict.get("business_name")
            or s_dict.get("business_name")
            or "Unknown Business"
        )
        website = (
            b_dict.get("website")
            or a_dict.get("website_url")
            or s_dict.get("website_url")
        )

        business_model = Business(
            id=b_dict.get("id"),
            business_name=b_name,
            category=b_dict.get("category"),
            address=b_dict.get("address"),
            phone=b_dict.get("phone"),
            website=website,
            google_rating=float(b_dict["google_rating"]) if b_dict.get("google_rating") is not None else None,
            review_count=int(b_dict["review_count"]) if b_dict.get("review_count") is not None else None,
            source_platforms=b_dict.get("source_platforms") or ["gmaps"],
            outreach_status=b_dict.get("outreach_status") or "new",
            recrawl_tier=b_dict.get("recrawl_tier") or "tier3",
        )

        # 2. Normalized ScoreCard (Explicit Polarity Preservation)
        sales_opp_score = float(s_dict.get("opportunity_score", 0.0))
        digital_health = float(hlth_dict.get("overall_health_score", 0.0))
        web_weakness = float(s_dict.get("website_quality_score", 0.0))
        seo_weakness = float(s_dict.get("seo_score", 0.0))
        auto_need = float(s_dict.get("automation_need_score", 0.0))
        conv_friction = float(c_dict.get("conversion_friction_score", 0.0))
        buying_intent = float(i_dict.get("intent_score", 0.0))
        urgency = i_dict.get("outreach_urgency", "normal")
        if urgency not in ("urgent", "high", "normal", "low"):
            urgency = "normal"

        score_card = ScoreCard(
            sales_opportunity_score=sales_opp_score,
            digital_health_rating=digital_health,
            website_weakness_penalty=web_weakness,
            seo_weakness_penalty=seo_weakness,
            automation_need_penalty=auto_need,
            conversion_friction_score=conv_friction,
            buying_intent_score=buying_intent,
            outreach_urgency=urgency,
        )

        # 3. Enrichment Model
        enrichment_model: Optional[BusinessEnrichment] = None
        if t_dict or e_dict or d_dict or soc_dict:
            # Parse validated emails
            validated_emails: List[ValidatedEmail] = []
            for em in e_dict.get("extracted_emails", []):
                if isinstance(em, dict) and "email" in em:
                    validated_emails.append(
                        ValidatedEmail(
                            email=em["email"],
                            syntax_valid=em.get("syntax_valid", True),
                            mx_record_exists=em.get("mx_record_exists", True),
                            confidence_score=em.get("confidence_score", 1.0),
                        )
                    )

            # Parse decision makers
            decision_makers: List[DecisionMakerCandidate] = []
            for dm in d_dict.get("candidates", []):
                if isinstance(dm, dict) and "name" in dm:
                    decision_makers.append(
                        DecisionMakerCandidate(
                            name=dm["name"],
                            role=dm.get("role"),
                            source=dm.get("source"),
                            confidence=dm.get("confidence", 0.5),
                        )
                    )

            best_dm_name = decision_makers[0].name if decision_makers else d_dict.get("decision_maker_name")

            enrichment_model = BusinessEnrichment(
                business_name=b_name,
                website_url=website,
                cms=t_dict.get("cms"),
                frontend_framework=t_dict.get("frontend_framework"),
                analytics_tools=t_dict.get("analytics_tools", []),
                validated_emails=validated_emails,
                decision_maker_name=best_dm_name,
                decision_makers=decision_makers,
                social_activity_score=float(soc_dict.get("social_activity_score", 0.0)),
            )

        # 4. Intelligence Model
        intelligence_model: Optional[BusinessIntelligence] = None
        if c_dict or rm_dict or p_dict or comp_dict or tr_dict or hlth_dict:
            competitors_list: List[CompetitorComparison] = []
            for comp in comp_dict.get("competitors", []):
                if isinstance(comp, dict) and "name" in comp:
                    competitors_list.append(
                        CompetitorComparison(
                            name=comp["name"],
                            website=comp.get("website"),
                            rating=comp.get("google_rating") or comp.get("rating"),
                            opportunity_score=float(comp.get("opportunity_score", 0.0)),
                            score_gap=float(comp.get("score_gap", 0.0)),
                        )
                    )

            complaints = (
                p_dict.get("recurring_complaints")
                or rm_dict.get("recurring_complaints")
                or []
            )
            praises = (
                p_dict.get("recurring_praise")
                or rm_dict.get("recurring_praise")
                or []
            )

            intelligence_model = BusinessIntelligence(
                business_name=b_name,
                overall_health_score=digital_health,
                website_health_score=float(hlth_dict.get("website_health_score", 0.0)),
                conversion_health_score=float(c_dict.get("conversion_health_score", 0.0)),
                conversion_friction_score=conv_friction,
                booking_flow_exists=bool(c_dict.get("booking_flow_exists", False)),
                weak_ctas=bool(c_dict.get("weak_ctas", False)),
                lead_capture_form_exists=bool(c_dict.get("lead_capture_form_exists", False)),
                contact_friction=bool(c_dict.get("contact_friction", False)),
                whatsapp_available=bool(c_dict.get("whatsapp_available", False)),
                conversion_issues=c_dict.get("conversion_issues", []),
                review_health_score=float(rm_dict.get("review_health_score", 0.0)),
                pain_score=float(p_dict.get("pain_score", 0.0)),
                recurring_complaints=complaints,
                recurring_praise=praises,
                common_themes=rm_dict.get("common_themes", []),
                bottlenecks=p_dict.get("bottlenecks", []),
                pain_summary=p_dict.get("pain_summary") or rm_dict.get("pain_summary"),
                trust_health_score=float(tr_dict.get("trust_health_score", 0.0)),
                trust_signals=tr_dict.get("trust_signals", []),
                competitor_gap_summary=comp_dict.get("competitor_gap_summary"),
                competitors=competitors_list,
            )

        # 5. Intent Model
        intent_model: Optional[IntentProfile] = None
        if i_dict or h_dict or f_dict or rt_dict:
            intent_model = IntentProfile(
                business_id=b_dict.get("id") or i_dict.get("business_id"),
                business_name=b_name,
                intent_score=buying_intent,
                hiring_signal_score=float(h_dict.get("hiring_signal_score") or i_dict.get("hiring_signal_score", 0.0)),
                review_trend_score=float(rt_dict.get("review_trend_score") or i_dict.get("review_trend_score", 0.0)),
                freshness_score=float(f_dict.get("freshness_score") or i_dict.get("freshness_score", 0.0)),
                opportunity_score=sales_opp_score,
                top_intent_signals=i_dict.get("top_intent_signals", []),
                outreach_urgency=urgency,
                evaluated_at=i_dict.get("evaluated_at"),
            )

        # 6. Opportunity Model
        opportunity_model: Optional[Opportunity] = None
        if s_dict or opp_dict:
            recs_list: List[ServiceRecommendation] = []
            for r in opp_dict.get("service_recommendations", []):
                if isinstance(r, dict) and "service_name" in r:
                    recs_list.append(
                        ServiceRecommendation(
                            service_name=r["service_name"],
                            impact_explanation=r.get("impact_explanation", ""),
                        )
                    )

            opportunity_model = Opportunity(
                business_name=b_name,
                website_url=website,
                opportunity_score=sales_opp_score,
                website_quality_score=web_weakness,
                seo_score=seo_weakness,
                automation_need_score=auto_need,
                detected_pain_points=s_dict.get("detected_pain_points", []),
                likely_service_match=s_dict.get("likely_service_match", []),
                service_recommendations=recs_list,
                opportunity_reasoning=opp_dict.get("opportunity_reasoning"),
            )

        # 7. Atomic Evidence Extraction & Provenance
        evidence_items: List[EvidenceItem] = []
        summary_bullets: List[str] = []

        # Technical Evidence
        if a_dict:
            has_web = a_dict.get("website_exists", False)
            if not has_web:
                claim = "No active dedicated website found"
                evidence_items.append(
                    EvidenceItem(category="technical", claim=claim, source="WebsiteAnalyzer", value=False)
                )
                summary_bullets.append("Critical: Business does not have an active website.")
            else:
                evidence_items.append(
                    EvidenceItem(category="technical", claim=f"Website detected at {website}", source="WebsiteAnalyzer", value=website)
                )
                if not a_dict.get("ssl_enabled", True):
                    claim = "Website lacks SSL certificate ('Not Secure' browser warning)"
                    evidence_items.append(
                        EvidenceItem(category="technical", claim=claim, source="WebsiteAnalyzer", value=False)
                    )
                    summary_bullets.append("Security issue: SSL missing, triggering browser warnings.")
                if not a_dict.get("mobile_friendly", True):
                    claim = "Website layout is not optimized for mobile devices"
                    evidence_items.append(
                        EvidenceItem(category="technical", claim=claim, source="WebsiteAnalyzer", value=False)
                    )
                    summary_bullets.append("UX flaw: Site is not mobile-responsive.")

        # CMS & Tech Stack Evidence
        if t_dict:
            if t_dict.get("cms"):
                cms = t_dict["cms"]
                evidence_items.append(
                    EvidenceItem(category="technical", claim=f"Built on {cms} CMS", source="TechStackDetector", value=cms)
                )
            if t_dict.get("frontend_framework"):
                fw = t_dict["frontend_framework"]
                evidence_items.append(
                    EvidenceItem(category="technical", claim=f"Frontend built with {fw}", source="TechStackDetector", value=fw)
                )

        # Conversion Friction Evidence
        if c_dict:
            if not c_dict.get("booking_flow_exists", False):
                claim = "Missing online appointment booking or reservation engine"
                evidence_items.append(
                    EvidenceItem(category="conversion", claim=claim, source="ConversionAnalyzer", value=False)
                )
                summary_bullets.append("Conversion leak: No 24/7 online booking flow.")
            if not c_dict.get("whatsapp_available", False):
                claim = "No WhatsApp instant chat widget integrated"
                evidence_items.append(
                    EvidenceItem(category="conversion", claim=claim, source="ConversionAnalyzer", value=False)
                )
            for issue in c_dict.get("conversion_issues", []):
                evidence_items.append(
                    EvidenceItem(category="conversion", claim=f"Conversion friction: {issue}", source="ConversionAnalyzer", value=issue)
                )

        # Customer Reputation Evidence
        if rm_dict or p_dict:
            complaints = rm_dict.get("recurring_complaints") or p_dict.get("recurring_complaints") or []
            for c in complaints:
                evidence_items.append(
                    EvidenceItem(category="reputation", claim=f"Customer complaint: '{c}'", source="ReviewMiner", value=c)
                )
                if len(summary_bullets) < 5:
                    summary_bullets.append(f"Customer pain: '{c}'")

            pain_sum = p_dict.get("pain_summary") or rm_dict.get("pain_summary")
            if pain_sum:
                evidence_items.append(
                    EvidenceItem(category="reputation", claim=f"Pain theme: {pain_sum}", source="CustomerPainExtractor", value=pain_sum)
                )

        # Review Trend Evidence
        if rt_dict:
            delta = rt_dict.get("rating_delta")
            trend_dir = rt_dict.get("trend_direction")
            if trend_dir == "declining" and delta is not None:
                claim = f"Rating is declining ({delta:+.1f} drop over recent snapshot)"
                evidence_items.append(
                    EvidenceItem(category="reputation", claim=claim, source="ReviewTrendDetector", value=delta)
                )
                summary_bullets.append(f"Reputation risk: {claim}.")

        # Competitor Gap Evidence
        if comp_dict and comp_dict.get("competitor_gap_summary"):
            gap = comp_dict["competitor_gap_summary"]
            evidence_items.append(
                EvidenceItem(category="competition", claim=f"Local competitive gap: {gap}", source="CompetitorAnalyzer", value=gap)
            )
            summary_bullets.append(f"Competitive pressure: {gap}")

        # Intent Evidence
        if h_dict and h_dict.get("is_hiring"):
            roles = h_dict.get("hiring_roles", [])
            claim = f"Active hiring detected for technical roles: {', '.join(roles)}" if roles else "Active hiring detected"
            evidence_items.append(
                EvidenceItem(category="intent", claim=claim, source="HiringSignalDetector", value=roles)
            )
            summary_bullets.append(f"Buying intent: {claim}.")

        if f_dict and f_dict.get("copyright_year"):
            cpy = f_dict["copyright_year"]
            claim = f"Stale website copyright footer ({cpy})"
            evidence_items.append(
                EvidenceItem(category="intent", claim=claim, source="FreshnessMonitor", value=cpy)
            )

        # Service Opportunity Evidence
        if opp_dict:
            for rec in opp_dict.get("service_recommendations", []):
                if isinstance(rec, dict) and "service_name" in rec:
                    claim = f"Recommended Pitch: {rec['service_name']} ({rec.get('impact_explanation', '')})"
                    evidence_items.append(
                        EvidenceItem(category="opportunity", claim=claim, source="OpportunityMapper", value=rec)
                    )

        # Ensure summary_bullets has at least 1-2 items if empty
        if not summary_bullets:
            if sales_opp_score > 60:
                summary_bullets.append(f"High digital sales opportunity detected (score: {sales_opp_score}/100).")
            else:
                summary_bullets.append(f"Prospect audited with opportunity score {sales_opp_score}/100.")

        return ProspectContext(
            business=business_model,
            scores=score_card,
            enrichment=enrichment_model,
            intelligence=intelligence_model,
            intent=intent_model,
            opportunity=opportunity_model,
            evidence=evidence_items,
            summary_bullets=summary_bullets[:6],
        )
