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


def test_verifier_catches_superseded_version_claim_cj_challenge():
    """CJ's Challenge Test: Verifies that citing an outdated/reversed document version
    as current reality is caught and rejected by the verifier, even if the link is 100% working
    and has high lexical overlap.
    """
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_policy_2018",
            tool_name="web_search",
            title="2018 Workplace Policy #401 (March 15, 2018)",
            excerpt="Policy 401 (March 15, 2018): All staff must be physically present in the office 5 days a week. Working from home is strictly forbidden.",
            trust_level="trusted",
        ),
        EvidenceItem(
            id="ev_policy_2023",
            tool_name="web_search",
            title="2023 Workplace Policy #802 (November 1, 2023)",
            excerpt="Policy 802 (November 1, 2023): This decision REVERSES and supersedes Policy 401. Full remote work is now authorized for all departments.",
            trust_level="trusted",
        ),
    ]

    # Bogus claim asserts that remote work is strictly forbidden today, citing the 2018 doc
    bogus_report = StructuredReport(
        title="Company Workplace Policy",
        executive_summary="Summary of work arrangements.",
        claims=[
            ReportClaim(
                text="Working from home is strictly forbidden today and staff must be physically present in the office 5 days a week.",
                evidence_ids=["ev_policy_2018"],
            )
        ],
        conclusion="Staff must report to the office.",
    )

    result = verifier.verify(bogus_report, evidence)
    assert result.passed is False
    assert result.grounding_score == 0.0
    assert len(result.unsupported_claims) == 1
    assert result.temporal_conflicts_count == 1
    assert result.claim_details[0].temporal_validity == "superseded_version"
    assert "Temporal violation" in result.warnings[0]
    assert "obsolete/superseded" in result.claim_details[0].notes


def test_verifier_accepts_valid_historical_and_current_claims():
    """Verifies that when a report accurately distinguishes historical context vs current
    status, both properly attributed claims pass verification.
    """
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_policy_2018",
            tool_name="web_search",
            title="2018 Workplace Policy #401",
            excerpt="Policy 401 (March 15, 2018): All staff must be physically present in the office 5 days a week. Working from home is strictly forbidden.",
            trust_level="trusted",
        ),
        EvidenceItem(
            id="ev_policy_2023",
            tool_name="web_search",
            title="2023 Workplace Policy #802",
            excerpt="Policy 802 (November 1, 2023): This decision REVERSES and supersedes Policy 401. Full remote work is now authorized for all departments.",
            trust_level="trusted",
        ),
    ]

    valid_report = StructuredReport(
        title="Workplace Policy Evolution",
        executive_summary="Analysis of company policy from 2018 to 2023.",
        claims=[
            ReportClaim(
                text="In 2018, Policy 401 established that all staff must be physically present in the office.",
                evidence_ids=["ev_policy_2018"],
            ),
            ReportClaim(
                text="Today, under Policy 802, full remote work is authorized across all departments.",
                evidence_ids=["ev_policy_2023"],
            ),
        ],
        conclusion="The company transitioned from strict office presence to full remote work.",
    )

    result = verifier.verify(valid_report, evidence)
    assert result.passed is True
    assert result.grounding_score == 1.0
    assert len(result.unsupported_claims) == 0
    assert result.temporal_conflicts_count == 0
    assert result.claim_details[0].temporal_validity == "valid"
    assert result.claim_details[1].temporal_validity == "valid"
