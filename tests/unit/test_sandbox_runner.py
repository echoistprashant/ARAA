import asyncio

from app.sandbox.runner import CodeSandboxRunner, SandboxConfig


def test_sandbox_runner_basic_execution():
    """Verifies executing basic Python code and capturing stdout."""
    runner = CodeSandboxRunner()
    code = "print(sum([x * 2 for x in range(10)]))"
    result = asyncio.run(runner.execute_python(code))

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout.strip() == "90"
    assert result.stderr == ""


def test_sandbox_runner_handles_errors():
    """Verifies that runtime exceptions are captured in stderr without crashing."""
    runner = CodeSandboxRunner()
    code = "x = 1 / 0"
    result = asyncio.run(runner.execute_python(code))

    assert result.exit_code == 1
    assert "ZeroDivisionError" in result.stderr


def test_sandbox_runner_timeout():
    """Verifies that long-running/infinite loops are killed after timeout."""
    runner = CodeSandboxRunner(SandboxConfig(timeout_seconds=0.5))
    code = "import time\nwhile True:\n    time.sleep(0.1)"
    result = asyncio.run(runner.execute_python(code))

    assert result.timed_out is True
    assert result.exit_code == 124
    assert "timed out" in result.stderr


def test_sandbox_runner_output_truncation():
    """Verifies truncation when output exceeds max_output_bytes."""
    runner = CodeSandboxRunner(SandboxConfig(max_output_bytes=100))
    code = "print('A' * 500)"
    result = asyncio.run(runner.execute_python(code))

    assert result.truncated is True
    assert "[OUTPUT TRUNCATED]" in result.stdout
