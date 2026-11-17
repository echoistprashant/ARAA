import asyncio

from app.agents.state import RunState, RunStatus
from app.evaluation.dataset import EvalTask, EvaluationDataset
from app.evaluation.metrics import Evaluator
from scripts.run_eval import run_evaluation_suite


def test_evaluation_dataset_structure():
    """Verifies standard evaluation tasks are properly populated."""
    tasks = EvaluationDataset.get_standard_tasks()
    assert len(tasks) >= 3
    for t in tasks:
        assert t.id.startswith("eval_")
        assert len(t.expected_facts) > 0


def test_evaluator_task_grading():
    """Verifies task outcome grading and negative assertion filtering."""
    task = EvalTask(
        id="test_01",
        category="math",
        prompt="Solve 10+10",
        expected_facts=["20"],
        negative_assertions=["30"],
        max_steps=5,
    )

    # Passing run
    passing_state = RunState(
        run_id="run_1",
        task="Solve 10+10",
        status=RunStatus.COMPLETED,
        final_report="The result is 20.",
        step_count=2,
    )
    result = Evaluator.evaluate_task(task, passing_state)
    assert result.passed is True
    assert result.grounded_facts_ratio == 1.0

    # Failing run (negative assertion triggered)
    failing_state = RunState(
        run_id="run_2",
        task="Solve 10+10",
        status=RunStatus.COMPLETED,
        final_report="The result is 20, or possibly 30.",
        step_count=2,
    )
    fail_result = Evaluator.evaluate_task(task, failing_state)
    assert fail_result.passed is False
    assert "30" in fail_result.negative_assertions_triggered


def test_evaluator_aggregate_summary():
    """Verifies benchmark aggregation arithmetic."""
    task = EvalTask(id="t1", category="general", prompt="p", expected_facts=["x"])
    s1 = RunState(run_id="1", task="p", status=RunStatus.COMPLETED, final_report="x", step_count=2)
    s2 = RunState(run_id="2", task="p", status=RunStatus.FAILED, final_report="", step_count=4)

    r1 = Evaluator.evaluate_task(task, s1)
    r2 = Evaluator.evaluate_task(task, s2)

    summary = Evaluator.aggregate([r1, r2])
    assert summary.total_tasks == 2
    assert summary.passed_tasks == 1
    assert summary.pass_at_1 == 0.5
    assert summary.avg_steps == 3.0


def test_run_eval_script_execution():
    """Verifies that the AgentOps evaluation runner executes end-to-end with 100% pass."""
    exit_code = asyncio.run(run_evaluation_suite())
    assert exit_code == 0
