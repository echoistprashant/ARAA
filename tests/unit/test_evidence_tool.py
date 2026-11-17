import asyncio

from app.agents.state import EvidenceItem
from app.repositories.evidence_repo import EvidenceRepository
from app.tools.base import RiskLevel, ToolContext
from app.tools.evidence_search import EvidenceSearchTool


def test_evidence_search_tool_execution():
    """Verifies that EvidenceSearchTool executes search and formats findings."""
    repo = EvidenceRepository()
    tool = EvidenceSearchTool(evidence_repo=repo)

    assert tool.name == "search_evidence"
    assert tool.risk_level == RiskLevel.READ

    # Seed evidence
    item = EvidenceItem(
        id="ev_semiconductor_1",
        tool_name="web_search",
        query="lithography EUV ASML",
        excerpt="High-NA EUV lithography machines cost over 350 million USD each.",
        source_url="https://asml.com/euv",
    )
    asyncio.run(repo.store_evidence(item, tenant_id="tenant_acme"))

    ctx = ToolContext(run_id="run_1", tenant_id="tenant_acme")
    result = asyncio.run(tool.execute({"query": "lithography machine price EUV", "limit": 2}, ctx=ctx))

    assert result.status == "succeeded"
    assert "ev_semiconductor_1" in result.content
    assert "350 million USD" in result.content
    assert len(result.citations) == 1


def test_evidence_search_tool_empty():
    """Verifies behavior when no matching evidence exists."""
    repo = EvidenceRepository()
    tool = EvidenceSearchTool(evidence_repo=repo)
    ctx = ToolContext(run_id="run_1", tenant_id="tenant_acme")

    result = asyncio.run(tool.execute({"query": "completely unrelated topic"}, ctx=ctx))
    assert result.status == "succeeded"
    assert "No historical evidence found" in result.content
    assert result.citations == []
