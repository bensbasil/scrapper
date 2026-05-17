"""
email_validator.py
------------------
Responsibility:
    Validate extracted email addresses to filter out bad/fake addresses
    before they enter the outreach pipeline.

Validation layers (in order):
    1. Syntax check  — regex format validation
    2. MX record check — does the domain have a mail server?
    3. SMTP check — (optional) does the mailbox exist? (requires careful rate-limiting)

Architecture decision:
    Kept as a standalone post-processing step so it can be applied to emails
    from any source — website extraction, JustDial, IndiaMart, etc.

Output contract:
    Returns EmailValidationResult per address — JSON/PostgreSQL compatible.

TODO:
    - Implement MX lookup using `dns.resolver` (dnspython library)
    - Implement optional SMTP VRFY / RCPT TO check
    - Add disposable email domain blocklist
    - Integrate confidence scoring (syntax=0.3, mx=0.6, smtp=1.0)
"""

import re
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("EmailValidator")

# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class EmailValidationResult:
    """
    Per-email validation outcome.
    Designed for storage in a future `email_intelligence` table alongside extracted_emails.
    """
    email: str
    syntax_valid: bool = False
    mx_record_exists: bool = False
    smtp_valid: Optional[bool] = None       # None = not checked
    is_disposable: bool = False
    confidence_score: float = 0.0           # 0.0 to 1.0
    validation_error: Optional[str] = None


# ---------------------------------------------------------
# Email Validator
# ---------------------------------------------------------
class EmailValidator:
    """
    Multi-layer email validator.

    Usage:
        validator = EmailValidator()
        result = validator.validate("contact@acmecorp.com")
        results = validator.validate_batch(["a@b.com", "bad-email"])
    """

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    # TODO: Load from a maintained blocklist file or API
    DISPOSABLE_DOMAINS = {
        "mailinator.com", "guerrillamail.com", "tempmail.com",
        "10minutemail.com", "throwaway.email"
    }

    def _check_syntax(self, email: str) -> bool:
        """Check email format using regex."""
        return bool(self.EMAIL_REGEX.match(email.strip()))

    def _check_mx_record(self, domain: str) -> bool:
        """
        Check if the domain has an MX (mail exchange) DNS record.

        TODO: Implement using dnspython:
            import dns.resolver
            records = dns.resolver.resolve(domain, 'MX')
            return len(records) > 0
        """
        # TODO: Replace with real MX lookup
        logger.debug(f"MX check not yet implemented for {domain}")
        return False

    def _check_disposable(self, domain: str) -> bool:
        """Check if domain is a known disposable email provider."""
        return domain.lower() in self.DISPOSABLE_DOMAINS

    def _calculate_confidence(self, result: EmailValidationResult) -> float:
        """
        Score from 0.0 to 1.0 based on which checks passed.

        Weights:
            syntax valid  → 0.3
            mx exists     → 0.5
            smtp valid    → 0.2 (when checked)
        """
        score = 0.0
        if result.syntax_valid:
            score += 0.3
        if result.mx_record_exists:
            score += 0.5
        if result.smtp_valid is True:
            score += 0.2
        if result.is_disposable:
            score = max(0.0, score - 0.5)
        return round(score, 2)

    def validate(self, email: str) -> EmailValidationResult:
        """
        Validate a single email address through all available layers.

        Args:
            email: Raw email string to validate.

        Returns:
            EmailValidationResult with populated confidence_score.
        """
        result = EmailValidationResult(email=email)

        try:
            result.syntax_valid = self._check_syntax(email)
            if not result.syntax_valid:
                result.validation_error = "Invalid email syntax"
                return result

            domain = email.split("@")[-1]
            result.is_disposable = self._check_disposable(domain)
            result.mx_record_exists = self._check_mx_record(domain)

            # TODO: Add optional SMTP check here (skip if rate-limiting is a concern)

        except Exception as e:
            logger.error(f"Validation failed for {email}: {e}")
            result.validation_error = str(e)

        result.confidence_score = self._calculate_confidence(result)
        logger.info(f"Validated {email} — confidence: {result.confidence_score}")
        return result

    def validate_batch(self, emails: List[str]) -> List[EmailValidationResult]:
        """Validate a list of emails. Skips duplicates."""
        seen = set()
        results = []
        for email in emails:
            if email in seen:
                continue
            seen.add(email)
            results.append(self.validate(email))
        return results


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    validator = EmailValidator()
    tests = ["contact@example.com", "not-an-email", "spam@mailinator.com"]
    for t in tests:
        r = validator.validate(t)
        print(json.dumps(asdict(r), indent=2))
