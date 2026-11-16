import asyncio
import time

from app.agents.state import RunState, RunStatus, reduce_add_message
from app.llm.client import ChatMessage, LLMResponse, Role, ToolCall
from app.llm.fake import FakeLLM
from app.repositories.runs_repo import RunsRepository
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.workers.run_worker import AgentWorker


def test_worker_claim_and_execute_to_completion():
    """Verifies that an AgentWorker claims a queued run, executes it, and releases the lease."""
    repo = RunsRepository()
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    llm = FakeLLM(
        responses=[
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call_1", name="calculator", arguments={"expression": "5 * 5"})],
            ),
            LLMResponse(
                content="Calculation complete. The result is 25.",
                tool_calls=[],
            ),
        ]
    )

    # 1. Create run in repo
    state = asyncio.run(repo.create_run(task="Compute 5 * 5"))
    run_id = state.run_id

    # 2. Worker executes run
    worker = AgentWorker(worker_id="worker_alpha", runs_repo=repo, llm=llm, registry=registry)
    final_state = asyncio.run(worker.execute_run(run_id))

    assert final_state.status == RunStatus.COMPLETED
    assert "25" in final_state.final_report
    assert final_state.step_count == 2

    # 3. Verify lease is cleanly released
    raw_run = repo._runs_db[run_id]
    assert raw_run["worker_id"] is None
    assert raw_run["status"] == RunStatus.COMPLETED.value


def test_worker_contention_prevented():
    """Verifies that a second worker cannot claim an active run held by another worker."""
    repo = RunsRepository()
    state = asyncio.run(repo.create_run(task="Concurrent task"))
    run_id = state.run_id

    # Worker 1 claims run
    claimed_1 = asyncio.run(repo.claim_run(run_id, worker_id="worker_1", lease_duration_seconds=60))
    assert claimed_1 is True

    # Worker 2 attempts to claim run while lease is active
    claimed_2 = asyncio.run(repo.claim_run(run_id, worker_id="worker_2", lease_duration_seconds=60))
    assert claimed_2 is False


def test_worker_crash_recovery_and_idempotent_resume():
    """Simulates a mid-run worker crash at step 1 and verifies recovery without duplicate execution."""
    repo = RunsRepository()
    registry = ToolRegistry()
    calc_tool = CalculatorTool()
    registry.register(calc_tool)

    # Pre-populate run state as if Worker 1 executed step 1 and then crashed
    state = asyncio.run(repo.create_run(task="Compute 100 + 50"))
    run_id = state.run_id

    # Step 1 was executed by Worker 1 before crashing
    state.step_count = 1
    state.status = RunStatus.RUNNING
    reduce_add_message(state, ChatMessage(role=Role.USER, content="Compute 100 + 50"))
    reduce_add_message(
        state,
        ChatMessage(
            role=Role.ASSISTANT,
            content=None,
            tool_calls=[ToolCall(id="tc_1", name="calculator", arguments={"expression": "100 + 50"})],
        ),
    )
    reduce_add_message(
        state,
        ChatMessage(role=Role.TOOL, content="150", tool_call_id="tc_1", name="calculator"),
    )

    # Checkpoint step 1 with idempotency key
    idemp_key = repo.generate_idempotency_key(run_id, 1, "calculator", {"expression": "100 + 50"})
    asyncio.run(repo.checkpoint_step(state, step_kind="tool", idempotency_key=idemp_key))

    # Mark Worker 1's lease as expired (simulating crash / timeout)
    repo._runs_db[run_id]["worker_id"] = "dead_worker"
    repo._runs_db[run_id]["lease_expires_at"] = time.time() - 10.0  # 10s in the past

    # Worker 2 comes online with LLM providing the concluding final report
    llm_worker2 = FakeLLM(
        responses=[
            LLMResponse(content="The final calculated sum is 150.", tool_calls=[]),
        ]
    )

    worker2 = AgentWorker(
        worker_id="worker_beta",
        runs_repo=repo,
        llm=llm_worker2,
        registry=registry,
    )

    # Worker 2 resumes run
    final_state = asyncio.run(worker2.execute_run(run_id))

    assert final_state.status == RunStatus.COMPLETED
    assert "150" in final_state.final_report
    assert final_state.step_count == 2

    # Checkpoint count should now have step 1 (from before crash) + completion step
    steps = repo._steps_db[run_id]
    assert len(steps) >= 2


def test_worker_zombie_recovery_sweep():
    """Verifies that recover_zombies identifies expired runs and drives them to completion."""
    repo = RunsRepository()
    registry = ToolRegistry()
    state = asyncio.run(repo.create_run(task="Zombie task"))
    run_id = state.run_id

    # Simulate expired lease on running task
    repo._runs_db[run_id]["status"] = RunStatus.RUNNING.value
    repo._runs_db[run_id]["worker_id"] = "ghost_worker"
    repo._runs_db[run_id]["lease_expires_at"] = time.time() - 30.0

    llm = FakeLLM(responses=[LLMResponse(content="Recovered report", tool_calls=[])])
    worker = AgentWorker(worker_id="sweeper", runs_repo=repo, llm=llm, registry=registry)

    recovered = asyncio.run(worker.recover_zombies())
    assert run_id in recovered

    updated_run = repo._runs_db[run_id]
    assert updated_run["status"] == RunStatus.COMPLETED.value
