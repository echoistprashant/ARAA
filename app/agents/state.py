from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

from app.llm.client import ChatMessage, Role, TokenUsage
from app.tools.base import ToolResult


class RunStatus(str, Enum):
    """Lifecycle states of an autonomous agent run."""
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"
    LOOP_DETECTED = "loop_detected"


class EvidenceItem(BaseModel):
    """A distinct factual excerpt collected by tools to ground final reports."""
    id: str
    tool_name: str
    excerpt: str
    source_url: str | None = None
    query: str | None = None
    trust_level: Literal["trusted", "untrusted"] = "untrusted"
    collected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PlanStep(BaseModel):
    """An individual sub-goal decomposed by the planner."""
    idx: int
    goal: str
    success_check: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class RunPlan(BaseModel):
    """Structured research plan decomposed into sequential sub-goals."""
    steps: list[PlanStep] = Field(default_factory=list)


class RunState(BaseModel):
    """Immutable, typed snapshot of an agent run's complete state.
    
    Acts as the source of truth for checkpointing, replay, and recovery.
    """
    run_id: str
    tenant_id: str = "default_tenant"
    user_id: str = "default_user"
    task: str
    status: RunStatus = RunStatus.QUEUED
    plan: RunPlan | None = None
    current_subgoal_idx: int = 0
    messages: list[ChatMessage] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    step_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    start_time_epoch: float | None = None
    final_report: str | None = None
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


# ------------------------------------------------------------------------------
# Pure Reducer Functions (State Transitions)
# ------------------------------------------------------------------------------

def reduce_add_message(state: RunState, message: ChatMessage) -> RunState:
    """Appends a new message to the conversation history."""
    state.messages.append(message)
    return state


def reduce_record_tool_result(
    state: RunState,
    tool_call_id: str,
    tool_name: str,
    result: ToolResult,
) -> RunState:
    """Appends the tool observation and extracts evidence items."""
    # 1. Append tool observation message to prompt history
    state.messages.append(
        ChatMessage(
            role=Role.TOOL,
            name=tool_name,
            tool_call_id=tool_call_id,
            content=result.content,
        )
    )

    # 2. Extract evidence items if tool provides citations or factual findings
    if result.status == "succeeded" and result.citations:
        for idx, citation in enumerate(result.citations):
            item_id = f"ev_{state.step_count}_{idx}_{tool_name}"
            state.evidence.append(
                EvidenceItem(
                    id=item_id,
                    tool_name=tool_name,
                    excerpt=result.content[:500],  # Bounded excerpt
                    source_url=citation.get("source_url"),
                    query=citation.get("query"),
                    trust_level=result.trust_level,
                )
            )

    return state


def reduce_token_usage(state: RunState, usage: TokenUsage) -> RunState:
    """Accumulates token consumption and estimated financial cost."""
    state.total_input_tokens += usage.input_tokens
    state.total_output_tokens += usage.output_tokens
    state.total_cost_usd += usage.cost_usd
    return state


def reduce_set_status(state: RunState, status: RunStatus, error: str | None = None) -> RunState:
    """Updates the execution status and optional error explanation."""
    state.status = status
    if error:
        state.error = error
    return state


def reduce_set_final_report(state: RunState, report: str) -> RunState:
    """Attaches the synthesized final report and marks the run as completed."""
    state.final_report = report
    state.status = RunStatus.COMPLETED
    return state
