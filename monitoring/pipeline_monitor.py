"""
pipeline_monitor.py
-------------------
Responsibility:
    Observe, log, and surface operational health metrics for each pipeline run.
    Tracks per-run statistics such as success rate, failure modes, timing, and
    data quality indicators.

Why this matters:
    As the pipeline runs more frequently (across more categories and cities),
    we need visibility into:
    - Which scraper steps are failing most
    - How long each pipeline stage takes
    - What percentage of businesses have complete vs. partial data
    - Which categories/locations yield the most high-quality leads

Architecture decision:
    This is a pure observability module — it does NOT control execution.
    It wraps pipeline runs and emits structured run reports.
    No external monitoring service required (e.g. no DataDog/Prometheus for MVP).

    Writes run summaries to:
    - logs/pipeline_runs.log (append-only structured log)
    - data/cache/run_summaries.json (rolling JSON history)

TODO:
    - Implement PipelineRun context manager for wrapping individual scrape runs
    - Track per-business stage success/failure (scrape, analyze, score, outreach)
    - Compute category-level success rates
    - Detect and log anomalies (e.g. 0 results from a normally productive query)
    - Build a simple text summary report for CLI output at end of run
    - Optional: Expose run metrics endpoint for Next.js dashboard display
"""

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("PipelineMonitor")


# ---------------------------------------------------------
# Output Data Structures
# ---------------------------------------------------------
@dataclass
class StageResult:
    """Result of a single pipeline stage for one business."""
    stage: str          # "scrape", "analyze", "score", "report", "outreach"
    success: bool
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class BusinessRunRecord:
    """Complete per-business pipeline run record."""
    business_name: str
    business_id: Optional[int] = None
    stages: List[StageResult] = field(default_factory=list)
    overall_success: bool = False
    total_duration_ms: Optional[float] = None


@dataclass
class PipelineRunSummary:
    """
    Full summary of a single pipeline execution (one search query).
    Designed for persistent logging and optional DB storage.
    """
    run_id: str
    search_query: str
    started_at: str
    finished_at: Optional[str] = None
    total_businesses: int = 0
    successful_businesses: int = 0
    failed_businesses: int = 0
    success_rate: float = 0.0
    high_opportunity_count: int = 0     # Businesses with score >= 70
    stage_failure_counts: Dict[str, int] = field(default_factory=dict)
    business_records: List[BusinessRunRecord] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------
# Pipeline Monitor
# ---------------------------------------------------------
class PipelineMonitor:
    """
    Tracks and reports on pipeline execution health.

    Usage:
        monitor = PipelineMonitor()
        run = monitor.start_run("Gyms in Trivandrum")
        # ... pipeline execution ...
        monitor.record_business(run, "Acme Gym", stages=[...])
        monitor.finish_run(run)
        monitor.save_run_summary(run)
    """

    def __init__(self, output_dir: str = "data/cache", db_manager=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db = db_manager

    def _generate_run_id(self) -> str:
        """Generate a unique run ID using timestamp."""
        return datetime.utcnow().strftime("run_%Y%m%d_%H%M%S")

    def start_run(self, search_query: str) -> PipelineRunSummary:
        """
        Initialize a new pipeline run summary.

        Args:
            search_query: The search query that triggered this run.

        Returns:
            PipelineRunSummary to be passed through the run and completed.
        """
        run = PipelineRunSummary(
            run_id=self._generate_run_id(),
            search_query=search_query,
            started_at=datetime.utcnow().isoformat(),
        )
        logger.info(f"Pipeline run started: {run.run_id} | Query: '{search_query}'")
        return run

    def record_business(
        self,
        run: PipelineRunSummary,
        business_name: str,
        business_id: Optional[int],
        stages: List[StageResult],
        opportunity_score: Optional[float] = None,
    ) -> None:
        """
        Record the outcome of processing a single business in this run.

        Args:
            run:              The active PipelineRunSummary.
            business_name:    Display name of the processed business.
            business_id:      Database ID of the business.
            stages:           List of StageResult for each pipeline stage.
            opportunity_score: The final opportunity score (for quality tracking).
        """
        record = BusinessRunRecord(
            business_name=business_name,
            business_id=business_id,
            stages=stages,
            overall_success=all(s.success for s in stages)
        )
        
        # Calculate total duration for this business
        durations = [s.duration_ms for s in stages if s.duration_ms is not None]
        record.total_duration_ms = sum(durations) if durations else None
        
        run.business_records.append(record)
        run.total_businesses += 1
        if record.overall_success:
            run.successful_businesses += 1
        else:
            run.failed_businesses += 1

        # Track stage_failure_counts per stage name
        for stage in stages:
            if not stage.success:
                run.stage_failure_counts[stage.stage] = run.stage_failure_counts.get(stage.stage, 0) + 1
        
        # Track high_opportunity_count if opportunity_score >= 70
        if opportunity_score is not None and opportunity_score >= 70:
            run.high_opportunity_count += 1

    def finish_run(self, run: PipelineRunSummary) -> None:
        """
        Finalize the run summary with completion time and success rate.

        Args:
            run: The active PipelineRunSummary to finalize.
        """
        run.finished_at = datetime.utcnow().isoformat()
        if run.total_businesses > 0:
            run.success_rate = round(
                (run.successful_businesses / run.total_businesses) * 100, 1
            )

        logger.info(
            f"Pipeline run finished: {run.run_id} | "
            f"Success rate: {run.success_rate}% "
            f"({run.successful_businesses}/{run.total_businesses})"
        )

    def save_run_summary(self, run: PipelineRunSummary) -> None:
        """
        Persist the run summary to the data/cache directory as JSON.
        Also appends a compact summary line to logs/pipeline_runs.log.
        Stores full summary in the pipeline_runs PostgreSQL table if self.db is present.
        """
        filepath = self.output_dir / f"{run.run_id}.json"
        run_dict = asdict(run)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(run_dict, f, indent=4)
            logger.info(f"Run summary saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save run summary: {e}")

        # Append compact summary line to logs/pipeline_runs.log
        log_filepath = Path("logs/pipeline_runs.log")
        log_filepath.parent.mkdir(exist_ok=True)
        try:
            with open(log_filepath, "a", encoding="utf-8") as lf:
                summary_line = (
                    f"{run.finished_at or datetime.utcnow().isoformat()} - {run.run_id} - "
                    f"Query: '{run.search_query}' - "
                    f"Success: {run.successful_businesses}/{run.total_businesses} "
                    f"({run.success_rate}%) - "
                    f"High Opp: {run.high_opportunity_count}\n"
                )
                lf.write(summary_line)
        except Exception as e:
            logger.error(f"Failed to append to pipeline_runs.log: {e}")

        # Save to database if db is available
        if self.db:
            try:
                from database.db import ScraperRepository
                repo = ScraperRepository(self.db)
                db_success = repo.insert_pipeline_run(run_dict)
                if db_success:
                    logger.info(f"Pipeline run {run.run_id} persisted in database.")
                else:
                    logger.error(f"Failed to insert pipeline run record in database.")
            except Exception as e:
                logger.error(f"Database insertion of pipeline run failed: {e}")

    def print_run_report(self, run: PipelineRunSummary) -> None:
        """
        Print a concise CLI-friendly summary of the completed run.
        """
        print(f"\n{'=' * 50}")
        print(f"Run ID:         {run.run_id}")
        print(f"Query:          {run.search_query}")
        print(f"Businesses:     {run.successful_businesses}/{run.total_businesses} successful")
        print(f"Success Rate:   {run.success_rate}%")
        print(f"High Opp Leads: {run.high_opportunity_count}")
        print(f"Duration:       {run.started_at} → {run.finished_at}")
        if run.stage_failure_counts:
            print(f"Stage Failures: {dict(run.stage_failure_counts)}")
        
        # Display top leads found
        top_leads = [
            r for r in run.business_records 
            if r.overall_success
        ]
        if top_leads:
            print("-" * 50)
            print("Successfully Processed Leads in this batch:")
            for lead in top_leads[:5]:
                print(f" - {lead.business_name} (ID: {lead.business_id or 'N/A'})")
                
        print(f"{'=' * 50}\n")


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    monitor = PipelineMonitor()
    run = monitor.start_run("Test Gyms in Trivandrum")
    monitor.record_business(run, "Acme Gym", business_id=1, stages=[
        StageResult("scrape", True, 1200.0),
        StageResult("analyze", True, 800.0),
        StageResult("score", True, 50.0),
    ])
    monitor.finish_run(run)
    monitor.print_run_report(run)
    monitor.save_run_summary(run)
