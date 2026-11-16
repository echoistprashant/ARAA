from typing import Any
from app.llm.client import ChatMessage, LLMResponse, TokenUsage, ToolCall, ToolDefinition


class FakeLLM:
    """Deterministic, scriptable in-memory LLM implementation for tests.
    
    Zero cost, zero network, 100% predictable.
    Allows replaying exact sequences of tool calls and text answers.
    """

    def __init__(self, responses: list[LLMResponse] | None = None):
        self.responses: list[LLMResponse] = list(responses or [])
        self.history: list[list[ChatMessage]] = []
        self.tools_received: list[list[ToolDefinition] | None] = []
        self.call_count: int = 0

    def add_response(
        self,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        input_tokens: int = 10,
        output_tokens: int = 10,
        cost_usd: float = 0.0,
    ) -> None:
        """Helper to append a scripted response to the replay queue."""
        self.responses.append(
            LLMResponse(
                content=content,
                tool_calls=tool_calls or [],
                finish_reason="tool_calls" if tool_calls else "stop",
                usage=TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    cost_usd=cost_usd,
                ),
                model="fake-llm-v1",
                latency_ms=1,
            )
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Returns the next queued response or a default stop response."""
        self.call_count += 1
        self.history.append(list(messages))
        self.tools_received.append(tools)

        if self.responses:
            return self.responses.pop(0)

        # Default fallback response if no scripted responses remain
        return LLMResponse(
            content="[Default FakeLLM response]",
            finish_reason="stop",
            usage=TokenUsage(input_tokens=5, output_tokens=5, total_tokens=10),
            model="fake-llm-v1",
            latency_ms=1,
        )
