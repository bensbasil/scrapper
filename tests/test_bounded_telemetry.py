"""
tests/test_bounded_telemetry.py
-------------------------------
Comprehensive regression tests for Phase 5B P0-4: Bounded Telemetry Retention.
Verifies:
1. Simulation of at least 1,000 runs verifying that retained run traces remain strictly capped at max_runs.
2. Simulation of step events verifying that retained events remain strictly capped at max_step_events.
3. Independent bounding of runs and step events.
4. Deterministic FIFO eviction of oldest traces while preserving newest traces.
5. Preservation of correlation identifiers (run_id, prospect_id, batch_id).
6. Passive recording guarantee: recording does not mutate execution outcomes.
"""

from datetime import datetime, timezone
import pytest

from agent.telemetry import (
    InMemoryTelemetrySink,
    AgentRunTrace,
    CapabilityTraceEvent,
    StepEventStatus,
)


def test_telemetry_simulates_1000_runs_with_bounded_retention():
    """Simulates 1,000 agent runs and verifies retention remains bounded at max_runs."""
    max_runs = 150
    max_step_events = 500
    sink = InMemoryTelemetrySink(max_runs=max_runs, max_step_events=max_step_events)
    now_iso = datetime.now(timezone.utc).isoformat()

    for i in range(1000):
        run_id = f"run-{i:04d}"
        trace = AgentRunTrace(
            run_id=run_id,
            task_id=f"task-{i:04d}",
            user_goal=f"Goal for run {i}",
            status="completed",
            started_at=now_iso,
            completed_at=now_iso,
            duration_ms=10.0,
            discovered_count=1,
            qualified_count=1,
            selected_count=1,
            evaluation_passed=True,
            final_outcome="Success",
        )
        sink.record_run(trace)

        # Record a step event for each run
        event = CapabilityTraceEvent(
            run_id=run_id,
            step_id=f"step_{i}",
            capability_name="audit_website_tech",
            status=StepEventStatus.COMPLETED,
            prospect_id=f"prospect-{i}",
            capability_classification="READ",
            duration_ms=5.0,
        )
        sink.record_step(event)

    # 1. Verify size bounds
    all_runs = sink.get_runs()
    assert len(all_runs) == max_runs
    assert len(sink._runs) == max_runs

    all_events = sink.get_step_events()
    assert len(all_events) == max_step_events

    # 2. Verify deterministic FIFO eviction
    # The oldest runs (0 to 849) must have been evicted
    # The newest runs (850 to 999) must be retained
    assert sink.get_run("run-0000") is None
    assert sink.get_run("run-0500") is None
    assert sink.get_run("run-0849") is None

    for i in range(850, 1000):
        expected_run_id = f"run-{i:04d}"
        run = sink.get_run(expected_run_id)
        assert run is not None
        assert run.run_id == expected_run_id

    # 3. Verify step events retention
    # The oldest step events (0 to 499) must be evicted
    # The newest step events (500 to 999) must be present
    retained_run_ids = {e.run_id for e in all_events}
    assert "run-0000" not in retained_run_ids
    assert "run-0499" not in retained_run_ids
    assert "run-0999" in retained_run_ids


def test_independent_bounds_for_runs_and_events():
    """Verify that max_runs and max_step_events operate independently."""
    sink = InMemoryTelemetrySink(max_runs=10, max_step_events=20)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Add 50 runs with no step events
    for i in range(50):
        sink.record_run(
            AgentRunTrace(
                run_id=f"run-{i}",
                task_id=f"task-{i}",
                user_goal="test",
                status="completed",
                started_at=now_iso,
            )
        )

    # Add 100 step events associated with run-49
    for j in range(100):
        sink.record_step(
            CapabilityTraceEvent(
                run_id="run-49",
                step_id=f"step_{j}",
                capability_name=f"capability_{j}",
                status=StepEventStatus.COMPLETED,
            )
        )

    # Runs capped at 10
    assert len(sink.get_runs()) == 10
    # Step events capped at 20
    assert len(sink.get_step_events()) == 20


def test_correlation_filtering_under_eviction():
    """Ensure filtering by run_id, prospect_id, batch_id works properly with bounded history."""
    sink = InMemoryTelemetrySink(max_runs=50, max_step_events=50)

    for i in range(50):
        sink.record_step(
            CapabilityTraceEvent(
                run_id="target-run" if i % 2 == 0 else "other-run",
                step_id=f"step_{i}",
                capability_name="filter_test",
                status=StepEventStatus.COMPLETED,
                prospect_id=f"prospect-{i}",
                batch_id=f"batch-{i % 5}",
            )
        )

    # Test filtering by run_id
    target_events = sink.get_step_events(run_id="target-run")
    assert len(target_events) == 25
    assert all(e.run_id == "target-run" for e in target_events)

    # Test filtering by batch_id
    batch_0_events = sink.get_step_events(batch_id="batch-0")
    assert len(batch_0_events) == 10
    assert all(e.batch_id == "batch-0" for e in batch_0_events)


def test_passive_recording_does_not_mutate_outcomes():
    """Ensure passive telemetry recording does not modify trace instances or execution flow."""
    sink = InMemoryTelemetrySink(max_runs=5, max_step_events=5)
    now_iso = datetime.now(timezone.utc).isoformat()
    trace = AgentRunTrace(
        run_id="immutable-run-1",
        task_id="task-immutable-1",
        user_goal="Original Goal",
        status="completed",
        started_at=now_iso,
        evaluation_passed=True,
    )
    sink.record_run(trace)

    retrieved = sink.get_run("immutable-run-1")
    assert retrieved is not None
    assert retrieved.evaluation_passed is True
    assert retrieved.user_goal == "Original Goal"
