import json
import uuid
from typing import Any
from pydantic import BaseModel, create_model

from app.mcp_servers.research_tools_server import MCPResearchServer
from app.tools.base import RiskLevel, Tool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class DynamicMCPTool:
    """Wrapper that adapts an MCP server tool definition to the ARAA Tool protocol."""

    def __init__(
        self,
        name: str,
        mcp_tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        client: "MCPClient",
        risk_level: RiskLevel = RiskLevel.READ,
    ):
        self._name = name
        self._mcp_tool_name = mcp_tool_name
        self._description = description
        self._input_schema = input_schema
        self._client = client
        self._risk_level = risk_level
        self._args_schema = self._create_pydantic_schema(name, input_schema)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def risk_level(self) -> RiskLevel:
        return self._risk_level

    @property
    def args_schema(self) -> type[BaseModel]:
        return self._args_schema

    def _create_pydantic_schema(self, tool_name: str, schema: dict[str, Any]) -> type[BaseModel]:
        """Dynamically synthesizes a Pydantic model from a JSON Schema object."""
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))
        fields: dict[str, Any] = {}

        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for prop_name, prop_def in properties.items():
            py_type = type_mapping.get(prop_def.get("type", "string"), str)
            default_val = prop_def.get("default", ... if prop_name in required_fields else None)
            fields[prop_name] = (py_type, default_val)

        model_name = f"MCP_{tool_name.title().replace('_', '')}Input"
        return create_model(model_name, **fields)

    async def execute(self, args: Any, ctx: ToolContext) -> ToolResult:
        if isinstance(args, BaseModel):
            raw_args = args.model_dump()
        elif isinstance(args, dict):
            raw_args = args
        else:
            raw_args = dict(args)

        # Dispatch via client using original MCP tool name
        response = await self._client.call_tool(self._mcp_tool_name, raw_args)
        if response.get("isError"):
            error_msg = response["content"][0]["text"] if response.get("content") else "MCP execution failed"
            return ToolResult(content=error_msg, status="failed", trust_level="untrusted")

        output_text = response["content"][0]["text"] if response.get("content") else ""
        return ToolResult(
            content=output_text,
            status="succeeded",
            trust_level="trusted",
        )


class MCPClient:
    """Client adapter connecting ARAA to external or in-process Model Context Protocol servers."""

    def __init__(self, server: MCPResearchServer | None = None):
        self.server = server or MCPResearchServer()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Queries the MCP server for available tool schemas."""
        req = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {},
        }
        res = self.server.handle_request(req)
        if "error" in res:
            raise RuntimeError(f"MCP tools/list failed: {res['error']}")
        return res.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Calls a tool on the MCP server via JSON-RPC."""
        req = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        res = self.server.handle_request(req)
        if "error" in res:
            raise RuntimeError(f"MCP tools/call failed: {res['error']}")
        return res.get("result", {})

    async def register_all_into(
        self,
        registry: ToolRegistry,
        prefix: str = "mcp_",
        risk_level: RiskLevel = RiskLevel.READ,
    ) -> list[str]:
        """Discovers tools on the MCP server and registers dynamic ARAA tools into the registry."""
        mcp_tools = await self.list_tools()
        registered_names: list[str] = []

        for tool_def in mcp_tools:
            original_name = tool_def["name"]
            prefixed_name = f"{prefix}{original_name}" if prefix else original_name
            tool_adapter = DynamicMCPTool(
                name=prefixed_name,
                mcp_tool_name=original_name,
                description=tool_def.get("description", ""),
                input_schema=tool_def.get("inputSchema", {}),
                client=self,
                risk_level=risk_level,
            )
            registry.register(tool_adapter)
            registered_names.append(prefixed_name)

        return registered_names
