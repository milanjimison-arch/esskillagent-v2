"""ImplementStage — stub for TDD RED phase.

Do NOT implement logic here yet; tests must fail first.
The import declarations below establish the module-level names that tests
patch, without providing any implementation.
"""
from __future__ import annotations

from typing import Any

from orchestrator.stages.base import Stage
from orchestrator.tdd.runner import TaskRunner  # noqa: F401 — patch target for tests


class ImplementStage(Stage):
    """Implement stage: executes TDD tasks (serial/parallel), runs review pipeline,
    handles feature-gap supplementary tasks, and performs final push+CI verification.
    """

    async def _execute_steps(self) -> dict[str, Any]:
        raise NotImplementedError("not implemented")
