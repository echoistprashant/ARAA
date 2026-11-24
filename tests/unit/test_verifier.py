import pytest
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


def test_verifier_loper_bright_overruling_claim_passes():
    """Test a: A correct claim citing Loper Bright (2024) while evidence discusses
    Chevron being overruled -> passes verification, no temporal violation.
    """
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_wex_cornell",
            tool_name="web_search",
            title="Wex: Chevron Deference | Legal Information Institute",
            source_url="https://www.law.cornell.edu/wex/chevron_deference",
            excerpt="In Loper Bright Enterprises v. Raimondo (2024), the Supreme Court overruled Chevron U.S.A. v. Natural Resources Defense Council (1984), holding that courts must exercise independent judgment in statutory interpretation.",
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_loper_holding",
            tool_name="web_search",
            title="Loper Bright Enterprises v. Raimondo, 603 U.S. ___ (2024)",
            source_url="https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf",
            excerpt="The Supreme Court held that courts may not defer to an agency interpretation of the law simply because a statute is ambiguous, overruling Chevron.",
            trust_level="untrusted",
        ),
    ]

    report = StructuredReport(
        title="Current Judicial Deference Under US Federal Law",
        executive_summary="Analysis of judicial deference to federal agencies.",
        claims=[
            ReportClaim(
                text="Under US federal law, courts currently do not defer to federal agencies' interpretations of ambiguous statutes following Loper Bright Enterprises v. Raimondo (2024), which overruled Chevron.",
                evidence_ids=["ev_wex_cornell", "ev_loper_holding"],
            )
        ],
        conclusion="Chevron deference is no longer controlling precedent.",
    )

    result = verifier.verify(report, evidence)
    assert result.passed is True
    assert result.grounding_score == 1.0
    assert result.temporal_conflicts_count == 0
    assert len(result.unsupported_claims) == 0
    assert result.claim_details[0].temporal_validity == "valid"
    assert not any("Temporal violation" in w for w in result.warnings)


def test_verifier_chevron_as_current_law_flagged_as_temporal_violation():
    """Test b: A claim that states the Chevron deference rule as current law
    -> temporal violation flagged.
    """
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_chevron_1984",
            tool_name="web_search",
            title="Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837 (1984)",
            source_url="https://supreme.justia.com/cases/federal/us/467/837/",
            excerpt="In Chevron v. NRDC (1984), the Supreme Court established the doctrine of Chevron deference: if a statute is ambiguous, federal courts must defer to the agency's reasonable construction.",
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_loper_2024",
            tool_name="web_search",
            title="Loper Bright Enterprises v. Raimondo (2024)",
            source_url="https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf",
            excerpt="Loper Bright Enterprises v. Raimondo (2024): This decision explicitly overrules and supersedes Chevron v. NRDC (1984). Courts must not defer to agency interpretations.",
            trust_level="untrusted",
        ),
    ]

    report = StructuredReport(
        title="US Administrative Law Overview",
        executive_summary="Review of judicial deference principles.",
        claims=[
            ReportClaim(
                text="Under US federal law, courts currently defer to federal agencies' interpretations of ambiguous statutes under Chevron deference.",
                evidence_ids=["ev_chevron_1984"],
            )
        ],
        conclusion="Courts follow Chevron.",
    )

    result = verifier.verify(report, evidence)
    assert result.passed is False
    assert result.temporal_conflicts_count == 1
    assert len(result.unsupported_claims) == 1
    assert result.claim_details[0].temporal_validity == "superseded_version"
    assert any("Temporal violation" in w for w in result.warnings)


def test_verifier_historical_chevron_claim_passes():
    """Test c: A historical claim ('in 1990 the rule was Chevron') citing the 1984 decision
    -> passes.
    """
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_chevron_1984",
            tool_name="web_search",
            title="Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837 (1984)",
            source_url="https://supreme.justia.com/cases/federal/us/467/837/",
            excerpt="In Chevron v. NRDC (1984), the Supreme Court established the doctrine of Chevron deference: if a statute is ambiguous, federal courts must defer to the agency's reasonable construction.",
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_loper_2024",
            tool_name="web_search",
            title="Loper Bright Enterprises v. Raimondo (2024)",
            source_url="https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf",
            excerpt="In Loper Bright Enterprises v. Raimondo (2024), the Supreme Court overruled Chevron v. NRDC (1984).",
            trust_level="untrusted",
        ),
    ]

    report = StructuredReport(
        title="Historical Administrative Law in 1990",
        executive_summary="Analysis of legal rules in the 1990s.",
        claims=[
            ReportClaim(
                text="In 1990, the rule on judicial deference was Chevron deference, established by Chevron v. NRDC in 1984, which required courts to defer to reasonable agency interpretations.",
                evidence_ids=["ev_chevron_1984"],
            )
        ],
        conclusion="Chevron governed administrative statutory interpretation in 1990.",
    )

    result = verifier.verify(report, evidence)
    assert result.passed is True
    assert result.grounding_score == 1.0
    assert result.temporal_conflicts_count == 0
    assert len(result.unsupported_claims) == 0
    assert result.claim_details[0].temporal_validity == "valid"


def test_verifier_q2_historical_mixed_evidence_regression():
    """Regression test mirroring live Q2 (1990 judicial deference) with mixed 1984-era
    and post-2024 overruling evidence. Historical claims in a 1990-framed report must not
    trigger a false-positive temporal violation.
    """
    verifier = Verifier()
    evidence = [
        EvidenceItem(
            id="ev_1_0_web_search",
            tool_name="web_search",
            title="Chevron v. Natural Resources Defense Council - Ballotpedia",
            source_url="https://ballotpedia.org/Chevron_v._Natural_Resources_Defense_Council",
            excerpt=(
                "Supreme Court of the United States Chevron U.S.A. v. Natural Resources Defense Council "
                "is a case that was decided on June 25, 1984, by the United States Supreme Court. "
                "These principles are known as Chevron deference: if a statute is ambiguous, federal "
                "courts had to defer to the agency's reasonable construction."
            ),
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_1_1_web_search",
            tool_name="web_search",
            title="The Supreme Court Ends Chevron Deference—What Now?",
            source_url="https://www.nrdc.org/stories/what-happens-if-supreme-court-ends-chevron-deference",
            excerpt="Established in 1984 by Chevron v. NRDC. The case that overruled Chevron deference.",
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_1_2_web_search",
            tool_name="web_search",
            title="Supreme Court overturns Chevron decision: What to know",
            source_url="https://finance.yahoo.com/video/supreme-court-overturns-chevron-decision-205356621.html",
            excerpt=(
                "The United States Supreme Court upended a 40-year-old decision from the Chevron v. "
                "Natural Resources Defense Council case. Now that power is reverted back into the courts."
            ),
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_1_3_web_search",
            tool_name="web_search",
            title="Chevron U.S.A., Inc. v. NRDC, 467 U.S. 837 (1984)",
            source_url="https://supreme.justia.com/cases/federal/us/467/837",
            excerpt=(
                "A government agency must conform to any clear legislative statements, but courts will "
                "give the agency deference in ambiguous situations as long as its interpretation is reasonable."
            ),
            trust_level="untrusted",
        ),
        EvidenceItem(
            id="ev_1_4_web_search",
            tool_name="web_search",
            title="In the Wake of the Chevron Decision",
            source_url="https://environment.yale.edu/news/article/wake-chevron-decision",
            excerpt=(
                "In the 6-3 ruling issued in Loper Bright Enterprises v. Raimondo (2024), the justices "
                "overruled their landmark 1984 decision in Chevron v. Natural Resources Defense Council."
            ),
            trust_level="untrusted",
        ),
    ]

    report = StructuredReport(
        title="The Rule on Judicial Deference in 1990",
        executive_summary="By 1990, the governing legal standard for judicial deference was Chevron deference.",
        claims=[
            ReportClaim(
                text="In 1990 the governing rule was Chevron deference, established by Chevron v. NRDC, 467 U.S. 837, decided June 25, 1984.",
                evidence_ids=["ev_1_0_web_search"],
            ),
            ReportClaim(
                text="In 1990, these principles were known as Chevron deference, decided June 25, 1984.",
                evidence_ids=["ev_1_0_web_search"],
            ),
            ReportClaim(
                text="Under this two-step framework, courts gave the agency deference in ambiguous situations if its interpretation was reasonable.",
                evidence_ids=["ev_1_3_web_search"],
            ),
        ],
        conclusion="Chevron deference governed federal courts in 1990.",
    )

    result = verifier.verify(report, evidence)
    assert result.passed is True
    assert result.grounding_score == 1.0
    assert result.temporal_conflicts_count == 0
    assert not any("Temporal violation" in w for w in result.warnings)
