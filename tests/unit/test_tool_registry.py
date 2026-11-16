import asyncio
from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class CalculatorInput(BaseModel):
    expression: str = Field(description="Mathematical expression to evaluate, e.g. '15 * 4'")


class MockCalculatorTool:
    name = "calculator"
    description = "Evaluates basic math expressions"
    risk_level = RiskLevel.READ
    args_schema = CalculatorInput

    async def execute(self, args: CalculatorInput, ctx: ToolContext) -> ToolResult:
        # Simple safe evaluation for testing
        expr = args.expression.replace(" ", "")
        if expr == "15*4":
            return ToolResult(content="60")
        return ToolResult(content="0")


class ShellTool:
    name = "system_shell"
    description = "Runs raw shell commands"
    risk_level = RiskLevel.DANGEROUS
    args_schema = CalculatorInput

    async def execute(self, args: CalculatorInput, ctx: ToolContext) -> ToolResult:
        return ToolResult(content="executed")


def test_tool_registration_and_schema_extraction():
    """Verifies that registered tools produce valid JSON Schemas for LLMs."""
    registry = ToolRegistry()
    registry.register(MockCalculatorTool())

    definitions = registry.get_definitions()
    assert len(definitions) == 1
    assert definitions[0].name == "calculator"
    assert definitions[0].description == "Evaluates basic math expressions"
    assert "expression" in definitions[0].parameters["properties"]
    assert "expression" in definitions[0].parameters["required"]


def test_tool_successful_execution():
    """Verifies successful dispatch and execution of a registered tool."""
    registry = ToolRegistry()
    registry.register(MockCalculatorTool())

    ctx = ToolContext(run_id="run_123")
    result = asyncio.run(registry.execute("calculator", {"expression": "15 * 4"}, ctx))

    assert result.status == "succeeded"
    assert result.content == "60"


def test_tool_invalid_argument_handling():
    """Verifies that invalid arguments return actionable error messages to the model."""
    registry = ToolRegistry()
    registry.register(MockCalculatorTool())

    ctx = ToolContext(run_id="run_123")
    # Passing empty dict when 'expression' is required
    result = asyncio.run(registry.execute("calculator", {}, ctx))

    assert result.status == "failed"
    assert "Invalid arguments for tool 'calculator'" in result.content
    assert "Field 'expression'" in result.content


def test_unknown_tool_handling():
    """Verifies handling when the model requests a non-existent tool."""
    registry = ToolRegistry()
    registry.register(MockCalculatorTool())

    ctx = ToolContext(run_id="run_123")
    result = asyncio.run(registry.execute("non_existent_tool", {}, ctx))

    assert result.status == "failed"
    assert "Unknown tool 'non_existent_tool'" in result.content
    assert "calculator" in result.content


def test_risk_level_filtering():
    """Verifies that dangerous tools are omitted when a lower risk ceiling is applied."""
    registry = ToolRegistry()
    registry.register(MockCalculatorTool())
    registry.register(ShellTool())

    # Only allow READ level tools
    safe_defs = registry.get_definitions(risk_limit=RiskLevel.READ)
    assert len(safe_defs) == 1
    assert safe_defs[0].name == "calculator"

    # Allow all tools
    all_defs = registry.get_definitions()
    assert len(all_defs) == 2
