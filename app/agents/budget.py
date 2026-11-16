import time
from dataclasses import dataclass
from typing import Literal

from app.agents.state import RunState


@dataclass
class BudgetLimits:
    """Configurable multidimensional budget ceilings for an agent run."""
    max_steps: int = 25
    max_cost_usd: float = 1.50
    timeout_s: float = 600.0


@dataclass
class BudgetCheckResult:
    """Result of budget verification check before an execution turn."""
    is_exceeded: bool
    reason: Literal["ok", "max_steps_exceeded", "max_cost_exceeded", "timeout_exceeded"] = "ok"
    message: str = ""


class BudgetManager:
    """Enforces multidimensional safety boundaries (steps, cost, wall-clock time).
    
    Prevents runaway token burns, infinite execution, and cloud bill spikes.
    """

    def __init__(self, limits: BudgetLimits | None = None):
        self.limits = limits or BudgetLimits()

    def check(self, state: RunState) -> BudgetCheckResult:
        """Verifies if the current run state is within all configured ceilings."""
        # 1. Step Budget Check
        if state.step_count >= self.limits.max_steps:
            return BudgetCheckResult(
                is_exceeded=True,
                reason="max_steps_exceeded",
                message=f"Agent exceeded maximum step ceiling ({self.limits.max_steps} steps).",
            )

        # 2. Financial Token Cost Check
        if state.total_cost_usd >= self.limits.max_cost_usd:
            return BudgetCheckResult(
                is_exceeded=True,
                reason="max_cost_exceeded",
                message=(
                    f"Agent exceeded financial cost limit of ${self.limits.max_cost_usd:.2f} "
                    f"(current spend: ${state.total_cost_usd:.4f})."
                ),
            )

        # 3. Wall-Clock Timeout Check
        if state.start_time_epoch is not None:
            elapsed = time.time() - state.start_time_epoch
            if elapsed >= self.limits.timeout_s:
                return BudgetCheckResult(
                    is_exceeded=True,
                    reason="timeout_exceeded",
                    message=f"Agent exceeded execution timeout of {self.limits.timeout_s}s (elapsed: {elapsed:.1f}s).",
                )

        return BudgetCheckResult(is_exceeded=False, reason="ok", message="Within budget boundaries.")
