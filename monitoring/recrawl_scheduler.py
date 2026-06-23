"""
recrawl_scheduler.py
--------------------
Responsibility:
    Determine which businesses are due for a re-scrape based on their last
    crawl timestamp and their priority level.

    High-priority businesses (high opportunity score) should be re-checked
    more frequently than low-priority ones.

Why this matters:
    A business website changes over time — they might add WhatsApp, fix their SSL,
    or update their CMS. Periodic recrawls keep the database fresh and surface
    new opportunities (or drop ones that are no longer viable).

Scheduling policy:
    - Tier 1 (opportunity_score >= 70): Recrawl every 7 days
    - Tier 2 (opportunity_score >= 40): Recrawl every 30 days
    - Tier 3 (opportunity_score < 40):  Recrawl every 90 days

Architecture decision:
    This module does NOT run a background scheduler (no Celery, no cron).
    It simply queries the database and returns a list of business IDs that
    are overdue, allowing pipeline_runner.py to process them on demand.

TODO:
    - Implement database query to find overdue businesses
    - Build get_overdue_businesses() using `last_checked` from businesses table
    - Add recrawl_tier column to businesses table in schema.sql
    - Integrate with change_detector.py to also trigger recrawls on demand
    - Optional: Write cron-friendly CLI entry point for nightly recrawl runs
"""

import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("RecrawlScheduler")


# ---------------------------------------------------------
# Scheduling Configuration
# ---------------------------------------------------------
RECRAWL_TIERS = {
    "tier1": {"min_score": 70.0, "interval_days": 7,  "label": "High Priority"},
    "tier2": {"min_score": 40.0, "interval_days": 30, "label": "Medium Priority"},
    "tier3": {"min_score": 0.0,  "interval_days": 90, "label": "Low Priority"},
}


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class RecrawlTask:
    """A single business flagged for recrawling."""
    business_id: int
    business_name: str
    opportunity_score: float
    last_checked: Optional[str]     # ISO timestamp
    days_overdue: int
    recrawl_tier: str               # "tier1", "tier2", "tier3"


# ---------------------------------------------------------
# Recrawl Scheduler
# ---------------------------------------------------------
class RecrawlScheduler:
    """
    Identifies businesses overdue for recrawling based on their tier policy.

    Usage:
        scheduler = RecrawlScheduler(db_manager)
        tasks = scheduler.get_overdue_businesses(limit=50)
        for task in tasks:
            # Pass to pipeline_runner for re-processing
            ...
    """

    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: DatabaseManager instance from database/db.py.
                        Optional for testing without a DB connection.
        """
        self.db = db_manager

    def _classify_tier(self, opportunity_score: float) -> str:
        """Determine which recrawl tier a business belongs to."""
        if opportunity_score >= RECRAWL_TIERS["tier1"]["min_score"]:
            return "tier1"
        elif opportunity_score >= RECRAWL_TIERS["tier2"]["min_score"]:
            return "tier2"
        return "tier3"

    def _is_overdue(self, last_checked: Optional[datetime], tier: str) -> tuple[bool, int]:
        """
        Check if a business is overdue for recrawling.

        Returns:
            (is_overdue: bool, days_overdue: int)
        """
        if last_checked is None:
            return True, 999  # Never checked = immediately overdue

        interval = timedelta(days=RECRAWL_TIERS[tier]["interval_days"])
        now = datetime.now(timezone.utc)
        due_date = last_checked + interval
        overdue_days = (now - due_date).days

        return overdue_days > 0, max(0, overdue_days)

    def get_overdue_businesses(self, limit: int = 50) -> List[RecrawlTask]:
        """
        Query the database for businesses overdue for recrawling, ordered by urgency.

        Args:
            limit: Maximum number of tasks to return per run.

        Returns:
            List of RecrawlTask objects, sorted by days_overdue descending.
        """
        logger.info(f"RecrawlScheduler: querying overdue businesses (limit={limit})")
        tasks: List[RecrawlTask] = []

        if not self.db:
            logger.warning("RecrawlScheduler: No database manager provided. Returning empty task list.")
            return tasks

        query = """
            SELECT b.id, b.business_name, b.last_checked, s.opportunity_score, b.recrawl_tier
            FROM businesses b
            JOIN scoring_results s ON b.id = s.business_id
            WHERE b.last_checked IS NULL
               OR (
                   b.recrawl_tier = 'tier1' AND b.last_checked < CURRENT_TIMESTAMP - INTERVAL '7 days'
               ) OR (
                   b.recrawl_tier = 'tier2' AND b.last_checked < CURRENT_TIMESTAMP - INTERVAL '30 days'
               ) OR (
                   b.recrawl_tier = 'tier3' AND b.last_checked < CURRENT_TIMESTAMP - INTERVAL '90 days'
               )
            ORDER BY b.last_checked ASC NULLS FIRST
            LIMIT %s;
        """

        try:
            from psycopg2.extras import RealDictCursor
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()

            for row in rows:
                last_checked_dt = row.get("last_checked")
                opportunity_score = float(row.get("opportunity_score") or 0.0)
                recrawl_tier = row.get("recrawl_tier") or self._classify_tier(opportunity_score)
                
                is_overdue, days_overdue = self._is_overdue(last_checked_dt, recrawl_tier)
                
                if is_overdue:
                    tasks.append(RecrawlTask(
                        business_id=row["id"],
                        business_name=row["business_name"],
                        opportunity_score=opportunity_score,
                        last_checked=last_checked_dt.isoformat() if last_checked_dt else None,
                        days_overdue=days_overdue,
                        recrawl_tier=recrawl_tier
                    ))

            # Sort by days_overdue descending
            tasks.sort(key=lambda t: t.days_overdue, reverse=True)
            logger.info(f"RecrawlScheduler: Found {len(tasks)} overdue businesses to recrawl.")
            return tasks

        except Exception as e:
            logger.error(f"Error querying overdue businesses in RecrawlScheduler: {e}")
            return []

    def get_schedule_summary(self) -> Dict[str, Any]:
        """
        Return a summary of the current recrawl schedule configuration.
        Useful for dashboard display or logging.
        """
        return {
            tier: {
                "interval_days": config["interval_days"],
                "label": config["label"],
                "min_opportunity_score": config["min_score"]
            }
            for tier, config in RECRAWL_TIERS.items()
        }


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    scheduler = RecrawlScheduler()
    print("Schedule configuration:")
    print(json.dumps(scheduler.get_schedule_summary(), indent=2))
    tasks = scheduler.get_overdue_businesses(limit=10)
    print(f"Overdue tasks found: {len(tasks)}")
