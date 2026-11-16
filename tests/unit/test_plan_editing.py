from app.agents.state import (
    PlanStep,
    RunPlan,
    RunState,
    reduce_advance_subgoal,
    reduce_set_plan,
)


def test_plan_setting_and_advancing():
    """Verifies human plan updates and sequential sub-goal progress tracking."""
    state = RunState(run_id="run_p1", task="Research vector DBs")
    initial_plan = RunPlan(
        steps=[
            PlanStep(idx=1, goal="Step 1: Search", success_check="Sources found"),
            PlanStep(idx=2, goal="Step 2: Calculate", success_check="Math done"),
            PlanStep(idx=3, goal="Step 3: Synthesize", success_check="Report written"),
        ]
    )

    reduce_set_plan(state, initial_plan)
    assert state.plan is not None
    assert state.current_subgoal_idx == 0
    assert state.plan.steps[0].status == "in_progress"
    assert state.plan.steps[1].status == "pending"

    # Advance to step 2
    reduce_advance_subgoal(state)
    assert state.current_subgoal_idx == 1
    assert state.plan.steps[0].status == "completed"
    assert state.plan.steps[1].status == "in_progress"

    # Human user edits plan in-flight (adds a 4th step or changes existing goal)
    edited_plan = RunPlan(
        steps=[
            PlanStep(idx=1, goal="Step 1: Search", success_check="Sources found", status="completed"),
            PlanStep(idx=2, goal="Step 2: Modified Goal by Human", success_check="Human check"),
        ]
    )
    reduce_set_plan(state, edited_plan)
    assert state.plan.steps[0].goal == "Step 1: Search"
    assert state.plan.steps[1].goal == "Step 2: Modified Goal by Human"
