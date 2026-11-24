import asyncio
import logging
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

logger = logging.getLogger(__name__)

# Models to try in order when the primary is overloaded/busy or unavailable.
FALLBACK_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]

# HTTP status codes that indicate the model is unavailable or busy, warranting a fallback.
_FALLBACK_STATUSES = {404, 429, 500, 502, 503, 504}


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
                    if tc.raw_part:
                        parts.append(tc.raw_part)
                    else:
                        fc_dict: dict[str, Any] = {
                            "name": tc.name,
                            "args": tc.arguments,
                        }
                        if tc.id:
                            fc_dict["id"] = tc.id
                        part_dict: dict[str, Any] = {"functionCall": fc_dict}
                        if tc.thought_signature:
                            part_dict["thoughtSignature"] = tc.thought_signature
                        parts.append(part_dict)
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

    async def _call_model(
        self,
        model: str,
        payload: dict[str, Any],
        start_time: float,
    ) -> tuple[httpx.Response | None, int, Exception | None]:
        """Makes a single HTTP call to a specific Gemini model."""
        url = f"{self.BASE_URL}/{model}:generateContent?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(url, json=payload)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return resp, latency_ms, None
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return None, latency_ms, exc

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Invokes Gemini generateContent endpoint with native function calling.

        Automatically falls back to FALLBACK_MODELS in order if the primary
        model returns 429 (rate-limited), 503 (overloaded), times out, or encounters errors.
        """
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

        # Build ordered list of models to try: primary first, then fallbacks.
        models_to_try = [self.model] + [
            m for m in FALLBACK_MODELS if m != self.model
        ]

        last_resp: httpx.Response | None = None
        last_error_msg: str = "Unknown error"
        last_latency_ms: int = 0
        active_model: str = self.model

        for attempt, model in enumerate(models_to_try):
            start_time = time.perf_counter()
            resp, latency_ms, exc = await self._call_model(model, payload, start_time)

            if exc is not None:
                last_error_msg = f"Network/timeout error for model '{model}': {exc}"
                if attempt < len(models_to_try) - 1:
                    logger.warning(
                        "Gemini model '%s' failed with error (%s). Waiting 1.5s then trying fallback model '%s'…",
                        model,
                        exc,
                        models_to_try[attempt + 1],
                    )
                    await asyncio.sleep(1.5)
                    continue
                raise ToolExecutionError(last_error_msg, retryable=True)

            if resp is not None and resp.status_code == 200:
                active_model = model
                last_latency_ms = latency_ms
                if attempt > 0:
                    logger.warning(
                        "Gemini model fallback: '%s' was busy/unavailable, "
                        "successfully switched to '%s'.",
                        self.model,
                        model,
                    )
                break  # success — exit fallback loop

            status_code = resp.status_code if resp is not None else 0
            err_text = resp.text if resp is not None else ""
            last_resp = resp
            last_latency_ms = latency_ms
            last_error_msg = f"HTTP {status_code} for model '{model}': {err_text[:200]}"

            if status_code in _FALLBACK_STATUSES and attempt < len(models_to_try) - 1:
                backoff_s = 1.5 if status_code == 503 else 0.5
                logger.warning(
                    "Gemini model '%s' returned HTTP %d. Waiting %.1fs then retrying with fallback model '%s'…",
                    model,
                    status_code,
                    backoff_s,
                    models_to_try[attempt + 1],
                )
                await asyncio.sleep(backoff_s)
                continue  # try next model

            # Non-fallback error or exhausted fallbacks — raise.
            raise ToolExecutionError(
                f"Gemini API returned HTTP {status_code} for model '{model}': {err_text}",
                retryable=(status_code in [429, 500, 502, 503, 504]),
            )
        else:
            # All models exhausted — raise with last response info.
            raise ToolExecutionError(
                f"All Gemini models are currently busy or unavailable. Last error: {last_error_msg}",
                retryable=True,
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
                ts = part.get("thoughtSignature") or part.get("thought_signature") or fc.get("thought_signature")
                tool_calls.append(
                    ToolCall(
                        id=fc.get("id") or f"call_{idx}_{int(time.time())}",
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                        thought_signature=ts,
                        raw_part=part,
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
            model=active_model,  # reflects whichever model actually responded
            latency_ms=last_latency_ms,
        )
