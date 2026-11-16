import asyncio

from app.agents.state import RunState, RunStatus, reduce_add_message
from app.llm.client import ChatMessage, Role
from app.repositories.runs_repo import RunsRepository


def test_runs_repo_create_and_checkpoint():
    """Verifies creating a run, recording step checkpoints, and state recovery."""
    repo = RunsRepository()

    # 1. Create run
    state = asyncio.run(repo.create_run(task="Analyze pricing models", tenant_id="acme"))
    assert state.run_id.startswith("run_")
    assert state.status == RunStatus.QUEUED

    # 2. Advance step and checkpoint
    state.step_count = 1
    state.total_input_tokens = 150
    state.total_output_tokens = 50
    state.status = RunStatus.RUNNING
    reduce_add_message(state, ChatMessage(role=Role.USER, content="Start"))

    idemp_key = repo.generate_idempotency_key(state.run_id, 1, "web_search", {"q": "pricing"})
    asyncio.run(repo.checkpoint_step(state, step_kind="llm", idempotency_key=idemp_key))

    # 3. Assert idempotency key is recorded
    assert asyncio.run(repo.has_idempotency_key(idemp_key)) is True

    # 4. Load state back from checkpoint
    recovered = asyncio.run(repo.load_run_state(state.run_id))
    assert recovered is not None
    assert recovered.run_id == state.run_id
    assert recovered.step_count == 1
    assert recovered.total_tokens == 200
    assert len(recovered.messages) == 1
    assert recovered.messages[0].content == "Start"


def test_idempotency_key_canonical_generation():
    """Verifies that key generation is order-independent for argument dicts."""
    repo = RunsRepository()
    args1 = {"query": "qdrant", "limit": 5}
    args2 = {"limit": 5, "query": "qdrant"}  # reversed order

    key1 = repo.generate_idempotency_key("run_1", 1, "search", args1)
    key2 = repo.generate_idempotency_key("run_1", 1, "search", args2)

    assert key1 == key2
