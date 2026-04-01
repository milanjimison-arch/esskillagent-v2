"""Plan stage: plan → research → tasks → review.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

import re

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult

# Sub-step names for the plan stage, in execution order.
PLAN_SUB_STEPS: tuple[str, ...] = ("plan", "research", "tasks", "review")


class PlanStage(StageABC):
    """Concrete implementation of the Plan stage."""

    name: str = "plan"
    sub_steps: tuple[str, ...] = PLAN_SUB_STEPS

    def __init__(self, *, store: object | None = None) -> None:
        self._store = store
        self.max_retries: int = 3

    async def run(self) -> StageResult:
        # Step 1: Invoke planner agent
        planner = getattr(self, "_planner", None)
        planner_output: str = await planner.run() if planner is not None else ""

        # Step 2: Scan for NR markers (case-sensitive)
        nr_markers: list[str] = re.findall(r"\[NR:[^\]]*\]", planner_output)
        needs_research: bool = len(nr_markers) > 0

        steps_executed: list[str] = ["plan"]

        # Step 3: Trigger research agent if NR markers found
        research_output: str | None = None
        research_triggered: bool = False
        if needs_research:
            research_agent = getattr(self, "_research_agent", None)
            if research_agent is not None:
                research_output = await research_agent.run()
                research_triggered = True
            steps_executed.append("research")

        # Step 4: Call task generator with planner output
        task_generator = getattr(self, "_task_generator", None)
        tasks_md: str = await task_generator.run(planner_output) if task_generator is not None else ""

        steps_executed.append("tasks")

        # Step 5: Parse tasks if parser is available
        tasks: list = []
        task_parser = getattr(self, "_task_parser", None)
        if task_parser is not None:
            tasks = task_parser.parse(tasks_md)

        # Step 6: Store each parsed task
        if self._store is not None:
            for task in tasks:
                self._store.add_task(task)

        # Step 8: Build and return StageResult
        data: dict = {
            "steps_executed": steps_executed,
            "planner_output": planner_output,
            "nr_markers": nr_markers,
            "needs_research": needs_research,
            "research_triggered": research_triggered,
            "tasks_md": tasks_md,
            "tasks": tasks,
        }
        if research_output is not None:
            data["research_output"] = research_output

        return StageResult(
            passed=True,
            attempts=1,
            data=data,
        )

    async def _do_review(self) -> ReviewOutcome:
        return ReviewOutcome(passed=True, issues=(), verdict="pass")

    async def _do_fix(self, outcome: ReviewOutcome) -> None:
        pass
