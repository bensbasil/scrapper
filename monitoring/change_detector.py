"""
change_detector.py
------------------
Responsibility:
    Detect meaningful changes on a business website between crawls.
    Compares the current state of a website against the previously stored
    snapshot and flags what has changed.

Why this matters:
    Changes on a business website are signals:
    - Added SSL → they're improving (lower priority now, follow up later)
    - Removed WhatsApp → they need help (re-engage)
    - Website completely down → urgent opportunity
    - New phone number → update our contact data

Comparison approach:
    Generate a lightweight "signature" of the current website state and
    compare against the stored snapshot in the database.

    Signature = {
        "ssl_enabled": bool,
        "meta_title": str,
        "contact_form_exists": bool,
        "social_links_count": int,
        "page_hash": str (MD5 of normalized HTML)
    }

Architecture decision:
    This module is stateless — it takes two snapshots as input and returns
    a diff. The pipeline_runner or recrawl_scheduler is responsible for
    fetching and persisting snapshots.

TODO:
    - Implement signature generation from WebsiteAnalysisResult
    - Implement diff comparison between two signatures
    - Build ChangeReport with per-field before/after values
    - Store change history in a `change_events` PostgreSQL table
    - Add notification hooks (future: send email/webhook on critical changes)
"""

import hashlib
import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("ChangeDetector")


# Fields that, if changed, are meaningful enough to log and potentially act on
MONITORED_FIELDS = [
    "ssl_enabled",
    "mobile_friendly",
    "contact_form_exists",
    "whatsapp_integration",
    "meta_title_exists",
    "website_exists",
    # TODO: Add tech stack fields when TechStackDetector is integrated
]


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class FieldChange:
    """A single field that changed between two snapshots."""
    field: str
    before: Any
    after: Any
    change_type: str    # "added", "removed", "modified"


@dataclass
class ChangeReport:
    """
    Full change report for a business between two crawl snapshots.
    Designed for a future `change_events` PostgreSQL table.
    """
    business_id: Optional[int]
    business_name: str
    changes_detected: bool = False
    changes: List[FieldChange] = field(default_factory=list)
    page_hash_changed: bool = False
    previous_snapshot_at: Optional[str] = None
    current_snapshot_at: Optional[str] = None
    change_summary: str = "No changes detected"


# ---------------------------------------------------------
# Change Detector
# ---------------------------------------------------------
class ChangeDetector:
    """
    Compares two website snapshots and produces a structured ChangeReport.

    Usage:
        detector = ChangeDetector()
        report = detector.compare(business_id=42, business_name="Acme",
                                  previous=old_snapshot, current=new_snapshot)
    """

    def _generate_page_hash(self, snapshot: Dict[str, Any]) -> str:
        """
        Generate a stable hash of key website signals for quick change detection.
        If hash differs → full diff comparison is warranted.

        TODO: Include more signals in the hash for better sensitivity.
        """
        key_fields = {k: snapshot.get(k) for k in MONITORED_FIELDS}
        hash_str = str(sorted(key_fields.items()))
        return hashlib.md5(hash_str.encode()).hexdigest()

    def _diff_fields(
        self,
        previous: Dict[str, Any],
        current: Dict[str, Any]
    ) -> List[FieldChange]:
        """
        Compare previous and current snapshot for changes in monitored fields.
        """
        changes: List[FieldChange] = []
        for field in MONITORED_FIELDS:
            prev_val = previous.get(field)
            curr_val = current.get(field)
            
            if prev_val != curr_val:
                # Determine change type
                if (prev_val is None or prev_val is False or prev_val == "") and (curr_val is not None and curr_val is not False and curr_val != ""):
                    change_type = "added"
                elif (prev_val is not None and prev_val is not False and prev_val != "") and (curr_val is None or curr_val is False or curr_val == ""):
                    change_type = "removed"
                else:
                    change_type = "modified"
                
                changes.append(FieldChange(
                    field=field,
                    before=prev_val,
                    after=curr_val,
                    change_type=change_type
                ))
        return changes

    def _build_summary(self, changes: List[FieldChange]) -> str:
        """Build a human-readable one-line change summary."""
        if not changes:
            return "No changes detected"
        parts = [f"{c.field}: {c.before} -> {c.after}" for c in changes[:3]]
        summary = " | ".join(parts)
        if len(changes) > 3:
            summary += f" (+{len(changes) - 3} more)"
        return summary

    def compare(
        self,
        business_id: Optional[int],
        business_name: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
        previous_at: Optional[str] = None,
        current_at: Optional[str] = None,
    ) -> ChangeReport:
        """
        Compare two website analysis snapshots and report what changed.

        Args:
            business_id:   DB ID of the business being monitored.
            business_name: Display name for logging.
            previous:      Website analysis dict from a previous crawl.
            current:       Website analysis dict from the most recent crawl.
            previous_at:   ISO timestamp of the previous snapshot.
            current_at:    ISO timestamp of the current snapshot.

        Returns:
            ChangeReport with detected field-level diffs.
        """
        report = ChangeReport(
            business_id=business_id,
            business_name=business_name,
            previous_snapshot_at=previous_at,
            current_snapshot_at=current_at,
        )

        if not previous:
            logger.info(f"[{business_name}] No previous snapshot to compare.")
            return report

        # Quick check via hash
        prev_hash = self._generate_page_hash(previous)
        curr_hash = self._generate_page_hash(current)
        report.page_hash_changed = prev_hash != curr_hash

        if not report.page_hash_changed:
            logger.info(f"[{business_name}] No changes detected (hash match)")
            return report

        # Full field diff
        report.changes = self._diff_fields(previous, current)
        report.changes_detected = len(report.changes) > 0
        report.change_summary = self._build_summary(report.changes)

        logger.info(
            f"[{business_name}] Changes detected: {len(report.changes)} "
            f"| Summary: {report.change_summary}"
        )
        return report


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    detector = ChangeDetector()
    prev = {"ssl_enabled": False, "mobile_friendly": False, "contact_form_exists": False}
    curr = {"ssl_enabled": True,  "mobile_friendly": False, "contact_form_exists": True}
    report = detector.compare(42, "Acme Corp", prev, curr)
    print(json.dumps(asdict(report), indent=2))
