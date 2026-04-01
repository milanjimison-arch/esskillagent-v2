"""Spec stage: constitution → specify → clarify → review.

This module defines the SpecStage concrete implementation of StageABC.
The spec stage guides an AI agent through four ordered sub-steps:
  1. constitution  — establish ground rules and constraints
  2. specify       — draft the functional specification
  3. clarify       — resolve ambiguities via dialogue
  4. review        — gate: approve the spec before advancing to plan

FR-004: Stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
"""

from __future__ import annotations

# Sub-step names for the spec stage, in execution order.
SPEC_SUB_STEPS: tuple[str, ...] = ("constitution", "specify", "clarify", "review")


class SpecStage:
    """Stub — implementation pending (RED phase)."""

    sub_steps: tuple[str, ...] = SPEC_SUB_STEPS

    def __init__(self) -> None:
        raise NotImplementedError("SpecStage is not yet implemented")
