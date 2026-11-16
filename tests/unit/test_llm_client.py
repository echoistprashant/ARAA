import asyncio
from app.llm.client import (
    ChatMessage,
    Role,
    ToolCall,
    ToolDefinition,
)
from app.llm.fake import FakeLLM
from app.llm.providers.gemini import GeminiProvider


def test_fake_llm_scripted_response():
    """Verifies that FakeLLM returns scripted text and tracks conversation messages."""
    fake = FakeLLM()
    fake.add_response(content="Hello research world!", input_tokens=15, output_tokens=5)

    messages = [ChatMessage(role=Role.USER, content="Start research")]
    response = asyncio.run(fake.generate(messages))

    assert response.content == "Hello research world!"
    assert response.has_tool_calls is False
    assert response.finish_reason == "stop"
    assert response.usage.total_tokens == 20
    assert fake.call_count == 1
    assert len(fake.history[0]) == 1
    assert fake.history[0][0].content == "Start research"


def test_fake_llm_tool_calls():
    """Verifies that FakeLLM can emit structured tool calls."""
    fake = FakeLLM()
    tool_call = ToolCall(id="call_1", name="calculator", arguments={"expression": "10 * 5"})
    fake.add_response(tool_calls=[tool_call])

    tool_def = ToolDefinition(
        name="calculator",
        description="Calculates arithmetic expressions",
        parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
    )

    messages = [ChatMessage(role=Role.USER, content="Calculate 10 * 5")]
    response = asyncio.run(fake.generate(messages, tools=[tool_def]))

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "calculator"
    assert response.tool_calls[0].arguments == {"expression": "10 * 5"}
    assert response.finish_reason == "tool_calls"


def test_gemini_message_conversion():
    """Verifies that GeminiProvider correctly converts ChatMessages to Gemini JSON format."""
    provider = GeminiProvider(api_key="test_key", model="gemini-2.0-flash")
    messages = [
        ChatMessage(role=Role.SYSTEM, content="You are a research agent."),
        ChatMessage(role=Role.USER, content="Find Qdrant pricing"),
        ChatMessage(
            role=Role.ASSISTANT,
            content=None,
            tool_calls=[ToolCall(id="call_1", name="web_search", arguments={"query": "Qdrant pricing"})],
        ),
        ChatMessage(role=Role.TOOL, name="web_search", content='{"pricing": "$25/mo"}'),
    ]

    system_instruction, contents = provider._convert_messages(messages)

    assert system_instruction == {"parts": [{"text": "You are a research agent."}]}
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert "functionCall" in contents[1]["parts"][0]
    assert contents[2]["role"] == "user"
    assert "functionResponse" in contents[2]["parts"][0]
