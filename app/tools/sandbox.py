from typing import Any
from pydantic import BaseModel, Field

from app.sandbox.runner import CodeSandboxRunner, SandboxConfig
from app.tools.base import RiskLevel, ToolContext, ToolResult


class PythonSandboxInput(BaseModel):
    code: str = Field(..., description="Self-contained Python code to execute for numerical analysis, simulation, or data processing.")


class PythonSandboxTool:
    """Executes Python code in an isolated sandbox with resource bounds and timeouts."""

    def __init__(self, runner: CodeSandboxRunner | None = None):
        self.runner = runner or CodeSandboxRunner()

    @property
    def name(self) -> str:
        return "python_sandbox"

    @property
    def description(self) -> str:
        return (
            "Executes Python code in an isolated, secure sandbox. Use this for complex multi-step math, "
            "data transformations, table aggregations, or statistical simulations. Print results to stdout."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.WRITE

    @property
    def args_schema(self) -> type[BaseModel]:
        return PythonSandboxInput

    async def execute(self, args: Any, ctx: ToolContext) -> ToolResult:
        if isinstance(args, BaseModel):
            code_str = args.code
        elif isinstance(args, dict):
            code_str = args.get("code", "")
        else:
            code_str = getattr(args, "code", str(args))

        res = await self.runner.execute_python(code_str)

        if res.timed_out:
            return ToolResult(
                content=f"Execution timed out: {res.stderr}",
                status="failed",
                truncated=res.truncated,
                trust_level="untrusted",
            )

        if res.exit_code != 0:
            return ToolResult(
                content=f"Execution error (exit {res.exit_code}):\n{res.stderr.strip()}",
                status="failed",
                truncated=res.truncated,
                trust_level="untrusted",
            )

        output = res.stdout.strip() or "Code executed successfully with no stdout."
        return ToolResult(
            content=output,
            status="succeeded",
            truncated=res.truncated,
            trust_level="trusted",
        )
