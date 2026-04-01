"""Acceptance stage: verification → traceability → review.

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

# Sub-step names for the acceptance stage, in execution order.
ACCEPTANCE_SUB_STEPS: tuple[str, ...] = ("verification", "traceability", "review")


class AcceptanceStage:
    """Stub — implementation pending (RED phase)."""

    sub_steps: tuple[str, ...] = ACCEPTANCE_SUB_STEPS

    def __init__(self) -> None:
        raise NotImplementedError("AcceptanceStage is not yet implemented")
