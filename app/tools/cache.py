import hashlib
import json
import time
from typing import Any

from app.tools.base import RiskLevel, ToolContext, ToolResult


class ToolCache:
    """Zero-cost TTL caching layer for deterministic, read-only tool executions.
    
    Guarantees:
    - Never caches write-actions or stateful side effects.
    - Generates canonical SHA-256 keys from normalized argument dictionaries.
    - Memory-bounded with automatic TTL expiration.
    """

    def __init__(self, default_ttl_seconds: float = 3600.0):
        self.default_ttl = default_ttl_seconds
        # In-memory storage for deterministic offline and zero-cost operation
        self._cache: dict[str, tuple[ToolResult, float]] = {}

    @staticmethod
    def generate_cache_key(tool_name: str, arguments: dict[str, Any]) -> str:
        """Computes an unambiguous, order-independent cache key."""
        canonical_args = json.dumps(arguments, sort_keys=True, default=str)
        arg_hash = hashlib.sha256(canonical_args.encode("utf-8")).hexdigest()[:24]
        return f"cache:{tool_name}:{arg_hash}"

    def get(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult | None:
        """Retrieves cached ToolResult if present and not expired."""
        key = self.generate_cache_key(tool_name, arguments)
        entry = self._cache.get(key)
        if not entry:
            return None

        result, expires_at = entry
        if time.time() > expires_at:
            del self._cache[key]
            return None

        return result

    def set(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        risk_level: RiskLevel,
        ttl_seconds: float | None = None,
    ) -> bool:
        """Caches a successful ToolResult only if the tool is safe and read-only."""
        # Safety constraint: never cache side effects or write actions
        if risk_level not in (RiskLevel.READ, RiskLevel.READ_EXTERNAL):
            return False

        # Only cache successful executions
        if result.status != "succeeded":
            return False

        key = self.generate_cache_key(tool_name, arguments)
        ttl = ttl_seconds or self.default_ttl
        expires_at = time.time() + ttl
        self._cache[key] = (result, expires_at)
        return True

    def clear(self) -> None:
        """Purges all cached entries."""
        self._cache.clear()
