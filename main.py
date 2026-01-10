"""
FastAPI application.

Adds to the original /solve + /healthz:
  * /auth/*          — register, login (JWT), API-key management
  * /solve           — auth-protected; creates a persisted Run and streams events
  * /runs, /runs/{id}— run history (user-scoped)
  * /runs/{id}/stream— live Server-Sent Events trace of a run

The agent still executes in a background threadpool task. A single-active-run
guard (409 if busy) is enforced because the agent keeps process-global state.
"""
from __future__ import annotations

import asyncio
import queue
import threading
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from agent import run_agent_instrumented
from auth.dependencies import get_current_user, get_user_from_query_token
from auth.routes import router as auth_router
from config import get_settings
from observability.events import AgentEvent, event_bus
from observability.metrics import get_json_logger, log_json
from observability.tracing import configure_tracing
from persistence.db import SessionLocal, get_session, init_db, session_scope
from persistence.models import User
from persistence.repository import RunRepository

settings = get_settings()
logger = get_json_logger("api")

app = FastAPI(title="Autonomous Quiz Solver Agent", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)

START_TIME = time.time()

# --- single-active-run guard (agent uses process-global state) -------------
_run_lock = threading.Lock()
_active_run_id: str | None = None


def _redacted_db_url(url: str) -> str:
    # Hide credentials before logging (e.g. the Supabase password).
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


@app.on_event("startup")
def _startup() -> None:
    init_db()
    configure_tracing()
    log_json(
        logger,
        "api startup",
        model=settings.gemini_model,
        db=_redacted_db_url(settings.database_url),
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}


# --------------------------------------------------------------------------
# /solve
# --------------------------------------------------------------------------
def _resolve_solver(request: Request, body: dict, session: Session) -> int | None:
    """Authenticate a /solve caller. Returns the user id, or None for a legacy
    shared-secret call. Raises 401/403 otherwise."""
    from auth.dependencies import _resolve_user

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    api_key = request.headers.get("x-api-key")
    user = _resolve_user(session, token, api_key)
    if user is not None:
        return user.id

    # Legacy fallback: shared SECRET in the body (deprecated).
    if settings.allow_legacy_secret and settings.secret:
        if body.get("secret") == settings.secret:
            return None
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def _execute_run(run_id: str, url: str, user_id: int | None) -> None:
    """Background task: run the agent, persisting every step + final metrics."""
    global _active_run_id
    try:
        with session_scope() as session:
            def persist(event: AgentEvent) -> None:
                RunRepository.append_step(
                    session,
                    run_id,
                    seq=event.seq,
                    type=event.type,
                    node=event.node,
                    name=event.name,
                    data=event.data,
                )

            outcome = run_agent_instrumented(url, run_id, persist=persist)
            m = outcome.metrics
            RunRepository.finalize_run(
                session,
                run_id,
                status="success" if outcome.success else "failed",
                success=outcome.success,
                prompt_tokens=m.prompt_tokens,
                completion_tokens=m.completion_tokens,
                total_tokens=m.total_tokens,
                est_cost_usd=m.est_cost_usd,
                tool_call_count=m.tool_call_count,
                final_result=outcome.result,
                error=outcome.error,
            )
            log_json(logger, "run finished", run_id=run_id, **m.snapshot(), success=outcome.success)
    finally:
        _active_run_id = None
        if _run_lock.locked():
            _run_lock.release()


@app.post("/solve")
async def solve(request: Request, session: Session = Depends(get_session)):
    global _active_run_id
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")

    user_id = _resolve_solver(request, body, session)

    # Only one quiz chain at a time (process-global agent state).
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail=f"A run is already active: {_active_run_id}")

    run_id = str(uuid.uuid4())
    _active_run_id = run_id
    try:
        RunRepository.create_run(session, run_id, url, user_id)
    except Exception:
        _active_run_id = None
        _run_lock.release()
        raise

    # Run in a real background thread so it survives the response returning.
    threading.Thread(target=_execute_run, args=(run_id, url, user_id), daemon=True).start()

    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "run_id": run_id, "stream": f"/runs/{run_id}/stream"},
    )


# --------------------------------------------------------------------------
# /runs history
# --------------------------------------------------------------------------
def _run_summary(run) -> dict:
    return {
        "id": run.id,
        "url": run.url,
        "status": run.status,
        "success": run.success,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "total_tokens": run.total_tokens,
        "est_cost_usd": run.est_cost_usd,
        "tool_call_count": run.tool_call_count,
    }


@app.get("/runs")
def list_runs(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    runs = RunRepository.list_runs(session, user.id, limit=limit, offset=offset)
    return {"runs": [_run_summary(r) for r in runs]}


@app.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = RunRepository.get_run(session, run_id, user_id=user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    detail = _run_summary(run)
    detail["prompt_tokens"] = run.prompt_tokens
    detail["completion_tokens"] = run.completion_tokens
    detail["final_result"] = run.final_result
    detail["error"] = run.error
    detail["steps"] = [
        {
            "seq": s.seq,
            "type": s.type,
            "node": s.node,
            "name": s.name,
            "data": s.data,
            "ts": s.ts.isoformat() if s.ts else None,
        }
        for s in run.steps
    ]
    return detail


# --------------------------------------------------------------------------
# /runs/{id}/stream — Server-Sent Events
# --------------------------------------------------------------------------
def _done_frame() -> str:
    return AgentEvent(run_id="", seq=-1, type="done").to_sse()


@app.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    user: User = Depends(get_user_from_query_token),
):
    async def event_generator():
        q = event_bus.subscribe(run_id)
        try:
            # Replay any steps already persisted (in case the client connected
            # after the run started or finished).
            replayed_seq = 0
            finished = False
            with SessionLocal() as s:
                run = RunRepository.get_run(s, run_id, user_id=user.id)
                if run is None:
                    yield AgentEvent(run_id=run_id, seq=0, type="error", data={"detail": "not found"}).to_sse()
                    return
                for step in run.steps:
                    ev = AgentEvent(
                        run_id=run_id, seq=step.seq, type=step.type,
                        name=step.name, node=step.node, data=step.data or {},
                    )
                    yield ev.to_sse()
                    replayed_seq = max(replayed_seq, step.seq)
                finished = run.status in ("success", "failed")

            if finished:
                yield _done_frame()
                return

            # Stream live events until the run signals completion.
            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                if item is None:  # end-of-stream sentinel
                    yield _done_frame()
                    break
                if item.seq <= replayed_seq:
                    continue
                yield item.to_sse()
        finally:
            event_bus.unsubscribe(run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
