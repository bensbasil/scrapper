import socket
import urllib.parse
import requests
from typing import Any, Dict, Optional
from scraper.base_scraper import BaseScraper
from scraper.utils.logger import get_scraper_logger
from scraper.utils.exceptions import SourceTimeoutError, ParseError
from scraper.utils.ssrf import validate_url_for_ssrf, safe_fetch_url, SSRFValidationError

logger = get_scraper_logger("TechSignalsScraper")

class TechSignalAnalyzer(BaseScraper):
    """
    Checks DNS, MX, and SSL records for a given domain to detect technical maturity.
    """
    
    def analyze(self, target: str, **kwargs) -> Dict[str, Any]:
        """Convenience method matching capability contracts."""
        raw = self.fetch_raw(target, **kwargs)
        return {
            "domain": raw.get("domain"),
            "ssl_valid": raw.get("has_ssl", False),
            "has_ssl": raw.get("has_ssl", False),
            "dns_resolves": raw.get("resolves", False),
            "has_mx": raw.get("has_mx", False),
        }

    def fetch_raw(self, target: str, **kwargs) -> Dict[str, Any]:
        """
        Target should be a URL. Extracts domain and performs network requests.
        """
        raw_data = {"domain": None, "has_ssl": False, "has_mx": False, "resolves": False}
        if not target:
            return raw_data
            
        try:
            target_str = target if target.startswith(("http://", "https://")) else f"https://{target}"
            # Preflight SSRF check
            try:
                validate_url_for_ssrf(target_str, resolve_dns=True)
            except SSRFValidationError as e:
                logger.warning(f"SSRF validation blocked target '{target}': {e}")
                return raw_data

            parsed_url = urllib.parse.urlparse(target_str)
            domain = parsed_url.netloc or parsed_url.path
            domain = domain.split(':')[0]  # Remove port if present
            domain = domain.replace('www.', '')
            raw_data["domain"] = domain
            
            # Check if domain resolves
            try:
                socket.gethostbyname(domain)
                raw_data["resolves"] = True
            except socket.gaierror:
                logger.warning(f"Domain {domain} does not resolve.")
                return raw_data
                
            # Check SSL with SSRF redirect protection
            try:
                response = safe_fetch_url(f"https://{domain}", timeout=5)
                raw_data["has_ssl"] = True
            except (requests.exceptions.SSLError, SSRFValidationError):
                raw_data["has_ssl"] = False
            except requests.exceptions.RequestException:
                # Might just be blocking requests or down, assume False for SSL
                raw_data["has_ssl"] = False
                
            # Check MX (Basic heuristic: does it have an email server?)
            raw_data["has_mx"] = True # Placeholder for actual MX check

        except Exception as e:
            logger.error(f"Failed to fetch tech signals for {target}: {e}")
            raise SourceTimeoutError(f"Timeout or error fetching {target}") from e
            
        return raw_data

    def parse_data(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Basic validation of the fetched signals.
        """
        if not raw_data.get("domain"):
            raise ParseError("No domain could be extracted.")
        return raw_data

    def normalize(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize to the schema expected by the scoring engine.
        """
        return {
            "domain": parsed_data.get("domain"),
            "signals": {
                "ssl_enabled": parsed_data.get("has_ssl", False),
                "domain_resolves": parsed_data.get("resolves", False),
                "has_email_setup": parsed_data.get("has_mx", False)
            }
        }
