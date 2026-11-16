import ipaddress
import re
import socket
import urllib.parse
from typing import Any
import httpx
from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, ToolContext, ToolError, ToolResult


class FetchUrlInput(BaseModel):
    """Input parameters for retrieving and parsing webpage content."""
    url: str = Field(description="The full HTTP/HTTPS URL of the webpage or documentation to read")
    max_length_chars: int = Field(default=4000, ge=500, le=15000, description="Maximum characters of text to extract")


class FetchUrlTool:
    """Production URL fetcher tool with enterprise SSRF protection and HTML content cleaner.
    
    Protects against Server-Side Request Forgery by rejecting localhost, link-local,
    cloud metadata (169.254.169.254), and private RFC 1918 subnets.
    """

    name = "fetch_url"
    description = (
        "Fetches and reads the full text of an external webpage or documentation page. "
        "Automatically strips HTML boilerplate and returns readable text with source metadata."
    )
    risk_level = RiskLevel.READ_EXTERNAL
    args_schema = FetchUrlInput

    @staticmethod
    def _validate_ssrf(url_str: str) -> str:
        """Validates that the target URL does not resolve to private, loopback, or metadata networks."""
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme.lower() not in ("http", "https"):
            raise ToolError(f"Disallowed URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

        hostname = parsed.hostname
        if not hostname:
            raise ToolError("Invalid URL: hostname is missing.")

        # Disallow explicit localhost or metadata names
        if hostname.lower() in ("localhost", "metadata.google.internal"):
            raise ToolError("Access to localhost or internal cloud metadata is blocked (SSRF Protection).")

        # Resolve IP addresses
        try:
            addr_info = socket.getaddrinfo(hostname, None)
        except socket.gaierror as ge:
            raise ToolError(f"DNS resolution failed for host '{hostname}': {str(ge)}")

        for item in addr_info:
            ip_str = item[4][0]
            ip_obj = ipaddress.ip_address(ip_str)

            # Check if IP is private, loopback, link-local, or reserved
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_str.startswith("169.254.")  # AWS/GCP metadata address
            ):
                raise ToolError(
                    f"Access to private/local/metadata network address '{ip_str}' is blocked (SSRF Protection)."
                )

        return url_str

    @staticmethod
    def _clean_html(html: str) -> str:
        """Strips HTML tags, scripts, styles, and extracts readable body text."""
        # Remove script and style elements
        text = re.sub(r"<(script|style|nav|header|footer|noscript|svg)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Extract title if present
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if title:
            return f"Page Title: {title}\n\nContent:\n{text}"
        return text

    async def execute(self, args: FetchUrlInput, ctx: ToolContext) -> ToolResult:
        """Validates security, fetches URL, strips HTML, and bounds token payload."""
        try:
            self._validate_ssrf(args.url)

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(args.url, headers=headers)

            if resp.status_code != 200:
                return ToolResult(
                    status="failed",
                    content=f"HTTP request to '{args.url}' failed with status code {resp.status_code}.",
                )

            cleaned_text = self._clean_html(resp.text)
            truncated = len(cleaned_text) > args.max_length_chars
            final_content = cleaned_text[: args.max_length_chars]

            if truncated:
                final_content += f"\n\n[Content truncated to {args.max_length_chars} characters for context economy.]"

            return ToolResult(
                status="succeeded",
                content=final_content,
                citations=[{"source_url": args.url}],
                truncated=truncated,
                trust_level="untrusted",
                cost_usd=0.0,
            )

        except ToolError as te:
            return ToolResult(status="failed", content=f"Security/Fetch error: {te.message}")
        except Exception as e:
            return ToolResult(status="failed", content=f"Failed to fetch URL '{args.url}': {str(e)}")
