import asyncio
from unittest.mock import AsyncMock, patch
import httpx

from app.tools.base import ToolContext
from app.tools.fetch_url import FetchUrlInput, FetchUrlTool


def test_fetch_url_ssrf_blocking_localhost():
    """Verifies that localhost / 127.0.0.1 is rejected by SSRF protection."""
    tool = FetchUrlTool()
    ctx = ToolContext(run_id="test_run")

    # 1. Test 127.0.0.1
    args = FetchUrlInput(url="http://127.0.0.1:8000/internal-data")
    result = asyncio.run(tool.execute(args, ctx))

    assert result.status == "failed"
    assert "SSRF Protection" in result.content

    # 2. Test metadata IP 169.254.169.254
    args_meta = FetchUrlInput(url="http://169.254.169.254/latest/meta-data")
    result_meta = asyncio.run(tool.execute(args_meta, ctx))

    assert result_meta.status == "failed"
    assert "SSRF Protection" in result_meta.content


def test_fetch_url_success_with_html_cleaning():
    """Verifies that valid HTML is fetched, scripts/styles stripped, and text normalized."""
    mock_html = """
    <html>
        <head><title>Qdrant Documentation</title></head>
        <style>.hide { display: none; }</style>
        <script>alert('xss');</script>
        <body>
            <nav>Menu Items</nav>
            <main>
                <h1>Architecture Overview</h1>
                <p>Qdrant is a vector search engine written in Rust.</p>
            </main>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """
    mock_response = httpx.Response(
        status_code=200,
        text=mock_html,
        request=httpx.Request("GET", "https://qdrant.tech/documentation"),
    )

    with patch.object(FetchUrlTool, "_validate_ssrf", return_value="https://qdrant.tech/documentation"):
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            tool = FetchUrlTool()
            ctx = ToolContext(run_id="test_run")
            args = FetchUrlInput(url="https://qdrant.tech/documentation")

            result = asyncio.run(tool.execute(args, ctx))

            assert result.status == "succeeded"
            assert result.trust_level == "untrusted"
            assert "Page Title: Qdrant Documentation" in result.content
            assert "vector search engine written in Rust" in result.content
            # Verify script, nav, and footer were stripped
            assert "alert('xss')" not in result.content
            assert "Menu Items" not in result.content
            assert "Copyright 2026" not in result.content


def test_fetch_url_truncation():
    """Verifies that pages exceeding max_length_chars are safely truncated."""
    long_text = "<html><body>" + ("Vector database analysis paragraph. " * 300) + "</body></html>"
    mock_response = httpx.Response(
        status_code=200,
        text=long_text,
        request=httpx.Request("GET", "https://example.com/long-page"),
    )

    with patch.object(FetchUrlTool, "_validate_ssrf", return_value="https://example.com/long-page"):
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            tool = FetchUrlTool()
            ctx = ToolContext(run_id="test_run")
            # Cap at 500 characters
            args = FetchUrlInput(url="https://example.com/long-page", max_length_chars=500)

            result = asyncio.run(tool.execute(args, ctx))

            assert result.status == "succeeded"
            assert result.truncated is True
            assert "Content truncated to 500 characters" in result.content
