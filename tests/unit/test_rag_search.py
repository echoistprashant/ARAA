import asyncio

from app.tools import get_default_registry
from app.tools.base import ToolContext
from app.tools.rag_search import RAGSearchInput, RAGSearchTool


def test_rag_search_scoped_retrieval():
    """Verifies that RAGSearchTool returns relevant internal excerpts with citations."""
    tool = RAGSearchTool()
    ctx = ToolContext(run_id="run_rag_1", tenant_id="acme_corp")
    args = RAGSearchInput(query="vector database HNSW RAM sizing")

    result = asyncio.run(tool.execute(args, ctx))

    assert result.status == "succeeded"
    assert result.trust_level == "trusted"
    assert "Enterprise Infrastructure Standards" in result.content
    assert "minimum of 32GB RAM" in result.content
    assert "Tenant: acme_corp" in result.content
    assert len(result.citations) >= 1
    assert result.citations[0]["doc_title"] == "Enterprise Infrastructure Standards 2026"


def test_rag_search_no_results():
    """Verifies graceful response when no documents match the query."""
    tool = RAGSearchTool()
    ctx = ToolContext(run_id="run_rag_1", tenant_id="acme_corp")
    args = RAGSearchInput(query="unrelated non-existent query xyz123")

    result = asyncio.run(tool.execute(args, ctx))

    assert result.status == "succeeded"
    assert "No relevant passages found" in result.content


def test_default_registry_factory():
    """Verifies that get_default_registry populates all production tools."""
    registry = get_default_registry()
    tools = registry.list_tools()

    assert "calculator" in tools
    assert "search_stub" in tools
    assert "web_search" in tools
    assert "fetch_url" in tools
    assert "rag_search" in tools
    assert "search_evidence" in tools
    assert len(tools) == 6
