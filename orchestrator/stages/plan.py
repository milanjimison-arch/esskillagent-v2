"""Plan stage: plan → research → tasks → review.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

# Sub-step names for the plan stage, in execution order.
PLAN_SUB_STEPS: tuple[str, ...] = ("plan", "research", "tasks", "review")


class PlanStage:
    """Stub — implementation pending (RED phase)."""

    sub_steps: tuple[str, ...] = PLAN_SUB_STEPS

    def __init__(self) -> None:
        raise NotImplementedError("PlanStage is not yet implemented")
