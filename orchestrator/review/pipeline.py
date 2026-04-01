"""ReviewPipeline — stub for TDD RED phase.

Only class/dataclass definitions are provided here. All methods raise
NotImplementedError so that the RED-phase tests fail on behavior, not on import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from orchestrator.store.models import Configuration, Review


@dataclass(frozen=True)
class ReviewResult:
    """Merged result from all reviewers."""

    verdict: str                        # "pass" / "fail"
    reviews: list[Review]
    supplementary_tasks: list[str] = field(default_factory=list)  # feature-gap tasks


class ReviewPipeline:
    """Orchestrates three-way parallel review with auto-fix cycle."""

    def __init__(self, agents: Any, store: Any, config: Configuration) -> None:
        self.agents = agents
        self.store = store
        self.config = config

    async def run_review(self, stage: str, artifacts: dict[str, Any]) -> ReviewResult:
        """Run parallel 3-way review, auto-fix on failure, detect feature gaps."""
        raise NotImplementedError("not implemented")
