"""
review_trend_detector.py
------------------------
Responsibility:
    Analyze a business's Google Maps review trajectory to detect negative
    trends that signal pain points and create outreach opportunities.

Why this matters:
    A business with a dropping rating or a surge in negative reviews is likely
    experiencing operational or digital pain points. They are primed to hear
    about solutions — making them a higher-intent lead.

Signals to detect:
    - Rating drop over time (requires historical data — Phase 2)
    - Recent negative reviews mentioning digital pain points
      (e.g., "couldn't find website", "no online booking", "bad website")
    - Large gap between total reviews and low review count (poor retention)
    - Unanswered negative reviews (no owner response)

Architecture decision:
    Phase 1 uses only the data already scraped (rating + review_count).
    Phase 2 will require storing historical snapshots to detect trends.
    This module is designed to accept either phase's data without refactoring.

TODO:
    - Implement Phase 1 heuristics (static rating + review count analysis)
    - Store review snapshots in a `review_snapshots` table for trend detection
    - Implement keyword scanning of review text for digital pain-point signals
    - Detect businesses with unanswered reviews using Google Maps scraper
    - Integrate with intent_engine as review_trend_score
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from datetime import datetime

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("ReviewTrendDetector")

# Keywords in reviews that signal digital/service pain points
DIGITAL_PAIN_KEYWORDS = [
    "no website", "can't find online", "couldn't book online", "no app",
    "website down", "bad website", "old website", "not on google",
    "hard to contact", "no email", "no whatsapp",
    # TODO: Expand with observed keywords from real reviews
]


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class ReviewTrendResult:
    """
    Review intelligence for a business.
    Designed for use by intent_engine.py.
    """
    business_name: str
    current_rating: Optional[float]
    current_review_count: Optional[int]

    rating_category: str = "unknown"            # "excellent", "good", "average", "poor"
    review_volume_category: str = "unknown"     # "high", "medium", "low"
    digital_pain_signals: List[str] = field(default_factory=list)

    # Phase 2 fields (historical comparison)
    previous_rating: Optional[float] = None
    rating_delta: Optional[float] = None        # current - previous
    trend_direction: str = "unknown"            # "improving", "declining", "stable"

    review_trend_score: float = 0.0             # 0-100 for intent_engine
    error: Optional[str] = None


# ---------------------------------------------------------
# Review Trend Detector
# ---------------------------------------------------------
class ReviewTrendDetector:
    """
    Analyzes Google Maps rating and review data to surface intent signals.

    Phase 1: Static analysis of existing scraped data.
    Phase 2: Historical trend detection (requires snapshot storage).

    Usage:
        detector = ReviewTrendDetector()
        result = detector.analyze(
            business_name="Acme Corp",
            current_rating=3.2,
            review_count=12,
        )
    """

    def _classify_rating(self, rating: Optional[float]) -> str:
        """Classify rating into named categories."""
        if rating is None:
            return "unknown"
        if rating >= 4.5:
            return "excellent"
        elif rating >= 4.0:
            return "good"
        elif rating >= 3.0:
            return "average"
        return "poor"

    def _classify_review_volume(self, count: Optional[int]) -> str:
        """
        Classify review count into volume categories.

        TODO: Calibrate thresholds against observed local business data
              (what is "high" volume for a local SMB in Kerala vs. Manhattan?)
        """
        if count is None:
            return "unknown"
        if count >= 200:
            return "high"
        elif count >= 50:
            return "medium"
        return "low"

    def _calculate_score(self, result: ReviewTrendResult) -> float:
        """
        Compute review_trend_score (0-100) for intent_engine.

        Higher score = more negative signals = higher outreach relevance.

        Scoring logic:
            - Poor rating (< 3.5)      → +40 points
            - Average rating (3.5-4.0) → +20 points
            - Low review count (< 50)  → +20 points
            - Declining trend          → +20 points (Phase 2)
            - Digital pain keywords    → +10 per keyword (capped at 20)
        """
        score = 0.0

        if result.rating_category == "poor":
            score += 40.0
        elif result.rating_category == "average":
            score += 20.0

        if result.review_volume_category == "low":
            score += 20.0

        # Trend direction penalty (Phase 2)
        if result.trend_direction == "declining":
            score += 20.0

        # Keyword signal bonus
        if result.digital_pain_signals:
            keyword_bonus = len(result.digital_pain_signals) * 10.0
            score += min(20.0, keyword_bonus)

        return round(min(100.0, score), 1)

    def analyze(
        self,
        business_name: str,
        current_rating: Optional[float],
        review_count: Optional[int],
        previous_rating: Optional[float] = None,
        review_texts: Optional[List[str]] = None,
    ) -> ReviewTrendResult:
        """
        Analyze review data for a business and compute intent signals.

        Args:
            business_name:    Display name for logging.
            current_rating:   Current Google Maps rating (0-5).
            review_count:     Total number of reviews on Google Maps.
            previous_rating:  Historical rating snapshot (Phase 2 — optional).
            review_texts:     List of recent review texts (future — optional).

        Returns:
            ReviewTrendResult with review_trend_score.
        """
        result = ReviewTrendResult(
            business_name=business_name,
            current_rating=current_rating,
            current_review_count=review_count,
            previous_rating=previous_rating
        )

        result.rating_category = self._classify_rating(current_rating)
        result.review_volume_category = self._classify_review_volume(review_count)

        # Phase 2: Trend direction
        if previous_rating is not None and current_rating is not None:
            result.rating_delta = round(current_rating - previous_rating, 2)
            if result.rating_delta < -0.1:
                result.trend_direction = "declining"
            elif result.rating_delta > 0.1:
                result.trend_direction = "improving"
            else:
                result.trend_direction = "stable"

        # Scan review_texts for DIGITAL_PAIN_KEYWORDS
        if review_texts:
            for text in review_texts:
                text_lower = text.lower()
                for keyword in DIGITAL_PAIN_KEYWORDS:
                    if keyword in text_lower:
                        if keyword not in result.digital_pain_signals:
                            result.digital_pain_signals.append(keyword)

        result.review_trend_score = self._calculate_score(result)

        logger.info(
            f"[{business_name}] Rating: {current_rating} ({result.rating_category}), "
            f"Reviews: {review_count} ({result.review_volume_category}), "
            f"Trend Score: {result.review_trend_score}"
        )
        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    detector = ReviewTrendDetector()
    test = detector.analyze("Acme Corp", current_rating=3.1, review_count=18)
    print(json.dumps(asdict(test), indent=2))
