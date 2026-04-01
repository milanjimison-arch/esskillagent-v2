"""LVL audit log query helpers for E+S Orchestrator v2.

Extracted from queries.py to keep module size under 400 lines.
All public symbols are re-exported from orchestrator.store.queries.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.store.db import Store, now


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


def _row_to_lvl_log_record(row: dict) -> LvlLogRecord:
    return LvlLogRecord(
        id=row["id"],
        pipeline_id=row["pipeline_id"],
        level=row["level"],
        message=row["message"],
        detail=row.get("detail"),
        created_at=row["created_at"],
    )


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
    if not pipeline_id:
        raise ValueError("pipeline_id must not be empty")
    if not level:
        raise ValueError("level must not be empty")
    if not message:
        raise ValueError("message must not be empty")
    timestamp = now()
    async with store.execute(
        """INSERT INTO lvl (pipeline_id, level, message, detail, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (pipeline_id, level, message, detail, timestamp),
    ) as cur:
        row_id = cur.lastrowid
    await store.commit()
    async with store.execute(
        "SELECT * FROM lvl WHERE id = ?", (row_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_lvl_log_record(dict(row))


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
    if not pipeline_id:
        raise ValueError("pipeline_id must not be empty")
    async with store.execute(
        "SELECT * FROM lvl WHERE pipeline_id = ? ORDER BY id ASC",
        (pipeline_id,),
    ) as cur:
        rows = await cur.fetchall()
    return tuple(_row_to_lvl_log_record(dict(row)) for row in rows)


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
    if not pipeline_id:
        raise ValueError("pipeline_id must not be empty")
    if not level:
        raise ValueError("level must not be empty")
    async with store.execute(
        "SELECT * FROM lvl WHERE pipeline_id = ? AND level = ? ORDER BY id ASC",
        (pipeline_id, level),
    ) as cur:
        rows = await cur.fetchall()
    return tuple(_row_to_lvl_log_record(dict(row)) for row in rows)
