"""
evaluation/datasets/fixtures.py
-------------------------------
Deterministic synthetic fixtures for AI reasoning evaluation.
Provides 6 standardized scenarios:
1. Strong evidence + good reasoning
2. Strong evidence + poor reasoning
3. Unsupported / hallucinated opportunity claim
4. Opportunity consistent + outreach inconsistent
5. Insufficient evidence
6. Deterministic fallback output
"""

from typing import Dict, Any, Tuple
from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard, EvidenceItem
from schemas.enrichment import BusinessEnrichment
from schemas.intelligence import BusinessIntelligence
from schemas.opportunity import Opportunity, ServiceRecommendation
from schemas.ai import OpportunityAnalysis, CommercialRecommendation, OutreachStrategy


def get_strong_evidence_good_reasoning_fixture() -> Dict[str, Any]:
    """
    Scenario 1: High opportunity prospect, rich verified evidence,
    and high-quality AI reasoning with accurate grounding and consistency.
    """
    business = Business(
        business_name="Apex Plumbing Pros",
        category="Plumber",
        address="123 Pipe Lane, Chicago, IL",
        website="https://apexplumbingpros.com",
        phone="+13125550199",
        google_rating=3.4,
        review_count=55
    )

    scores = ScoreCard(
        sales_opportunity_score=82.0,
        digital_health_rating=35.0,
        conversion_friction_score=78.0,
        website_weakness_penalty=65.0,
        seo_weakness_penalty=55.0,
        automation_need_penalty=70.0,
        buying_intent_score=80.0,
        outreach_urgency="urgent"
    )

    evidence = [
        EvidenceItem(
            category="conversion",
            claim="Mobile booking form fails to load on iOS devices",
            source="ConversionAnalyzer",
            confidence=0.95
        ),
        EvidenceItem(
            category="reputation",
            claim="Recurring customer complaints about missed service appointment callbacks",
            source="ReviewMiner",
            confidence=0.90
        ),
        EvidenceItem(
            category="technical",
            claim="Slow mobile page load speed exceeding 5.8 seconds",
            source="TechnicalAuditor",
            confidence=0.92
        )
    ]

    intelligence = BusinessIntelligence(
        business_name="Apex Plumbing Pros",
        bottlenecks=["Mobile site broken on iPhone", "Poor appointment confirmation flow"],
        recurring_complaints=["Missed callbacks", "Slow mobile booking"],
        competitor_gap_summary="Local competitors provide instant online booking and SMS dispatch confirmation"
    )

    enrichment = BusinessEnrichment(
        business_name="Apex Plumbing Pros",
        decision_maker_name="Mark Vance",
        cms="WordPress"
    )

    opportunity = Opportunity(
        business_name="Apex Plumbing Pros",
        opportunity_score=82.0,
        detected_pain_points=[
            "Mobile booking form failure on iOS",
            "Customer complaints regarding missed callback confirmations"
        ],
        service_recommendations=[
            ServiceRecommendation(
                service_name="Mobile Conversion Optimization",
                impact_explanation="Recovers 15-20 emergency plumbing jobs monthly"
            )
        ]
    )

    context = ProspectContext(
        business=business,
        scores=scores,
        evidence=evidence,
        summary_bullets=[
            "Mobile booking form fails on iOS devices causing lead abandonment",
            "Recurring customer complaints around missed callbacks",
            "Mobile site load speed is 5.8s"
        ],
        intelligence=intelligence,
        enrichment=enrichment,
        opportunity=opportunity
    )

    opportunity_analysis = OpportunityAnalysis(
        executive_diagnosis="Apex Plumbing Pros is leaking emergency plumbing leads due to a broken iOS mobile booking form and unconfirmed customer callbacks.",
        primary_pain_category="conversion",
        strategic_pitch_angle="Mobile Conversion Optimization & Automated Lead Dispatch",
        cited_evidence_points=[
            "Mobile booking form fails to load on iOS devices",
            "Recurring customer complaints about missed service appointment callbacks"
        ],
        recommendations=[
            CommercialRecommendation(
                service_name="Mobile Conversion Optimization",
                target_problem="Mobile booking form failure on iOS devices",
                commercial_impact="Recovers 15-20 lost emergency plumbing calls monthly",
                suggested_pricing_tier="core"
            )
        ],
        confidence_score=0.92,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    outreach_strategy = OutreachStrategy(
        positioning_summary="Consultative teardown demonstrating lost mobile bookings on iOS devices.",
        primary_angle="Leaky Bucket",
        target_decision_maker_type="Business Owner",
        strongest_pain_point="Mobile booking form failure on iOS devices",
        value_proposition="Fix mobile friction and capture 15+ additional booking calls monthly",
        recommended_service="Mobile Conversion Optimization",
        cold_email_subject="Quick fix for Apex Plumbing mobile booking",
        cold_email_body="Hi Mark, noticed that when mobile users try to book an emergency plumber on iOS, the form fails to submit. We recorded a quick 2-minute fix teardown showing how to prevent those lost bookings. Worth a quick look?",
        whatsapp_message="Hi Mark, noticed your mobile booking form is dropping iOS customers. Recorded a quick 2-min fix teardown if helpful.",
        call_opening_hook="Mark, I'm calling because your mobile site is dropping emergency plumbing bookings on iPhones.",
        anticipated_objection="We get plenty of direct calls already.",
        objection_counter="Totally get that—this is strictly capturing customers already landing on your site who leave without calling.",
        cited_evidence_points=["Mobile booking form fails to load on iOS devices"],
        confidence_score=0.90,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    return {
        "name": "strong_evidence_good_reasoning",
        "context": context,
        "opportunity_analysis": opportunity_analysis,
        "outreach_strategy": outreach_strategy
    }


def get_strong_evidence_poor_reasoning_fixture() -> Dict[str, Any]:
    """
    Scenario 2: Rich evidence available, but AI output commits severe
    polarity errors (praising online presence when sales opportunity score is high).
    """
    good_fixture = get_strong_evidence_good_reasoning_fixture()
    context = good_fixture["context"]

    # Poor opportunity reasoning: praises digital presence despite sales_opportunity_score = 82
    poor_opp = OpportunityAnalysis(
        executive_diagnosis="Apex Plumbing Pros demonstrates an exceptional online presence and flawless digital presence with virtually no flaws.",
        primary_pain_category="growth",
        strategic_pitch_angle="National Brand Billboard Campaigns",
        cited_evidence_points=[],
        recommendations=[
            CommercialRecommendation(
                service_name="National Billboard Advertising",
                target_problem="Brand notoriety",
                commercial_impact="Higher national brand visibility",
                suggested_pricing_tier="premium"
            )
        ],
        confidence_score=0.50,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    poor_outreach = OutreachStrategy(
        positioning_summary="Compliment their outstanding digital dominance.",
        primary_angle="Brand Elevation",
        target_decision_maker_type="Marketing Director",
        strongest_pain_point="None identified",
        value_proposition="Become a household name with billboards",
        recommended_service="National Billboard Advertising",
        cold_email_subject="Congratulations on your perfect online presence",
        cold_email_body="Hi team, loved seeing your flawless digital presence. Would you like to buy billboard space across the country?",
        whatsapp_message="Hey team, billboards available for your flawless business.",
        cited_evidence_points=[],
        confidence_score=0.45,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    return {
        "name": "strong_evidence_poor_reasoning",
        "context": context,
        "opportunity_analysis": poor_opp,
        "outreach_strategy": poor_outreach
    }


def get_unsupported_hallucination_fixture() -> Dict[str, Any]:
    """
    Scenario 3: AI hallucinates that the prospect has no website and terrible reviews,
    directly contradicting verified context facts.
    """
    business = Business(
        business_name="Radiant Smile Dental",
        category="Dentist",
        address="450 Grand Ave, Austin, TX",
        website="https://radiantsmiledental.com",
        phone="+15125550188",
        google_rating=4.9,
        review_count=180
    )

    scores = ScoreCard(
        sales_opportunity_score=28.0,
        digital_health_rating=88.0,
        conversion_friction_score=20.0,
        website_weakness_penalty=15.0,
        seo_weakness_penalty=20.0,
        buying_intent_score=40.0,
        outreach_urgency="low"
    )

    evidence = [
        EvidenceItem(
            category="reputation",
            claim="Outstanding 4.9 rating across 180 Google reviews",
            source="ReviewMiner",
            confidence=0.98
        )
    ]

    context = ProspectContext(
        business=business,
        scores=scores,
        evidence=evidence,
        summary_bullets=["Top rated local dental practice with 4.9 stars on Google"]
    )

    # Hallucinated Opportunity: claims missing website and abysmal rating
    hallucinated_opp = OpportunityAnalysis(
        executive_diagnosis="Radiant Smile Dental has no website and is suffering from an abysmal rating and low rating crisis.",
        primary_pain_category="technical",
        strategic_pitch_angle="Emergency Website Rebuilding",
        cited_evidence_points=[
            "No website found for Radiant Smile Dental",
            "Missing SSL certificate on checkout portal"
        ],
        recommendations=[
            CommercialRecommendation(
                service_name="Custom Web Development",
                target_problem="Prospect lacks a website",
                commercial_impact="Establishes first digital web presence",
                suggested_pricing_tier="premium"
            )
        ],
        confidence_score=0.85,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    hallucinated_outreach = OutreachStrategy(
        positioning_summary="Urgent warning about having no website and terrible reviews.",
        primary_angle="Trust Deficit",
        strongest_pain_point="Lacks a website and has terrible reviews",
        value_proposition="Build your first website and fix your bad rating",
        recommended_service="Custom Web Development",
        cold_email_subject="Why Radiant Smile Dental has no website",
        cold_email_body="Hi team, noticed you currently have no website and poor reviews online. We can build your first site in 7 days.",
        whatsapp_message="Notice you have no website online. We can build one quickly.",
        cited_evidence_points=["No website found for Radiant Smile Dental"],
        confidence_score=0.80,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    return {
        "name": "unsupported_hallucination",
        "context": context,
        "opportunity_analysis": hallucinated_opp,
        "outreach_strategy": hallucinated_outreach
    }


def get_opportunity_consistent_outreach_inconsistent_fixture() -> Dict[str, Any]:
    """
    Scenario 4: OpportunityAnalysis is grounded and accurate, but OutreachStrategy
    diverges completely (switches pain point to an unsupported tech flaw and recommends an unaligned service).
    """
    good_fixture = get_strong_evidence_good_reasoning_fixture()
    context = good_fixture["context"]
    opp_analysis = good_fixture["opportunity_analysis"]

    # Divergent Outreach: pitches WordPress security instead of mobile conversion
    divergent_outreach = OutreachStrategy(
        positioning_summary="Aggressive security warning pitch.",
        primary_angle="Security Breach Risk",
        strongest_pain_point="Critical SQL injection vulnerability in MySQL database",
        value_proposition="Enterprise Cyber Security Audit & Firewall Migration",
        recommended_service="Enterprise Cyber Security Audit",
        cold_email_subject="Urgent: Your MySQL database security vulnerability",
        cold_email_body="Hi team, we detected an unpatched SQL vulnerability in your backend database that could expose patient records.",
        whatsapp_message="Warning: database vulnerability detected on your servers.",
        cited_evidence_points=["Critical SQL injection vulnerability in MySQL database"],
        confidence_score=0.75,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient"
    )

    return {
        "name": "opportunity_consistent_outreach_inconsistent",
        "context": context,
        "opportunity_analysis": opp_analysis,
        "outreach_strategy": divergent_outreach
    }


def get_insufficient_evidence_fixture() -> Dict[str, Any]:
    """
    Scenario 5: Prospect with minimal data (no reviews, no technical audits, no complaints).
    Outputs should reflect cautious, exploratory reasoning without hallucinations.
    """
    business = Business(
        business_name="Blue Sky Painter",
        category="Painter",
        address="Rural Route 4, Boise, ID"
    )

    scores = ScoreCard(
        sales_opportunity_score=50.0,
        digital_health_rating=50.0
    )

    context = ProspectContext(
        business=business,
        scores=scores,
        evidence=[],
        summary_bullets=[]
    )

    cautious_opp = OpportunityAnalysis(
        executive_diagnosis="Insufficient prospect evidence available to formulate a definitive commercial diagnosis.",
        primary_pain_category="general",
        strategic_pitch_angle="Discovery & Business Introduction",
        cited_evidence_points=[],
        recommendations=[],
        confidence_score=0.40,
        reasoning_mode="deterministic_fallback",
        evidence_sufficiency="insufficient"
    )

    cautious_outreach = OutreachStrategy(
        positioning_summary="Exploratory outreach to learn about current painter scheduling.",
        primary_angle="Exploratory Introduction",
        target_decision_maker_type="Owner",
        strongest_pain_point="General scheduling and quote workflow",
        value_proposition="Streamline quoting and customer response times",
        recommended_service="Digital Lead Management Teardown",
        cold_email_subject="Quick question for Blue Sky Painter",
        cold_email_body="Hi team, reaching out to learn how you currently handle customer quote requests during your peak painting season. Open to connecting?",
        whatsapp_message="Hi team, quick question about your painting quote requests. Open to a brief chat?",
        cited_evidence_points=[],
        confidence_score=0.50,
        reasoning_mode="deterministic_fallback",
        evidence_sufficiency="insufficient"
    )

    return {
        "name": "insufficient_evidence",
        "context": context,
        "opportunity_analysis": cautious_opp,
        "outreach_strategy": cautious_outreach
    }


def get_deterministic_fallback_fixture() -> Dict[str, Any]:
    """
    Scenario 6: Deterministic fallback output generated rule-based when LLM is unavailable.
    """
    good_fixture = get_strong_evidence_good_reasoning_fixture()
    context = good_fixture["context"]

    fallback_opp = OpportunityAnalysis(
        executive_diagnosis="Deterministic diagnosis: High sales opportunity identified based on conversion friction score of 78.0/100.",
        primary_pain_category="conversion",
        strategic_pitch_angle="Automated Lead Capture",
        cited_evidence_points=["Mobile booking form fails on iOS devices causing lead abandonment"],
        recommendations=[
            CommercialRecommendation(
                service_name="Mobile Conversion Optimization",
                target_problem="Broken mobile booking flow",
                commercial_impact="Recovers 15-20 emergency plumbing jobs monthly",
                suggested_pricing_tier="core"
            )
        ],
        confidence_score=0.70,
        reasoning_mode="deterministic_fallback",
        evidence_sufficiency="sufficient"
    )

    fallback_outreach = OutreachStrategy(
        positioning_summary="Deterministic outreach strategy targeting verified conversion bottlenecks.",
        primary_angle="Leaky Bucket",
        strongest_pain_point="Broken mobile booking flow",
        value_proposition="Plug mobile lead leaks and increase customer conversion",
        recommended_service="Mobile Conversion Optimization",
        cold_email_subject="Fixing booking friction for Apex Plumbing Pros",
        cold_email_body="Hi team, noticed friction on your mobile booking flow that might be costing you calls. Would you be open to a brief breakdown of where leads drop off?",
        whatsapp_message="Hi team, noticed booking friction on your site. Happy to share a quick teardown.",
        cited_evidence_points=["Mobile booking form fails on iOS devices causing lead abandonment"],
        confidence_score=0.70,
        reasoning_mode="deterministic_fallback",
        evidence_sufficiency="sufficient"
    )

    return {
        "name": "deterministic_fallback",
        "context": context,
        "opportunity_analysis": fallback_opp,
        "outreach_strategy": fallback_outreach
    }


def get_all_synthetic_fixtures() -> Dict[str, Dict[str, Any]]:
    """Returns a dictionary of all 6 standard synthetic fixtures."""
    return {
        "strong_evidence_good_reasoning": get_strong_evidence_good_reasoning_fixture(),
        "strong_evidence_poor_reasoning": get_strong_evidence_poor_reasoning_fixture(),
        "unsupported_hallucination": get_unsupported_hallucination_fixture(),
        "opportunity_consistent_outreach_inconsistent": get_opportunity_consistent_outreach_inconsistent_fixture(),
        "insufficient_evidence": get_insufficient_evidence_fixture(),
        "deterministic_fallback": get_deterministic_fallback_fixture()
    }
