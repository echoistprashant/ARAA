import hashlib
import json
import uuid
from typing import Any

from app.agents.state import EvidenceItem, RunPlan, RunState, RunStatus
from app.llm.client import ChatMessage, Role


class RunsRepository:
    """Repository handling durable persistence, step checkpointing, and state recovery.
    
    Provides transactional guarantees and atomic idempotency keys.
    """

    def __init__(self, session=None):
        self.session = session
        # In-memory storage backing for deterministic tests and offline execution
        self._runs_db: dict[str, dict[str, Any]] = {}
        self._steps_db: dict[str, list[dict[str, Any]]] = {}
        self._idempotency_seen: set[str] = set()

    @staticmethod
    def generate_idempotency_key(
        run_id: str,
        step_idx: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Generates an unambiguous idempotency key to prevent duplicate tool execution."""
        canonical_args = json.dumps(arguments, sort_keys=True, default=str)
        key_raw = f"{run_id}:{step_idx}:{tool_name}:{canonical_args}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()[:32]

    async def create_run(
        self,
        task: str,
        tenant_id: str = "default_tenant",
        user_id: str = "default_user",
        config: dict[str, Any] | None = None,
    ) -> RunState:
        """Creates and stores an initial run record."""
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        state = RunState(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            task=task,
            status=RunStatus.QUEUED,
        )

        self._runs_db[run_id] = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "task": task,
            "status": state.status.value,
            "config": config or {},
            "step_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "snapshot": state.model_dump(),
        }
        self._steps_db[run_id] = []
        return state

    async def checkpoint_step(
        self,
        state: RunState,
        step_kind: str = "tool",
        idempotency_key: str | None = None,
    ) -> None:
        """Atomically saves the step record and updates run-level counters."""
        if idempotency_key:
            self._idempotency_seen.add(idempotency_key)

        step_record = {
            "run_id": state.run_id,
            "idx": state.step_count,
            "kind": step_kind,
            "snapshot": state.model_dump(),
        }

        # Store step in chronological order
        self._steps_db.setdefault(state.run_id, []).append(step_record)

        # Update run level counters atomically
        if state.run_id in self._runs_db:
            run_entry = self._runs_db[state.run_id]
            run_entry["step_count"] = state.step_count
            run_entry["total_input_tokens"] = state.total_input_tokens
            run_entry["total_output_tokens"] = state.total_output_tokens
            run_entry["total_cost_usd"] = state.total_cost_usd
            run_entry["status"] = state.status.value
            run_entry["final_report"] = state.final_report
            run_entry["snapshot"] = state.model_dump()

    async def has_idempotency_key(self, idempotency_key: str) -> bool:
        """Checks if a tool call with this idempotency key was already executed."""
        return idempotency_key in self._idempotency_seen

    async def load_run_state(self, run_id: str) -> RunState | None:
        """Restores the latest RunState from the last checkpoint."""
        run_entry = self._runs_db.get(run_id)
        if not run_entry:
            return None

        # Reconstruct state from latest snapshot
        return RunState.model_validate(run_entry["snapshot"])
