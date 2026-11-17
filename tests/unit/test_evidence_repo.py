import asyncio

from app.agents.state import EvidenceItem
from app.repositories.evidence_repo import EvidenceRepository


def test_evidence_repo_store_and_search():
    """Verifies storing evidence and semantic similarity search."""
    repo = EvidenceRepository()

    item1 = EvidenceItem(
        id="ev_quantum_1",
        tool_name="web_search",
        query="quantum supremacy sycamore",
        excerpt="Sycamore achieved quantum supremacy performing calculation in 200 seconds.",
        source_url="https://nature.com/articles/quantum",
    )
    item2 = EvidenceItem(
        id="ev_gardening_1",
        tool_name="web_search",
        query="tomato gardening tips",
        excerpt="Tomato plants require 6 to 8 hours of direct sunlight each day.",
        source_url="https://garden.org/tomatoes",
    )

    asyncio.run(repo.store_evidence(item1, tenant_id="tenant_1", run_id="run_100"))
    asyncio.run(repo.store_evidence(item2, tenant_id="tenant_1", run_id="run_100"))

    # Search for quantum
    results = asyncio.run(repo.search("quantum supremacy processor", tenant_id="tenant_1", top_k=2))
    assert len(results) >= 1
    assert results[0].evidence.id == "ev_quantum_1"
    assert results[0].score > 0.3

    # List by run
    items = asyncio.run(repo.list_by_run("run_100"))
    assert len(items) == 2


def test_evidence_repo_tenant_isolation():
    """Verifies that evidence from Tenant B is strictly hidden from Tenant A."""
    repo = EvidenceRepository()

    item_secret = EvidenceItem(
        id="ev_corp_secret",
        tool_name="rag_search",
        query="revenue forecast",
        excerpt="Projected revenue is 100M USD for Q4.",
    )
    asyncio.run(repo.store_evidence(item_secret, tenant_id="tenant_b"))

    # Tenant A searches with identical keywords
    results = asyncio.run(repo.search("revenue forecast Q4", tenant_id="tenant_a", top_k=5))
    assert len(results) == 0
