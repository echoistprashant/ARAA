import json
from typing import Any
from pydantic import BaseModel, Field

from app.agents.state import EvidenceItem, RunPlan
from app.llm.client import ChatMessage, LLMClient, Role


class ReportClaim(BaseModel):
    """An individual assertion in the research report linked directly to supporting evidence."""
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class StructuredReport(BaseModel):
    """A verified, structured synthesis of research findings grounded in collected evidence."""
    title: str
    executive_summary: str
    claims: list[ReportClaim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conclusion: str


class Synthesizer:
    """Transforms raw evidence items and research observations into a structured, citable report."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm

    def _build_prompt(self, task: str, evidence: list[EvidenceItem]) -> str:
        evidence_snippets = []
        for ev in evidence:
            source = ev.source_url or ev.tool_name
            evidence_snippets.append(f"[{ev.id}] (Source: {source}): \"{ev.excerpt}\"")

        evidence_block = "\n".join(evidence_snippets) if evidence_snippets else "No empirical evidence collected."

        return (
            f"RESEARCH TASK: {task}\n\n"
            f"AVAILABLE EVIDENCE ITEMS:\n{evidence_block}\n\n"
            "INSTRUCTIONS:\n"
            "1. Synthesize a structured research report based ONLY on the evidence above.\n"
            "2. For every factual claim, you MUST attach the exact evidence_ids supporting it.\n"
            "3. TEMPORAL ACCURACY & VERSION ATTRIBUTION:\n"
            "   - When evidence contains older vs newer decisions, policies, or rulings (or where a document reverses or supersedes an earlier one), explicitly distinguish between historical rules vs what applies TODAY.\n"
            "   - When stating past rules, cite the historical document with its date.\n"
            "   - When stating current rules, cite the active superseding document with its date.\n"
            "   - Never present an outdated, reversed, or superseded version as current reality.\n"
            "4. Format your response strictly as valid JSON matching this schema:\n"
            "{\n"
            '  "title": "...",\n'
            '  "executive_summary": "...",\n'
            '  "claims": [{"text": "...", "evidence_ids": ["ev_1"], "confidence": 0.95}],\n'
            '  "limitations": ["..."],\n'
            '  "conclusion": "..."\n'
            "}"
        )

    async def synthesize(
        self,
        task: str,
        evidence: list[EvidenceItem],
        plan: RunPlan | None = None,
    ) -> StructuredReport:
        """Generates a structured report from the collected evidence."""
        if not evidence:
            return StructuredReport(
                title=f"Research Report: {task}",
                executive_summary="No empirical evidence was gathered to resolve this task.",
                claims=[],
                limitations=["Insufficient evidence retrieved during autonomous investigation."],
                conclusion="Inconclusive due to lack of verifiable data.",
            )

        if self.llm:
            prompt = self._build_prompt(task, evidence)
            messages = [
                ChatMessage(role=Role.SYSTEM, content="You are a strict, objective scientific report synthesizer."),
                ChatMessage(role=Role.USER, content=prompt),
            ]
            response = await self.llm.generate(messages=messages, tools=None)
            raw_text = response.content or "{}"
            try:
                # Strip markdown code blocks if model wrapped JSON
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                parsed = json.loads(raw_text)
                return StructuredReport.model_validate(parsed)
            except Exception:
                pass  # Fall through to deterministic synthesizer

        # Deterministic fallback synthesis
        claims = [
            ReportClaim(
                text=ev.excerpt[:250],
                evidence_ids=[ev.id],
                confidence=0.9 if ev.trust_level == "trusted" else 0.7,
            )
            for ev in evidence
        ]
        return StructuredReport(
            title=f"Autonomous Research Report: {task[:60]}",
            executive_summary=f"Synthesized analysis based on {len(evidence)} verified evidence sources.",
            claims=claims,
            limitations=["Report generated via deterministic baseline synthesizer."],
            conclusion=f"Successfully collected and verified {len(claims)} primary factual claims.",
        )
