from app.agents.state import (
    EvidenceItem,
    PlanStep,
    RunPlan,
    RunState,
    RunStatus,
    reduce_add_message,
    reduce_record_tool_result,
    reduce_set_final_report,
    reduce_set_status,
    reduce_token_usage,
)
from app.llm.client import ChatMessage, Role, TokenUsage
from app.tools.base import ToolResult


def test_run_state_initialization():
    """Verifies default values and property calculations of RunState."""
    state = RunState(
        run_id="run_test_01",
        task="Evaluate vector databases",
    )
    assert state.status == RunStatus.QUEUED
    assert state.step_count == 0
    assert state.total_tokens == 0
    assert len(state.messages) == 0
    assert len(state.evidence) == 0


def test_reduce_add_message():
    """Verifies that reduce_add_message correctly appends conversation turns."""
    state = RunState(run_id="run_1", task="Test Task")
    msg = ChatMessage(role=Role.USER, content="Hello")
    
    updated = reduce_add_message(state, msg)
    assert len(updated.messages) == 1
    assert updated.messages[0].content == "Hello"


def test_reduce_record_tool_result_with_evidence():
    """Verifies that tool results are appended to messages and extracted as evidence items."""
    state = RunState(run_id="run_1", task="Research task", step_count=2)
    
    tool_result = ToolResult(
        content="Qdrant node costs $25/month",
        status="succeeded",
        citations=[{"source_url": "https://qdrant.tech/pricing", "query": "qdrant pricing"}],
        trust_level="untrusted",
    )

    updated = reduce_record_tool_result(state, "call_123", "search_stub", tool_result)

    # Assert message was added
    assert len(updated.messages) == 1
    assert updated.messages[0].role == Role.TOOL
    assert updated.messages[0].name == "search_stub"
    assert updated.messages[0].tool_call_id == "call_123"

    # Assert evidence item was extracted
    assert len(updated.evidence) == 1
    evidence_item = updated.evidence[0]
    assert evidence_item.tool_name == "search_stub"
    assert "costs $25/month" in evidence_item.excerpt
    assert evidence_item.source_url == "https://qdrant.tech/pricing"
    assert evidence_item.trust_level == "untrusted"


def test_reduce_token_usage():
    """Verifies accurate accumulation of tokens and USD cost."""
    state = RunState(run_id="run_1", task="Test Task")
    
    usage1 = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150, cost_usd=0.002)
    usage2 = TokenUsage(input_tokens=200, output_tokens=30, total_tokens=230, cost_usd=0.003)

    reduce_token_usage(state, usage1)
    reduce_token_usage(state, usage2)

    assert state.total_input_tokens == 300
    assert state.total_output_tokens == 80
    assert state.total_tokens == 380
    assert abs(state.total_cost_usd - 0.005) < 1e-6


def test_reduce_status_and_final_report():
    """Verifies state finalization and report synthesis reduction."""
    state = RunState(run_id="run_1", task="Test Task")
    
    reduce_set_status(state, RunStatus.RUNNING)
    assert state.status == RunStatus.RUNNING

    report = "### Executive Summary\nVector DB analysis complete."
    reduce_set_final_report(state, report)

    assert state.status == RunStatus.COMPLETED
    assert state.final_report == report


def test_run_state_json_serialization():
    """Verifies that RunState serializes cleanly to JSON for Postgres checkpointing."""
    state = RunState(
        run_id="run_check_1",
        task="Test Serializability",
        plan=RunPlan(steps=[PlanStep(idx=1, goal="Step 1", success_check="Done")]),
    )
    json_str = state.model_dump_json()
    assert "run_check_1" in json_str
    assert "Step 1" in json_str

    # Deserialization check
    restored = RunState.model_validate_json(json_str)
    assert restored.run_id == "run_check_1"
    assert restored.plan is not None
    assert restored.plan.steps[0].goal == "Step 1"


def test_reduce_record_tool_result_deduplicates_normalized_urls():
    """Verifies that canonical, /amp/, query-string, and trailing-slash URL variants
    are deduplicated both within a tool call and across sequential tool calls.
    """
    state = RunState(run_id="run_dedup", task="Dedup Test", step_count=1)

    res1 = ToolResult(
        content="Search results 1",
        status="succeeded",
        citations=[
            {
                "source_url": "https://www.cnbc.com/2024/06/28/chevron.html",
                "title": "CNBC Canonical",
                "snippet": "Supreme Court overturns Chevron.",
            },
            {
                "source_url": "https://www.cnbc.com/amp/2024/06/28/chevron.html?utm_source=ddg",
                "title": "CNBC AMP Duplicate",
                "snippet": "Supreme Court overturns Chevron (AMP).",
            },
            {
                "source_url": "https://supreme.justia.com/cases/federal/us/467/837/",
                "title": "Justia Chevron",
                "snippet": "Chevron 467 U.S. 837.",
            },
        ],
        trust_level="untrusted",
    )
    reduce_record_tool_result(state, "call_1", "web_search", res1)
    assert len(state.evidence) == 2
    assert state.evidence[0].title == "CNBC Canonical"
    assert state.evidence[1].title == "Justia Chevron"

    state.step_count = 2
    res2 = ToolResult(
        content="Search results 2",
        status="succeeded",
        citations=[
            {
                "source_url": "https://supreme.justia.com/cases/federal/us/467/837",
                "title": "Justia Chevron Duplicate Across Steps",
                "snippet": "Duplicate across step.",
            },
            {
                "source_url": "https://www.scotusblog.com/2024/06/loper-bright/",
                "title": "SCOTUSblog",
                "snippet": "Unique new source.",
            },
        ],
        trust_level="untrusted",
    )
    reduce_record_tool_result(state, "call_2", "web_search", res2)
    assert len(state.evidence) == 3
    assert state.evidence[2].title == "SCOTUSblog"
