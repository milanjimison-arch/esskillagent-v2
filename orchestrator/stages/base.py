"""Stage base class — template method pattern for all pipeline stages."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EngineContext:
    """Container for all dependencies injected into stages."""
    project_path: str
    config: Any
    store: Any
    agents: Any
    checker: Any
    review_pipeline: Any


class Stage(ABC):
    """Abstract base class for all pipeline stages.

    Subclasses implement _execute_steps; the run() template method
    orchestrates review, gate, and checkpoint around it.

    Lifecycle enforced by run():
        _execute_steps() -> _run_review() -> _check_gate() -> _save_checkpoint()
    """

    def __init__(self, ctx: EngineContext) -> None:
        self.ctx = ctx

    async def run(self) -> None:
        """Template method: execute_steps → review → gate → checkpoint."""
        artifacts = await self._execute_steps()
        review_result = await self._run_review(artifacts)
        gate_passed = await self._check_gate(review_result)
        await self._save_checkpoint(git_sha="")

    @abstractmethod
    async def _execute_steps(self) -> dict[str, Any]:
        """Execute stage-specific steps. Returns artifacts dict.

        Subclasses must override this method to provide stage logic.
        """

    async def _run_review(self, artifacts: dict[str, Any]) -> Any:
        """Run review pipeline against stage artifacts.

        Delegates to self.ctx.review_pipeline.run_review and returns
        the result directly.
        """
        return await self.ctx.review_pipeline.run_review(artifacts)

    async def _check_gate(self, review_result: Any) -> bool:
        """Return True if stage may proceed, False if it must retry/fail.

        Inspects the 'verdict' field of review_result: 'pass' -> True,
        anything else -> False.
        """
        if isinstance(review_result, dict):
            return review_result.get("verdict") == "pass"
        return bool(review_result)

    async def _save_checkpoint(self, git_sha: str) -> None:
        """Persist checkpoint to the store.

        Delegates to self.ctx.store.save_checkpoint with the given git SHA.
        """
        await self.ctx.store.save_checkpoint(git_sha)
