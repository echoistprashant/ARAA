from typing import TYPE_CHECKING
from app.tools.base import RiskLevel, Tool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.tools.calculator import CalculatorTool
    from app.tools.evidence_search import EvidenceSearchTool
    from app.tools.fetch_url import FetchUrlTool
    from app.tools.rag_search import RAGSearchTool
    from app.tools.sandbox import PythonSandboxTool
    from app.tools.search_stub import SearchStubTool
    from app.tools.web_search import WebSearchTool


def get_default_registry() -> ToolRegistry:
    """Returns a fully populated production ToolRegistry."""
    from app.tools.calculator import CalculatorTool
    from app.tools.evidence_search import EvidenceSearchTool
    from app.tools.fetch_url import FetchUrlTool
    from app.tools.rag_search import RAGSearchTool
    from app.tools.sandbox import PythonSandboxTool
    from app.tools.search_stub import SearchStubTool
    from app.tools.web_search import WebSearchTool

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(SearchStubTool())
    registry.register(WebSearchTool())
    registry.register(FetchUrlTool())
    registry.register(RAGSearchTool())
    registry.register(EvidenceSearchTool())
    registry.register(PythonSandboxTool())
    return registry


__all__ = [
    "RiskLevel",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "get_default_registry",
]
