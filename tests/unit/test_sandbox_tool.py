import asyncio

from app.sandbox.runner import CodeSandboxRunner, SandboxConfig
from app.tools.base import RiskLevel, ToolContext
from app.tools.sandbox import PythonSandboxTool


def test_python_sandbox_tool_properties():
    """Verifies tool metadata and risk tier."""
    tool = PythonSandboxTool()
    assert tool.name == "python_sandbox"
    assert tool.risk_level == RiskLevel.WRITE


def test_python_sandbox_tool_successful_math():
    """Verifies running Python code to compute mathematical operations."""
    tool = PythonSandboxTool()
    ctx = ToolContext(run_id="run_sandbox_test")

    code = (
        "data = [10, 20, 30, 40, 50]\n"
        "mean = sum(data) / len(data)\n"
        "print(f'mean={mean}')\n"
    )

    result = asyncio.run(tool.execute({"code": code}, ctx=ctx))
    assert result.status == "succeeded"
    assert "mean=30.0" in result.content


def test_python_sandbox_tool_adversarial_timeout():
    """Verifies that an adversarial infinite loop is halted and reported as failed."""
    runner = CodeSandboxRunner(SandboxConfig(timeout_seconds=0.5))
    tool = PythonSandboxTool(runner=runner)
    ctx = ToolContext(run_id="run_adversarial_test")

    code = "while True:\n    pass\n"
    result = asyncio.run(tool.execute({"code": code}, ctx=ctx))

    assert result.status == "failed"
    assert "timed out" in result.content
