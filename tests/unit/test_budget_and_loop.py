import time

from app.agents.budget import BudgetLimits, BudgetManager
from app.agents.loop_detector import LoopDetector
from app.agents.state import RunState


def test_budget_within_limits():
    """Verifies that an agent state within configured limits passes checks."""
    manager = BudgetManager(BudgetLimits(max_steps=10, max_cost_usd=1.00, timeout_s=60.0))
    state = RunState(run_id="r1", task="Test", step_count=2, total_cost_usd=0.10, start_time_epoch=time.time())

    result = manager.check(state)
    assert result.is_exceeded is False
    assert result.reason == "ok"


def test_budget_step_limit_exceeded():
    """Verifies that reaching max_steps halts execution."""
    manager = BudgetManager(BudgetLimits(max_steps=5))
    state = RunState(run_id="r1", task="Test", step_count=5)

    result = manager.check(state)
    assert result.is_exceeded is True
    assert result.reason == "max_steps_exceeded"
    assert "maximum step ceiling" in result.message


def test_budget_cost_limit_exceeded():
    """Verifies that exceeding financial cost ceiling triggers budget exceeded."""
    manager = BudgetManager(BudgetLimits(max_cost_usd=0.50))
    state = RunState(run_id="r1", task="Test", total_cost_usd=0.55)

    result = manager.check(state)
    assert result.is_exceeded is True
    assert result.reason == "max_cost_exceeded"
    assert "$0.50" in result.message


def test_budget_timeout_exceeded():
    """Verifies that exceeding wall-clock execution time halts execution."""
    manager = BudgetManager(BudgetLimits(timeout_s=5.0))
    # Start time was 10 seconds ago
    state = RunState(run_id="r1", task="Test", start_time_epoch=time.time() - 10.0)

    result = manager.check(state)
    assert result.is_exceeded is True
    assert result.reason == "timeout_exceeded"
    assert "execution timeout" in result.message


def test_loop_detector_consecutive_repeats():
    """Verifies detection of identical tool calls 3 times in a row."""
    detector = LoopDetector(max_consecutive_repeats=3)

    # Call 1 & 2: Same query, healthy
    res1 = detector.record_and_check("search_stub", {"query": "pricing"}, 0)
    assert res1.is_stalled is False

    res2 = detector.record_and_check("search_stub", {"query": "pricing"}, 0)
    assert res2.is_stalled is False

    # Call 3: 3rd identical call triggers loop detection
    res3 = detector.record_and_check("search_stub", {"query": "pricing"}, 0)
    assert res3.is_stalled is True
    assert "repeated action loop" in res3.reason.lower()


def test_loop_detector_cyclic_repeats():
    """Verifies detection of alternating cyclic tool pattern (A -> B -> A -> B)."""
    detector = LoopDetector()

    detector.record_and_check("search_stub", {"query": "qdrant"}, 1)
    detector.record_and_check("calculator", {"expression": "10 * 2"}, 1)
    detector.record_and_check("search_stub", {"query": "qdrant"}, 1)
    res = detector.record_and_check("calculator", {"expression": "10 * 2"}, 1)

    assert res.is_stalled is True
    assert "cyclic loop pattern" in res.reason.lower()


def test_loop_detector_stagnation():
    """Verifies detection when 4 consecutive steps produce zero new evidence."""
    detector = LoopDetector(max_stagnant_steps=4)

    # 4 calls made, but evidence count remains 0 throughout
    detector.record_and_check("search_stub", {"query": "qdrant"}, 0)
    detector.record_and_check("search_stub", {"query": "weaviate"}, 0)
    detector.record_and_check("search_stub", {"query": "pgvector"}, 0)
    res = detector.record_and_check("search_stub", {"query": "pinecone"}, 0)

    assert res.is_stalled is True
    assert "zero new evidence" in res.reason.lower()


def test_loop_detector_healthy_progression():
    """Verifies that diverse queries and accumulating evidence pass without false alarms."""
    detector = LoopDetector()

    res1 = detector.record_and_check("search_stub", {"query": "qdrant pricing"}, 0)
    assert res1.is_stalled is False

    res2 = detector.record_and_check("calculator", {"expression": "25 * 12"}, 1)
    assert res2.is_stalled is False

    res3 = detector.record_and_check("search_stub", {"query": "pgvector benchmarks"}, 2)
    assert res3.is_stalled is False
