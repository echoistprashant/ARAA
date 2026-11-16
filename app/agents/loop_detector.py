import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ActionRecord:
    """Historical trace of a single tool execution action."""
    tool_name: str
    args_hash: str
    evidence_count_before: int


@dataclass
class LoopCheckResult:
    """Result of loop and stall detection evaluation."""
    is_stalled: bool
    reason: str = ""


class LoopDetector:
    """Detects repetitive, cyclic, or stagnant execution patterns in autonomous agents.
    
    Prevents the agent from wandering endlessly or repeating failed queries.
    """

    def __init__(
        self,
        max_consecutive_repeats: int = 3,
        max_stagnant_steps: int = 4,
    ):
        self.max_consecutive = max_consecutive_repeats
        self.max_stagnant_steps = max_stagnant_steps
        self.action_history: list[ActionRecord] = []

    @staticmethod
    def hash_action(tool_name: str, arguments: dict[str, Any]) -> str:
        """Computes a deterministic SHA-256 hash of tool name and sorted JSON arguments."""
        canonical_str = json.dumps(
            {"tool": tool_name, "args": arguments},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:16]

    def record_and_check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        current_evidence_count: int,
    ) -> LoopCheckResult:
        """Records a new action and verifies whether the agent has entered a stall or loop."""
        action_hash = self.hash_action(tool_name, arguments)
        record = ActionRecord(
            tool_name=tool_name,
            args_hash=action_hash,
            evidence_count_before=current_evidence_count,
        )
        self.action_history.append(record)

        # Check 1: Consecutive identical actions (e.g. exact same query 3x)
        if len(self.action_history) >= self.max_consecutive:
            recent_repeats = self.action_history[-self.max_consecutive:]
            if all(r.args_hash == action_hash for r in recent_repeats):
                return LoopCheckResult(
                    is_stalled=True,
                    reason=(
                        f"Detected repeated action loop: tool '{tool_name}' was invoked with identical "
                        f"arguments {self.max_consecutive} times consecutively."
                    ),
                )

        # Check 2: Cyclic 2-step loop pattern: A -> B -> A -> B
        if len(self.action_history) >= 4:
            hashes = [r.args_hash for r in self.action_history]
            if hashes[-1] == hashes[-3] and hashes[-2] == hashes[-4]:
                return LoopCheckResult(
                    is_stalled=True,
                    reason="Detected cyclic loop pattern (repeating alternating tool sequence).",
                )

        # Check 3: Stagnation without evidence progress
        if len(self.action_history) >= self.max_stagnant_steps:
            earliest_count = self.action_history[-self.max_stagnant_steps].evidence_count_before
            if current_evidence_count == earliest_count:
                # If the last N steps produced 0 new evidence items
                unique_tools = {r.tool_name for r in self.action_history[-self.max_stagnant_steps:]}
                if len(unique_tools) <= 2:
                    return LoopCheckResult(
                        is_stalled=True,
                        reason=f"Agent stalled: {self.max_stagnant_steps} consecutive steps produced zero new evidence.",
                    )

        return LoopCheckResult(is_stalled=False, reason="Execution pattern is healthy.")
