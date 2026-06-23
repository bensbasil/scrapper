import logging
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from pathlib import Path

# Structured Logging
logger = logging.getLogger("ConversionAnalyzer")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [ConversionAnalyzer] - %(message)s')
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

@dataclass
class ConversionAnalysisResult:
    business_name: str
    website_url: Optional[str]
    booking_flow_exists: bool
    weak_ctas: bool
    lead_capture_form_exists: bool
    contact_friction: bool
    whatsapp_available: bool
    conversion_friction_score: float
    conversion_health_score: float
    conversion_issues: List[str]

class ConversionAnalyzer:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def analyze(self, business_name: str, url: Optional[str]) -> ConversionAnalysisResult:
        logger.info(f"[{business_name}] Analyzing conversion friction for {url}...")
        issues = []
        
        # Defaults if no website exists
        if not url or str(url).strip() == "" or str(url).lower() == "none":
            return ConversionAnalysisResult(
                business_name=business_name,
                website_url=url,
                booking_flow_exists=False,
                weak_ctas=True,
                lead_capture_form_exists=False,
                contact_friction=True,
                whatsapp_available=False,
                conversion_friction_score=100.0,
                conversion_health_score=0.0,
                conversion_issues=["No website exists to convert leads"]
            )

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout, verify=False)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            html_lower = html.lower()
        except Exception as e:
            logger.warning(f"[{business_name}] Connection failed for conversion analysis: {e}")
            return ConversionAnalysisResult(
                business_name=business_name,
                website_url=url,
                booking_flow_exists=False,
                weak_ctas=True,
                lead_capture_form_exists=False,
                contact_friction=True,
                whatsapp_available=False,
                conversion_friction_score=100.0,
                conversion_health_score=0.0,
                conversion_issues=[f"Connection failed: {str(e)}"]
            )

        # 1. Booking Flow Detection
        booking_keywords = ["book", "reserve", "schedule", "appointment", "calendly", "acuity", "booking"]
        booking_flow_exists = False
        # Check text on links/buttons
        for elem in soup.find_all(["a", "button"]):
            elem_text = elem.text.strip().lower()
            href = elem.get("href", "").lower()
            if any(kw in elem_text or kw in href for kw in booking_keywords):
                booking_flow_exists = True
                break
        
        if not booking_flow_exists:
            issues.append("Missing online booking/scheduler flow")

        # 2. Weak CTA Detection
        ctas = []
        cta_keywords = ["get started", "buy", "contact", "subscribe", "join", "order", "register", "download", "call now", "submit"]
        for elem in soup.find_all(["a", "button"]):
            elem_text = elem.text.strip().lower()
            if any(kw in elem_text for kw in cta_keywords):
                ctas.append(elem_text)
        
        weak_ctas = len(ctas) < 2
        if weak_ctas:
            issues.append("Weak calls-to-action (low conversion triggers)")

        # 3. Lead Capture Form Detection
        forms = soup.find_all("form")
        lead_capture_form_exists = False
        for f in forms:
            inputs = f.find_all("input")
            text_inputs = [i for i in inputs if i.get("type", "text") in ["text", "email", "tel"]]
            # Make sure it's not just a search bar (search forms usually have 1 input)
            if len(text_inputs) >= 2:
                lead_capture_form_exists = True
                break
        
        if not lead_capture_form_exists:
            issues.append("No structured lead capture forms")

        # 4. Contact Friction
        # Prominent phone/email links check
        has_tel = any(link.get("href", "").lower().startswith("tel:") for link in soup.find_all("a", href=True))
        has_mail = any(link.get("href", "").lower().startswith("mailto:") for link in soup.find_all("a", href=True))
        contact_friction = not (has_tel or has_mail)
        if contact_friction:
            issues.append("Contact friction: phone/email links are not clickable anchors")

        # 5. WhatsApp Integration
        whatsapp_available = any(
            any(pat in link.get("href", "").lower() for pat in ["wa.me", "api.whatsapp.com", "whatsapp.com/send"])
            for link in soup.find_all("a", href=True)
        )
        if not whatsapp_available:
            issues.append("No instant WhatsApp chat integration")

        # Score Calculations
        friction = 0.0
        if not booking_flow_exists: friction += 30.0
        if weak_ctas: friction += 20.0
        if not lead_capture_form_exists: friction += 20.0
        if contact_friction: friction += 20.0
        if not whatsapp_available: friction += 10.0
        
        friction = min(100.0, friction)
        health = 100.0 - friction

        return ConversionAnalysisResult(
            business_name=business_name,
            website_url=url,
            booking_flow_exists=booking_flow_exists,
            weak_ctas=weak_ctas,
            lead_capture_form_exists=lead_capture_form_exists,
            contact_friction=contact_friction,
            whatsapp_available=whatsapp_available,
            conversion_friction_score=friction,
            conversion_health_score=health,
            conversion_issues=issues
        )
