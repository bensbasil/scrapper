"""
intent_engine.py
----------------
Responsibility:
    Aggregate signals from all intent-detection sub-modules and compute a
    composite "buying intent" score for each business.

    Intent = the likelihood that a business is actively experiencing a pain
    point that makes them receptive to a pitch RIGHT NOW.

Input signals:
    - hiring_signal_detector: Is the business actively hiring technical roles?
    - review_trend_detector:  Are their reviews trending negatively?
    - freshness_monitor:      Is their website stale / abandoned?
    - scoring_engine:         What are their existing digital weakness scores?

Output:
    Returns IntentProfile — a composite view of a business's current
    receptivity to outreach. High intent + high opportunity = top priority lead.

Architecture decision:
    Designed as an aggregator — it does NOT collect its own data.
    It reads the outputs of specialist sub-modules and synthesizes them.
    This keeps each detection module independently testable.

TODO:
    - Integrate with hiring_signal_detector output
    - Integrate with review_trend_detector output
    - Integrate with freshness_monitor output
    - Build the composite scoring formula with configurable weights
    - Store IntentProfile in a new `intent_profiles` PostgreSQL table
    - Add time-decay: intent signals expire after N days (staleness penalty)
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from datetime import datetime

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("IntentEngine")


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class IntentProfile:
    """
    Composite intent profile for a business.
    Designed for a future `intent_profiles` table in PostgreSQL.
    """
    business_id: Optional[int]
    business_name: str
    intent_score: float = 0.0                    # 0-100, higher = more receptive NOW
    hiring_signal_score: float = 0.0             # From hiring_signal_detector
    review_trend_score: float = 0.0              # From review_trend_detector
    freshness_score: float = 0.0                 # From freshness_monitor
    opportunity_score: float = 0.0               # From scoring_engine (existing)
    top_intent_signals: List[str] = field(default_factory=list)
    outreach_urgency: str = "normal"             # "high", "normal", "low"
    evaluated_at: str = ""


# ---------------------------------------------------------
# Intent Engine
# ---------------------------------------------------------
class IntentEngine:
    """
    Synthesizes intent signals from multiple sub-modules into a single
    actionable IntentProfile.

    Usage:
        engine = IntentEngine()
        profile = engine.evaluate(business_id=42, business_name="Acme", signals={...})
    """

    # Configurable weights for composite intent score
    # TODO: Make these configurable via a YAML config file
    WEIGHTS = {
        "hiring_signal":  0.30,
        "review_trend":   0.25,
        "freshness":      0.25,
        "opportunity":    0.20,
    }

    def _determine_urgency(self, intent_score: float) -> str:
        """Classify outreach urgency based on intent score threshold."""
        if intent_score >= 70:
            return "high"
        elif intent_score >= 40:
            return "normal"
        return "low"

    def evaluate(
        self,
        business_id: Optional[int],
        business_name: str,
        signals: Dict[str, Any]
    ) -> IntentProfile:
        """
        Compute an IntentProfile from aggregated sub-module signals.

        Args:
            business_id:   Database ID of the business (None if not yet stored).
            business_name: Display name for logging.
            signals: Dict containing outputs from sub-modules:
                {
                    "hiring_signal_score": float,   # from hiring_signal_detector
                    "review_trend_score": float,    # from review_trend_detector
                    "freshness_score": float,       # from freshness_monitor
                    "opportunity_score": float,     # from scoring_engine
                }

        Returns:
            IntentProfile with composite intent_score and urgency classification.
        """
        profile = IntentProfile(
            business_id=business_id,
            business_name=business_name,
            evaluated_at=datetime.utcnow().isoformat()
        )

        profile.hiring_signal_score = signals.get("hiring_signal_score", 0.0)
        profile.review_trend_score = signals.get("review_trend_score", 0.0)
        profile.freshness_score = signals.get("freshness_score", 0.0)
        profile.opportunity_score = signals.get("opportunity_score", 0.0)

        # Weighted composite intent score
        profile.intent_score = round(
            (profile.hiring_signal_score * self.WEIGHTS["hiring_signal"]) +
            (profile.review_trend_score  * self.WEIGHTS["review_trend"]) +
            (profile.freshness_score     * self.WEIGHTS["freshness"]) +
            (profile.opportunity_score   * self.WEIGHTS["opportunity"]),
            1
        )

        # Populate top_intent_signals based on thresholds
        if profile.hiring_signal_score >= 25.0:
            profile.top_intent_signals.append("Active hiring for technical roles")
        if profile.review_trend_score >= 40.0:
            profile.top_intent_signals.append("Negative customer review trend detected")
        if profile.freshness_score >= 30.0:
            profile.top_intent_signals.append("Neglected/outdated website detected")
        if profile.opportunity_score >= 60.0:
            profile.top_intent_signals.append("High digital improvement opportunities")

        profile.outreach_urgency = self._determine_urgency(profile.intent_score)

        logger.info(
            f"[{business_name}] Intent Score: {profile.intent_score} "
            f"| Urgency: {profile.outreach_urgency}"
        )
        return profile


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    engine = IntentEngine()
    test_signals = {
        "hiring_signal_score": 80.0,
        "review_trend_score": 60.0,
        "freshness_score": 70.0,
        "opportunity_score": 75.5,
    }
    profile = engine.evaluate(42, "Acme Corp", test_signals)
    print(json.dumps(asdict(profile), indent=2))
