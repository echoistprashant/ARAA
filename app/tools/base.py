from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Protocol
from pydantic import BaseModel


class RiskLevel(str, Enum):
    """Risk tier categorization for agent tools (Least Privilege Policy)."""
    READ = "read"                      # Safe in-memory/scoped reads (e.g. calculator, RAG)
    READ_EXTERNAL = "read_external"    # External fetches (e.g. web search, url fetch)
    WRITE = "write"                    # Internal workspace writes (e.g. file write)
    EXTERNAL_EFFECT = "external_effect"# Outbound side effects (e.g. send email, webhook)
    DANGEROUS = "dangerous"            # High-risk system tools (e.g. shell, delete data)


@dataclass
class ToolContext:
    """Runtime execution context passed to each tool execution."""
    run_id: str
    step_idx: int = 0
    tenant_id: str = "default_tenant"
    user_id: str = "default_user"


@dataclass
class ToolResult:
    """Standardized output produced by any tool."""
    content: str
    status: Literal["succeeded", "failed"] = "succeeded"
    citations: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    cost_usd: float = 0.0
    trust_level: Literal["trusted", "untrusted"] = "trusted"


class ToolError(Exception):
    """Base exception class for tool failures with explicit error taxonomy."""

    def __init__(self, message: str, code: str = "tool_error", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class Tool(Protocol):
    """Protocol that every ARAA tool must satisfy."""
    name: str
    description: str
    risk_level: RiskLevel
    args_schema: type[BaseModel]

    async def execute(self, args: Any, ctx: ToolContext) -> ToolResult:
        """Executes the tool with validated arguments."""
        ...
