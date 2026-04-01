"""CI-based check strategy stub.

FR-013: CICheckStrategy for CI-based test execution.
FR-015: Stack scoping — filter CI jobs to task's technology stack.
FR-016: Skipped/cancelled jobs must not be treated as passing.
FR-017: Per-job error logs capped at 2000 characters.
FR-018: CI job name matching uses startswith prefix matching.
FR-045: Extensible technology registry via config.
FR-046: File classification uses both extension and path prefix.
FR-047: CI job name mapping loaded from configuration.

This is a minimal stub to allow imports; all public methods raise
NotImplementedError to guarantee RED-phase test failures on assertions.
"""

from __future__ import annotations

from orchestrator.checks.base import CheckStrategy


class CICheckStrategy(CheckStrategy):
    """CI-based check strategy stub — not yet implemented."""

    def __init__(self, config: dict | None = None) -> None:
        raise NotImplementedError("CICheckStrategy.__init__ not implemented")

    def tests_must_fail(self, task_id: str, command: str) -> bool:
        raise NotImplementedError("CICheckStrategy.tests_must_fail not implemented")

    def tests_must_pass(self, task_id: str, command: str) -> bool:
        raise NotImplementedError("CICheckStrategy.tests_must_pass not implemented")

    def evaluate(self, ci_results: list[dict], stack: str | None = None) -> dict:
        raise NotImplementedError("CICheckStrategy.evaluate not implemented")
