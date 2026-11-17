import asyncio
import json

from app.agents.state import EvidenceItem
from app.agents.synthesizer import Synthesizer
from app.llm.client import LLMResponse
from app.llm.fake import FakeLLM


def test_synthesizer_empty_evidence():
    """Verifies synthesis when no evidence was collected."""
    synthesizer = Synthesizer()
    report = asyncio.run(synthesizer.synthesize("Find life on Jupiter", []))

    assert "No empirical evidence" in report.executive_summary
    assert len(report.claims) == 0
    assert len(report.limitations) > 0


def test_synthesizer_deterministic_fallback():
    """Verifies deterministic synthesis linking evidence IDs to claims."""
    synthesizer = Synthesizer()
    evidence = [
        EvidenceItem(
            id="ev_101",
            tool_name="web_search",
            query="quantum supremacy",
            excerpt="Sycamore solved benchmark calculation in 200 seconds.",
        ),
        EvidenceItem(
            id="ev_102",
            tool_name="rag_search",
            query="supercomputer comparison",
            excerpt="Frontier supercomputer would take 10,000 years for same benchmark.",
        ),
    ]

    report = asyncio.run(synthesizer.synthesize("Evaluate Sycamore Quantum Advantage", evidence))
    assert len(report.claims) == 2
    assert report.claims[0].evidence_ids == ["ev_101"]
    assert report.claims[1].evidence_ids == ["ev_102"]


def test_synthesizer_with_llm():
    """Verifies synthesis using an LLM JSON response."""
    llm_payload = {
        "title": "Quantum Supremacy Analysis",
        "executive_summary": "Empirical evidence supports quantum advantage over classical supercomputers.",
        "claims": [
            {
                "text": "Sycamore processor achieved quantum supremacy in 2019.",
                "evidence_ids": ["ev_101"],
                "confidence": 0.98,
            }
        ],
        "limitations": ["Limited to sampling problems."],
        "conclusion": "Clear proof-of-concept demonstrated.",
    }
    llm = FakeLLM(responses=[LLMResponse(content=json.dumps(llm_payload), tool_calls=[])])
    synthesizer = Synthesizer(llm=llm)

    evidence = [
        EvidenceItem(
            id="ev_101",
            tool_name="web_search",
            query="quantum",
            excerpt="Sycamore achieved quantum supremacy.",
        )
    ]

    report = asyncio.run(synthesizer.synthesize("Quantum Advantage", evidence))
    assert report.title == "Quantum Supremacy Analysis"
    assert len(report.claims) == 1
    assert report.claims[0].evidence_ids == ["ev_101"]
    assert report.claims[0].confidence == 0.98
