import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

# ---------------------------------------------------------
# 1. Structured Logging
# ---------------------------------------------------------
class StructuredLogger:
    @staticmethod
    def get_logger(name: str):
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
            
            # Console handler
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            
            # File handler
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            fh = logging.FileHandler(log_dir / "report_generator.log")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        return logger

logger = StructuredLogger.get_logger(__name__)

# ---------------------------------------------------------
# 2. Data Structure
# ---------------------------------------------------------
@dataclass
class BusinessReport:
    """Structured data container for a human-readable business report."""
    business_name: str
    overall_opportunity: str
    website_quality_summary: str
    seo_summary: str
    automation_summary: str
    suggested_services: List[str]
    outreach_angles: List[str]
    improvement_recommendations: List[str]
    raw_text_report: str

# ---------------------------------------------------------
# 3. Report Generator Engine
# ---------------------------------------------------------
class ReportGenerator:
    """
    Translates technical analysis and scoring data into human-readable, 
    business-focused insights to support outreach and sales.
    Prepares data perfectly for future Generative AI email drafting.
    """
    
    def _generate_website_summary(self, analysis: Dict[str, Any], score: Dict[str, Any]) -> str:
        """Converts technical website issues into business-focused language."""
        if not analysis.get("website_exists", False):
            return "This business does not have a professional website, severely limiting their online visibility, credibility, and ability to capture local searches."
            
        issues = []
        if not analysis.get("ssl_enabled", False):
            issues.append("lacks basic security (no SSL), which deters modern customers and triggers 'Not Secure' browser warnings")
        if not analysis.get("mobile_friendly", False):
            issues.append("is not optimized for mobile phones, frustrating users and causing them to bounce to competitors")
            
        if issues:
            return f"The business has a website, but it {', and '.join(issues)}. This directly costs them potential customers."
        return "The website appears structurally sound and secure from a high-level technical view."

    def _generate_seo_summary(self, analysis: Dict[str, Any], score: Dict[str, Any]) -> str:
        """Converts technical SEO issues into business-focused language."""
        if not analysis.get("website_exists", False):
            return "Cannot rank on Google without a central website."
            
        issues = []
        if not analysis.get("meta_title_exists", False) or not analysis.get("meta_description_exists", False):
            issues.append("missing critical metadata that helps Google understand and index their services")
        if not analysis.get("h1_exists", False):
            issues.append("missing primary page headings, confusing both users and search engines")
            
        if issues:
            return f"The site is {', and '.join(issues)}. Because of this, they are likely losing valuable local search traffic."
        return "Basic technical SEO elements are present and properly configured."

    def _generate_automation_summary(self, analysis: Dict[str, Any], score: Dict[str, Any]) -> str:
        """Converts conversion/automation issues into business-focused language."""
        issues = []
        if not analysis.get("contact_form_exists", False):
            issues.append("no way for customers to easily request quotes or send messages directly through the site")
        if not analysis.get("whatsapp_integration", False):
            issues.append("no modern instant messaging or chat options")
            
        if issues:
            return f"Lead capture is weak. There is {', and '.join(issues)}. They are making it too hard for interested customers to contact them."
        return "Adequate lead capture and contact tools are detected."

    def _generate_outreach_angles(self, score: Dict[str, Any]) -> List[str]:
        """Provides actionable sales angles based on detected pain points."""
        angles = []
        services = score.get("likely_service_match", [])
        pain_points = score.get("detected_pain_points", [])
        
        if "No website detected" in pain_points:
            angles.append("Pitch a simple, modern landing page to instantly establish trust and appear on Google.")
        if "SSL missing (Not secure)" in pain_points:
            angles.append("Highlight the 'Not Secure' browser warning and offer a quick security fix to stop scaring away visitors.")
        if "Likely not mobile friendly" in pain_points:
            angles.append("Show them how their site looks broken on mobile phones and pitch a responsive, fast-loading redesign.")
        if "automation" in services:
            angles.append("Pitch an automated lead-capture form or WhatsApp integration to stop losing after-hours leads.")
        if "SEO" in services:
            angles.append("Point out their invisibility on local search and pitch basic SEO optimization to outrank competitors.")
            
        if not angles:
            angles.append("Offer a general digital health-check and an analytics dashboard setup.")
            
        return angles

    def _generate_recommendations(self, score: Dict[str, Any]) -> List[str]:
        """Provides direct, actionable recommendations to fix the issues."""
        recs = []
        pain_points = score.get("detected_pain_points", [])
        
        if "No website detected" in pain_points:
            recs.append("Build a high-converting, mobile-friendly 1-page website.")
        if "SSL missing (Not secure)" in pain_points:
            recs.append("Install an SSL certificate to secure customer data and boost Google rankings.")
        if "Missing meta title" in pain_points or "Missing meta description" in pain_points:
            recs.append("Write keyword-rich titles and descriptions for Google search results.")
        if "No contact form on site" in pain_points:
            recs.append("Implement a smart contact form connected directly to their email or CRM.")
            
        if not recs:
            recs.append("Maintain current digital presence and explore paid advertising or advanced automations.")
            
        return recs

    def generate_report(self, analysis_data: Dict[str, Any], scoring_data: Dict[str, Any]) -> BusinessReport:
        """
        Combines raw analysis and calculated scores into a comprehensive business report.
        Outputs both structured data and a pre-formatted text document.
        """
        b_name = scoring_data.get("business_name", "Unknown Business")
        opp_score = scoring_data.get("opportunity_score", 0)
        
        # 1. Generate Summaries
        web_sum = self._generate_website_summary(analysis_data, scoring_data)
        seo_sum = self._generate_seo_summary(analysis_data, scoring_data)
        auto_sum = self._generate_automation_summary(analysis_data, scoring_data)
        
        # 2. Generate Strategy
        services = scoring_data.get("likely_service_match", [])
        angles = self._generate_outreach_angles(scoring_data)
        recs = self._generate_recommendations(scoring_data)
        
        # 3. Overall Context
        if opp_score >= 70:
            overall = "High Priority Prospect. Their digital presence is severely lacking, causing an immediate loss of revenue and credibility."
        elif opp_score >= 40:
            overall = "Moderate Opportunity. They have a foundational presence but are losing customers due to specific technical or conversion bottlenecks."
        else:
            overall = "Low Opportunity. Their digital fundamentals are solid. Pitching would require advanced services (Paid Ads, complex dashboards)."

        # 4. Generate Formatted Text Document
        text_report = f"""BUSINESS OPPORTUNITY REPORT: {b_name}
Opportunity Score: {opp_score}/100

--- OVERALL SUMMARY ---
{overall}

--- WEBSITE QUALITY ---
{web_sum}

--- SEO ISSUES ---
{seo_sum}

--- CONVERSION WEAKNESSES ---
{auto_sum}

--- SUGGESTED SERVICES ---
{', '.join(services).title() if services else 'Consulting'}

--- OUTREACH ANGLES ---
"""
        for a in angles:
            text_report += f"- {a}\n"
            
        text_report += "\n--- IMPROVEMENT RECOMMENDATIONS ---\n"
        for r in recs:
            text_report += f"- {r}\n"

        logger.info(f"Generated report for {b_name}.")

        return BusinessReport(
            business_name=b_name,
            overall_opportunity=overall,
            website_quality_summary=web_sum,
            seo_summary=seo_sum,
            automation_summary=auto_sum,
            suggested_services=services,
            outreach_angles=angles,
            improvement_recommendations=recs,
            raw_text_report=text_report
        )

if __name__ == "__main__":
    # MVP Execution Test
    test_analysis = {
        "business_name": "Old Plumbing Co",
        "website_url": "http://oldplumbing.com",
        "website_exists": True,
        "ssl_enabled": False,
        "mobile_friendly": False,
        "meta_title_exists": True,
        "meta_description_exists": False,
        "contact_form_exists": False,
        "whatsapp_integration": False,
        "social_links_found": [],
        "h1_exists": False
    }
    
    test_score = {
        "business_name": "Old Plumbing Co",
        "website_url": "http://oldplumbing.com",
        "opportunity_score": 75.0,
        "website_quality_score": 70.0,
        "seo_score": 60.0,
        "automation_need_score": 50.0,
        "likely_service_match": ["web development", "SEO", "automation"],
        "detected_pain_points": [
            "SSL missing (Not secure)",
            "Likely not mobile friendly",
            "No social media links detected",
            "Missing meta description",
            "Missing H1 tag",
            "No contact form on site"
        ]
    }

    generator = ReportGenerator()
    report = generator.generate_report(test_analysis, test_score)
    print(report.raw_text_report)
