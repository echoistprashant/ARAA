import asyncio

from app.agents.memory import ContextCompressor
from app.llm.client import ChatMessage, Role, ToolCall


def test_context_compressor_threshold():
    """Checks compression threshold decision."""
    compressor = ContextCompressor(max_uncompressed_messages=5, keep_recent_messages=2)
    messages = [
        ChatMessage(role=Role.SYSTEM, content="System prompt"),
        ChatMessage(role=Role.USER, content="User task"),
        ChatMessage(role=Role.ASSISTANT, content="Thinking..."),
    ]
    assert compressor.should_compress(messages) is False

    messages.extend([
        ChatMessage(role=Role.TOOL, content="Result 1"),
        ChatMessage(role=Role.ASSISTANT, content="Thinking 2..."),
        ChatMessage(role=Role.TOOL, content="Result 2"),
    ])
    assert compressor.should_compress(messages) is True


def test_context_compressor_preserves_prefix_and_suffix():
    """Verifies that system instruction, initial user request, and recent turns are preserved."""
    compressor = ContextCompressor(max_uncompressed_messages=6, keep_recent_messages=2)

    messages = [
        ChatMessage(role=Role.SYSTEM, content="System Prompt Instructions"),
        ChatMessage(role=Role.USER, content="What is quantum supremacy?"),
        ChatMessage(
            role=Role.ASSISTANT,
            content=None,
            tool_calls=[ToolCall(id="1", name="search", arguments={"q": "quantum"})],
        ),
        ChatMessage(role=Role.TOOL, content="Quantum supremacy achieved in 2019 by Sycamore processor", name="search"),
        ChatMessage(role=Role.ASSISTANT, content="Analyzing results..."),
        ChatMessage(role=Role.ASSISTANT, content="Final summary upcoming..."),
        ChatMessage(role=Role.USER, content="Keep going"),
    ]

    compressed = asyncio.run(compressor.compress(messages))

    # Assertions
    assert len(compressed) < len(messages)
    # Prefix preserved
    assert compressed[0].role == Role.SYSTEM
    assert compressed[0].content == "System Prompt Instructions"
    assert compressed[1].role == Role.USER
    assert compressed[1].content == "What is quantum supremacy?"

    # Middle is compressed into memory block
    assert compressed[2].role == Role.SYSTEM
    assert "[CONSOLIDATED RESEARCH MEMORY" in compressed[2].content
    assert "Sycamore processor" in compressed[2].content

    # Suffix preserved
    assert compressed[-1].role == Role.USER
    assert compressed[-1].content == "Keep going"
