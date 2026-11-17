import asyncio
import uuid
from typing import Any
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

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


class RunSummaryResponse(BaseModel):
    run_id: str
    task: str
    status: str
    step_count: int
    final_report: str | None = None
    markdown_report: str | None = None
    audit_passed: bool | None = None
    grounding_score: float | None = None


async def _execute_agent_run(run_id: str, task: str, user_role: str) -> None:
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

        state = RunState(run_id=run_id, task=task, user_role=user_role)
        active_runs[run_id]["status"] = "running"
        await broadcast_event("run_started", {"run_id": run_id, "task": task})

        final_state = await orchestrator.run(state)

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
        active_runs[run_id]["status"] = "failed"
        active_runs[run_id]["error"] = str(e)
        await event_broadcaster.publish(run_id, "failed", {"error": str(e)})


@router.post("", response_model=RunSummaryResponse)
async def create_and_start_run(payload: CreateRunRequest, background_tasks: BackgroundTasks):
    """Creates and starts an autonomous research run in the background."""
    run_id = f"run_{uuid.uuid4().hex[:10]}"

    active_runs[run_id] = {
        "run_id": run_id,
        "task": payload.task,
        "status": "queued",
        "step_count": 0,
        "final_report": None,
        "markdown_report": None,
        "audit_passed": None,
        "grounding_score": None,
        "evidence": [],
    }

    background_tasks.add_task(_execute_agent_run, run_id, payload.task, payload.user_role)

    return RunSummaryResponse(
        run_id=run_id,
        task=payload.task,
        status="queued",
        step_count=0,
    )


@router.get("/{run_id}", response_model=dict[str, Any])
async def get_run_status(run_id: str):
    """Retrieves current status, evidence items, and generated reports for a run."""
    run = active_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("", response_model=list[dict[str, Any]])
async def list_recent_runs():
    """Returns list of recent runs."""
    return list(active_runs.values())
