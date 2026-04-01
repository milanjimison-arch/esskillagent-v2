"""Parallel task validator — stub for TDD RED phase.

Real implementation is intentionally absent.  Every method raises
NotImplementedError so that tests fail with an AssertionError (or
NotImplementedError) rather than an ImportError.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_parallel_safe: bool = False
    conflicts: list = field(default_factory=list)
    execution_mode: str = ""


class ParallelTaskValidator:
    """Validates a list of tasks for parallel execution safety."""

    def validate_tasks(self, tasks: list) -> ValidationResult:
        raise NotImplementedError("not implemented")

    def detect_conflicts(self, tasks: list) -> list:
        raise NotImplementedError("not implemented")
