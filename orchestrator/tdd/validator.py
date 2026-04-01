"""Parallel task validator — implementation for TDD GREEN phase."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_parallel_safe: bool = False
    conflicts: list = field(default_factory=list)
    execution_mode: str = ""


def _get_file_path(task) -> str | None:
    """Extract file_path from a task object or dict."""
    if isinstance(task, dict):
        return task.get("file_path")
    return getattr(task, "file_path", None)


class ParallelTaskValidator:
    """Validates a list of tasks for parallel execution safety."""

    def detect_conflicts(self, tasks: list) -> list:
        """Return file_path strings that appear in 2+ tasks. None is ignored."""
        seen: set[str] = set()
        conflicts: set[str] = set()

        for task in tasks:
            path = _get_file_path(task)
            if path is None:
                continue
            if path in seen:
                conflicts.add(path)
            else:
                seen.add(path)

        return list(conflicts)

    def validate_tasks(self, tasks: list) -> ValidationResult:
        """Validate tasks and return a ValidationResult."""
        conflicts = self.detect_conflicts(tasks)
        is_safe = len(conflicts) == 0
        mode = "parallel" if is_safe else "serial"
        return ValidationResult(
            is_parallel_safe=is_safe,
            conflicts=conflicts,
            execution_mode=mode,
        )
