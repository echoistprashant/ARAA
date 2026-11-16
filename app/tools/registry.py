from typing import Any
from pydantic import ValidationError

from app.llm.client import ToolDefinition
from app.tools.base import RiskLevel, Tool, ToolContext, ToolError, ToolResult


class ToolRegistry:
    """Central registry and dispatch engine for agent tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registers a tool instance into the catalog."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Retrieves a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Returns the names of all registered tools."""
        return list(self._tools.keys())

    def get_definitions(self, risk_limit: RiskLevel | None = None) -> list[ToolDefinition]:
        """Generates wire-level ToolDefinitions with Pydantic JSON Schemas.
        
        Optionally filters out tools exceeding a specified risk ceiling.
        """
        definitions: list[ToolDefinition] = []

        # Risk ordering for filtering
        risk_ranks = {
            RiskLevel.READ: 1,
            RiskLevel.READ_EXTERNAL: 2,
            RiskLevel.WRITE: 3,
            RiskLevel.EXTERNAL_EFFECT: 4,
            RiskLevel.DANGEROUS: 5,
        }

        max_rank = risk_ranks.get(risk_limit, 99) if risk_limit else 99

        for tool in self._tools.values():
            if risk_ranks.get(tool.risk_level, 99) > max_rank:
                continue

            schema = tool.args_schema.model_json_schema()

            # Clean schema for strict LLM tool calling compatibility
            parameters = {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }

            definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=parameters,
                )
            )

        return definitions

    async def execute(
        self,
        name: str,
        raw_args: dict[str, Any] | None,
        ctx: ToolContext,
    ) -> ToolResult:
        """Safely dispatches and executes a tool with strict Pydantic argument validation."""
        tool = self._tools.get(name)
        if not tool:
            available = ", ".join(self.list_tools()) or "none"
            return ToolResult(
                status="failed",
                content=f"Error: Unknown tool '{name}'. Available tools are: {available}.",
            )

        # 1. Pydantic validation
        args_payload = raw_args or {}
        try:
            validated_args = tool.args_schema.model_validate(args_payload)
        except ValidationError as val_err:
            # Format concise, model-actionable error message
            error_messages = []
            for err in val_err.errors():
                loc = ".".join(str(x) for x in err.get("loc", []))
                msg = err.get("msg", "invalid")
                error_messages.append(f"Field '{loc}': {msg}")
            
            detailed_err = "; ".join(error_messages)
            return ToolResult(
                status="failed",
                content=f"Invalid arguments for tool '{name}': {detailed_err}. Please correct the parameters and try again.",
            )

        # 2. Execution with error boundary
        try:
            return await tool.execute(validated_args, ctx)
        except ToolError as te:
            return ToolResult(
                status="failed",
                content=f"Tool '{name}' execution error: {te.message}",
            )
        except Exception as e:
            return ToolResult(
                status="failed",
                content=f"Unexpected internal error executing tool '{name}': {str(e)}",
            )
