"""SpecStage — runs constitution → specify → clarify → review sub-steps."""
from __future__ import annotations

from typing import Any

from orchestrator.stages.base import Stage


class SpecStage(Stage):
    """Spec stage: runs constitution → specify → clarify → review sub-steps
    in order, returning all artifacts.

    No skip logic — all four sub-steps always execute regardless of
    project size or any other condition.
    """

    async def _execute_steps(self) -> dict[str, Any]:
        """Execute spec sub-steps sequentially via corresponding agents.

        Returns:
            Artifacts dict with keys: constitution, spec, clarification, review.
        """
        agents = self.ctx.agents

        # 1. Constitution
        constitution_result = await agents.call_agent(
            prompt="Generate project constitution",
            agent_name="constitution-writer",
        )

        # 2. Specify
        spec_result = await agents.call_agent(
            prompt="Generate feature specification",
            agent_name="spec-writer",
        )

        # 3. Clarify
        clarify_result = await agents.call_agent(
            prompt="Clarify specification ambiguities",
            agent_name="clarifier",
        )

        # 4. Review (via review_pipeline, not agents)
        review_result = await self.ctx.review_pipeline.run_review()

        return {
            "constitution": constitution_result.text,
            "spec": spec_result.text,
            "clarification": clarify_result.text,
            "review": review_result,
        }
