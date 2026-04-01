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

from dataclasses import dataclass, field
from typing import Any

from orchestrator.store.db import Store
from orchestrator.store._lvl_queries import (
    LvlLogRecord,
    insert_lvl_log,
    list_lvl_logs,
    list_lvl_logs_by_level,
)

__all__ = [
    "TaskRecord",
    "EvidenceRecord",
    "LvlLogRecord",
    "upsert_task_record",
    "get_task_record",
    "list_task_records",
    "update_task_status_record",
    "insert_evidence_record",
    "list_evidence_records",
    "list_evidence_records_for_stage",
    "insert_lvl_log",
    "list_lvl_logs",
    "list_lvl_logs_by_level",
]


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_task_record(row: dict) -> TaskRecord:
    reqs = row.get("requirements") or []
    return TaskRecord(
        task_id=row["task_id"],
        description=row["description"],
        file_path=row["file_path"],
        parallel=bool(row["parallel"]),
        status=row["status"],
        group_name=row["group_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        user_story=row.get("user_story"),
        requirements=tuple(reqs),
    )


def _row_to_evidence_record(row: dict) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row["evidence_id"],
        pipeline_id=row["pipeline_id"],
        stage=row["stage"],
        task_id=row.get("task_id"),
        event_type=row["event_type"],
        detail=row["detail"],
        created_at=row["created_at"],
    )


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
    if not task_id:
        raise ValueError("task_id must not be empty")
    if not description:
        raise ValueError("description must not be empty")
    await store.upsert_task(
        task_id=task_id,
        description=description,
        file_path=file_path,
        parallel=parallel,
        user_story=user_story,
        requirements=requirements,
        status=status,
        group_name=group_name,
    )
    row = await store.get_task(task_id)
    return _row_to_task_record(row)


async def get_task_record(store: Store, task_id: str) -> TaskRecord | None:
    """Fetch a single task by task_id and return it as a frozen TaskRecord.

    Returns None when no task with the given id exists.

    Raises
    ------
    ValueError
        If task_id is empty.
    """
    if not task_id:
        raise ValueError("task_id must not be empty")
    row = await store.get_task(task_id)
    if row is None:
        return None
    return _row_to_task_record(row)


async def list_task_records(store: Store) -> tuple[TaskRecord, ...]:
    """Fetch all task rows and return them as a frozen tuple of TaskRecords.

    Returns an empty tuple when no tasks are persisted.
    """
    rows = await store.list_tasks()
    return tuple(_row_to_task_record(row) for row in rows)


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
    if not task_id:
        raise ValueError("task_id must not be empty")
    if not status:
        raise ValueError("status must not be empty")
    existing = await store.get_task(task_id)
    if existing is None:
        raise KeyError(f"No task with task_id={task_id!r}")
    await store.update_task_status(task_id, status)
    row = await store.get_task(task_id)
    return _row_to_task_record(row)


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
    if not evidence_id:
        raise ValueError("evidence_id must not be empty")
    if not pipeline_id:
        raise ValueError("pipeline_id must not be empty")
    if not stage:
        raise ValueError("stage must not be empty")
    if not event_type:
        raise ValueError("event_type must not be empty")
    await store.insert_evidence(
        evidence_id=evidence_id,
        pipeline_id=pipeline_id,
        stage=stage,
        task_id=task_id,
        event_type=event_type,
        detail=detail,
    )
    async with store.execute(
        "SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_evidence_record(dict(row))


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
    if not pipeline_id:
        raise ValueError("pipeline_id must not be empty")
    rows = await store.list_evidence(pipeline_id)
    return tuple(_row_to_evidence_record(row) for row in rows)


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
    if not pipeline_id:
        raise ValueError("pipeline_id must not be empty")
    if not stage:
        raise ValueError("stage must not be empty")
    async with store.execute(
        "SELECT * FROM evidence WHERE pipeline_id = ? AND stage = ?",
        (pipeline_id, stage),
    ) as cur:
        rows = await cur.fetchall()
    return tuple(_row_to_evidence_record(dict(row)) for row in rows)


