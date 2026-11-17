from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Protocol


class Role(str, Enum):
    """Standard message roles in LLM conversations."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Represents a structured function call request emitted by the model."""
    id: str
    name: str
    arguments: dict[str, Any]
    thought_signature: str | None = None
    raw_part: dict[str, Any] | None = None


@dataclass
class ChatMessage:
    """A single message in the LLM conversation history."""
    role: Role | Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """JSON Schema definition of a tool presented to the LLM."""
    name: str
    description: str
    parameters: dict[str, Any]  # Valid JSON Schema object


@dataclass
class TokenUsage:
    """Token consumption and estimated financial cost accounting."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LLMResponse:
    """Normalized response returned by any LLM provider adapter."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter"] = "stop"
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = "unknown"
    latency_ms: int = 0

    @property
    def has_tool_calls(self) -> bool:
        """Helper to quickly check if the model wants to call tools."""
        return len(self.tool_calls) > 0


class LLMClient(Protocol):
    """Provider-agnostic interface for generating LLM completions and tool calls."""

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generates a completion from the model given messages and optional tools."""
        ...
