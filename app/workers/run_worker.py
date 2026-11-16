import asyncio
import logging
import uuid
from typing import Any

from app.agents.orchestrator import Orchestrator
from app.agents.state import RunState, RunStatus
from app.llm.client import LLMClient
from app.repositories.runs_repo import RunsRepository
from app.tools.registry import ToolRegistry

logger = logging.getLogger("araa.worker")


class AgentWorker:
    """Production background worker for distributed task execution.
    
    Guarantees:
    - At-least-once task execution with idempotent step deduplication.
    - Lease-based concurrency preventing multiple workers from stepping on each other.
    - Automatic zombie detection and resume from last durable checkpoint.
    """

    def __init__(
        self,
        worker_id: str | None = None,
        runs_repo: RunsRepository | None = None,
        llm: LLMClient | None = None,
        registry: ToolRegistry | None = None,
        lease_duration_seconds: float = 60.0,
    ):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.runs_repo = runs_repo or RunsRepository()
        self.llm = llm
        self.registry = registry or ToolRegistry()
        self.lease_duration_seconds = lease_duration_seconds
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}

    async def _heartbeat_loop(self, run_id: str) -> None:
        """Periodically refreshes the worker's lease on an active run."""
        interval = max(0.5, self.lease_duration_seconds / 3.0)
        try:
            while True:
                await asyncio.sleep(interval)
                success = await self.runs_repo.heartbeat(run_id, self.worker_id, self.lease_duration_seconds)
                if not success:
                    logger.warning("Heartbeat renewal failed for run %s by worker %s", run_id, self.worker_id)
                    break
        except asyncio.CancelledError:
            pass

    async def execute_run(self, run_id: str) -> RunState:
        """Claims a run, hydrates state from checkpoint, and executes to completion."""
        if not self.llm:
            raise ValueError("Cannot execute run without a configured LLMClient.")

        # 1. Acquire lease
        claimed = await self.runs_repo.claim_run(run_id, self.worker_id, self.lease_duration_seconds)
        if not claimed:
            raise RuntimeError(f"Worker {self.worker_id} failed to claim run {run_id}. Already claimed or invalid state.")

        # 2. Hydrate state
        state = await self.runs_repo.load_run_state(run_id)
        if not state:
            raise ValueError(f"Run {run_id} not found in repository.")

        if state.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            logger.info("Run %s is already terminal (%s). Skipping execution.", run_id, state.status)
            await self.runs_repo.release_run(run_id, self.worker_id, state.status.value)
            return state

        # 3. Start background heartbeat task
        hb_task = asyncio.create_task(self._heartbeat_loop(run_id))
        self._heartbeat_tasks[run_id] = hb_task

        try:
            # 4. Instantiate orchestrator wired to this repository
            orchestrator = Orchestrator(
                llm=self.llm,
                registry=self.registry,
                runs_repo=self.runs_repo,
            )

            # 5. Execute or resume run loop
            final_state = await orchestrator.run(state)
            return final_state

        finally:
            # Cancel heartbeat and release worker lease with final status
            if run_id in self._heartbeat_tasks:
                self._heartbeat_tasks[run_id].cancel()
                del self._heartbeat_tasks[run_id]

            await self.runs_repo.release_run(
                run_id,
                self.worker_id,
                state.status.value if "state" in locals() and state else None,
            )

    async def recover_zombies(self) -> list[str]:
        """Finds orphaned runs whose previous worker crashed and resumes them."""
        zombies = await self.runs_repo.get_zombie_runs(timeout_seconds=self.lease_duration_seconds)
        recovered: list[str] = []
        for run_id in zombies:
            logger.warning("Recovering zombie run %s", run_id)
            try:
                await self.execute_run(run_id)
                recovered.append(run_id)
            except Exception as e:
                logger.error("Failed to recover zombie run %s: %s", run_id, e)
        return recovered
