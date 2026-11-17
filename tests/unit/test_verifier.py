from app.agents.state import EvidenceItem
from app.agents.synthesizer import ReportClaim, StructuredReport
from app.agents.verifier import Verifier


def test_verifier_all_grounded():
    """Verifies a fully grounded report passes verification with 1.0 score."""
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_1",
            tool_name="rag_search",
            query="ASML EUV price",
            excerpt="ASML High-NA EUV lithography system costs 350 million dollars.",
            trust_level="trusted",
        )
    ]
    report = StructuredReport(
        title="Lithography Report",
        executive_summary="ASML machinery pricing summary.",
        claims=[
            ReportClaim(
                text="The ASML High-NA EUV system costs approximately 350 million dollars.",
                evidence_ids=["ev_1"],
            )
        ],
        conclusion="High capital expenditure required.",
    )

    result = verifier.verify(report, evidence)
    assert result.passed is True
    assert result.grounding_score == 1.0
    assert len(result.unsupported_claims) == 0


def test_verifier_flags_hallucinated_evidence():
    """Verifies that referencing non-existent evidence IDs is caught and flagged."""
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_existing",
            tool_name="rag_search",
            query="test",
            excerpt="Some verified fact.",
        )
    ]
    report = StructuredReport(
        title="Hallucinated Report",
        executive_summary="Testing.",
        claims=[
            ReportClaim(
                text="Flying cars became common in 2022.",
                evidence_ids=["ev_non_existent"],  # Hallucinated ID
            )
        ],
        conclusion="Test conclusion.",
    )

    result = verifier.verify(report, evidence)
    assert result.passed is False
    assert result.grounding_score == 0.0
    assert "Flying cars became common in 2022." in result.unsupported_claims


def test_verifier_warns_on_untrusted_sources():
    """Verifies that citations from untrusted web scrape sources trigger audit warnings."""
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_untrusted",
            tool_name="web_search",
            query="random blog",
            excerpt="Bitcoin is projected to reach one million dollars soon.",
            trust_level="untrusted",
        )
    ]
    report = StructuredReport(
        title="Crypto Speculation",
        executive_summary="Bitcoin predictions.",
        claims=[
            ReportClaim(
                text="Bitcoin projected to reach one million dollars.",
                evidence_ids=["ev_untrusted"],
            )
        ],
        conclusion="High volatility expected.",
    )

    result = verifier.verify(report, evidence)
    assert result.grounding_score == 1.0
    assert len(result.warnings) > 0
    assert "untrusted source" in result.warnings[0]
