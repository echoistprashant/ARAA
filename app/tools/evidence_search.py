from typing import Any
from pydantic import BaseModel, Field

from app.repositories.evidence_repo import EvidenceRepository
from app.tools.base import RiskLevel, ToolContext, ToolResult


class EvidenceSearchInput(BaseModel):
    query: str = Field(..., description="Semantic search query to retrieve past verified evidence and citations.")
    limit: int = Field(default=3, ge=1, le=10, description="Maximum number of evidence snippets to return.")


class EvidenceSearchTool:
    """Retrieves verified historical evidence items across prior research runs with tenant isolation."""

    def __init__(self, evidence_repo: EvidenceRepository | None = None):
        self.evidence_repo = evidence_repo or EvidenceRepository()

    @property
    def name(self) -> str:
        return "search_evidence"

    @property
    def description(self) -> str:
        return (
            "Searches previously collected, verified evidence snippets and citations across past runs. "
            "Use this to cross-reference previous findings before making duplicate external web requests."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ

    @property
    def args_schema(self) -> type[BaseModel]:
        return EvidenceSearchInput

    async def execute(self, args: Any, ctx: ToolContext) -> ToolResult:
        if isinstance(args, dict):
            validated = EvidenceSearchInput(**args)
        else:
            validated = args

        tenant_id = ctx.tenant_id if ctx else "default_tenant"

        results = await self.evidence_repo.search(
            query=validated.query,
            tenant_id=tenant_id,
            top_k=validated.limit,
        )

        if not results:
            return ToolResult(
                content="No historical evidence found matching this query in tenant repository.",
                status="succeeded",
                citations=[],
                trust_level="trusted",
            )

        formatted_lines = []
        citations = []
        for scored in results:
            ev = scored.evidence
            source = ev.source_url or ev.tool_name
            formatted_lines.append(
                f"[{ev.id}] (relevance: {scored.score:.2f}) from {source}:\n\"{ev.excerpt}\""
            )
            citations.append({
                "id": ev.id,
                "score": scored.score,
                "source": source,
                "excerpt": ev.excerpt,
            })

        output_text = "\n\n".join(formatted_lines)
        return ToolResult(
            content=output_text,
            status="succeeded",
            citations=citations,
            trust_level="trusted",
        )
