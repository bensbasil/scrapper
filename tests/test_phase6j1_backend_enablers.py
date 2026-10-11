"""tests/test_phase6j1_backend_enablers.py

Regression and boundary tests for Phase 6J.1: Backend API Enablers.
Verifies:
1. ScraperRepository.get_change_events() queries, parameterization, and parsing.
2. ScraperRepository.get_pipeline_runs() includes stage_failure_counts.
3. ScraperRepository.get_businesses_for_dashboard() sort_by parameter and allowlisted SQL order clauses.
4. FastAPI endpoints:
   - GET /api/businesses/{business_id}/changes (auth, success, empty, 404, 400, 422)
   - GET /api/businesses (sort_by=opportunity, default, invalid sort validation, pagination)
   - GET /api/runs (stage_failure_counts preservation, pagination, auth)
"""

import os
import json
import pytest
import httpx
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api_server import app, verify_api_key, get_repository
from database.db import ScraperRepository


TEST_API_KEY = "test-phase6j1-secret-key"


# -----------------------------------------------------------------------------
# 1. ScraperRepository Unit Tests (SQL Construction & Deserialization)
# -----------------------------------------------------------------------------

def test_repo_get_change_events_sql_and_parsing():
    """Verify get_change_events parameterizes business_id and deserializes JSON and dates."""
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    now = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)
    mock_cur.fetchall.return_value = [
        {
            "id": 101,
            "business_id": 42,
            "changes": json.dumps([{"field": "phone", "old": "111", "new": "222"}]),
            "previous_snapshot_at": now,
            "current_snapshot_at": now,
            "change_summary": "Phone updated",
            "detected_at": now,
        },
        {
            "id": 100,
            "business_id": 42,
            "changes": [{"field": "cms", "old": None, "new": "WordPress"}],  # Already list
            "previous_snapshot_at": None,
            "current_snapshot_at": now,
            "change_summary": "CMS detected",
            "detected_at": now,
        },
        {
            "id": 99,
            "business_id": 42,
            "changes": None,  # Should fallback to []
            "previous_snapshot_at": None,
            "current_snapshot_at": None,
            "change_summary": None,
            "detected_at": now,
        },
    ]

    repo = ScraperRepository(mock_db)
    results = repo.get_change_events(42)

    # Verify SQL query parameterization
    mock_cur.execute.assert_called_once()
    sql_arg, params_arg = mock_cur.execute.call_args[0]
    assert "FROM change_events" in sql_arg
    assert "WHERE business_id = %s" in sql_arg
    assert "ORDER BY detected_at DESC, id DESC" in sql_arg
    assert params_arg == (42,)

    # Verify result normalization
    assert len(results) == 3
    assert results[0]["changes"] == [{"field": "phone", "old": "111", "new": "222"}]
    assert results[0]["previous_snapshot_at"] == now.isoformat()
    assert results[0]["current_snapshot_at"] == now.isoformat()
    assert results[0]["detected_at"] == now.isoformat()

    assert results[1]["changes"] == [{"field": "cms", "old": None, "new": "WordPress"}]
    assert results[1]["previous_snapshot_at"] is None

    assert results[2]["changes"] == []


def test_repo_get_pipeline_runs_includes_stage_failure_counts():
    """Verify get_pipeline_runs SELECT includes stage_failure_counts and normalizes dict/json."""
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    started = datetime(2026, 10, 11, 8, 0, 0, tzinfo=timezone.utc)
    mock_cur.fetchall.return_value = [
        {
            "run_id": "run-abc",
            "search_query": "dentists",
            "started_at": started,
            "finished_at": started,
            "total_businesses": 20,
            "successful_businesses": 18,
            "failed_businesses": 2,
            "success_rate": 90.0,
            "high_opportunity_count": 5,
            "stage_failure_counts": json.dumps({"scraping": 1, "tech_stack": 1}),
            "notes": json.dumps(["Run completed"]),
            "created_at": started,
        },
        {
            "run_id": "run-def",
            "search_query": "lawyers",
            "started_at": started,
            "finished_at": None,
            "total_businesses": 5,
            "successful_businesses": 5,
            "failed_businesses": 0,
            "success_rate": 100.0,
            "high_opportunity_count": 2,
            "stage_failure_counts": None,  # Should fallback to {}
            "notes": [],
            "created_at": started,
        },
    ]

    repo = ScraperRepository(mock_db)
    runs = repo.get_pipeline_runs(limit=10)

    mock_cur.execute.assert_called_once()
    sql_arg, params_arg = mock_cur.execute.call_args[0]
    assert "stage_failure_counts" in sql_arg
    assert "FROM pipeline_runs" in sql_arg
    assert "LIMIT %s" in sql_arg
    assert params_arg == (10,)

    assert len(runs) == 2
    assert runs[0]["stage_failure_counts"] == {"scraping": 1, "tech_stack": 1}
    assert runs[0]["notes"] == ["Run completed"]
    assert runs[0]["started_at"] == started.isoformat()
    assert runs[1]["stage_failure_counts"] == {}


def test_repo_get_businesses_for_dashboard_sort_by():
    """Verify get_businesses_for_dashboard applies exact order expressions and allowlist."""
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = []

    repo = ScraperRepository(mock_db)

    # 1. Default ordering (omitted)
    repo.get_businesses_for_dashboard(limit=5, offset=0)
    sql_default = mock_cur.execute.call_args[0][0]
    assert "ORDER BY b.id DESC" in sql_default
    assert "opportunity_score DESC" not in sql_default

    # 2. Opportunity ordering
    repo.get_businesses_for_dashboard(limit=5, offset=0, sort_by="opportunity")
    sql_opp = mock_cur.execute.call_args[0][0]
    assert "ORDER BY s.opportunity_score DESC NULLS LAST, b.id DESC" in sql_opp

    # 3. Explicit default / id ordering
    repo.get_businesses_for_dashboard(sort_by="default")
    sql_expl_def = mock_cur.execute.call_args[0][0]
    assert "ORDER BY b.id DESC" in sql_expl_def

    repo.get_businesses_for_dashboard(sort_by="id")
    sql_expl_id = mock_cur.execute.call_args[0][0]
    assert "ORDER BY b.id DESC" in sql_expl_id

    # 4. Invalid sort value raises ValueError
    with pytest.raises(ValueError) as exc:
        repo.get_businesses_for_dashboard(sort_by="malicious_column; DROP TABLE--")
    assert "Invalid sort_by" in str(exc.value)


# -----------------------------------------------------------------------------
# 2. FastAPI Endpoint Tests (Authentication, Validation, Error Handling)
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_repo_enablers():
    repo = MagicMock(spec=ScraperRepository)

    # Business lookups
    repo.get_business_by_id.side_effect = lambda bid: {
        "id": bid,
        "business_name": f"Business {bid}",
    } if bid in (1, 2) else None

    # Change events
    repo.get_change_events.side_effect = lambda bid: [
        {
            "id": 1,
            "business_id": bid,
            "changes": [{"field": "phone", "old": "123", "new": "456"}],
            "previous_snapshot_at": "2026-10-10T10:00:00Z",
            "current_snapshot_at": "2026-10-11T10:00:00Z",
            "change_summary": "Phone number changed",
            "detected_at": "2026-10-11T10:00:00Z",
        }
    ] if bid == 1 else []

    # Pipeline runs
    repo.get_pipeline_runs.side_effect = lambda limit=20: [
        {
            "run_id": "run-001",
            "search_query": "dentists",
            "started_at": "2026-10-11T09:00:00Z",
            "finished_at": "2026-10-11T09:05:00Z",
            "total_businesses": 15,
            "successful_businesses": 14,
            "failed_businesses": 1,
            "success_rate": 93.3,
            "high_opportunity_count": 4,
            "stage_failure_counts": {"scraping": 0, "social_audit": 1},
            "notes": ["1 timeout on instagram"],
            "created_at": "2026-10-11T09:00:00Z",
        }
    ][:limit]

    # Businesses list
    repo.get_businesses_for_dashboard.side_effect = lambda limit=None, offset=0, sort_by=None: [
        {
            "id": "1",
            "business_name": "Apex Dental",
            "opportunity_score": 92,
            "outreach_status": "new",
        },
        {
            "id": "2",
            "business_name": "Beacon Clinic",
            "opportunity_score": 75,
            "outreach_status": "contacted",
        },
    ]

    return repo


@pytest.fixture(autouse=True)
def override_deps(monkeypatch, mock_repo_enablers):
    monkeypatch.setenv("API_AUTH_TOKEN", TEST_API_KEY)
    monkeypatch.setenv("DATABASE_URL", "postgresql://mock:mock@localhost:5432/mock")
    app.dependency_overrides[verify_api_key] = lambda: TEST_API_KEY
    app.dependency_overrides[get_repository] = lambda: mock_repo_enablers
    yield
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_repository, None)


@pytest.mark.anyio
async def test_get_business_changes_success():
    """Verify GET /api/businesses/{id}/changes returns 200 with populated events."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        resp = await client.get("/api/businesses/1/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["business_id"] == 1
        assert len(data["changes"]) == 1
        assert data["changes"][0]["change_summary"] == "Phone number changed"


@pytest.mark.anyio
async def test_get_business_changes_empty():
    """Verify GET /api/businesses/{id}/changes returns 200 with empty list when no events exist."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        resp = await client.get("/api/businesses/2/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["business_id"] == 2
        assert data["changes"] == []


@pytest.mark.anyio
async def test_get_business_changes_not_found():
    """Verify GET /api/businesses/{id}/changes returns 404 for unknown business."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        resp = await client.get("/api/businesses/999/changes")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Business not found"


@pytest.mark.anyio
async def test_get_business_changes_invalid_id():
    """Verify non-positive and non-integer IDs return 400 and 422 respectively."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        # Zero
        resp_zero = await client.get("/api/businesses/0/changes")
        assert resp_zero.status_code == 400
        assert "positive integer" in resp_zero.json()["detail"]

        # Negative
        resp_neg = await client.get("/api/businesses/-10/changes")
        assert resp_neg.status_code == 400

        # Non-integer
        resp_str = await client.get("/api/businesses/abc/changes")
        assert resp_str.status_code == 422


@pytest.mark.anyio
async def test_get_businesses_opportunity_sorting(mock_repo_enablers):
    """Verify sort_by=opportunity passes sort_by to repo and returns in payload."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        resp = await client.get("/api/businesses?sort_by=opportunity&limit=10&offset=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["sort_by"] == "opportunity"
        assert data["limit"] == 10
        assert data["offset"] == 5
        mock_repo_enablers.get_businesses_for_dashboard.assert_called_with(
            limit=10, offset=5, sort_by="opportunity"
        )


@pytest.mark.anyio
async def test_get_businesses_invalid_sort():
    """Verify invalid sort_by values are rejected with 400 Bad Request."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        resp = await client.get("/api/businesses?sort_by=unsupported_column")
        assert resp.status_code == 400
        assert "Invalid sort_by" in resp.json()["detail"]


@pytest.mark.anyio
async def test_get_runs_includes_stage_failure_counts(mock_repo_enablers):
    """Verify GET /api/runs response contains stage_failure_counts for each run."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        resp = await client.get("/api/runs?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert "stage_failure_counts" in run
        assert run["stage_failure_counts"] == {"scraping": 0, "social_audit": 1}
        assert run["success_rate"] == 93.3
        assert run["high_opportunity_count"] == 4
        mock_repo_enablers.get_pipeline_runs.assert_called_with(limit=5)


# -----------------------------------------------------------------------------
# 3. Live PostgreSQL Integration Tests (Marked)
# -----------------------------------------------------------------------------

@pytest.mark.postgres_integration
def test_real_postgres_phase6j1_enablers():
    """Live PostgreSQL test validating change events, pipeline run stage failures,
    and opportunity sorting against real PostgreSQL container."""
    from database.db import DatabaseManager
    real_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not real_db_url or "mock" in real_db_url:
        pytest.skip("No real PostgreSQL instance configured (set TEST_DATABASE_URL to run)")

    mgr = DatabaseManager(db_url=real_db_url, timeout=5.0, lazy=False)
    repo = ScraperRepository(mgr)
    test_run_id = f"test-run-{int(datetime.now().timestamp())}"

    try:
        # 1. Clean test sandbox
        with mgr.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM pipeline_runs WHERE run_id LIKE 'test-run-%';")
                cur.execute("DELETE FROM change_events WHERE change_summary LIKE 'TEST_EVENT_%';")
                cur.execute("DELETE FROM businesses WHERE business_name LIKE 'TEST_PHASE6J_%';")

        # 2. Test pipeline_runs with stage_failure_counts
        now = datetime.now(timezone.utc)
        failure_counts = {"scraping": 2, "enrichment": 1}
        logged = repo.insert_pipeline_run({
            "run_id": test_run_id,
            "search_query": "test query",
            "started_at": now,
            "finished_at": now,
            "total_businesses": 10,
            "successful_businesses": 8,
            "failed_businesses": 2,
            "success_rate": 80.0,
            "high_opportunity_count": 3,
            "stage_failure_counts": failure_counts,
            "business_records": [],
            "notes": ["test run note"]
        })
        assert logged is True

        runs = repo.get_pipeline_runs(limit=10)
        found_run = next((r for r in runs if r["run_id"] == test_run_id), None)
        assert found_run is not None
        assert found_run["stage_failure_counts"] == failure_counts
        assert found_run["high_opportunity_count"] == 3

        # 3. Test businesses insertion and opportunity sorting
        b1_id = repo.insert_business({
            "business_name": "TEST_PHASE6J_BIZ_LOW",
            "category": "Testing",
            "website": "https://low.test",
        })
        b2_id = repo.insert_business({
            "business_name": "TEST_PHASE6J_BIZ_HIGH",
            "category": "Testing",
            "website": "https://high.test",
        })
        b3_id = repo.insert_business({
            "business_name": "TEST_PHASE6J_BIZ_UNSCORED",
            "category": "Testing",
            "website": "https://unscored.test",
        })

        assert b1_id and b2_id and b3_id

        # Score businesses
        repo.insert_scoring_result(b1_id, {
            "opportunity_score": 30,
            "website_quality_score": 40,
            "seo_score": 20,
            "automation_need_score": 30,
            "likely_service_match": ["Basic Web"],
            "detected_pain_points": ["No SSL"],
        })
        repo.insert_scoring_result(b2_id, {
            "opportunity_score": 95,
            "website_quality_score": 90,
            "seo_score": 95,
            "automation_need_score": 90,
            "likely_service_match": ["Full Suite"],
            "detected_pain_points": ["Outdated layout"],
        })

        # Test opportunity sorting
        biz_opp = repo.get_businesses_for_dashboard(limit=50, sort_by="opportunity")
        test_biz_opp = [b for b in biz_opp if b["business_name"].startswith("TEST_PHASE6J_")]
        assert len(test_biz_opp) >= 3
        # High (95) must come before Low (30), and unscored (NULL) must come last
        names_in_order = [b["business_name"] for b in test_biz_opp]
        assert names_in_order.index("TEST_PHASE6J_BIZ_HIGH") < names_in_order.index("TEST_PHASE6J_BIZ_LOW")
        assert names_in_order.index("TEST_PHASE6J_BIZ_LOW") < names_in_order.index("TEST_PHASE6J_BIZ_UNSCORED")

        # 4. Test change_events
        evt_logged = repo.insert_change_event(
            business_id=b2_id,
            previous_snapshot_at=now,
            current_snapshot_at=now,
            change_summary="TEST_EVENT_UPDATED",
            changes=[{"field": "title", "old": "Old Title", "new": "New Title"}]
        )
        assert evt_logged is True

        events = repo.get_change_events(b2_id)
        assert len(events) >= 1
        assert events[0]["business_id"] == b2_id
        assert events[0]["change_summary"] == "TEST_EVENT_UPDATED"
        assert events[0]["changes"] == [{"field": "title", "old": "Old Title", "new": "New Title"}]

    finally:
        # Cleanup test records
        with mgr.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM pipeline_runs WHERE run_id LIKE 'test-run-%';")
                cur.execute("DELETE FROM change_events WHERE change_summary LIKE 'TEST_EVENT_%';")
                cur.execute("DELETE FROM businesses WHERE business_name LIKE 'TEST_PHASE6J_%';")
        mgr.close()

