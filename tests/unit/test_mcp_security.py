import asyncio

from app.mcp_servers.research_tools_server import MCPResearchServer
from app.tools.base import RiskLevel, ToolContext
from app.tools.mcp.client import MCPClient
from app.tools.mcp.security import MCPSecurityPolicy
from app.tools.registry import ToolRegistry


def test_mcp_security_namespacing_and_filtering():
    """Verifies that MCP tools are securely namespaced and filtered by policy."""
    server = MCPResearchServer()
    client = MCPClient(server=server)
    registry = ToolRegistry()

    policy = MCPSecurityPolicy(
        server_namespace="external_research",
        allowed_tools=["text_statistics"],  # block extract_keywords
        blocked_tools=["extract_keywords"],
        max_output_bytes=50,
    )

    registered = asyncio.run(client.register_all_into(registry, policy=policy))

    # Assert namespacing
    assert "mcp__external_research__text_statistics" in registered
    assert "mcp__external_research__extract_keywords" not in registered

    # Verify tool execution and output safety truncation
    ctx = ToolContext(run_id="run_sec_test")
    result = asyncio.run(
        registry.execute(
            "mcp__external_research__text_statistics",
            {"text": "A comprehensive analysis of distributed autonomous software agents and resilience."},
            ctx,
        )
    )

    assert result.status == "succeeded"
    assert result.trust_level == "untrusted"
    assert result.truncated is True
    assert "WARNING: MCP output truncated" in result.content


def test_mcp_security_block_execution_if_disallowed():
    """Verifies execution is rejected if policy blocks tool dynamically."""
    server = MCPResearchServer()
    client = MCPClient(server=server)
    registry = ToolRegistry()

    policy = MCPSecurityPolicy(
        server_namespace="sandbox",
        allowed_tools=["extract_keywords"],
    )

    registered = asyncio.run(client.register_all_into(registry, policy=policy))
    tool_name = registered[0]

    # Dynamically revoke tool in policy
    policy.blocked_tools.add("extract_keywords")

    ctx = ToolContext(run_id="run_blocked_test")
    result = asyncio.run(registry.execute(tool_name, {"text": "some text"}, ctx))

    assert result.status == "failed"
    assert "Security Policy violation" in result.content
