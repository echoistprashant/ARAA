import json
import urllib.parse
from typing import Any
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.tools.base import RiskLevel, ToolContext, ToolError, ToolResult


class WebSearchInput(BaseModel):
    """Input parameters for internet web search."""
    query: str = Field(description="Search keywords to query across the web, e.g. 'vector database pricing comparison 2026'")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of search result snippets to retrieve")


class WebSearchTool:
    """Production zero-cost web search tool with multi-provider fallback.
    
    Defaults to DuckDuckGo (100% Free, no API key required) and supports Tavily Free Tier.
    All outputs are explicitly tagged as trust_level='untrusted'.
    """

    name = "web_search"
    description = (
        "Searches the public internet for fresh, real-time technical documentation, "
        "benchmarks, articles, and pricing. Returns excerpts with source URLs."
    )
    risk_level = RiskLevel.READ_EXTERNAL
    args_schema = WebSearchInput

    def __init__(self, search_provider: str | None = None, tavily_api_key: str | None = None):
        self.provider = search_provider or settings.SEARCH_PROVIDER
        self.tavily_key = tavily_api_key or settings.TAVILY_API_KEY

    async def _search_duckduckgo(self, query: str, max_results: int) -> tuple[str, list[dict[str, Any]]]:
        """Queries DuckDuckGo HTML endpoint without requiring API keys or dependencies."""
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            raise ToolError(f"DuckDuckGo search failed with HTTP {resp.status_code}", retryable=True)

        html = resp.text
        results: list[dict[str, Any]] = []

        # Lightweight parsing of DuckDuckGo results
        import re
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
        urls = re.findall(r'<a class="result__url[^>]*href="([^"]+)"', html)
        titles = re.findall(r'<a class="result__url[^>]*>(.*?)</a>', html)

        for i in range(min(len(snippets), max_results)):
            snippet_clean = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            raw_url = urls[i] if i < len(urls) else "https://duckduckgo.com"
            title = re.sub(r"<[^>]+>", "", titles[i]).strip() if i < len(titles) else "Search Result"

            # Parse out actual destination if wrapped in DDG redirect
            if "uddg=" in raw_url:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                dest_url = parsed.get("uddg", [raw_url])[0]
            else:
                dest_url = raw_url

            results.append({
                "title": title,
                "url": dest_url,
                "snippet": snippet_clean,
            })

        if not results:
            return f"No web search results found for '{query}'.", []

        formatted_lines = [f"Search Results for '{query}':"]
        citations = []
        for idx, r in enumerate(results, start=1):
            formatted_lines.append(f"[{idx}] {r['title']}\n    URL: {r['url']}\n    Snippet: {r['snippet']}")
            citations.append({
                "source_url": r["url"],
                "title": r["title"],
                "snippet": r["snippet"],
                "query": query,
            })

        return "\n\n".join(formatted_lines), citations

    async def _search_tavily(self, query: str, max_results: int) -> tuple[str, list[dict[str, Any]]]:
        """Queries Tavily AI Search API (Free tier: 1000 searches/mo)."""
        if not self.tavily_key:
            return await self._search_duckduckgo(query, max_results)

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)

        if resp.status_code != 200:
            raise ToolError(f"Tavily search API returned HTTP {resp.status_code}", retryable=True)

        data = resp.json()
        raw_results = data.get("results", [])

        formatted_lines = [f"Search Results for '{query}':"]
        citations = []
        for idx, r in enumerate(raw_results, start=1):
            title = r.get("title", "Untitled")
            source_url = r.get("url", "")
            snippet = r.get("content", "")
            formatted_lines.append(f"[{idx}] {title}\n    URL: {source_url}\n    Snippet: {snippet}")
            citations.append({
                "source_url": source_url,
                "title": title,
                "snippet": snippet,
                "query": query,
            })

        return "\n\n".join(formatted_lines), citations

    async def execute(self, args: WebSearchInput, ctx: ToolContext) -> ToolResult:
        """Executes the search and returns untrusted observation content with citations."""
        try:
            if self.provider == "tavily" and self.tavily_key:
                content, citations = await self._search_tavily(args.query, args.max_results)
            else:
                content, citations = await self._search_duckduckgo(args.query, args.max_results)

            return ToolResult(
                status="succeeded",
                content=content,
                citations=citations,
                trust_level="untrusted",
                cost_usd=0.0,  # Zero-Cost
            )
        except ToolError as te:
            return ToolResult(status="failed", content=f"Search failed: {te.message}")
        except Exception as e:
            return ToolResult(status="failed", content=f"Unexpected search error: {str(e)}")
