import os
import sys
import json
import secrets
import asyncio
import subprocess
import traceback
import logging
from collections import deque
from typing import Dict, Any, List, Optional

# On Windows + Python < 3.12, asyncio defaults to SelectorEventLoop which
# cannot spawn subprocesses. ProactorEventLoop is required.
if sys.platform == "win32" and sys.version_info < (3, 12):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        pass  # Already default

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Header, Security, Depends, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from database.db import DatabaseManager, ScraperRepository
from agent.agent import Agent
from schemas.api import AgentExecutionRequest, AgentExecutionResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Lead Intelligence Platform API")

# Phase 5B: API Authentication dependency
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    api_key_val: Optional[str] = Security(api_key_header),
    auth_header: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    Enforces API authentication using API_AUTH_TOKEN from environment.
    Fails closed if API_AUTH_TOKEN is not configured on the server.
    Safely compares credentials in constant time using secrets.compare_digest.
    Never logs incoming API keys or credentials.
    """
    configured_token = os.getenv("API_AUTH_TOKEN")
    if not configured_token or not configured_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: server API authentication token is not configured.",
        )

    token = api_key_val
    if not token and auth_header:
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        else:
            token = auth_header.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: missing API key. Provide via 'X-API-Key' header.",
        )

    if not secrets.compare_digest(token, configured_token.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid API key.",
        )

    return token


# Sig fix #9: CORS allow_origins=["*"] + allow_credentials=True is invalid
# per the CORS spec — browsers silently reject credentialed cross-origin
# requests when the origin is a wildcard. Use an explicit allowlist from env.
# Note: CORS is a browser origin policy, not an authentication boundary.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Database & Repository dependency injection (Phase 5C)
db_manager = DatabaseManager(lazy=True)
_repo_instance: Optional[ScraperRepository] = None


def get_repository() -> ScraperRepository:
    """Dependency provider for the scraper repository."""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = ScraperRepository(db_manager)
    return _repo_instance


def set_repository(custom_repo: Optional[ScraperRepository]) -> None:
    """Dependency override helper for testing and isolation."""
    global _repo_instance
    _repo_instance = custom_repo


repo = get_repository()


def _resolve_repo(repo_dep: Any) -> ScraperRepository:
    """
    Resolves repository dependency. Falls back to module repo if called directly
    without FastAPI dependency injection runner (e.g. legacy unit test invocation).
    """
    from fastapi.params import Depends
    if repo_dep is None or isinstance(repo_dep, Depends):
        return repo
    return repo_dep


# Significant fix #5: bounded deque buffer (O(1) pops) & concurrency lock
log_history: deque = deque(maxlen=500)
log_queues: List[asyncio.Queue] = []
running_process: Optional[asyncio.subprocess.Process] = None
process_lock = asyncio.Lock()

# Agent task store & dependency management (Phase 4E)
agent_task_store: Dict[str, AgentExecutionResponse] = {}
_task_id_order: deque = deque(maxlen=200)
_agent_instance: Optional[Agent] = None


def get_agent() -> Agent:
    """Dependency provider for the autonomous agent."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = Agent()
    return _agent_instance


def set_agent(agent: Optional[Agent]) -> None:
    """Dependency override for tests or custom agent configurations."""
    global _agent_instance
    _agent_instance = agent


# Significant fix #7: Strict Pydantic input validations
class ScrapeRequest(BaseModel):
    query: Optional[str] = Field(None, max_length=250)
    category: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    limit: Optional[int] = Field(0, ge=0, le=500)
    source: Optional[str] = Field("gmaps", pattern="^(gmaps|justdial|indiamart)$")


class UpdateStatusRequest(BaseModel):
    outreach_status: str = Field(..., pattern="^(new|contacted|followed_up|closed)$")


def add_log(line: str):
    """Adds a log line to buffer and pushes to subscriber queues safely."""
    log_history.append(line)
    for q in list(log_queues):
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            # Drop oldest line if subscriber queue is full to prevent lockup
            try:
                q.get_nowait()
                q.put_nowait(line)
            except Exception:
                pass


async def read_stream(stream: asyncio.StreamReader, is_stderr: bool):
    """
    Critical fix #3: Read lines safely from stdout/stderr.
    Guards against LimitOverrunError and decoding crashes to prevent line buffer lockup.
    """
    while True:
        try:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue

            if is_stderr:
                if " - ERROR - " in line or " - CRITICAL - " in line:
                    formatted = f"[Scraper ERROR] {line}"
                elif " - WARNING - " in line:
                    formatted = f"[Scraper WARNING] {line}"
                else:
                    formatted = f"[Scraper Info] {line}"
            else:
                formatted = f"[Scraper Output] {line}"

            add_log(formatted)
        except asyncio.LimitOverrunError:
            # Over-long line fallback: read chunks
            chunk = await stream.read(4096)
            if not chunk:
                break
            add_log(f"[{'Scraper WARNING' if is_stderr else 'Scraper Output'}] {chunk.decode('utf-8', errors='replace').rstrip()}")
        except Exception as e:
            add_log(f"[System] Stream reader warning: {e}")
            break


def read_sync_stream(stream, is_stderr: bool):
    """Sync line reader for subprocess.Popen fallback."""
    for line in iter(stream.readline, ''):
        if not line:
            break
        line_clean = line.rstrip()
        if not line_clean:
            continue
        if is_stderr:
            if " - ERROR - " in line_clean or " - CRITICAL - " in line_clean:
                formatted = f"[Scraper ERROR] {line_clean}"
            elif " - WARNING - " in line_clean:
                formatted = f"[Scraper WARNING] {line_clean}"
            else:
                formatted = f"[Scraper Info] {line_clean}"
        else:
            formatted = f"[Scraper Output] {line_clean}"
        add_log(formatted)
    try:
        stream.close()
    except Exception:
        pass


async def run_scraper_process(args: List[str]):
    """
    Robust subprocess lifecycle manager.
    Tries async create_subprocess_exec first, then falls back to Popen + ThreadPoolExecutor
    if Windows asyncio event loop limitation (NotImplementedError) occurs.
    """
    global running_process
    rootDir = os.path.dirname(os.path.abspath(__file__))

    venv_python = os.path.join(rootDir, "..", "env", "Scripts", "python.exe")
    venv_python = os.path.normpath(venv_python)
    if not os.path.isfile(venv_python):
        venv_python_alt = os.path.join(rootDir, "env", "Scripts", "python.exe")
        venv_python = venv_python_alt if os.path.isfile(venv_python_alt) else sys.executable

    script_path = os.path.join(rootDir, "pipeline_runner.py")
    cmd = [venv_python, "-u", script_path] + args
    add_log(f"[System] Starting scraper: {' '.join(cmd)}")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}

    use_async = True
    proc = None
    sync_proc = None

    async with process_lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=rootDir,
                env=env
            )
            running_process = proc
            use_async = True
        except (NotImplementedError, AttributeError, Exception) as e:
            add_log(f"[System] Async subprocess spawn limitation ({type(e).__name__}). Using Threaded Popen fallback...")
            try:
                sync_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=rootDir,
                    env=env,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace"
                )
                running_process = sync_proc
                use_async = False
            except Exception as pe:
                add_log(f"[System] Failed to spawn scraper process ({type(pe).__name__}): {pe}")
                running_process = None
                return

    if use_async and proc is not None:
        try:
            await asyncio.gather(
                read_stream(proc.stdout, is_stderr=False),
                read_stream(proc.stderr, is_stderr=True)
            )
            await proc.wait()
            add_log(f"[System] Scraper pipeline finished with exit code {proc.returncode}")
        except Exception as e:
            add_log(f"[System] Execution exception ({type(e).__name__}): {e}")
            add_log(f"[Scraper ERROR] {traceback.format_exc()}")
        finally:
            async with process_lock:
                running_process = None
    elif not use_async and sync_proc is not None:
        try:
            loop = asyncio.get_running_loop()
            t1 = loop.run_in_executor(None, read_sync_stream, sync_proc.stdout, False)
            t2 = loop.run_in_executor(None, read_sync_stream, sync_proc.stderr, True)
            await asyncio.gather(t1, t2)
            await loop.run_in_executor(None, sync_proc.wait)
            add_log(f"[System] Scraper pipeline finished with exit code {sync_proc.returncode}")
        except Exception as e:
            add_log(f"[System] Execution exception in Popen fallback ({type(e).__name__}): {e}")
            add_log(f"[Scraper ERROR] {traceback.format_exc()}")
        finally:
            async with process_lock:
                running_process = None


def is_scraper_running() -> bool:
    """Returns True if a scraper process is actively running."""
    global running_process
    if running_process is not None:
        if hasattr(running_process, "poll"):
            ret = running_process.poll()
            if ret is not None:
                running_process = None
                return False
            return True
        elif hasattr(running_process, "returncode"):
            if running_process.returncode is not None:
                running_process = None
                return False
            return True
    return False


@app.get("/api/status")
def get_status():
    """
    Public health/status endpoint returning pipeline execution state.
    Intentionally unauthenticated for health checks, heartbeat probes, and load balancers.
    """
    running = is_scraper_running()
    return {"success": True, "is_running": running, "running_process": running}



# Significant fix #6: Shutdown event handler to prevent orphan Playwright/Chrome processes
@app.on_event("shutdown")
async def shutdown_event():
    global running_process
    if running_process is not None and running_process.returncode is None:
        try:
            add_log("[System] API server shutting down. Terminating active scraper process...")
            running_process.terminate()
            await asyncio.sleep(1)
            if running_process.returncode is None:
                running_process.kill()
        except Exception as e:
            print(f"Error terminating scraper subprocess on shutdown: {e}")


# ------------------------------------------------------------------
# Business Endpoints (Protected)
# ------------------------------------------------------------------

@app.get("/api/businesses", dependencies=[Depends(verify_api_key)])
def get_businesses(
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    repo_dep: ScraperRepository = Depends(get_repository),
):
    """Returns processed businesses list for dashboard with optional pagination."""
    active_repo = _resolve_repo(repo_dep)
    try:
        biz_list = active_repo.get_businesses_for_dashboard(limit=limit, offset=offset)
        return {"success": True, "businesses": biz_list, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"[API] Error in get_businesses: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while retrieving businesses.")


@app.get("/api/businesses/{business_id}", dependencies=[Depends(verify_api_key)])
def get_business_detail(business_id: int, repo_dep: ScraperRepository = Depends(get_repository)):
    """Returns full enriched detail for a single business."""
    active_repo = _resolve_repo(repo_dep)
    try:
        detail = active_repo.get_business_detail_for_dashboard(business_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Business not found")
        return {"success": True, "business": detail}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error in get_business_detail for id={business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while retrieving business details.")


@app.get("/api/businesses/{business_id}/outreach", dependencies=[Depends(verify_api_key)])
def get_outreach_drafts(business_id: int, repo_dep: ScraperRepository = Depends(get_repository)):
    """Critical fix #2: Encapsulated repo call instead of inline SQL."""
    active_repo = _resolve_repo(repo_dep)
    try:
        outreach = active_repo.get_outreach_drafts(business_id)
        return {"success": True, "outreach": outreach}
    except Exception as e:
        logger.error(f"[API] Error in get_outreach_drafts for id={business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while retrieving outreach drafts.")


@app.get("/api/businesses/{business_id}/intent", dependencies=[Depends(verify_api_key)])
def get_intent_profile(business_id: int, repo_dep: ScraperRepository = Depends(get_repository)):
    """Critical fix #2: Encapsulated repo call instead of inline SQL."""
    active_repo = _resolve_repo(repo_dep)
    try:
        intent = active_repo.get_intent_profile(business_id)
        return {"success": True, "intent": intent}
    except Exception as e:
        logger.error(f"[API] Error in get_intent_profile for id={business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while retrieving intent profile.")


class UpdateBusinessRequest(BaseModel):
    business_name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    outreach_status: Optional[str] = Field(None, pattern="^(new|contacted|followed_up|closed)$")


class BatchDeleteRequest(BaseModel):
    ids: List[str]


@app.delete("/api/businesses", dependencies=[Depends(verify_api_key)])
def delete_all_businesses(repo_dep: ScraperRepository = Depends(get_repository)):
    active_repo = _resolve_repo(repo_dep)
    try:
        active_repo.delete_all_businesses()
        log_history.clear()
        return {"success": True, "message": "Database cleared successfully."}
    except Exception as e:
        logger.error(f"[API] Error in delete_all_businesses: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while clearing businesses.")


@app.delete("/api/businesses/{business_id}", dependencies=[Depends(verify_api_key)])
def delete_single_business(business_id: str, repo_dep: ScraperRepository = Depends(get_repository)):
    """Deletes a single business by ID."""
    active_repo = _resolve_repo(repo_dep)
    try:
        numeric_id = int(business_id)
        active_repo.delete_business(numeric_id)
        return {"success": True, "id": business_id, "message": "Business deleted successfully."}
    except ValueError:
        # Mock ID or non-integer string — return success so frontend removes seamlessly
        return {"success": True, "id": business_id, "message": "Local item removed."}
    except Exception as e:
        logger.error(f"[API] Error in delete_single_business for id={business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while deleting business.")


@app.post("/api/businesses/batch-delete", dependencies=[Depends(verify_api_key)])
def batch_delete_businesses(req: BatchDeleteRequest, repo_dep: ScraperRepository = Depends(get_repository)):
    """Deletes multiple businesses by list of string IDs."""
    if not req.ids:
        return {"success": True, "deleted_count": 0}
    active_repo = _resolve_repo(repo_dep)
    try:
        # Convert IDs to integers safely
        int_ids = [int(i) for i in req.ids if i.isdigit()]
        if not int_ids:
            return {"success": True, "deleted_count": 0}

        deleted_count = active_repo.batch_delete_businesses(int_ids)
        return {"success": True, "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"[API] Error in batch_delete_businesses: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while batch deleting businesses.")


@app.patch("/api/businesses/{business_id}", dependencies=[Depends(verify_api_key)])
def update_business_field(business_id: int, req: UpdateBusinessRequest, repo_dep: ScraperRepository = Depends(get_repository)):
    """Updates one or more fields of a business."""
    updates = req.model_dump(exclude_none=True) if hasattr(req, "model_dump") else req.dict(exclude_none=True)
    if not updates:
        return {"success": True, "message": "No fields to update."}

    active_repo = _resolve_repo(repo_dep)
    try:
        updated = active_repo.update_business(business_id, updates)
        if not updated:
            raise HTTPException(status_code=404, detail="Business not found")
        return {"success": True, "id": business_id, "updated": updates}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error in update_business_field for id={business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while updating business.")



# ------------------------------------------------------------------
# Scraping Endpoints (Protected)
# ------------------------------------------------------------------

@app.post("/api/scrape", dependencies=[Depends(verify_api_key)])
async def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Critical fix #1: Lock-protected scrape trigger prevents process collision."""
    async with process_lock:
        if is_scraper_running():
            return {"success": False, "message": "Scraper is already running in background."}

        args = []
        if req.query and req.query.strip():
            args += [req.query.strip()]
        else:
            if req.category and req.category.strip() and req.category.strip() != "ALL":
                args += ["--category", req.category.strip()]
            if req.city and req.city.strip():
                args += ["--city", req.city.strip()]
            if req.state and req.state.strip():
                args += ["--state", req.state.strip()]
            if req.country and req.country.strip():
                args += ["--country", req.country.strip()]

        if req.limit is not None:
            args += ["--limit", str(req.limit)]

        source = req.source or "gmaps"
        if source in ("justdial", "indiamart"):
            args += ["--source", source]

        log_history.clear()
        background_tasks.add_task(run_scraper_process, args)
        return {"success": True, "message": f"Scraper started successfully in background (source: {source})."}


@app.post("/api/stop", dependencies=[Depends(verify_api_key)])
async def stop_scraper():
    """Terminates active running scraper process safely."""
    global running_process
    async with process_lock:
        if running_process is None:
            return {"success": False, "message": "No active scraper process running."}

        try:
            if hasattr(running_process, "terminate"):
                running_process.terminate()
            elif hasattr(running_process, "kill"):
                running_process.kill()
            
            add_log("[System] 🛑 Scrape process manually terminated by user.")
            running_process = None
            return {"success": True, "message": "Scraper process terminated successfully."}
        except Exception as e:
            logger.error(f"Error terminating process: {e}", exc_info=True)
            return {"success": False, "message": "An error occurred while stopping the scraper process."}



@app.post("/api/recrawl", dependencies=[Depends(verify_api_key)])
async def trigger_recrawl(background_tasks: BackgroundTasks, limit: int = Query(10, ge=1, le=200)):
    """Critical fix #1: Lock-protected recrawl trigger."""
    async with process_lock:
        if is_scraper_running():
            return {"success": False, "message": "Scraper is already running in background."}

        args = ["--recrawl", "--limit", str(limit)]
        log_history.clear()
        background_tasks.add_task(run_scraper_process, args)
        return {"success": True, "message": f"Recrawl mode started (limit: {limit} businesses)."}


# ------------------------------------------------------------------
# Pipeline Run History Endpoints (Protected)
# ------------------------------------------------------------------

@app.get("/api/runs", dependencies=[Depends(verify_api_key)])
def get_pipeline_runs(limit: int = 20, repo_dep: ScraperRepository = Depends(get_repository)):
    """Critical fix #2: Encapsulated repo query for run history."""
    active_repo = _resolve_repo(repo_dep)
    try:
        runs = active_repo.get_pipeline_runs(limit=limit)
        return {"success": True, "runs": runs}
    except Exception as e:
        logger.error(f"Error retrieving pipeline runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while retrieving pipeline runs.")


@app.get("/api/runs/{run_id}", dependencies=[Depends(verify_api_key)])
def get_pipeline_run_detail(run_id: str, repo_dep: ScraperRepository = Depends(get_repository)):
    """Critical fix #2: Encapsulated repo query for run detail."""
    active_repo = _resolve_repo(repo_dep)
    try:
        run = active_repo.get_pipeline_run_detail(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"success": True, "run": run}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving pipeline run detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while retrieving run details.")


# ------------------------------------------------------------------
# Log Streaming (Protected)
# ------------------------------------------------------------------

@app.get("/api/logs", dependencies=[Depends(verify_api_key)])
async def stream_logs():
    async def log_event_generator():
        queue = asyncio.Queue(maxsize=200)
        log_queues.append(queue)

        for log in list(log_history):
            yield f"data: {log}\n\n"

        try:
            while True:
                log = await queue.get()
                yield f"data: {log}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in log_queues:
                log_queues.remove(queue)

    return StreamingResponse(log_event_generator(), media_type="text/event-stream")


# ------------------------------------------------------------------
# Autonomous Agent Endpoints (Phase 4E, Protected)
# ------------------------------------------------------------------

@app.post("/api/agent/run", response_model=AgentExecutionResponse, dependencies=[Depends(verify_api_key)])
@app.post("/api/agent/execute", response_model=AgentExecutionResponse, dependencies=[Depends(verify_api_key)])
def execute_agent_goal(request: AgentExecutionRequest):
    """
    Submits a natural-language user goal to the autonomous agent.

    Synchronous Execution & Lifecycle Semantics:
    - Execution is synchronous within this handler (executed in FastAPI threadpool).
    - Result state is held in an in-memory ring-buffer (max 200 tasks).
    - Task results do NOT survive process restarts or multi-worker process boundaries.
    - Prospect limits are clamped to the platform safety ceiling (15).
    - Client-supplied capability overrides or plan injections are strictly forbidden.
    """
    agent = get_agent()

    # Map validated constraints and optional target entities into initial_params
    params: Dict[str, Any] = {}
    if request.limit is not None:
        params["limit"] = min(request.limit, 15)
    if request.business_name:
        params["business_name"] = request.business_name
    if request.website_url:
        params["website_url"] = request.website_url
    if request.location:
        params["location"] = request.location
    if request.category:
        params["category"] = request.category

    try:
        state = agent.run(user_goal=request.goal, initial_params=params)
        response = AgentExecutionResponse.from_state(state)

        # Store in bounded in-memory registry
        if len(_task_id_order) >= 200:
            oldest = _task_id_order.popleft()
            agent_task_store.pop(oldest, None)
        _task_id_order.append(response.task_id)
        agent_task_store[response.task_id] = response

        return response
    except Exception as e:
        logger.error(f"[AgentAPI] Unhandled error during agent execution: {e}")
        # Never leak raw stack traces or internal implementation details
        raise HTTPException(
            status_code=500,
            detail="An error occurred while executing the agent goal. Please retry with a refined request."
        )


@app.get("/api/agent/tasks/{task_id}", response_model=AgentExecutionResponse, dependencies=[Depends(verify_api_key)])
def get_agent_task(task_id: str):
    """
    Retrieves the execution status and structured results of a previously executed agent task.

    Task Retention Semantics:
    - Retained in process memory only (last 200 tasks).
    - Does not persist across server restarts.
    """
    if task_id not in agent_task_store:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found in memory. Note: tasks reside in process memory and do not persist across restarts."
        )
    return agent_task_store[task_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=True)
