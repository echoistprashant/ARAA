import asyncio
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.client import ChatMessage, LLMClient, Role, ToolCall
from app.llm.fake import FakeLLM
from app.tools.base import ToolContext
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.tools.search_stub import SearchStubTool


async def run_toy_agent_loop(
    task: str,
    llm: LLMClient,
    max_steps: int = 10,
) -> dict[str, Any]:
    """Executes a framework-free, wire-level 2-tool agent loop.
    
    Demonstrates:
    1. Reason -> 2. Propose Tool Call -> 3. Execute -> 4. Observe -> 5. Synthesize.
    """
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(SearchStubTool())
    tool_defs = registry.get_definitions()

    ctx = ToolContext(run_id="toy_run_demo")

    system_prompt = (
        "You are an autonomous technical research assistant. "
        "Use the 'search_stub' tool to find technical specifications and pricing facts. "
        "Always use the 'calculator' tool for any mathematical calculations or cost estimation. "
        "When you have collected all necessary facts and completed the math, answer the user's "
        "question directly and summarize your findings."
    )

    messages: list[ChatMessage] = [
        ChatMessage(role=Role.SYSTEM, content=system_prompt),
        ChatMessage(role=Role.USER, content=task),
    ]

    steps_taken = 0
    total_tokens = 0
    terminated_reason = "completed"

    while steps_taken < max_steps:
        steps_taken += 1

        # 1. Ask model for next action
        response = await llm.generate(messages=messages, tools=tool_defs)
        total_tokens += response.usage.total_tokens

        # 2. Check if model wants to call tools
        if response.has_tool_calls:
            # Append model's tool call intent to conversation history
            messages.append(
                ChatMessage(
                    role=Role.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # 3. Execute each tool call (supports parallel calls)
            for tc in response.tool_calls:
                result = await registry.execute(tc.name, tc.arguments, ctx)

                # 4. Append observation back into conversation history
                messages.append(
                    ChatMessage(
                        role=Role.TOOL,
                        name=tc.name,
                        tool_call_id=tc.id,
                        content=result.content,
                    )
                )
        else:
            # 5. Final answer reached
            messages.append(ChatMessage(role=Role.ASSISTANT, content=response.content))
            return {
                "status": "completed",
                "final_answer": response.content,
                "steps_taken": steps_taken,
                "total_tokens": total_tokens,
                "messages": messages,
            }

    # If step limit was reached without final answer
    return {
        "status": "budget_exceeded",
        "final_answer": "Failed: Exceeded maximum allowed step budget.",
        "steps_taken": steps_taken,
        "total_tokens": total_tokens,
        "messages": messages,
    }


async def main():
    print("--- Running Deterministic Toy Agent Loop with FakeLLM ---")
    
    # Setup FakeLLM scripted multi-step resolution
    fake = FakeLLM()
    # Turn 1: Agent decides to search for Qdrant pricing
    fake.add_response(
        tool_calls=[ToolCall(id="c1", name="search_stub", arguments={"query": "Qdrant pricing"})],
        input_tokens=50,
        output_tokens=15,
    )
    # Turn 2: Agent reads that Qdrant costs $25/mo, decides to calculate annual cost (25 * 12)
    fake.add_response(
        tool_calls=[ToolCall(id="c2", name="calculator", arguments={"expression": "25 * 12"})],
        input_tokens=120,
        output_tokens=15,
    )
    # Turn 3: Agent reads calculation result (300) and produces final synthesized report
    fake.add_response(
        content="Qdrant managed standard node costs $25 per month, which totals $300 annually.",
        input_tokens=180,
        output_tokens=25,
    )

    task = "Find the monthly cost of Qdrant and calculate its annual cost."
    result = await run_toy_agent_loop(task, fake)

    print(f"Status: {result['status']}")
    print(f"Steps: {result['steps_taken']}")
    print(f"Total Tokens: {result['total_tokens']}")
    print(f"Answer: {result['final_answer']}")


if __name__ == "__main__":
    asyncio.run(main())
