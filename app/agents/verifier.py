import re
from typing import Any, Literal
from pydantic import BaseModel, Field

from app.agents.state import EvidenceItem
from app.agents.synthesizer import ReportClaim, StructuredReport

# Keywords signaling that an evidence document explicitly supersedes, reverses, or overrules an earlier decision/policy
REVERSAL_KEYWORDS = {
    "reverse", "reverses", "reversed", "reversing",
    "supersede", "supersedes", "superseded", "superseding",
    "overrule", "overrules", "overruled", "overruling",
    "overturn", "overturns", "overturned", "overturning",
    "repeal", "repeals", "repealed", "repealing",
    "replace", "replaces", "replaced", "replacing",
    "void", "voids", "voided", "voiding",
    "amend", "amends", "amended", "amending",
}

# Tokens indicating current / present validity assertion
CURRENT_TERMS = {
    "today", "now", "currently", "current", "presently", "at present",
    "present-day", "in effect", "effective today", "active rule", "active policy",
    "as of today", "applies today", "applies now", "as of now",
}

# Tokens indicating historical context assertion
HISTORICAL_TERMS = {
    "previously", "historically", "formerly", "former", "prior to",
    "earlier", "was established", "original", "originally",
    "under the old", "past rule", "past policy", "was the rule",
    "at the time", "back in", "initially",
}

# Terms indicating a claim states a decision/policy reversal, overruling, or cessation
REVERSAL_CLAIM_TERMS = {
    "overrule", "overrules", "overruled", "overruling",
    "reverse", "reverses", "reversed", "reversing",
    "supersede", "supersedes", "superseded", "superseding",
    "overturn", "overturns", "overturned", "overturning",
    "repeal", "repeals", "repealed", "repealing",
    "replace", "replaces", "replaced", "replacing",
    "no longer", "not defer", "does not defer", "do not defer",
    "no longer applies", "no longer defer", "no longer in effect",
    "ended", "ends", "ending", "struck down", "abandoned",
}

YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")


class ClaimVerificationStatus(BaseModel):
    """Detailed verification record for an individual report claim."""
    claim_text: str
    is_grounded: bool
    evidence_ids: list[str]
    trust_level: str  # "trusted", "untrusted", "missing", or "temporal_conflict"
    notes: str
    temporal_validity: Literal["valid", "superseded_version", "date_mismatch", "unspecified"] = "unspecified"


class VerificationResult(BaseModel):
    """Holistic verification audit of a synthesized research report."""
    total_claims: int
    grounded_claims_count: int
    grounding_score: float  # 0.0 to 1.0
    passed: bool
    claim_details: list[ClaimVerificationStatus] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    temporal_conflicts_count: int = 0


class Verifier:
    """Rigorous factual verification engine checking claims against empirical evidence items.
    
    Includes Temporal Lineage & Supersession Detection to ensure claims do not cite
    outdated, reversed, or overruled document versions as current reality.
    """

    def __init__(self, min_grounding_score: float = 0.8):
        self.min_grounding_score = min_grounding_score

    def _extract_years(self, text: str) -> set[int]:
        """Extracts 4-digit calendar years from text."""
        return {int(y) for y in YEAR_PATTERN.findall(text)}

    def _build_supersession_graph(self, evidence: list[EvidenceItem]) -> dict[str, str]:
        """Builds a mapping of superseded_evidence_id -> superseding_evidence_id.
        
        Detects if an evidence item explicitly reverses, supersedes, or overrules another.
        """
        superseded_map: dict[str, str] = {}
        
        reversal_items = []
        for ev in evidence:
            full_text = f"{getattr(ev, 'title', '') or ''} {ev.excerpt}".lower()
            if any(kw in full_text for kw in REVERSAL_KEYWORDS):
                reversal_items.append((ev, full_text))

        for rev_ev, rev_text in reversal_items:
            rev_years = self._extract_years(rev_text)
            max_rev_year = max(rev_years) if rev_years else 9999

            for other_ev in evidence:
                if other_ev.id == rev_ev.id:
                    continue
                
                other_text = f"{getattr(other_ev, 'title', '') or ''} {other_ev.excerpt}".lower()
                other_years = self._extract_years(other_text)
                max_other_year = max(other_years) if other_years else 0
                min_other_year = min(other_years) if other_years else 0

                # Check if other_ev itself discusses the reversal in a contemporary or newer year;
                # an evidence document reporting the reversal is NOT an obsolete/superseded document!
                other_has_reversal = any(kw in other_text for kw in REVERSAL_KEYWORDS)
                if other_has_reversal and max_other_year >= max_rev_year:
                    continue

                # Check if the reversal text explicitly references keywords/identifiers from the other doc
                other_tokens = set(re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", other_text))
                stopwords = {
                    "the", "and", "for", "with", "all", "must", "from", "this", "that",
                    "working", "rules", "policy", "court", "decision", "under", "case", "law",
                }
                meaningful_other_tokens = other_tokens - stopwords
                
                matches = [t for t in meaningful_other_tokens if t in rev_text]
                
                # Check for significant identifier overlap and older year or explicit supersession
                is_older = (max_other_year < max_rev_year) if (other_years and rev_years) else True
                if len(matches) >= 2 and is_older and not other_has_reversal:
                    superseded_map[other_ev.id] = rev_ev.id
                elif other_years and rev_years and max_other_year < max_rev_year and not other_has_reversal:
                    overlap_topic = len(set(rev_text.split()).intersection(set(other_text.split())))
                    if overlap_topic >= 5:
                        superseded_map[other_ev.id] = rev_ev.id

        return superseded_map

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

        # Build supersession/temporal precedence graph
        superseded_map = self._build_supersession_graph(evidence)

        grounded_count = 0
        temporal_conflicts_count = 0

        for claim in report.claims:
            claim_text_lower = claim.text.lower()

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
                        temporal_validity="unspecified",
                    )
                )
                unsupported.append(claim.text)
                continue

            # 2. Check source trust levels
            untrusted_evs = [ev for ev in valid_evs if ev.trust_level == "untrusted"]
            if untrusted_evs:
                warning_msg = "Claims incorporate findings from external untrusted source(s)."
                if warning_msg not in warnings:
                    warnings.append(warning_msg)

            # 3. Check token overlap / grounding heuristic
            claim_tokens = set(claim_text_lower.split())
            evidence_tokens = set()
            for ev in valid_evs:
                evidence_tokens.update(ev.excerpt.lower().split())

            overlap = claim_tokens.intersection(evidence_tokens)
            overlap_ratio = len(overlap) / max(1, len(claim_tokens))

            # If token overlap is insufficient, mark as ungrounded
            if overlap_ratio < 0.2:
                details.append(
                    ClaimVerificationStatus(
                        claim_text=claim.text,
                        is_grounded=False,
                        evidence_ids=claim.evidence_ids,
                        trust_level="missing",
                        notes=f"Cited evidence has insufficient factual overlap ({overlap_ratio:.0%}).",
                        temporal_validity="unspecified",
                    )
                )
                unsupported.append(claim.text)
                continue

            # 4. TEMPORAL ACCURACY & VERSION AUDIT (CJ's Challenge)
            claim_years = self._extract_years(claim.text)
            has_current_marker = any(term in claim_text_lower for term in CURRENT_TERMS)
            has_historical_marker = any(term in claim_text_lower for term in HISTORICAL_TERMS) or bool(claim_years)
            is_stating_reversal = any(term in claim_text_lower for term in REVERSAL_CLAIM_TERMS)

            # Check if any cited evidence is superseded
            superseded_citation = None
            for ev in valid_evs:
                if ev.id in superseded_map:
                    superseded_citation = (ev.id, superseded_map[ev.id])
                    break

            if superseded_citation:
                outdated_id, newer_id = superseded_citation
                outdated_ev = evidence_map[outdated_id]
                outdated_years = self._extract_years(f"{getattr(outdated_ev, 'title', '') or ''} {outdated_ev.excerpt}")

                # Check if the claim explicitly frames this as the historical / older period
                mentions_outdated_year = bool(claim_years and outdated_years and claim_years.intersection(outdated_years))
                is_valid_historical = mentions_outdated_year or (has_historical_marker and not has_current_marker)

                # A claim is flagged ONLY when it asserts the superseded rule as currently in force,
                # or cites the superseded document as authority for a current claim without stating the reversal.
                # A claim that correctly states the reversal/overruling MUST pass.
                if (has_current_marker or not is_valid_historical) and not is_stating_reversal:
                    temporal_conflicts_count += 1
                    err_msg = (
                        f"Temporal violation: Claim asserts current rule/status, but cites an obsolete/superseded "
                        f"version ({outdated_id}) that was reversed by newer evidence ({newer_id}). "
                        f"Working link alone is invalid for superseded version."
                    )
                    details.append(
                        ClaimVerificationStatus(
                            claim_text=claim.text,
                            is_grounded=False,
                            evidence_ids=claim.evidence_ids,
                            trust_level="temporal_conflict",
                            notes=err_msg,
                            temporal_validity="superseded_version",
                        )
                    )
                    unsupported.append(claim.text)
                    warn = f"Temporal violation: Claim drawn from outdated/reversed document version ({outdated_id})."
                    if warn not in warnings:
                        warnings.append(warn)
                    continue
                else:
                    # Valid historical attribution or claim accurately stating the reversal
                    grounded_count += 1
                    details.append(
                        ClaimVerificationStatus(
                            claim_text=claim.text,
                            is_grounded=True,
                            evidence_ids=claim.evidence_ids,
                            trust_level="untrusted" if untrusted_evs else "trusted",
                            notes=f"Grounded claim accurately citing evidence in proper temporal context. Lexical overlap: {overlap_ratio:.0%}",
                            temporal_validity="valid",
                        )
                    )
                    continue

            # 5. Check for Date Attribution Mismatch
            ev_years = set()
            for ev in valid_evs:
                ev_years.update(self._extract_years(f"{getattr(ev, 'title', '') or ''} {ev.excerpt}"))

            temporal_validity: Literal["valid", "superseded_version", "date_mismatch", "unspecified"] = "valid"
            if claim_years and ev_years and not claim_years.intersection(ev_years):
                temporal_validity = "date_mismatch"
                warn = f"Date attribution notice: Claim cites years {sorted(claim_years)} but cited evidence contains years {sorted(ev_years)}."
                if warn not in warnings:
                    warnings.append(warn)

            grounded_count += 1
            details.append(
                ClaimVerificationStatus(
                    claim_text=claim.text,
                    is_grounded=True,
                    evidence_ids=claim.evidence_ids,
                    trust_level="untrusted" if untrusted_evs else "trusted",
                    notes=f"Grounded with {len(valid_evs)} citation(s). Lexical overlap: {overlap_ratio:.0%}",
                    temporal_validity=temporal_validity,
                )
            )

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
            temporal_conflicts_count=temporal_conflicts_count,
        )
