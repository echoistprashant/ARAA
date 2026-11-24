import asyncio
import json
import pytest
import httpx
from unittest.mock import patch

from app.core.errors import ToolExecutionError
from app.llm.client import ChatMessage, Role
from app.llm.providers.gemini import GeminiProvider
from app.api.v1.runs import _format_clean_error


def test_gemini_retry_503_then_success():
    """Test d.1: A mocked 503 followed by success returns a normal result."""
    provider = GeminiProvider(
        api_key="test_key",
        model="gemini-test-primary",
        fallback_model=None,
        max_attempts=3,
        base_delay=0.001,
        max_delay=0.01,
    )

    req = httpx.Request("POST", "https://test.url")
    resp_503 = httpx.Response(503, text=json.dumps({"error": {"code": 503, "status": "UNAVAILABLE", "message": "High demand"}}), request=req)
    resp_200 = httpx.Response(
        200,
        text=json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": "Normal synthesized result after 503 retry"}]
                }
            }],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20, "totalTokenCount": 70}
        }),
        request=req,
    )

    call_count = 0

    async def mock_call_model(model, payload, start_time):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resp_503, 10, None
        return resp_200, 10, None

    with patch.object(provider, "_call_model", side_effect=mock_call_model):
        messages = [ChatMessage(role=Role.USER, content="Explain judicial deference.")]
        res = asyncio.run(provider.generate(messages=messages))

    assert call_count == 2
    assert res.content == "Normal synthesized result after 503 retry"
    assert res.model == "gemini-test-primary"


def test_gemini_repeated_503_triggers_fallback_model():
    """Test d.2: Repeated 503 on primary triggers the fallback model."""
    provider = GeminiProvider(
        api_key="test_key",
        model="gemini-test-primary",
        fallback_model="gemini-test-fallback",
        max_attempts=3,
        base_delay=0.001,
        max_delay=0.01,
    )

    req = httpx.Request("POST", "https://test.url")
    resp_503 = httpx.Response(503, text=json.dumps({"error": {"code": 503, "status": "UNAVAILABLE", "message": "Model is busy"}}), request=req)
    resp_200_fallback = httpx.Response(
        200,
        text=json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": "Synthesized report from fallback model"}]
                }
            }],
            "usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 30, "totalTokenCount": 70}
        }),
        request=req,
    )

    models_called = []

    async def mock_call_model(model, payload, start_time):
        models_called.append(model)
        if model == "gemini-test-primary":
            return resp_503, 10, None
        return resp_200_fallback, 10, None

    with patch.object(provider, "_call_model", side_effect=mock_call_model):
        messages = [ChatMessage(role=Role.USER, content="Research task")]
        res = asyncio.run(provider.generate(messages=messages))

    assert models_called.count("gemini-test-primary") == 3
    assert "gemini-test-fallback" in models_called
    assert res.content == "Synthesized report from fallback model"
    assert res.model == "gemini-test-fallback"


def test_gemini_all_attempts_failing_returns_clean_failed_status():
    """Test d.3: All attempts failing raises a retryable ToolExecutionError and formats clean failed status."""
    provider = GeminiProvider(
        api_key="test_key",
        model="gemini-test-primary",
        fallback_model="gemini-test-fallback",
        max_attempts=2,
        base_delay=0.001,
        max_delay=0.01,
    )

    req = httpx.Request("POST", "https://test.url")
    resp_503 = httpx.Response(503, text=json.dumps({"error": {"code": 503, "status": "UNAVAILABLE", "message": "Model overloaded"}}), request=req)

    async def mock_call_model(model, payload, start_time):
        return resp_503, 10, None

    with patch.object(provider, "_call_model", side_effect=mock_call_model):
        messages = [ChatMessage(role=Role.USER, content="Research task")]
        with pytest.raises(ToolExecutionError) as exc_info:
            asyncio.run(provider.generate(messages=messages))

    err_text = str(exc_info.value)
    assert exc_info.value.retryable is True
    assert "unavailable" in err_text.lower() or "high demand" in err_text.lower()

    # Verify user-facing clean failed message formatting
    clean_msg = _format_clean_error(err_text)
    assert "The AI research model is temporarily experiencing high demand" in clean_msg
    assert "collected evidence has been preserved" in clean_msg.lower()
    assert "{" not in clean_msg and "}" not in clean_msg
