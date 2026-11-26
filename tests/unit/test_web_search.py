import asyncio
from unittest.mock import AsyncMock, patch
import httpx

from app.tools.base import ToolContext
from app.tools.web_search import WebSearchInput, WebSearchTool


def test_web_search_duckduckgo_success():
    """Verifies that WebSearchTool correctly parses DuckDuckGo HTML results."""
    mock_html = """
    <html>
        <body>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fqdrant.tech%2Fpricing">Qdrant Pricing</a>
                <a class="result__snippet">Managed nodes start at $25 per month.</a>
            </div>
        </body>
    </html>
    """
    mock_response = httpx.Response(
        status_code=200,
        text=mock_html,
        request=httpx.Request("GET", "https://html.duckduckgo.com/html/"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        tool = WebSearchTool(search_provider="duckduckgo")
        ctx = ToolContext(run_id="test_run")
        args = WebSearchInput(query="qdrant pricing", max_results=1)

        result = asyncio.run(tool.execute(args, ctx))

        assert result.status == "succeeded"
        assert result.trust_level == "untrusted"
        assert "$25 per month" in result.content
        assert len(result.citations) == 1
        assert result.citations[0]["source_url"] == "https://qdrant.tech/pricing"


def test_web_search_duckduckgo_http_error():
    """Verifies that search HTTP failures return structured error without crashing."""
    mock_response = httpx.Response(
        status_code=503,
        text="Service Unavailable",
        request=httpx.Request("GET", "https://html.duckduckgo.com/html/"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        tool = WebSearchTool(search_provider="duckduckgo")
        ctx = ToolContext(run_id="test_run")
        args = WebSearchInput(query="test query")

        result = asyncio.run(tool.execute(args, ctx))

        assert result.status == "failed"
        assert "Search failed" in result.content


def test_web_search_filters_irrelevant_personal_profiles():
    """Verifies that accidental personal profile URLs (e.g. linkedin.com/in/...)
    are filtered out from general web searches.
    """
    mock_html = """
    <html>
        <body>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fin%2Floper-tim-6bb6315">loper</a>
                <a class="result__snippet">Vice President at Carollo Engineers.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.scotusblog.com%2Fcase-files%2Floper-bright">Loper Bright</a>
                <a class="result__snippet">Supreme Court overruled Chevron deference in 2024.</a>
            </div>
        </body>
    </html>
    """
    mock_response = httpx.Response(
        status_code=200,
        text=mock_html,
        request=httpx.Request("GET", "https://html.duckduckgo.com/html/"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        tool = WebSearchTool(search_provider="duckduckgo")
        ctx = ToolContext(run_id="test_run")
        args = WebSearchInput(query="Loper Bright chevron deference", max_results=5)

        result = asyncio.run(tool.execute(args, ctx))

        assert result.status == "succeeded"
        assert len(result.citations) == 1
        assert result.citations[0]["source_url"] == "https://www.scotusblog.com/case-files/loper-bright"
        assert "linkedin.com/in/" not in result.content


def test_web_search_filters_social_media_domains():
    """Verifies that social media domains (facebook, linkedin posts/in, x, twitter, instagram, tiktok) are filtered out."""
    mock_html = """
    <html>
        <body>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fsolarquarter%2Fposts%2F123">FB</a>
                <a class="result__snippet">Facebook post.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fposts%2Fsomeone_solar-123">LI</a>
                <a class="result__snippet">LinkedIn post.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.com%2Fopenai%2Fstatus%2F123">X</a>
                <a class="result__snippet">X post.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftwitter.com%2Fopenai%2Fstatus%2F123">Twitter</a>
                <a class="result__snippet">Twitter post.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.instagram.com%2Fp%2Fabc">IG</a>
                <a class="result__snippet">Instagram post.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.tiktok.com%2F%40user%2Fvideo%2F123">TT</a>
                <a class="result__snippet">TikTok video.</a>
            </div>
            <div class="result">
                <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Firena.org%2Freport-2025">IRENA</a>
                <a class="result__snippet">Solar and wind cost report.</a>
            </div>
        </body>
    </html>
    """
    mock_response = httpx.Response(
        status_code=200,
        text=mock_html,
        request=httpx.Request("GET", "https://html.duckduckgo.com/html/"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        tool = WebSearchTool(search_provider="duckduckgo")
        ctx = ToolContext(run_id="test_run")
        args = WebSearchInput(query="solar and wind energy costs in India 2025", max_results=10)

        result = asyncio.run(tool.execute(args, ctx))

        assert result.status == "succeeded"
        assert len(result.citations) == 1
        assert result.citations[0]["source_url"] == "https://irena.org/report-2025"
