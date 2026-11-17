from app.agents.state import EvidenceItem
from app.agents.synthesizer import StructuredReport
from app.agents.verifier import VerificationResult


class ReportExporter:
    """Formats structured research reports and verification audits into clean, citable Markdown."""

    @staticmethod
    def to_markdown(
        report: StructuredReport,
        verification: VerificationResult | None = None,
        evidence: list[EvidenceItem] | None = None,
        raw_final_report: str | None = None,
    ) -> str:
        """Converts structured report into GitHub Flavored Markdown with citations and bibliography."""
        evidence_map = {ev.id: ev for ev in (evidence or [])}
        citation_index: dict[str, int] = {}
        ordered_sources: list[EvidenceItem] = []

        def get_citation_num(ev_id: str) -> int:
            if ev_id not in citation_index:
                citation_index[ev_id] = len(citation_index) + 1
                if ev_id in evidence_map:
                    ordered_sources.append(evidence_map[ev_id])
            return citation_index[ev_id]

        if raw_final_report and len(raw_final_report.strip()) > 30:
            lines = [
                raw_final_report.strip(),
                "",
            ]
            if verification:
                status_badge = "VERIFIED" if verification.passed else "UNVERIFIED"
                lines.extend([
                    "---",
                    "## Empirical Verification & Grounding Audit",
                    "> [!NOTE]",
                    f"> **Audit Status:** {status_badge} | **Grounding Score:** {verification.grounding_score:.0%}",
                ])
                if verification.warnings:
                    for w in verification.warnings:
                        lines.append(f"> - *Notice:* {w}")
                lines.append("")
        else:
            lines = [
                f"# {report.title}\n",
                "## Executive Summary",
                report.executive_summary,
                "",
            ]

            # Audit Summary Badge
            if verification:
                status_badge = "VERIFIED" if verification.passed else "UNVERIFIED"
                lines.extend([
                    "> [!NOTE]",
                    f"> **Audit Status:** {status_badge} | **Grounding Score:** {verification.grounding_score:.0%}",
                ])
                if verification.warnings:
                    for w in verification.warnings:
                        lines.append(f"> - *Notice:* {w}")
                lines.append("")

            # Claims & Findings
            lines.append("## Key Findings & Empirical Claims")
            if not report.claims:
                lines.append("No empirical claims collected.")
            else:
                for idx, claim in enumerate(report.claims, start=1):
                    if claim.evidence_ids:
                        valid_ids = [eid for eid in claim.evidence_ids if eid in evidence_map]
                        if valid_ids:
                            cites = "".join(f"[{get_citation_num(eid)}]" for eid in valid_ids)
                            lines.append(f"{idx}. {claim.text} {cites}")
                        else:
                            lines.append(f"{idx}. {claim.text} **[UNVERIFIED - Missing Evidence]**")
                    else:
                        lines.append(f"{idx}. {claim.text} **[UNVERIFIED - No Citation]**")

            lines.append("")

            # Limitations
            if report.limitations:
                lines.append("## Limitations & Caveats")
                for lim in report.limitations:
                    lines.append(f"- {lim}")
                lines.append("")

            # Conclusion
            lines.append("## Conclusion")
            lines.append(report.conclusion)
            lines.append("")

        # Bibliography & Sources
        sources_to_render = ordered_sources if ordered_sources else (evidence or [])
        if sources_to_render:
            lines.extend([
                "---",
                "## References & Evidence Inventory",
                "| # | Source URL / Tool | Trust Level | Verified Excerpt |",
                "|---|---|---|---|",
            ])
            for idx, ev in enumerate(sources_to_render, start=1):
                num = citation_index.get(ev.id, idx)
                source_display = ev.source_url if ev.source_url else f"`{ev.tool_name}`"
                clean_excerpt = ev.excerpt[:150].replace("\n", " ").replace("|", "/")
                lines.append(f"| [{num}] | {source_display} | `{ev.trust_level}` | \"{clean_excerpt}\" |")
            lines.append("")

        return "\n".join(lines)
