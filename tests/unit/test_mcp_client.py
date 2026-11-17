import asyncio
import json

from app.mcp_servers.research_tools_server import MCPResearchServer
from app.tools.base import RiskLevel, ToolContext
from app.tools.mcp.client import MCPClient
from app.tools.registry import ToolRegistry


def test_mcp_client_registration_and_execution():
    """Verifies that MCP tools are dynamically converted to ARAA tools and executed."""
    server = MCPResearchServer()
    client = MCPClient(server=server)
    registry = ToolRegistry()

    # Register all MCP tools with 'mcp_' prefix
    registered = asyncio.run(client.register_all_into(registry, prefix="mcp_", risk_level=RiskLevel.READ))

    assert "mcp_extract_keywords" in registered
    assert "mcp_text_statistics" in registered

    # Verify tool is listed in registry
    assert "mcp_extract_keywords" in registry.list_tools()

    # Execute tool through registry
    ctx = ToolContext(run_id="run_mcp_test")
    result = asyncio.run(
        registry.execute(
            "mcp_text_statistics",
            {"text": "Artificial intelligence and distributed agent systems are advancing rapidly."},
            ctx,
        )
    )

    assert result.status == "succeeded"
    data = json.loads(result.content)
    assert data["word_count"] == 9
    assert data["sentence_count"] == 1


def test_mcp_client_error_handling():
    """Verifies graceful handling when an MCP tool fails."""
    server = MCPResearchServer()
    client = MCPClient(server=server)

    # Intentionally call non-existent tool
    res = asyncio.run(client.call_tool("non_existent_tool", {}))
    assert res.get("isError") is True
    assert "Error executing non_existent_tool" in res["content"][0]["text"]
