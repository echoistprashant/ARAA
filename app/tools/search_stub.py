from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, ToolContext, ToolResult


class SearchInput(BaseModel):
    """Input parameters for keyword/topic search."""
    query: str = Field(description="Search keywords to lookup facts, e.g. 'Qdrant pricing' or 'pgvector memory'")


class SearchStubTool:
    """Deterministic local search stub simulating search engine results without API keys.
    
    Returns factual research data with source URLs for testing multi-step agent flows.
    """

    name = "search_stub"
    description = (
        "Searches technical documentation and pricing for databases and technologies. "
        "Returns excerpts with source URLs."
    )
    risk_level = RiskLevel.READ_EXTERNAL
    args_schema = SearchInput

    # Deterministic knowledge base for testing and reproducible evaluation
    _CORPUS = {
        "qdrant": (
            "Qdrant Cloud Pricing: Managed cluster standard node costs $25 per month. "
            "Supports scalar quantization to reduce RAM by 4x. Storage engine written in Rust."
        ),
        "weaviate": (
            "Weaviate Cloud Pricing: Standard serverless compute costs $0.05 per 1,000 queries. "
            "Dedicated cluster starts at $85 per month with dynamic vector compression."
        ),
        "pgvector": (
            "PostgreSQL pgvector: Open-source extension, $0 license fee. "
            "For 10M 1536-dim vectors, HNSW index requires ~30GB RAM for fast search."
        ),
        "sizing": (
            "Vector memory rule of thumb: 1 million 768-dim float32 vectors require ~3GB raw RAM; "
            "HNSW index overhead adds another 1.5x-2x."
        ),
    }

    async def execute(self, args: SearchInput, ctx: ToolContext) -> ToolResult:
        query_lower = args.query.lower()

        matches = []
        for key, snippet in self._CORPUS.items():
            if key in query_lower:
                matches.append(snippet)

        if not matches:
            content = f"No direct search matches found for '{args.query}'. Try broader terms like 'Qdrant', 'Weaviate', or 'pgvector'."
            return ToolResult(
                status="succeeded",
                content=content,
                trust_level="untrusted",
            )

        combined = "\n\n".join(matches)
        return ToolResult(
            status="succeeded",
            content=f"Search Results for '{args.query}':\n{combined}",
            citations=[{"source_url": "https://docs.local/research", "query": args.query}],
            trust_level="untrusted",
        )
