from typing import Any
from app.tools.base import RiskLevel, Tool, ToolContext, ToolResult


class MCPSecurityPolicy:
    """Zero-trust security policy engine for external MCP tool integrations.
    
    Protects against:
    - Built-in tool shadowing/spoofing (e.g. malicious server trying to override 'fetch_url').
    - Context-flooding / prompt injection denial-of-service via massive output payloads.
    - Unauthorized tool execution outside the allowlist.
    """

    def __init__(
        self,
        server_namespace: str,
        allowed_tools: list[str] | None = None,
        blocked_tools: list[str] | None = None,
        max_output_bytes: int = 10_000,
        default_trust: str = "untrusted",
    ):
        self.server_namespace = server_namespace
        self.allowed_tools = set(allowed_tools) if allowed_tools is not None else None
        self.blocked_tools = set(blocked_tools or [])
        self.max_output_bytes = max_output_bytes
        self.default_trust = default_trust

    def format_namespaced_name(self, raw_tool_name: str) -> str:
        """Enforces unambiguous namespacing to prevent tool collision or spoofing."""
        # Clean alphanumeric characters and underscores
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in raw_tool_name)
        return f"mcp__{self.server_namespace}__{safe_name}"

    def is_tool_allowed(self, raw_tool_name: str) -> bool:
        """Validates if an MCP tool is permitted under allowlist/denylist rules."""
        if raw_tool_name in self.blocked_tools:
            return False
        if self.allowed_tools is not None and raw_tool_name not in self.allowed_tools:
            return False
        return True

    def sanitize_result(self, raw_output: str) -> tuple[str, bool]:
        """Truncates excessively large MCP output payloads to protect LLM context."""
        raw_bytes = raw_output.encode("utf-8")
        if len(raw_bytes) > self.max_output_bytes:
            truncated_bytes = raw_bytes[:self.max_output_bytes]
            clean_text = truncated_bytes.decode("utf-8", errors="ignore")
            notice = f"\n\n[WARNING: MCP output truncated to {self.max_output_bytes} bytes for context safety]"
            return clean_text + notice, True
        return raw_output, False
