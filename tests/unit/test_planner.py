import asyncio

from app.agents.planner import Planner
from app.agents.state import PlanStep
from app.llm.fake import FakeLLM


def test_planner_structured_generation():
    """Verifies that Planner converts model output into a validated RunPlan."""
    fake_llm = FakeLLM()
    plan_json = """
    {
        "steps": [
            {"idx": 1, "goal": "Search Qdrant pricing", "success_check": "Pricing data acquired"},
            {"idx": 2, "goal": "Calculate annual costs via calculator", "success_check": "Math validated"},
            {"idx": 3, "goal": "Synthesize comparison report", "success_check": "Final report complete"}
        ]
    }
    """
    fake_llm.add_response(content=plan_json)

    planner = Planner(llm=fake_llm)
    plan = asyncio.run(planner.plan("Compare vector DB pricing"))

    assert len(plan.steps) == 3
    assert plan.steps[0].goal == "Search Qdrant pricing"
    assert plan.steps[1].success_check == "Math validated"
    assert plan.steps[2].status == "pending"


def test_planner_fallback_on_malformed_json():
    """Verifies that malformed model outputs fall back gracefully to standard plan."""
    fake_llm = FakeLLM()
    fake_llm.add_response(content="I am not returning valid JSON sorry")

    planner = Planner(llm=fake_llm)
    plan = asyncio.run(planner.plan("Any task"))

    assert len(plan.steps) >= 2
    assert plan.steps[0].goal.startswith("Search")
