from app.tools.calculator import CalculatorTool
from app.tools.fetch_url import FetchUrlTool
from app.tools.rag_search import RAGSearchTool
from app.tools.registry import ToolRegistry
from app.tools.search_stub import SearchStubTool
from app.tools.web_search import WebSearchTool


def get_default_registry() -> ToolRegistry:
    """Returns a fully populated production ToolRegistry."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(SearchStubTool())
    registry.register(WebSearchTool())
    registry.register(FetchUrlTool())
    registry.register(RAGSearchTool())
    return registry


__all__ = [
    "CalculatorTool",
    "FetchUrlTool",
    "RAGSearchTool",
    "SearchStubTool",
    "ToolRegistry",
    "WebSearchTool",
    "get_default_registry",
]
