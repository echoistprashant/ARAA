import time
from dataclasses import dataclass, field
from typing import Any

from app.llm.client import ChatMessage, LLMResponse, TokenUsage


@dataclass
class GenerationRecord:
    """Detailed observation record of an individual LLM generation turn."""
    trace_id: str
    generation_id: str
    model: str
    input_messages_count: int
    output_length: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


class LangfuseAdapter:
    """Zero-cost observability adapter for LLM calls with optional Langfuse cloud export."""

    def __init__(self, enabled: bool = False, public_key: str | None = None):
        self.enabled = enabled
        self.public_key = public_key
        self._records: list[GenerationRecord] = []

    def log_generation(
        self,
        trace_id: str,
        generation_id: str,
        model: str,
        messages: list[ChatMessage],
        response: LLMResponse,
        latency_ms: float,
    ) -> GenerationRecord:
        """Records an LLM generation with token and cost breakdown."""
        usage = response.usage or TokenUsage()
        record = GenerationRecord(
            trace_id=trace_id,
            generation_id=generation_id,
            model=model,
            input_messages_count=len(messages),
            output_length=len(response.content or ""),
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=round(latency_ms, 2),
        )
        self._records.append(record)
        return record

    def get_summary(self, trace_id: str | None = None) -> dict[str, Any]:
        """Calculates total prompt tokens, completion tokens, and financial cost."""
        records = [r for r in self._records if trace_id is None or r.trace_id == trace_id]
        return {
            "total_generations": len(records),
            "total_prompt_tokens": sum(r.prompt_tokens for r in records),
            "total_completion_tokens": sum(r.completion_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records),
            "total_cost_usd": round(sum(r.cost_usd for r in records), 6),
            "avg_latency_ms": round(sum(r.latency_ms for r in records) / len(records), 2) if records else 0.0,
        }
