import asyncio

from app.llm.client import Role, ToolCall
from app.llm.fake import FakeLLM
from scripts.toy_loop import run_toy_agent_loop


def test_toy_agent_loop_multistep_success():
    """Verifies that the agent loop successfully resolves a multi-step research and calculation task."""
    fake = FakeLLM()
    # Step 1: Search for pricing
    fake.add_response(
        tool_calls=[ToolCall(id="c1", name="search_stub", arguments={"query": "Qdrant pricing"})],
        input_tokens=40,
        output_tokens=10,
    )
    # Step 2: Calculate annual cost
    fake.add_response(
        tool_calls=[ToolCall(id="c2", name="calculator", arguments={"expression": "25 * 12"})],
        input_tokens=80,
        output_tokens=10,
    )
    # Step 3: Produce final answer
    fake.add_response(
        content="Qdrant costs $25/mo, which is $300/year.",
        input_tokens=120,
        output_tokens=20,
    )

    task = "Find monthly cost of Qdrant and calculate its yearly total."
    result = asyncio.run(run_toy_agent_loop(task, fake, max_steps=5))

    assert result["status"] == "completed"
    assert result["steps_taken"] == 3
    assert result["total_tokens"] == 280
    assert "$300/year" in result["final_answer"]

    # Verify conversation history sequence:
    # 0: SYSTEM
    # 1: USER
    # 2: ASSISTANT (tool_calls=[search_stub])
    # 3: TOOL (observation from search_stub)
    # 4: ASSISTANT (tool_calls=[calculator])
    # 5: TOOL (observation from calculator)
    # 6: ASSISTANT (final answer)
    msgs = result["messages"]
    assert len(msgs) == 7
    assert msgs[0].role == Role.SYSTEM
    assert msgs[1].role == Role.USER
    assert msgs[2].role == Role.ASSISTANT and msgs[2].tool_calls[0].name == "search_stub"
    assert msgs[3].role == Role.TOOL and msgs[3].name == "search_stub"
    assert msgs[4].role == Role.ASSISTANT and msgs[4].tool_calls[0].name == "calculator"
    assert msgs[5].role == Role.TOOL and msgs[5].content == "300"
    assert msgs[6].role == Role.ASSISTANT and "Qdrant costs" in msgs[6].content


def test_toy_agent_loop_budget_exceeded():
    """Verifies that the agent halts safely when max_steps limit is reached."""
    fake = FakeLLM()
    # Script an infinite loop where model keeps repeating calculator call
    for i in range(10):
        fake.add_response(
            tool_calls=[ToolCall(id=f"c_{i}", name="calculator", arguments={"expression": "1 + 1"})],
            input_tokens=20,
            output_tokens=5,
        )

    task = "Loop indefinitely"
    # Cap at 3 steps
    result = asyncio.run(run_toy_agent_loop(task, fake, max_steps=3))

    assert result["status"] == "budget_exceeded"
    assert result["steps_taken"] == 3
    assert "Exceeded maximum allowed step budget" in result["final_answer"]
