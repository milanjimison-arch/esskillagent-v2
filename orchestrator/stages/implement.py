"""Implement stage: TDD → review → push+CI.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

# Sub-step names for the implement stage, in execution order.
IMPLEMENT_SUB_STEPS: tuple[str, ...] = ("TDD", "review", "push+CI")


class ImplementStage:
    """Stub — implementation pending (RED phase)."""

    sub_steps: tuple[str, ...] = IMPLEMENT_SUB_STEPS

    def __init__(self) -> None:
        raise NotImplementedError("ImplementStage is not yet implemented")
