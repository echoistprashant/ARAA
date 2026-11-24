import asyncio
import logging
import random
import re
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

# Models to try in order when the primary is overloaded/busy or unavailable (used if GEMINI_FALLBACK_MODEL is unset).
FALLBACK_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]

# HTTP status codes that warrant retry with exponential backoff & jitter.
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class GeminiProvider:
    """Wire-level adapter for Google Gemini models using native HTTP REST API.
    
    100% Free Tier compatible via Google AI Studio API Key.
    Implements the LLMClient protocol with exponential backoff, jitter, and fallback model support.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        max_attempts: int = 5,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.ACTOR_MODEL
        self.fallback_model = fallback_model or settings.GEMINI_FALLBACK_MODEL
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

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

        # Build ordered list of models to try: primary first, then fallback(s).
        configured_fallback = self.fallback_model or settings.GEMINI_FALLBACK_MODEL
        if configured_fallback:
            fallback_list = [configured_fallback] if configured_fallback != self.model else []
        else:
            # If unset, behavior stays as before (ordered pool of fallback models)
            fallback_list = [m for m in FALLBACK_MODELS if m != self.model]

        models_to_try = [self.model] + fallback_list

        last_resp: httpx.Response | None = None
        last_error_msg: str = "Unknown error"
        last_latency_ms: int = 0
        active_model: str = self.model
        resp: httpx.Response | None = None

        for model_idx, model in enumerate(models_to_try):
            is_fallback = model_idx > 0
            if is_fallback:
                logger.warning(
                    "Primary model exhausted or unavailable. Switching to fallback Gemini model: '%s'...",
                    model,
                )

            model_succeeded = False
            for attempt in range(1, self.max_attempts + 1):
                start_time = time.perf_counter()
                call_resp, latency_ms, exc = await self._call_model(model, payload, start_time)
                last_latency_ms = latency_ms

                if exc is not None:
                    last_error_msg = f"Network/timeout error for model '{model}': {exc}"
                    if attempt < self.max_attempts:
                        delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1))) + random.uniform(0.01, 0.1)
                        logger.warning(
                            "Gemini model '%s' network error on attempt %d/%d (%s). Retrying in %.2fs with backoff...",
                            model, attempt, self.max_attempts, exc, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            "Gemini model '%s' exhausted all %d attempts due to network error (%s).",
                            model, self.max_attempts, exc,
                        )
                        break

                if call_resp is not None and call_resp.status_code == 200:
                    resp = call_resp
                    active_model = model
                    model_succeeded = True
                    if is_fallback:
                        logger.info(
                            "Fallback Gemini model '%s' succeeded on attempt %d.",
                            model, attempt,
                        )
                    break

                status_code = call_resp.status_code if call_resp is not None else 0
                err_text = call_resp.text if call_resp is not None else ""
                last_resp = call_resp
                last_error_msg = f"HTTP {status_code} for model '{model}': {err_text[:200]}"

                # 404 indicates model endpoint does not exist on this version; don't retry, switch to fallback
                if status_code == 404:
                    logger.warning("Gemini model '%s' returned HTTP 404 (not found). Proceeding to fallback.", model)
                    break

                is_retryable = status_code in _RETRY_STATUSES or "unavailable" in err_text.lower() or "overloaded" in err_text.lower()

                if is_retryable:
                    if attempt < self.max_attempts:
                        delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1))) + random.uniform(0.01, 0.1)
                        logger.warning(
                            "Gemini model '%s' returned HTTP %d on attempt %d/%d (%s). Retrying in %.2fs with backoff...",
                            model, status_code, attempt, self.max_attempts, err_text[:120], delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            "Gemini model '%s' exhausted all %d attempts with HTTP %d.",
                            model, self.max_attempts, status_code,
                        )
                        break
                else:
                    # Non-retryable error (e.g. 400 Bad Request)
                    raise ToolExecutionError(
                        f"Gemini API returned HTTP {status_code} for model '{model}': {err_text}",
                        retryable=False,
                    )

            if model_succeeded and resp is not None:
                break
        else:
            # All models and retries exhausted
            raise ToolExecutionError(
                f"The AI research model is currently unavailable or experiencing high demand. "
                f"All retries and fallback models failed. Last error: {last_error_msg}",
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
