from datetime import datetime, timezone
from enum import Enum
import re
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
    title: str | None = None
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
    user_role: str = "researcher"
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
            # Extract distinct snippet and title for each individual evidence item
            snippet = citation.get("snippet") or citation.get("excerpt")
            title = citation.get("title")

            if not snippet:
                # If no individual snippet was provided, parse corresponding [idx+1] block from result.content
                pattern = rf"\[{idx + 1}\]\s*([^\n]+)?\n?(?:.*?Snippet:\s*(.*?))(?=(?:\n\[\d+\])|\Z)"
                match = re.search(pattern, result.content, re.DOTALL)
                if match:
                    matched_title = match.group(1).strip() if match.group(1) else None
                    matched_snippet = match.group(2).strip() if match.group(2) else None
                    if matched_title and not title:
                        title = matched_title
                    snippet = matched_snippet or match.group(0)[:500].strip()
                else:
                    snippet = result.content[:500].strip()

            source_url = citation.get("source_url") or citation.get("url") or citation.get("source")
            query = citation.get("query")
            state.evidence.append(
                EvidenceItem(
                    id=item_id,
                    tool_name=tool_name,
                    title=title,
                    excerpt=snippet,
                    source_url=source_url,
                    query=query,
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


def reduce_set_plan(state: RunState, plan: RunPlan) -> RunState:
    """Sets or edits the research plan (supports human edit-in-flight)."""
    state.plan = plan
    state.current_subgoal_idx = 0
    if plan.steps:
        plan.steps[0].status = "in_progress"
    return state


def reduce_advance_subgoal(state: RunState) -> RunState:
    """Marks the active sub-goal as completed and advances to the next step."""
    if not state.plan or not state.plan.steps:
        return state

    idx = state.current_subgoal_idx
    if idx < len(state.plan.steps):
        state.plan.steps[idx].status = "completed"

    if idx + 1 < len(state.plan.steps):
        state.current_subgoal_idx = idx + 1
        state.plan.steps[idx + 1].status = "in_progress"

    return state
