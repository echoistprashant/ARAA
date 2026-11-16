import asyncio
from typing import Any

from app.agents.budget import BudgetLimits
from app.agents.orchestrator import Orchestrator
from app.agents.state import RunState, RunStatus
from app.llm.client import Role, ToolCall
from app.llm.fake import FakeLLM
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.tools.search_stub import SearchStubTool


def test_orchestrator_successful_run():
    """Verifies that the orchestrator executes multi-step research to completion."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(SearchStubTool())

    fake_llm = FakeLLM()
    # Step 1: Search pricing
    fake_llm.add_response(
        tool_calls=[ToolCall(id="c1", name="search_stub", arguments={"query": "qdrant pricing"})],
        input_tokens=50,
        output_tokens=15,
        cost_usd=0.001,
    )
    # Step 2: Math calculation
    fake_llm.add_response(
        tool_calls=[ToolCall(id="c2", name="calculator", arguments={"expression": "25 * 12"})],
        input_tokens=120,
        output_tokens=15,
        cost_usd=0.002,
    )
    # Step 3: Synthesis
    fake_llm.add_response(
        content="Qdrant node costs $25/month ($300/year).",
        input_tokens=180,
        output_tokens=30,
        cost_usd=0.003,
    )

    orchestrator = Orchestrator(llm=fake_llm, registry=registry)
    initial_state = RunState(run_id="run_orch_1", task="Research Qdrant pricing and compute annual cost")

    final_state = asyncio.run(orchestrator.run(initial_state))

    assert final_state.status == RunStatus.COMPLETED
    assert final_state.step_count == 3
    assert final_state.total_tokens == (50 + 15 + 120 + 15 + 180 + 30)
    assert abs(final_state.total_cost_usd - 0.006) < 1e-6
    assert final_state.final_report == "Qdrant node costs $25/month ($300/year)."
    assert len(final_state.evidence) == 1
    assert final_state.evidence[0].tool_name == "search_stub"


def test_orchestrator_budget_exceeded():
    """Verifies that orchestrator terminates cleanly when max_steps ceiling is reached."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    fake_llm = FakeLLM()
    # Queue 10 calculator calls
    for i in range(10):
        fake_llm.add_response(
            tool_calls=[ToolCall(id=f"c_{i}", name="calculator", arguments={"expression": f"{i} + 1"})]
        )

    # Budget capped at 2 steps
    limits = BudgetLimits(max_steps=2)
    orchestrator = Orchestrator(llm=fake_llm, registry=registry, budget_limits=limits)
    initial_state = RunState(run_id="run_budget_1", task="Test budget stop")

    final_state = asyncio.run(orchestrator.run(initial_state))

    assert final_state.status == RunStatus.BUDGET_EXCEEDED
    assert final_state.step_count == 2
    assert "maximum step ceiling" in (final_state.error or "")


def test_orchestrator_loop_detected():
    """Verifies that orchestrator detects and halts infinite repetitive loops."""
    registry = ToolRegistry()
    registry.register(SearchStubTool())

    fake_llm = FakeLLM()
    # Repeatedly emit exact same query 3 times
    for _ in range(4):
        fake_llm.add_response(
            tool_calls=[ToolCall(id="c_same", name="search_stub", arguments={"query": "stuck query"})]
        )

    orchestrator = Orchestrator(llm=fake_llm, registry=registry)
    initial_state = RunState(run_id="run_loop_1", task="Test loop stop")

    final_state = asyncio.run(orchestrator.run(initial_state))

    assert final_state.status == RunStatus.LOOP_DETECTED
    assert "repeated action loop" in (final_state.error or "").lower()


def test_orchestrator_event_streaming():
    """Verifies that lifecycle and step events are fired to the event listener."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    fake_llm = FakeLLM()
    fake_llm.add_response(
        tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "100 / 4"})]
    )
    fake_llm.add_response(content="Result is 25.")

    events_captured: list[tuple[str, dict[str, Any]]] = []

    async def listener(event_type: str, payload: dict[str, Any]):
        events_captured.append((event_type, payload))

    orchestrator = Orchestrator(llm=fake_llm, registry=registry, event_listener=listener)
    state = RunState(run_id="run_events_1", task="Test event listener")

    asyncio.run(orchestrator.run(state))

    event_names = [e[0] for e in events_captured]
    assert "run_started" in event_names
    assert "step_started" in event_names
    assert "tool_executed" in event_names
    assert "run_completed" in event_names
