import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/events", tags=["events"])


class EventBroadcaster:
    """In-memory pub-sub event broadcaster for Server-Sent Events (SSE) streaming."""

    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Subscribes to events for a specific agent run."""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribes a queue from a run's event channel."""
        if run_id in self._queues and queue in self._queues[run_id]:
            self._queues[run_id].remove(queue)
            if not self._queues[run_id]:
                del self._queues[run_id]

    async def publish(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Dispatches an event to all active subscribers for the run."""
        message = {"event": event_type, "data": payload}
        for q in self._queues.get(run_id, []):
            await q.put(message)


# Global broadcaster instance
event_broadcaster = EventBroadcaster()


async def event_generator(run_id: str) -> AsyncIterator[str]:
    """Yields formatted SSE messages until terminal event or disconnect."""
    queue = event_broadcaster.subscribe(run_id)
    try:
        while True:
            # Wait for next event with a periodic keepalive ping
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_name = msg["event"]
                data_str = json.dumps(msg["data"])
                yield f"event: {event_name}\ndata: {data_str}\n\n"

                if event_name in ("run_completed", "budget_exceeded", "loop_detected", "failed"):
                    break
            except asyncio.TimeoutError:
                # SSE heartbeat comment
                yield ": keepalive\n\n"
    finally:
        event_broadcaster.unsubscribe(run_id, queue)


@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str):
    """Streams live execution steps, tool events, and status updates via SSE."""
    return StreamingResponse(
        event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
