import re

from app.agents.state import EvidenceItem
from app.agents.synthesizer import StructuredReport
from app.agents.verifier import VerificationResult


class ReportExporter:
    """Formats structured research reports and verification audits into clean, citable Markdown."""

    @staticmethod
    def _sanitize_excerpt(text: str) -> str:
        """Removes relative anchor links (e.g. Wikipedia #cite_note-1) and normalizes whitespace."""
        cleaned = re.sub(r"\[\[\d+\]\]\(#[^)]*\)", "", text)
        cleaned = re.sub(r"\[\d+\]\(#[^)]*\)", "", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", cleaned)
        cleaned = re.sub(r"<a\b[^>]*href=[\"']#[^\"']*[\"'][^>]*>.*?</a>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _inject_inline_citations(
        raw_text: str,
        report: StructuredReport,
        evidence: list[EvidenceItem],
        get_citation_num,
    ) -> str:
        """Ensures inline [1], [2] citations appear in raw_final_report when missing."""
        if re.search(r"\[\d+\]", raw_text) or not evidence:
            return raw_text

        # Map each evidence item to its citation number and keywords
        ev_entries: list[tuple[int, set[str]]] = []
        for ev in evidence:
            num = get_citation_num(ev.id)
            words = {w for w in re.findall(r"[a-z0-9]{4,}", f"{ev.title or ''} {ev.excerpt}".lower())}
            ev_entries.append((num, words))

        # Also use synthesized claims' evidence_ids if available
        claim_cites: list[tuple[set[str], list[int]]] = []
        for claim in (report.claims or []):
            if claim.evidence_ids:
                c_words = {w for w in re.findall(r"[a-z0-9]{4,}", claim.text.lower())}
                nums = [get_citation_num(eid) for eid in claim.evidence_ids]
                if nums:
                    claim_cites.append((c_words, nums))

        out_lines: list[str] = []
        for line in raw_text.splitlines():
            stripped = line.strip()
            # Skip headings, empty lines, tables, horizontal rules, blockquotes, and code fences
            if (
                not stripped
                or stripped.startswith("#")
                or stripped.startswith("|")
                or stripped.startswith("---")
                or stripped.startswith(">")
                or stripped.startswith("```")
                or len(stripped) < 40
            ):
                out_lines.append(line)
                continue

            line_words = {w for w in re.findall(r"[a-z0-9]{4,}", stripped.lower())}
            best_nums: list[int] = []

            best_overlap = 0
            for c_words, nums in claim_cites:
                overlap = len(line_words & c_words)
                if overlap > best_overlap and overlap >= 2:
                    best_overlap = overlap
                    best_nums = nums

            if not best_nums:
                scored = [(len(line_words & e_words), num) for num, e_words in ev_entries]
                scored.sort(reverse=True)
                if scored and scored[0][0] >= 2:
                    best_nums = [scored[0][1]]

            if best_nums:
                cite_str = " ".join(f"[{n}]" for n in dict.fromkeys(best_nums))
                out_lines.append(f"{line} {cite_str}")
            else:
                out_lines.append(line)

        return "\n".join(out_lines)

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
            body_text = ReportExporter._inject_inline_citations(
                raw_final_report.strip(),
                report,
                evidence or [],
                get_citation_num,
            )
            lines = [
                body_text,
                "",
            ]
            if verification:
                status_badge = "VERIFIED" if verification.passed else "UNVERIFIED"
                lines.extend([
                    "---",
                    "## Empirical Verification & Grounding Audit",
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
                clean_excerpt = ReportExporter._sanitize_excerpt(ev.excerpt)[:150].replace("|", "/")
                lines.append(f"| [{num}] | {source_display} | `{ev.trust_level}` | \"{clean_excerpt}\" |")
            lines.append("")

        return "\n".join(lines)
