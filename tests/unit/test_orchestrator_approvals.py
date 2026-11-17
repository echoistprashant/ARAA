import asyncio
from typing import Any
from pydantic import BaseModel, Field

from app.agents.orchestrator import Orchestrator
from app.agents.state import RunState, RunStatus
from app.llm.client import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.services.approval_service import ApprovalService
from app.tools.base import RiskLevel, ToolContext, ToolResult
from app.tools.permissions import PolicyEngine, UserRole
from app.tools.registry import ToolRegistry


class DummyWriteInput(BaseModel):
    filename: str = Field(...)
    content: str = Field(...)


class DummyWriteTool:
    """A simulated tool with WRITE risk level requiring approval."""
    name = "file_write"
    description = "Writes file to storage."
    risk_level = RiskLevel.WRITE
    args_schema = DummyWriteInput

    async def execute(self, args: Any, ctx: ToolContext) -> ToolResult:
        return ToolResult(content="File successfully written.", status="succeeded")


def test_orchestrator_pause_and_resume_on_approval():
    """Verifies that Orchestrator pauses on WRITE tool requiring approval, and resumes once approved."""
    registry = ToolRegistry()
    registry.register(DummyWriteTool())

    policy_engine = PolicyEngine()
    approval_service = ApprovalService()

    # Step 1: Model requests file_write
    # Step 2: After approval and execution, model generates final report
    llm = FakeLLM(
        responses=[
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc_1", name="file_write", arguments={"filename": "output.txt", "content": "data"})],
            ),
            LLMResponse(content="Research task completed and saved to disk.", tool_calls=[]),
        ]
    )

    orchestrator = Orchestrator(
        llm=llm,
        registry=registry,
        policy_engine=policy_engine,
        approval_service=approval_service,
    )

    state = RunState(run_id="run_hitl_test", task="Write report to output.txt", user_role="researcher")

    # 1. Execute run - should pause awaiting approval!
    paused_state = asyncio.run(orchestrator.run(state))
    assert paused_state.status == RunStatus.AWAITING_APPROVAL

    # 2. Check pending approvals in service
    pending = asyncio.run(approval_service.list_pending(run_id=state.run_id))
    assert len(pending) == 1
    approval_id = pending[0].approval_id

    # 3. Human resolves approval
    asyncio.run(approval_service.resolve_request(approval_id, "approve", resolved_by="senior_engineer"))

    # 4. Resume run - should proceed with execution and finish!
    resumed_state = asyncio.run(orchestrator.run(paused_state))
    assert resumed_state.status == RunStatus.COMPLETED
    assert "Research task completed" in resumed_state.final_report
