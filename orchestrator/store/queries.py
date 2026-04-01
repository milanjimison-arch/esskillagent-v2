"""CRUD query helpers for E+S Orchestrator v2.

FR-036: Upsert task records (INSERT OR REPLACE semantics).
FR-037: Evidence chain — store and retrieve evidence linked to pipeline stages.
FR-LVL: LVL audit logs — create and query orchestrator audit log entries.

All query functions return frozen dataclass types from models.py.

This is a minimal stub. All public functions raise NotImplementedError.
Tests in tests/unit/store/test_queries.py assert concrete return values —
they will fail (RED) until the full implementation is provided.

Design rules:
- All returned objects are frozen dataclasses (immutable).
- No bare except; explicit exception types only.
- Module < 400 lines.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from orchestrator.store.db import Store


# ---------------------------------------------------------------------------
# Frozen result types returned by query helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskRecord:
    """Frozen snapshot of a task row returned by query helpers.

    Fields
    ------
    task_id     : Unique task identifier.
    description : Human-readable task description.
    file_path   : Source file this task targets.
    parallel    : Whether the task may run in parallel.
    user_story  : Optional user story text linked to the task.
    requirements: Tuple of requirement strings (immutable).
    status      : Current lifecycle status string.
    group_name  : Logical group this task belongs to.
    created_at  : ISO-8601 creation timestamp string.
    updated_at  : ISO-8601 last-update timestamp string.
    """

    task_id: str
    description: str
    file_path: str
    parallel: bool
    status: str
    group_name: str
    created_at: str
    updated_at: str
    user_story: str | None = None
    requirements: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EvidenceRecord:
    """Frozen snapshot of an evidence row returned by query helpers.

    Fields
    ------
    evidence_id : Unique evidence identifier.
    pipeline_id : Foreign key to the pipeline that owns this evidence.
    stage       : Pipeline stage during which evidence was captured.
    task_id     : Optional task identifier associated with this evidence.
    event_type  : Category of the evidence event.
    detail      : Raw text detail of the evidence.
    created_at  : ISO-8601 timestamp string when the evidence was created.
    """

    evidence_id: str
    pipeline_id: str
    stage: str
    event_type: str
    detail: str
    created_at: str
    task_id: str | None = None


@dataclass(frozen=True)
class LvlLogRecord:
    """Frozen snapshot of an LVL audit log row.

    Fields
    ------
    id          : Auto-incremented row id.
    pipeline_id : Foreign key to the pipeline that generated this log.
    level       : Log level string (e.g. "INFO", "WARN", "ERROR").
    message     : Short log message.
    detail      : Optional extended detail text.
    created_at  : ISO-8601 timestamp string when the entry was written.
    """

    id: int
    pipeline_id: str
    level: str
    message: str
    created_at: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# Task query helpers
# ---------------------------------------------------------------------------


async def upsert_task_record(
    store: Store,
    task_id: str,
    description: str,
    file_path: str,
    parallel: bool,
    user_story: str | None,
    requirements: list[str],
    status: str,
    group_name: str,
) -> TaskRecord:
    """INSERT OR REPLACE a task row and return the persisted frozen record.

    FR-036: MUST use upsert (INSERT OR REPLACE) semantics so that mutable
    fields (file_path, status, group_name) are updated on re-insert.

    Returns
    -------
    TaskRecord
        Frozen dataclass reflecting the stored state.

    Raises
    ------
    ValueError
        If task_id or description is empty.
    """
    raise NotImplementedError


async def get_task_record(store: Store, task_id: str) -> TaskRecord | None:
    """Fetch a single task by task_id and return it as a frozen TaskRecord.

    Returns None when no task with the given id exists.

    Raises
    ------
    ValueError
        If task_id is empty.
    """
    raise NotImplementedError


async def list_task_records(store: Store) -> tuple[TaskRecord, ...]:
    """Fetch all task rows and return them as a frozen tuple of TaskRecords.

    Returns an empty tuple when no tasks are persisted.
    """
    raise NotImplementedError


async def update_task_status_record(
    store: Store, task_id: str, status: str
) -> TaskRecord:
    """Update a task's status field and return the updated frozen record.

    Raises
    ------
    ValueError
        If task_id or status is empty.
    KeyError
        If no task with task_id exists.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Evidence chain query helpers
# ---------------------------------------------------------------------------


async def insert_evidence_record(
    store: Store,
    evidence_id: str,
    pipeline_id: str,
    stage: str,
    task_id: str | None,
    event_type: str,
    detail: str,
) -> EvidenceRecord:
    """Insert an evidence row and return the persisted frozen record.

    FR-037: MUST append to the audit trail; existing rows MUST NOT be altered.

    Raises
    ------
    ValueError
        If evidence_id, pipeline_id, stage, or event_type is empty.
    """
    raise NotImplementedError


async def list_evidence_records(
    store: Store, pipeline_id: str
) -> tuple[EvidenceRecord, ...]:
    """Fetch all evidence rows for a pipeline and return a frozen tuple.

    Returns an empty tuple when no evidence exists for the pipeline.

    Raises
    ------
    ValueError
        If pipeline_id is empty.
    """
    raise NotImplementedError


async def list_evidence_records_for_stage(
    store: Store, pipeline_id: str, stage: str
) -> tuple[EvidenceRecord, ...]:
    """Fetch evidence rows filtered by pipeline and stage.

    Returns an empty tuple when no evidence matches the criteria.

    Raises
    ------
    ValueError
        If pipeline_id or stage is empty.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# LVL audit log query helpers
# ---------------------------------------------------------------------------


async def insert_lvl_log(
    store: Store,
    pipeline_id: str,
    level: str,
    message: str,
    detail: str | None = None,
) -> LvlLogRecord:
    """Append an LVL audit log entry and return the frozen record.

    The auto-incremented id is populated from the database after insertion.

    Raises
    ------
    ValueError
        If pipeline_id, level, or message is empty.
    """
    raise NotImplementedError


async def list_lvl_logs(
    store: Store, pipeline_id: str
) -> tuple[LvlLogRecord, ...]:
    """Fetch all LVL audit log entries for a pipeline, ordered by id ascending.

    Returns an empty tuple when no logs exist.

    Raises
    ------
    ValueError
        If pipeline_id is empty.
    """
    raise NotImplementedError


async def list_lvl_logs_by_level(
    store: Store, pipeline_id: str, level: str
) -> tuple[LvlLogRecord, ...]:
    """Fetch LVL audit log entries filtered by level for a pipeline.

    Returns an empty tuple when no matching entries exist.

    Raises
    ------
    ValueError
        If pipeline_id or level is empty.
    """
    raise NotImplementedError
