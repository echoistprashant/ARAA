import time
from typing import Any
import httpx

from app.core.config import settings
from app.core.errors import ToolExecutionError
from app.llm.client import (
    ChatMessage,
    LLMResponse,
    Role,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


class GeminiProvider:
    """Wire-level adapter for Google Gemini models using native HTTP REST API.
    
    100% Free Tier compatible via Google AI Studio API Key.
    Implements the LLMClient protocol.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.ACTOR_MODEL

    def _convert_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Converts normalized ChatMessage objects into Gemini's contents format."""
        system_instruction = None
        contents: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.SYSTEM or msg.role == "system":
                # Gemini accepts system prompt via separate systemInstruction field
                system_instruction = {"parts": [{"text": msg.content or ""}]}
            elif msg.role == Role.USER or msg.role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg.content or ""}],
                })
            elif msg.role == Role.ASSISTANT or msg.role == "assistant":
                parts: list[dict[str, Any]] = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tc in msg.tool_calls:
                    parts.append({
                        "functionCall": {
                            "name": tc.name,
                            "args": tc.arguments,
                        }
                    })
                contents.append({"role": "model", "parts": parts})
            elif msg.role == Role.TOOL or msg.role == "tool":
                # Function response returned to model
                contents.append({
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": msg.name or "unknown_function",
                                "response": {"output": msg.content or ""},
                            }
                        }
                    ],
                })

        return system_instruction, contents

    def _convert_tools(
        self, tools: list[ToolDefinition] | None
    ) -> list[dict[str, Any]] | None:
        """Converts ToolDefinition schemas into Gemini functionDeclarations."""
        if not tools:
            return None

        declarations = []
        for t in tools:
            declarations.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            })

        return [{"functionDeclarations": declarations}]

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Invokes Gemini generateContent endpoint with native function calling."""
        if not self.api_key:
            raise ToolExecutionError(
                "GEMINI_API_KEY is not configured. Set it in .env or provide it directly."
            )

        system_instruction, contents = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        if system_instruction:
            payload["systemInstruction"] = system_instruction

        if gemini_tools:
            payload["tools"] = gemini_tools

        url = f"{self.BASE_URL}/{self.model}:generateContent?key={self.api_key}"

        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        if resp.status_code != 200:
            raise ToolExecutionError(
                f"Gemini API returned HTTP {resp.status_code}: {resp.text}",
                retryable=(resp.status_code in [429, 500, 503]),
            )

        data = resp.json()
        candidate = data.get("candidates", [{}])[0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])

        text_content = ""
        tool_calls: list[ToolCall] = []

        for idx, part in enumerate(parts):
            if "text" in part:
                text_content += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    ToolCall(
                        id=f"call_{idx}_{int(time.time())}",
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                    )
                )

        usage_meta = data.get("usageMetadata", {})
        usage = TokenUsage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
            cost_usd=0.0,  # Free Tier
        )

        finish_reason = "tool_calls" if tool_calls else "stop"

        return LLMResponse(
            content=text_content or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model,
            latency_ms=latency_ms,
        )
