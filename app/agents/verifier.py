from typing import Any
from pydantic import BaseModel, Field

from app.agents.state import EvidenceItem
from app.agents.synthesizer import ReportClaim, StructuredReport


class ClaimVerificationStatus(BaseModel):
    """Detailed verification record for an individual report claim."""
    claim_text: str
    is_grounded: bool
    evidence_ids: list[str]
    trust_level: str  # "trusted", "untrusted", or "missing"
    notes: str


class VerificationResult(BaseModel):
    """Holistic verification audit of a synthesized research report."""
    total_claims: int
    grounded_claims_count: int
    grounding_score: float  # 0.0 to 1.0
    passed: bool
    claim_details: list[ClaimVerificationStatus] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Verifier:
    """Rigorous factual verification engine checking claims against empirical evidence items.
    
    Prevents hallucination leaks and ungrounded statements from reaching the final report.
    """

    def __init__(self, min_grounding_score: float = 0.8):
        self.min_grounding_score = min_grounding_score

    def verify(
        self,
        report: StructuredReport,
        evidence: list[EvidenceItem],
    ) -> VerificationResult:
        """Audits every claim in the report against the verified evidence repository."""
        evidence_map = {ev.id: ev for ev in evidence}
        details: list[ClaimVerificationStatus] = []
        unsupported: list[str] = []
        warnings: list[str] = []

        grounded_count = 0

        for claim in report.claims:
            # 1. Check if evidence IDs exist
            valid_evs = [evidence_map[eid] for eid in claim.evidence_ids if eid in evidence_map]

            if not claim.evidence_ids or not valid_evs:
                # Completely ungrounded claim!
                details.append(
                    ClaimVerificationStatus(
                        claim_text=claim.text,
                        is_grounded=False,
                        evidence_ids=claim.evidence_ids,
                        trust_level="missing",
                        notes="No supporting empirical evidence found in run history.",
                    )
                )
                unsupported.append(claim.text)
                continue

            # 2. Check source trust levels
            untrusted_evs = [ev for ev in valid_evs if ev.trust_level == "untrusted"]
            if untrusted_evs:
                warnings.append(
                    f"Claim '{claim.text[:60]}...' is supported by {len(untrusted_evs)} untrusted source(s)."
                )

            # 3. Check token overlap / grounding heuristic
            claim_tokens = set(claim.text.lower().split())
            evidence_tokens = set()
            for ev in valid_evs:
                evidence_tokens.update(ev.excerpt.lower().split())

            overlap = claim_tokens.intersection(evidence_tokens)
            overlap_ratio = len(overlap) / max(1, len(claim_tokens))

            # If token overlap is reasonable, mark as grounded
            if overlap_ratio >= 0.2:
                grounded_count += 1
                details.append(
                    ClaimVerificationStatus(
                        claim_text=claim.text,
                        is_grounded=True,
                        evidence_ids=claim.evidence_ids,
                        trust_level="untrusted" if untrusted_evs else "trusted",
                        notes=f"Grounded with {len(valid_evs)} citation(s). Lexical overlap: {overlap_ratio:.0%}",
                    )
                )
            else:
                details.append(
                    ClaimVerificationStatus(
                        claim_text=claim.text,
                        is_grounded=False,
                        evidence_ids=claim.evidence_ids,
                        trust_level="missing",
                        notes=f"Cited evidence has insufficient factual overlap ({overlap_ratio:.0%}).",
                    )
                )
                unsupported.append(claim.text)

        total_claims = len(report.claims)
        grounding_score = (grounded_count / total_claims) if total_claims > 0 else 1.0
        passed = (grounding_score >= self.min_grounding_score) and (len(unsupported) == 0)

        return VerificationResult(
            total_claims=total_claims,
            grounded_claims_count=grounded_count,
            grounding_score=round(grounding_score, 2),
            passed=passed,
            claim_details=details,
            unsupported_claims=unsupported,
            warnings=warnings,
        )
