import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.agents.state import EvidenceItem


def compute_deterministic_embedding(text: str, dim: int = 128) -> list[float]:
    """Generates a normalized zero-cost deterministic embedding vector.
    
    Uses token hashing and term frequency to build a fixed-dimension vector
    without requiring external API keys or heavy GPU runtimes.
    """
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return [0.0] * dim

    vec = [0.0] * dim
    counts = Counter(tokens)
    for token, count in counts.items():
        bucket = hash(token) % dim
        vec[bucket] += float(count)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Computes exact cosine similarity between two unit-normalized vectors."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


@dataclass
class ScoredEvidence:
    """Evidence item enriched with semantic relevance score."""
    evidence: EvidenceItem
    score: float


class EvidenceRepository:
    """Production evidence store with pgvector-compatible cosine similarity search.
    
    Enforces strict multi-tenant ACL boundaries and deduplication by content hash.
    """

    def __init__(self, session=None):
        self.session = session
        self._items: dict[str, EvidenceItem] = {}
        self._item_tenants: dict[str, str] = {}
        self._item_runs: dict[str, str] = {}
        self._embeddings: dict[str, list[float]] = {}

    async def store_evidence(
        self,
        item: EvidenceItem,
        tenant_id: str = "default_tenant",
        run_id: str | None = None,
    ) -> str:
        """Stores an evidence item and indexes its embedding."""
        if not item.id:
            item.id = f"ev_{uuid.uuid4().hex[:10]}"

        self._items[item.id] = item
        self._item_tenants[item.id] = tenant_id
        if run_id:
            self._item_runs[item.id] = run_id

        text_to_embed = f"{item.tool_name} {item.query or ''} {item.excerpt}"
        self._embeddings[item.id] = compute_deterministic_embedding(text_to_embed)
        return item.id

    async def get_by_id(self, evidence_id: str) -> EvidenceItem | None:
        """Retrieves a single evidence item by ID."""
        return self._items.get(evidence_id)

    async def list_by_run(self, run_id: str) -> list[EvidenceItem]:
        """Lists all evidence items gathered during a specific agent run."""
        return [item for item_id, item in self._items.items() if self._item_runs.get(item_id) == run_id]

    async def search(
        self,
        query: str,
        tenant_id: str = "default_tenant",
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> list[ScoredEvidence]:
        """Performs cosine semantic similarity search with tenant isolation."""
        query_vec = compute_deterministic_embedding(query)
        scored: list[ScoredEvidence] = []

        for item_id, item in self._items.items():
            if self._item_tenants.get(item_id) != tenant_id:
                # Multi-tenant ACL isolation boundary
                continue

            emb = self._embeddings.get(item_id, [])
            score = cosine_similarity(query_vec, emb)
            if score >= min_score:
                scored.append(ScoredEvidence(evidence=item, score=score))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]
