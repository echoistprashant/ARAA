import json
from typing import Any
from pydantic import BaseModel, Field

from app.agents.state import PlanStep, RunPlan, RunState
from app.llm.client import ChatMessage, LLMClient, Role


class PlannerOutputSchema(BaseModel):
    """Pydantic contract for structured plan generation."""
    steps: list[PlanStep] = Field(
        min_length=1,
        max_length=8,
        description="Ordered sequence of 2 to 6 concrete, verifiable research sub-goals."
    )


class Planner:
    """Decomposes open-ended research tasks into checkable, sequential sub-goals.
    
    Prevents agent wandering and provides human-inspectable plan checkpoints.
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _build_planner_prompt(self, task: str, tools_summary: str) -> str:
        return (
            "You are an expert Research Planning AI.\n"
            "Decompose the following user research task into a clear, minimal, sequential plan "
            "(between 2 and 6 checkable steps).\n\n"
            f"AVAILABLE TOOLS:\n{tools_summary}\n\n"
            "PLANNING RULES:\n"
            "1. Each step must have a specific 'goal' and a clear 'success_check'.\n"
            "2. Keep steps focused: search first, calculate second, synthesize third.\n"
            "3. Output MUST be valid JSON adhering strictly to the schema:\n"
            '{"steps": [{"idx": 1, "goal": "...", "success_check": "..."}]}'
        )

    async def plan(
        self,
        task: str,
        tools_summary: str = "web_search, fetch_url, calculator, rag_search",
        max_steps: int = 6,
    ) -> RunPlan:
        """Invokes the model to generate a structured execution plan."""
        system_prompt = self._build_planner_prompt(task, tools_summary)
        messages = [
            ChatMessage(role=Role.SYSTEM, content=system_prompt),
            ChatMessage(role=Role.USER, content=f"Create a research plan for: {task}"),
        ]

        response = await self.llm.generate(messages=messages, temperature=0.0)
        content = response.content or ""

        # Parse JSON output from model
        try:
            # Handle potential markdown code block formatting
            clean_json = content
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()

            data = json.loads(clean_json)
            parsed = PlannerOutputSchema.model_validate(data)
            return RunPlan(steps=parsed.steps[:max_steps])

        except Exception:
            # Fallback heuristic plan if parsing fails
            return RunPlan(
                steps=[
                    PlanStep(idx=1, goal="Search and gather facts on topic", success_check="Relevant sources identified"),
                    PlanStep(idx=2, goal="Verify figures and calculate totals", success_check="Calculations verified"),
                    PlanStep(idx=3, goal="Synthesize final cited report", success_check="Comprehensive report produced"),
                ]
            )
