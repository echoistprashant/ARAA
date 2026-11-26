from app.agents.exporter import ReportExporter
from app.agents.state import EvidenceItem
from app.agents.synthesizer import ReportClaim, StructuredReport
from app.agents.verifier import VerificationResult


def test_report_exporter_to_markdown():
    """Verifies generating structured Markdown with numbered citations and sources table."""
    evidence = [
        EvidenceItem(
            id="ev_001",
            tool_name="web_search",
            query="ASML EUV",
            excerpt="High-NA EUV lithography tool costs 350M USD.",
            source_url="https://asml.com",
            trust_level="trusted",
        )
    ]

    report = StructuredReport(
        title="Lithography Market Report",
        executive_summary="Summary of high NA EUV deployment.",
        claims=[
            ReportClaim(
                text="ASML High-NA systems cost 350M USD.",
                evidence_ids=["ev_001"],
            ),
            ReportClaim(
                text="Competitors have equivalent machines ready.",
                evidence_ids=[],  # Unverified claim
            ),
        ],
        limitations=["Market volatility not modeled."],
        conclusion="Monopolistic advantage maintained.",
    )

    verification = VerificationResult(
        total_claims=2,
        grounded_claims_count=1,
        grounding_score=0.5,
        passed=False,
        unsupported_claims=["Competitors have equivalent machines ready."],
    )

    md = ReportExporter.to_markdown(report, verification, evidence)

    assert "# Lithography Market Report" in md
    assert "[!NOTE]" not in md
    assert "Audit Status:** UNVERIFIED" in md
    assert "Grounding Score:** 50%" in md
    assert "ASML High-NA systems cost 350M USD. [1]" in md
    assert "**[UNVERIFIED - No Citation]**" in md
    assert "References & Evidence Inventory" in md
    assert "| [1] | https://asml.com | `trusted` |" in md


def test_report_exporter_sanitizes_relative_anchors_and_injects_citations():
    """Verifies relative #cite_note anchors are stripped and inline [1] citations are injected."""
    evidence = [
        EvidenceItem(
            id="ev_001",
            tool_name="web_search",
            query="Sam Altman OpenAI",
            excerpt="Sam Altman is CEO of OpenAI [[1]](#cite_note-1) since 2019 [2](#cite_note-2).",
            source_url="https://en.wikipedia.org/wiki/Sam_Altman",
            trust_level="untrusted",
        )
    ]
    report = StructuredReport(
        title="OpenAI CEO",
        executive_summary="Sam Altman is CEO.",
        claims=[
            ReportClaim(
                text="Sam Altman is the Chief Executive Officer of OpenAI since 2019.",
                evidence_ids=["ev_001"],
            )
        ],
        limitations=[],
        conclusion="Sam Altman leads OpenAI.",
    )
    raw_report = (
        "# OpenAI CEO\n\n"
        "Sam Altman is the Chief Executive Officer of OpenAI and has led the organization since 2019."
    )

    md = ReportExporter.to_markdown(report, None, evidence, raw_final_report=raw_report)

    assert "#cite_note-1" not in md
    assert "#cite_note-2" not in md
    assert "[1]" in md
