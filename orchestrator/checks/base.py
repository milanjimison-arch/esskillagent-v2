"""Abstract CheckStrategy interface for TDD test verification."""
from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator.store.models import CheckResult


class CheckStrategy(ABC):
    """Strategy interface for executing TDD test checks.

    FR-026: defines tests_must_fail (RED) and tests_must_pass (GREEN).
    """

    @abstractmethod
    async def tests_must_fail(
        self,
        cwd: str,
        task_id: str,
        file_path: str | None,
    ) -> CheckResult:
        """RED phase: run tests and verify that they fail.

        Returns CheckResult with success=True when tests fail as expected.
        """

    @abstractmethod
    async def tests_must_pass(
        self,
        cwd: str,
        task_id: str,
        file_path: str | None,
    ) -> CheckResult:
        """GREEN phase: run tests and verify that they all pass.

        Returns CheckResult with success=True when tests pass.
        """
