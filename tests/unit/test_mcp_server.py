import json

from app.mcp_servers.research_tools_server import MCPResearchServer


def test_mcp_server_initialize():
    """Verifies MCP JSON-RPC initialize handshake."""
    server = MCPResearchServer()
    req = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {},
    }
    res = server.handle_request(req)
    assert res["id"] == "1"
    assert "serverInfo" in res["result"]
    assert res["result"]["serverInfo"]["name"] == "araa-research-tools"


def test_mcp_server_tools_list():
    """Verifies listing available tools via MCP protocol."""
    server = MCPResearchServer()
    req = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "tools/list",
        "params": {},
    }
    res = server.handle_request(req)
    assert res["id"] == "2"
    tools = res["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "extract_keywords" in tool_names
    assert "text_statistics" in tool_names


def test_mcp_server_tool_call():
    """Verifies executing tools over MCP JSON-RPC protocol."""
    server = MCPResearchServer()

    # Call extract_keywords
    call_req = {
        "jsonrpc": "2.0",
        "id": "3",
        "method": "tools/call",
        "params": {
            "name": "extract_keywords",
            "arguments": {
                "text": "Deep learning models and neural networks require large datasets for training artificial intelligence.",
                "max_keywords": 3,
            },
        },
    }
    res = server.handle_request(call_req)
    assert res["id"] == "3"
    assert res["result"]["isError"] is False
    payload = json.loads(res["result"]["content"][0]["text"])
    assert "keywords" in payload
    assert payload["count"] <= 3

    # Call text_statistics
    call_stats = {
        "jsonrpc": "2.0",
        "id": "4",
        "method": "tools/call",
        "params": {
            "name": "text_statistics",
            "arguments": {
                "text": "Autonomous agents are transforming intelligence. They plan and execute actions reliably.",
            },
        },
    }
    res_stats = server.handle_request(call_stats)
    stats_payload = json.loads(res_stats["result"]["content"][0]["text"])
    assert stats_payload["word_count"] > 5
    assert stats_payload["sentence_count"] == 2
