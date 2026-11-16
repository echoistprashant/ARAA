import asyncio

from app.agents.planner import Planner
from app.agents.state import PlanStep, RunPlan
from app.llm.fake import FakeLLM


def test_planner_replan_success():
    """Verifies that the replanner adapts remaining steps based on failure context."""
    fake_llm = FakeLLM()
    revised_json = """
    {
        "steps": [
            {"idx": 1, "goal": "Search alternative sources for pricing", "success_check": "Alternative found"},
            {"idx": 2, "goal": "Synthesize report with limitations note", "success_check": "Report finalized"}
        ]
    }
    """
    fake_llm.add_response(content=revised_json)

    planner = Planner(llm=fake_llm)
    current_plan = RunPlan(
        steps=[PlanStep(idx=1, goal="Fetch official site", success_check="Site fetched", status="failed")]
    )

    revised_plan = asyncio.run(
        planner.replan(
            task="Find vector DB pricing",
            current_plan=current_plan,
            failed_subgoal="Fetch official site",
            failure_reason="404 Not Found on pricing page",
            collected_evidence_count=0,
        )
    )

    assert len(revised_plan.steps) == 2
    assert "Search alternative sources" in revised_plan.steps[0].goal
    assert revised_plan.steps[1].success_check == "Report finalized"


def test_planner_replan_fallback():
    """Verifies that replanner falls back gracefully on model parse error."""
    fake_llm = FakeLLM()
    fake_llm.add_response(content="Not json")

    planner = Planner(llm=fake_llm)
    current_plan = RunPlan(steps=[])

    revised_plan = asyncio.run(
        planner.replan(
            task="Find pricing",
            current_plan=current_plan,
            failed_subgoal="Search pricing",
            failure_reason="Timeout",
            collected_evidence_count=0,
        )
    )

    assert len(revised_plan.steps) >= 1
    assert "alternative" in revised_plan.steps[0].goal.lower()
