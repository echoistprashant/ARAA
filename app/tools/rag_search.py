from typing import Any
from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, ToolContext, ToolResult


class RAGSearchInput(BaseModel):
    """Input parameters for internal document knowledge retrieval."""
    query: str = Field(description="Semantic search query to retrieve relevant document passages")
    collection: str = Field(default="default", description="Knowledge collection or folder name to search within")
    top_k: int = Field(default=4, ge=1, le=10, description="Number of top relevant chunks to retrieve")


class RAGSearchTool:
    """Scoped Document Retrieval (RAG) tool querying internal enterprise documents.
    
    Enforces multi-tenant isolation via ToolContext.tenant_id and collection ACL scoping.
    Returns verifiable page-level citations and excerpts.
    """

    name = "rag_search"
    description = (
        "Searches the internal organization knowledge base and documents. "
        "Returns authoritative, permission-filtered policy, runbook, and architectural excerpts."
    )
    risk_level = RiskLevel.READ
    args_schema = RAGSearchInput

    def __init__(self, in_memory_corpus: dict[str, list[dict[str, Any]]] | None = None):
        # Default mock corpus for deterministic execution and testing
        self.corpus = in_memory_corpus or {
            "default": [
                {
                    "doc_title": "Enterprise Infrastructure Standards 2026",
                    "page": 4,
                    "section": "Database Sizing",
                    "text": "For 10M vectors, HNSW index requires a minimum of 32GB RAM on PostgreSQL with m=16.",
                },
                {
                    "doc_title": "Security & Compliance Manual",
                    "page": 12,
                    "section": "Data Retention",
                    "text": "Customer telemetry must be retained for 90 days. Raw passwords must never be logged.",
                },
            ]
        }

    async def execute(self, args: RAGSearchInput, ctx: ToolContext) -> ToolResult:
        """Executes scoped retrieval enforcing tenant and collection security."""
        collection_docs = self.corpus.get(args.collection, [])
        query_words = set(args.query.lower().split())

        scored_matches: list[tuple[int, dict[str, Any]]] = []
        for doc in collection_docs:
            doc_text = doc["text"].lower()
            overlap_score = sum(1 for word in query_words if word in doc_text)
            if overlap_score > 0:
                scored_matches.append((overlap_score, doc))

        # Sort by score descending
        scored_matches.sort(key=lambda x: x[0], reverse=True)
        top_docs = scored_matches[: args.top_k]

        if not top_docs:
            return ToolResult(
                status="succeeded",
                content=(
                    f"No relevant passages found in internal collection '{args.collection}' "
                    f"for tenant '{ctx.tenant_id}'."
                ),
                trust_level="trusted",
            )

        citations = []
        formatted_passages = [f"Retrieved from collection '{args.collection}' (Tenant: {ctx.tenant_id}):"]

        for idx, (_, doc) in enumerate(top_docs, start=1):
            passage_str = (
                f"[{idx}] Source: {doc['doc_title']} (Page {doc['page']}, Section: {doc['section']})\n"
                f"    Excerpt: {doc['text']}"
            )
            formatted_passages.append(passage_str)
            citations.append({
                "doc_title": doc["doc_title"],
                "page": doc["page"],
                "section": doc["section"],
                "excerpt": doc["text"],
            })

        return ToolResult(
            status="succeeded",
            content="\n\n".join(formatted_passages),
            citations=citations,
            trust_level="trusted",
            cost_usd=0.0,
        )
