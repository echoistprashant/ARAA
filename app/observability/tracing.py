import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """An individual OpenTelemetry-compatible tracing span."""
    trace_id: str
    span_id: str
    name: str
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    start_time_epoch: float = field(default_factory=time.time)
    end_time_epoch: float | None = None
    status: str = "UNSET"  # "OK", "ERROR", "UNSET"
    error_message: str | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def end(self, status: str = "OK", error: str | None = None) -> None:
        self.end_time_epoch = time.time()
        self.status = status
        self.error_message = error


class Tracer:
    """Manages distributed trace contexts and span collection."""

    def __init__(self, service_name: str = "araa-agent"):
        self.service_name = service_name
        self.completed_spans: list[Span] = []
        self._current_trace_id: str = uuid.uuid4().hex
        self._span_stack: list[Span] = []

    @contextmanager
    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
        """Context manager creating and managing the lifecycle of a tracing span."""
        parent_id = self._span_stack[-1].span_id if self._span_stack else None
        span = Span(
            trace_id=self._current_trace_id,
            span_id=uuid.uuid4().hex[:16],
            name=name,
            parent_span_id=parent_id,
            attributes=attributes or {},
        )
        self._span_stack.append(span)

        try:
            yield span
            span.end(status="OK")
        except Exception as e:
            span.end(status="ERROR", error=str(e))
            raise
        finally:
            self._span_stack.pop()
            self.completed_spans.append(span)

    def get_spans(self) -> list[Span]:
        """Returns all completed spans."""
        return list(self.completed_spans)

    def clear(self) -> None:
        """Clears completed spans."""
        self.completed_spans.clear()


# Default global tracer instance
default_tracer = Tracer()
