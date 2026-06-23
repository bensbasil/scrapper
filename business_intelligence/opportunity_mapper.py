import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

logger = logging.getLogger("OpportunityMapper")
logger.setLevel(logging.INFO)

@dataclass
class ServiceRecommendation:
    service_name: str
    impact_explanation: str

@dataclass
class OpportunityMappingResult:
    business_name: str
    service_recommendations: List[Dict[str, Any]]
    opportunity_reasoning: str

class OpportunityMapper:
    def __init__(self):
        pass

    def map_opportunities(self, 
                          business_name: str, 
                          web_score: float, 
                          seo_score: float,
                          conversion_friction_score: float,
                          trust_health_score: float,
                          conversion_issues: List[str],
                          competitors_gap: str) -> OpportunityMappingResult:
        logger.info(f"[{business_name}] Mapping issues to concrete services...")
        
        recs: List[ServiceRecommendation] = []
        reasoning_bullets = []

        # 1. Custom Web Redesign / Development
        if web_score > 50 or "No website exists to convert leads" in conversion_issues:
            recs.append(ServiceRecommendation(
                service_name="Custom Responsive Web Development",
                impact_explanation="Build a modern, secure, and fast-loading web landing page to establish local authority and capture mobile visitors."
            ))
            reasoning_bullets.append("Your current website lack of optimization or absence is actively scaring away digital visitors who search for your services.")

        # 2. Online Appointment Scheduler Setup
        if any("booking" in issue.lower() or "scheduler" in issue.lower() for issue in conversion_issues):
            recs.append(ServiceRecommendation(
                service_name="Online Booking & Scheduling Engine",
                impact_explanation="Integrate an automated scheduling flow (e.g. Calendly/Acuity) so clients can reserve slots 24/7 without calling."
            ))
            reasoning_bullets.append("The absence of an online scheduler forces prospects to call during business hours, resulting in significant leak of after-hours leads.")

        # 3. WhatsApp Integration
        if any("whatsapp" in issue.lower() for issue in conversion_issues):
            recs.append(ServiceRecommendation(
                service_name="WhatsApp Chat Widget Integration",
                impact_explanation="Add a direct WhatsApp float button to allow prospects to initiate quick support chats, boosting chat-to-lead rates by 3x."
            ))
            reasoning_bullets.append("Customers in local markets expect instantaneous chat access; lacking WhatsApp blocks a high-intent conversion channel.")

        # 4. Local SEO SEO Campaign
        if seo_score > 40:
            recs.append(ServiceRecommendation(
                service_name="Local SEO Domination Campaign",
                impact_explanation="Optimize meta tags, structural headers, schema markups, and local citations to outrank neighborhood competitors."
            ))
            reasoning_bullets.append("Basic search index metrics are weak (missing H1/metadata), leaving your business invisible to customers searching Google.")

        # 5. Review Widgets & Trust Signals
        if trust_health_score < 40:
            recs.append(ServiceRecommendation(
                service_name="Trust & Reputation Management Setup",
                impact_explanation="Integrate live Google/Trustpilot review badges and social proof sections to build immediate customer trust."
            ))
            reasoning_bullets.append("Lacking visible customer reviews or testimonials makes it hard for new visitors to trust your brand quickly.")

        # Construct reasoning narrative
        if not recs:
            recs.append(ServiceRecommendation(
                service_name="Advanced Marketing Dashboard Integration",
                impact_explanation="Set up client attribution widgets to track traffic channels."
            ))
            narrative = f"[{business_name}] has a strong digital footprint. We recommend optimizing performance with advanced attribution tracking."
        else:
            narrative = f"Reasoning: We audited your digital presence and compared it to local competitors. {competitors_gap} Based on this, we detected critical friction points: {', '.join([b.lower().replace('your ', '').replace('.', '') for b in reasoning_bullets[:2]])}. Fixing these weaknesses will directly recover leaked leads and boost your local monthly revenue."

        # Convert to dictionary array
        recommendations_list = [asdict(r) for r in recs]

        return OpportunityMappingResult(
            business_name=business_name,
            service_recommendations=recommendations_list,
            opportunity_reasoning=narrative
        )
