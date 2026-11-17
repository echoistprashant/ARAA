from typing import Any

from app.llm.client import ChatMessage, LLMClient, Role


class ContextCompressor:
    """Manages context window size across long research runs using rolling summaries.
    
    Guarantees:
    - Retains original system instructions and root user prompt.
    - Preserves uncompressed recent turn window (e.g. last 4 messages) for continuity.
    - Compresses intermediate turns into a structured research summary block.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        max_uncompressed_messages: int = 10,
        keep_recent_messages: int = 4,
    ):
        self.llm = llm
        self.max_uncompressed_messages = max_uncompressed_messages
        self.keep_recent_messages = keep_recent_messages
        self.current_summary: str = ""

    def should_compress(self, messages: list[ChatMessage]) -> bool:
        """Determines if the message history has exceeded the compression threshold."""
        return len(messages) > self.max_uncompressed_messages

    async def compress(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Compresses intermediate messages into a consolidated memory block."""
        if not self.should_compress(messages):
            return list(messages)

        # Invariant: preserve system instruction and first user request
        prefix_count = 2 if len(messages) >= 2 and messages[0].role == Role.SYSTEM else 1
        prefix = messages[:prefix_count]
        suffix = messages[-self.keep_recent_messages:]

        middle_start = prefix_count
        middle_end = len(messages) - self.keep_recent_messages

        if middle_start >= middle_end:
            return list(messages)

        middle_messages = messages[middle_start:middle_end]

        # Generate summary of middle messages
        extracted_facts: list[str] = []
        for msg in middle_messages:
            if msg.role == Role.TOOL:
                snippet = (msg.content or "")[:200].replace("\n", " ")
                extracted_facts.append(f"- Tool observation ({msg.name or 'unknown'}): {snippet}")
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                call_names = ", ".join(tc.name for tc in msg.tool_calls)
                extracted_facts.append(f"- Agent action proposed: {call_names}")
            elif msg.role == Role.ASSISTANT and msg.content:
                snippet = msg.content[:200].replace("\n", " ")
                extracted_facts.append(f"- Agent reasoning: {snippet}")

        incremental_summary = "\n".join(extracted_facts)
        if self.current_summary:
            self.current_summary = f"{self.current_summary}\n{incremental_summary}"
        else:
            self.current_summary = incremental_summary

        summary_message = ChatMessage(
            role=Role.SYSTEM,
            content=(
                "[CONSOLIDATED RESEARCH MEMORY - EARLIER TURNS COMPRESSED]\n"
                f"{self.current_summary}\n"
                "[END CONSOLIDATED MEMORY]"
            ),
        )

        return [*prefix, summary_message, *suffix]
