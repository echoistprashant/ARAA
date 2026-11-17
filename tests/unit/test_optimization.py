import asyncio
import time

from app.llm.client import ChatMessage, LLMResponse, Role
from app.llm.fake import FakeLLM
from app.llm.router import ModelRouter
from app.tools.base import RiskLevel, ToolResult
from app.tools.cache import ToolCache
from scripts.e2e_verify import run_full_system_verification


def test_tool_cache_safety_and_ttl():
    """Verifies that ToolCache caches read-only tools and ignores writes and expired entries."""
    cache = ToolCache(default_ttl_seconds=0.5)

    res = ToolResult(content="200 OK", status="succeeded")

    # 1. Read tool is cached
    cached = cache.set("web_search", {"q": "ai"}, res, RiskLevel.READ)
    assert cached is True
    assert cache.get("web_search", {"q": "ai"}) is not None

    # 2. Write tool is refused by safety constraint
    cached_write = cache.set("file_write", {"p": "a.txt"}, res, RiskLevel.WRITE)
    assert cached_write is False
    assert cache.get("file_write", {"p": "a.txt"}) is None

    # 3. TTL expiration
    time.sleep(0.6)
    assert cache.get("web_search", {"q": "ai"}) is None


def test_model_router_fallback():
    """Verifies model router failover to secondary client upon primary error."""
    class FailingLLM(FakeLLM):
        async def generate(self, messages, tools=None):
            raise RuntimeError("API Rate limit exceeded (HTTP 429)")

    primary = FailingLLM()
    fallback = FakeLLM(responses=[LLMResponse(content="Fallback success", tool_calls=[])])

    router = ModelRouter(primary_client=primary, fallback_client=fallback)
    res = asyncio.run(router.generate([ChatMessage(role=Role.USER, content="Hello")]))

    assert res.content == "Fallback success"
    assert router.fallback_triggers == 1


def test_e2e_system_verification_execution():
    """Executes the master end-to-end integration test exercising all 16 phases."""
    success = asyncio.run(run_full_system_verification())
    assert success is True
