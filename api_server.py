import os
import sys
import json
import asyncio
import subprocess
import traceback
from collections import deque
from typing import Dict, Any, List, Optional

# On Windows + Python < 3.12, asyncio defaults to SelectorEventLoop which
# cannot spawn subprocesses. ProactorEventLoop is required.
if sys.platform == "win32" and sys.version_info < (3, 12):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        pass  # Already default

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from database.db import DatabaseManager, ScraperRepository

app = FastAPI(title="Lead Intelligence Platform API")

# Sig fix #9: CORS allow_origins=["*"] + allow_credentials=True is invalid
# per the CORS spec — browsers silently reject credentialed cross-origin
# requests when the origin is a wildcard. Use an explicit allowlist from env.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

db_manager = DatabaseManager()
repo = ScraperRepository(db_manager)

# Significant fix #5: bounded deque buffer (O(1) pops) & concurrency lock
log_history: deque = deque(maxlen=500)
log_queues: List[asyncio.Queue] = []
running_process: Optional[asyncio.subprocess.Process] = None
process_lock = asyncio.Lock()


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


async def run_scraper_process(args: List[str]):
    """
    Critical fix #1 & #4: Robust subprocess lifecycle manager.
    Guarantees state cleanup even if process spawning fails.
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
        except Exception as e:
            add_log(f"[System] Failed to spawn scraper process ({type(e).__name__}): {e}")
            running_process = None
            return

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


def is_scraper_running() -> bool:
    """Returns True if a scraper process is actively running."""
    global running_process
    if running_process is not None:
        if running_process.returncode is not None:
            running_process = None
            return False
        return True
    return False


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
# Business Endpoints
# ------------------------------------------------------------------

@app.get("/api/businesses")
def get_businesses(limit: Optional[int] = Query(None, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """Returns processed businesses list for dashboard with optional pagination."""
    try:
        biz_list = repo.get_businesses_for_dashboard(limit=limit, offset=offset)
        return {"success": True, "businesses": biz_list, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/businesses/{business_id}")
def get_business_detail(business_id: int):
    """Returns full enriched detail for a single business."""
    try:
        detail = repo.get_business_detail_for_dashboard(business_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Business not found")
        return {"success": True, "business": detail}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/businesses/{business_id}/outreach")
def get_outreach_drafts(business_id: int):
    """Critical fix #2: Encapsulated repo call instead of inline SQL."""
    try:
        outreach = repo.get_outreach_drafts(business_id)
        return {"success": True, "outreach": outreach}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/businesses/{business_id}/intent")
def get_intent_profile(business_id: int):
    """Critical fix #2: Encapsulated repo call instead of inline SQL."""
    try:
        intent = repo.get_intent_profile(business_id)
        return {"success": True, "intent": intent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/businesses")
def delete_all_businesses():
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM businesses;")
        log_history.clear()
        return {"success": True, "message": "Database cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/businesses/{business_id}")
def update_outreach_status(business_id: int, req: UpdateStatusRequest):
    query_sql = "UPDATE businesses SET outreach_status = %s WHERE id = %s RETURNING id;"
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_sql, (req.outreach_status, business_id))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Business not found")
        return {"success": True, "id": business_id, "outreach_status": req.outreach_status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Scraping Endpoints
# ------------------------------------------------------------------

@app.post("/api/scrape")
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


@app.post("/api/recrawl")
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
# Pipeline Run History Endpoints
# ------------------------------------------------------------------

@app.get("/api/runs")
def get_pipeline_runs(limit: int = 20):
    """Critical fix #2: Encapsulated repo query for run history."""
    try:
        runs = repo.get_pipeline_runs(limit=limit)
        return {"success": True, "runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/runs/{run_id}")
def get_pipeline_run_detail(run_id: str):
    """Critical fix #2: Encapsulated repo query for run detail."""
    try:
        run = repo.get_pipeline_run_detail(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"success": True, "run": run}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Log Streaming & Status
# ------------------------------------------------------------------

@app.get("/api/logs")
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


@app.get("/api/status")
def get_status():
    """Returns whether the scraper is currently running."""
    return {"is_running": is_scraper_running()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=True)
