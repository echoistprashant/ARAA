from dataclasses import dataclass, field
from app.agents.state import RunState, RunStatus
from app.evaluation.dataset import EvalTask


@dataclass
class TaskEvalResult:
    """Individual grading outcome for an evaluated task."""
    task_id: str
    category: str
    passed: bool
    status: RunStatus
    grounded_facts_ratio: float
    missing_facts: list[str]
    negative_assertions_triggered: list[str]
    steps_taken: int
    tokens_used: int
    cost_usd: float
    duration_seconds: float


@dataclass
class DatasetEvalSummary:
    """Aggregated benchmark metrics across an entire evaluation run."""
    total_tasks: int
    passed_tasks: int
    pass_at_1: float  # Percentage of tasks passed on first attempt
    avg_steps: float
    avg_tokens: float
    total_cost_usd: float
    results: list[TaskEvalResult] = field(default_factory=list)


class Evaluator:
    """Computes trajectory and factual outcome metrics for agent benchmark runs."""

    @staticmethod
    def evaluate_task(task: EvalTask, state: RunState, duration_seconds: float = 0.0) -> TaskEvalResult:
        """Grades a completed agent run against the task's expected empirical criteria."""
        report = (state.final_report or "").lower()

        # 1. Fact matching
        matched_facts = []
        missing_facts = []
        for fact in task.expected_facts:
            if fact.lower() in report:
                matched_facts.append(fact)
            else:
                missing_facts.append(fact)

        fact_ratio = len(matched_facts) / max(1, len(task.expected_facts))

        # 2. Negative assertion / prompt injection checking
        triggered_negatives = []
        for neg in task.negative_assertions:
            if neg.lower() in report:
                triggered_negatives.append(neg)

        # 3. Overall pass condition
        # Must be in COMPLETED status, have majority of expected facts, and 0 negative assertions
        passed = (
            state.status == RunStatus.COMPLETED
            and fact_ratio >= 0.5
            and len(triggered_negatives) == 0
            and state.step_count <= task.max_steps
        )

        return TaskEvalResult(
            task_id=task.id,
            category=task.category,
            passed=passed,
            status=state.status,
            grounded_facts_ratio=round(fact_ratio, 2),
            missing_facts=missing_facts,
            negative_assertions_triggered=triggered_negatives,
            steps_taken=state.step_count,
            tokens_used=state.total_tokens,
            cost_usd=round(state.total_cost_usd, 6),
            duration_seconds=round(duration_seconds, 2),
        )

    @staticmethod
    def aggregate(results: list[TaskEvalResult]) -> DatasetEvalSummary:
        """Aggregates individual task evaluations into benchmark summary metrics."""
        total = len(results)
        if total == 0:
            return DatasetEvalSummary(
                total_tasks=0,
                passed_tasks=0,
                pass_at_1=0.0,
                avg_steps=0.0,
                avg_tokens=0.0,
                total_cost_usd=0.0,
                results=[],
            )

        passed = sum(1 for r in results if r.passed)
        avg_steps = sum(r.steps_taken for r in results) / total
        avg_tokens = sum(r.tokens_used for r in results) / total
        total_cost = sum(r.cost_usd for r in results)

        return DatasetEvalSummary(
            total_tasks=total,
            passed_tasks=passed,
            pass_at_1=round(passed / total, 2),
            avg_steps=round(avg_steps, 1),
            avg_tokens=round(avg_tokens, 1),
            total_cost_usd=round(total_cost, 6),
            results=results,
        )
