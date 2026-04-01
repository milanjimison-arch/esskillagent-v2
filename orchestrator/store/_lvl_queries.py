"""LVL audit log query helpers for E+S Orchestrator v2.

Extracted from queries.py to keep module size under 400 lines.
All public symbols are re-exported from orchestrator.store.queries.

Also contains LVL event chain operations (append_event, get_latest_event,
verify_chain, verify_stage_invariant) and artifact lifecycle operations
(register_artifact, freeze_artifact, check_staleness, cascade_invalidate).
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


# ---------------------------------------------------------------------------
# LVL Event Chain operations (stubs — raise NotImplementedError)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LvlEvent:
    """Frozen snapshot of an LVL event chain entry.

    Fields
    ------
    event_id    : Unique event identifier (UUID hex).
    pipeline_id : Foreign key to the owning pipeline.
    stage       : Pipeline stage that produced this event (e.g. "spec").
    event_type  : Event category (e.g. "stage_complete", "stage_start").
    payload     : Arbitrary JSON-serialisable dict stored as a string.
    prev_hash   : SHA-256 hex digest of the previous event (None for genesis).
    event_hash  : SHA-256 hex digest of this event's canonical content.
    created_at  : ISO-8601 UTC timestamp string.
    """

    event_id: str
    pipeline_id: str
    stage: str
    event_type: str
    payload: str
    prev_hash: str | None
    event_hash: str
    created_at: str


async def append_event(
    store: Store,
    pipeline_id: str,
    stage: str,
    event_type: str,
    payload: dict,
) -> LvlEvent:
    """Append a new event to the LVL chain and return the frozen record.

    Each event's hash is computed over (prev_hash, pipeline_id, stage,
    event_type, payload_json, created_at) so the chain is tamper-evident.

    Raises
    ------
    ValueError
        If pipeline_id, stage, or event_type is empty.
    """
    raise NotImplementedError("append_event is not yet implemented")


async def get_latest_event(
    store: Store,
    pipeline_id: str,
) -> LvlEvent | None:
    """Return the most recent LvlEvent for the pipeline, or None if empty.

    Raises
    ------
    ValueError
        If pipeline_id is empty.
    """
    raise NotImplementedError("get_latest_event is not yet implemented")


async def verify_chain(
    store: Store,
    pipeline_id: str,
) -> bool:
    """Verify the integrity of every event in the chain for this pipeline.

    Recomputes each event's hash and checks that it matches the stored
    event_hash, and that each event's prev_hash equals the previous
    event's event_hash.

    Returns True when the chain is intact, False when any link is broken.

    Raises
    ------
    ValueError
        If pipeline_id is empty.
    """
    raise NotImplementedError("verify_chain is not yet implemented")


def verify_stage_invariant(from_stage: str, to_stage: str) -> bool:
    """Return True iff the transition from_stage -> to_stage is valid.

    Valid order: spec -> plan -> implement -> acceptance.
    Any other ordering (e.g. skipping, reversing) returns False.

    Raises
    ------
    ValueError
        If from_stage or to_stage is not a recognised stage name.
    """
    raise NotImplementedError("verify_stage_invariant is not yet implemented")


# ---------------------------------------------------------------------------
# Artifact lifecycle operations (stubs — raise NotImplementedError)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactRecord:
    """Frozen snapshot of a registered pipeline artifact.

    Fields
    ------
    artifact_id  : Unique artifact identifier.
    pipeline_id  : Foreign key to the owning pipeline.
    name         : Human-readable artifact name (unique per pipeline).
    stage        : Pipeline stage that produced this artifact.
    file_path    : Relative or absolute path to the artifact file.
    frozen_hash  : SHA-256 hex digest of content at freeze time (None if not frozen).
    is_frozen    : True once freeze_artifact has been called.
    is_valid     : False when the artifact has been cascade-invalidated.
    created_at   : ISO-8601 UTC timestamp string.
    """

    artifact_id: str
    pipeline_id: str
    name: str
    stage: str
    file_path: str
    frozen_hash: str | None
    is_frozen: bool
    is_valid: bool
    created_at: str


async def register_artifact(
    store: Store,
    pipeline_id: str,
    name: str,
    stage: str,
    file_path: str,
) -> ArtifactRecord:
    """Register a new artifact and return the frozen record.

    Raises
    ------
    ValueError
        If pipeline_id, name, stage, or file_path is empty.
    ValueError
        If an artifact with the same name already exists for this pipeline.
    """
    raise NotImplementedError("register_artifact is not yet implemented")


async def freeze_artifact(
    store: Store,
    pipeline_id: str,
    name: str,
) -> ArtifactRecord:
    """Compute the content hash of an artifact file and mark it frozen.

    A frozen artifact is considered immutable; subsequent writes to the file
    will be detectable via check_staleness.

    Raises
    ------
    ValueError
        If pipeline_id or name is empty.
    KeyError
        If no artifact with the given name exists for this pipeline.
    FileNotFoundError
        If the artifact file does not exist on disk.
    """
    raise NotImplementedError("freeze_artifact is not yet implemented")


async def check_staleness(
    store: Store,
    pipeline_id: str,
    name: str,
) -> bool:
    """Return True if the artifact's current file content differs from its frozen hash.

    Returns False when the content matches (artifact is fresh).

    Raises
    ------
    ValueError
        If pipeline_id or name is empty.
    KeyError
        If no artifact with the given name exists for this pipeline.
    RuntimeError
        If the artifact has not been frozen yet (no baseline hash to compare).
    FileNotFoundError
        If the artifact file does not exist on disk.
    """
    raise NotImplementedError("check_staleness is not yet implemented")


async def cascade_invalidate(
    store: Store,
    pipeline_id: str,
    name: str,
) -> tuple[ArtifactRecord, ...]:
    """Invalidate an artifact and all downstream artifacts from later stages.

    Stage order for cascade purposes: spec -> plan -> implement -> acceptance.
    Any artifact whose stage comes after the invalidated artifact's stage is
    also marked invalid.

    Returns a tuple of all ArtifactRecords that were invalidated (including
    the named artifact itself).

    Raises
    ------
    ValueError
        If pipeline_id or name is empty.
    KeyError
        If no artifact with the given name exists for this pipeline.
    """
    raise NotImplementedError("cascade_invalidate is not yet implemented")
