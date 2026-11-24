import asyncio
import logging
import re
import uuid
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _format_clean_error(err_str: str) -> str:
    """Formats raw errors/JSON into human-readable user-facing status messages."""
    err_lower = err_str.lower()
    if any(s in err_lower for s in ["503", "unavailable", "high demand", "overloaded", "busy"]):
        return (
            "The AI research model is temporarily experiencing high demand (HTTP 503 / Service Unavailable). "
            "All retries and fallbacks were exhausted. Your collected evidence has been preserved. Please retry shortly."
        )
    if any(s in err_lower for s in ["429", "resource_exhausted", "quota"]):
        return (
            "The AI service rate limit was reached (HTTP 429). "
            "All retries were exhausted. Your collected evidence has been preserved. Please retry in a few moments."
        )
    if any(s in err_lower for s in ["500", "502", "504", "gateway"]):
        return "The AI service encountered a temporary server error. Please retry shortly."
    if "{" in err_str and "}" in err_str:
        match = re.search(r'"message":\s*"([^"]+)"', err_str)
        if match:
            return f"Model error: {match.group(1)}"
    return err_str[:300]

from app.agents.exporter import ReportExporter
from app.agents.orchestrator import Orchestrator
from app.agents.state import RunState, RunStatus
from app.agents.synthesizer import Synthesizer
from app.agents.verifier import Verifier
from app.api.v1.approvals import approval_service
from app.api.v1.events import event_broadcaster
from app.core.config import settings
from app.llm.fake import FakeLLM
from app.llm.providers.gemini import GeminiProvider
from app.tools import get_default_registry
from app.tools.permissions import PolicyEngine

router = APIRouter(prefix="/runs", tags=["runs"])

# In-memory store for active and completed runs
active_runs: dict[str, dict[str, Any]] = {}


class CreateRunRequest(BaseModel):
    task: str = Field(..., description="The research or analytical goal for the agent.")
    user_role: str = Field(default="researcher", description="User permission role (viewer, researcher, operator, admin).")
    session_id: str | None = Field(default=None, description="Client session identifier for isolated history.")


class RunSummaryResponse(BaseModel):
    run_id: str
    task: str
    status: str
    step_count: int
    final_report: str | None = None
    markdown_report: str | None = None
    audit_passed: bool | None = None
    grounding_score: float | None = None


async def _execute_agent_run(run_id: str, task: str, user_role: str, session_id: str = "default_session") -> None:
    """Background worker driving the agent run and publishing real-time events."""
    try:
        # 1. Setup LLM provider
        if settings.GEMINI_API_KEY:
            llm = GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.ACTOR_MODEL)
        else:
            # Deterministic fallback if unconfigured
            llm = FakeLLM()

        registry = get_default_registry()
        policy_engine = PolicyEngine()

        async def broadcast_event(event_type: str, payload: dict[str, Any]) -> None:
            await event_broadcaster.publish(run_id, event_type, payload)

        orchestrator = Orchestrator(
            llm=llm,
            registry=registry,
            policy_engine=policy_engine,
            approval_service=approval_service,
            event_listener=broadcast_event,
        )

        state = RunState(run_id=run_id, task=task, user_role=user_role, tenant_id=session_id)
        final_state = state
        active_runs[run_id]["status"] = "running"
        await broadcast_event("run_started", {"run_id": run_id, "task": task})

        final_state = await orchestrator.run(state)

        # Broadcast synthesis phase and checkpoint intermediate results
        active_runs[run_id]["step_count"] = final_state.step_count
        active_runs[run_id]["evidence"] = [ev.model_dump() for ev in final_state.evidence]
        if final_state.final_report:
            active_runs[run_id]["final_report"] = final_state.final_report
        await broadcast_event("synthesizing", {"run_id": run_id, "message": "Synthesizing verified report & empirical audit..."})

        # Post-run synthesis and verification
        synthesizer = Synthesizer(llm=llm)
        report = await synthesizer.synthesize(task, final_state.evidence)

        verifier = Verifier()
        audit = verifier.verify(report, final_state.evidence)

        markdown = ReportExporter.to_markdown(
            report,
            audit,
            final_state.evidence,
            raw_final_report=final_state.final_report,
        )

        active_runs[run_id].update({
            "status": final_state.status.value,
            "step_count": final_state.step_count,
            "final_report": final_state.final_report,
            "markdown_report": markdown,
            "audit_passed": audit.passed,
            "grounding_score": audit.grounding_score,
            "evidence": [ev.model_dump() for ev in final_state.evidence],
        })

        await broadcast_event("run_finished", {
            "run_id": run_id,
            "status": final_state.status.value,
            "final_report": final_state.final_report,
            "markdown": markdown,
            "grounding_score": audit.grounding_score,
        })

    except Exception as e:
        logger.error("Error executing agent run '%s': %s", run_id, e, exc_info=True)
        # Preserve work already done: collected evidence and step count must not be discarded
        preserved_evidence = [
            ev.model_dump() for ev in (getattr(final_state, "evidence", None) or getattr(state, "evidence", []))
        ]
        preserved_steps = getattr(final_state, "step_count", getattr(state, "step_count", 0))

        clean_error = _format_clean_error(str(e))
        active_runs[run_id]["status"] = "failed"
        active_runs[run_id]["step_count"] = preserved_steps
        active_runs[run_id]["evidence"] = preserved_evidence
        active_runs[run_id]["error"] = clean_error
        await event_broadcaster.publish(run_id, "failed", {"error": clean_error, "step_count": preserved_steps})


@router.post("", response_model=RunSummaryResponse)
async def create_and_start_run(
    payload: CreateRunRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """Creates and starts an autonomous research run in the background with session isolation."""
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    session_id = payload.session_id or x_session_id or f"sess_{uuid.uuid4().hex[:8]}"

    active_runs[run_id] = {
        "run_id": run_id,
        "session_id": session_id,
        "task": payload.task,
        "status": "queued",
        "step_count": 0,
        "final_report": None,
        "markdown_report": None,
        "audit_passed": None,
        "grounding_score": None,
        "evidence": [],
    }

    background_tasks.add_task(_execute_agent_run, run_id, payload.task, payload.user_role, session_id)

    return RunSummaryResponse(
        run_id=run_id,
        task=payload.task,
        status="queued",
        step_count=0,
    )


@router.get("/{run_id}", response_model=dict[str, Any])
async def get_run_status(
    run_id: str,
    session_id: str | None = Query(None),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """Retrieves current status, evidence items, and generated reports for a run."""
    run = active_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    active_session = session_id or x_session_id
    if run.get("session_id") and active_session and run.get("session_id") != active_session:
        raise HTTPException(status_code=404, detail="Run not found.")

    return run


@router.get("", response_model=list[dict[str, Any]])
async def list_recent_runs(
    session_id: str | None = Query(None, description="Client session ID to filter history."),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """Returns list of recent runs isolated strictly to the calling session."""
    active_session = session_id or x_session_id
    if not active_session:
        return []

    return [
        run for run in active_runs.values()
        if run.get("session_id") == active_session
    ]


@router.delete("", response_model=dict[str, Any])
async def clear_session_runs(
    session_id: str | None = Query(None),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """Clears all runs for the calling session."""
    active_session = session_id or x_session_id
    if not active_session:
        return {"cleared": 0}

    to_delete = [
        k for k, v in active_runs.items()
        if v.get("session_id") == active_session
    ]
    for k in to_delete:
        active_runs.pop(k, None)

    return {"cleared": len(to_delete)}
