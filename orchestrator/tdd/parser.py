"""tasks.md parser — parses task lines in em-dash format.

Line format:
  {task_id} — [{tag}] {description}
  {task_id} — [{tag}] {description} — {file_path}

Where — is the em-dash character U+2014.
"""

from __future__ import annotations

import re

EM = "\u2014"
_TAG_PATTERN = re.compile(r"^\[([A-Z0-9]+)\]\s*(.*)")
_VALID_TAG = re.compile(r"^(S|P|US\d+)$")
_SEPARATOR = re.compile(r"\s+" + EM + r"\s+")


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
        self.task_id = task_id
        self.tag = tag
        self.description = description
        self.file_path = file_path


class TaskGroup:
    """Holds tasks grouped by category (setup / us / polish)."""

    def __init__(self) -> None:
        self.setup: list[Task] = []
        self.us: list[Task] = []
        self.polish: list[Task] = []


def parse_line(line: str) -> Task:
    """Parse a single task line and return a Task."""
    stripped = line.lstrip()

    if not stripped:
        raise TaskParseError("Empty or whitespace-only line")

    if EM not in stripped:
        raise TaskParseError(f"No em-dash separator found in line: {stripped!r}")

    # Split on whitespace-surrounded em-dash, max 2 splits -> 3 segments
    segments = _SEPARATOR.split(stripped, maxsplit=2)

    if len(segments) < 2:
        raise TaskParseError(f"Line missing required em-dash separator: {stripped!r}")

    # Parse task_id from first segment
    id_str = segments[0].strip()
    if not id_str.lstrip("-").isdigit():
        raise TaskParseError(f"Non-numeric task ID: {id_str!r}")
    task_id = int(id_str)
    if task_id <= 0:
        raise TaskParseError(f"Task ID must be positive integer, got: {task_id}")

    # Parse tag and description from second segment
    tag_desc = segments[1].strip()
    tag_match = _TAG_PATTERN.match(tag_desc)
    if not tag_match:
        raise TaskParseError(f"Missing or invalid [TAG] in segment: {tag_desc!r}")

    tag = tag_match.group(1)
    description = tag_match.group(2).strip()

    if not _VALID_TAG.match(tag):
        raise TaskParseError(f"Invalid tag: {tag!r}. Must be S, P, or US<digits>")

    # Check for mixed separators: hyphen used as separator inside the description
    if " - " in description:
        raise TaskParseError(
            f"Mixed separators detected (em-dash and hyphen) in: {stripped!r}"
        )

    # Parse optional file_path from third segment
    file_path: str | None = None
    if len(segments) == 3:
        file_path = segments[2].strip()

    # Require file_path for S and US* tags
    if tag != "P" and file_path is None:
        raise TaskParseError(
            f"Tag [{tag}] requires a file_path, but none was provided"
        )

    return Task(task_id=task_id, tag=tag, description=description, file_path=file_path)


def parse_tasks(content: str) -> list[Task]:
    """Parse the full content of a tasks.md file."""
    if not content:
        return []

    tasks: list[Task] = []
    seen_ids: set[int] = set()

    for raw_line in content.splitlines():
        stripped = raw_line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        task = parse_line(raw_line)

        if task.task_id in seen_ids:
            raise TaskParseError(f"Duplicate task_id: {task.task_id}")

        seen_ids.add(task.task_id)
        tasks.append(task)

    return sorted(tasks, key=lambda t: t.task_id)


def group_tasks(tasks: list[Task]) -> TaskGroup:
    """Group a list of Task objects into a TaskGroup."""
    group = TaskGroup()

    for task in tasks:
        if task.tag == "S":
            group.setup.append(task)
        elif task.tag == "P":
            group.polish.append(task)
        elif _VALID_TAG.match(task.tag) and task.tag.startswith("US"):
            group.us.append(task)
        else:
            raise TaskParseError(f"Unknown tag for grouping: {task.tag!r}")

    return group


def format_task_line(task: Task) -> str:
    """Serialize a Task back into the em-dash line format expected by parse_line.

    Format: ``{task_id} — [{tag}] {description}``
    or:     ``{task_id} — [{tag}] {description} — {file_path}``

    Raises:
        ValueError: if task_id <= 0, description is empty, or description
                    contains the em-dash separator sequence ' — '.
    """
    if task.task_id <= 0:
        raise ValueError(
            f"task_id must be a positive integer, got: {task.task_id}"
        )

    description = task.description.strip()

    if not description:
        raise ValueError("description must not be empty or whitespace-only")

    separator = f" {EM} "
    if separator in description:
        raise ValueError(
            f"description must not contain the em-dash separator {separator!r}, "
            f"got: {description!r}"
        )

    tag_segment = f"[{task.tag}] {description}"
    base = f"{task.task_id} {EM} {tag_segment}"

    if task.file_path is not None:
        return f"{base} {EM} {task.file_path}"

    return base
