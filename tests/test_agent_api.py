"""
tests/test_agent_api.py
-----------------------
Focused test suite for Phase 4E: Agent API & Application Integration.
Verifies:
1. Valid goal submission (POST /api/agent/run and POST /api/agent/execute alias)
2. Known-business goal submission
3. Discovery goal submission
4. Ambiguous goal and clarification response
5. Invalid request validation (short goals, missing fields, forbidden extra fields)
6. Oversized prospect limits (schema rejection & safety-ceiling clamping)
7. Evaluation failure reflected correctly in the response
8. Task lookup behavior (GET /api/agent/tasks/{task_id})
9. Unknown task IDs (404 with documented lifetime semantics)
10. No external communication authorization
11. Capability-policy boundaries & prevention of secret/stack trace leakage
12. Existing API backwards compatibility (/api/status, /api/runs, /api/businesses)
"""

import pytest
import httpx
from unittest.mock import MagicMock

from api_server import app, set_agent, agent_task_store
from agent.models import AgentStatus, AgentFinalResponse
from agent.state import AgentState
from agent.intent import ClarificationRequest
from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard, EvidenceItem
from schemas.ai import OpportunityAnalysis, CommercialRecommendation, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult, ComponentEvaluation


from evaluation.datasets.fixtures import (
    get_strong_evidence_good_reasoning_fixture,
    get_unsupported_hallucination_fixture,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_agent_state(monkeypatch):
    """Ensure clean agent injection, auth token, and task store between tests."""
    monkeypatch.setenv("API_AUTH_TOKEN", "test-agent-api-token")
    from api_server import verify_api_key, get_repository
    app.dependency_overrides[verify_api_key] = lambda: "test-agent-api-token"
    mock_repo = MagicMock()
    mock_repo.get_pipeline_runs.return_value = [{"run_id": "run-test-1", "search_query": "plumbers"}]
    mock_repo.get_businesses_for_dashboard.return_value = [{"id": 1, "business_name": "Test Co"}]
    app.dependency_overrides[get_repository] = lambda: mock_repo
    agent_task_store.clear()
    set_agent(None)
    yield
    agent_task_store.clear()
    set_agent(None)
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_repository, None)


def _create_mock_context(business_name="Acme Dental"):
    fixture = get_strong_evidence_good_reasoning_fixture()
    ctx = fixture["context"]
    ctx.business.business_name = business_name
    return ctx


def _create_mock_analysis():
    return get_strong_evidence_good_reasoning_fixture()["opportunity_analysis"]


def _create_mock_strategy():
    return get_strong_evidence_good_reasoning_fixture()["outreach_strategy"]


def _create_mock_eval_result(passed=True):
    return EvaluationResult(
        passed=passed,
        overall_score=0.92 if passed else 0.45,
        grounding_score=0.95 if passed else 0.40,
        relevance_score=0.90 if passed else 0.45,
        consistency_score=0.90 if passed else 0.45,
        evidence_coverage_score=0.88 if passed else 0.35,
        issues=[] if passed else ["Evidence grounding failure: Cited points unverified in context"],
        hallucination_flags=[] if passed else ["unsupported_claim"]
    )


def _create_mock_draft(business_name="Acme Dental"):
    return OutreachDraft(
        business_name=business_name,
        cold_email_draft="Hi Acme Dental team,\n\nI noticed an opportunity to modernize your online appointment booking...",
        whatsapp_draft="Hi! Noticed booking friction on your site.",
        outreach_angles=["Mobile conversion optimization"],
        generation_mode="template"
    )


# -----------------------------------------------------------------------------
# 1 & 2. Valid Goal Submission & Aliases
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_valid_goal_submission_run():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_test_01",
        run_id="run_test_01",
        user_goal="Analyze Acme Dental"
    )
    state.status = AgentStatus.COMPLETED
    state.prospect_context = _create_mock_context()
    state.opportunity_analysis = _create_mock_analysis()
    state.outreach_strategy = _create_mock_strategy()
    state.evaluation_result = _create_mock_eval_result(passed=True)
    state.outreach_draft = _create_mock_draft()
    state.final_response = AgentFinalResponse(
        task_id="task_test_01",
        user_goal="Analyze Acme Dental",
        status=AgentStatus.COMPLETED,
        summary="Successfully analyzed Acme Dental and drafted outreach.",
        completed_capabilities=["acquire_evidence", "reason_opportunity", "synthesize_outreach", "evaluate_reasoning", "render_outreach"]
    )
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Analyze Acme Dental"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["task_id"] == "task_test_01"
        assert data["run_id"] == "run_test_01"
        assert data["user_goal"] == "Analyze Acme Dental"
        assert data["status"] == "COMPLETED"
        assert "acquire_evidence" in data["completed_capabilities"]
        assert data["summary"] == "Successfully analyzed Acme Dental and drafted outreach."
        assert data["prospect_context"]["business"]["business_name"] == "Acme Dental"
        assert len(data["opportunity_analysis"]["cited_evidence_points"]) > 0
        assert data["outreach_draft"]["cold_email_draft"] is not None
        assert data["evaluation_result"]["passed"] is True


@pytest.mark.anyio
async def test_valid_goal_submission_execute_alias():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_alias_01",
        run_id="run_alias_01",
        user_goal="Analyze Acme Dental"
    )
    state.status = AgentStatus.COMPLETED
    state.final_response = AgentFinalResponse(
        task_id="task_alias_01",
        user_goal="Analyze Acme Dental",
        status=AgentStatus.COMPLETED,
        summary="Alias execution completed."
    )
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/execute", json={"goal": "Analyze Acme Dental"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task_alias_01"
        assert data["status"] == "COMPLETED"


# -----------------------------------------------------------------------------
# 3. Known-Business Goal Submission
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_known_business_goal_submission():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_known_01",
        run_id="run_known_01",
        user_goal="Audit Acme Dental in Austin"
    )
    state.status = AgentStatus.COMPLETED
    state.prospect_context = _create_mock_context("Acme Dental")
    state.opportunity_analysis = _create_mock_analysis()
    state.outreach_draft = _create_mock_draft()
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    payload = {
        "goal": "Audit Acme Dental in Austin",
        "business_name": "Acme Dental",
        "website_url": "https://acmedental.com",
        "location": "Austin, TX",
        "category": "Dentist"
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "COMPLETED"
        assert data["prospect_context"]["business"]["business_name"] == "Acme Dental"
        assert data["outreach_draft"] is not None

        # Verify initial_params forwarded to agent
        mock_agent.run.assert_called_once()
        call_kwargs = mock_agent.run.call_args.kwargs
        assert call_kwargs["user_goal"] == "Audit Acme Dental in Austin"
        assert call_kwargs["initial_params"]["business_name"] == "Acme Dental"
        assert call_kwargs["initial_params"]["website_url"] == "https://acmedental.com"
        assert call_kwargs["initial_params"]["location"] == "Austin, TX"
        assert call_kwargs["initial_params"]["category"] == "Dentist"


# -----------------------------------------------------------------------------
# 4. Discovery Goal Submission
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_discovery_goal_submission():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_disc_01",
        run_id="run_disc_01",
        user_goal="Find 5 dental clinics in Austin, TX"
    )
    state.status = AgentStatus.COMPLETED
    state.prospects = [
        Business(business_name="Austin Dental 1", phone="512-111-0001", address="Austin, TX", source="test"),
        Business(business_name="Austin Dental 2", phone="512-111-0002", address="Austin, TX", source="test"),
        Business(business_name="Austin Dental 3", phone="512-111-0003", address="Austin, TX", source="test"),
    ]
    state.discovered_count = 3
    state.qualified_count = 3
    state.selected_count = 3
    state.batch_result = MagicMock(
        batch_id="batch_01",
        selected_count=3,
        completed_count=3,
        failed_count=0,
        duration_ms=450.0
    )
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Find 5 dental clinics in Austin, TX", "limit": 5})
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "COMPLETED"
        assert data["prospects_count"] == 3
        assert data["qualification_summary"] == {
            "discovered": 3,
            "qualified": 3,
            "disqualified": 0,
            "selected": 3
        }
        assert data["batch_summary"]["selected_count"] == 3
        assert data["batch_summary"]["completed_count"] == 3


# -----------------------------------------------------------------------------
# 5. Ambiguous Goal and Clarification Response
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ambiguous_goal_returns_clarification():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_clarif_01",
        run_id="run_clarif_01",
        user_goal="Do some work for me"
    )
    state.status = AgentStatus.NEEDS_CLARIFICATION
    state.clarification_request = ClarificationRequest(
        question="Which business name, industry, or geographic location would you like to target?",
        missing_information=["business_name", "location"]
    )
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Do some work for me"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "NEEDS_CLARIFICATION"
        assert "Which business name" in data["clarification_question"]
        assert "business_name" in data["missing_information"]
        assert data["outreach_draft"] is None
        assert "Goal clarification needed" in data["summary"]


# -----------------------------------------------------------------------------
# 6. Invalid Request Validation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_invalid_request_short_goal():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # min_length=3 required for goal
        resp = await client.post("/api/agent/run", json={"goal": "hi"})
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_invalid_request_missing_goal():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"limit": 5})
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_invalid_request_forbids_extra_fields():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Client attempts injecting arbitrary capability or plan
        resp = await client.post("/api/agent/run", json={
            "goal": "Audit dental clinic",
            "injected_capability": "bypass_eval",
            "policy_override": True
        })
        assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 7. Oversized Prospect Limits
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_oversized_prospect_limit_rejected_by_schema():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # limit is bounded le=50
        resp = await client.post("/api/agent/run", json={"goal": "Find 100 dentists", "limit": 100})
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_prospect_limit_clamped_to_safety_ceiling():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_limit_01",
        run_id="run_limit_01",
        user_goal="Find 25 dentists in Austin"
    )
    state.status = AgentStatus.COMPLETED
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Find 25 dentists in Austin", "limit": 25})
        assert resp.status_code == 200

        # Safety ceiling is 15: min(25, 15) == 15
        mock_agent.run.assert_called_once()
        params = mock_agent.run.call_args.kwargs["initial_params"]
        assert params["limit"] == 15


# -----------------------------------------------------------------------------
# 8. Evaluation Failure Reflected Correctly in Response
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_evaluation_failure_blocks_draft_and_sets_status_failed():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_fail_01",
        run_id="run_fail_01",
        user_goal="Audit suspicious website"
    )
    state.status = AgentStatus.FAILED
    state.prospect_context = _create_mock_context()
    state.opportunity_analysis = _create_mock_analysis()
    state.outreach_strategy = _create_mock_strategy()
    state.evaluation_result = _create_mock_eval_result(passed=False)
    state.outreach_draft = None  # Blocked by evaluation gate
    state.record_error("Evaluation gate failed: Grounding score below threshold 0.70")
    state.final_response = AgentFinalResponse(
        task_id="task_fail_01",
        user_goal="Audit suspicious website",
        status=AgentStatus.FAILED,
        summary="Evaluation gate rejected ungrounded reasoning. Outreach blocked.",
        errors=["Evaluation gate failed: Grounding score below threshold 0.70"]
    )
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Audit suspicious website"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "FAILED"
        assert data["evaluation_result"]["passed"] is False
        assert data["outreach_draft"] is None
        assert any("Evaluation gate failed" in err for err in data["errors"])
        assert "Outreach blocked" in data["summary"]


# -----------------------------------------------------------------------------
# 9 & 10. Task Lookup Behavior & Unknown Task Lookup
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_task_lookup_retrieves_cached_task():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_persist_01",
        run_id="run_persist_01",
        user_goal="Audit Acme Dental"
    )
    state.status = AgentStatus.COMPLETED
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Run task
        post_resp = await client.post("/api/agent/run", json={"goal": "Audit Acme Dental"})
        assert post_resp.status_code == 200
        task_id = post_resp.json()["task_id"]

        # Retrieve task
        get_resp = await client.get(f"/api/agent/tasks/{task_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["task_id"] == "task_persist_01"
        assert data["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_unknown_task_id_returns_404():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/agent/tasks/task_nonexistent_999")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found in memory" in data["detail"]
        assert "restarts" in data["detail"]


# -----------------------------------------------------------------------------
# 11. No External Communication Authorization
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_no_external_communication_dispatched():
    mock_agent = MagicMock()
    state = AgentState(
        task_id="task_safe_01",
        run_id="run_safe_01",
        user_goal="Send marketing email and WhatsApp messages"
    )
    state.status = AgentStatus.FAILED
    state.record_error("External dispatch is unsupported and blocked by safety policies.")
    state.final_response = AgentFinalResponse(
        task_id="task_safe_01",
        user_goal="Send marketing email and WhatsApp messages",
        status=AgentStatus.FAILED,
        summary="External messaging is prohibited by system safety policies.",
        errors=["External dispatch is unsupported and blocked by safety policies."]
    )
    mock_agent.run.return_value = state
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Send marketing email and WhatsApp messages"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "FAILED"
        assert data["outreach_draft"] is None
        # Verify no external action was allowed
        assert "External dispatch is unsupported" in data["errors"][0]


# -----------------------------------------------------------------------------
# 12. Security: Unhandled Internal Exception Does Not Leak Secrets or Traces
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_unhandled_agent_exception_does_not_leak_internals():
    mock_agent = MagicMock()
    mock_agent.run.side_effect = RuntimeError("FATAL_SECRET_DB_PASSWORD_12345: Connection dropped at internal/infra.py:42")
    set_agent(mock_agent)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post("/api/agent/run", json={"goal": "Analyze Dental Clinic"})
        assert resp.status_code == 500
        data = resp.json()

        # Must NOT leak secret or stack trace
        assert "FATAL_SECRET_DB_PASSWORD" not in data["detail"]
        assert "internal/infra.py" not in data["detail"]
        assert "An error occurred while executing the agent goal." in data["detail"]


# -----------------------------------------------------------------------------
# 13. Backwards Compatibility with Existing API Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_existing_api_compatibility():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        status_resp = await client.get("/api/status")
        assert status_resp.status_code == 200
        assert "is_running" in status_resp.json()

        runs_resp = await client.get("/api/runs?limit=2")
        assert runs_resp.status_code == 200
        assert runs_resp.json()["success"] is True

        businesses_resp = await client.get("/api/businesses?limit=2")
        assert businesses_resp.status_code == 200
        assert businesses_resp.json()["success"] is True


# -----------------------------------------------------------------------------
# 14. Real Agent Pipeline End-to-End via API
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_full_agent_execution_end_to_end_via_api():
    from unittest.mock import patch
    from application.capabilities.registry import CapabilityRegistry
    from application.contracts.base import CapabilityResult
    from agent.intent import GoalInterpreter
    from agent.agent import Agent
    from agent.telemetry import InMemoryTelemetrySink

    fixture = get_strong_evidence_good_reasoning_fixture()
    ctx = fixture["context"]
    opp = fixture["opportunity_analysis"]
    strat = fixture["outreach_strategy"]
    eval_pass = EvaluationResult(
        overall_score=0.92,
        grounding_score=0.95,
        relevance_score=0.90,
        consistency_score=0.92,
        evidence_coverage_score=0.90,
        hallucination_flags=[],
        issues=[],
        passed=True,
        structural_validity=True,
    )
    draft = OutreachDraft(
        business_name="Apex Plumbing Pros",
        outreach_angles=["Transform your customer booking on iOS"],
        cold_email_draft="Hi team, we noticed mobile booking bottlenecks...",
        whatsapp_draft="Hi, loved your plumbing work in Chicago...",
        generation_mode="template"
    )

    registry = CapabilityRegistry.default_registry()
    sink = InMemoryTelemetrySink()
    real_agent = Agent(
        registry=registry,
        telemetry_sink=sink,
        interpreter=GoalInterpreter(),
    )
    set_agent(real_agent)

    with patch.object(registry, "execute") as mock_exec:
        mock_exec.side_effect = [
            CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
            CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
            CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
            CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
            CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx),
            CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=opp),
            CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=strat),
            CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=eval_pass),
            CapabilityResult(success=True, capability_name="render_outreach_drafts", data=draft),
        ]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            resp = await client.post("/api/agent/run", json={
                "goal": "Research Apex Plumbing Pros and prepare consultative outreach drafts",
                "business_name": "Apex Plumbing Pros",
                "website_url": "https://apexplumbingpros.com"
            })
            assert resp.status_code == 200
            data = resp.json()

            assert data["status"] == "COMPLETED"
            assert data["prospect_context"] is not None
            assert data["prospect_context"]["business"]["business_name"] == "Apex Plumbing Pros"
            assert data["opportunity_analysis"] is not None
            assert data["outreach_strategy"] is not None
            assert data["evaluation_result"]["passed"] is True
            assert data["outreach_draft"]["cold_email_draft"] is not None
            assert len(data["completed_capabilities"]) >= 5

            # Verify task is retrievable via GET /api/agent/tasks/{task_id}
            task_id = data["task_id"]
            get_resp = await client.get(f"/api/agent/tasks/{task_id}")
            assert get_resp.status_code == 200
            get_data = get_resp.json()
            assert get_data["task_id"] == task_id
            assert get_data["status"] == "COMPLETED"
            assert get_data["evaluation_result"]["passed"] is True
