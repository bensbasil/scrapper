"""
application/capabilities/website_audit.py
-----------------------------------------
Typed application capability for website and technical auditing.
Delegates to WebsiteAnalyzer and TechSignalAnalyzer.
"""

import logging
from typing import Optional, Any
from dataclasses import asdict

from application.contracts.inputs import AuditWebsiteTechInput
from application.contracts.outputs import AuditWebsiteTechOutput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class AuditWebsiteTechCapability:
    """
    Analyzes website responsiveness, load speed, forms, DNS, and SSL.
    Classified as READ: external website inspection without persistent mutations.
    """
    NAME = "audit_website_tech"
    DESCRIPTION = "Performs DOM, tech stack, and network audits on a prospect website"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, website_analyzer: Optional[Any] = None, tech_analyzer: Optional[Any] = None):
        self._website_analyzer = website_analyzer
        self._tech_analyzer = tech_analyzer

    def execute(self, params: AuditWebsiteTechInput) -> AuditWebsiteTechOutput:
        """
        Executes technical audit on candidate website URL.
        """
        url = params.website_url.strip()
        name = params.business_name.strip()
        logger.info(f"[Capability:{self.NAME}] Auditing website for '{name}': {url}")

        w_analyzer = self._website_analyzer
        if w_analyzer is None:
            from scraper.connectors.public_web.company_website import WebsiteAnalyzer
            w_analyzer = WebsiteAnalyzer()

        t_analyzer = self._tech_analyzer
        if t_analyzer is None:
            from scraper.connectors.technical.tech_signals import TechSignalAnalyzer
            t_analyzer = TechSignalAnalyzer()

        analysis_dict = {}
        try:
            analysis_obj = w_analyzer.analyze(url)
            analysis_dict = asdict(analysis_obj) if hasattr(analysis_obj, "__dataclass_fields__") else dict(analysis_obj)
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] WebsiteAnalyzer failed for {url}: {e}")

        tech_dict = {}
        try:
            tech_obj = t_analyzer.analyze(url)
            tech_dict = asdict(tech_obj) if hasattr(tech_obj, "__dataclass_fields__") else dict(tech_obj)
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] TechSignalAnalyzer failed for {url}: {e}")

        # Consolidate results into typed output contract
        has_ssl = bool(tech_dict.get("ssl_valid") or tech_dict.get("has_ssl") or url.startswith("https"))
        is_active = bool(analysis_dict.get("website_active", False) or tech_dict.get("dns_resolves", False))
        is_mobile = bool(analysis_dict.get("mobile_friendly", False))

        return AuditWebsiteTechOutput(
            business_name=name,
            website_url=url,
            is_active=is_active,
            has_ssl=has_ssl,
            is_mobile_friendly=is_mobile,
            page_load_speed_seconds=analysis_dict.get("load_time_seconds"),
            cms=analysis_dict.get("cms"),
            tech_stack=analysis_dict.get("detected_technologies", []),
            forms_detected=bool(analysis_dict.get("forms_detected", False)),
            phone_found=analysis_dict.get("phone_number"),
            emails_found=analysis_dict.get("emails", []),
            social_links_found=analysis_dict.get("social_links_found", []),
            raw_details={**analysis_dict, **tech_dict}
        )
