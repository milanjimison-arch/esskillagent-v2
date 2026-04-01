"""tasks.md parser stub — implementation pending (RED phase).

All public symbols are defined as minimal stubs so that imports succeed.
No business logic is implemented here; tests MUST fail until GREEN phase.
"""

from __future__ import annotations


class TaskParseError(Exception):
    """Raised when a task line cannot be parsed."""
    pass


class Task:
    """Represents a single parsed task entry."""

    def __init__(
        self,
        task_id: int,
        tag: str,
        description: str,
        file_path: str | None = None,
    ) -> None:
        pass


class TaskGroup:
    """Holds tasks grouped by category (setup / us / polish)."""

    def __init__(self) -> None:
        pass


def parse_line(line: str) -> Task:
    """Parse a single task line and return a Task.

    Raises TaskParseError for malformed lines.
    """
    raise NotImplementedError("not implemented")


def parse_tasks(content: str) -> list[Task]:
    """Parse the full content of a tasks.md file.

    Returns tasks sorted by numeric ID.
    Raises TaskParseError for any malformed line.
    """
    raise NotImplementedError("not implemented")


def group_tasks(tasks: list[Task]) -> TaskGroup:
    """Group a list of Task objects into a TaskGroup.

    Returns a TaskGroup with .setup, .us, and .polish lists.
    """
    raise NotImplementedError("not implemented")
