"""PlanStage — stub for TDD RED phase."""
from __future__ import annotations

from typing import Any

from orchestrator.stages.base import Stage


class PlanStage(Stage):
    """Executes the plan pipeline stage.

    Runs plan / research / tasks / review sub-steps and returns
    an artifacts dict.  Implementation is intentionally absent so that
    all RED-phase tests fail.
    """

    async def _execute_steps(self) -> dict[str, Any]:
        raise NotImplementedError("not implemented")
